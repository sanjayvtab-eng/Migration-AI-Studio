from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    MigrationColumn,
    MigrationDependency,
    MigrationMedallionEdge,
    MigrationMedallionNode,
    MigrationMetadataSnapshot,
    MigrationObject,
    MigrationProject,
    MigrationSource,
    MigrationStageArtifact,
    MigrationStageArtifactVersion,
    PromptArtifactRequest,
    PromptClarification,
    PromptPlanApproval,
    PromptSpecification,
    PromptSpecificationVersion,
    RequirementArtifactTrace,
)
from app.services import deployment, environment_provisioning, medallion
from app.services.databricks_client import execute_sql, with_project_databricks
from app.services.engine import qident, uid


ARTIFACT_TYPES = {
    "TABLE_COPY",
    "VIEW",
    "FUNCTION",
    "PROCEDURE_OR_WORKFLOW",
    "DIMENSION",
    "FACT",
    "SUMMARY_VIEW",
}
LAYERS = {"BRONZE", "SILVER", "GOLD"}
TERMINAL_GROUNDING = {"UNKNOWN", "AMBIGUOUS", "NEEDS_INPUT"}


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _snake(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value or "")
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()


def _checksum(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _source(db: Session, project_id: str, prompt: str) -> MigrationSource:
    sources = list(db.scalars(select(MigrationSource).where(MigrationSource.project_id == project_id)).all())
    lowered = prompt.lower()
    matches = [
        row for row in sources
        if (row.database_name and row.database_name.lower() in lowered)
        or (row.profile_name and row.profile_name.lower() in lowered)
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches and len(sources) == 1:
        return sources[0]
    if not sources:
        raise ValueError("No SQL Server source is registered for this project")
    if len(matches) > 1:
        # Repeated registrations for the same database are still ambiguous because
        # their discovery snapshots can differ.
        raise ValueError("The prompt matches more than one registered source; select a source explicitly")
    raise ValueError("The prompt does not identify exactly one registered source")


def _metadata_payload(db: Session, project_id: str, source_id: str) -> dict[str, Any]:
    objects = list(db.scalars(select(MigrationObject).where(
        MigrationObject.project_id == project_id,
        MigrationObject.source_id == source_id,
    ).order_by(MigrationObject.schema_name, MigrationObject.object_name, MigrationObject.object_type)).all())
    result = []
    for obj in objects:
        columns = list(db.scalars(select(MigrationColumn).where(
            MigrationColumn.project_id == project_id,
            MigrationColumn.object_id == obj.id,
        ).order_by(MigrationColumn.ordinal)).all())
        dependencies = list(db.scalars(select(MigrationDependency).where(
            MigrationDependency.project_id == project_id,
            MigrationDependency.object_id == obj.id,
        )).all())
        result.append({
            "object_id": obj.id,
            "schema": obj.schema_name,
            "name": obj.object_name,
            "type": obj.object_type,
            "source_hash": obj.source_hash,
            "columns": [{
                "name": column.column_name,
                "target_name": _snake(column.column_name),
                "ordinal": column.ordinal,
                "data_type": column.data_type,
                "precision": column.precision,
                "scale": column.scale,
                "nullable": column.nullable,
                "is_identity": column.is_identity,
            } for column in columns],
            "dependencies": [{
                "schema": item.referenced_schema,
                "object": item.referenced_object,
                "column": item.referenced_column,
                "type": item.dependency_type,
            } for item in dependencies],
        })
    if not any(item["type"] == "TABLE" for item in result):
        raise ValueError("Discovery does not contain any SQL Server tables for the selected source")
    return {"source_id": source_id, "objects": result}


def _snapshot(db: Session, project_id: str, source_id: str) -> MigrationMetadataSnapshot:
    payload = _metadata_payload(db, project_id, source_id)
    digest = _checksum(payload)
    existing = db.scalar(select(MigrationMetadataSnapshot).where(
        MigrationMetadataSnapshot.project_id == project_id,
        MigrationMetadataSnapshot.source_id == source_id,
        MigrationMetadataSnapshot.content_hash == digest,
    ).order_by(MigrationMetadataSnapshot.created_at.desc()))
    if existing:
        return existing
    row = MigrationMetadataSnapshot(
        id=uid("MDS"), project_id=project_id, source_id=source_id,
        content_hash=digest, payload_json=_json(payload),
    )
    db.add(row)
    db.flush()
    return row


def _tables(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["name"].lower(): item
        for item in snapshot.get("objects", [])
        if item.get("type") == "TABLE"
    }


def _sentence(prompt: str, token: str) -> str:
    for part in re.split(r"(?<=[.;])\s+|\n+", prompt):
        if token.lower() in part.lower():
            return part.strip(" -\t")
    return token


def _named_requests(prompt: str) -> list[str]:
    return list(dict.fromkeys(re.findall(
        r"\b(?:vw|fn|usp|dim|fact|agg)_[A-Za-z][A-Za-z0-9_]*\b",
        prompt,
        re.IGNORECASE,
    )))


def _source_refs_for(name: str, sentence: str, table_map: dict[str, dict[str, Any]]) -> list[str]:
    found = [item["name"] for key, item in table_map.items() if re.search(rf"\b{re.escape(key)}\b", sentence, re.I)]
    lowered = name.lower()
    defaults: dict[str, list[str]] = {
        "vw_customersales": ["Customers", "Orders", "OrderItems"],
        "fn_calculateorderamount": ["OrderItems"],
        "usp_loadcustomersales": ["CustomerSales", "Customers", "Orders", "OrderItems"],
        "usp_loadordersummary": ["OrderSummary", "Orders", "OrderItems"],
        "dim_customer": ["Customers"],
        "dim_product": ["Products"],
        "fact_sales": ["Orders", "OrderItems", "Customers", "Products"],
        "vw_customer_sales_summary": ["Customers", "Orders", "OrderItems"],
        "vw_product_sales_summary": ["Products", "Orders", "OrderItems"],
    }
    for candidate in defaults.get(lowered, []):
        if candidate.lower() in table_map and candidate not in found:
            found.append(candidate)
    return found


def _request_type(name: str) -> tuple[str, str]:
    lowered = name.lower()
    if lowered.startswith("fn_"):
        return "FUNCTION", "SILVER"
    if lowered.startswith("usp_"):
        return "PROCEDURE_OR_WORKFLOW", "SILVER"
    if lowered.startswith("dim_"):
        return "DIMENSION", "GOLD"
    if lowered.startswith("fact_"):
        return "FACT", "GOLD"
    if "summary" in lowered:
        return "SUMMARY_VIEW", "GOLD"
    return "VIEW", "SILVER"


def _canonical_column(table: dict[str, Any], requested: str) -> tuple[str | None, str]:
    exact = [column for column in table["columns"] if column["name"] == requested or column["target_name"] == requested]
    if len(exact) == 1:
        return exact[0]["target_name"], "EXACT"
    canonical = _snake(requested)
    candidates = [column for column in table["columns"] if _snake(column["name"]) == canonical]
    if len(candidates) == 1:
        return candidates[0]["target_name"], "CANONICAL"
    return None, "AMBIGUOUS" if len(candidates) > 1 else "UNKNOWN"


def _required_columns(name: str) -> dict[str, list[str]]:
    rules = {
        "vw_customersales": {
            "Customers": ["CustomerID", "CustomerName", "Country"],
            "Orders": ["OrderID", "CustomerID", "OrderStatus"],
            "OrderItems": ["OrderID", "Quantity", "UnitPrice", "DiscountPercent"],
        },
        "fn_calculateorderamount": {
            "OrderItems": ["OrderID", "Quantity", "UnitPrice", "DiscountPercent"],
        },
        "usp_loadcustomersales": {
            "CustomerSales": ["CustomerID", "CustomerName", "Country", "OrderCount", "TotalSales", "LoadDate"],
            "Customers": ["CustomerID", "CustomerName", "Country"],
            "Orders": ["OrderID", "CustomerID", "OrderStatus"],
            "OrderItems": ["OrderID", "Quantity", "UnitPrice", "DiscountPercent"],
        },
        "usp_loadordersummary": {
            "OrderSummary": ["OrderID", "CustomerID", "OrderDate", "OrderAmount", "LoadDate"],
            "Orders": ["OrderID", "CustomerID", "OrderDate"],
            "OrderItems": ["OrderID", "Quantity", "UnitPrice", "DiscountPercent"],
        },
        "dim_customer": {"Customers": ["CustomerID"]},
        "dim_product": {"Products": ["ProductID"]},
        "fact_sales": {
            "Orders": ["OrderID", "CustomerID", "OrderDate"],
            "OrderItems": ["OrderItemID", "OrderID", "ProductID", "Quantity", "UnitPrice", "DiscountPercent"],
        },
        "vw_customer_sales_summary": {"Customers": ["CustomerID", "CustomerName"], "Orders": ["OrderID", "CustomerID"], "OrderItems": ["OrderID", "Quantity", "UnitPrice"]},
        "vw_product_sales_summary": {"Products": ["ProductID", "ProductName"], "OrderItems": ["ProductID", "Quantity", "UnitPrice"]},
    }
    return rules.get(name.lower(), {})


def _open_questions(prompt: str, names: list[str], table_map: dict[str, dict[str, Any]], answers: dict[str, Any]) -> list[dict[str, Any]]:
    lower_names = {name.lower() for name in names}
    questions = []

    def add(key: str, question: str, affected: list[str], choices: list[str], default: str) -> None:
        if key not in answers:
            questions.append({"key": key, "question": question, "affected": affected, "choices": choices, "recommended": default})

    if any(name in lower_names for name in {"vw_customersales", "usp_loadcustomersales"}) and "orders" in table_map:
        if any(column["target_name"] == "order_status" for column in table_map["orders"]["columns"]):
            add("completed_order_value", "Which source OrderStatus value represents a completed order?", [name for name in names if name.lower() in {"vw_customersales", "usp_loadcustomersales"}], ["COMPLETED", "COMPLETE", "PAID"], "COMPLETED")
    if "usp_loadcustomersales" in lower_names and "customersales" in table_map:
        add("customer_sales_target", "CustomerSales already exists at the source. Which distinct Silver target should the derived loader own?", [name for name in names if name.lower() == "usp_loadcustomersales"], ["customer_sales_derived", "customer_sales_summary"], "customer_sales_derived")
    if "usp_loadordersummary" in lower_names and "ordersummary" in table_map:
        add("order_summary_target", "OrderSummary already exists at the source. Which distinct Silver target should the derived loader own?", [name for name in names if name.lower() == "usp_loadordersummary"], ["order_summary_derived", "daily_order_summary"], "order_summary_derived")
    if any(name.lower().startswith("dim_") for name in names):
        add("dimension_scd_type", "Which slowly changing dimension policy should the generated dimensions use?", [name for name in names if name.lower().startswith("dim_")], ["TYPE_1", "TYPE_2"], "TYPE_1")
    if any(name.lower().startswith("fact_") for name in names):
        add("fact_sales_grain", "What is the approved fact_sales grain?", [name for name in names if name.lower().startswith("fact_")], ["ORDER_ITEM", "ORDER"], "ORDER_ITEM")
    return questions


def _build_requests(prompt: str, snapshot: dict[str, Any], answers: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    table_map = _tables(snapshot)
    requests: list[dict[str, Any]] = []
    sequence = 0

    def add(name: str, artifact_type: str, layer: str, purpose: str, source_refs: list[str], structured: dict[str, Any] | None = None) -> None:
        nonlocal sequence
        sequence += 1
        request_id = f"REQ-{layer[:1]}-{artifact_type[:3]}-{sequence:03d}"
        requests.append({
            "request_id": request_id,
            "name": name,
            "type": artifact_type,
            "layer": layer,
            "purpose": purpose,
            "source_refs": source_refs,
            "structured": structured or {},
            "dependencies": [],
            "identifier_mappings": [],
            "assumptions": [],
            "grounding_status": "PENDING",
            "grounding_errors": [],
        })

    # Bronze is source-driven and includes only tables named in the prompt. If the
    # prompt says "all" or does not list a table after Bronze, include all tables.
    bronze_section = re.search(r"(?is)\bbronze\s*:\s*(.*?)(?=\b(?:silver|gold)\s*:|$)", prompt)
    bronze_text = bronze_section.group(1) if bronze_section else prompt
    selected_tables = [item["name"] for key, item in table_map.items() if re.search(rf"\b{re.escape(key)}\b", bronze_text, re.I)]
    if not selected_tables and re.search(r"(?i)\b(?:all tables|bronze|ingest|migrate)\b", prompt):
        selected_tables = [item["name"] for item in table_map.values()]
    for table_name in selected_tables:
        add(table_name, "TABLE_COPY", "BRONZE", f"Traceable raw copy of dbo.{table_name}", [table_name], {"load_strategy": "FULL_LOAD"})

    clean_match = re.search(r"(?is)clean(?:ed)?\s+views?\s+for\s+(.+?)(?:\s+using\b|[.;\n]|$)", prompt)
    clean_names = []
    if clean_match:
        clean_names = [item["name"] for key, item in table_map.items() if re.search(rf"\b{re.escape(key)}\b", clean_match.group(1), re.I)]
    for table_name in clean_names:
        add(f"vw_{_snake(table_name)}_clean", "VIEW", "SILVER", f"Cleaned and canonically named {table_name} view", [table_name], {"view_kind": "CLEAN"})

    names = _named_requests(prompt)
    for name in names:
        artifact_type, layer = _request_type(name)
        sentence = _sentence(prompt, name)
        refs = _source_refs_for(name, sentence, table_map)
        structured: dict[str, Any] = {"statement": sentence}
        if artifact_type == "FUNCTION":
            structured.update({
                "parameters": [{"name": "p_order_id", "type": "INT"}],
                "returns": "DECIMAL(18,2)",
                "calculation": "SUM(quantity * unit_price * (1 - discount_percent / 100))",
                "filter": "order_id = p_order_id",
            })
        if artifact_type == "PROCEDURE_OR_WORKFLOW":
            structured.update({
                "load_strategy": "MERGE",
                "capability_decision": "PROCEDURE" if get_settings().databricks_sql_procedures_supported else "WORKFLOW_SQL",
            })
        if artifact_type == "DIMENSION":
            structured.update({"scd_type": answers.get("dimension_scd_type", "TYPE_1")})
        if artifact_type == "FACT":
            structured.update({"grain": answers.get("fact_sales_grain", "ORDER_ITEM")})
        add(name, artifact_type, layer, sentence, refs, structured)

    questions = _open_questions(prompt, names, table_map, answers)
    by_name = {request["name"].lower(): request for request in requests}
    bronze_by_source = {request["source_refs"][0].lower(): request for request in requests if request["type"] == "TABLE_COPY"}
    clean_by_source = {request["source_refs"][0].lower(): request for request in requests if request["structured"].get("view_kind") == "CLEAN"}

    for request in requests:
        errors: list[str] = []
        mappings = []
        for source_ref in request["source_refs"]:
            table = table_map.get(source_ref.lower())
            if not table:
                errors.append(f"Unknown source table {source_ref}")
                continue
            for requested in _required_columns(request["name"]).get(source_ref, []):
                target, method = _canonical_column(table, requested)
                if not target:
                    errors.append(f"{method}: {source_ref}.{requested}")
                else:
                    mappings.append({
                        "source": f"dbo.{source_ref}.{requested}",
                        "target": f"{_snake(source_ref)}.{target}",
                        "method": method,
                    })
        request["identifier_mappings"] = mappings
        if errors:
            request["grounding_status"] = "UNKNOWN" if any(item.startswith("UNKNOWN") or item.startswith("Unknown") for item in errors) else "AMBIGUOUS"
            request["grounding_errors"] = errors
        else:
            request["grounding_status"] = "GROUNDED"

        dependencies = []
        if request["type"] != "TABLE_COPY":
            for source_ref in request["source_refs"]:
                clean = clean_by_source.get(source_ref.lower())
                # A clean view depends on its Bronze copy. Other consumers use
                # the clean view when one exists, otherwise the Bronze copy.
                upstream = (
                    bronze_by_source.get(source_ref.lower())
                    if clean and clean["request_id"] == request["request_id"]
                    else clean or bronze_by_source.get(source_ref.lower())
                )
                if upstream and upstream["request_id"] != request["request_id"]:
                    dependencies.append(upstream["request_id"])
        lowered = request["name"].lower()
        if lowered in {"vw_customer_sales_summary", "vw_product_sales_summary"} and "fact_sales" in by_name:
            dependencies.append(by_name["fact_sales"]["request_id"])
        if lowered == "fact_sales":
            for target in ("dim_customer", "dim_product"):
                if target in by_name:
                    dependencies.append(by_name[target]["request_id"])
        request["dependencies"] = list(dict.fromkeys(dependencies))

        if request["type"] == "PROCEDURE_OR_WORKFLOW" and not get_settings().databricks_sql_procedures_supported:
            request["assumptions"].append("Configured target does not declare SQL procedure support; generate governed workflow SQL")
        if request["type"] == "DIMENSION":
            request["assumptions"].append(f"SCD policy: {answers.get('dimension_scd_type', 'TYPE_1')}")
        if request["type"] == "FACT":
            request["assumptions"].append(f"Fact grain: {answers.get('fact_sales_grain', 'ORDER_ITEM')}")

    affected = {request_id for question in questions for request_id in question["affected"]}
    for request in requests:
        if request["name"] in affected and request["grounding_status"] == "GROUNDED":
            request["grounding_status"] = "NEEDS_INPUT"
    return requests, questions


def _validate_dag(requests: list[dict[str, Any]]) -> list[str]:
    ids = {item["request_id"] for item in requests}
    indegree = {item["request_id"]: 0 for item in requests}
    graph: dict[str, list[str]] = defaultdict(list)
    errors = []
    for item in requests:
        for dependency in item["dependencies"]:
            if dependency not in ids:
                errors.append(f"{item['request_id']} has unknown dependency {dependency}")
                continue
            graph[dependency].append(item["request_id"])
            indegree[item["request_id"]] += 1
    queue = deque(sorted(key for key, value in indegree.items() if value == 0))
    visited = []
    while queue:
        key = queue.popleft()
        visited.append(key)
        for target in graph[key]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(visited) != len(requests):
        errors.append("Artifact dependency graph contains a cycle")
    return errors


def _persist_version(
    db: Session,
    spec: PromptSpecification,
    *,
    prompt: str,
    snapshot: MigrationMetadataSnapshot,
    actor: str,
    answers: dict[str, Any],
) -> PromptSpecificationVersion:
    snapshot_payload = _loads(snapshot.payload_json, {})
    requests, questions = _build_requests(prompt, snapshot_payload, answers)
    if not requests:
        raise ValueError("The prompt does not contain any supported Bronze, Silver, or Gold artifact request")
    dag_errors = _validate_dag(requests)
    if dag_errors:
        raise ValueError("; ".join(dag_errors))
    next_version = int(db.scalar(select(func.max(PromptSpecificationVersion.version)).where(
        PromptSpecificationVersion.specification_id == spec.id,
    )) or 0) + 1
    parsed = {
        "specification_version": next_version,
        "source_id": spec.source_id,
        "target_environment": spec.target_environment,
        "metadata_snapshot_id": snapshot.id,
        "answers": answers,
        "artifacts": requests,
    }
    version = PromptSpecificationVersion(
        id=uid("PSV"), project_id=spec.project_id, specification_id=spec.id,
        version=next_version, original_prompt=prompt, parsed_json=_json(parsed),
        metadata_snapshot_id=snapshot.id, checksum=_checksum(parsed), created_by=actor,
    )
    db.add(version)
    db.flush()
    for item in requests:
        db.add(PromptArtifactRequest(
            id=uid("PAR"), project_id=spec.project_id, spec_version_id=version.id,
            request_id=item["request_id"], name=item["name"], artifact_type=item["type"],
            layer=item["layer"], structured_json=_json({"purpose": item["purpose"], **item["structured"], "grounding_errors": item["grounding_errors"]}),
            grounding_status=item["grounding_status"], source_refs_json=_json(item["source_refs"]),
            dependencies_json=_json(item["dependencies"]), identifier_mappings_json=_json(item["identifier_mappings"]),
            assumptions_json=_json(item["assumptions"]),
        ))
    for question in questions:
        db.add(PromptClarification(
            id=uid("PCL"), project_id=spec.project_id, spec_version_id=version.id,
            question_key=question["key"], question=question["question"],
            affected_request_ids_json=_json(question["affected"]), choices_json=_json(question["choices"]),
            answer_json=None, status="OPEN",
        ))
    spec.current_version_id = version.id
    if questions:
        spec.current_status = "NEEDS_USER_INPUT"
    elif any(item["grounding_status"] in TERMINAL_GROUNDING for item in requests):
        spec.current_status = "NEEDS_USER_INPUT"
    else:
        spec.current_status = "PENDING_PLAN_APPROVAL"
    db.commit()
    return version


def submit(db: Session, project_id: str, prompt: str, actor: str) -> dict[str, Any]:
    if not get_settings().prompt_native_design_enabled:
        raise PermissionError("Prompt-native artifact design is disabled")
    if not prompt or not prompt.strip():
        raise ValueError("A business prompt is required")
    if not db.get(MigrationProject, project_id):
        raise LookupError("Project not found")
    source = _source(db, project_id, prompt)
    plan = environment_provisioning.get_dev_plan(db, project_id)
    if not plan or plan.status != "PROVISIONED":
        raise ValueError("The Databricks DEV environment must be provisioned before prompt design")
    snapshot = _snapshot(db, project_id, source.id)
    spec = PromptSpecification(
        id=uid("PSP"), project_id=project_id, source_id=source.id,
        target_environment="DEV", current_status="PARSING", created_by=actor,
    )
    db.add(spec)
    db.flush()
    _persist_version(db, spec, prompt=prompt.strip(), snapshot=snapshot, actor=actor, answers={})
    return detail(db, project_id, spec.id)


def _current_version(db: Session, spec: PromptSpecification) -> PromptSpecificationVersion:
    version = db.get(PromptSpecificationVersion, spec.current_version_id)
    if not version or version.project_id != spec.project_id:
        raise RuntimeError("Prompt specification current version is missing")
    return version


def _request_view(row: PromptArtifactRequest) -> dict[str, Any]:
    structured = _loads(row.structured_json, {})
    return {
        "id": row.id, "request_id": row.request_id, "name": row.name,
        "type": row.artifact_type, "layer": row.layer,
        "purpose": structured.pop("purpose", ""), "requirements": structured,
        "grounding_status": row.grounding_status,
        "source_refs": _loads(row.source_refs_json, []),
        "dependencies": _loads(row.dependencies_json, []),
        "identifier_mappings": _loads(row.identifier_mappings_json, []),
        "assumptions": _loads(row.assumptions_json, []),
    }


def detail(db: Session, project_id: str, specification_id: str) -> dict[str, Any]:
    spec = db.get(PromptSpecification, specification_id)
    if not spec or spec.project_id != project_id:
        raise LookupError("Prompt specification not found in project")
    version = _current_version(db, spec)
    requests = list(db.scalars(select(PromptArtifactRequest).where(
        PromptArtifactRequest.project_id == project_id,
        PromptArtifactRequest.spec_version_id == version.id,
    ).order_by(PromptArtifactRequest.layer, PromptArtifactRequest.request_id)).all())
    questions = list(db.scalars(select(PromptClarification).where(
        PromptClarification.project_id == project_id,
        PromptClarification.spec_version_id == version.id,
    ).order_by(PromptClarification.asked_at)).all())
    approval = db.scalars(select(PromptPlanApproval).where(
        PromptPlanApproval.project_id == project_id,
        PromptPlanApproval.spec_version_id == version.id,
    ).order_by(PromptPlanApproval.reviewed_at.desc())).first()
    return {
        "id": spec.id, "project_id": project_id, "status": spec.current_status,
        "source_id": spec.source_id, "target_environment": spec.target_environment,
        "version": version.version, "version_id": version.id,
        "prompt": version.original_prompt, "metadata_snapshot_id": version.metadata_snapshot_id,
        "checksum": version.checksum,
        "artifacts": [_request_view(row) for row in requests],
        "clarifications": [{
            "id": row.id, "key": row.question_key, "question": row.question,
            "affected_request_ids": _loads(row.affected_request_ids_json, []),
            "choices": _loads(row.choices_json, []), "answer": _loads(row.answer_json, None),
            "status": row.status,
        } for row in questions],
        "approval": None if not approval else {
            "status": approval.status, "reviewer": approval.reviewer,
            "comment": approval.comment, "reviewed_at": approval.reviewed_at,
        },
    }


def answer_clarifications(
    db: Session, project_id: str, specification_id: str,
    answers: dict[str, Any], actor: str,
) -> dict[str, Any]:
    spec = db.get(PromptSpecification, specification_id)
    if not spec or spec.project_id != project_id:
        raise LookupError("Prompt specification not found in project")
    previous = _current_version(db, spec)
    previous_payload = _loads(previous.parsed_json, {})
    merged = {**previous_payload.get("answers", {}), **answers}
    open_rows = list(db.scalars(select(PromptClarification).where(
        PromptClarification.spec_version_id == previous.id,
        PromptClarification.project_id == project_id,
        PromptClarification.status == "OPEN",
    )).all())
    allowed = {row.question_key for row in open_rows}
    unknown = sorted(set(answers) - allowed)
    if unknown:
        raise ValueError("Unknown or already answered clarification key(s): " + ", ".join(unknown))
    missing = sorted(allowed - set(answers))
    if missing:
        raise ValueError("Answers are required for all open clarifications: " + ", ".join(missing))
    now = datetime.utcnow()
    for row in open_rows:
        row.answer_json = _json(answers[row.question_key])
        row.status = "ANSWERED"
        row.answered_at = now
        row.answered_by = actor
    # Any prior approval is immutable but no longer current; the new version starts unapproved.
    snapshot = db.get(MigrationMetadataSnapshot, previous.metadata_snapshot_id)
    if not snapshot:
        raise RuntimeError("Bound metadata snapshot is missing")
    _persist_version(db, spec, prompt=previous.original_prompt, snapshot=snapshot, actor=actor, answers=merged)
    return detail(db, project_id, specification_id)


def plan(db: Session, project_id: str, specification_id: str) -> dict[str, Any]:
    result = detail(db, project_id, specification_id)
    by_layer = {layer: [] for layer in ("BRONZE", "SILVER", "GOLD")}
    for item in result["artifacts"]:
        by_layer[item["layer"]].append(item)
    return {
        "specification_id": specification_id, "version": result["version"],
        "version_id": result["version_id"], "status": result["status"],
        "metadata_snapshot_id": result["metadata_snapshot_id"],
        "layers": by_layer,
        "dependency_order": _topological_requests(result["artifacts"]),
        "blocking_questions": [item for item in result["clarifications"] if item["status"] == "OPEN"],
        "grounding_blockers": [
            {"request_id": item["request_id"], "name": item["name"], "status": item["grounding_status"], "errors": item["requirements"].get("grounding_errors", [])}
            for item in result["artifacts"] if item["grounding_status"] != "GROUNDED"
        ],
    }


def _topological_requests(requests: list[dict[str, Any]]) -> list[str]:
    by_id = {item["request_id"]: item for item in requests}
    indegree = {key: 0 for key in by_id}
    graph: dict[str, list[str]] = defaultdict(list)
    for item in requests:
        for dependency in item["dependencies"]:
            if dependency in by_id:
                graph[dependency].append(item["request_id"])
                indegree[item["request_id"]] += 1
    ready = sorted((key for key, value in indegree.items() if value == 0), key=lambda key: ({"BRONZE": 1, "SILVER": 2, "GOLD": 3}[by_id[key]["layer"]], key))
    ordered = []
    while ready:
        key = ready.pop(0)
        ordered.append(key)
        for target in graph[key]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=lambda value: ({"BRONZE": 1, "SILVER": 2, "GOLD": 3}[by_id[value]["layer"]], value))
    if len(ordered) != len(by_id):
        raise ValueError("Artifact dependency graph contains a cycle")
    return ordered


def approve_plan(db: Session, project_id: str, specification_id: str, actor: str, status: str, comment: str | None = None) -> dict[str, Any]:
    spec = db.get(PromptSpecification, specification_id)
    if not spec or spec.project_id != project_id:
        raise LookupError("Prompt specification not found in project")
    version = _current_version(db, spec)
    state = status.upper().strip()
    if state not in {"APPROVED", "REJECTED", "CHANGES_REQUIRED"}:
        raise ValueError("status must be APPROVED, REJECTED or CHANGES_REQUIRED")
    if state == "APPROVED":
        if spec.current_status != "PENDING_PLAN_APPROVAL":
            raise ValueError("Only a fully grounded current plan can be approved")
        blockers = list(db.scalars(select(PromptArtifactRequest).where(
            PromptArtifactRequest.spec_version_id == version.id,
            PromptArtifactRequest.grounding_status != "GROUNDED",
        )).all())
        if blockers:
            raise ValueError("Plan approval is blocked until every artifact is grounded")
    if state in {"REJECTED", "CHANGES_REQUIRED"} and not (comment or "").strip():
        raise ValueError("A comment is required when rejecting or requesting changes")
    db.add(PromptPlanApproval(
        id=uid("PPA"), project_id=project_id, spec_version_id=version.id,
        status=state, reviewer=actor, comment=comment,
    ))
    spec.current_status = "PLAN_APPROVED" if state == "APPROVED" else state
    db.commit()
    return detail(db, project_id, specification_id)


def _catalog(db: Session, project_id: str) -> str:
    row = environment_provisioning.get_dev_plan(db, project_id)
    if not row or row.status != "PROVISIONED":
        raise ValueError("DEV environment is not provisioned")
    return row.catalog_name


def _fqn(catalog: str, layer: str, name: str) -> str:
    return f"{qident(catalog)}.{qident(layer.lower())}.{qident(_snake(name))}"


def _source_object(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [item for item in snapshot.get("objects", []) if item.get("type") == "TABLE" and item.get("name", "").lower() == name.lower()]
    if len(matches) != 1:
        raise ValueError(f"Grounded source table {name} is unavailable in the bound snapshot")
    return matches[0]


def _clean_view_sql(catalog: str, request: dict[str, Any], snapshot: dict[str, Any]) -> str:
    table = _source_object(snapshot, request["source_refs"][0])
    select_list = ",\n  ".join(
        f"{qident(column['name'])} AS {qident(column['target_name'])}"
        if column["name"] != column["target_name"] else qident(column["name"])
        for column in table["columns"]
    )
    return f"CREATE OR REPLACE VIEW {_fqn(catalog, 'silver', request['name'])} AS\nSELECT\n  {select_list}\nFROM {_fqn(catalog, 'bronze', table['name'])};"


def _bronze_sql(catalog: str, request: dict[str, Any], snapshot: dict[str, Any]) -> str:
    table = _source_object(snapshot, request["source_refs"][0])
    definitions = []
    for column in table["columns"]:
        dtype = str(column["data_type"]).upper()
        if dtype in {"VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "TEXT"}:
            dtype = "STRING"
        elif dtype in {"DATETIME", "DATETIME2", "SMALLDATETIME"}:
            dtype = "TIMESTAMP"
        elif dtype == "BIT":
            dtype = "BOOLEAN"
        elif dtype in {"MONEY", "SMALLMONEY"}:
            dtype = "DECIMAL(19,4)"
        elif dtype == "DECIMAL" and column.get("precision"):
            dtype = f"DECIMAL({column['precision']},{column.get('scale') or 0})"
        definitions.append(f"  {qident(column['name'])} {dtype}" + ("" if column["nullable"] else " NOT NULL"))
    definitions.extend(["  `_migration_ingested_at` TIMESTAMP", "  `_migration_source_system` STRING"])
    return f"CREATE TABLE IF NOT EXISTS {_fqn(catalog, 'bronze', table['name'])} (\n" + ",\n".join(definitions) + "\n) USING DELTA;"


def _customer_sales_select(catalog: str, completed: str) -> str:
    return f"""SELECT
  c.customer_id,
  c.customer_name,
  c.country,
  COUNT(DISTINCT o.order_id) AS order_count,
  CAST(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100)) AS DECIMAL(18,2)) AS total_sales,
  current_timestamp() AS load_date
FROM {_fqn(catalog, 'silver', 'vw_customers_clean')} c
JOIN {_fqn(catalog, 'silver', 'vw_orders_clean')} o ON o.customer_id = c.customer_id
JOIN {_fqn(catalog, 'silver', 'vw_order_items_clean')} oi ON oi.order_id = o.order_id
WHERE o.order_status = '{completed.replace("'", "''")}'
GROUP BY c.customer_id, c.customer_name, c.country"""


def _order_summary_select(catalog: str) -> str:
    return f"""SELECT
  o.order_id,
  o.customer_id,
  CAST(o.order_date AS DATE) AS order_date,
  CAST(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100)) AS DECIMAL(18,2)) AS order_amount,
  current_timestamp() AS load_date
FROM {_fqn(catalog, 'silver', 'vw_orders_clean')} o
JOIN {_fqn(catalog, 'silver', 'vw_order_items_clean')} oi ON oi.order_id = o.order_id
GROUP BY o.order_id, o.customer_id, CAST(o.order_date AS DATE)"""


def _merge_workflow(target: str, select_sql: str, keys: list[str], columns: list[str]) -> str:
    create = f"CREATE TABLE IF NOT EXISTS {target} USING DELTA AS\nSELECT * FROM (\n{select_sql}\n) source WHERE 1 = 0"
    on_clause = " AND ".join(f"target.{qident(key)} = source.{qident(key)}" for key in keys)
    updates = ",\n    ".join(f"target.{qident(column)} = source.{qident(column)}" for column in columns if column not in keys)
    insert_columns = ", ".join(qident(column) for column in columns)
    insert_values = ", ".join(f"source.{qident(column)}" for column in columns)
    merge = f"""MERGE INTO {target} target
USING (
{select_sql}
) source
ON {on_clause}
WHEN MATCHED THEN UPDATE SET
    {updates}
WHEN NOT MATCHED THEN INSERT ({insert_columns})
VALUES ({insert_values})"""
    return create + ";\n" + merge + ";"


def _sql_for(request: dict[str, Any], catalog: str, snapshot: dict[str, Any], answers: dict[str, Any]) -> tuple[str, str]:
    name = request["name"]
    lowered = name.lower()
    if request["type"] == "TABLE_COPY":
        return _bronze_sql(catalog, request, snapshot), "DELTA_TABLE"
    if request["requirements"].get("view_kind") == "CLEAN":
        return _clean_view_sql(catalog, request, snapshot), "VIEW"
    if lowered == "vw_customersales":
        select_sql = _customer_sales_select(catalog, str(answers.get("completed_order_value", "COMPLETED")))
        return f"CREATE OR REPLACE VIEW {_fqn(catalog, 'silver', name)} AS\n{select_sql};", "VIEW"
    if lowered == "fn_calculateorderamount":
        sql = f"""CREATE OR REPLACE FUNCTION {_fqn(catalog, 'silver', name)}(p_order_id INT)
RETURNS DECIMAL(18,2)
LANGUAGE SQL
READS SQL DATA
RETURN COALESCE((
  SELECT SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100))
  FROM {_fqn(catalog, 'silver', 'vw_order_items_clean')} oi
  WHERE oi.order_id = p_order_id
), CAST(0 AS DECIMAL(18,2)));"""
        return sql, "SQL_FUNCTION"
    if lowered == "usp_loadcustomersales":
        target = _fqn(catalog, "silver", str(answers.get("customer_sales_target", "customer_sales_derived")))
        return _merge_workflow(target, _customer_sales_select(catalog, str(answers.get("completed_order_value", "COMPLETED"))), ["customer_id"], ["customer_id", "customer_name", "country", "order_count", "total_sales", "load_date"]), "WORKFLOW_SQL"
    if lowered == "usp_loadordersummary":
        target = _fqn(catalog, "silver", str(answers.get("order_summary_target", "order_summary_derived")))
        return _merge_workflow(target, _order_summary_select(catalog), ["order_id"], ["order_id", "customer_id", "order_date", "order_amount", "load_date"]), "WORKFLOW_SQL"
    if lowered == "dim_customer":
        sql = f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', name)} AS\nSELECT customer_id, customer_name, country, city, state, customer_status\nFROM {_fqn(catalog, 'silver', 'vw_customers_clean')};"
        return sql, "SEMANTIC_MODEL"
    if lowered == "dim_product":
        sql = f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', name)} AS\nSELECT product_id, product_name, category, sub_category, unit_price, cost_price, product_status\nFROM {_fqn(catalog, 'silver', 'vw_products_clean')};"
        return sql, "SEMANTIC_MODEL"
    if lowered == "fact_sales":
        sql = f"""CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', name)} AS
SELECT
  oi.order_item_id,
  o.order_id,
  o.customer_id,
  oi.product_id,
  CAST(o.order_date AS DATE) AS order_date,
  oi.quantity,
  oi.unit_price,
  oi.discount_percent,
  CAST(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100) AS DECIMAL(18,2)) AS sales_amount
FROM {_fqn(catalog, 'silver', 'vw_orders_clean')} o
JOIN {_fqn(catalog, 'silver', 'vw_order_items_clean')} oi ON oi.order_id = o.order_id;"""
        return sql, "SEMANTIC_MODEL"
    if lowered == "vw_customer_sales_summary":
        return f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', name)} AS\nSELECT customer_id, COUNT(DISTINCT order_id) AS order_count, SUM(sales_amount) AS total_sales\nFROM {_fqn(catalog, 'gold', 'fact_sales')}\nGROUP BY customer_id;", "VIEW"
    if lowered == "vw_product_sales_summary":
        return f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', name)} AS\nSELECT product_id, SUM(quantity) AS units_sold, SUM(sales_amount) AS total_sales\nFROM {_fqn(catalog, 'gold', 'fact_sales')}\nGROUP BY product_id;", "VIEW"
    # Generic prompt-native views use explicit grounded columns from their first source.
    if request["type"] in {"VIEW", "SUMMARY_VIEW"} and request["source_refs"]:
        table = _source_object(snapshot, request["source_refs"][0])
        columns = ", ".join(qident(column["target_name"]) for column in table["columns"])
        source_name = f"vw_{_snake(table['name'])}_clean"
        return f"CREATE OR REPLACE VIEW {_fqn(catalog, request['layer'], name)} AS\nSELECT {columns}\nFROM {_fqn(catalog, 'silver', source_name)};", "VIEW"
    raise ValueError(f"No deterministic generator is available for {request['type']} {name}")


def _sql_issues(content: str, node_type: str) -> list[str]:
    errors = []
    upper = content.upper()
    if content.count("(") != content.count(")"):
        errors.append("Unbalanced SQL parentheses")
    if "[" in content or "]" in content:
        errors.append("SQL Server bracket identifiers are not permitted")
    if re.search(r"(?i)\b(?:fn_[A-Za-z0-9_]+)\s*\.\s*`?p?order_id`?", content):
        errors.append("Function parameters must use their unqualified p_ namespace")
    if node_type == "SQL_FUNCTION" and not re.search(r"(?i)\bp_[A-Za-z0-9_]+\b", content):
        errors.append("Function parameters must use a distinct p_ namespace")
    if node_type == "WORKFLOW_SQL":
        if "MERGE INTO" not in upper:
            errors.append("Loader workflow must use MERGE")
        if re.search(r"(?is)WHEN\s+NOT\s+MATCHED\s+BY\s+SOURCE\s+THEN\s+DELETE", content):
            errors.append("Loader workflow cannot delete rows absent from the current source batch")
    if node_type == "SQL_PROCEDURE" and re.search(r"(?i)\b(?:READS SQL DATA|CONTAINS SQL)\b", content):
        errors.append("Databricks procedure contains an unsupported function-only clause")
    for token in ("DROP CATALOG", "DROP SCHEMA", "TRUNCATE TABLE"):
        if token in upper:
            errors.append(f"Governed statement is not permitted: {token}")
    return errors


def generate(db: Session, project_id: str, specification_id: str, actor: str) -> dict[str, Any]:
    spec = db.get(PromptSpecification, specification_id)
    if not spec or spec.project_id != project_id:
        raise LookupError("Prompt specification not found in project")
    if spec.current_status != "PLAN_APPROVED":
        raise ValueError("The current prompt plan must be approved before generation")
    version = _current_version(db, spec)
    approval = db.scalars(select(PromptPlanApproval).where(
        PromptPlanApproval.spec_version_id == version.id,
        PromptPlanApproval.status == "APPROVED",
    ).order_by(PromptPlanApproval.reviewed_at.desc())).first()
    if not approval:
        raise ValueError("The current prompt plan version has no approval")
    snapshot_row = db.get(MigrationMetadataSnapshot, version.metadata_snapshot_id)
    if not snapshot_row:
        raise RuntimeError("Bound metadata snapshot is missing")
    snapshot = _loads(snapshot_row.payload_json, {})
    parsed = _loads(version.parsed_json, {})
    answers = parsed.get("answers", {})
    requests = [_request_view(row) for row in db.scalars(select(PromptArtifactRequest).where(
        PromptArtifactRequest.spec_version_id == version.id,
        PromptArtifactRequest.project_id == project_id,
    )).all()]
    ordered_ids = _topological_requests(requests)
    by_id = {item["request_id"]: item for item in requests}
    catalog = _catalog(db, project_id)
    spec.current_status = "GENERATING_ARTIFACTS"
    db.commit()
    generated = []
    node_by_request: dict[str, MigrationMedallionNode] = {}
    try:
        for request_id in ordered_ids:
            request = by_id[request_id]
            content, node_type = _sql_for(request, catalog, snapshot, answers)
            errors = _sql_issues(content, node_type)
            target_fqn = _fqn(catalog, request["layer"], request["name"])
            if node_type == "WORKFLOW_SQL":
                # The artifact represents a requested loader name even though the
                # generated statements target the approved derived table.
                target_fqn = _fqn(catalog, request["layer"], request["name"])
            node = db.scalar(select(MigrationMedallionNode).where(
                MigrationMedallionNode.project_id == project_id,
                MigrationMedallionNode.environment == "DEV",
                MigrationMedallionNode.target_fqn == target_fqn,
            ))
            source_obj = None
            if len(request["source_refs"]) == 1:
                source_obj = next((item for item in snapshot["objects"] if item["type"] == "TABLE" and item["name"].lower() == request["source_refs"][0].lower()), None)
            if not node:
                node = MigrationMedallionNode(
                    id=uid("MDN"), project_id=project_id,
                    source_object_id=source_obj.get("object_id") if source_obj else None,
                    semantic_definition_id=None, environment="DEV", layer=request["layer"],
                    node_type=node_type, model_role=request["type"], target_name=request["name"],
                    target_fqn=target_fqn, generation_strategy="PROMPT_NATIVE",
                    confidence_score=1.0, status="VALIDATING", review_required=True,
                    lineage_json=_json({"specification_id": spec.id, "spec_version_id": version.id, "request_id": request_id}),
                    transformation_json=_json(request["requirements"]),
                )
                db.add(node)
                db.flush()
            else:
                node.node_type = node_type
                node.model_role = request["type"]
                node.generation_strategy = "PROMPT_NATIVE"
                node.lineage_json = _json({"specification_id": spec.id, "spec_version_id": version.id, "request_id": request_id})
                node.transformation_json = _json(request["requirements"])
                node.status = "VALIDATING"
                node.review_required = True
            node_by_request[request_id] = node
            artifact = db.scalar(select(MigrationStageArtifact).where(
                MigrationStageArtifact.project_id == project_id,
                MigrationStageArtifact.node_id == node.id,
            ))
            if not artifact:
                artifact = MigrationStageArtifact(
                    id=uid("MSA"), project_id=project_id, node_id=node.id,
                    artifact_type=request["type"], current_version=0,
                )
                db.add(artifact)
                db.flush()
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            current = db.scalar(select(MigrationStageArtifactVersion).where(
                MigrationStageArtifactVersion.project_id == project_id,
                MigrationStageArtifactVersion.artifact_id == artifact.id,
                MigrationStageArtifactVersion.content_hash == digest,
            ).order_by(MigrationStageArtifactVersion.version.desc()))
            if current:
                artifact.current_version = current.version
                current.review_status = "PENDING_REVIEW"
                current.reviewer = None
                current.reviewed_at = None
            else:
                current = MigrationStageArtifactVersion(
                    id=uid("MSV"), project_id=project_id, artifact_id=artifact.id, node_id=node.id,
                    version=artifact.current_version + 1, content=content, content_hash=digest,
                    executable=not errors and not get_settings().prompt_target_validation_required,
                    validation_status="FAILED" if errors else ("PASSED" if not get_settings().prompt_target_validation_required else "TARGET_VALIDATION_REQUIRED"),
                    validation_json=_json({
                        "errors": errors, "deterministic_checks": ["PROMPT_SCHEMA", "METADATA_GROUNDING", "TARGET_CAPABILITY", "IDENTIFIER_BINDING", "IDEMPOTENCY"],
                        "metadata_snapshot_id": snapshot_row.id, "specification_version_id": version.id,
                        "target_validation_required": get_settings().prompt_target_validation_required,
                    }),
                    review_status="PENDING_REVIEW", generator_version="prompt-native-7.0",
                )
                db.add(current)
                db.flush()
                artifact.current_version = current.version
            node.status = "REVIEW_REQUIRED" if errors else "TARGET_VALIDATION_REQUIRED" if get_settings().prompt_target_validation_required else "ARTIFACT_READY"
            trace = db.scalar(select(RequirementArtifactTrace).where(
                RequirementArtifactTrace.spec_version_id == version.id,
                RequirementArtifactTrace.request_id == request_id,
            ))
            if not trace:
                trace = RequirementArtifactTrace(
                    id=uid("RAT"), project_id=project_id, specification_id=spec.id,
                    spec_version_id=version.id, request_id=request_id,
                )
                db.add(trace)
            trace.node_id = node.id
            trace.artifact_id = artifact.id
            trace.artifact_version_id = current.id
            trace.evidence_json = _json({
                "metadata_snapshot_id": snapshot_row.id, "plan_approval_id": approval.id,
                "identifier_mappings": request["identifier_mappings"], "assumptions": request["assumptions"],
            })
            generated.append({
                "request_id": request_id, "name": request["name"], "target_fqn": target_fqn,
                "artifact_version_id": current.id, "validation_status": current.validation_status,
                "executable": current.executable, "errors": errors,
            })
        db.execute(delete(MigrationMedallionEdge).where(
            MigrationMedallionEdge.project_id == project_id,
            MigrationMedallionEdge.environment == "DEV",
            MigrationMedallionEdge.edge_type == "PROMPT_REQUIREMENT",
        ))
        for request in requests:
            for dependency in request["dependencies"]:
                upstream = node_by_request.get(dependency)
                downstream = node_by_request.get(request["request_id"])
                if not upstream or not downstream:
                    continue
                edge = db.scalar(select(MigrationMedallionEdge).where(
                    MigrationMedallionEdge.project_id == project_id,
                    MigrationMedallionEdge.environment == "DEV",
                    MigrationMedallionEdge.from_node_id == upstream.id,
                    MigrationMedallionEdge.to_node_id == downstream.id,
                    MigrationMedallionEdge.edge_type == "PROMPT_REQUIREMENT",
                ))
                if not edge:
                    db.add(MigrationMedallionEdge(
                        id=uid("MDE"), project_id=project_id, environment="DEV",
                        from_node_id=upstream.id, to_node_id=downstream.id,
                        edge_type="PROMPT_REQUIREMENT", evidence_json=_json({"spec_version_id": version.id}),
                    ))
        spec.current_status = "VALIDATING" if get_settings().prompt_target_validation_required else "PENDING_ARTIFACT_REVIEW"
        db.commit()
    except Exception:
        spec.current_status = "GENERATION_FAILED"
        db.commit()
        raise
    return {"specification_id": spec.id, "version": version.version, "status": spec.current_status, "generated": generated}


def _probe_sql(content: str, node_type: str) -> list[str]:
    if node_type == "DELTA_TABLE":
        return []  # Bronze is validated by the existing ingestion preflight and deployment evidence.
    if node_type == "WORKFLOW_SQL":
        statements = [part.strip() for part in content.split(";\n") if part.strip()]
        merge = next((part for part in statements if part.upper().startswith("MERGE INTO")), None)
        return ["EXPLAIN " + merge] if merge else []
    match = re.search(r"(?is)\bAS\s+(SELECT\b.*);?\s*$", content)
    if match:
        return ["EXPLAIN " + match.group(1).rstrip(";")]
    function_body = re.search(r"(?is)\bRETURN\s+(.*);\s*$", content)
    if function_body:
        expression = function_body.group(1).strip()
        return ["EXPLAIN SELECT " + expression]
    return ["EXPLAIN " + content.rstrip(";")]


@with_project_databricks
def validate_target(db: Session, project_id: str, specification_id: str) -> dict[str, Any]:
    spec = db.get(PromptSpecification, specification_id)
    if not spec or spec.project_id != project_id:
        raise LookupError("Prompt specification not found in project")
    if spec.current_status not in {"VALIDATING", "TARGET_VALIDATION_FAILED", "PENDING_ARTIFACT_REVIEW"}:
        raise ValueError("Generate the approved current plan before target validation")
    version = _current_version(db, spec)
    traces = list(db.scalars(select(RequirementArtifactTrace).where(
        RequirementArtifactTrace.project_id == project_id,
        RequirementArtifactTrace.spec_version_id == version.id,
    )).all())
    results = []
    any_failed = False
    for trace in traces:
        artifact_version = db.get(MigrationStageArtifactVersion, trace.artifact_version_id)
        node = db.get(MigrationMedallionNode, trace.node_id)
        if not artifact_version or not node:
            any_failed = True
            results.append({"request_id": trace.request_id, "status": "FAILED", "error": "Trace artifact is missing"})
            continue
        evidence = _loads(artifact_version.validation_json, {})
        errors = _sql_issues(artifact_version.content, node.node_type)
        probes = _probe_sql(artifact_version.content, node.node_type)
        probe_evidence = []
        if not errors:
            for statement in probes:
                try:
                    rows = execute_sql(statement, safe_retry=True)
                    probe_evidence.append({"statement_hash": hashlib.sha256(statement.encode()).hexdigest(), "status": "PASSED", "rows": len(rows or [])})
                except Exception as exc:
                    errors.append(str(exc))
                    probe_evidence.append({"statement_hash": hashlib.sha256(statement.encode()).hexdigest(), "status": "FAILED", "error": str(exc)})
                    break
        artifact_version.executable = not errors
        artifact_version.validation_status = "PASSED" if not errors else "FAILED"
        evidence.update({"errors": errors, "target_validation": probe_evidence, "target_validated_at": datetime.utcnow().isoformat()})
        artifact_version.validation_json = _json(evidence)
        node.status = "ARTIFACT_READY" if not errors else "REVIEW_REQUIRED"
        any_failed = any_failed or bool(errors)
        results.append({"request_id": trace.request_id, "artifact_version_id": artifact_version.id, "status": artifact_version.validation_status, "errors": errors})
    spec.current_status = "TARGET_VALIDATION_FAILED" if any_failed else "PENDING_ARTIFACT_REVIEW"
    db.commit()
    return {"specification_id": spec.id, "version": version.version, "status": spec.current_status, "artifacts": results}


def review_artifact(db: Session, project_id: str, specification_id: str, artifact_version_id: str, status: str, actor: str, comment: str | None = None) -> dict[str, Any]:
    spec = db.get(PromptSpecification, specification_id)
    if not spec or spec.project_id != project_id:
        raise LookupError("Prompt specification not found in project")
    version = _current_version(db, spec)
    trace = db.scalar(select(RequirementArtifactTrace).where(
        RequirementArtifactTrace.project_id == project_id,
        RequirementArtifactTrace.spec_version_id == version.id,
        RequirementArtifactTrace.artifact_version_id == artifact_version_id,
    ))
    if not trace:
        raise ValueError("Artifact version is not part of the current prompt plan")
    if status.upper() in {"REJECTED", "CHANGES_REQUIRED"} and not (comment or "").strip():
        raise ValueError("A comment is required when rejecting or requesting changes")
    medallion.review_medallion_artifact(db, project_id, artifact_version_id, status=status, reviewer=actor)
    evidence = _loads(trace.evidence_json, {})
    evidence["artifact_review"] = {"status": status.upper(), "reviewer": actor, "comment": comment, "reviewed_at": datetime.utcnow().isoformat()}
    trace.evidence_json = _json(evidence)
    traces = list(db.scalars(select(RequirementArtifactTrace).where(
        RequirementArtifactTrace.spec_version_id == version.id,
        RequirementArtifactTrace.project_id == project_id,
    )).all())
    all_approved = True
    for item in traces:
        current = db.get(MigrationStageArtifactVersion, item.artifact_version_id)
        if not current or current.review_status != "APPROVED" or current.validation_status != "PASSED" or not current.executable:
            all_approved = False
            break
    spec.current_status = "ARTIFACTS_APPROVED" if all_approved else "PENDING_ARTIFACT_REVIEW"
    db.commit()
    return detail(db, project_id, specification_id)


def deploy_dev(db: Session, project_id: str, specification_id: str, actor: str) -> dict[str, Any]:
    spec = db.get(PromptSpecification, specification_id)
    if not spec or spec.project_id != project_id:
        raise LookupError("Prompt specification not found in project")
    if spec.current_status not in {"ARTIFACTS_APPROVED", "DEV_DEPLOYMENT_FAILED", "DEPLOYING_DEV"}:
        raise ValueError("Every current artifact must be validated, executable, and approved before DEV deployment")
    spec.current_status = "DEPLOYING_DEV"
    db.commit()
    try:
        result = medallion.deploy_medallion_dev(db, project_id, allow_destructive=True, reuse_bronze=True)
    except Exception as exc:
        spec.current_status = "DEV_DEPLOYMENT_FAILED"
        db.commit()
        return {"specification_id": spec.id, "status": "DEV_DEPLOYMENT_FAILED", "error": str(exc), "deployment": {"status": "FAILED", "error": str(exc)}}
    if result.get("status") != "PASSED":
        spec.current_status = "DEV_DEPLOYMENT_FAILED"
        db.commit()
        return result
    reconciliation = deployment.run_reconciliation(db, project_id, environment="DEV", actor=actor)
    gate = deployment.evaluate_dev_gate(db, project_id)
    spec.current_status = "DEV_GATE_PASSED" if reconciliation.get("status") == "PASSED" and gate.get("status") == "PASSED" else "RECONCILIATION_FAILED"
    db.commit()
    return {"specification_id": spec.id, "status": spec.current_status, "deployment": result, "reconciliation": reconciliation, "gate": gate}


def trace(db: Session, project_id: str, specification_id: str) -> dict[str, Any]:
    spec = db.get(PromptSpecification, specification_id)
    if not spec or spec.project_id != project_id:
        raise LookupError("Prompt specification not found in project")
    version = _current_version(db, spec)
    rows = list(db.scalars(select(RequirementArtifactTrace).where(
        RequirementArtifactTrace.project_id == project_id,
        RequirementArtifactTrace.spec_version_id == version.id,
    ).order_by(RequirementArtifactTrace.request_id)).all())
    result = []
    for row in rows:
        artifact_version = db.get(MigrationStageArtifactVersion, row.artifact_version_id) if row.artifact_version_id else None
        node = db.get(MigrationMedallionNode, row.node_id) if row.node_id else None
        result.append({
            "request_id": row.request_id, "node_id": row.node_id,
            "target_fqn": node.target_fqn if node else None,
            "artifact_version_id": row.artifact_version_id,
            "artifact_version": artifact_version.version if artifact_version else None,
            "validation_status": artifact_version.validation_status if artifact_version else None,
            "executable": artifact_version.executable if artifact_version else None,
            "review_status": artifact_version.review_status if artifact_version else None,
            "node_status": node.status if node else None,
            "evidence": _loads(row.evidence_json, {}),
        })
    return {
        "specification_id": spec.id, "status": spec.current_status,
        "version": version.version, "version_id": version.id,
        "prompt_checksum": version.checksum, "metadata_snapshot_id": version.metadata_snapshot_id,
        "requirements": result,
    }
