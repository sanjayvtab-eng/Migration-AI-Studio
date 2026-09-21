from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import CanonicalRecord, MigrationProject, MigrationSource
from app.models.canonical import MigrationDeployment
from app.services import deployment, medallion, prompt_orchestration, prompt_promotion
from app.services.engine import sha, uid


MASTER_STAGES = (
    ("DEV_MIGRATION", "SQL Server to governed DEV", "DEV"),
    ("TEST_PROMOTION", "Promote DEV release to TEST", "TEST"),
    ("UAT_PROMOTION", "Promote TEST release to UAT", "UAT"),
    ("PROD_PROMOTION", "Promote UAT release to PROD", "PROD"),
)
MAX_STAGE_ATTEMPTS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    run_id: str,
    **details: Any,
) -> CanonicalRecord:
    record = CanonicalRecord(
        id=uid("REC"),
        project_id=project_id,
        environment="ALL",
        record_type=record_type,
        payload_json=json.dumps(
            {"status": status, "run_id": run_id, **details},
            default=str,
            sort_keys=True,
        ),
    )
    db.add(record)
    db.commit()
    return record


def _master_plan_record(
    db: Session, project_id: str, plan_id: str | None = None
) -> CanonicalRecord | None:
    records = db.scalars(
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "MASTER_MIGRATION_PLAN",
        )
        .order_by(CanonicalRecord.created_at.desc())
    ).all()
    for record in records:
        plan = _payload(record.payload_json).get("plan") or {}
        if not plan_id or plan.get("plan_id") == plan_id:
            return record
    return None


def _save_plan(db: Session, record: CanonicalRecord, plan: dict[str, Any]) -> None:
    record.payload_json = json.dumps(
        {"status": plan["status"], "run_id": plan["plan_id"], "plan": plan},
        default=str,
        sort_keys=True,
    )
    db.commit()


def _dev_retry_evidence(db: Session, project_id: str) -> dict[str, Any]:
    """Snapshot actual SQL so internally generated versions cannot renew retries."""
    return {
        item["target_fqn"]: {
            "artifact_version_id": item["artifact_version_id"],
            "version": item["version"],
            "content_hash": sha(item["content"]),
            "approved": bool(
                item["review_status"] == "APPROVED"
                and item["validation_status"] == "PASSED"
                and item["executable"]
                and not medallion.medallion_routine_issues(
                    db, project_id, "DEV", item["content"], item.get("source_object_type") or ""
                )
            ),
        }
        for item in medallion.list_medallion_artifacts(db, project_id, environment="DEV")
    }


def _legacy_dev_retry_evidence(db: Session, project_id: str) -> dict[str, Any]:
    """Recover the last failed SQL revision for plans created before snapshots."""
    failures = db.scalars(select(MigrationDeployment).where(
        MigrationDeployment.project_id == project_id,
        MigrationDeployment.environment == "DEV",
        MigrationDeployment.status == "FAILED",
    ).order_by(MigrationDeployment.created_at.desc())).all()
    for failure in failures:
        evidence = _payload(failure.payload_json)
        if evidence.get("artifact_version_id") and evidence.get("target_fqn"):
            content_hash = evidence.get("artifact_content_hash")
            # Older runs may not include a hash. Without recorded evidence of
            # different SQL, do not silently grant an exhausted plan retries.
            return {evidence["target_fqn"]: evidence} if content_hash else {}
    return {}


def _renew_dev_retries(
    db: Session, project_id: str, plan: dict[str, Any], checkpoint: dict[str, Any],
    run_id: str, actor: str,
) -> bool:
    previous = checkpoint.get("retry_evidence")
    if previous is None:
        previous = _legacy_dev_retry_evidence(db, project_id)
    current = _dev_retry_evidence(db, project_id)
    corrections = {
        target: {"previous": old, "current": current[target]}
        for target, old in previous.items()
        if target in current and current[target]["approved"]
        and (old.get("content_hash") or old.get("artifact_content_hash"))
        and current[target]["content_hash"] != (old.get("content_hash") or old.get("artifact_content_hash"))
    }
    if not corrections:
        return False
    _record(
        db, project_id, record_type="MASTER_STAGE_RETRY_RENEWAL", status="RENEWED",
        run_id=run_id, plan_id=plan["plan_id"], stage="DEV_MIGRATION", actor=actor,
        previous_checkpoint=dict(checkpoint), corrections=corrections,
        reason="Validated and approved DEV SQL changed since the failed attempts",
    )
    checkpoint.update({
        "total_attempts": int(checkpoint.get("total_attempts", checkpoint.get("attempts", 0))),
        "attempts": 0,
        "retry_renewals": int(checkpoint.get("retry_renewals") or 0) + 1,
        "retry_evidence": current,
    })
    return True


def _renew_promotion_retries(
    db: Session,
    project_id: str,
    plan: dict[str, Any],
    checkpoint: dict[str, Any],
    stage: str,
    run_id: str,
    actor: str,
) -> bool:
    target = {"TEST_PROMOTION": "TEST", "UAT_PROMOTION": "UAT", "PROD_PROMOTION": "PROD"}.get(stage)
    if not target:
        return False
    source = prompt_promotion.PROMOTION_PATH.get(target, "DEV")
    manifest = deployment._latest_successful_medallion_run(db, project_id, source)
    if not manifest:
        return False
    previous_manifest_id = (checkpoint.get("details") or {}).get("stages", {}).get("PREFLIGHT", {}).get("source_deployment_run_id")
    failed_target = (checkpoint.get("details") or {}).get("stages", {}).get("DEPLOYMENT", {}).get("failed_target")
    current_key = f"{manifest[0]}:{failed_target or ''}"
    if checkpoint.get("last_renewed_key") == current_key:
        return False
    reason = None
    if previous_manifest_id and manifest[0] != previous_manifest_id:
        reason = f"New successful {source} deployment manifest {manifest[0]} is available"
    elif failed_target or checkpoint.get("status") == "FAILED":
        reason = f"Promotion deployment order and evidence resolved for {target} promotion"
    if not reason:
        return False
    _record(
        db,
        project_id,
        record_type="MASTER_STAGE_RETRY_RENEWAL",
        status="RENEWED",
        run_id=run_id,
        plan_id=plan["plan_id"],
        stage=stage,
        actor=actor,
        previous_checkpoint=dict(checkpoint),
        reason=reason,
    )
    checkpoint.update({
        "total_attempts": int(checkpoint.get("total_attempts", checkpoint.get("attempts", 0))),
        "attempts": 0,
        "retry_renewals": int(checkpoint.get("retry_renewals") or 0) + 1,
        "last_renewed_key": current_key,
    })
    return True


def _full_environment_scope(prompt: str) -> bool:
    normalized = prompt.upper()
    environments = set(re.findall(r"\b(DEV|TEST|UAT|PROD|PRODUCTION)\b", normalized))
    if "PRODUCTION" in environments:
        environments.remove("PRODUCTION")
        environments.add("PROD")
    explicit_chain = {"DEV", "TEST", "UAT", "PROD"}.issubset(environments)
    end_to_end = bool(re.search(r"\b(END[- ]TO[- ]END|ALL ENVIRONMENTS)\b", normalized))
    prod_explicit = "PROD" in environments
    return explicit_chain or (end_to_end and prod_explicit)


def _source_for_prompt(db: Session, project_id: str, prompt: str) -> MigrationSource | None:
    sources = list(
        db.scalars(
            select(MigrationSource).where(MigrationSource.project_id == project_id)
        ).all()
    )
    normalized = prompt.lower()
    for source in sources:
        if source.database_name and source.database_name.lower() in normalized:
            return source
        if source.profile_name and source.profile_name.lower() in normalized:
            return source
    return sources[0] if len(sources) == 1 else None


def generate_master_plan(
    db: Session,
    project_id: str,
    prompt: str,
    actor: str = "admin",
) -> dict[str, Any]:
    """Create one plan for DEV migration followed by TEST/UAT/PROD promotion."""
    if not prompt or not prompt.strip():
        raise ValueError("A master migration prompt is required")
    if not db.get(MigrationProject, project_id):
        raise LookupError("Project not found")
    if not _full_environment_scope(prompt):
        return {
            "status": "NEEDS_USER_INPUT",
            "prompt": prompt.strip(),
            "blockers": [
                "Production scope must be explicit. Include DEV, TEST, UAT, and PROD in the prompt."
            ],
            "actionable_steps": [
                "Example: Migrate MigrationDemo from SQL Server through DEV, TEST, UAT, and PROD Databricks."
            ],
        }

    source = _source_for_prompt(db, project_id, prompt)
    if not source:
        return {
            "status": "NEEDS_USER_INPUT",
            "prompt": prompt.strip(),
            "blockers": ["Specify exactly one registered SQL Server source database."],
            "actionable_steps": ["Select or name the source database and generate the plan again."],
        }

    dev_prompt = (
        f"Migrate {source.database_name} from SQL Server to DEV Databricks"
    )
    dev_plan = prompt_orchestration.generate_prompt_plan(
        db, project_id, dev_prompt, actor=actor
    )
    if dev_plan.get("status") == "NEEDS_USER_INPUT":
        return {
            **dev_plan,
            "prompt": prompt.strip(),
            "master_scope": ["DEV", "TEST", "UAT", "PROD"],
        }

    plan_id = uid("MMP")
    plan = {
        "plan_id": plan_id,
        "status": "PENDING_APPROVAL",
        "prompt": prompt.strip(),
        "actor": actor,
        "source": {
            "id": source.id,
            "database_name": source.database_name,
            "server_name": source.server_name,
        },
        "scope": {
            "source_platform": "SQL Server",
            "target_platform": "Databricks",
            "environments": ["DEV", "TEST", "UAT", "PROD"],
            "single_prompt": True,
            "authorization_mode": "ONE_TIME_ADMIN_AUTHORIZATION",
            "automatic_policy_gates": True,
        },
        "impact": {
            "table_count": dev_plan.get("impact", {}).get("table_count", 0),
            "estimated_rows": dev_plan.get("impact", {}).get("estimated_rows", 0),
            "risk_level": "HIGH",
            "requires_data_replacement_confirmation": bool(
                dev_plan.get("impact", {}).get("requires_overwrite")
            ),
            "requires_production_authorization": True,
        },
        "dev_plan_id": dev_plan["plan_id"],
        "stages": [
            {"stage": stage, "title": title, "environment": environment}
            for stage, title, environment in MASTER_STAGES
        ],
        "checkpoints": {
            stage: {"status": "PENDING", "attempts": 0}
            for stage, _, _ in MASTER_STAGES
        },
        "authorization": None,
        "created_at": _now(),
    }
    _record(
        db,
        project_id,
        record_type="MASTER_MIGRATION_PLAN",
        status="PENDING_APPROVAL",
        run_id=plan_id,
        plan=plan,
    )
    return plan


def get_master_plan(
    db: Session, project_id: str, plan_id: str | None = None
) -> dict[str, Any] | None:
    record = _master_plan_record(db, project_id, plan_id)
    return (_payload(record.payload_json).get("plan") or {}) if record else None


def _fresh_dev_plan(
    db: Session, project_id: str, plan: dict[str, Any], actor: str
) -> dict[str, Any]:
    existing = prompt_orchestration.get_prompt_plan(
        db, project_id, plan.get("dev_plan_id")
    )
    if existing and existing.get("status") in {"PENDING_APPROVAL", "APPROVED"}:
        return existing
    source_database = plan.get("source", {}).get("database_name")
    replacement = prompt_orchestration.generate_prompt_plan(
        db,
        project_id,
        f"Migrate {source_database} from SQL Server to DEV Databricks",
        actor=actor,
    )
    if replacement.get("status") == "NEEDS_USER_INPUT":
        raise RuntimeError("; ".join(replacement.get("blockers", [])))
    plan["dev_plan_id"] = replacement["plan_id"]
    return replacement


def _run_stage(
    db: Session,
    project_id: str,
    plan: dict[str, Any],
    stage: str,
    actor: str,
) -> dict[str, Any]:
    if stage == "DEV_MIGRATION":
        dev_plan = _fresh_dev_plan(db, project_id, plan, actor)
        return prompt_orchestration.execute_prompt_plan(
            db,
            project_id,
            plan_id=dev_plan["plan_id"],
            actor=actor,
            overwrite_confirmed=bool(
                (plan.get("authorization") or {}).get("data_replacement_authorized")
            ),
        )

    target = {
        "TEST_PROMOTION": "TEST",
        "UAT_PROMOTION": "UAT",
        "PROD_PROMOTION": "PROD",
    }[stage]
    source = prompt_promotion.PROMOTION_PATH[target]
    promotion_plan = prompt_promotion.generate_promotion_plan(
        db,
        project_id,
        f"Promote approved {source} release to {target}",
        actor=actor,
    )
    if promotion_plan.get("status") == "NEEDS_USER_INPUT":
        return {
            "status": "FAILED",
            "failed_stage": "PREFLIGHT",
            "error": "; ".join(promotion_plan.get("blockers", [])),
            "errors": [
                {
                    "stage": "PREFLIGHT",
                    "message": "; ".join(promotion_plan.get("blockers", [])),
                    "recommended_action": promotion_plan.get("actionable_steps", [
                        f"Resolve the {source} quality gate and resume the master workflow."
                    ])[0],
                }
            ],
        }
    return prompt_promotion.execute_promotion_plan(
        db,
        project_id,
        plan_id=promotion_plan["plan_id"],
        actor=actor,
        production_confirmed=target == "PROD",
    )


def execute_master_plan(
    db: Session,
    project_id: str,
    plan_id: str,
    actor: str = "admin",
    workflow_authorized: bool = False,
    production_authorized: bool = False,
    data_replacement_authorized: bool = False,
) -> dict[str, Any]:
    """Execute or resume the entire governed chain from the last passed checkpoint."""
    record = _master_plan_record(db, project_id, plan_id)
    if not record:
        raise LookupError(f"Master migration plan {plan_id} not found")
    plan = _payload(record.payload_json).get("plan") or {}
    if plan.get("status") not in {"PENDING_APPROVAL", "FAILED", "PAUSED"}:
        raise ValueError(f"Master plan cannot be executed in status {plan.get('status')}")

    authorization = plan.get("authorization")
    if not authorization:
        if not workflow_authorized:
            raise PermissionError("Explicit authorization for the complete workflow is required")
        if not production_authorized:
            raise PermissionError("Explicit PROD authorization is required")
        if (
            plan.get("impact", {}).get("requires_data_replacement_confirmation")
            and not data_replacement_authorized
        ):
            raise PermissionError("Explicit FULL_LOAD replacement authorization is required")
        authorization = {
            "authorized_by": actor,
            "authorized_at": _now(),
            "scope": ["DEV", "TEST", "UAT", "PROD"],
            "production_authorized": True,
            "data_replacement_authorized": data_replacement_authorized,
        }
        plan["authorization"] = authorization

    run_id = uid("MMR")
    started_at = _now()
    plan.update({"status": "EXECUTING", "active_run_id": run_id})
    _save_plan(db, record, plan)
    _record(
        db,
        project_id,
        record_type="MASTER_MIGRATION_RUN",
        status="RUNNING",
        run_id=run_id,
        plan_id=plan_id,
        started_at=started_at,
    )

    result: dict[str, Any] = {
        "run_id": run_id,
        "plan_id": plan_id,
        "status": "RUNNING",
        "authorization": authorization,
        "started_at": started_at,
        "stages": {},
        "errors": [],
    }
    for stage, title, environment in MASTER_STAGES:
        checkpoint = plan["checkpoints"].setdefault(
            stage, {"status": "PENDING", "attempts": 0}
        )
        if checkpoint.get("status") == "PASSED":
            result["stages"][stage] = {**checkpoint, "checkpoint_reused": True}
            continue
        attempts = int(checkpoint.get("attempts") or 0)
        checkpoint["max_attempts"] = MAX_STAGE_ATTEMPTS
        if stage == "DEV_MIGRATION" and attempts > 0 and checkpoint.get("status") == "FAILED":
            if _renew_dev_retries(db, project_id, plan, checkpoint, run_id, actor):
                attempts = 0
        elif stage in {"TEST_PROMOTION", "UAT_PROMOTION", "PROD_PROMOTION"} and attempts >= MAX_STAGE_ATTEMPTS and checkpoint.get("status") == "FAILED":
            if _renew_promotion_retries(db, project_id, plan, checkpoint, stage, run_id, actor):
                attempts = 0
        if attempts >= MAX_STAGE_ATTEMPTS:
            stage_result = {
                "status": "FAILED",
                "error": f"{title} reached the maximum of {MAX_STAGE_ATTEMPTS} attempts",
                "errors": [{"recommended_action": (
                    "Repair and approve corrected DEV SQL, then resume this master plan. "
                    "The retry budget renews only when validated, approved SQL has changed."
                    if stage == "DEV_MIGRATION" else
                    f"Resolve the {environment} evidence and resume this master plan."
                )}],
            }
        else:
            checkpoint.update({
                "status": "RUNNING",
                "attempts": attempts + 1,
                "total_attempts": int(checkpoint.get("total_attempts", attempts)) + 1,
                "started_at": _now(),
            })
            _save_plan(db, record, plan)
            try:
                stage_result = _run_stage(db, project_id, plan, stage, actor)
            except Exception as exc:
                stage_result = {"status": "FAILED", "error": str(exc)}
            if stage == "DEV_MIGRATION":
                # Save the final inputs after in-stage generation/remediation,
                # so merely pressing Resume cannot refresh its own budget.
                checkpoint["retry_evidence"] = _dev_retry_evidence(db, project_id)

        if stage_result.get("status") != "COMPLETED":
            error_message = stage_result.get("error") or f"{title} did not complete"
            checkpoint.update({
                "status": "FAILED",
                "ended_at": _now(),
                "error": error_message,
                "details": stage_result,
            })
            plan.update({
                "status": "FAILED",
                "failed_stage": stage,
                "error": error_message,
            })
            _save_plan(db, record, plan)
            error = {
                "stage": stage,
                "environment": environment,
                "message": error_message,
                "recommended_action": (
                    stage_result.get("errors") or [{}]
                )[0].get(
                    "recommended_action",
                    f"Resolve the {environment} evidence and resume this master plan.",
                ),
            }
            result.update({
                "status": "FAILED",
                "failed_stage": stage,
                "error": error_message,
                "errors": [error],
                "ended_at": _now(),
            })
            result["stages"][stage] = {**checkpoint}
            _record(
                db,
                project_id,
                record_type="MASTER_MIGRATION_RUN",
                status="FAILED",
                run_id=run_id,
                plan_id=plan_id,
                results=result,
            )
            return result

        checkpoint.update({
            "status": "PASSED",
            "ended_at": _now(),
            "error": None,
            "details": stage_result,
        })
        result["stages"][stage] = {**checkpoint}
        _save_plan(db, record, plan)

    ended_at = _now()
    plan.update({"status": "COMPLETED", "ended_at": ended_at, "failed_stage": None, "error": None})
    _save_plan(db, record, plan)
    result.update({"status": "COMPLETED", "ended_at": ended_at})
    _record(
        db,
        project_id,
        record_type="MASTER_MIGRATION_RUN",
        status="COMPLETED",
        run_id=run_id,
        plan_id=plan_id,
        results=result,
    )
    return result


def latest_master_execution(db: Session, project_id: str) -> dict[str, Any] | None:
    records = db.scalars(
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "MASTER_MIGRATION_RUN",
        )
        .order_by(CanonicalRecord.created_at.desc())
    ).all()
    for record in records:
        payload = _payload(record.payload_json)
        if payload.get("results"):
            return payload["results"]
    return _payload(records[0].payload_json) if records else None
