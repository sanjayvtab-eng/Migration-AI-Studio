import pytest

from app.models.entities import CanonicalRecord
from app.services import prompt_promotion
from app.services.engine import ensure_project


def _eligible(source="DEV", target="TEST", run_id="RUN_SOURCE_1", count=6):
    return {
        "eligible": True,
        "source_environment": source,
        "target_environment": target,
        "artifact_count": count,
        "source_deployment_run_id": run_id,
        "blockers": [],
        "databricks": {"tested": True, "ok": True},
    }


def test_promotion_prompt_requires_exactly_one_target(db):
    project = ensure_project(db, "Release 5 target validation")

    result = prompt_promotion.generate_promotion_plan(
        db, project.id, "Promote the migration"
    )

    assert result["status"] == "NEEDS_USER_INPUT"
    assert "TEST, UAT, or PROD" in result["blockers"][0]


def test_promotion_prompt_rejects_multi_environment_chain(db):
    project = ensure_project(db, "Release 5 chain rejection")

    result = prompt_promotion.generate_promotion_plan(
        db, project.id, "Promote DEV to TEST and then UAT and PROD"
    )

    assert result["status"] == "NEEDS_USER_INPUT"
    assert "exactly one target environment" in result["blockers"][0]


def test_promotion_prompt_enforces_sequential_source(db):
    project = ensure_project(db, "Release 5 sequential validation")

    result = prompt_promotion.generate_promotion_plan(
        db, project.id, "Promote from DEV to UAT"
    )

    assert result["status"] == "NEEDS_USER_INPUT"
    assert "UAT can only receive" in result["blockers"][0]


def test_promotion_plan_returns_precheck_blockers(db, monkeypatch):
    project = ensure_project(db, "Release 5 blocked plan")
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "test_promotion_precheck",
        lambda *a, **kw: {
            "eligible": False,
            "source_deployment_run_id": None,
            "artifact_count": 0,
            "blockers": [{"code": "DEV_GATE", "message": "Latest DEV quality gate is not PASSED."}],
        },
    )

    result = prompt_promotion.generate_promotion_plan(
        db, project.id, "Promote approved DEV release to TEST"
    )

    assert result["status"] == "NEEDS_USER_INPUT"
    assert result["blockers"] == ["Latest DEV quality gate is not PASSED."]


def test_promotion_plan_is_single_environment_and_immutable(db, monkeypatch):
    project = ensure_project(db, "Release 5 governed plan")
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "uat_promotion_precheck",
        lambda *a, **kw: _eligible("TEST", "UAT", "RUN_TEST_1", 9),
    )

    plan = prompt_promotion.generate_promotion_plan(
        db, project.id, "Promote the approved TEST release to UAT", actor="architect"
    )

    assert plan["status"] == "PENDING_APPROVAL"
    assert plan["intent"]["source_environment"] == "TEST"
    assert plan["intent"]["target_environment"] == "UAT"
    assert plan["intent"]["single_environment_only"] is True
    assert plan["intent"]["ai_used"] is False
    assert plan["impact"]["artifact_count"] == 9
    assert plan["impact"]["source_deployment_run_id"] == "RUN_TEST_1"
    assert len(plan["stages"]) == 4
    assert db.query(CanonicalRecord).filter_by(
        project_id=project.id, record_type="PROMPT_PROMOTION_PLAN"
    ).count() == 1


def test_prod_execution_requires_explicit_confirmation(db, monkeypatch):
    project = ensure_project(db, "Release 5 PROD confirmation")
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "prod_promotion_precheck",
        lambda *a, **kw: _eligible("UAT", "PROD", "RUN_UAT_1", 4),
    )
    plan = prompt_promotion.generate_promotion_plan(
        db, project.id, "Promote approved UAT release to PROD"
    )

    with pytest.raises(PermissionError, match="production confirmation"):
        prompt_promotion.execute_promotion_plan(db, project.id, plan["plan_id"])

    stored = prompt_promotion.get_promotion_plan(db, project.id, plan["plan_id"])
    assert stored["status"] == "PENDING_APPROVAL"


def test_execute_promotion_runs_preflight_deploy_reconcile_and_gate(db, monkeypatch):
    project = ensure_project(db, "Release 5 TEST execution")
    precheck = lambda *a, **kw: _eligible("DEV", "TEST", "RUN_DEV_1", 6)
    monkeypatch.setattr(prompt_promotion.deployment, "test_promotion_precheck", precheck)
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "promote_medallion_to_test",
        lambda *a, **kw: {
            "status": "PASSED", "run_id": "RUN_TEST_1", "source_run_id": "RUN_DEV_1",
            "count": 6, "deployed": [],
        },
    )
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "run_reconciliation",
        lambda *a, **kw: {"status": "PASSED", "run_id": "RUN_TEST_1", "passed": 6, "failed": 0},
    )
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "evaluate_test_gate",
        lambda *a, **kw: {
            "status": "PASSED", "gate_id": "GATE_TEST_1",
            "deployment_run_id": "RUN_TEST_1", "blockers": [],
        },
    )
    plan = prompt_promotion.generate_promotion_plan(
        db, project.id, "Promote approved DEV release to TEST"
    )

    result = prompt_promotion.execute_promotion_plan(
        db, project.id, plan["plan_id"], actor="release-manager"
    )

    assert result["status"] == "COMPLETED"
    assert list(result["stages"]) == ["PREFLIGHT", "DEPLOYMENT", "RECONCILIATION", "QUALITY_GATE"]
    assert all(stage["status"] == "PASSED" for stage in result["stages"].values())
    assert prompt_promotion.get_promotion_plan(db, project.id, plan["plan_id"])["status"] == "COMPLETED"


def test_execute_promotion_stops_if_manifest_changes_after_plan(db, monkeypatch):
    project = ensure_project(db, "Release 5 manifest drift")
    state = {"run_id": "RUN_DEV_1"}
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "test_promotion_precheck",
        lambda *a, **kw: _eligible("DEV", "TEST", state["run_id"], 6),
    )
    plan = prompt_promotion.generate_promotion_plan(
        db, project.id, "Promote approved DEV release to TEST"
    )
    state["run_id"] = "RUN_DEV_2"

    result = prompt_promotion.execute_promotion_plan(db, project.id, plan["plan_id"])

    assert result["status"] == "FAILED"
    assert result["failed_stage"] == "PREFLIGHT"
    assert "manifest changed" in result["error"]


def test_prompt_promotion_api_workflow(client, auth_headers, db, monkeypatch):
    project = client.post(
        "/api/projects", headers=auth_headers, json={"name": "Release 5 API"}
    ).json()
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "test_promotion_precheck",
        lambda *a, **kw: _eligible("DEV", "TEST", "RUN_DEV_API", 3),
    )
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "promote_medallion_to_test",
        lambda *a, **kw: {
            "status": "PASSED", "run_id": "RUN_TEST_API",
            "source_run_id": "RUN_DEV_API", "count": 3,
        },
    )
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "run_reconciliation",
        lambda *a, **kw: {"status": "PASSED", "run_id": "RUN_TEST_API", "passed": 3, "failed": 0},
    )
    monkeypatch.setattr(
        prompt_promotion.deployment,
        "evaluate_test_gate",
        lambda *a, **kw: {
            "status": "PASSED", "gate_id": "GATE_TEST_API",
            "deployment_run_id": "RUN_TEST_API", "blockers": [],
        },
    )

    planned = client.post(
        f"/api/projects/{project['id']}/prompt-promotion/plan",
        headers=auth_headers,
        json={"prompt": "Promote approved DEV release to TEST"},
    )
    assert planned.status_code == 200, planned.text
    assert planned.json()["status"] == "PENDING_APPROVAL"

    executed = client.post(
        f"/api/projects/{project['id']}/prompt-promotion/execute",
        headers=auth_headers,
        json={"plan_id": planned.json()["plan_id"]},
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "COMPLETED"

    latest = client.get(
        f"/api/projects/{project['id']}/prompt-promotion/latest",
        headers=auth_headers,
    )
    assert latest.status_code == 200
    assert latest.json()["execution"]["target_environment"] == "TEST"
