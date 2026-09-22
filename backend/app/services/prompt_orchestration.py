from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    CanonicalRecord,
    MigrationColumn,
    MigrationEnvironmentPlan,
    MigrationObject,
    MigrationProject,
    MigrationRun,
    MigrationSource,
)
from app.services import environment_provisioning
from app.services import bronze_ingestion
from app.services import medallion
from app.services import ai_remediation
from app.services import deployment
from app.services import discovery
from app.services import source_connector
from app.services.engine import ingest_snapshot, uid


def _payload(value: str | None) -> dict[str, Any]:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _record(
    db: Session,
    project_id: str,
    *,
    record_type: str,
    status: str,
    run_id: str | None = None,
    object_id: str | None = None,
    **details: Any,
) -> CanonicalRecord:
    rec = CanonicalRecord(
        id=uid("REC"),
        project_id=project_id,
        object_id=object_id,
        environment="DEV",
        record_type=record_type,
        payload_json=json.dumps(
            {"status": status, "run_id": run_id, **details},
            default=str,
            sort_keys=True,
        ),
    )
    db.add(rec)
    db.commit()
    return rec


def _reusable_bronze_checkpoint(
    db: Session, project_id: str, tables: list[MigrationObject]
) -> dict[str, Any] | None:
    """Return the latest complete Bronze run only when it matches this plan's tables."""
    latest = bronze_ingestion.latest(db, project_id)
    if latest.get("status") != "PASSED" or not latest.get("run_id"):
        return None
    expected_sources = {f"{table.schema_name}.{table.object_name}" for table in tables}
    passed_results = [
        item for item in latest.get("results", []) if item.get("status") == "PASSED"
    ]
    actual_sources = {str(item.get("source")) for item in passed_results}
    if expected_sources != actual_sources:
        return None
    return {
        "reusable": True,
        "run_id": latest["run_id"],
        "table_count": len(passed_results),
        "rows_transferred": sum(int(item.get("rows_loaded") or 0) for item in passed_results),
        "completed_at": latest.get("ended_at"),
    }


def parse_and_validate_prompt(
    db: Session,
    project_id: str,
    prompt: str,
    actor: str = "admin",
) -> dict[str, Any]:
    """Parse user prompt, validate prerequisites, and return intent or NEEDS_USER_INPUT."""
    if not prompt or not prompt.strip():
        raise ValueError("A prompt is required")

    project = db.get(MigrationProject, project_id)
    if not project:
        raise LookupError("Project not found")

    cleaned_prompt = prompt.strip()
    lower = cleaned_prompt.lower()

    # 1. Identify source database/profile
    sources = list(db.scalars(select(MigrationSource).where(MigrationSource.project_id == project_id)).all())
    matched_source: MigrationSource | None = None

    for s in sources:
        if s.database_name and s.database_name.lower() in lower:
            matched_source = s
            break
        if s.profile_name and s.profile_name.lower() in lower:
            matched_source = s
            break

    # If no exact match found, try regex extraction
    extracted_db = None
    if not matched_source:
        m = re.search(r"(?:migrate|load|ingest|source|database|db)\s+([a-zA-Z0-9_\-]+)", cleaned_prompt, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in {"from", "to", "all", "tables", "sql", "databricks", "dev", "bronze"}:
                extracted_db = candidate

        # If only 1 source exists in the project and user didn't specify a different one
        if len(sources) == 1:
            matched_source = sources[0]

    # 2. Identify target environment
    env = "DEV"
    if "dev" in lower or "development" in lower:
        env = "DEV"
    elif "prod" in lower or "production" in lower:
        env = "PROD"
    elif "uat" in lower:
        env = "UAT"
    elif "test" in lower:
        env = "TEST"

    # 3. Check prerequisites & handle blockers
    blockers: list[str] = []
    actionable_steps: list[str] = []

    if env != "DEV":
        blockers.append(f"Prompt requested {env}, but Release 3 initiates migration into DEV first.")
        actionable_steps.append("Controlled promotion to TEST, UAT, and PROD is governed through Release 5.")

    if not matched_source:
        if sources:
            available = ", ".join(s.database_name or s.profile_name for s in sources)
            blockers.append(f"Could not identify source database from prompt. Available sources: {available}")
            actionable_steps.append("Specify a registered source name in your prompt (e.g. 'Migrate " + (sources[0].database_name or "MigrationDemo") + "...').")
        else:
            blockers.append("No SQL Server source database is registered for this project.")
            actionable_steps.append("Add and test a SQL Server source in the Sources tab first.")

    config = environment_provisioning.get_configuration(db, project_id)
    if not config or config.status != "READY":
        blockers.append("Databricks connection is not configured or tested.")
        actionable_steps.append("Configure workspace host, SQL warehouse path, and test connection in Environment Setup.")

    plan = environment_provisioning.get_dev_plan(db, project_id)
    if not plan or plan.status != "PROVISIONED":
        blockers.append("Databricks DEV environment (catalog and schemas) is not provisioned.")
        actionable_steps.append("Approve and provision DEV catalog in Environment Setup.")

    if blockers:
        return {
            "status": "NEEDS_USER_INPUT",
            "prompt": cleaned_prompt,
            "blockers": blockers,
            "actionable_steps": actionable_steps,
            "intent": {
                "source_database": matched_source.database_name if matched_source else extracted_db,
                "target_environment": env,
                "target_platform": "Databricks",
            },
        }

    return {
        "status": "VALIDATED",
        "prompt": cleaned_prompt,
        "source": {
            "id": matched_source.id,
            "server_name": matched_source.server_name,
            "database_name": matched_source.database_name,
            "profile_name": matched_source.profile_name,
        },
        "intent": {
            "source_id": matched_source.id,
            "source_database": matched_source.database_name,
            "target_environment": "DEV",
            "target_catalog": plan.catalog_name,
            "target_schemas": ["bronze", "silver", "gold"],
            "load_mode": "FULL_LOAD",
            "target_platform": "Databricks",
        },
    }


def generate_prompt_plan(
    db: Session,
    project_id: str,
    prompt: str,
    actor: str = "admin",
) -> dict[str, Any]:
    """Validate prompt and generate a structured migration plan with impact assessment."""
    validation = parse_and_validate_prompt(db, project_id, prompt, actor)
    if validation["status"] == "NEEDS_USER_INPUT":
        return validation

    source_info = validation["source"]
    intent = validation["intent"]
    catalog_name = intent["target_catalog"]

    source_id = source_info["id"]
    tables = list(
        db.scalars(
            select(MigrationObject)
            .where(
                MigrationObject.project_id == project_id,
                MigrationObject.source_id == source_id,
                MigrationObject.object_type == "TABLE",
            )
            .order_by(MigrationObject.schema_name, MigrationObject.object_name)
        ).all()
    )

    views = list(
        db.scalars(
            select(MigrationObject)
            .where(
                MigrationObject.project_id == project_id,
                MigrationObject.source_id == source_id,
                MigrationObject.object_type == "VIEW",
            )
        ).all()
    )

    routines = list(
        db.scalars(
            select(MigrationObject)
            .where(
                MigrationObject.project_id == project_id,
                MigrationObject.source_id == source_id,
                MigrationObject.object_type.in_(["PROCEDURE", "FUNCTION"]),
            )
        ).all()
    )

    if not tables:
        return {
            "status": "NEEDS_USER_INPUT",
            "prompt": prompt.strip(),
            "blockers": [
                f"No discovered SQL Server tables are available for {source_info['database_name']}."
            ],
            "actionable_steps": [
                "Run source discovery and confirm that table metadata is visible before generating the migration plan."
            ],
            "intent": intent,
            "source": source_info,
        }

    bronze_checkpoint = _reusable_bronze_checkpoint(db, project_id, tables)
    estimated_rows = bronze_checkpoint["rows_transferred"] if bronze_checkpoint else 0
    destinations: list[dict[str, Any]] = []
    for t in tables:
        columns = list(
            db.scalars(
                select(MigrationColumn).where(
                    MigrationColumn.project_id == project_id,
                    MigrationColumn.object_id == t.id,
                )
            ).all()
        )
        destinations.append({
            "object_id": t.id,
            "source_fqn": f"{t.schema_name}.{t.object_name}",
            "object_type": t.object_type,
            "bronze": f"{catalog_name}.bronze.{t.object_name.lower()}",
            "silver": f"{catalog_name}.silver.{t.object_name.lower()}",
            "gold": f"{catalog_name}.gold.dim_{t.object_name.lower()}",
            "column_count": len(columns),
        })

    existing_bronze_records = list(
        db.scalars(
            select(CanonicalRecord)
            .where(
                CanonicalRecord.project_id == project_id,
                CanonicalRecord.record_type == "BRONZE_INGESTION",
            )
            .order_by(CanonicalRecord.created_at.desc())
        ).all()
    )

    requires_overwrite = len(existing_bronze_records) > 0
    risk_level = "MEDIUM" if requires_overwrite else "LOW"

    plan_id = uid("PMP")
    stages = [
        {"stage": "DISCOVERY", "title": "SQL Server Discovery", "description": f"Verify schema discovery for {source_info['database_name']}"},
        {"stage": "BRONZE_INGESTION", "title": "DEV Bronze Ingestion", "description": f"Stream {len(tables)} tables into {catalog_name}.bronze"},
        {"stage": "MEDALLION_GENERATION", "title": "Medallion Modeling", "description": "Generate Silver & Gold semantic models and artifacts"},
        {"stage": "VALIDATION_AND_REMEDIATION", "title": "Validation & AI Remediation", "description": "Deterministic validation and bounded AI remediation for SQL syntax"},
        {"stage": "DEV_DEPLOYMENT", "title": "DEV Medallion Deployment", "description": f"Deploy approved artifacts to {catalog_name}"},
        {"stage": "RECONCILIATION", "title": "Reconciliation & Quality Gate", "description": "Verify source vs target row counts and evaluate DEV gate"},
    ]

    plan_payload = {
        "plan_id": plan_id,
        "status": "PENDING_APPROVAL",
        "prompt": prompt,
        "actor": actor,
        "intent": intent,
        "source": source_info,
        "impact": {
            "table_count": len(tables),
            "view_count": len(views),
            "routine_count": len(routines),
            "estimated_rows": estimated_rows,
            "risk_level": risk_level,
            "requires_overwrite": requires_overwrite,
            "bronze_checkpoint": bronze_checkpoint,
        },
        "stages": stages,
        "destinations": destinations,
        "created_at": datetime.utcnow().isoformat(),
    }

    _record(
        db,
        project_id,
        record_type="PROMPT_MIGRATION_PLAN",
        status="PENDING_APPROVAL",
        run_id=plan_id,
        plan=plan_payload,
    )

    return plan_payload


def get_prompt_plan(db: Session, project_id: str, plan_id: str | None = None) -> dict[str, Any] | None:
    """Retrieve an existing prompt plan by ID or latest."""
    query = (
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "PROMPT_MIGRATION_PLAN",
        )
        .order_by(CanonicalRecord.created_at.desc())
    )
    records = list(db.scalars(query).all())
    if not records:
        return None

    if plan_id:
        for r in records:
            p = _payload(r.payload_json)
            plan_data = p.get("plan") or {}
            if plan_data.get("plan_id") == plan_id or p.get("run_id") == plan_id:
                return plan_data
        return None

    latest_payload = _payload(records[0].payload_json)
    return latest_payload.get("plan") or latest_payload


def execute_prompt_plan(
    db: Session,
    project_id: str,
    plan_id: str,
    actor: str = "admin",
    overwrite_confirmed: bool = False,
) -> dict[str, Any]:
    """Approve and execute a governed prompt migration plan step-by-step."""
    plan_record = None
    query = (
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "PROMPT_MIGRATION_PLAN",
        )
        .order_by(CanonicalRecord.created_at.desc())
    )
    for r in db.scalars(query).all():
        p = _payload(r.payload_json)
        plan_data = p.get("plan") or {}
        if plan_data.get("plan_id") == plan_id or p.get("run_id") == plan_id:
            plan_record = r
            break

    if not plan_record:
        raise LookupError(f"Prompt plan {plan_id} not found")

    plan_payload = _payload(plan_record.payload_json).get("plan") or {}
    if plan_payload.get("status") not in {"PENDING_APPROVAL", "APPROVED"}:
        raise ValueError(f"Plan cannot be executed in status {plan_payload.get('status')}")

    source_info = plan_payload.get("source") or {}
    source_id = source_info.get("id")
    intent = plan_payload.get("intent") or {}
    catalog_name = intent.get("target_catalog", "migration_dev")

    run_id = uid("PMR")
    started_at = datetime.utcnow()

    plan_payload["status"] = "EXECUTING"
    plan_payload["approved_by"] = actor
    plan_payload["approved_at"] = started_at.isoformat()
    plan_payload["run_id"] = run_id
    plan_record.payload_json = json.dumps(
        {"status": "EXECUTING", "run_id": plan_id, "plan": plan_payload},
        default=str,
        sort_keys=True,
    )
    db.commit()

    _record(
        db,
        project_id,
        record_type="PROMPT_MIGRATION_RUN",
        status="RUNNING",
        run_id=run_id,
        plan_id=plan_id,
        step="STARTING",
        started_at=started_at.isoformat(),
    )

    execution_results: dict[str, Any] = {
        "run_id": run_id,
        "plan_id": plan_id,
        "status": "RUNNING",
        "actor": actor,
        "started_at": started_at.isoformat(),
        "stages": {},
        "errors": [],
    }
    current_stage = "STARTING"
    recommended_actions = {
        "DISCOVERY": "Open Discovery, rerun source discovery, and confirm that SQL Server objects are visible.",
        "BRONZE_INGESTION": "Open Environment Setup, review the latest Bronze ingestion details, then retry the prompt migration.",
        "MEDALLION_GENERATION": "Open Medallion Design and review semantic inference, keys, grain, and generated artifact evidence.",
        "VALIDATION_AND_REMEDIATION": "Open Medallion Design or AI Remediation and review the remaining failed artifacts before retrying.",
        "DEV_DEPLOYMENT": "Open DEV Deployment → Deployment attempts and logs. Review the failed target and Bronze reuse/replacement evidence before resuming.",
        "RECONCILIATION": "Open DEV Deployment and review source-to-target reconciliation and quality-gate evidence.",
    }

    try:
        # Step 1: Discovery Check
        current_stage = "DISCOVERY"
        existing_objects = list(
            db.scalars(
                select(MigrationObject).where(
                    MigrationObject.project_id == project_id,
                    MigrationObject.source_id == source_id,
                )
            ).all()
        )
        if not existing_objects and source_id:
            source = db.get(MigrationSource, source_id)
            if not source or source.project_id != project_id:
                raise LookupError("Source not found in project")
            if source_connector.connector_info(source_id)["mode"] == "CONNECTOR":
                snapshot = source_connector.request(source_id, "discover")
            else:
                snapshot = discovery.discover_sqlserver(
                    bronze_ingestion._source_connection_string(source)
                )
            disc_res = {
                "counts": ingest_snapshot(db, project_id, source_id, snapshot),
                "database": snapshot.get("database"),
                "objects": len(snapshot.get("objects", [])),
            }
            execution_results["stages"]["DISCOVERY"] = {"status": "PASSED", "details": disc_res}
        else:
            execution_results["stages"]["DISCOVERY"] = {"status": "PASSED", "details": {"objects": len(existing_objects)}}

        # Step 2: Bronze Ingestion
        current_stage = "BRONZE_INGESTION"
        tables = [obj for obj in existing_objects if obj.object_type == "TABLE"]
        if not tables:
            tables = list(db.scalars(select(MigrationObject).where(
                MigrationObject.project_id == project_id, MigrationObject.source_id == source_id,
                MigrationObject.object_type == "TABLE",
            )).all())
        bronze_checkpoint = bronze_ingestion.verified_checkpoint(db, project_id, tables)
        if bronze_checkpoint:
            bronze_res = bronze_checkpoint
        else:
            bronze_res = bronze_ingestion.run(
                db,
                project_id,
                actor=actor,
                load_mode=intent.get("load_mode", "FULL_LOAD"),
                source_id=source_id,
                replace_existing_data=overwrite_confirmed,
            )
        execution_results["stages"]["BRONZE_INGESTION"] = {
            "status": bronze_res.get("status", "FAILED"),
            "tables_ingested": bronze_res.get("passed", 0),
            "rows_transferred": sum(
                int(item.get("rows_loaded") or 0)
                for item in bronze_res.get("results", [])
                if item.get("status") == "PASSED"
            ),
            "failures": bronze_res.get("failed", 0),
            "run_id": bronze_res.get("run_id"),
            "checkpoint_reused": bronze_res.get("checkpoint_reused", False),
        }
        if bronze_res.get("status") != "PASSED":
            failed_items = [
                item for item in bronze_res.get("results", [])
                if item.get("status") != "PASSED"
            ]
            detail = "; ".join(
                f"{item.get('source', 'unknown table')}: {item.get('error', 'load failed')}"
                for item in failed_items[:3]
            )
            raise RuntimeError(f"Bronze ingestion did not fully pass: {detail or 'one or more tables failed'}")

        # Step 3: Medallion Modeling & Artifact Generation
        current_stage = "MEDALLION_GENERATION"
        sem_res = medallion.infer_semantics_hybrid(db, project_id)
        semantic_approval = medallion.approve_all_semantics(db, project_id, actor=actor)
        if semantic_approval.get("errors"):
            raise RuntimeError(
                "Semantic approval failed: " + "; ".join(semantic_approval["errors"][:3])
            )
        plan_res = medallion.build_medallion_plan(db, project_id, environment="DEV", catalog=catalog_name)
        art_res = medallion.generate_medallion_artifacts(db, project_id, environment="DEV")
        generated_count = int(art_res.get("generated_count", art_res.get("generated", 0)) or 0)
        if generated_count < 1:
            raise RuntimeError("Medallion generation produced no deployable artifacts")

        execution_results["stages"]["MEDALLION_GENERATION"] = {
            "status": "PASSED",
            "nodes_planned": plan_res.get("node_count", 0),
            "artifacts_generated": generated_count,
            "ai_attempted": sem_res.get("ai_attempted", 0),
        }

        # Step 4: Static Validation & AI Remediation
        current_stage = "VALIDATION_AND_REMEDIATION"
        rem_res = ai_remediation.run_remediation_batch(
            db,
            project_id,
            environment="DEV",
            use_ai=True,
            apply_valid_candidates=True,
            reviewer=actor,
            max_objects=50,
        )
        validation_report = medallion.medallion_validation_report(db, project_id, environment="DEV")
        if validation_report.get("status") != "PASSED":
            failed = validation_report.get("failed_artifacts", [])
            detail = "; ".join(
                f"{item.get('target_fqn', 'artifact')}: {', '.join(item.get('errors') or ['validation failed'])}"
                for item in failed[:3]
            )
            raise RuntimeError(
                f"{validation_report.get('failed_count', len(failed))} artifact(s) remain unresolved after remediation"
                + (f": {detail}" if detail else "")
            )
        artifact_approval = medallion.approve_all_medallion_artifacts(
            db, project_id, environment="DEV", reviewer=actor
        )
        if artifact_approval.get("errors"):
            raise RuntimeError(
                "Artifact approval failed: " + "; ".join(artifact_approval["errors"][:3])
            )
        execution_results["stages"]["VALIDATION_AND_REMEDIATION"] = {
            "status": "PASSED",
            "remediated_count": rem_res.get("applied_count", 0),
            "validated_count": validation_report.get("passed_count", generated_count),
            "remaining_failures": 0,
        }

        # Step 5: DEV Medallion Deployment
        current_stage = "DEV_DEPLOYMENT"
        dep_res = medallion.deploy_medallion_dev(
            db,
            project_id,
            allow_destructive=False,
            replace_existing_data=overwrite_confirmed,
            reuse_bronze=True,
            parent_run_id=run_id,
        )
        execution_results["stages"]["DEV_DEPLOYMENT"] = {
            "status": dep_res.get("status", "FAILED"),
            "deployed_count": dep_res.get("count", len(dep_res.get("deployed", []))),
            "run_id": dep_res.get("run_id"),
            "failed_target": dep_res.get("failed_target"),
            "error": dep_res.get("error"),
        }
        if dep_res.get("status") != "PASSED":
            raise RuntimeError(dep_res.get("error") or "DEV deployment did not pass")
        execution_results["stages"]["DEV_DEPLOYMENT"] = {
            "status": "PASSED",
            "deployed_count": dep_res.get("count", dep_res.get("deployed_count", 0)),
            "run_id": dep_res.get("run_id", run_id),
        }

        # Step 6: Reconciliation & Gate
        current_stage = "RECONCILIATION"
        rec_res = deployment.run_reconciliation(db, project_id, environment="DEV", actor=actor)
        gate_res = deployment.evaluate_dev_gate(db, project_id)
        if rec_res.get("status") != "PASSED" or gate_res.get("status") != "PASSED":
            raise RuntimeError(
                f"DEV quality gate did not pass (reconciliation={rec_res.get('status')}, gate={gate_res.get('status')})"
            )
        execution_results["stages"]["RECONCILIATION"] = {
            "status": "PASSED",
            "reconciliation_status": rec_res.get("status"),
            "gate_status": gate_res.get("status"),
        }

        ended_at = datetime.utcnow()
        execution_results["status"] = "COMPLETED"
        execution_results["ended_at"] = ended_at.isoformat()
        plan_payload["status"] = "COMPLETED"
        plan_payload["ended_at"] = ended_at.isoformat()
        plan_record.payload_json = json.dumps(
            {"status": "COMPLETED", "run_id": plan_id, "plan": plan_payload},
            default=str,
            sort_keys=True,
        )
        db.commit()

        _record(
            db,
            project_id,
            record_type="PROMPT_MIGRATION_RUN",
            status="COMPLETED",
            run_id=run_id,
            plan_id=plan_id,
            results=execution_results,
        )

    except Exception as exc:
        ended_at = datetime.utcnow()
        execution_results["status"] = "FAILED"
        execution_results["error"] = str(exc)
        execution_results["failed_stage"] = current_stage
        execution_results["errors"].append({
            "stage": current_stage,
            "message": str(exc),
            "recommended_action": recommended_actions.get(
                current_stage, "Review the execution evidence and retry after correcting the blocker."
            ),
        })
        failed_stage = execution_results["stages"].setdefault(current_stage, {})
        failed_stage.update({
            "status": "FAILED",
            "error": str(exc),
            "recommended_action": recommended_actions.get(current_stage),
        })
        execution_results["ended_at"] = ended_at.isoformat()
        plan_payload["status"] = "FAILED"
        plan_payload["error"] = str(exc)
        plan_payload["failed_stage"] = current_stage
        plan_record.payload_json = json.dumps(
            {"status": "FAILED", "run_id": plan_id, "plan": plan_payload},
            default=str,
            sort_keys=True,
        )
        db.commit()

        _record(
            db,
            project_id,
            record_type="PROMPT_MIGRATION_RUN",
            status="FAILED",
            run_id=run_id,
            plan_id=plan_id,
            error=str(exc),
            results=execution_results,
        )

    return execution_results


def latest_prompt_execution(db: Session, project_id: str) -> dict[str, Any] | None:
    """Return latest prompt execution run details and metrics."""
    records = db.scalars(
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "PROMPT_MIGRATION_RUN",
        )
        .order_by(CanonicalRecord.created_at.desc())
    ).all()
    if not records:
        return None
    for record in records:
        payload = _payload(record.payload_json)
        if "results" in payload:
            return payload.get("results") or payload
    payload = _payload(records[0].payload_json)
    return payload.get("results") or payload
