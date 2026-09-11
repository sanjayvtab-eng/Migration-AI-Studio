from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    CanonicalRecord,
    MigrationArtifact,
    MigrationArtifactVersion,
    MigrationColumn,
    MigrationConsumer,
    MigrationDependency,
    MigrationMapping,
    MigrationMedallionEdge,
    MigrationMedallionNode,
    MigrationObject,
    MigrationProject,
    MigrationReview,
    MigrationSemanticDefinition,
    MigrationStageArtifact,
    MigrationStageArtifactVersion,
)
from app.models.canonical import MigrationValidation
from app.services.engine import (
    _convert_function,
    _convert_procedure,
    _retarget_view_header,
    databricks_routine_contract_issues,
    normalize_databricks_routine_contract,
    qident,
    rewrite_common_tsql,
    uid,
)
from app.services.rules import classify_function, classify_procedure, classify_trigger, map_sqlserver_type
from app.core.config import get_settings
from app.services.ai_remediation import call_structured_llm

SEMANTIC_ROLES = {"FACT", "DIMENSION", "AGGREGATE", "KPI", "REPORTING", "ENTITY"}
GOLD_ROLES = {"FACT", "DIMENSION", "AGGREGATE", "KPI", "REPORTING"}
NUMERIC_TYPES = {"tinyint", "smallint", "int", "bigint", "decimal", "numeric", "money", "smallmoney", "float", "real"}
DATE_TYPES = {"date", "datetime", "datetime2", "smalldatetime", "datetimeoffset", "time"}
TEXT_TYPES = {"char", "varchar", "text", "nchar", "nvarchar", "ntext", "sysname", "xml"}

FACT_NAME_TOKENS = {
    "fact", "transaction", "txn", "order", "orderdetail", "detail", "line", "sales", "sale", "invoice",
    "payment", "movement", "event", "journal", "booking", "claim", "usage", "activity", "balance",
}
DIM_NAME_TOKENS = {
    "dim", "customer", "product", "supplier", "vendor", "employee", "date", "calendar", "location", "region",
    "category", "status", "reference", "lookup", "master", "account", "department", "channel", "currency",
}
REPORTING_TOKENS = {"report", "dashboard", "kpi", "semantic", "aggregate", "agg", "summary", "mart", "cube"}


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean_name(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_]+", "_", name or "").strip("_")
    return out or "model"


def _tokens(name: str) -> set[str]:
    # Split camel/pascal case as well as separators so OrderDetail becomes order/detail.
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name or "")
    return {x for x in re.split(r"[^a-z0-9]+", split.lower()) if x}


def _semantic_input_fingerprint(
    obj: MigrationObject,
    columns: list[MigrationColumn],
    primary_key: list[str],
    foreign_keys: list[dict[str, Any]],
    consumers: list[MigrationConsumer],
    stats: dict[str, Any],
) -> str:
    """Hash only evidence that can change a table's semantic classification."""
    payload = {
        "source_hash": obj.source_hash,
        "columns": [
            [c.column_name, c.data_type, c.nullable, c.precision, c.scale]
            for c in columns
        ],
        "primary_key": primary_key,
        "foreign_keys": foreign_keys,
        "consumer_signals": sorted({
            (c.consumer_type, c.usage_type, c.dependency_depth, c.evidence_type)
            for c in consumers
        }),
        "approx_row_count": stats.get("approx_row_count"),
    }
    return hashlib.sha256(_json(payload).encode()).hexdigest()


def _catalog_from_mappings(db: Session, project_id: str, environment: str) -> str | None:
    row = db.scalars(select(MigrationMapping).where(
        MigrationMapping.project_id == project_id,
        MigrationMapping.environment == environment.upper(),
    )).first()
    if not row:
        return None
    parts = [x.strip().strip("`") for x in row.target_fqn.split(".")]
    return parts[0] if len(parts) == 3 else None


def _columns(db: Session, project_id: str, object_id: str) -> list[MigrationColumn]:
    return list(db.scalars(select(MigrationColumn).where(
        MigrationColumn.project_id == project_id,
        MigrationColumn.object_id == object_id,
    ).order_by(MigrationColumn.ordinal)).all())


def _constraints(db: Session, project_id: str, object_id: str) -> list[dict[str, Any]]:
    rows = db.scalars(select(CanonicalRecord).where(
        CanonicalRecord.project_id == project_id,
        CanonicalRecord.object_id == object_id,
        CanonicalRecord.record_type == "CONSTRAINT",
    )).all()
    return [_loads(r.payload_json, {}) for r in rows]


def _table_stats(db: Session, project_id: str, object_id: str) -> dict[str, Any]:
    row = db.scalars(select(CanonicalRecord).where(
        CanonicalRecord.project_id == project_id,
        CanonicalRecord.object_id == object_id,
        CanonicalRecord.record_type == "TABLE_STATS",
    )).first()
    return _loads(row.payload_json, {}) if row else {}


def _primary_key(db: Session, project_id: str, object_id: str) -> list[str]:
    for c in _constraints(db, project_id, object_id):
        if str(c.get("type") or "").upper() == "PRIMARY_KEY":
            return [str(x) for x in c.get("columns") or []]
    return []


def _foreign_keys(db: Session, project_id: str, object_id: str) -> list[dict[str, Any]]:
    return [c for c in _constraints(db, project_id, object_id) if str(c.get("type") or "").upper() == "FOREIGN_KEY"]


def _consumer_usage(obj: MigrationObject) -> str:
    text = (obj.definition or "").lower()
    name_tokens = _tokens(obj.object_name)
    if obj.object_type == "TRIGGER":
        return "AUDIT_OR_SIDE_EFFECT"
    if obj.object_type == "PROCEDURE":
        if any(x in text for x in ("insert ", "update ", "delete ", "merge ")):
            return "TRANSFORMATION_WRITE"
        if any(x in text for x in ("group by", "sum(", "avg(", "count(")) or name_tokens & REPORTING_TOKENS:
            return "REPORTING_READ"
        return "ORCHESTRATION_OR_READ"
    if obj.object_type == "VIEW":
        if any(x in text for x in ("group by", "sum(", "avg(", "count(", "rollup", "cube")) or name_tokens & REPORTING_TOKENS:
            return "REPORTING_READ"
        return "TRANSFORMATION_READ"
    if obj.object_type == "FUNCTION":
        return "TRANSFORMATION_READ"
    return "READ"


def analyze_downstream_consumers(db: Session, project_id: str) -> dict[str, Any]:
    """Rebuild project-scoped downstream consumer evidence from discovered dependencies.

    The analysis is intentionally evidence-based. It records internal SQL dependencies and
    preserves user-registered/external consumer rows rather than inventing BI consumers that
    are not visible in SQL Server metadata.
    """
    if not db.get(MigrationProject, project_id):
        raise ValueError("Project not found")

    # Preserve explicitly registered external consumers; rebuild discovery-derived rows.
    db.query(MigrationConsumer).filter(
        MigrationConsumer.project_id == project_id,
        MigrationConsumer.evidence_type != "EXPLICIT_EXTERNAL",
    ).delete(synchronize_session=False)

    objects = list(db.scalars(select(MigrationObject).where(MigrationObject.project_id == project_id)).all())
    by_id = {o.id: o for o in objects}
    by_key = defaultdict(list)
    for o in objects:
        by_key[(o.schema_name.lower(), o.object_name.lower())].append(o)

    adjacency: dict[str, set[str]] = defaultdict(set)  # producer -> direct consumer
    evidence_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for dep in db.scalars(select(MigrationDependency).where(MigrationDependency.project_id == project_id)).all():
        consumer = by_id.get(dep.object_id)
        if not consumer or not dep.referenced_object:
            continue
        candidates: list[MigrationObject] = []
        if dep.referenced_schema:
            candidates = by_key.get((dep.referenced_schema.lower(), dep.referenced_object.lower()), [])
        else:
            candidates = [o for o in objects if o.object_name.lower() == dep.referenced_object.lower()]
        if len(candidates) != 1:
            continue
        producer = candidates[0]
        if producer.id == consumer.id:
            continue
        adjacency[producer.id].add(consumer.id)
        evidence_by_pair[(producer.id, consumer.id)].append({
            "dependency_type": dep.dependency_type,
            "referenced_column": dep.referenced_column,
            "referenced_database": dep.referenced_database,
            "referenced_schema": dep.referenced_schema,
        })

    # Build minimum-depth transitive downstream paths. Direct dependencies carry full
    # confidence; transitive consumers remain useful but their score decays with depth.
    created = 0
    for producer in objects:
        q = deque((cid, 1) for cid in sorted(adjacency.get(producer.id, set())))
        seen: dict[str, int] = {}
        while q:
            consumer_id, depth = q.popleft()
            if consumer_id in seen and seen[consumer_id] <= depth:
                continue
            seen[consumer_id] = depth
            consumer = by_id.get(consumer_id)
            if not consumer:
                continue
            direct_evidence = evidence_by_pair.get((producer.id, consumer_id), []) if depth == 1 else []
            db.add(MigrationConsumer(
                id=uid("CNS"), project_id=project_id, producer_object_id=producer.id,
                consumer_object_id=consumer.id,
                consumer_name=f"{consumer.schema_name}.{consumer.object_name}",
                consumer_type=consumer.object_type,
                usage_type=_consumer_usage(consumer), dependency_depth=depth,
                evidence_type="SQL_DEPENDENCY" if depth == 1 else "TRANSITIVE_DEPENDENCY",
                evidence_json=_json({"direct_evidence": direct_evidence, "path_depth": depth}),
                confidence_score=max(0.55, 1.0 - (depth - 1) * 0.12),
            ))
            created += 1
            for nxt in adjacency.get(consumer_id, set()):
                q.append((nxt, depth + 1))
    db.commit()

    rows = list(db.scalars(select(MigrationConsumer).where(MigrationConsumer.project_id == project_id)).all())
    per_object: dict[str, dict[str, Any]] = {}
    for o in objects:
        owned = [x for x in rows if x.producer_object_id == o.id]
        per_object[o.id] = {
            "object_id": o.id,
            "name": f"{o.schema_name}.{o.object_name}",
            "type": o.object_type,
            "direct_consumers": sum(1 for x in owned if x.dependency_depth == 1),
            "transitive_consumers": sum(1 for x in owned if x.dependency_depth > 1),
            "reporting_consumers": sum(1 for x in owned if "REPORTING" in x.usage_type),
            "write_consumers": sum(1 for x in owned if "WRITE" in x.usage_type),
            "max_depth": max([x.dependency_depth for x in owned], default=0),
        }
    return {
        "project_id": project_id,
        "consumer_records": len(rows),
        "internal_records_created": created,
        "explicit_external_records": sum(1 for x in rows if x.evidence_type == "EXPLICIT_EXTERNAL"),
        "objects": list(per_object.values()),
        "coverage_note": "Internal SQL dependencies are discovered automatically. BI tools, applications and files not visible to SQL Server must be registered explicitly or integrated through their metadata APIs.",
    }


def register_external_consumer(db: Session, project_id: str, object_id: str, *, name: str,
                               consumer_type: str, usage_type: str, evidence: dict[str, Any] | None = None) -> MigrationConsumer:
    obj = db.get(MigrationObject, object_id)
    if not obj or obj.project_id != project_id:
        raise ValueError("Producer object not found in project")
    row = MigrationConsumer(
        id=uid("CNS"), project_id=project_id, producer_object_id=object_id,
        consumer_object_id=None, consumer_name=name.strip(), consumer_type=consumer_type.upper().strip(),
        usage_type=usage_type.upper().strip(), dependency_depth=1, evidence_type="EXPLICIT_EXTERNAL",
        evidence_json=_json(evidence or {}), confidence_score=1.0,
    )
    db.add(row); db.commit(); return row


def _incoming_fk_count(db: Session, project_id: str, obj: MigrationObject) -> int:
    count = 0
    rows = db.scalars(select(CanonicalRecord).where(
        CanonicalRecord.project_id == project_id,
        CanonicalRecord.record_type == "CONSTRAINT",
    )).all()
    for row in rows:
        p = _loads(row.payload_json, {})
        if str(p.get("type") or "").upper() != "FOREIGN_KEY":
            continue
        if str(p.get("referenced_schema") or "").lower() == obj.schema_name.lower() and str(p.get("referenced_object") or "").lower() == obj.object_name.lower():
            count += 1
    return count


def infer_semantics(db: Session, project_id: str, *, refresh_consumers: bool = True) -> dict[str, Any]:
    if refresh_consumers:
        analyze_downstream_consumers(db, project_id)
    objects = list(db.scalars(select(MigrationObject).where(
        MigrationObject.project_id == project_id,
        MigrationObject.object_type == "TABLE",
    ).order_by(MigrationObject.schema_name, MigrationObject.object_name)).all())
    consumers = list(db.scalars(select(MigrationConsumer).where(MigrationConsumer.project_id == project_id)).all())
    results = []

    for obj in objects:
        cols = _columns(db, project_id, obj.id)
        pk = _primary_key(db, project_id, obj.id)
        fks = _foreign_keys(db, project_id, obj.id)
        incoming_fk = _incoming_fk_count(db, project_id, obj)
        owned_consumers = [x for x in consumers if x.producer_object_id == obj.id]
        reporting_consumers = sum(1 for x in owned_consumers if "REPORTING" in x.usage_type)
        tokens = _tokens(obj.object_name)

        key_names = {x.lower() for x in pk}
        for fk in fks:
            key_names.update(str(x).lower() for x in fk.get("columns") or [])
        # Conservative key-name evidence supplements missing constraint metadata but does
        # not replace it; it lowers confidence when real PK/FK evidence is unavailable.
        key_like = {c.column_name.lower() for c in cols if re.search(r"(?:^id$|id$|key$)", c.column_name, re.I)}
        numeric = [c for c in cols if c.data_type.lower().split("(", 1)[0] in NUMERIC_TYPES]
        dates = [c for c in cols if c.data_type.lower().split("(", 1)[0] in DATE_TYPES]
        texts = [c for c in cols if c.data_type.lower().split("(", 1)[0] in TEXT_TYPES]
        measures = [c.column_name for c in numeric if c.column_name.lower() not in key_names | key_like]
        attributes = [c.column_name for c in cols if c.column_name.lower() not in key_names and c.column_name not in measures]

        fact_score = 0.0; dim_score = 0.0; evidence: list[str] = []
        fact_name_hits = sorted(tokens & FACT_NAME_TOKENS)
        dim_name_hits = sorted(tokens & DIM_NAME_TOKENS)
        if fact_name_hits:
            fact_score += 3.0; evidence.append("fact_name_tokens=" + ",".join(fact_name_hits))
        if dim_name_hits:
            dim_score += 3.0; evidence.append("dimension_name_tokens=" + ",".join(dim_name_hits))
        if len(fks) >= 2:
            fact_score += 2.5; evidence.append(f"outgoing_foreign_keys={len(fks)}")
        elif len(fks) == 1:
            fact_score += 0.75
        if incoming_fk >= 1:
            dim_score += min(3.0, 1.5 + 0.5 * incoming_fk); evidence.append(f"incoming_foreign_keys={incoming_fk}")
        if len(measures) >= 2:
            fact_score += 2.0; evidence.append(f"numeric_measure_candidates={len(measures)}")
        elif len(measures) == 1:
            fact_score += 0.75
        if dates:
            fact_score += 0.75; evidence.append(f"date_columns={len(dates)}")
        if len(texts) >= 2:
            dim_score += 1.5; evidence.append(f"descriptive_columns={len(texts)}")
        if len(fks) <= 1 and len(texts) >= 1:
            dim_score += 0.75
        if reporting_consumers:
            fact_score += min(1.5, 0.5 * reporting_consumers); evidence.append(f"reporting_consumers={reporting_consumers}")

        max_score = max(fact_score, dim_score)
        diff = abs(fact_score - dim_score)
        role = "ENTITY"
        status = "REVIEW_REQUIRED"
        if fact_score >= 4.0 and fact_score >= dim_score + 1.25:
            role = "FACT"; status = "INFERRED"
        elif dim_score >= 4.0 and dim_score >= fact_score + 1.25:
            role = "DIMENSION"; status = "INFERRED"
        confidence = min(0.96, 0.50 + max_score * 0.045 + diff * 0.04)
        if not pk:
            confidence = max(0.35, confidence - 0.08); evidence.append("primary_key_metadata_missing")
        if not fks and incoming_fk == 0:
            confidence = max(0.35, confidence - 0.05); evidence.append("relationship_metadata_sparse")

        business_keys = pk or [c.column_name for c in cols if c.column_name.lower() in key_like][:2]
        grain = business_keys[:] if role == "FACT" else []
        dimension_keys = []
        for fk in fks:
            dimension_keys.extend(str(x) for x in fk.get("columns") or [])
        target_name = ("fact_" if role == "FACT" else "dim_" if role == "DIMENSION" else "entity_") + _clean_name(obj.object_name).lower()
        measure_specs = [{"name": m, "source_column": m, "aggregation": "NONE"} for m in measures]

        existing_rows = list(db.scalars(select(MigrationSemanticDefinition).where(
            MigrationSemanticDefinition.project_id == project_id,
            MigrationSemanticDefinition.object_id == obj.id,
        ).order_by(MigrationSemanticDefinition.created_at)).all())
        approved = next((row for row in existing_rows if row.status == "APPROVED"), None)
        explicit = next((row for row in existing_rows if row.definition_source == "EXPLICIT"), None)
        existing = next((row for row in existing_rows if row.definition_source == "INFERRED"), None)
        if not existing:
            # Reuse an unapproved AI candidate as the working inference row. It will
            # be refreshed deterministically first, then reconsidered by Hybrid V2.
            existing = next((row for row in existing_rows
                             if row.status != "APPROVED" and (row.definition_source or "").startswith("AI_ASSISTED_")), None)
        payload = {
            "fact_score": fact_score, "dimension_score": dim_score, "evidence": evidence,
            "outgoing_fk_count": len(fks), "incoming_fk_count": incoming_fk,
            "reporting_consumer_count": reporting_consumers,
            "approx_row_count": _table_stats(db, project_id, obj.id).get("approx_row_count"),
        }
        input_fingerprint = _semantic_input_fingerprint(
            obj, cols, pk, fks, owned_consumers, {"approx_row_count": payload["approx_row_count"]},
        )
        cached_ai = next((
            row for row in existing_rows
            if row.status == "AI_RECOMMENDED"
            and (row.definition_source or "").startswith("AI_ASSISTED_")
            and _loads(row.evidence_json, {}).get("input_fingerprint") == input_fingerprint
        ), None)
        protected = approved or explicit or cached_ai
        if protected:
            # Approved and explicit semantics are governed records regardless of
            # which inference engine created them. Preserve the canonical row and
            # remove stale unapproved inference duplicates for the same object.
            sem = protected
            for duplicate in existing_rows:
                if duplicate.id != sem.id and duplicate.status != "APPROVED":
                    db.delete(duplicate)
        else:
            if not existing:
                sem = MigrationSemanticDefinition(id=uid("SEM"), project_id=project_id, object_id=obj.id,
                                                  semantic_role=role, target_name=target_name)
                db.add(sem)
            else:
                sem = existing
            sem.semantic_role = role; sem.target_name = target_name
            sem.grain_json = _json(grain); sem.business_keys_json = _json(business_keys)
            sem.dimension_keys_json = _json(dimension_keys); sem.attributes_json = _json(attributes)
            sem.measures_json = _json(measure_specs); sem.scd_type = "1" if role == "DIMENSION" else None
            sem.definition_source = "INFERRED"; sem.status = status; sem.confidence_score = confidence
            sem.evidence_json = _json(payload)
        results.append({
            "id": sem.id, "object_id": obj.id, "name": f"{obj.schema_name}.{obj.object_name}",
            "role": sem.semantic_role, "status": sem.status, "confidence": sem.confidence_score,
            "target_name": sem.target_name, "business_keys": _loads(sem.business_keys_json, []),
            "grain": _loads(sem.grain_json, []), "dimension_keys": _loads(sem.dimension_keys_json, []),
            "measures": _loads(sem.measures_json, []), "attributes": _loads(sem.attributes_json, []),
            "evidence": _loads(sem.evidence_json, {}),
        })
    db.commit()
    return {
        "project_id": project_id,
        "tables_analyzed": len(results),
        "facts": sum(1 for x in results if x["role"] == "FACT"),
        "dimensions": sum(1 for x in results if x["role"] == "DIMENSION"),
        "review_required": sum(1 for x in results if x["status"] == "REVIEW_REQUIRED"),
        "definitions": results,
        "policy": "Inference recommends semantics. Gold generation requires an APPROVED semantic definition; business meaning is never invented.",
    }


def _sanitize_error(exc: Exception) -> str:
    """Return a safe, key-free string representation of an exception.

    The Gemini API key must never appear in ai_errors, logs, API responses,
    UI messages, downloaded logs, or test output.
    """
    try:
        _key = get_settings().llm_api_key or ""
    except Exception:
        _key = ""
    msg = str(exc)[:500]
    return msg.replace(_key, "***") if _key else msg


def infer_semantics_hybrid(db: Session, project_id: str) -> dict[str, Any]:
    """Run V1 deterministic inference first; use governed AI only for ambiguous objects.

    Governance guarantees:
    - APPROVED semantics are never overwritten; every field is preserved.
    - Invented columns (not in discovered schema) cause per-object fallback to
      REVIEW_REQUIRED and continue processing remaining objects.
    - AI recommendations are stored as AI_RECOMMENDED, never APPROVED.
    - API key is scrubbed from all error messages before storage.
    """
    baseline = infer_semantics(db, project_id)
    cfg = get_settings()
    baseline.update({
        "engine": "HYBRID_V2_2",
        "ai_provider": cfg.llm_provider.upper().strip(),
        "ai_attempted": 0,
        "ai_recommended": 0,
        "ai_corrected": 0,
        "ai_retry_attempts": 0,
        "ai_errors": [],
        "ai_usage": {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_tokens": 0},
        "ai_cache_hits": sum(
            1 for item in baseline["definitions"]
            if item["status"] == "AI_RECOMMENDED"
            and (item.get("evidence") or {}).get("input_fingerprint")
        ),
    })
    if not cfg.llm_enabled:
        baseline["policy"] += " AI is disabled; deterministic results were preserved."
        return baseline

    objects = {x.id: x for x in db.scalars(select(MigrationObject).where(MigrationObject.project_id == project_id)).all()}
    consumers_by_producer: dict[str, list[MigrationConsumer]] = {}
    for c in db.scalars(select(MigrationConsumer).where(MigrationConsumer.project_id == project_id)).all():
        consumers_by_producer.setdefault(c.producer_object_id, []).append(c)

    for item in baseline["definitions"]:
        if item["status"] != "REVIEW_REQUIRED":
            continue
        obj = objects.get(item["object_id"])
        sem = db.get(MigrationSemanticDefinition, item["id"])
        if not obj or not sem:
            continue

        # Correction 5: Never overwrite an APPROVED definition; preserve every field.
        if sem.status == "APPROVED":
            continue

        cols = _columns(db, project_id, obj.id)
        names = {c.column_name.lower(): c.column_name for c in cols}
        pk = _primary_key(db, project_id, obj.id)
        fks = _foreign_keys(db, project_id, obj.id)
        stats = _table_stats(db, project_id, obj.id)
        owned_consumers = consumers_by_producer.get(obj.id, [])
        input_fingerprint = _semantic_input_fingerprint(obj, cols, pk, fks, owned_consumers, stats)

        # Build structured evidence package (never includes API key or secrets).
        package = {
            "project_scoped_object": {
                "object_id": obj.id,
                "schema": obj.schema_name,
                "object_name": obj.object_name,
                "object_type": obj.object_type,
            },
            "columns": [
                {
                    "name": c.column_name,
                    "data_type": c.data_type,
                    "nullable": c.nullable,   # MigrationColumn.nullable (not is_nullable)
                    "precision": c.precision,
                    "scale": c.scale,
                }
                for c in cols
            ],
            "primary_keys": pk,
            "foreign_keys": fks,
            "deterministic_evidence": {
                "semantic_role": item.get("role"),
                "fact_score": item.get("evidence", {}).get("fact_score"),
                "dimension_score": item.get("evidence", {}).get("dimension_score"),
                # item["evidence"] is already the full evidence dict from infer_semantics
                "evidence_signals": item.get("evidence", {}).get("evidence") or [],
            },
            "downstream_consumer_signals": [
                {
                    "consumer_type": c.consumer_type,
                    "usage_type": c.usage_type,
                    "dependency_depth": c.dependency_depth,
                    "evidence_type": c.evidence_type,
                }
                for c in {
                    (x.consumer_type, x.usage_type, x.dependency_depth, x.evidence_type): x
                    for x in owned_consumers
                }.values()
            ],
            "approx_row_count": stats.get("approx_row_count"),
        }

        prompt = (
            "Classify this SQL Server table for a Databricks medallion Gold semantic layer.\n"
            "Allowed roles: FACT, DIMENSION, AGGREGATE, KPI, REPORTING, ENTITY.\n"
            "Return JSON only with these fields:\n"
            "  role, confidence (0.0–1.0), grain, business_keys, dimension_keys, attributes,\n"
            "  measures [{name, source_column, aggregation}], reasoning_summary, conflicts, missing_evidence.\n\n"
            "Classification rules (classify from evidence, not from the object name alone):\n"
            "- FACT: transaction-level or periodic event table with additive measures and grain (transaction key, business key, or date).\n"
            "- DIMENSION: master data, entity, or reference table with a stable business key and descriptive attributes, referenced by other tables.\n"
            "- AGGREGATE: pre-aggregated summary table or view containing grouped metrics/measures (e.g. Total*, Count*, Amount*, Quantity*) grouped by dimension/business keys (e.g. CustomerID), or with GROUP BY aggregation evidence.\n"
            "- KPI: derived metric aggregation with business KPI semantics.\n"
            "- REPORTING: pre-built summary or reporting view without standard fact/dim semantics.\n"
            "- ENTITY: base relational entity only when the table is not an aggregate, fact, or dimension.\n\n"
            "Structural requirements (reject if not met):\n"
            "- FACT: grain and measures are both required.\n"
            "- DIMENSION: business_keys is required.\n"
            "- AGGREGATE / KPI: measures are required.\n"
            "- Every column you reference must appear in the supplied columns list; never invent columns.\n\n"
            "Evidence:\n"
            + json.dumps(package, default=str)
        )

        baseline["ai_attempted"] += 1
        correction_history: list[dict[str, Any]] = []
        object_usage = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_tokens": 0}
        request_prompt = prompt
        semantic_attempt_limit = min(3, max(1, cfg.llm_max_attempts))
        for semantic_attempt in range(1, semantic_attempt_limit + 1):
            if semantic_attempt > 1:
                baseline["ai_retry_attempts"] += 1
            try:
                raw, provider, model = call_structured_llm(request_prompt)
                call_usage = raw.pop("_provider_usage", {}) or {}
                for usage_key in object_usage:
                    used = max(0, int(call_usage.get(usage_key) or 0))
                    object_usage[usage_key] += used
                    baseline["ai_usage"][usage_key] += used

                role = str(raw.get("role") or "ENTITY").upper().strip()
                if role not in SEMANTIC_ROLES:
                    raise ValueError(f"Unsupported semantic role returned by AI: {role!r}")

                confidence = max(0.0, min(1.0, float(raw.get("confidence") or 0)))

            # Correction 3: Strict column validation per object.
            # Any invented column raises ValueError → falls back to REVIEW_REQUIRED for this
            # object and continues processing the remaining objects (not a total failure).
                def _clean_token(v: Any) -> str:
                    s = str(v or "").strip()
                    return re.sub(r"^[`'\"\[]+|[`'\"\]]+$", "", s).strip()

                def _resolve_col(value: str) -> str | None:
                    """Resolve a column name against discovered columns; raise on invented names."""
                    token = _clean_token(value)
                    if not token or token.lower() in {"none", "n/a", "null", "-", "no grain", "no key", "no business keys"}:
                        return None
                    resolved = names.get(token.lower())
                    if resolved is None:
                        raise ValueError(
                            f"AI returned column {value!r} which does not exist in the discovered "
                            f"schema for {obj.schema_name}.{obj.object_name}."
                        )
                    return resolved

                def _as_list(val) -> list:
                    if val is None: return []
                    if isinstance(val, str): return [val]
                    if isinstance(val, list): return val
                    return [val]

                safe_repairs: list[dict[str, Any]] = []
                grain = [col for v in _as_list(raw.get("grain")) if (col := _resolve_col(v)) is not None]
                business_keys = [col for v in _as_list(raw.get("business_keys")) if (col := _resolve_col(v)) is not None]
                dimension_keys = [col for v in _as_list(raw.get("dimension_keys")) if (col := _resolve_col(v)) is not None]
                attributes: list[str] = []
                for value in _as_list(raw.get("attributes")):
                    token = _clean_token(value)
                    if not token or token.lower() in {"none", "n/a", "null", "-"}:
                        continue
                    resolved = names.get(token.lower())
                    if resolved is None:
                        # Attributes are optional descriptive hints. Removing an invented
                        # attribute is safe when all role-critical fields validate below.
                        safe_repairs.append({
                            "field": "attributes",
                            "value": str(value),
                            "action": "REMOVED_UNKNOWN_OPTIONAL_COLUMN",
                        })
                        continue
                    attributes.append(resolved)

                measures: list[dict] = []
                for m in raw.get("measures") or []:
                    if not isinstance(m, dict):
                        continue
                    raw_source = _clean_token(m.get("source_column") or m.get("name") or "")
                    source = _resolve_col(raw_source)
                    if not source:
                        continue
                    measures.append({
                        "name": _clean_token(m.get("name") or source),
                        "source_column": source,
                        "aggregation": str(m.get("aggregation") or "NONE").upper(),
                    })

                if role == "AGGREGATE":
                    if not grain and business_keys:
                        grain = business_keys[:]
                    elif not business_keys and grain:
                        business_keys = grain[:]
                    elif not grain and not business_keys and pk:
                        grain = pk[:]
                        business_keys = pk[:]

            # Low confidence or ENTITY → preserve REVIEW_REQUIRED, do not store.
                if role == "ENTITY" or confidence < 0.75:
                    break

            # Structural role requirements.
                if role == "FACT" and (not grain or not measures):
                    raise ValueError(f"AI recommended FACT for {obj.object_name} but grain or measures are missing after column validation.")
                if role == "DIMENSION" and not business_keys:
                    raise ValueError(f"AI recommended DIMENSION for {obj.object_name} but business_keys are missing after column validation.")
                if role in {"AGGREGATE", "KPI"} and not measures:
                    raise ValueError(f"AI recommended {role} for {obj.object_name} but measures are missing after column validation.")

            # Deduplicate lists preserving order.
                def _dedup(lst: list) -> list:
                    seen: set = set(); out = []
                    for x in lst:
                        if x not in seen:
                            seen.add(x); out.append(x)
                    return out

                grain = _dedup(grain)
                business_keys = _dedup(business_keys)
                dimension_keys = _dedup(dimension_keys)
                attributes = _dedup(attributes)

                sem.semantic_role = role
                sem.target_name = (
                    ("fact_" if role == "FACT" else "dim_" if role == "DIMENSION" else "gold_")
                    + _clean_name(obj.object_name).lower()
                )
                sem.grain_json = _json(grain)
                sem.business_keys_json = _json(business_keys)
                sem.dimension_keys_json = _json(dimension_keys)
                sem.attributes_json = _json(attributes)
                sem.measures_json = _json(measures)
                sem.scd_type = "1" if role == "DIMENSION" else None
                sem.definition_source = "AI_ASSISTED_HYBRID_V2_2"
                sem.status = "AI_RECOMMENDED"
                sem.confidence_score = confidence
                sem.evidence_json = _json({
                    "provider": provider,
                    "model": model,
                    "deterministic": item.get("evidence"),
                    "reasoning_summary": raw.get("reasoning_summary"),
                    "conflicts": raw.get("conflicts") or [],
                    "missing_evidence": raw.get("missing_evidence") or [],
                    "column_validation": "PASSED",
                    "semantic_attempts": semantic_attempt,
                    "automatically_corrected": semantic_attempt > 1 or bool(safe_repairs),
                    "safe_repairs": safe_repairs,
                    "correction_history": correction_history,
                    "input_fingerprint": input_fingerprint,
                    "provider_usage": object_usage,
                })
                baseline["ai_recommended"] += 1
                if semantic_attempt > 1 or safe_repairs:
                    baseline["ai_corrected"] += 1
                break

            except ValueError as exc:
                safe_err = _sanitize_error(exc)
                correction_history.append({"attempt": semantic_attempt, "validation_error": safe_err})
                if semantic_attempt >= semantic_attempt_limit:
                    baseline["ai_errors"].append({
                        "object": f"{obj.schema_name}.{obj.object_name}",
                        "error": safe_err,
                        "attempts": semantic_attempt,
                    })
                    break
                valid_columns = [c.column_name for c in cols]
                request_prompt = (
                    prompt
                    + "\n\nCORRECTION REQUIRED. Your previous JSON failed deterministic validation.\n"
                    + f"Validation error: {safe_err}\n"
                    + "Use only these exact, case-preserved source column names: "
                    + json.dumps(valid_columns)
                    + "\nDo not use friendly labels, derived names, table names, spaces not present in the list, "
                      "or any other column. Correct structural omissions too. Return the complete corrected JSON only.\n"
                    + "Previous response:\n"
                    + json.dumps(raw, separators=(",", ":"), default=str)[:4000]
                )
            except Exception as exc:
                safe_err = _sanitize_error(exc)
                baseline["ai_errors"].append({
                    "object": f"{obj.schema_name}.{obj.object_name}",
                    "error": safe_err,
                    "attempts": semantic_attempt,
                })
                break

    db.commit()
    baseline["definitions"] = list_semantics(db, project_id)
    baseline["review_required"] = sum(1 for x in baseline["definitions"] if x["status"] == "REVIEW_REQUIRED")
    baseline["policy"] = (
        "Hybrid V2.2 validates, safely repairs, revalidates, then delivers recommendations with deterministic fallback. "
        "Unknown optional attributes are removed with evidence; invalid keys, grain, measures or structures receive up to two correction attempts. "
        "Unchanged AI recommendations are reused by evidence fingerprint without another provider call. "
        "AI results are AI_RECOMMENDED and never auto-approved or auto-deployed."
    )
    return baseline


def list_semantics(db: Session, project_id: str) -> list[dict[str, Any]]:
    objects = {o.id: o for o in db.scalars(select(MigrationObject).where(MigrationObject.project_id == project_id)).all()}
    rows = db.scalars(select(MigrationSemanticDefinition).where(
        MigrationSemanticDefinition.project_id == project_id,
    ).order_by(MigrationSemanticDefinition.created_at)).all()
    result = []
    for s in rows:
        obj = objects.get(s.object_id) if s.object_id else None
        _obj_name = f"{obj.schema_name}.{obj.object_name}" if obj else None
        result.append({
            "id": s.id, "object_id": s.object_id,
            # Canonical fields
            "object_name": _obj_name,
            "semantic_role": s.semantic_role,
            # Backward-compatible aliases (existing tests use x['name'] and x['role'])
            "name": _obj_name,
            "role": s.semantic_role,
            "target_name": s.target_name,
            "grain": _loads(s.grain_json, []), "business_keys": _loads(s.business_keys_json, []),
            "dimension_keys": _loads(s.dimension_keys_json, []), "attributes": _loads(s.attributes_json, []),
            "measures": _loads(s.measures_json, []), "scd_type": s.scd_type,
            "definition_source": s.definition_source, "status": s.status,
            "confidence": s.confidence_score, "evidence": _loads(s.evidence_json, {}),
            "approved_by": s.approved_by, "approved_at": s.approved_at,
        })
    return result


def _validate_semantic_columns(db: Session, project_id: str, object_id: str, data: dict[str, Any]) -> list[str]:
    names = {c.column_name.lower(): c.column_name for c in _columns(db, project_id, object_id)}
    errors = []
    fields = ["grain", "business_keys", "dimension_keys", "attributes"]
    for field in fields:
        for col in data.get(field) or []:
            if str(col).lower() not in names:
                errors.append(f"{field} references unknown column {col}")
    for measure in data.get("measures") or []:
        source_col = measure.get("source_column") if isinstance(measure, dict) else None
        if source_col and str(source_col).lower() not in names:
            errors.append(f"measure {measure.get('name') or source_col} references unknown column {source_col}")
    return errors


def upsert_explicit_semantic(db: Session, project_id: str, object_id: str, data: dict[str, Any]) -> MigrationSemanticDefinition:
    obj = db.get(MigrationObject, object_id)
    if not obj or obj.project_id != project_id:
        raise ValueError("Object not found in project")
    role = str(data.get("semantic_role") or "").upper().strip()
    if role not in SEMANTIC_ROLES:
        raise ValueError("semantic_role must be FACT, DIMENSION, AGGREGATE, KPI, REPORTING or ENTITY")
    errors = _validate_semantic_columns(db, project_id, object_id, data)
    if role == "FACT" and not (data.get("grain") or []): errors.append("FACT requires explicit grain columns")
    if role == "FACT" and not (data.get("measures") or []): errors.append("FACT requires at least one explicit measure")
    if role == "DIMENSION" and not (data.get("business_keys") or []): errors.append("DIMENSION requires an explicit business key")
    if role in {"AGGREGATE", "KPI"} and not (data.get("measures") or []): errors.append(f"{role} requires explicit measures")
    if errors:
        raise ValueError("; ".join(errors))
    target_name = _clean_name(str(data.get("target_name") or (("fact_" if role == "FACT" else "dim_" if role == "DIMENSION" else "gold_") + obj.object_name))).lower()
    row = db.scalar(select(MigrationSemanticDefinition).where(
        MigrationSemanticDefinition.project_id == project_id,
        MigrationSemanticDefinition.object_id == object_id,
        MigrationSemanticDefinition.definition_source == "EXPLICIT",
        MigrationSemanticDefinition.target_name == target_name,
    ))
    if not row:
        row = MigrationSemanticDefinition(id=uid("SEM"), project_id=project_id, object_id=object_id,
                                          semantic_role=role, target_name=target_name)
        db.add(row)
    row.semantic_role = role; row.target_name = target_name
    row.grain_json = _json(data.get("grain") or []); row.business_keys_json = _json(data.get("business_keys") or [])
    row.dimension_keys_json = _json(data.get("dimension_keys") or []); row.attributes_json = _json(data.get("attributes") or [])
    row.measures_json = _json(data.get("measures") or []); row.scd_type = str(data.get("scd_type") or "1") if role == "DIMENSION" else None
    row.definition_source = "EXPLICIT"; row.status = "PENDING_APPROVAL"; row.confidence_score = 1.0
    row.evidence_json = _json({"source": "USER_EXPLICIT_BUSINESS_SEMANTICS", "notes": data.get("notes") or ""})
    row.approved_by = None; row.approved_at = None
    db.commit(); return row


def approve_semantic(
    db: Session, project_id: str, semantic_id: str, actor: str, role: str | None = None
) -> MigrationSemanticDefinition:
    row = db.get(MigrationSemanticDefinition, semantic_id)
    if not row or row.project_id != project_id:
        raise ValueError("Semantic definition not found in project")

    if role:
        role_upper = str(role).upper().strip()
        if role_upper not in GOLD_ROLES:
            raise ValueError(f"Role must be one of {', '.join(sorted(GOLD_ROLES))}")
        row.semantic_role = role_upper
        obj = db.get(MigrationObject, row.object_id) if row.object_id else None
        obj_name = obj.object_name if obj else "model"
        row.target_name = (
            ("fact_" if role_upper == "FACT" else "dim_" if role_upper == "DIMENSION" else "agg_" if role_upper == "AGGREGATE" else "gold_")
            + _clean_name(obj_name).lower()
        )
        if obj:
            cols = _columns(db, project_id, obj.id)
            pk = _primary_key(db, project_id, obj.id)
            key_like = [c.column_name for c in cols if re.search(r"(?:^id$|id$|key$)", c.column_name, re.I)]
            keys = pk or key_like[:2]
            current_bk = _loads(row.business_keys_json, [])
            current_grain = _loads(row.grain_json, [])
            current_measures = _loads(row.measures_json, [])
            if not current_bk and keys:
                row.business_keys_json = _json(keys)
            if not current_grain and keys and role_upper in {"FACT", "AGGREGATE"}:
                row.grain_json = _json(keys)
            if not current_measures and role_upper in {"FACT", "AGGREGATE", "KPI"}:
                numeric = [c.column_name for c in cols if c.data_type.lower().split("(", 1)[0] in NUMERIC_TYPES and c.column_name not in keys]
                if numeric:
                    row.measures_json = _json([{"name": m, "source_column": m, "aggregation": "NONE"} for m in numeric])

    if row.semantic_role not in GOLD_ROLES:
        raise ValueError("Only FACT/DIMENSION/AGGREGATE/KPI/REPORTING definitions can be approved for Gold generation")
    # Revalidate at approval time so source drift cannot silently invalidate business semantics.
    data = {
        "grain": _loads(row.grain_json, []), "business_keys": _loads(row.business_keys_json, []),
        "dimension_keys": _loads(row.dimension_keys_json, []), "attributes": _loads(row.attributes_json, []),
        "measures": _loads(row.measures_json, []),
    }
    errors = _validate_semantic_columns(db, project_id, row.object_id, data) if row.object_id else ["source object missing"]
    if errors:
        raise ValueError("Semantic approval blocked: " + "; ".join(errors))
    if row.semantic_role == "FACT" and (not data["grain"] or not data["measures"]):
        raise ValueError("FACT approval requires explicit grain and measures")
    if row.semantic_role == "DIMENSION" and not data["business_keys"]:
        raise ValueError("DIMENSION approval requires an explicit business key")
    if row.semantic_role in {"AGGREGATE", "KPI"} and not data["measures"]:
        raise ValueError(f"{row.semantic_role} approval requires explicit measures")
    row.status = "APPROVED"; row.approved_by = actor; row.approved_at = datetime.utcnow()
    db.commit(); return row


def approve_all_semantics(db: Session, project_id: str, actor: str) -> dict[str, Any]:
    rows = list(db.scalars(select(MigrationSemanticDefinition).where(
        MigrationSemanticDefinition.project_id == project_id,
        MigrationSemanticDefinition.status != "APPROVED",
    )).all())
    approved_count = 0
    errors = []
    for row in rows:
        target_role = None
        if row.semantic_role not in GOLD_ROLES:
            measures = _loads(row.measures_json, [])
            target_role = "AGGREGATE" if measures else "DIMENSION"
        try:
            approve_semantic(db, project_id, row.id, actor, role=target_role)
            approved_count += 1
        except Exception as exc:
            errors.append(f"{row.target_name or row.id}: {exc}")
    db.commit()
    return {"approved_count": approved_count, "errors": errors, "total": len(rows)}


def approve_all_medallion_artifacts(
    db: Session, project_id: str, *, environment: str = "DEV", reviewer: str = "system"
) -> dict[str, Any]:
    env = environment.upper()
    artifacts = list_medallion_artifacts(db, project_id, environment=env)
    approved_count = 0
    errors = []
    for a in artifacts:
        can_approve = (a["validation_status"] == "PASSED" and a["executable"]) or a.get("node_type") == "ARCHITECTURE_REVIEW"
        if can_approve and a["review_status"] != "APPROVED":
            try:
                review_medallion_artifact(db, project_id, a["artifact_version_id"], status="APPROVED", reviewer=reviewer)
                approved_count += 1
            except Exception as exc:
                errors.append(f"{a['target_fqn']}: {exc}")
    db.commit()
    return {"approved_count": approved_count, "errors": errors, "total": len(artifacts)}


def _upsert_node(db: Session, *, project_id: str, source_object_id: str | None, semantic_definition_id: str | None,
                 environment: str, layer: str, node_type: str, model_role: str, target_name: str, target_fqn: str,
                 generation_strategy: str, confidence: float = 1.0, status: str = "PLANNED",
                 review_required: bool = False, lineage: dict[str, Any] | None = None,
                 transformation: dict[str, Any] | None = None) -> MigrationMedallionNode:
    row = db.scalar(select(MigrationMedallionNode).where(
        MigrationMedallionNode.project_id == project_id,
        MigrationMedallionNode.environment == environment.upper(),
        MigrationMedallionNode.target_fqn == target_fqn,
    ))
    if not row:
        row = MigrationMedallionNode(id=uid("MDN"), project_id=project_id, environment=environment.upper(),
                                     layer=layer, node_type=node_type, model_role=model_role,
                                     target_name=target_name, target_fqn=target_fqn,
                                     generation_strategy=generation_strategy)
        db.add(row)
    row.source_object_id = source_object_id; row.semantic_definition_id = semantic_definition_id
    row.layer = layer; row.node_type = node_type; row.model_role = model_role; row.target_name = target_name
    row.generation_strategy = generation_strategy; row.confidence_score = confidence; row.status = status
    row.review_required = review_required; row.lineage_json = _json(lineage or {}); row.transformation_json = _json(transformation or {})
    return row


def _upsert_edge(db: Session, project_id: str, environment: str, from_id: str, to_id: str,
                 edge_type: str, evidence: dict[str, Any] | None = None) -> None:
    row = db.scalar(select(MigrationMedallionEdge).where(
        MigrationMedallionEdge.project_id == project_id,
        MigrationMedallionEdge.environment == environment.upper(),
        MigrationMedallionEdge.from_node_id == from_id,
        MigrationMedallionEdge.to_node_id == to_id,
        MigrationMedallionEdge.edge_type == edge_type,
    ))
    if not row:
        db.add(MigrationMedallionEdge(id=uid("MDE"), project_id=project_id, environment=environment.upper(),
                                     from_node_id=from_id, to_node_id=to_id, edge_type=edge_type,
                                     evidence_json=_json(evidence or {})))
    else:
        row.evidence_json = _json(evidence or {})


def build_medallion_plan(db: Session, project_id: str, *, environment: str = "DEV", catalog: str | None = None) -> dict[str, Any]:
    if not db.get(MigrationProject, project_id):
        raise ValueError("Project not found")
    env = environment.upper()
    catalog = (catalog or _catalog_from_mappings(db, project_id, env) or "").strip().strip("`")
    if not catalog:
        raise ValueError("Target catalog is required. Create mappings first or pass catalog explicitly.")

    # Consumer evidence influences semantic recommendations and is refreshed before planning.
    analyze_downstream_consumers(db, project_id)
    if not db.scalars(select(MigrationSemanticDefinition).where(MigrationSemanticDefinition.project_id == project_id)).first():
        infer_semantics(db, project_id, refresh_consumers=False)

    objects = list(db.scalars(select(MigrationObject).where(MigrationObject.project_id == project_id).order_by(
        MigrationObject.schema_name, MigrationObject.object_name)).all())
    approved_semantics = list(db.scalars(select(MigrationSemanticDefinition).where(
        MigrationSemanticDefinition.project_id == project_id,
        MigrationSemanticDefinition.status == "APPROVED",
    )).all())
    approved_by_object = defaultdict(list)
    for sem in approved_semantics:
        approved_by_object[sem.object_id].append(sem)

    nodes_by_object_layer: dict[tuple[str, str], MigrationMedallionNode] = {}
    for obj in objects:
        source_fqn = f"sqlserver://{obj.database_name}/{obj.schema_name}/{obj.object_name}"
        source_node = _upsert_node(
            db, project_id=project_id, source_object_id=obj.id, semantic_definition_id=None, environment=env,
            layer="SOURCE", node_type="SOURCE_OBJECT", model_role=obj.object_type, target_name=obj.object_name,
            target_fqn=source_fqn, generation_strategy="SOURCE_METADATA", confidence=1.0, status="DISCOVERED",
            lineage={"database": obj.database_name, "schema": obj.schema_name, "object": obj.object_name},
        )
        nodes_by_object_layer[(obj.id, "SOURCE")] = source_node

        if obj.object_type == "TABLE":
            bronze_fqn = f"{qident(catalog)}.{qident('bronze')}.{qident(obj.object_name)}"
            bronze = _upsert_node(
                db, project_id=project_id, source_object_id=obj.id, semantic_definition_id=None, environment=env,
                layer="BRONZE", node_type="DELTA_TABLE", model_role="RAW", target_name=obj.object_name,
                target_fqn=bronze_fqn, generation_strategy="SOURCE_ALIGNED_DELTA", confidence=1.0,
                lineage={"source_object_id": obj.id}, transformation={"mode": "RAW_INGEST", "business_transformations": False},
            )
            silver_fqn = f"{qident(catalog)}.{qident('silver')}.{qident(obj.object_name)}"
            silver = _upsert_node(
                db, project_id=project_id, source_object_id=obj.id, semantic_definition_id=None, environment=env,
                layer="SILVER", node_type="VIEW", model_role="CONFORMED_ENTITY", target_name=obj.object_name,
                target_fqn=silver_fqn, generation_strategy="STANDARDIZED_PASSTHROUGH", confidence=0.98,
                lineage={"source_object_id": obj.id, "bronze_target": bronze_fqn},
                transformation={"mode": "PASSTHROUGH", "note": "No business rule fabricated; source-aligned typed columns are exposed as a reusable Silver entity."},
            )
            nodes_by_object_layer[(obj.id, "BRONZE")] = bronze; nodes_by_object_layer[(obj.id, "SILVER")] = silver
            _upsert_edge(db, project_id, env, source_node.id, bronze.id, "RAW_INGEST", {"source_object_id": obj.id})
            _upsert_edge(db, project_id, env, bronze.id, silver.id, "STANDARDIZE", {"business_rule_fabricated": False})
        elif obj.object_type == "VIEW":
            silver_fqn = f"{qident(catalog)}.{qident('silver')}.{qident(obj.object_name)}"
            silver = _upsert_node(
                db, project_id=project_id, source_object_id=obj.id, semantic_definition_id=None, environment=env,
                layer="SILVER", node_type="VIEW", model_role="TRANSFORMATION", target_name=obj.object_name,
                target_fqn=silver_fqn, generation_strategy="CONVERT_SOURCE_VIEW", confidence=0.90,
                lineage={"source_object_id": obj.id}, transformation={"mode": "SOURCE_VIEW_CONVERSION"},
            )
            nodes_by_object_layer[(obj.id, "SILVER")] = silver
            _upsert_edge(db, project_id, env, source_node.id, silver.id, "CONVERT_LOGIC", {})
        elif obj.object_type in {"PROCEDURE", "FUNCTION"}:
            if obj.object_type == "PROCEDURE":
                intent, target = classify_procedure(obj.definition or "")
                node_type = "SQL_PROCEDURE" if target.startswith("Databricks SQL") else "ROUTINE_PLAN"
                role = intent
            else:
                intent, target = classify_function(obj.definition or "")
                node_type = "SQL_FUNCTION" if "SQL" in target else "FUNCTION_PLAN"
                role = intent
            fqn = f"{qident(catalog)}.{qident('silver')}.{qident(obj.object_name)}"
            routine = _upsert_node(
                db, project_id=project_id, source_object_id=obj.id, semantic_definition_id=None, environment=env,
                layer="SILVER", node_type=node_type, model_role=role, target_name=obj.object_name, target_fqn=fqn,
                generation_strategy=target.replace(" ", "_").upper(), confidence=0.80,
                review_required=("MANUAL" in target.upper() or "REVIEW" in target.upper() or "PYSPARK" in target.upper()),
                lineage={"source_object_id": obj.id}, transformation={"intent": intent, "recommended_target": target},
            )
            nodes_by_object_layer[(obj.id, "SILVER")] = routine
            _upsert_edge(db, project_id, env, source_node.id, routine.id, "CONVERT_LOGIC", {"intent": intent})
        elif obj.object_type == "TRIGGER":
            intent, target = classify_trigger(obj.definition or "")
            fqn = f"architecture-review://{obj.schema_name}/{obj.object_name}"
            trg = _upsert_node(
                db, project_id=project_id, source_object_id=obj.id, semantic_definition_id=None, environment=env,
                layer="SILVER", node_type="ARCHITECTURE_REVIEW", model_role=intent, target_name=obj.object_name,
                target_fqn=fqn, generation_strategy=target.replace(" ", "_").upper(), confidence=0.70,
                status="REVIEW_REQUIRED", review_required=True,
                transformation={"trigger_intent": intent, "recommended_target": target},
            )
            nodes_by_object_layer[(obj.id, "SILVER")] = trg
            _upsert_edge(db, project_id, env, source_node.id, trg.id, "REDESIGN_LOGIC", {"intent": intent})

    # Add dependency lineage between generated nodes. Tables feed Silver views/routines through
    # their Bronze targets; converted views/functions feed consumers through Silver targets.
    object_lookup = {(o.schema_name.lower(), o.object_name.lower()): o for o in objects}
    for dep in db.scalars(select(MigrationDependency).where(MigrationDependency.project_id == project_id)).all():
        consumer_node = nodes_by_object_layer.get((dep.object_id, "SILVER"))
        if not consumer_node or not dep.referenced_object:
            continue
        producer = None
        if dep.referenced_schema:
            producer = object_lookup.get((dep.referenced_schema.lower(), dep.referenced_object.lower()))
        else:
            matches = [o for o in objects if o.object_name.lower() == dep.referenced_object.lower()]
            producer = matches[0] if len(matches) == 1 else None
        if not producer:
            continue
        producer_node = nodes_by_object_layer.get((producer.id, "BRONZE")) or nodes_by_object_layer.get((producer.id, "SILVER"))
        if producer_node and producer_node.id != consumer_node.id:
            _upsert_edge(db, project_id, env, producer_node.id, consumer_node.id, "READS_FROM", {
                "dependency_type": dep.dependency_type, "referenced_column": dep.referenced_column,
            })

    # Gold nodes are generated only from explicit/approved business semantics. Inferred semantics
    # remain recommendations until a person approves them, preventing fabricated KPIs/models.
    for sem in approved_semantics:
        obj = next((o for o in objects if o.id == sem.object_id), None)
        if not obj or sem.semantic_role not in GOLD_ROLES:
            continue
        silver = nodes_by_object_layer.get((obj.id, "SILVER"))
        if not silver:
            continue
        gold_fqn = f"{qident(catalog)}.{qident('gold')}.{qident(sem.target_name)}"
        gold = _upsert_node(
            db, project_id=project_id, source_object_id=obj.id, semantic_definition_id=sem.id, environment=env,
            layer="GOLD", node_type="SEMANTIC_MODEL", model_role=sem.semantic_role,
            target_name=sem.target_name, target_fqn=gold_fqn,
            generation_strategy=f"EXPLICIT_{sem.semantic_role}_MODEL", confidence=1.0,
            status="PLANNED", review_required=False,
            lineage={"silver_node_id": silver.id, "semantic_definition_id": sem.id},
            transformation={
                "grain": _loads(sem.grain_json, []), "business_keys": _loads(sem.business_keys_json, []),
                "dimension_keys": _loads(sem.dimension_keys_json, []), "attributes": _loads(sem.attributes_json, []),
                "measures": _loads(sem.measures_json, []), "scd_type": sem.scd_type,
            },
        )
        nodes_by_object_layer[(obj.id, f"GOLD:{sem.id}")] = gold
        _upsert_edge(db, project_id, env, silver.id, gold.id, "SERVES_GOLD", {"semantic_role": sem.semantic_role})

    db.commit()
    return medallion_plan(db, project_id, environment=env)


def medallion_plan(db: Session, project_id: str, *, environment: str = "DEV") -> dict[str, Any]:
    env = environment.upper()
    nodes = list(db.scalars(select(MigrationMedallionNode).where(
        MigrationMedallionNode.project_id == project_id,
        MigrationMedallionNode.environment == env,
    ).order_by(MigrationMedallionNode.layer, MigrationMedallionNode.target_name)).all())
    edges = list(db.scalars(select(MigrationMedallionEdge).where(
        MigrationMedallionEdge.project_id == project_id,
        MigrationMedallionEdge.environment == env,
    )).all())
    semantics = list_semantics(db, project_id)
    consumer_rows = list(db.scalars(select(MigrationConsumer).where(MigrationConsumer.project_id == project_id)).all())
    counts = defaultdict(int)
    for n in nodes: counts[n.layer] += 1
    return {
        "project_id": project_id, "environment": env,
        "counts": dict(counts),
        "nodes": [{
            "id": n.id, "source_object_id": n.source_object_id, "semantic_definition_id": n.semantic_definition_id,
            "layer": n.layer, "node_type": n.node_type, "model_role": n.model_role,
            "target_name": n.target_name, "target_fqn": n.target_fqn,
            "generation_strategy": n.generation_strategy, "confidence": n.confidence_score,
            "status": n.status, "review_required": n.review_required,
            "lineage": _loads(n.lineage_json, {}), "transformation": _loads(n.transformation_json, {}),
        } for n in nodes],
        "edges": [{"id": e.id, "from_node_id": e.from_node_id, "to_node_id": e.to_node_id,
                   "edge_type": e.edge_type, "evidence": _loads(e.evidence_json, {})} for e in edges],
        "semantics": semantics,
        "consumer_summary": {
            "records": len(consumer_rows),
            "reporting": sum(1 for x in consumer_rows if "REPORTING" in x.usage_type),
            "external": sum(1 for x in consumer_rows if x.evidence_type == "EXPLICIT_EXTERNAL"),
        },
        "policy": {
            "tables_always_have_source_bronze_silver_lineage": True,
            "gold_requires_approved_business_semantics": True,
            "inferred_semantics_auto_generate_gold": False,
            "routine_logic_is_planned_separately_from_data_nodes": True,
            "triggers_require_architecture_review": True,
        },
    }


def _node_lookup(db: Session, project_id: str, environment: str) -> tuple[dict[str, MigrationMedallionNode], dict[tuple[str, str], MigrationMedallionNode]]:
    nodes = list(db.scalars(select(MigrationMedallionNode).where(
        MigrationMedallionNode.project_id == project_id,
        MigrationMedallionNode.environment == environment.upper(),
    )).all())
    return {n.id: n for n in nodes}, {(n.source_object_id or "", n.layer): n for n in nodes if n.source_object_id and n.layer in {"BRONZE", "SILVER"}}


def _replace_source_references(db: Session, project_id: str, environment: str, sql: str, *, for_gold: bool = False) -> str:
    objects = list(db.scalars(select(MigrationObject).where(MigrationObject.project_id == project_id)).all())
    _, by_obj_layer = _node_lookup(db, project_id, environment)
    out = sql
    for obj in sorted(objects, key=lambda x: len(x.object_name), reverse=True):
        # Silver transformations consume Bronze tables; Gold transformations consume Silver entities.
        desired = "SILVER" if for_gold else ("BRONZE" if obj.object_type == "TABLE" else "SILVER")
        node = by_obj_layer.get((obj.id, desired)) or by_obj_layer.get((obj.id, "SILVER")) or by_obj_layer.get((obj.id, "BRONZE"))
        if not node:
            continue
        patterns = [
            rf"(?<![\w`])\[{re.escape(obj.schema_name)}\]\.\[{re.escape(obj.object_name)}\](?![\w`])",
            rf"(?<![\w`]){re.escape(obj.schema_name)}\.{re.escape(obj.object_name)}(?![\w`])",
            rf"(?<![\w`])`{re.escape(obj.schema_name)}`\.`{re.escape(obj.object_name)}`(?![\w`])",
        ]
        for pat in patterns:
            out = re.sub(pat, node.target_fqn, out, flags=re.I)
    return out


def _gold_sql(db: Session, project_id: str, node: MigrationMedallionNode, sem: MigrationSemanticDefinition,
              silver: MigrationMedallionNode) -> tuple[str, list[str]]:
    errors = []
    cols = _columns(db, project_id, sem.object_id)
    names = {c.column_name.lower(): c.column_name for c in cols}
    grain = _loads(sem.grain_json, []); bkeys = _loads(sem.business_keys_json, [])
    dkeys = _loads(sem.dimension_keys_json, []); attrs = _loads(sem.attributes_json, []); measures = _loads(sem.measures_json, [])
    role = sem.semantic_role

    def qcols(items: list[str]) -> list[str]:
        result = []
        for c in items:
            actual = names.get(str(c).lower())
            if not actual: errors.append(f"Unknown semantic column {c}")
            else: result.append(qident(actual))
        return result

    if role == "DIMENSION":
        selected = []
        seen = set()
        for c in qcols(bkeys + attrs):
            if c.lower() not in seen: selected.append(c); seen.add(c.lower())
        if not bkeys: errors.append("DIMENSION requires business_keys")
        if not selected: errors.append("DIMENSION has no selected columns")
        content = f"CREATE OR REPLACE VIEW {node.target_fqn} AS\nSELECT\n  " + ",\n  ".join(selected) + f"\nFROM {silver.target_fqn};"
        if str(sem.scd_type or "1") == "2":
            # SCD2 cannot be invented from source metadata. Explicit lifecycle columns are required.
            lifecycle = _loads(sem.evidence_json, {}).get("scd2_columns") or {}
            required = {"effective_from", "effective_to", "is_current"}
            if not required.issubset(set(lifecycle)):
                errors.append("SCD2 requires explicit scd2_columns: effective_from, effective_to and is_current")
        return content, errors

    if role in {"FACT", "AGGREGATE", "KPI", "REPORTING"}:
        keys = []
        seen = set()
        for c in qcols(grain + dkeys):
            if c.lower() not in seen: keys.append(c); seen.add(c.lower())
        measure_sql = []
        aggregated = False
        for m in measures:
            if not isinstance(m, dict):
                errors.append(f"Invalid measure definition {m}"); continue
            name = _clean_name(str(m.get("name") or m.get("source_column") or "measure"))
            source_col = m.get("source_column")
            aggregation = str(m.get("aggregation") or "NONE").upper()
            expression = str(m.get("expression") or "").strip()
            if source_col:
                actual = names.get(str(source_col).lower())
                if not actual:
                    errors.append(f"Measure {name} references unknown column {source_col}"); continue
                base = qident(actual)
                if aggregation in {"SUM", "AVG", "MIN", "MAX", "COUNT", "COUNT_DISTINCT"}:
                    expr = f"COUNT(DISTINCT {base})" if aggregation == "COUNT_DISTINCT" else f"{aggregation}({base})"
                    aggregated = True
                elif aggregation == "NONE":
                    expr = base
                else:
                    errors.append(f"Unsupported deterministic aggregation {aggregation} for measure {name}"); continue
            elif expression:
                # Explicit custom expressions are allowed only after human semantic approval.
                # Still block statements/control tokens so an expression cannot become executable DDL/DML.
                if re.search(r"\b(drop|delete|insert|update|merge|alter|create|execute|exec|truncate)\b|;", expression, re.I):
                    errors.append(f"Unsafe custom expression for measure {name}"); continue
                expr = expression; aggregated = bool(re.search(r"\b(sum|avg|min|max|count)\s*\(", expression, re.I))
            else:
                errors.append(f"Measure {name} requires source_column or explicit expression"); continue
            measure_sql.append(f"{expr} AS {qident(name)}")
        if role == "FACT" and not grain: errors.append("FACT requires explicit grain")
        if not measure_sql: errors.append(f"{role} requires explicit measures")
        select_parts = keys + measure_sql
        content = f"CREATE OR REPLACE VIEW {node.target_fqn} AS\nSELECT\n  " + ",\n  ".join(select_parts) + f"\nFROM {silver.target_fqn}"
        if aggregated and keys:
            content += "\nGROUP BY " + ", ".join(keys)
        content += ";"
        return content, errors

    return f"-- NON_EXECUTABLE: Unsupported Gold semantic role {role}", [f"Unsupported Gold semantic role {role}"]


def _stage_content(db: Session, project_id: str, node: MigrationMedallionNode, environment: str) -> tuple[str, bool, list[str]]:
    obj = db.get(MigrationObject, node.source_object_id) if node.source_object_id else None
    if node.layer == "BRONZE" and obj and obj.object_type == "TABLE":
        cols = _columns(db, project_id, obj.id)
        defs = [f"  {qident(c.column_name)} {map_sqlserver_type(c.data_type,c.precision,c.scale)}" + (" NOT NULL" if not c.nullable else "") for c in cols]
        content = f"CREATE TABLE {node.target_fqn} (\n" + ",\n".join(defs + ["  `_migration_ingested_at` TIMESTAMP", "  `_migration_source_system` STRING"]) + "\n) USING DELTA;"
        return content, True, []
    if node.layer == "SILVER" and obj and obj.object_type == "TABLE":
        bronze = db.scalar(select(MigrationMedallionNode).where(
            MigrationMedallionNode.project_id == project_id,
            MigrationMedallionNode.environment == environment.upper(),
            MigrationMedallionNode.source_object_id == obj.id,
            MigrationMedallionNode.layer == "BRONZE",
        ))
        if not bronze: return "-- NON_EXECUTABLE: Bronze parent missing", False, ["Bronze parent node missing"]
        cols = _columns(db, project_id, obj.id)
        selected = ",\n  ".join(qident(c.column_name) for c in cols)
        return f"CREATE OR REPLACE VIEW {node.target_fqn} AS\nSELECT\n  {selected}\nFROM {bronze.target_fqn};", True, []
    if node.layer == "SILVER" and obj and obj.object_type == "VIEW":
        repaired = _approved_repaired_artifact(db, project_id, obj.id, environment)
        if repaired:
            content = _retarget_view_header(repaired.content, node.target_fqn)
            return content, bool(content.strip()), [] if content.strip() else ["View definition empty"]
        content = rewrite_common_tsql(obj.definition or "")
        content = _replace_source_references(db, project_id, environment, content, for_gold=False)
        content = _retarget_view_header(content, node.target_fqn)
        return content, bool(content.strip()), [] if content.strip() else ["View definition empty"]
    if node.layer == "SILVER" and obj and obj.object_type in {"PROCEDURE", "FUNCTION"}:
        repaired = _approved_repaired_artifact(db, project_id, obj.id, environment)
        if repaired:
            content = _retarget_repaired_routine(repaired.content, obj.object_type, node.target_fqn)
            return content, True, []
        # Use the deterministic routine converters but target the Medallion node rather than
        # the legacy one-object/one-layer mapping.
        transient = MigrationMapping(project_id=project_id, object_id=obj.id, source_fqn="", target_fqn=node.target_fqn,
                                     target_layer="SILVER", environment=environment.upper())
        if obj.object_type == "PROCEDURE":
            content, executable, reason = _convert_procedure(db, project_id, obj, transient, environment)
        else:
            content, executable, reason = _convert_function(db, project_id, obj, transient, environment)
        return content, executable, [] if executable else [reason]
    if node.layer == "SILVER" and obj and obj.object_type == "TRIGGER":
        intent, target = classify_trigger(obj.definition or "")
        return f"-- ARCHITECT_REVIEW_REQUIRED\n-- TRIGGER_INTENT: {intent}\n-- RECOMMENDED_TARGET: {target}\n{obj.definition or ''}", False, ["SQL Server trigger requires architecture review"]
    if node.layer == "GOLD" and node.semantic_definition_id:
        sem = db.get(MigrationSemanticDefinition, node.semantic_definition_id)
        if not sem or sem.project_id != project_id or sem.status != "APPROVED":
            return "-- NON_EXECUTABLE: Gold semantics are not approved", False, ["Gold semantic definition is not APPROVED"]
        silver = db.scalar(select(MigrationMedallionNode).where(
            MigrationMedallionNode.project_id == project_id,
            MigrationMedallionNode.environment == environment.upper(),
            MigrationMedallionNode.source_object_id == sem.object_id,
            MigrationMedallionNode.layer == "SILVER",
        ))
        if not silver: return "-- NON_EXECUTABLE: Silver source missing", False, ["Silver source node missing"]
        content, errors = _gold_sql(db, project_id, node, sem, silver)
        return content, not errors, errors
    return "-- NON_EXECUTABLE: Unsupported Medallion node", False, ["Unsupported Medallion node"]


def _approved_repaired_artifact(
    db: Session, project_id: str, object_id: str, environment: str
) -> MigrationArtifactVersion | None:
    """Return the effective current routine version only when it passed validation and approval."""
    artifacts = list(db.scalars(select(MigrationArtifact).where(
        MigrationArtifact.project_id == project_id,
        MigrationArtifact.object_id == object_id,
    )).all())
    versions: list[MigrationArtifactVersion] = []
    for artifact in artifacts:
        version = db.scalar(select(MigrationArtifactVersion).where(
            MigrationArtifactVersion.project_id == project_id,
            MigrationArtifactVersion.artifact_id == artifact.id,
            MigrationArtifactVersion.version == artifact.current_version,
        ))
        if version:
            versions.append(version)
    current = max(versions, key=lambda row: (row.created_at, row.version, row.id), default=None)
    if not current or "-- NON_EXECUTABLE:" in current.content.upper() or "ARCHITECT_REVIEW_REQUIRED" in current.content.upper():
        return None

    validations = list(db.scalars(select(MigrationValidation).where(
        MigrationValidation.project_id == project_id,
        MigrationValidation.object_id == object_id,
        MigrationValidation.environment == environment.upper(),
    ).order_by(MigrationValidation.created_at.desc())).all())
    validated = False
    for row in validations:
        payload = _loads(row.payload_json, {})
        if payload.get("artifact_version_id") == current.id:
            validated = row.status == "PASSED"
            break
    if not validated:
        return None

    review = db.scalars(select(MigrationReview).where(
        MigrationReview.project_id == project_id,
        MigrationReview.artifact_version_id == current.id,
        MigrationReview.review_type == "ARCHITECT_REVIEW",
    ).order_by(MigrationReview.reviewed_at.desc())).first()
    return current if review and review.status == "APPROVED" else None


def _retarget_repaired_routine(content: str, object_type: str, target_fqn: str) -> str:
    kind = "FUNCTION" if object_type == "FUNCTION" else "PROCEDURE"
    pattern = rf"(?is)^\s*CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?{kind}\s+[^\s(]+"
    replacement = f"CREATE OR REPLACE {kind} {target_fqn}"
    retargeted = re.sub(pattern, lambda _: replacement, content, count=1)
    return normalize_databricks_routine_contract(retargeted, object_type)


def generate_medallion_artifacts(db: Session, project_id: str, *, environment: str = "DEV") -> dict[str, Any]:
    env = environment.upper()
    nodes = list(db.scalars(select(MigrationMedallionNode).where(
        MigrationMedallionNode.project_id == project_id,
        MigrationMedallionNode.environment == env,
        MigrationMedallionNode.layer.in_(["BRONZE", "SILVER", "GOLD"]),
    ).order_by(MigrationMedallionNode.layer, MigrationMedallionNode.target_name)).all())
    if not nodes:
        raise ValueError("Medallion plan is empty. Build the plan first.")
    generated = []
    for node in nodes:
        content, executable, errors = _stage_content(db, project_id, node, env)
        source_version = None
        source_obj = db.get(MigrationObject, node.source_object_id) if node.source_object_id else None
        if source_obj and source_obj.object_type in {"PROCEDURE", "FUNCTION"}:
            content = normalize_databricks_routine_contract(content, source_obj.object_type)
            contract_errors = databricks_routine_contract_issues(content, source_obj.object_type)
            if contract_errors:
                executable = False
                errors = list(dict.fromkeys([*errors, *contract_errors]))
        if node.layer == "SILVER" and source_obj and source_obj.object_type in {"PROCEDURE", "FUNCTION"}:
            source_version = _approved_repaired_artifact(db, project_id, source_obj.id, env)
        validation = "PASSED" if executable and not errors else "FAILED"
        art = db.scalar(select(MigrationStageArtifact).where(
            MigrationStageArtifact.project_id == project_id,
            MigrationStageArtifact.node_id == node.id,
        ))
        if not art:
            art = MigrationStageArtifact(id=uid("MSA"), project_id=project_id, node_id=node.id,
                                         artifact_type=node.node_type, current_version=0)
            db.add(art); db.flush()
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        current = db.scalar(select(MigrationStageArtifactVersion).where(
            MigrationStageArtifactVersion.project_id == project_id,
            MigrationStageArtifactVersion.artifact_id == art.id,
            MigrationStageArtifactVersion.version == art.current_version,
        )) if art.current_version else None
        if current and current.content_hash == content_hash:
            version = current
        else:
            version = MigrationStageArtifactVersion(
                id=uid("MSV"), project_id=project_id, artifact_id=art.id, node_id=node.id,
                version=art.current_version + 1, content=content, content_hash=content_hash,
                executable=executable, validation_status=validation,
                validation_json=_json({
                    "errors": errors, "node_id": node.id, "target_fqn": node.target_fqn,
                    "source_artifact_version_id": source_version.id if source_version else None,
                    "source_artifact_version": source_version.version if source_version else None,
                    "source_artifact_hash": source_version.target_hash if source_version else None,
                }),
                review_status="PENDING_REVIEW",
            )
            db.add(version); art.current_version = version.version
        node.status = "ARTIFACT_READY" if validation == "PASSED" else "REVIEW_REQUIRED"
        generated.append({"node_id": node.id, "target_fqn": node.target_fqn, "layer": node.layer,
                          "artifact_version_id": version.id, "version": version.version,
                          "executable": version.executable, "validation_status": version.validation_status,
                          "review_status": version.review_status, "errors": errors})
    db.commit()
    return {"project_id": project_id, "environment": env, "generated": len(generated), "artifacts": generated}


def list_medallion_artifacts(db: Session, project_id: str, *, environment: str = "DEV") -> list[dict[str, Any]]:
    env = environment.upper()
    nodes = {n.id: n for n in db.scalars(select(MigrationMedallionNode).where(
        MigrationMedallionNode.project_id == project_id,
        MigrationMedallionNode.environment == env,
    )).all()}
    arts = list(db.scalars(select(MigrationStageArtifact).where(MigrationStageArtifact.project_id == project_id)).all())
    result = []
    for art in arts:
        node = nodes.get(art.node_id)
        if not node: continue
        source_obj = db.get(MigrationObject, node.source_object_id) if node.source_object_id else None
        version = db.scalar(select(MigrationStageArtifactVersion).where(
            MigrationStageArtifactVersion.project_id == project_id,
            MigrationStageArtifactVersion.artifact_id == art.id,
            MigrationStageArtifactVersion.version == art.current_version,
        ))
        if not version: continue
        result.append({
            "artifact_id": art.id, "artifact_version_id": version.id, "node_id": node.id,
            "layer": node.layer, "node_type": node.node_type, "model_role": node.model_role,
            "source_object_id": node.source_object_id,
            "source_object_type": source_obj.object_type if source_obj else None,
            "target_fqn": node.target_fqn, "version": version.version, "content": version.content,
            "executable": version.executable, "validation_status": version.validation_status,
            "validation": _loads(version.validation_json, {}), "review_status": version.review_status,
            "reviewer": version.reviewer, "reviewed_at": version.reviewed_at,
        })
    return sorted(result, key=lambda x:({"BRONZE":1,"SILVER":2,"GOLD":3}.get(x["layer"],9), x["target_fqn"].lower()))


def review_medallion_artifact(db: Session, project_id: str, version_id: str, *, status: str, reviewer: str) -> MigrationStageArtifactVersion:
    version = db.get(MigrationStageArtifactVersion, version_id)
    if not version or version.project_id != project_id:
        raise ValueError("Medallion artifact version not found in project")
    artifact = db.get(MigrationStageArtifact, version.artifact_id)
    if not artifact or artifact.project_id != project_id or artifact.current_version != version.version:
        raise ValueError("Only the current Medallion artifact version can receive a review decision")
    state = status.upper().strip()
    if state not in {"APPROVED", "REJECTED", "CHANGES_REQUIRED"}:
        raise ValueError("status must be APPROVED, REJECTED or CHANGES_REQUIRED")
    if state == "APPROVED" and (not version.executable or version.validation_status != "PASSED"):
        node = db.get(MigrationMedallionNode, version.node_id)
        if not node or node.node_type != "ARCHITECTURE_REVIEW":
            raise ValueError("Approval blocked: artifact must be executable and validation must PASSED")
    version.review_status = state; version.reviewer = reviewer; version.reviewed_at = datetime.utcnow()

    # A repaired Medallion routine is derived from a governed source-object
    # candidate. Mirror the human approval to that exact source version so a
    # later idempotent regeneration continues to use the approved repair.
    if state == "APPROVED":
        source_version_id = _loads(version.validation_json, {}).get("source_artifact_version_id")
        source_version = db.get(MigrationArtifactVersion, source_version_id) if source_version_id else None
        if source_version and source_version.project_id == project_id:
            latest = db.scalars(select(MigrationReview).where(
                MigrationReview.project_id == project_id,
                MigrationReview.artifact_version_id == source_version.id,
                MigrationReview.review_type == "ARCHITECT_REVIEW",
            ).order_by(MigrationReview.reviewed_at.desc())).first()
            if not latest or latest.status != "APPROVED":
                db.add(MigrationReview(
                    id=uid("REV"), project_id=project_id,
                    artifact_version_id=source_version.id,
                    review_type="ARCHITECT_REVIEW", status="APPROVED",
                    reviewer=reviewer,
                    comments=f"Approved through Medallion artifact {version.id}",
                ))
    db.commit()
    return version


def remediate_medallion_artifact(
    db: Session,
    project_id: str,
    version_id: str,
    *,
    environment: str = "DEV",
    use_ai: bool = True,
    reviewer: str = "system",
) -> dict[str, Any]:
    """Repair one failed routine and publish a new Medallion version for review.

    The existing remediation engine operates on source-object artifacts. This bridge
    deliberately reuses that governed engine, then copies only a successfully
    statically-validated candidate into a new Medallion stage version. It never
    approves or deploys the candidate.
    """
    from app.services.ai_remediation import remediate_one_artifact
    from app.services.engine import generate_artifact, static_validate

    env = environment.upper()
    if env != "DEV":
        raise ValueError("Medallion artifact remediation is currently restricted to DEV")
    version = db.get(MigrationStageArtifactVersion, version_id)
    if not version or version.project_id != project_id:
        raise ValueError("Medallion artifact version not found in project")
    artifact = db.get(MigrationStageArtifact, version.artifact_id)
    if not artifact or artifact.project_id != project_id or artifact.current_version != version.version:
        raise ValueError("Only the current Medallion artifact version can be remediated")
    if version.executable and version.validation_status == "PASSED":
        raise ValueError("Artifact already passed validation and is ready for human review")

    node = db.get(MigrationMedallionNode, version.node_id)
    obj = db.get(MigrationObject, node.source_object_id) if node and node.source_object_id else None
    if not node or node.project_id != project_id or not obj or obj.project_id != project_id:
        raise ValueError("Failed Medallion artifact has no source object for remediation")
    if obj.object_type not in {"PROCEDURE", "FUNCTION"}:
        raise ValueError(f"{obj.object_type} artifact requires manual architecture review")

    mapping = db.scalar(select(MigrationMapping).where(
        MigrationMapping.project_id == project_id,
        MigrationMapping.object_id == obj.id,
        MigrationMapping.environment == env,
    ))
    if not mapping:
        mapping = MigrationMapping(
            id=uid("MAP"), project_id=project_id, object_id=obj.id,
            source_fqn=f"{obj.database_name}.{obj.schema_name}.{obj.object_name}",
            target_fqn=node.target_fqn, target_layer=node.layer, environment=env,
        )
        db.add(mapping)
        db.commit()

    # Seed the source-object repair loop with the same deterministic conversion
    # that failed Medallion generation, including version-specific validation.
    generate_artifact(db, project_id, obj.id, env)
    static_validate(db, project_id, obj.id, env)
    repaired = remediate_one_artifact(
        db, project_id, obj.id, environment=env, use_ai=use_ai, reviewer=reviewer,
        confirmed_blocker=f"MEDALLION_STAGE_VALIDATION:{version.id}",
    )
    if repaired.get("status") != "READY_FOR_REVIEW":
        errors = repaired.get("errors") or repaired.get("static_validation", {}).get("issues") or []
        raise ValueError("AI remediation did not produce a valid candidate: " + "; ".join(errors))

    source_version = db.get(MigrationArtifactVersion, repaired["artifact_version_id"])
    if not source_version or source_version.project_id != project_id:
        raise ValueError("Validated remediation candidate was not found")
    content = _retarget_repaired_routine(source_version.content, obj.object_type, node.target_fqn)
    contract_errors = databricks_routine_contract_issues(content, obj.object_type)
    if contract_errors:
        raise ValueError("Remediation candidate failed Databricks routine validation: " + "; ".join(contract_errors))
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    new_version = MigrationStageArtifactVersion(
        id=uid("MSV"), project_id=project_id, artifact_id=artifact.id, node_id=node.id,
        version=artifact.current_version + 1, content=content, content_hash=content_hash,
        executable=True, validation_status="PASSED",
        validation_json=_json({
            "errors": [], "node_id": node.id, "target_fqn": node.target_fqn,
            "source_artifact_version_id": source_version.id,
            "source_artifact_version": source_version.version,
            "source_artifact_hash": source_version.target_hash,
            "ai_run_id": repaired.get("ai_run_id"),
            "provider": repaired.get("provider"),
            "validation_type": "GOVERNED_AI_REMEDIATION",
        }),
        review_status="PENDING_REVIEW",
    )
    db.add(new_version)
    artifact.current_version = new_version.version
    node.status = "ARTIFACT_READY"
    db.commit()
    return {
        "artifact_version_id": new_version.id,
        "version": new_version.version,
        "status": "READY_FOR_REVIEW",
        "validation_status": new_version.validation_status,
        "review_status": new_version.review_status,
        "provider": repaired.get("provider"),
        "auto_approved": False,
        "auto_deployed": False,
    }


def _layer_order(layer: str) -> int:
    return {"BRONZE": 1, "SILVER": 2, "GOLD": 3}.get(layer, 9)


def deploy_medallion_dev(db: Session, project_id: str, *, allow_destructive: bool = False,
                         batch_size: int = 10000, max_rows: int | None = None) -> dict[str, Any]:
    """Deploy reviewed Medallion artifacts in Bronze -> Silver -> Gold order.

    Bronze data loading reuses the existing metadata-driven loader. Schema drift remains
    governed by the existing deployment policy; destructive replacement requires an explicit
    allow_destructive flag and is never performed silently.
    """
    from app.models.canonical import MigrationDeployment
    from app.services.databricks_client import execute_sql
    from app.services.deployment import (
        _apply_table_schema_policy,
        databricks_workspace_identity,
        load_bronze_table,
    )

    env = "DEV"
    artifacts = list_medallion_artifacts(db, project_id, environment=env)
    if not artifacts:
        raise ValueError("No Medallion artifacts generated")
    blockers = [
        x for x in artifacts
        if x["review_status"] != "APPROVED"
        or (x.get("node_type") != "ARCHITECTURE_REVIEW" and (x["validation_status"] != "PASSED" or not x["executable"]))
    ]
    if blockers:
        raise ValueError(f"Medallion deployment blocked: {len(blockers)} artifact(s) are not approved/executable/validated")

    runtime_contract_blockers = []
    for item in artifacts:
        if item.get("node_type") == "ARCHITECTURE_REVIEW":
            continue
        issues = databricks_routine_contract_issues(
            item["content"], item.get("source_object_type") or item.get("node_type") or ""
        )
        if issues:
            runtime_contract_blockers.append(f"{item['target_fqn']}: {'; '.join(issues)}")
    if runtime_contract_blockers:
        raise ValueError(
            "Medallion deployment blocked by Databricks routine preflight. Regenerate and review the corrected "
            "artifact version: " + " | ".join(runtime_contract_blockers)
        )

    node_by_id = {n.id: n for n in db.scalars(select(MigrationMedallionNode).where(
        MigrationMedallionNode.project_id == project_id,
        MigrationMedallionNode.environment == env,
    )).all()}
    object_by_id = {o.id: o for o in db.scalars(select(MigrationObject).where(MigrationObject.project_id == project_id)).all()}
    run_id = uid("MDR")
    deployed = []
    for item in sorted(artifacts, key=lambda x:(_layer_order(x["layer"]), x["target_fqn"].lower())):
        node = node_by_id[item["node_id"]]
        obj = object_by_id.get(node.source_object_id)
        try:
            if node.node_type == "ARCHITECTURE_REVIEW":
                detail = {"action": "ARCHITECTURE_REVIEW_ACKNOWLEDGED"}
            elif node.layer == "BRONZE" and obj and obj.object_type == "TABLE":
                transient = MigrationMapping(project_id=project_id, object_id=obj.id,
                                             source_fqn=f"{obj.database_name}.{obj.schema_name}.{obj.object_name}",
                                             target_fqn=node.target_fqn, target_layer="BRONZE", environment="DEV")
                policy = _apply_table_schema_policy(db, project_id, obj, transient, allow_destructive)
                if policy["action"] == "CREATE":
                    execute_sql(item["content"], safe_retry=False)
                elif policy["action"] == "REPLACE":
                    if not allow_destructive:
                        raise RuntimeError("DEV replacement requires explicit destructive approval")
                    execute_sql(f"DROP TABLE {node.target_fqn}", safe_retry=False)
                    execute_sql(item["content"], safe_retry=False)
                load = load_bronze_table(db, project_id, obj, transient, run_id, batch_size, max_rows,
                                         "FULL_LOAD", replace_existing_data=allow_destructive)
                detail = {"schema_policy": policy, "load": load}
            else:
                execute_sql(item["content"], safe_retry=False)
                detail = {"action": "EXECUTE_ARTIFACT"}
            db.add(MigrationDeployment(id=uid("DPL"), project_id=project_id, object_id=node.source_object_id,
                                       environment="DEV", status="PASSED",
                                       payload_json=_json({"run_id": run_id,
                                                           "databricks_workspace": databricks_workspace_identity(),
                                                           "medallion_node_id": node.id,
                                                           "layer": node.layer, "target_fqn": node.target_fqn,
                                                           "artifact_version_id": item["artifact_version_id"], **detail})))
            node.status = "DEPLOYED"; deployed.append({"target_fqn": node.target_fqn, "layer": node.layer, "status": "PASSED"})
            db.commit()
        except Exception as exc:
            db.add(MigrationDeployment(id=uid("DPL"), project_id=project_id, object_id=node.source_object_id,
                                       environment="DEV", status="FAILED",
                                       payload_json=_json({"run_id": run_id,
                                                           "databricks_workspace": databricks_workspace_identity(),
                                                           "medallion_node_id": node.id,
                                                           "layer": node.layer, "target_fqn": node.target_fqn,
                                                           "artifact_version_id": item["artifact_version_id"], "error": str(exc)})))
            node.status = "FAILED"; db.commit()
            return {"run_id": run_id, "status": "FAILED", "failed_target": node.target_fqn, "error": str(exc), "deployed": deployed}
    db.add(MigrationDeployment(
        id=uid("DPL"), project_id=project_id, object_id=None, environment="DEV", status="PASSED",
        payload_json=_json({"run_id": run_id,
                            "databricks_workspace": databricks_workspace_identity(),
                            "medallion_run_complete": True,
                            "deployed": len(deployed), "expected": len(artifacts)}),
    ))
    db.commit()
    return {"run_id": run_id, "status": "PASSED", "deployed": deployed, "count": len(deployed)}
