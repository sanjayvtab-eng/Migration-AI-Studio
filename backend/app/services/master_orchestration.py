from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import CanonicalRecord, MigrationIssue, MigrationProject, MigrationSource, MigrationStageArtifact, MigrationStageArtifactVersion
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

    # Preserve the complete business prompt. Release 7 parsing depends on artifact
    # names, joins, filters, measures, and approval language that a generic prompt
    # would discard.
    dev_prompt = prompt.strip()
    dev_plan = prompt_orchestration.generate_prompt_plan(
        db, project_id, dev_prompt, actor=actor, target_environment_override="DEV"
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
        str(plan.get("prompt") or f"Migrate {source_database} from SQL Server to DEV Databricks"),
        actor=actor,
        target_environment_override="DEV",
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


AUTOMATED_PROMOTION_RECORD_TYPE = "AUTOMATED_PROMOTION_RUN"
AUTOMATED_PROMOTION_CONFIRMATION = "PROMOTE TO PROD"

AUTOMATED_PROMOTION_STATES = (
    "NOT_STARTED",
    "AUTHORIZED",
    "TEST_PRECHECK",
    "TEST_PROMOTING",
    "TEST_RECONCILING",
    "TEST_EVALUATING_GATE",
    "TEST_PASSED",
    "UAT_PRECHECK",
    "UAT_PROMOTING",
    "UAT_RECONCILING",
    "UAT_EVALUATING_GATE",
    "UAT_PASSED",
    "PROD_PRECHECK",
    "PROD_PROMOTING",
    "PROD_VALIDATING",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
    "PAUSED",
    "CANCELLED",
    "RESUMABLE",
)


def _latest_gate_status(db: Session, project_id: str, environment: str) -> str | None:
    rec = db.scalars(
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "QUALITY_GATE",
            CanonicalRecord.environment == environment,
        )
        .order_by(CanonicalRecord.created_at.desc())
    ).first()
    if rec:
        return str(_payload(rec.payload_json).get("status") or "")
    from app.models.entities import MigrationQualityGate
    gate = db.scalars(
        select(MigrationQualityGate)
        .where(
            MigrationQualityGate.project_id == project_id,
            MigrationQualityGate.environment == environment,
        )
        .order_by(MigrationQualityGate.created_at.desc())
    ).first()
    return gate.status if gate else None


def _latest_recon_status(db: Session, project_id: str, environment: str) -> str | None:
    rec = db.scalars(
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "RECONCILIATION",
            CanonicalRecord.environment == environment,
        )
        .order_by(CanonicalRecord.created_at.desc())
    ).first()
    if rec:
        return str(_payload(rec.payload_json).get("status") or "")
    from app.models.canonical import MigrationReconciliation
    recon = db.scalars(
        select(MigrationReconciliation)
        .where(
            MigrationReconciliation.project_id == project_id,
            MigrationReconciliation.environment == environment,
        )
        .order_by(MigrationReconciliation.created_at.desc())
    ).first()
    return recon.status if recon else None


def _automated_run_record(
    db: Session, project_id: str, run_id: str | None = None
) -> CanonicalRecord | None:
    records = db.scalars(
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == AUTOMATED_PROMOTION_RECORD_TYPE,
        )
        .order_by(CanonicalRecord.created_at.desc())
    ).all()
    for record in records:
        payload = _payload(record.payload_json)
        if not run_id or payload.get("run_id") == run_id:
            return record
    return None


def _save_automated_run(db: Session, record: CanonicalRecord, run: dict[str, Any]) -> None:
    record.payload_json = json.dumps(run, default=str, sort_keys=True)
    db.commit()


def get_automated_promotion_preflight(db: Session, project_id: str) -> dict[str, Any]:
    project = db.get(MigrationProject, project_id)
    if not project:
        raise LookupError("Project not found")

    dev_catalog, test_catalog, uat_catalog, prod_catalog = deployment._project_catalogs(db, project_id)
    dev_manifest = deployment._latest_successful_medallion_run(db, project_id, "DEV")

    dev_gate_status = _latest_gate_status(db, project_id, "DEV")
    dev_recon_status = _latest_recon_status(db, project_id, "DEV")

    blockers: list[str] = []
    if not dev_manifest:
        blockers.append("DEV deployment is not complete or no successful manifest found.")
    if dev_gate_status != "PASSED":
        blockers.append(f"DEV quality gate status is {dev_gate_status or 'NOT_EVALUATED'} (must be PASSED).")
    if dev_recon_status != "PASSED":
        blockers.append(f"DEV reconciliation status is {dev_recon_status or 'NOT_RUN'} (must be PASSED).")

    # Check unapproved reviews
    unapproved = db.scalars(
        select(MigrationStageArtifactVersion)
        .join(MigrationStageArtifact, MigrationStageArtifact.id == MigrationStageArtifactVersion.artifact_id)
        .where(
            MigrationStageArtifact.project_id == project_id,
            MigrationStageArtifactVersion.review_status != "APPROVED",
        )
    ).all()
    if unapproved:
        blockers.append(f"{len(unapproved)} artifact version(s) are awaiting required review approval.")

    # Check open blockers
    open_blockers = db.scalars(
        select(MigrationIssue)
        .where(
            MigrationIssue.project_id == project_id,
            MigrationIssue.severity == "BLOCKER",
            MigrationIssue.status == "OPEN",
        )
    ).all()
    if open_blockers:
        blockers.append(f"{len(open_blockers)} open BLOCKER issue(s) exist.")

    # Check TEST precheck
    test_chk = deployment.test_promotion_precheck(db, project_id, test_databricks=False)
    if not test_chk.get("eligible"):
        for b in test_chk.get("blockers", []):
            msg = b.get("message") if isinstance(b, dict) else str(b)
            if msg and msg not in blockers:
                blockers.append(msg)

    # Current artifact snapshot
    artifact_versions = {}
    if dev_manifest:
        for evidence, payload in dev_manifest[1]:
            target_fqn = str(payload.get("target_fqn") or "")
            artifact_versions[target_fqn] = {
                "artifact_version_id": payload.get("artifact_version_id"),
                "artifact_version": payload.get("artifact_version"),
                "content_hash": payload.get("artifact_content_hash"),
                "layer": payload.get("layer"),
                "object_id": evidence.object_id,
            }

    latest_record = _automated_run_record(db, project_id)
    active_run = _payload(latest_record.payload_json) if latest_record else None

    return {
        "eligible": len(blockers) == 0,
        "blockers": blockers,
        "source_project": {"id": project.id, "name": project.name},
        "release_id": dev_manifest[0] if dev_manifest else None,
        "artifact_count": len(dev_manifest[1]) if dev_manifest else 0,
        "dev_catalog": dev_catalog,
        "test_catalog": test_catalog,
        "uat_catalog": uat_catalog,
        "prod_catalog": prod_catalog,
        "bronze_strategy": "Databricks native DEEP CLONE (DEV -> TEST -> UAT -> PROD)",
        "silver_gold_strategy": "Catalog-reference retargeting + DDL/DML deployment",
        "risk_level": "HIGH",
        "environments": ["DEV", "TEST", "UAT", "PROD"],
        "current_artifact_versions": artifact_versions,
        "active_run": active_run,
        "required_confirmation_text": AUTOMATED_PROMOTION_CONFIRMATION,
    }


def authorize_automated_promotion(
    db: Session,
    project_id: str,
    confirmation_text: str,
    actor: str = "admin",
) -> dict[str, Any]:
    if (confirmation_text or "").strip() != AUTOMATED_PROMOTION_CONFIRMATION:
        raise ValueError(
            f"Explicit confirmation '{AUTOMATED_PROMOTION_CONFIRMATION}' is required to authorize end-to-end promotion to PROD"
        )

    preflight = get_automated_promotion_preflight(db, project_id)
    if not preflight["eligible"]:
        raise ValueError(
            "Automated promotion preflight blocked: " + "; ".join(preflight["blockers"])
        )

    active_run = preflight.get("active_run")
    if active_run and active_run.get("status") == "RUNNING":
        raise ValueError(
            f"An automated promotion run is already active ({active_run.get('run_id')})"
        )

    run_id = uid("APR")
    run = {
        "run_id": run_id,
        "project_id": project_id,
        "status": "RUNNING",
        "state": "AUTHORIZED",
        "current_environment": "TEST",
        "current_operation": "TEST_PRECHECK",
        "authorized_release_id": preflight["release_id"],
        "artifact_count": preflight["artifact_count"],
        "authorized_artifact_versions": preflight["current_artifact_versions"],
        "catalogs": {
            "DEV": preflight["dev_catalog"],
            "TEST": preflight["test_catalog"],
            "UAT": preflight["uat_catalog"],
            "PROD": preflight["prod_catalog"],
        },
        "authorization": {
            "authorized_by": actor,
            "authorized_at": _now(),
            "confirmation_text": confirmation_text.strip(),
            "scope": ["TEST", "UAT", "PROD"],
            "risk_level": "HIGH",
        },
        "environments": {
            "TEST": {"status": "PENDING", "attempts": 0, "stages": {}},
            "UAT": {"status": "PENDING", "attempts": 0, "stages": {}},
            "PROD": {"status": "PENDING", "attempts": 0, "stages": {}},
        },
        "pause_requested": False,
        "is_resumable": False,
        "last_successful_checkpoint": "DEV_PASSED",
        "started_at": _now(),
        "ended_at": None,
        "errors": [],
    }

    record = CanonicalRecord(
        id=uid("REC"),
        project_id=project_id,
        environment="ALL",
        record_type=AUTOMATED_PROMOTION_RECORD_TYPE,
        payload_json=json.dumps(run, default=str, sort_keys=True),
    )
    db.add(record)
    db.commit()

    return run_automated_promotion(db, project_id, run_id=run_id, actor=actor)


def run_automated_promotion(
    db: Session,
    project_id: str,
    run_id: str,
    actor: str = "admin",
) -> dict[str, Any]:
    record = _automated_run_record(db, project_id, run_id)
    if not record:
        raise LookupError(f"Automated promotion run {run_id} not found")
    run = _payload(record.payload_json)

    if run.get("status") in {"COMPLETED", "CANCELLED"}:
        return run

    run["status"] = "RUNNING"
    run["is_resumable"] = False
    _save_automated_run(db, record, run)

    def transition(state: str, env: str, op: str) -> None:
        run["state"] = state
        run["current_environment"] = env
        run["current_operation"] = op
        run["updated_at"] = _now()
        _save_automated_run(db, record, run)

    def fail(env: str, op: str, err: str) -> dict[str, Any]:
        run["status"] = "FAILED"
        run["state"] = "FAILED"
        run["is_resumable"] = True
        run["current_environment"] = env
        run["current_operation"] = op
        if env in run.get("environments", {}):
            run["environments"][env]["status"] = "FAILED"
            run["environments"][env]["error"] = err
        run.setdefault("errors", []).append({
            "environment": env,
            "operation": op,
            "message": err,
            "occurred_at": _now(),
        })
        run["ended_at"] = _now()
        _save_automated_run(db, record, run)
        return run

    def verify_artifact_versions() -> str | None:
        authorized = run.get("authorized_artifact_versions") or {}
        dev_manifest = deployment._latest_successful_medallion_run(db, project_id, "DEV")
        if not dev_manifest:
            return "DEV deployment manifest is missing or invalid"
        if dev_manifest[0] != run.get("authorized_release_id"):
            return f"Source deployment manifest {dev_manifest[0]} does not match authorized release {run.get('authorized_release_id')}"
        current = {}
        for evidence, payload in dev_manifest[1]:
            target_fqn = str(payload.get("target_fqn") or "")
            current[target_fqn] = payload.get("artifact_version_id")
        for target_fqn, auth_meta in authorized.items():
            if target_fqn not in current:
                return f"Artifact {target_fqn} missing from current DEV deployment manifest"
            if current[target_fqn] != auth_meta.get("artifact_version_id"):
                return f"Artifact {target_fqn} version changed since authorization"
        return None

    # Stage 1: TEST Promotion
    if run["environments"]["TEST"]["status"] != "PASSED":
        transition("TEST_PRECHECK", "TEST", "Running TEST Precheck")
        version_err = verify_artifact_versions()
        if version_err:
            return fail("TEST", "TEST_PRECHECK", version_err)

        try:
            precheck = deployment.test_promotion_precheck(db, project_id, test_databricks=True)
            if not precheck.get("eligible"):
                blockers = "; ".join(
                    b.get("message") if isinstance(b, dict) else str(b)
                    for b in precheck.get("blockers", [])
                )
                return fail("TEST", "TEST_PRECHECK", blockers or "TEST precheck failed")
            run["environments"]["TEST"]["stages"]["PRECHECK"] = {
                "status": "PASSED",
                "artifact_count": precheck.get("artifact_count"),
                "source_deployment_run_id": precheck.get("source_deployment_run_id"),
            }
        except Exception as exc:
            return fail("TEST", "TEST_PRECHECK", str(exc))

        transition("TEST_PROMOTING", "TEST", "Promoting to TEST (DEEP CLONE & Retargeting)")
        run["environments"]["TEST"]["attempts"] = int(run["environments"]["TEST"].get("attempts") or 0) + 1
        try:
            promo = deployment.promote_medallion_to_test(db, project_id)
            if promo.get("status") != "PASSED":
                return fail("TEST", "TEST_PROMOTING", promo.get("error") or "TEST promotion failed")
            run["environments"]["TEST"]["stages"]["DEPLOYMENT"] = {
                "status": "PASSED",
                "run_id": promo.get("run_id"),
                "count": promo.get("count"),
            }
        except Exception as exc:
            return fail("TEST", "TEST_PROMOTING", str(exc))

        transition("TEST_RECONCILING", "TEST", "Reconciling TEST Deployment")
        try:
            recon = deployment.run_reconciliation(db, project_id, "TEST", actor=actor)
            if recon.get("status") != "PASSED":
                return fail("TEST", "TEST_RECONCILING", f"TEST reconciliation failed for {recon.get('failed', 0)} object(s)")
            run["environments"]["TEST"]["stages"]["RECONCILIATION"] = {
                "status": "PASSED",
                "run_id": recon.get("run_id"),
                "passed": recon.get("passed"),
            }
        except Exception as exc:
            return fail("TEST", "TEST_RECONCILING", str(exc))

        transition("TEST_EVALUATING_GATE", "TEST", "Evaluating TEST Quality Gate")
        try:
            gate = deployment.evaluate_test_gate(db, project_id)
            if gate.get("status") != "PASSED":
                blockers = "; ".join(gate.get("blockers", []))
                return fail("TEST", "TEST_EVALUATING_GATE", blockers or "TEST quality gate blocked")
            run["environments"]["TEST"]["stages"]["QUALITY_GATE"] = {
                "status": "PASSED",
                "gate_id": gate.get("gate_id"),
            }
        except Exception as exc:
            return fail("TEST", "TEST_EVALUATING_GATE", str(exc))

        run["environments"]["TEST"]["status"] = "PASSED"
        run["last_successful_checkpoint"] = "TEST_PASSED"
        transition("TEST_PASSED", "TEST", "TEST Promotion Complete")

        if run.get("pause_requested"):
            run["status"] = "PAUSED"
            run["state"] = "PAUSED"
            run["is_resumable"] = True
            run["current_operation"] = "Paused after TEST completion by user request"
            _save_automated_run(db, record, run)
            return run

    # Stage 2: UAT Promotion
    if run["environments"]["UAT"]["status"] != "PASSED":
        transition("UAT_PRECHECK", "UAT", "Running UAT Precheck")
        version_err = verify_artifact_versions()
        if version_err:
            return fail("UAT", "UAT_PRECHECK", version_err)

        try:
            precheck = deployment.uat_promotion_precheck(db, project_id, test_databricks=True)
            if not precheck.get("eligible"):
                blockers = "; ".join(
                    b.get("message") if isinstance(b, dict) else str(b)
                    for b in precheck.get("blockers", [])
                )
                return fail("UAT", "UAT_PRECHECK", blockers or "UAT precheck failed")
            run["environments"]["UAT"]["stages"]["PRECHECK"] = {
                "status": "PASSED",
                "artifact_count": precheck.get("artifact_count"),
                "source_deployment_run_id": precheck.get("source_deployment_run_id"),
            }
        except Exception as exc:
            return fail("UAT", "UAT_PRECHECK", str(exc))

        transition("UAT_PROMOTING", "UAT", "Promoting to UAT (DEEP CLONE & Retargeting)")
        run["environments"]["UAT"]["attempts"] = int(run["environments"]["UAT"].get("attempts") or 0) + 1
        try:
            promo = deployment.promote_medallion_to_uat(db, project_id)
            if promo.get("status") != "PASSED":
                return fail("UAT", "UAT_PROMOTING", promo.get("error") or "UAT promotion failed")
            run["environments"]["UAT"]["stages"]["DEPLOYMENT"] = {
                "status": "PASSED",
                "run_id": promo.get("run_id"),
                "count": promo.get("count"),
            }
        except Exception as exc:
            return fail("UAT", "UAT_PROMOTING", str(exc))

        transition("UAT_RECONCILING", "UAT", "Reconciling UAT Deployment")
        try:
            recon = deployment.run_reconciliation(db, project_id, "UAT", actor=actor)
            if recon.get("status") != "PASSED":
                return fail("UAT", "UAT_RECONCILING", f"UAT reconciliation failed for {recon.get('failed', 0)} object(s)")
            run["environments"]["UAT"]["stages"]["RECONCILIATION"] = {
                "status": "PASSED",
                "run_id": recon.get("run_id"),
                "passed": recon.get("passed"),
            }
        except Exception as exc:
            return fail("UAT", "UAT_RECONCILING", str(exc))

        transition("UAT_EVALUATING_GATE", "UAT", "Evaluating UAT Quality Gate")
        try:
            gate = deployment.evaluate_uat_gate(db, project_id)
            if gate.get("status") != "PASSED":
                blockers = "; ".join(gate.get("blockers", []))
                return fail("UAT", "UAT_EVALUATING_GATE", blockers or "UAT quality gate blocked")
            run["environments"]["UAT"]["stages"]["QUALITY_GATE"] = {
                "status": "PASSED",
                "gate_id": gate.get("gate_id"),
            }
        except Exception as exc:
            return fail("UAT", "UAT_EVALUATING_GATE", str(exc))

        run["environments"]["UAT"]["status"] = "PASSED"
        run["last_successful_checkpoint"] = "UAT_PASSED"
        transition("UAT_PASSED", "UAT", "UAT Promotion Complete")

        if run.get("pause_requested"):
            run["status"] = "PAUSED"
            run["state"] = "PAUSED"
            run["is_resumable"] = True
            run["current_operation"] = "Paused after UAT completion by user request"
            _save_automated_run(db, record, run)
            return run

    # Stage 3: PROD Promotion & Post-Deployment Validation
    if run["environments"]["PROD"]["status"] != "PASSED":
        transition("PROD_PRECHECK", "PROD", "Running PROD Precheck")
        version_err = verify_artifact_versions()
        if version_err:
            return fail("PROD", "PROD_PRECHECK", version_err)

        try:
            precheck = deployment.prod_promotion_precheck(db, project_id, test_databricks=True)
            if not precheck.get("eligible"):
                blockers = "; ".join(
                    b.get("message") if isinstance(b, dict) else str(b)
                    for b in precheck.get("blockers", [])
                )
                return fail("PROD", "PROD_PRECHECK", blockers or "PROD precheck failed")
            run["environments"]["PROD"]["stages"]["PRECHECK"] = {
                "status": "PASSED",
                "artifact_count": precheck.get("artifact_count"),
                "source_deployment_run_id": precheck.get("source_deployment_run_id"),
            }
        except Exception as exc:
            return fail("PROD", "PROD_PRECHECK", str(exc))

        transition("PROD_PROMOTING", "PROD", "Promoting to PROD (DEEP CLONE & Retargeting)")
        run["environments"]["PROD"]["attempts"] = int(run["environments"]["PROD"].get("attempts") or 0) + 1
        try:
            promo = deployment.promote_medallion_to_prod(db, project_id)
            if promo.get("status") != "PASSED":
                return fail("PROD", "PROD_PROMOTING", promo.get("error") or "PROD promotion failed")
            run["environments"]["PROD"]["stages"]["DEPLOYMENT"] = {
                "status": "PASSED",
                "run_id": promo.get("run_id"),
                "count": promo.get("count"),
            }
        except Exception as exc:
            return fail("PROD", "PROD_PROMOTING", str(exc))

        transition("PROD_VALIDATING", "PROD", "Running Safe PROD Post-Deployment Validation")
        try:
            recon = deployment.run_reconciliation(db, project_id, "PROD", actor=actor)
            if recon.get("status") != "PASSED":
                return fail("PROD", "PROD_VALIDATING", f"PROD reconciliation validation failed for {recon.get('failed', 0)} object(s)")
            gate = deployment.evaluate_prod_gate(db, project_id)
            if gate.get("status") != "PASSED":
                blockers = "; ".join(gate.get("blockers", []))
                return fail("PROD", "PROD_VALIDATING", blockers or "PROD quality gate blocked")
            run["environments"]["PROD"]["stages"]["VALIDATION"] = {
                "status": "PASSED",
                "reconciliation_run_id": recon.get("run_id"),
                "gate_id": gate.get("gate_id"),
            }
        except Exception as exc:
            return fail("PROD", "PROD_VALIDATING", str(exc))

        run["environments"]["PROD"]["status"] = "PASSED"
        run["last_successful_checkpoint"] = "PROD_PASSED"

    # COMPLETED
    run["status"] = "COMPLETED"
    run["state"] = "COMPLETED"
    run["ended_at"] = _now()
    run["current_environment"] = "PROD"
    run["current_operation"] = "End-to-end automated promotion completed with all quality gates passed"
    _save_automated_run(db, record, run)
    return run


def pause_automated_promotion(
    db: Session,
    project_id: str,
    run_id: str | None = None,
    actor: str = "admin",
) -> dict[str, Any]:
    record = _automated_run_record(db, project_id, run_id)
    if not record:
        raise LookupError("Automated promotion run not found")
    run = _payload(record.payload_json)
    if run.get("status") != "RUNNING":
        return run
    run["pause_requested"] = True
    _save_automated_run(db, record, run)
    return run


def resume_automated_promotion(
    db: Session,
    project_id: str,
    run_id: str | None = None,
    actor: str = "admin",
) -> dict[str, Any]:
    record = _automated_run_record(db, project_id, run_id)
    if not record:
        raise LookupError("Automated promotion run not found")
    run = _payload(record.payload_json)
    if run.get("status") not in {"PAUSED", "FAILED", "BLOCKED", "RESUMABLE"}:
        raise ValueError(f"Run in status {run.get('status')} cannot be resumed")
    run["status"] = "RUNNING"
    run["pause_requested"] = False
    run["errors"] = []
    _save_automated_run(db, record, run)
    return run_automated_promotion(db, project_id, run["run_id"], actor=actor)


def cancel_automated_promotion(
    db: Session,
    project_id: str,
    run_id: str | None = None,
    actor: str = "admin",
) -> dict[str, Any]:
    record = _automated_run_record(db, project_id, run_id)
    if not record:
        raise LookupError("Automated promotion run not found")
    run = _payload(record.payload_json)
    if run.get("status") == "COMPLETED":
        return run
    run["status"] = "CANCELLED"
    run["state"] = "CANCELLED"
    run["ended_at"] = _now()
    run["current_operation"] = "Promotion cancelled by user"
    for env in ("TEST", "UAT", "PROD"):
        if run.get("environments", {}).get(env, {}).get("status") != "PASSED":
            run.setdefault("environments", {}).setdefault(env, {})["status"] = "CANCELLED"
    _save_automated_run(db, record, run)
    return run


def get_automated_promotion_status(
    db: Session,
    project_id: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    preflight = get_automated_promotion_preflight(db, project_id)
    record = _automated_run_record(db, project_id, run_id)
    run = _payload(record.payload_json) if record else None
    return {
        "preflight": preflight,
        "run": run,
        "is_active": bool(run and run.get("status") == "RUNNING"),
        "is_resumable": bool(run and (run.get("is_resumable") or run.get("status") in {"PAUSED", "FAILED"})),
    }
