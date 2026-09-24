from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import CanonicalRecord, MigrationProject
from app.services import deployment
from app.services.engine import uid


PROMOTION_PATH = {
    "TEST": "DEV",
    "UAT": "TEST",
    "PROD": "UAT",
}


def _payload(value: str | None) -> dict[str, Any]:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _record(
    db: Session,
    project_id: str,
    environment: str,
    *,
    record_type: str,
    status: str,
    run_id: str,
    **details: Any,
) -> CanonicalRecord:
    record = CanonicalRecord(
        id=uid("REC"),
        project_id=project_id,
        environment=environment,
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


def _target_environment(prompt: str) -> str | None:
    normalized = prompt.strip().upper()
    direct = {
        "PROD" if value == "PRODUCTION" else value
        for value in re.findall(r"\bTO\s+(TEST|UAT|PROD|PRODUCTION)\b", normalized)
    }
    if len(direct) == 1:
        target = next(iter(direct))
        mentions = {
            "PROD" if value == "PRODUCTION" else value
            for value in re.findall(r"\b(TEST|UAT|PROD|PRODUCTION)\b", normalized)
        }
        if mentions.issubset({target, PROMOTION_PATH[target]}):
            return target
        return None
    if len(direct) > 1:
        return None
    mentions = {
        "PROD" if value == "PRODUCTION" else value
        for value in re.findall(r"\b(TEST|UAT|PROD|PRODUCTION)\b", normalized)
    }
    return next(iter(mentions)) if len(mentions) == 1 else None


def _source_environment(prompt: str) -> str | None:
    match = re.search(r"\bFROM\s+(DEV|TEST|UAT)\b", prompt.strip().upper())
    return match.group(1) if match else None


def _services(target: str) -> tuple[Callable[..., dict], Callable[..., dict], Callable[..., dict]]:
    if target == "TEST":
        return (
            deployment.test_promotion_precheck,
            deployment.promote_medallion_to_test,
            deployment.evaluate_test_gate,
        )
    if target == "UAT":
        return (
            deployment.uat_promotion_precheck,
            deployment.promote_medallion_to_uat,
            deployment.evaluate_uat_gate,
        )
    if target == "PROD":
        return (
            deployment.prod_promotion_precheck,
            deployment.promote_medallion_to_prod,
            deployment.evaluate_prod_gate,
        )
    raise ValueError(f"Unsupported promotion target {target}")


def _target_catalog(target: str) -> str:
    settings = get_settings()
    return {
        "TEST": settings.test_catalog,
        "UAT": settings.uat_catalog,
        "PROD": settings.prod_catalog,
    }[target]


def _blocker_messages(precheck: dict[str, Any]) -> list[str]:
    return [
        str(item.get("message") if isinstance(item, dict) else item)
        for item in precheck.get("blockers", [])
    ]


def generate_promotion_plan(
    db: Session,
    project_id: str,
    prompt: str,
    actor: str = "admin",
) -> dict[str, Any]:
    """Build one immutable, environment-scoped promotion plan without calling AI."""
    if not prompt or not prompt.strip():
        raise ValueError("A promotion prompt is required")
    if not db.get(MigrationProject, project_id):
        raise LookupError("Project not found")

    target = _target_environment(prompt)
    if not target:
        return {
            "status": "NEEDS_USER_INPUT",
            "prompt": prompt.strip(),
            "blockers": ["Specify exactly one target environment: TEST, UAT, or PROD."],
            "actionable_steps": ["Example: Promote the approved DEV release to TEST."],
        }
    source = PROMOTION_PATH[target]
    requested_source = _source_environment(prompt)
    if requested_source and requested_source != source:
        return {
            "status": "NEEDS_USER_INPUT",
            "prompt": prompt.strip(),
            "intent": {"source_environment": requested_source, "target_environment": target},
            "blockers": [
                f"{target} can only receive the governed release from {source}, not {requested_source}."
            ],
            "actionable_steps": [f"Complete and approve the {source} quality gate first."],
        }

    precheck_fn, _, _ = _services(target)
    precheck = precheck_fn(db, project_id, test_databricks=True)
    if not precheck.get("eligible"):
        return {
            "status": "NEEDS_USER_INPUT",
            "prompt": prompt.strip(),
            "intent": {"source_environment": source, "target_environment": target},
            "blockers": _blocker_messages(precheck),
            "actionable_steps": [
                f"Resolve the {source} gate, manifest, connectivity, or open-blocker evidence and generate the plan again."
            ],
            "precheck": precheck,
        }

    plan_id = uid("PRP")
    plan = {
        "plan_id": plan_id,
        "status": "PENDING_APPROVAL",
        "prompt": prompt.strip(),
        "actor": actor,
        "intent": {
            "source_environment": source,
            "target_environment": target,
            "target_catalog": _target_catalog(target),
            "single_environment_only": True,
            "ai_used": False,
        },
        "impact": {
            "artifact_count": int(precheck.get("artifact_count") or 0),
            "source_deployment_run_id": precheck.get("source_deployment_run_id"),
            "promotion_mode": "DEEP_CLONE_BRONZE_AND_REPLAY_APPROVED_SQL",
            "risk_level": "HIGH" if target == "PROD" else "MEDIUM",
            "requires_production_confirmation": target == "PROD",
        },
        "stages": [
            {"stage": "PREFLIGHT", "title": f"{target} promotion preflight"},
            {"stage": "DEPLOYMENT", "title": f"Promote {source} manifest to {target}"},
            {"stage": "RECONCILIATION", "title": f"Reconcile {target} objects"},
            {"stage": "QUALITY_GATE", "title": f"Evaluate {target} quality gate"},
        ],
        "precheck": precheck,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _record(
        db,
        project_id,
        target,
        record_type="PROMPT_PROMOTION_PLAN",
        status="PENDING_APPROVAL",
        run_id=plan_id,
        plan=plan,
    )
    return plan


def get_promotion_plan(
    db: Session, project_id: str, plan_id: str | None = None
) -> dict[str, Any] | None:
    records = db.scalars(
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "PROMPT_PROMOTION_PLAN",
        )
        .order_by(CanonicalRecord.created_at.desc())
    ).all()
    for record in records:
        payload = _payload(record.payload_json)
        plan = payload.get("plan") or {}
        if not plan_id or plan.get("plan_id") == plan_id:
            return plan
    return None


def _save_plan(db: Session, record: CanonicalRecord, plan: dict[str, Any]) -> None:
    record.payload_json = json.dumps(
        {"status": plan["status"], "run_id": plan["plan_id"], "plan": plan},
        default=str,
        sort_keys=True,
    )
    db.commit()


def execute_promotion_plan(
    db: Session,
    project_id: str,
    plan_id: str,
    actor: str = "admin",
    production_confirmed: bool = False,
) -> dict[str, Any]:
    records = db.scalars(
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "PROMPT_PROMOTION_PLAN",
        )
        .order_by(CanonicalRecord.created_at.desc())
    ).all()
    plan_record = next(
        (
            record
            for record in records
            if (_payload(record.payload_json).get("plan") or {}).get("plan_id") == plan_id
        ),
        None,
    )
    if not plan_record:
        raise LookupError(f"Promotion plan {plan_id} not found")
    plan = _payload(plan_record.payload_json).get("plan") or {}
    if plan.get("status") != "PENDING_APPROVAL":
        raise ValueError(f"Promotion plan cannot be executed in status {plan.get('status')}")

    intent = plan.get("intent") or {}
    target = str(intent.get("target_environment") or "").upper()
    source = PROMOTION_PATH.get(target)
    if not source:
        raise ValueError("Promotion plan has an invalid target environment")
    if target == "PROD" and not production_confirmed:
        raise PermissionError("Explicit production confirmation is required")

    precheck_fn, promote_fn, gate_fn = _services(target)
    run_id = uid("PRR")
    started_at = datetime.now(timezone.utc)
    plan.update({
        "status": "EXECUTING",
        "approved_by": actor,
        "approved_at": started_at.isoformat(),
        "run_id": run_id,
    })
    _save_plan(db, plan_record, plan)
    _record(
        db,
        project_id,
        target,
        record_type="PROMPT_PROMOTION_RUN",
        status="RUNNING",
        run_id=run_id,
        plan_id=plan_id,
        started_at=started_at.isoformat(),
    )

    result: dict[str, Any] = {
        "run_id": run_id,
        "plan_id": plan_id,
        "source_environment": source,
        "target_environment": target,
        "status": "RUNNING",
        "stages": {},
        "errors": [],
        "started_at": started_at.isoformat(),
    }
    current_stage = "PREFLIGHT"
    actions = {
        "PREFLIGHT": f"Resolve all {source} gate, manifest, connectivity, and blocker evidence, then generate a new {target} plan.",
        "DEPLOYMENT": f"Open Waves, inspect the {target} deployment evidence, and retry after correcting the failed target.",
        "RECONCILIATION": f"Open Waves and inspect the {target} reconciliation details before retrying.",
        "QUALITY_GATE": f"Resolve the listed {target} quality-gate blockers before continuing.",
    }
    try:
        precheck = precheck_fn(db, project_id, test_databricks=True)
        result["stages"]["PREFLIGHT"] = {
            "status": "PASSED" if precheck.get("eligible") else "FAILED",
            "artifact_count": precheck.get("artifact_count", 0),
            "source_deployment_run_id": precheck.get("source_deployment_run_id"),
            "blockers": _blocker_messages(precheck),
        }
        if not precheck.get("eligible"):
            raise RuntimeError("; ".join(_blocker_messages(precheck)) or "Promotion preflight failed")
        if precheck.get("source_deployment_run_id") != plan.get("impact", {}).get("source_deployment_run_id"):
            raise RuntimeError(
                "The source deployment manifest changed after plan approval; generate a new promotion plan."
            )

        current_stage = "DEPLOYMENT"
        promoted = promote_fn(db, project_id)
        result["stages"]["DEPLOYMENT"] = {
            "status": promoted.get("status", "FAILED"),
            "deployment_run_id": promoted.get("run_id"),
            "source_deployment_run_id": promoted.get("source_run_id"),
            "deployed_count": promoted.get("count", len(promoted.get("deployed", []))),
            "failed_target": promoted.get("failed_target"),
        }
        if promoted.get("status") != "PASSED":
            raise RuntimeError(promoted.get("error") or f"{target} deployment failed")

        current_stage = "RECONCILIATION"
        reconciliation = deployment.run_reconciliation(
            db, project_id, target, actor=actor
        )
        result["stages"]["RECONCILIATION"] = {
            "status": reconciliation.get("status", "FAILED"),
            "deployment_run_id": reconciliation.get("run_id"),
            "passed": reconciliation.get("passed", 0),
            "failed": reconciliation.get("failed", 0),
        }
        if reconciliation.get("status") != "PASSED":
            raise RuntimeError(
                f"{target} reconciliation failed for {reconciliation.get('failed', 0)} object(s)"
            )

        current_stage = "QUALITY_GATE"
        gate = gate_fn(db, project_id)
        result["stages"]["QUALITY_GATE"] = {
            "status": gate.get("status", "BLOCKED"),
            "gate_id": gate.get("gate_id"),
            "deployment_run_id": gate.get("deployment_run_id"),
            "blockers": gate.get("blockers", []),
        }
        if gate.get("status") != "PASSED":
            raise RuntimeError("; ".join(gate.get("blockers", [])) or f"{target} quality gate is blocked")

        ended_at = datetime.now(timezone.utc)
        result.update({"status": "COMPLETED", "ended_at": ended_at.isoformat()})
        plan.update({"status": "COMPLETED", "ended_at": ended_at.isoformat()})
        _save_plan(db, plan_record, plan)
        _record(
            db,
            project_id,
            target,
            record_type="PROMPT_PROMOTION_RUN",
            status="COMPLETED",
            run_id=run_id,
            plan_id=plan_id,
            results=result,
        )
    except Exception as exc:
        ended_at = datetime.now(timezone.utc)
        failed_stage = result["stages"].setdefault(current_stage, {})
        failed_stage.update({"status": "FAILED", "error": str(exc)})
        error = {
            "stage": current_stage,
            "message": str(exc),
            "recommended_action": actions[current_stage],
        }
        result.update({
            "status": "FAILED",
            "failed_stage": current_stage,
            "error": str(exc),
            "errors": [error],
            "ended_at": ended_at.isoformat(),
        })
        plan.update({
            "status": "FAILED",
            "failed_stage": current_stage,
            "error": str(exc),
            "ended_at": ended_at.isoformat(),
        })
        _save_plan(db, plan_record, plan)
        _record(
            db,
            project_id,
            target,
            record_type="PROMPT_PROMOTION_RUN",
            status="FAILED",
            run_id=run_id,
            plan_id=plan_id,
            error=str(exc),
            results=result,
        )
    return result


def latest_promotion_execution(db: Session, project_id: str) -> dict[str, Any] | None:
    records = db.scalars(
        select(CanonicalRecord)
        .where(
            CanonicalRecord.project_id == project_id,
            CanonicalRecord.record_type == "PROMPT_PROMOTION_RUN",
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
