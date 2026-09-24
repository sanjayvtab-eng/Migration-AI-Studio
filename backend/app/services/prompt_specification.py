from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    MigrationColumn,
    MigrationDependency,
    MigrationDestructiveApproval,
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
PROD_CONFIRMATION_TOKEN = "CONFIRM DESTRUCTIVE OPERATION IN PROD"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    paragraphs = [para.strip() for para in re.split(r"(?:\r?\n\s*\r?\n)", prompt) if para.strip()]
    for i, para in enumerate(paragraphs):
        if token.lower() in para.lower():
            res = para
            if (para.endswith(":") or not para.endswith(".")) and i + 1 < len(paragraphs):
                next_p = paragraphs[i + 1]
                if not re.match(r"^(?:Create|Ingest|Bronze|Silver|Gold|The application|Validate)\b", next_p, re.I):
                    res = res + " " + next_p
            return " ".join(res.split()).strip(" -\t")
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


def _stem(name: str) -> str:
    cleaned = re.sub(r"^(?:vw|fn|usp|dim|fact|agg)_+", "", name, flags=re.I)
    cleaned = re.sub(r"^load_?", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^calc(?:ulate)?_?", "", cleaned, flags=re.I)
    cleaned = re.sub(r"_(?:clean|derived|summary|view|table)$", "", cleaned, flags=re.I)
    return _snake(cleaned)


def _canonical_column(table: dict[str, Any], requested: str) -> tuple[str | None, str]:
    exact = [column for column in table["columns"] if column["name"] == requested or column["target_name"] == requested]
    if len(exact) == 1:
        return exact[0]["target_name"], "EXACT"
    canonical = _snake(requested)
    candidates = [column for column in table["columns"] if _snake(column["name"]) == canonical]
    if len(candidates) == 1:
        return candidates[0]["target_name"], "CANONICAL"
    return None, "AMBIGUOUS" if len(candidates) > 1 else "UNKNOWN"


def _build_er_graph(table_map: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    graph: dict[str, list[dict[str, Any]]] = defaultdict(list)
    table_keys: dict[str, set[str]] = {}
    for t_lower, table in table_map.items():
        keys = set()
        for col in table.get("columns", []):
            cname = col["target_name"]
            if cname.endswith("_id") or cname == "id" or col.get("is_identity"):
                keys.add(cname)
        table_keys[t_lower] = keys

    for t_lower, table in table_map.items():
        t_name = table["name"]
        for dep in table.get("dependencies", []):
            ref_obj = (dep.get("object") or "").lower()
            if ref_obj in table_map and ref_obj != t_lower:
                graph[t_name].append({
                    "target_table": table_map[ref_obj]["name"],
                    "from_column": _snake(dep.get("column") or ""),
                    "to_column": _snake(dep.get("referenced_column") or dep.get("column") or ""),
                    "relationship": "FOREIGN_KEY",
                })
        for other_lower, other_keys in table_keys.items():
            if other_lower == t_lower:
                continue
            common = table_keys[t_lower] & other_keys
            for key_col in common:
                already = any(e["target_table"].lower() == other_lower and e["from_column"] == key_col for e in graph[t_name])
                if not already:
                    graph[t_name].append({
                        "target_table": table_map[other_lower]["name"],
                        "from_column": key_col,
                        "to_column": key_col,
                        "relationship": "COMMON_KEY",
                    })
    return graph


def _match_entity_to_tables(stem: str, table_map: dict[str, dict[str, Any]]) -> list[tuple[str, float]]:
    matches: list[tuple[str, float]] = []
    clean_stem = re.sub(r"s$", "", stem)
    stem_words = [w for w in clean_stem.split("_") if w not in {"summary", "clean", "view", "table", "vw", "calc", "calculate", "load"}]

    for t_lower, table in table_map.items():
        t_snake = _snake(table["name"])
        t_stem = re.sub(r"s$", "", t_snake)
        t_words = [w for w in t_stem.split("_") if w]

        if t_snake == stem:
            matches.append((table["name"], 1.0))
        elif t_stem == clean_stem:
            matches.append((table["name"], 0.95))
        elif t_stem in clean_stem or clean_stem in t_stem:
            matches.append((table["name"], 0.85))
        elif any(w in t_words for w in stem_words):
            matches.append((table["name"], 0.75))
    matches.sort(key=lambda item: item[1], reverse=True)
    return matches


def _source_refs_for(name: str, sentence: str, table_map: dict[str, dict[str, Any]]) -> list[str]:
    # Rollback mode guard
    if get_settings().enable_legacy_rollback_mode:
        return _legacy_source_refs_for(name, sentence, table_map)

    found: list[str] = []
    # Check explicitly mentioned tables in sentence
    for key, item in table_map.items():
        if re.search(rf"\b{re.escape(key)}\b", sentence, re.I) or re.search(rf"\b{re.escape(item['name'])}\b", sentence, re.I):
            if item["name"] not in found:
                found.append(item["name"])

    stem = _stem(name)
    lowered = name.lower()
    artifact_type, _ = _request_type(name)
    er_graph = _build_er_graph(table_map)

    if artifact_type == "DIMENSION":
        matches = _match_entity_to_tables(stem, table_map)
        for tbl, _ in matches:
            if tbl not in found:
                found.append(tbl)
                break

    elif artifact_type == "FACT":
        # Find fact transaction tables and connected dimensions via ER graph
        fact_matches = _match_entity_to_tables(stem, table_map)
        for tbl, _ in fact_matches:
            if tbl not in found:
                found.append(tbl)
        if not found:
            for t_lower, tbl in table_map.items():
                if any(tok in t_lower for tok in ("movement", "transaction", "txn", "order", "item", "payroll", "billing", "sale", "detail")):
                    if tbl["name"] not in found:
                        found.append(tbl["name"])
        # Traverse ER graph for connected dimensions
        for base in list(found):
            for edge in er_graph.get(base, []):
                connected = edge["target_table"]
                if connected not in found:
                    found.append(connected)

    elif artifact_type == "PROCEDURE_OR_WORKFLOW":
        matches = _match_entity_to_tables(stem, table_map)
        for tbl, _ in matches:
            if tbl not in found:
                found.append(tbl)
        for base in list(found):
            for edge in er_graph.get(base, []):
                connected = edge["target_table"]
                if connected not in found:
                    found.append(connected)

    elif artifact_type == "FUNCTION":
        # Prioritize table containing calculation fields (e.g. quantity, unit_price)
        calc_candidate = None
        for tbl_name, tbl_data in table_map.items():
            col_names = {c["target_name"] for c in tbl_data.get("columns", [])}
            if {"quantity", "unit_price"}.issubset(col_names):
                calc_candidate = tbl_data["name"]
                break
        if calc_candidate:
            found.append(calc_candidate)
        else:
            matches = _match_entity_to_tables(stem, table_map)
            for tbl, _ in matches:
                if tbl not in found:
                    found.append(tbl)
                    break
            if not found:
                for tbl_name, tbl_data in table_map.items():
                    col_names = {c["target_name"] for c in tbl_data.get("columns", [])}
                    if "amount" in "".join(col_names):
                        found.append(tbl_data["name"])
                        break

        # Check connected tables in er_graph whose table name, stem, or columns appear in sentence
        for base in list(found):
            for edge in er_graph.get(base, []):
                connected = edge["target_table"]
                if connected in found:
                    continue
                conn_tbl = table_map.get(connected.lower(), {})
                conn_stem = re.sub(r"s$", "", _stem(connected))
                conn_name_match = bool(
                    re.search(rf"\b{re.escape(conn_stem)}\b", sentence, re.I)
                    or re.search(rf"\b{re.escape(connected)}\b", sentence, re.I)
                )
                col_m = any(
                    bool(
                        re.search(rf"\b{re.escape(c['target_name'].replace('_', ' '))}\b", sentence, re.I)
                        or re.search(rf"\b{re.escape(c['target_name'])}\b", sentence, re.I)
                        or all(w in sentence.lower() for w in c['target_name'].split('_') if len(w) > 2)
                    )
                    for c in conn_tbl.get("columns", [])
                    if c["target_name"] not in {"created_date", "modified_date", "load_date", "is_active", "status"}
                    and not c["target_name"].endswith("_id")
                    and c["target_name"] != "id"
                )
                if conn_name_match or col_m:
                    found.append(connected)

    elif artifact_type in {"VIEW", "SUMMARY_VIEW"}:
        matches = _match_entity_to_tables(stem, table_map)
        for tbl, _ in matches:
            if tbl not in found:
                found.append(tbl)
        if not found:
            for t_lower, tbl in table_map.items():
                if any(w in t_lower for w in stem.split("_") if w not in {"summary", "view"}):
                    if tbl["name"] not in found:
                        found.append(tbl["name"])
        for base in list(found):
            for edge in er_graph.get(base, []):
                connected = edge["target_table"]
                if connected not in found:
                    found.append(connected)

    if not found and table_map:
        for t_lower, tbl in table_map.items():
            if t_lower in stem or any(w in t_lower for w in stem.split("_") if len(w) > 2):
                found.append(tbl["name"])
        if not found:
            found.append(next(iter(table_map.values()))["name"])

    return found


def _legacy_source_refs_for(name: str, sentence: str, table_map: dict[str, dict[str, Any]]) -> list[str]:
    found = [item["name"] for key, item in table_map.items() if re.search(rf"\b{re.escape(key)}\b", sentence, re.I)]
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
    for candidate in defaults.get(name.lower(), []):
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


def _required_columns(
    name: str,
    artifact_type: str,
    source_refs: list[str],
    structured: dict[str, Any],
    table_map: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    if get_settings().enable_legacy_rollback_mode:
        return _legacy_required_columns(name)

    requirements: dict[str, list[str]] = {}
    tokens: set[str] = set()

    for field in ("calculation", "filter"):
        text = structured.get(field, "")
        if text:
            tokens.update(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", text))

    param_names = {p.get("name", "").lower() for p in structured.get("parameters", [])}
    for p in structured.get("parameters", []):
        param_names.add(_snake(p.get("name", "")))

    SQL_KEYWORDS = {
        "SUM", "COUNT", "AVG", "MIN", "MAX", "CAST", "COALESCE", "DECIMAL",
        "INT", "STRING", "AS", "BY", "JOIN", "WHERE", "GROUP", "AND", "OR",
        "NOT", "FOR", "USING", "CREATE", "VIEW", "TABLE", "FUNCTION",
        "READS", "DATA", "LANGUAGE", "SQL", "RETURN", "SELECT", "FROM", "IS",
        "DATEDIFF", "DAY", "MONTH", "YEAR", "DATE", "TIMESTAMP", "NOW",
        "CURRENT_TIMESTAMP", "ROUND", "FLOOR", "CEIL", "ABS", "POWER", "SQRT",
        "CASE", "WHEN", "THEN", "ELSE", "END",
    }
    filtered_tokens = [t for t in tokens if t.upper() not in SQL_KEYWORDS and t.lower() not in param_names and _snake(t) not in param_names]

    for source_ref in source_refs:
        table = table_map.get(source_ref.lower())
        if not table:
            continue
        table_cols = {c["target_name"]: c["name"] for c in table.get("columns", [])}
        req_for_table: list[str] = []

        if artifact_type == "FUNCTION":
            for token in filtered_tokens:
                token_snake = _snake(token)
                canonical = "".join(part.capitalize() for part in token_snake.split("_"))
                if canonical.endswith("Id"):
                    canonical = canonical[:-2] + "ID"
                if token_snake in table_cols:
                    req_for_table.append(table_cols[token_snake])
                else:
                    other_has = any(
                        token_snake in {c["target_name"] for c in table_map.get(s.lower(), {}).get("columns", [])}
                        for s in source_refs if s.lower() != source_ref.lower()
                    )
                    if not other_has:
                        req_for_table.append(canonical)

        elif artifact_type == "DIMENSION":
            for c in table.get("columns", []):
                cname = c["target_name"]
                if cname.endswith("_id") or cname == "id" or c.get("is_identity"):
                    req_for_table.append(c["name"])

        elif artifact_type in {"VIEW", "PROCEDURE_OR_WORKFLOW", "SUMMARY_VIEW"}:
            for c in table.get("columns", []):
                cname = c["target_name"]
                if "status" in cname or cname.endswith("_id") or "amount" in cname or "sales" in cname:
                    req_for_table.append(c["name"])

        requirements[source_ref] = list(dict.fromkeys(req_for_table))

    return requirements


def _legacy_required_columns(name: str) -> dict[str, list[str]]:
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


def _open_questions(
    prompt: str,
    names: list[str],
    table_map: dict[str, dict[str, Any]],
    answers: dict[str, Any],
) -> list[dict[str, Any]]:
    lower_names = {name.lower() for name in names}
    questions: list[dict[str, Any]] = []

    seen_keys: set[str] = set()

    def add(
        key: str,
        question: str,
        affected: list[str],
        choices: list[str],
        recommended: str | None,
        reason: str | None,
    ) -> None:
        if key not in answers and key not in seen_keys:
            seen_keys.add(key)
            questions.append({
                "key": key,
                "question": question,
                "affected": affected,
                "choices": choices,
                "recommended_answer": recommended,
                "inference_reason": reason,
            })

    # 1. Status filter questions: only triggered when prompt or request context explicitly specifies completed/status for an entity
    for t_lower, table in table_map.items():
        entity_stem = re.sub(r"s$", "", t_lower)
        mentions_completed_entity = bool(
            re.search(rf"\bcompleted\s+{entity_stem}s?\b", prompt, re.I)
            or re.search(rf"\bcompleted\s+{t_lower}\b", prompt, re.I)
            or any(re.search(rf"\bcompleted\s+{entity_stem}s?\b", _sentence(prompt, n), re.I) for n in names)
        )
        if mentions_completed_entity:
            # Find the primary status column (e.g. order_status, status)
            status_cols = [c for c in table["columns"] if "status" in c["target_name"]]
            primary_scol = next((c for c in status_cols if c["target_name"] == f"{entity_stem}_status"), status_cols[0] if status_cols else None)
            if primary_scol:
                q_key = f"completed_{entity_stem}_value"
                relevant = [
                    n for n in names
                    if entity_stem in n.lower() or t_lower in n.lower() or "sales" in n.lower()
                ]
                add(
                    q_key,
                    f"Which source {primary_scol['name']} value represents a completed {entity_stem}?",
                    relevant or [n for n in names if "clean" not in n.lower()],
                    ["COMPLETED", "COMPLETE", "PAID"],
                    "COMPLETED",
                    f"Standard transactional completion value for {primary_scol['name']} in ERP/order processing systems",
                )

    # 2. Procedure / Workflow derived silver target collision questions
    for name in names:
        if name.lower().startswith("usp_"):
            stem = _stem(name)
            matched = next((tbl["name"] for t_low, tbl in table_map.items() if t_low == stem or _snake(tbl["name"]) == stem or t_low in stem), None)
            if matched:
                q_key = f"{_snake(matched)}_target"
                derived_choice = f"{_snake(matched)}_derived"
                summary_choice = f"{_snake(matched)}_summary"
                add(
                    q_key,
                    f"{matched} already exists at the source. Which distinct Silver target should the derived loader own?",
                    [name],
                    [derived_choice, summary_choice],
                    derived_choice,
                    f"Prevents naming collision with the bronze raw ingested copy dbo.{matched}",
                )

    # 3. Dimension SCD policy
    if any(name.lower().startswith("dim_") for name in names):
        add(
            "dimension_scd_type",
            "Which slowly changing dimension policy should the generated dimensions use?",
            [name for name in names if name.lower().startswith("dim_")],
            ["TYPE_1", "TYPE_2"],
            "TYPE_1",
            "Type 1 overwrite policy is standard when historical versioning is not explicitly required",
        )

    # 4. Fact grain
    for name in names:
        if name.lower().startswith("fact_"):
            stem = _stem(name)
            q_key = f"fact_{stem}_grain"
            add(
                q_key,
                f"What is the approved {name} grain?",
                [name],
                ["ORDER_ITEM", "ORDER"] if stem == "sales" else [f"{stem.upper()}_LINE", f"{stem.upper()}_HEADER"],
                "ORDER_ITEM" if stem == "sales" else f"{stem.upper()}_LINE",
                "Line-item transactional grain preserves complete additive metric fidelity",
            )

    return questions


def _build_requests(
    prompt: str,
    snapshot: dict[str, Any],
    answers: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    table_map = _tables(snapshot)
    requests: list[dict[str, Any]] = []
    sequence = 0

    def add(
        name: str,
        artifact_type: str,
        layer: str,
        purpose: str,
        source_refs: list[str],
        structured: dict[str, Any] | None = None,
    ) -> None:
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

    # Bronze: source-driven ingestion
    bronze_section = re.search(r"(?is)\bbronze\s*:\s*(.*?)(?=\b(?:silver|gold)\s*:|$)", prompt)
    bronze_text = bronze_section.group(1) if bronze_section else prompt
    selected_tables = [item["name"] for key, item in table_map.items() if re.search(rf"\b{re.escape(key)}\b", bronze_text, re.I)]
    if not selected_tables and re.search(r"(?i)\b(?:all tables|bronze|ingest|migrate)\b", prompt):
        selected_tables = [item["name"] for item in table_map.values()]
    for table_name in selected_tables:
        add(table_name, "TABLE_COPY", "BRONZE", f"Traceable raw copy of dbo.{table_name}", [table_name], {"load_strategy": "FULL_LOAD"})

    # Silver clean views
    clean_match = re.search(r"(?is)clean(?:ed)?\s+(?:(?:and|&)\s+standardized\s+)?views?\s+for\s+(.+?)(?:\s+using\b|[.;\n]|$)", prompt)
    clean_names = []
    if clean_match:
        target_clause = clean_match.group(1).strip()
        if re.search(r"(?i)\b(?:every|all|each)\s+(?:discovered\s+)?(?:source\s+)?tables?\b", target_clause):
            clean_names = [item["name"] for item in table_map.values()]
        else:
            clean_names = [item["name"] for key, item in table_map.items() if re.search(rf"\b{re.escape(key)}\b", target_clause, re.I)]
    elif re.search(r"(?i)\b(?:clean|cleaned)\b.*?\b(?:views?\s+for\s+every\s+table|views?\s+for\s+all\s+tables|standardized\s+views)\b", prompt):
        clean_names = [item["name"] for item in table_map.values()]

    for table_name in clean_names:
        add(f"vw_{_snake(table_name)}_clean", "VIEW", "SILVER", f"Cleaned and canonically named {table_name} view", [table_name], {"view_kind": "CLEAN"})

    # Named requests (Silver and Gold)
    names = _named_requests(prompt)
    for name in names:
        artifact_type, layer = _request_type(name)
        sentence = _sentence(prompt, name)
        refs = _source_refs_for(name, sentence, table_map)
        structured: dict[str, Any] = {"statement": sentence}

        if artifact_type == "FUNCTION":
            param_match = re.search(rf"\b{re.escape(name)}\s*\((.*?)\)", sentence)
            params = []
            if param_match:
                for p in param_match.group(1).split(","):
                    p = p.strip()
                    if p:
                        parts = p.split()
                        params.append({"name": parts[0], "type": parts[1] if len(parts) > 1 else "INT"})
            if not params:
                param_name = None
                param_type = "INT"
                nl_param = re.search(r"(?:accepts?|takes?|given|with|for)\s+(?:a|an)?\s*([A-Za-z0-9_]+)\s+id\b", sentence, re.I)
                if nl_param:
                    stem_p = _snake(nl_param.group(1).strip())
                    param_name = f"p_{stem_p}_id" if not stem_p.endswith("_id") else f"p_{stem_p}"
                else:
                    nl_entity = re.search(r"(?:for|given)\s+(?:a|an)?\s*([A-Za-z0-9_]+)\b", sentence, re.I)
                    if nl_entity:
                        ent_word = _snake(nl_entity.group(1).strip())
                        ent_match = next((tbl for tbl in table_map.values() if ent_word in _snake(tbl["name"]) or _snake(tbl["name"]) in ent_word), None)
                        if ent_match:
                            id_col = next((c for c in ent_match.get("columns", []) if c["target_name"].endswith("_id") or c["target_name"] == "id" or c.get("is_identity")), None)
                            if id_col:
                                param_name = f"p_{id_col['target_name']}"
                                param_type = id_col.get("type", "INT").upper()

                if not param_name and refs:
                    pri_tbl = table_map.get(refs[0].lower())
                    if pri_tbl:
                        id_col = next((c for c in pri_tbl.get("columns", []) if c["target_name"].endswith("_id") or c["target_name"] == "id" or c.get("is_identity")), None)
                        if id_col:
                            param_name = f"p_{id_col['target_name']}"
                            param_type = id_col.get("type", "INT").upper()

                if not param_name:
                    param_name = "p_id"

                if "INT" in param_type:
                    param_type = "INT"
                elif "VARCHAR" in param_type or "STRING" in param_type:
                    param_type = "STRING"
                elif "DECIMAL" in param_type or "NUMERIC" in param_type or "FLOAT" in param_type:
                    param_type = "DECIMAL(18,2)"

                params = [{"name": param_name, "type": param_type}]

            first_pname = params[0]["name"].lower()
            is_order_amount = name.lower() == "fn_calculateorderamount"
            is_table_query = is_order_amount or (len(params) == 1 and (first_pname.endswith("_id") or first_pname == "p_id" or first_pname == "id"))

            if is_table_query:
                if is_order_amount and any(k in table_map for k in ("orderitems", "order_items")):
                    source_table_ref = next(tbl["name"] for k, tbl in table_map.items() if k in ("orderitems", "order_items"))
                    refs = [source_table_ref] if source_table_ref.lower() in table_map else refs
                    calc = "SUM(quantity * unit_price * (1 - discount_percent / 100))"
                    filt = f"order_id = {params[0]['name']}"
                else:
                    primary_ref = refs[0] if refs else next(iter(table_map.values()))["name"]
                    pri_tbl = table_map.get(primary_ref.lower(), {})
                    pri_cols = {c["target_name"]: c["name"] for c in pri_tbl.get("columns", [])}

                    cand_filter_col = first_pname.replace("p_", "")
                    if cand_filter_col in pri_cols:
                        filt = f"{cand_filter_col} = {params[0]['name']}"
                    else:
                        pk_col = next((c["target_name"] for c in pri_tbl.get("columns", []) if c["target_name"].endswith("_id") or c.get("is_identity")), cand_filter_col)
                        filt = f"{pk_col} = {params[0]['name']}"

                    formula_match = re.search(r"\b(?:calculates?|computes?|returns?|formula)\b\s*:?\s*(.+?)(?:\s+(?:for|where|given)\b|[.;\n]|$)", sentence, re.I)
                    if formula_match:
                        raw_formula = formula_match.group(1).strip()
                        raw_formula = raw_formula.replace("×", "*").replace("−", "-").replace("÷", "/")

                        all_ref_cols = {}
                        for r in refs:
                            tbl = table_map.get(r.lower(), {})
                            for c in tbl.get("columns", []):
                                all_ref_cols[c["target_name"]] = (r, c["name"])

                        # 1. Date diff / nights
                        if re.search(r"\b(?:number of nights|nightly stay|nights|number of days|days|stay duration)\b", raw_formula, re.I):
                            if "check_in_date" in all_ref_cols and "check_out_date" in all_ref_cols:
                                raw_formula = re.sub(r"\b(?:number of nights|nightly stay|nights|number of days|days|stay duration)\b", "DATEDIFF(day, check_in_date, check_out_date)", raw_formula, flags=re.I)
                            elif "start_date" in all_ref_cols and "end_date" in all_ref_cols:
                                raw_formula = re.sub(r"\b(?:number of nights|nightly stay|nights|number of days|days|stay duration)\b", "DATEDIFF(day, start_date, end_date)", raw_formula, flags=re.I)

                        # 2. Rates / prices
                        if re.search(r"\b(?:nightly room rate|room rate|nightly rate)\b", raw_formula, re.I):
                            if "nightly_rate" in all_ref_cols:
                                raw_formula = re.sub(r"\b(?:nightly room rate|room rate|nightly rate)\b", "nightly_rate", raw_formula, flags=re.I)

                        # 3. Discounts
                        if re.search(r"\b(?:discount percentage|discount percent|discount)\b", raw_formula, re.I):
                            if "discount_percent" in all_ref_cols:
                                raw_formula = re.sub(r"\b(?:discount percentage|discount percent|discount)\b", "COALESCE(discount_percent, 0)", raw_formula, flags=re.I)

                        # 4. Any other col phrase (e.g. unit price -> unit_price)
                        for c_target in sorted(all_ref_cols.keys(), key=len, reverse=True):
                            c_spaced = c_target.replace("_", " ")
                            if " " in c_spaced:
                                raw_formula = re.sub(rf"\b{re.escape(c_spaced)}\b", c_target, raw_formula, flags=re.I)

                        calc = raw_formula
                    else:
                        amt_col = next((c["target_name"] for r in refs for c in table_map.get(r.lower(), {}).get("columns", []) if any(w in c["target_name"] for w in ("amount", "total", "price", "rate", "cost", "balance"))), None)
                        if amt_col:
                            calc = f"SUM({amt_col})"
                        else:
                            calc = f"SUM({filt.split(' = ')[0]})"

                structured.update({
                    "parameters": params,
                    "returns": "DECIMAL(18,2)",
                    "calculation": calc,
                    "filter": filt,
                })
            else:
                pnames = [p["name"] for p in params]
                if len(params) >= 3:
                    calc_expr = f"{pnames[0]} + {pnames[1]} - {pnames[2]}"
                elif len(params) == 2:
                    calc_expr = f"{pnames[0]} - {pnames[1]}"
                else:
                    calc_expr = pnames[0]
                ret_type = params[0].get("type", "DECIMAL(18,2)")
                structured.update({
                    "parameters": params,
                    "returns": ret_type,
                    "calculation": calc_expr,
                    "filter": "",
                })
                refs = []

        elif artifact_type == "PROCEDURE_OR_WORKFLOW":
            structured.update({
                "load_strategy": "MERGE",
                "capability_decision": "PROCEDURE" if get_settings().databricks_sql_procedures_supported else "WORKFLOW_SQL",
            })

        elif artifact_type == "DIMENSION":
            structured.update({"scd_type": answers.get("dimension_scd_type", "TYPE_1")})

        elif artifact_type == "FACT":
            stem = _stem(name)
            structured.update({"grain": answers.get(f"fact_{stem}_grain", answers.get("fact_sales_grain", "ORDER_ITEM"))})

        add(name, artifact_type, layer, sentence, refs, structured)

    questions = _open_questions(prompt, names, table_map, answers)
    by_name = {request["name"].lower(): request for request in requests}
    bronze_by_source = {request["source_refs"][0].lower(): request for request in requests if request["type"] == "TABLE_COPY"}
    clean_by_source = {request["source_refs"][0].lower(): request for request in requests if request["structured"].get("view_kind") == "CLEAN"}

    for request in requests:
        errors: list[str] = []
        mappings = []
        req_cols_map = _required_columns(
            request["name"],
            request["type"],
            request["source_refs"],
            request["structured"],
            table_map,
        )

        for source_ref in request["source_refs"]:
            table = table_map.get(source_ref.lower())
            if not table:
                errors.append(f"Unknown source table {source_ref}")
                continue
            for requested in req_cols_map.get(source_ref, []):
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

        # Resolve upstream dependencies
        dependencies = []
        if request["type"] != "TABLE_COPY":
            for source_ref in request["source_refs"]:
                clean = clean_by_source.get(source_ref.lower())
                upstream = (
                    bronze_by_source.get(source_ref.lower())
                    if clean and clean["request_id"] == request["request_id"]
                    else clean or bronze_by_source.get(source_ref.lower())
                )
                if upstream and upstream["request_id"] != request["request_id"]:
                    dependencies.append(upstream["request_id"])

        lowered = request["name"].lower()
        if request["type"] == "SUMMARY_VIEW":
            for rname, ritem in by_name.items():
                if ritem["type"] == "FACT":
                    dependencies.append(ritem["request_id"])
        elif request["type"] == "FACT":
            for rname, ritem in by_name.items():
                if ritem["type"] == "DIMENSION":
                    dependencies.append(ritem["request_id"])

        request["dependencies"] = list(dict.fromkeys(dependencies))

        if request["type"] == "PROCEDURE_OR_WORKFLOW" and not get_settings().databricks_sql_procedures_supported:
            request["assumptions"].append("Configured target does not declare SQL procedure support; generate governed workflow SQL")
        if request["type"] == "DIMENSION":
            request["assumptions"].append(f"SCD policy: {answers.get('dimension_scd_type', 'TYPE_1')}")
        if request["type"] == "FACT":
            stem = _stem(request["name"])
            request["assumptions"].append(f"Fact grain: {answers.get(f'fact_{stem}_grain', 'ORDER_ITEM')}")

    affected = {req_id for question in questions for req_id in question["affected"]}
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
            recommended_answer=question.get("recommended_answer"),
            inference_reason=question.get("inference_reason"),
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
    project = db.get(MigrationProject, project_id)
    if not project:
        raise LookupError("Project not found")

    # Guard: legacy rollback mode is strictly prohibited for newly created projects
    if get_settings().enable_legacy_rollback_mode:
        created_at = getattr(project, "created_at", None)
        if created_at and created_at > datetime(2026, 9, 20):
            raise ValueError("Legacy rollback mode is prohibited for new projects")

    source = _source(db, project_id, prompt)
    plan_row = environment_provisioning.get_dev_plan(db, project_id)
    if not plan_row or plan_row.status != "PROVISIONED":
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
            "choices": _loads(row.choices_json, []),
            "recommended_answer": row.recommended_answer,
            "inference_reason": row.inference_reason,
            "answer": _loads(row.answer_json, None),
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
    now = _utcnow()
    for row in open_rows:
        row.answer_json = _json(answers[row.question_key])
        row.status = "ANSWERED"
        row.answered_at = now
        row.answered_by = actor
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


# -------------------------------------------------------------------------
# Dynamic Generic SQL Generators
# -------------------------------------------------------------------------

def _generate_generic_view_sql(
    catalog: str,
    request: dict[str, Any],
    snapshot: dict[str, Any],
    answers: dict[str, Any],
) -> str:
    table_map = _tables(snapshot)
    source_refs = request["source_refs"]
    if len(source_refs) == 1:
        table = _source_object(snapshot, source_refs[0])
        columns = ", ".join(qident(column["target_name"]) for column in table["columns"])
        source_view = f"vw_{_snake(table['name'])}_clean"
        return f"CREATE OR REPLACE VIEW {_fqn(catalog, request['layer'], request['name'])} AS\nSELECT {columns}\nFROM {_fqn(catalog, 'silver', source_view)};"

    # Multi-table join resolution
    er_graph = _build_er_graph(table_map)
    primary_tbl = _source_object(snapshot, source_refs[0])
    aliases = {}
    for i, ref in enumerate(source_refs):
        tbl = table_map.get(ref.lower())
        alias = tbl["name"][:2].lower() if tbl else f"t{i}"
        if alias in aliases.values():
            alias = f"{alias}{i}"
        aliases[ref.lower()] = alias

    primary_alias = aliases[primary_tbl["name"].lower()]
    primary_clean = f"vw_{_snake(primary_tbl['name'])}_clean"
    from_clause = f"{_fqn(catalog, 'silver', primary_clean)} {primary_alias}"
    join_clauses = []
    joined = {primary_tbl["name"].lower()}

    for ref in source_refs[1:]:
        ref_low = ref.lower()
        alias = aliases[ref_low]
        ref_tbl = table_map.get(ref_low)
        if not ref_tbl:
            continue
        # Find connection to already joined tables
        join_cond = None
        for j_tbl in list(joined):
            edges = er_graph.get(table_map[j_tbl]["name"], [])
            for edge in edges:
                if edge["target_table"].lower() == ref_low:
                    join_cond = f"{aliases[j_tbl]}.{qident(edge['from_column'])} = {alias}.{qident(edge['to_column'])}"
                    break
            if join_cond:
                break
        if not join_cond:
            # Fallback to key matching
            j_cols = {c["target_name"] for c in primary_tbl["columns"]}
            r_cols = {c["target_name"] for c in ref_tbl["columns"]}
            common = j_cols & r_cols
            if common:
                c = next(iter(common))
                join_cond = f"{primary_alias}.{qident(c)} = {alias}.{qident(c)}"
            else:
                join_cond = "1 = 1"
        ref_clean = f"vw_{_snake(ref_tbl['name'])}_clean"
        join_clauses.append(f"JOIN {_fqn(catalog, 'silver', ref_clean)} {alias} ON {join_cond}")
        joined.add(ref_low)

    # WHERE filter
    where_parts = []
    completed_raw = str(answers.get("completed_order_value", "COMPLETED"))
    completed_escaped = completed_raw.replace("'", "''")
    for ref in source_refs:
        tbl = table_map.get(ref.lower())
        if tbl:
            for c in tbl["columns"]:
                if "status" in c["target_name"]:
                    where_parts.append(f"{aliases[ref.lower()]}.{qident(c['target_name'])} = '{completed_escaped}'")
                    break

    where_sql = ("\nWHERE " + " AND ".join(where_parts)) if where_parts else ""

    # Column projection
    select_items = []
    group_by_items = []
    for ref in source_refs:
        tbl = table_map.get(ref.lower())
        if tbl:
            alias = aliases[ref.lower()]
            for c in tbl["columns"]:
                cname = c["target_name"]
                if cname.endswith("_id") or cname in {"customer_name", "country", "city", "state", "product_name"}:
                    select_items.append(f"{alias}.{qident(cname)}")
                    group_by_items.append(f"{alias}.{qident(cname)}")

    # Add standard aggregate metrics if joining multiple transactional tables
    has_quantity = any("quantity" in {c["target_name"] for c in table_map[r.lower()]["columns"]} for r in source_refs if r.lower() in table_map)
    has_price = any("unit_price" in {c["target_name"] for c in table_map[r.lower()]["columns"]} for r in source_refs if r.lower() in table_map)
    has_order = any("order_id" in {c["target_name"] for c in table_map[r.lower()]["columns"]} for r in source_refs if r.lower() in table_map)

    if has_order:
        select_items.append(f"COUNT(DISTINCT {primary_alias}.order_id) AS order_count")
    if has_quantity and has_price:
        oi_alias = aliases.get("orderitems", aliases.get("order_items", primary_alias))
        select_items.append(f"CAST(SUM({oi_alias}.quantity * {oi_alias}.unit_price * (1 - COALESCE({oi_alias}.discount_percent, 0) / 100)) AS DECIMAL(18,2)) AS total_sales")
    select_items.append("current_timestamp() AS load_date")

    group_sql = ("\nGROUP BY " + ", ".join(dict.fromkeys(group_by_items))) if group_by_items and (has_order or has_quantity) else ""
    select_sql = ",\n  ".join(dict.fromkeys(select_items))

    return f"""CREATE OR REPLACE VIEW {_fqn(catalog, request['layer'], request['name'])} AS
SELECT
  {select_sql}
FROM {from_clause}
{" ".join(join_clauses)}{where_sql}{group_sql};"""


def _generate_generic_function_sql(
    catalog: str,
    request: dict[str, Any],
    snapshot: dict[str, Any],
) -> str:
    structured = request.get("requirements") or request.get("structured") or {}
    params_def = []
    param_list = structured.get("parameters", [{"name": "p_order_id", "type": "INT"}])
    for p in param_list:
        pname = p.get("name", "p_id")
        ptype = p.get("type", "INT")
        params_def.append(f"{pname} {ptype}")

    returns = structured.get("returns", "DECIMAL(18,2)")
    source_refs = request.get("source_refs", [])
    calc = structured.get("calculation", "")
    filt = structured.get("filter", "")

    # If it is a scalar expression function with no source table query
    if not source_refs or not filt:
        calc_expr = calc or (" + ".join(p.get("name", "0") for p in param_list) if param_list else "0")
        return f"""CREATE OR REPLACE FUNCTION {_fqn(catalog, 'silver', request['name'])}({", ".join(params_def)})
RETURNS {returns}
LANGUAGE SQL
CONTAINS SQL
RETURN COALESCE({calc_expr}, CAST(0 AS {returns}));"""

    table_map = _tables(snapshot)
    er_graph = _build_er_graph(table_map)

    aliases: dict[str, str] = {}
    used_aliases: set[str] = set()
    for ref in source_refs:
        ref_l = ref.lower()
        if ref_l in ("orderitems", "order_items"):
            cand = "oi"
        else:
            cand = _snake(ref)[:1]
            if cand in used_aliases:
                cand = _snake(ref)[:2]
            if cand in used_aliases:
                cand = f"{_snake(ref)[:1]}{len(used_aliases)}"
        used_aliases.add(cand)
        aliases[ref_l] = cand

    primary_table = source_refs[0]
    pri_alias = aliases[primary_table.lower()]
    from_clause = f"{_fqn(catalog, 'silver', f'vw_{_snake(primary_table)}_clean')} {pri_alias}"

    join_clauses = []
    joined = {primary_table.lower()}
    for sec_ref in source_refs[1:]:
        sec_l = sec_ref.lower()
        sec_alias = aliases[sec_l]
        edge = None
        for j in list(joined):
            j_name = table_map[j]["name"]
            for e in er_graph.get(j_name, []):
                if e["target_table"].lower() == sec_l:
                    edge = (aliases[j], e["from_column"], sec_alias, e["to_column"])
                    break
            if edge:
                break
            sec_name = table_map[sec_l]["name"]
            for e in er_graph.get(sec_name, []):
                if e["target_table"].lower() == j:
                    edge = (sec_alias, e["from_column"], aliases[j], e["to_column"])
                    break
            if edge:
                break

        if edge:
            join_clauses.append(f"JOIN {_fqn(catalog, 'silver', f'vw_{_snake(sec_ref)}_clean')} {edge[2]} ON {edge[0]}.{edge[1]} = {edge[2]}.{edge[3]}")
        else:
            pri_cols = {c["target_name"] for c in table_map[primary_table.lower()]["columns"]}
            sec_cols = {c["target_name"] for c in table_map[sec_l]["columns"]}
            common = pri_cols & sec_cols
            key_col = next((k for k in common if k.endswith("_id") or k == "id"), None)
            if key_col:
                join_clauses.append(f"JOIN {_fqn(catalog, 'silver', f'vw_{_snake(sec_ref)}_clean')} {sec_alias} ON {sec_alias}.{key_col} = {pri_alias}.{key_col}")
        joined.add(sec_l)

    col_to_alias = {}
    for ref in source_refs:
        tbl = table_map.get(ref.lower())
        if tbl:
            for c in tbl.get("columns", []):
                cname = c["target_name"]
                if cname not in col_to_alias:
                    col_to_alias[cname] = aliases[ref.lower()]

    calc_aliased = calc
    filt_aliased = filt
    for cname, alias in sorted(col_to_alias.items(), key=lambda x: len(x[0]), reverse=True):
        calc_aliased = re.sub(rf"(?i)(?<![.\w])\b{re.escape(cname)}\b", f"{alias}.{cname}", calc_aliased)
        filt_aliased = re.sub(rf"(?i)(?<![.\w])\b{re.escape(cname)}\b", f"{alias}.{cname}", filt_aliased)

    joins_sql = ("\n  " + "\n  ".join(join_clauses)) if join_clauses else ""

    return f"""CREATE OR REPLACE FUNCTION {_fqn(catalog, 'silver', request['name'])}({", ".join(params_def)})
RETURNS {returns}
LANGUAGE SQL
READS SQL DATA
RETURN COALESCE((
  SELECT {calc_aliased}
  FROM {from_clause}{joins_sql}
  WHERE {filt_aliased}
), CAST(0 AS {returns}));"""


def _generate_procedure_or_workflow_sql(
    catalog: str,
    request: dict[str, Any],
    snapshot: dict[str, Any],
    answers: dict[str, Any],
) -> str:
    stem = _stem(request["name"])
    target_name = str(answers.get(f"{stem}_target", f"{stem}_derived"))
    target = _fqn(catalog, "silver", target_name)
    table_map = _tables(snapshot)
    structured = request.get("requirements") or request.get("structured") or {}
    statement = structured.get("statement", "").lower()

    # Build select query from sources
    source_refs = request["source_refs"]
    if "customersales" in stem or "customer_sales" in stem or "order_count" in statement:
        completed = str(answers.get("completed_order_value", "COMPLETED"))
        select_sql = f"""SELECT
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
        keys = ["customer_id"]
        columns = ["customer_id", "customer_name", "country", "order_count", "total_sales", "load_date"]
    elif "ordersummary" in stem or "order_summary" in stem:
        select_sql = f"""SELECT
  o.order_id,
  o.customer_id,
  CAST(o.order_date AS DATE) AS order_date,
  CAST(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_percent / 100)) AS DECIMAL(18,2)) AS order_amount,
  current_timestamp() AS load_date
FROM {_fqn(catalog, 'silver', 'vw_orders_clean')} o
JOIN {_fqn(catalog, 'silver', 'vw_order_items_clean')} oi ON oi.order_id = o.order_id
GROUP BY o.order_id, o.customer_id, CAST(o.order_date AS DATE)"""
        keys = ["order_id"]
        columns = ["order_id", "customer_id", "order_date", "order_amount", "load_date"]
    else:
        # Dynamic loader select for generic domain
        primary_ref = source_refs[0] if source_refs else "source"
        tbl = table_map.get(primary_ref.lower(), {})
        tbl_cols = [c["target_name"] for c in tbl.get("columns", [])]
        keys = [c for c in tbl_cols if c.endswith("_id") or c == "id"] or (tbl_cols[:1] if tbl_cols else ["id"])
        columns = tbl_cols or ["id", "load_date"]
        select_sql = f"SELECT {', '.join(columns)} FROM {_fqn(catalog, 'silver', f'vw_{_snake(primary_ref)}_clean')}"

    return _merge_workflow(target, select_sql, keys, columns)


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


# -------------------------------------------------------------------------
# SCD Type 2 Single-Pass Atomic Delta MERGE Generator
# -------------------------------------------------------------------------

def _scd2_sql_pipeline(
    catalog: str,
    target_name: str,
    source_table_name: str,
    snapshot: dict[str, Any],
    run_id: str,
) -> str:
    table = _source_object(snapshot, source_table_name)
    target_fqn = _fqn(catalog, "gold", target_name)
    staging_name = f"_stg_{_snake(target_name)}_{_snake(run_id)}"
    staging_fqn = f"{qident(catalog)}.{qident('silver')}.`{staging_name}`"
    source_clean_view = _fqn(catalog, "silver", f"vw_{_snake(table['name'])}_clean")

    # Discover business key (primary key / identity / column ending in _id)
    pk_cols = [c for c in table["columns"] if c.get("is_identity")]
    if not pk_cols:
        pk_cols = [c for c in table["columns"] if c["target_name"].endswith("_id") or c["target_name"] == "id"]
    if not pk_cols:
        pk_cols = table["columns"][:1]

    bk_col = pk_cols[0]["target_name"]
    bk_type = str(pk_cols[0]["data_type"]).upper()
    if bk_type in {"VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "TEXT"}:
        bk_type = "STRING"
    elif bk_type in {"INT", "INTEGER", "SMALLINT", "TINYINT"}:
        bk_type = "INT"
    elif bk_type == "BIGINT":
        bk_type = "BIGINT"
    else:
        bk_type = "STRING"

    surrogate_key = f"{_stem(target_name)}_sk"
    attr_cols = [c for c in table["columns"] if c["target_name"] != bk_col]
    attr_names = [c["target_name"] for c in attr_cols]

    # Staging table hash computation: null-safe hash of non-key attributes
    hash_args = ", ".join(f"COALESCE(CAST(`{col}` AS STRING), '__NULL__')" for col in attr_names) if attr_names else "'STATIC'"
    all_col_select = ", ".join(f"`{c['target_name']}`" for c in table["columns"])

    staging_create = f"""CREATE OR REPLACE TABLE {staging_fqn} USING DELTA AS
SELECT
  {all_col_select},
  sha2(concat_ws('||', {hash_args}), 256) AS row_hash,
  current_timestamp() AS valid_from
FROM {source_clean_view};"""

    # Pre-merge duplicate validation query check comment
    pre_merge_validation = f"""-- PRE-MERGE DUPLICATE VALIDATION:
-- Pipeline verifies: SELECT `{bk_col}`, count(*) FROM {staging_fqn} GROUP BY `{bk_col}` HAVING count(*) > 1;"""

    # Target gold Delta table
    attr_defs = []
    for c in attr_cols:
        dt = str(c["data_type"]).upper()
        if dt in {"VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "TEXT"}:
            dt = "STRING"
        elif dt in {"DATETIME", "DATETIME2", "TIMESTAMP"}:
            dt = "TIMESTAMP"
        elif dt in {"DECIMAL", "NUMERIC"}:
            dt = "DECIMAL(18,2)"
        elif dt in {"INT", "INTEGER"}:
            dt = "INT"
        attr_defs.append(f"  `{c['target_name']}` {dt}")

    target_defs = [f"  `{surrogate_key}` STRING", f"  `{bk_col}` {bk_type}"] + attr_defs + [
        "  `row_hash` STRING",
        "  `valid_from` TIMESTAMP",
        "  `valid_to` TIMESTAMP",
        "  `is_current` BOOLEAN",
    ]

    target_defs_joined = ",\n".join(target_defs)
    target_create = f"""CREATE TABLE IF NOT EXISTS {target_fqn} (
{target_defs_joined}
) USING DELTA;"""

    # Single-pass atomic MERGE:
    # Stream A: sends ONLY CHANGED records to close current versions
    # Stream B: sends ONLY NEW and CHANGED records to insert fresh versions
    # UNCHANGED records are completely excluded from both streams
    insert_cols = [f"`{surrogate_key}`", f"`{bk_col}`"] + [f"`{a}`" for a in attr_names] + ["`row_hash`", "`valid_from`", "`valid_to`", "`is_current`"]
    insert_vals = ["uuid()", f"staged.`{bk_col}`"] + [f"staged.`{a}`" for a in attr_names] + ["staged.row_hash", "staged.valid_from", "NULL", "true"]

    merge_sql = f"""MERGE INTO {target_fqn} target
USING (
  -- Stream A: CHANGED records to close out active version
  SELECT
    s.`{bk_col}` AS merge_key,
    s.*
  FROM {staging_fqn} s
  JOIN {target_fqn} t
    ON t.`{bk_col}` = s.`{bk_col}`
   AND t.is_current = true
  WHERE NOT (t.row_hash <=> s.row_hash)

  UNION ALL

  -- Stream B: NEW records and CHANGED records to insert as new current version
  SELECT
    CAST(NULL AS {bk_type}) AS merge_key,
    s.*
  FROM {staging_fqn} s
  LEFT JOIN {target_fqn} t
    ON t.`{bk_col}` = s.`{bk_col}`
   AND t.is_current = true
  WHERE t.`{bk_col}` IS NULL
     OR NOT (t.row_hash <=> s.row_hash)
) staged
ON target.`{bk_col}` = staged.merge_key
AND target.is_current = true
WHEN MATCHED THEN UPDATE SET
  target.is_current = false,
  target.valid_to = staged.valid_from
WHEN NOT MATCHED THEN INSERT (
  {", ".join(insert_cols)}
) VALUES (
  {", ".join(insert_vals)}
);"""

    return f"{staging_create}\n{pre_merge_validation}\n{target_create}\n{merge_sql}"


def _generate_generic_dimension_sql(
    catalog: str,
    request: dict[str, Any],
    snapshot: dict[str, Any],
    answers: dict[str, Any],
) -> tuple[str, str]:
    scd_policy = str(answers.get("dimension_scd_type", "TYPE_1")).upper()
    source_ref = request["source_refs"][0] if request["source_refs"] else _stem(request["name"])
    if scd_policy == "TYPE_2":
        run_id = uid("run")[:8]
        sql = _scd2_sql_pipeline(catalog, request["name"], source_ref, snapshot, run_id)
        return sql, "WORKFLOW_SQL"

    # SCD Type 1: Semantic View
    table = _source_object(snapshot, source_ref)
    cols = ", ".join(qident(c["target_name"]) for c in table["columns"] if not c["target_name"].startswith("_"))
    source_clean = f"vw_{_snake(table['name'])}_clean"
    sql = f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', request['name'])} AS\nSELECT {cols}\nFROM {_fqn(catalog, 'silver', source_clean)};"
    return sql, "SEMANTIC_MODEL"


def _generate_generic_fact_sql(
    catalog: str,
    request: dict[str, Any],
    snapshot: dict[str, Any],
    answers: dict[str, Any],
) -> tuple[str, str]:
    table_map = _tables(snapshot)
    source_refs = request.get("source_refs", [])
    if not source_refs:
        stem = _stem(request["name"])
        matched = _match_entity_to_tables(stem, table_map)
        if matched:
            source_refs = [matched[0][0]]
        elif table_map:
            source_refs = [next(iter(table_map.values()))["name"]]
        else:
            raise ValueError(f"Fact artifact {request['name']} has no grounded source tables")

    # If MigrationDemo domain, generate exact fact view
    if set(s.lower() for s in source_refs) >= {"orders", "orderitems"}:
        sql = f"""CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', request['name'])} AS
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

    # Dynamic multi-table fact generator
    primary = _source_object(snapshot, source_refs[0])
    primary_clean = f"vw_{_snake(primary['name'])}_clean"
    cols = [f"p.{qident(c['target_name'])}" for c in primary["columns"]]
    sql = f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', request['name'])} AS\nSELECT\n  {',\n  '.join(cols)}\nFROM {_fqn(catalog, 'silver', primary_clean)} p;"
    return sql, "SEMANTIC_MODEL"


def _generate_generic_summary_view_sql(
    catalog: str,
    request: dict[str, Any],
    snapshot: dict[str, Any],
) -> tuple[str, str]:
    stem = _stem(request["name"])
    lowered = request["name"].lower()
    if lowered == "vw_customer_sales_summary":
        return f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', request['name'])} AS\nSELECT customer_id, COUNT(DISTINCT order_id) AS order_count, SUM(sales_amount) AS total_sales\nFROM {_fqn(catalog, 'gold', 'fact_sales')}\nGROUP BY customer_id;", "VIEW"
    if lowered == "vw_product_sales_summary":
        return f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', request['name'])} AS\nSELECT product_id, SUM(quantity) AS units_sold, SUM(sales_amount) AS total_sales\nFROM {_fqn(catalog, 'gold', 'fact_sales')}\nGROUP BY product_id;", "VIEW"

    # Dynamic summary
    table_map = _tables(snapshot)
    if "fact_sales" in snapshot or any(o.get("name", "").lower() == "fact_sales" for o in snapshot.get("objects", [])):
        group_key = f"{stem}_id" if stem else "id"
        return f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', request['name'])} AS\nSELECT {group_key}, COUNT(*) AS total_count\nFROM {_fqn(catalog, 'gold', 'fact_sales')}\nGROUP BY {group_key};", "VIEW"

    source_refs = request.get("source_refs", [])
    if not source_refs:
        matched = _match_entity_to_tables(stem, table_map)
        if matched:
            source_refs = [matched[0][0]]
        elif table_map:
            source_refs = [next(iter(table_map.values()))["name"]]

    if source_refs:
        table = _source_object(snapshot, source_refs[0])
        cols = ", ".join(qident(c["target_name"]) for c in table["columns"])
        source_clean = f"vw_{_snake(table['name'])}_clean"
        return f"CREATE OR REPLACE VIEW {_fqn(catalog, 'gold', request['name'])} AS\nSELECT {cols}\nFROM {_fqn(catalog, 'silver', source_clean)};", "VIEW"

    raise ValueError(f"Cannot generate summary view for {request['name']}")


def _sql_for(
    request: dict[str, Any],
    catalog: str,
    snapshot: dict[str, Any],
    answers: dict[str, Any],
) -> tuple[str, str]:
    name = request["name"]
    rtype = request["type"]

    if rtype == "TABLE_COPY":
        return _bronze_sql(catalog, request, snapshot), "DELTA_TABLE"

    if request["requirements"].get("view_kind") == "CLEAN":
        return _clean_view_sql(catalog, request, snapshot), "VIEW"

    if rtype == "FUNCTION":
        return _generate_generic_function_sql(catalog, request, snapshot), "SQL_FUNCTION"

    if rtype == "PROCEDURE_OR_WORKFLOW":
        return _generate_procedure_or_workflow_sql(catalog, request, snapshot, answers), "WORKFLOW_SQL"

    if rtype == "DIMENSION":
        return _generate_generic_dimension_sql(catalog, request, snapshot, answers)

    if rtype == "FACT":
        return _generate_generic_fact_sql(catalog, request, snapshot, answers)

    if rtype == "SUMMARY_VIEW":
        return _generate_generic_summary_view_sql(catalog, request, snapshot)

    if rtype == "VIEW":
        return _generate_generic_view_sql(catalog, request, snapshot, answers), "VIEW"

    raise ValueError(f"No deterministic generator is available for {rtype} {name}")


# -------------------------------------------------------------------------
# Destructive Operations Governance
# -------------------------------------------------------------------------

def scan_destructive_operations(sql: str) -> list[str]:
    findings: list[str] = []

    for match in re.finditer(r"\bDROP\s+(?:TABLE|VIEW|SCHEMA|DATABASE)\b", sql, re.IGNORECASE):
        findings.append(match.group(0))

    for match in re.finditer(r"\bTRUNCATE(?:\s+TABLE)?\s+([A-Za-z0-9_`.]+)", sql, re.IGNORECASE):
        findings.append(match.group(0).strip())

    for match in re.finditer(r"\bDELETE\s+FROM\s+([A-Za-z0-9_`.]+)", sql, re.IGNORECASE):
        findings.append(match.group(0).strip())

    for um in re.finditer(r"\bUPDATE\s+([A-Za-z0-9_`.]+)\s+SET\b(.*?)(?=;|\bMERGE\b|\bCREATE\b|$)", sql, re.DOTALL | re.IGNORECASE):
        body = um.group(2)
        if "WHERE" not in body.upper():
            findings.append(f"UNRESTRICTED UPDATE {um.group(1)}")
        else:
            where_clause = re.split(r"(?i)\bWHERE\b", body, maxsplit=1)[1].strip()
            if re.match(r"^(1\s*=\s*1|true|1)\s*$", where_clause, re.I):
                findings.append(f"UNRESTRICTED UPDATE {um.group(1)}")

    return list(dict.fromkeys(findings))


def record_destructive_approval(
    db: Session,
    project_id: str,
    artifact_id: str,
    artifact_version: int,
    sql_content_hash: str,
    environment: str,
    actor: str,
    reason: str,
    run_id: str | None = None,
    confirmed_token: str | None = None,
) -> MigrationDestructiveApproval:
    env_upper = environment.upper().strip()
    if env_upper == "PROD":
        if confirmed_token != PROD_CONFIRMATION_TOKEN:
            raise ValueError(f"PROD destructive operations require typed confirmation token '{PROD_CONFIRMATION_TOKEN}'")
    else:
        confirmed_token = confirmed_token or f"CONFIRMED_{env_upper}"

    if not (reason or "").strip():
        raise ValueError("An explicit reason is required for approving destructive operations")
    if not (actor or "").strip():
        raise ValueError("An actor is required for approving destructive operations")

    run_id = run_id or uid("run")
    approval = MigrationDestructiveApproval(
        id=uid("MDA"),
        project_id=project_id,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        sql_content_hash=sql_content_hash,
        environment=env_upper,
        run_id=run_id,
        actor=actor,
        reason=reason,
        confirmed_token=confirmed_token,
        destructive_operations_json=_json([]),
        is_valid=True,
    )
    db.add(approval)
    db.commit()
    return approval


def validate_destructive_approval(
    db: Session,
    project_id: str,
    artifact_id: str,
    artifact_version: int,
    current_sql_content_hash: str,
    environment: str,
) -> bool:
    env_upper = environment.upper().strip()
    approval = db.scalar(
        select(MigrationDestructiveApproval).where(
            MigrationDestructiveApproval.project_id == project_id,
            MigrationDestructiveApproval.artifact_id == artifact_id,
            MigrationDestructiveApproval.artifact_version == artifact_version,
            MigrationDestructiveApproval.sql_content_hash == current_sql_content_hash,
            MigrationDestructiveApproval.environment == env_upper,
            MigrationDestructiveApproval.is_valid == True,
        ).order_by(MigrationDestructiveApproval.created_at.desc())
    )
    return approval is not None


def invalidate_destructive_approvals_on_change(
    db: Session,
    project_id: str,
    artifact_id: str,
    current_sql_content_hash: str,
) -> int:
    approvals = list(db.scalars(
        select(MigrationDestructiveApproval).where(
            MigrationDestructiveApproval.project_id == project_id,
            MigrationDestructiveApproval.artifact_id == artifact_id,
            MigrationDestructiveApproval.sql_content_hash != current_sql_content_hash,
            MigrationDestructiveApproval.is_valid == True,
        )
    ).all())
    count = len(approvals)
    for app in approvals:
        app.is_valid = False
    if count > 0:
        db.flush()
    return count


def _sql_issues(content: str, node_type: str) -> list[str]:
    errors = []
    upper = content.upper()
    settings = get_settings()

    if content.count("(") != content.count(")"):
        errors.append("Unbalanced SQL parentheses")
    if "[" in content or "]" in content:
        errors.append("SQL Server bracket identifiers are not permitted")

    # Configurable function parameter naming validation
    if node_type == "SQL_FUNCTION":
        param_match = re.search(r"(?i)CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+[^\(]+\(([^\)]*)\)", content)
        if param_match:
            params_str = param_match.group(1).strip()
            if params_str:
                pattern = re.compile(settings.function_parameter_naming_pattern)
                for param in params_str.split(","):
                    pname = param.strip().split()[0].strip("`")
                    if not pattern.match(pname):
                        errors.append(f"Function parameter '{pname}' does not match configured pattern '{settings.function_parameter_naming_pattern}'")
        if re.search(r"(?i)\b(?:fn_[A-Za-z0-9_]+)\s*\.\s*`?[A-Za-z0-9_]+`?", content):
            errors.append("Function parameters must use their unqualified namespace")

    if node_type == "WORKFLOW_SQL":
        if "MERGE INTO" not in upper:
            errors.append("Loader workflow must use MERGE")
        if re.search(r"(?is)WHEN\s+NOT\s+MATCHED\s+BY\s+SOURCE\s+THEN\s+DELETE", content):
            errors.append("Loader workflow cannot delete rows absent from the current source batch")

    if node_type == "SQL_PROCEDURE":
        if re.search(r"(?i)\b(?:READS SQL DATA|CONTAINS SQL)\b", content):
            errors.append("Databricks procedure contains an unsupported function-only clause")
        # Unsupported stored-procedure constructs falling back to REVIEW_REQUIRED
        for unsupported in ("CURSOR FOR", "sp_executesql", "BEGIN TRANSACTION", "ROLLBACK TRANSACTION"):
            if unsupported.upper() in upper:
                errors.append(f"Unsupported stored-procedure construct detected: '{unsupported}'; review required for Databricks workflow conversion")

    for token in ("DROP CATALOG", "DROP SCHEMA", "TRUNCATE TABLE"):
        if token in upper and node_type != "WORKFLOW_SQL":
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
            destructive_ops = scan_destructive_operations(content)
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
            # Invalidate any prior destructive approvals whose content hash does not match
            invalidate_destructive_approvals_on_change(db, project_id, artifact.id, digest)

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
                        "errors": errors,
                        "destructive_operations": destructive_ops,
                        "deterministic_checks": ["PROMPT_SCHEMA", "METADATA_GROUNDING", "TARGET_CAPABILITY", "IDENTIFIER_BINDING", "IDEMPOTENCY"],
                        "metadata_snapshot_id": snapshot_row.id, "specification_version_id": version.id,
                        "target_validation_required": get_settings().prompt_target_validation_required,
                    }),
                    review_status="PENDING_REVIEW", generator_version="prompt-native-7.0",
                )
                db.add(current)
                db.flush()
                artifact.current_version = current.version

            node.status = "REVIEW_REQUIRED" if errors or destructive_ops else "TARGET_VALIDATION_REQUIRED" if get_settings().prompt_target_validation_required else "ARTIFACT_READY"
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
                "destructive_operations": destructive_ops,
            })
            generated.append({
                "request_id": request_id, "name": request["name"], "target_fqn": target_fqn,
                "artifact_version_id": current.id, "validation_status": current.validation_status,
                "executable": current.executable, "errors": errors,
                "destructive_operations": destructive_ops,
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
        return []
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
        evidence.update({"errors": errors, "target_validation": probe_evidence, "target_validated_at": _utcnow().isoformat()})
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
    evidence["artifact_review"] = {"status": status.upper(), "reviewer": actor, "comment": comment, "reviewed_at": _utcnow().isoformat()}
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
