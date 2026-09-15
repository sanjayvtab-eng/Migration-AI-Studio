import pytest

from app.models.entities import CanonicalRecord
from app.services import master_orchestration
from app.services.engine import add_source, ensure_project


MASTER_PROMPT = (
    "Migrate MigrationDemo from SQL Server through DEV, TEST, UAT, and PROD Databricks"
)


def _project(db, name="Release 6 master workflow"):
    project = ensure_project(db, name)
    add_source(db, project.id, "SQL Server", "localhost", "MigrationDemo")
    return project


def _mock_dev_plan(monkeypatch):
    dev_plan = {
        "plan_id": "DEV_PLAN_1",
        "status": "PENDING_APPROVAL",
        "impact": {"table_count": 6, "estimated_rows": 32, "requires_overwrite": False},
    }
    monkeypatch.setattr(
        master_orchestration.prompt_orchestration,
        "generate_prompt_plan",
        lambda *a, **kw: dict(dev_plan),
    )
    monkeypatch.setattr(
        master_orchestration.prompt_orchestration,
        "get_prompt_plan",
        lambda *a, **kw: dict(dev_plan),
    )
    return dev_plan


def _mock_successful_chain(monkeypatch, calls):
    monkeypatch.setattr(
        master_orchestration.prompt_orchestration,
        "execute_prompt_plan",
        lambda *a, **kw: calls.append("DEV") or {"status": "COMPLETED", "run_id": "DEV_RUN"},
    )

    def promotion_plan(*args, **kwargs):
        prompt = kwargs.get("prompt") or args[2]
        target = prompt.rsplit(" ", 1)[-1]
        calls.append(f"PLAN_{target}")
        return {"status": "PENDING_APPROVAL", "plan_id": f"PLAN_{target}"}

    def promotion_execute(*args, **kwargs):
        target = kwargs["plan_id"].replace("PLAN_", "")
        calls.append(target)
        return {"status": "COMPLETED", "run_id": f"RUN_{target}"}

    monkeypatch.setattr(
        master_orchestration.prompt_promotion, "generate_promotion_plan", promotion_plan
    )
    monkeypatch.setattr(
        master_orchestration.prompt_promotion, "execute_promotion_plan", promotion_execute
    )


def test_master_plan_requires_explicit_full_production_scope(db):
    project = _project(db)

    result = master_orchestration.generate_master_plan(
        db, project.id, "Migrate MigrationDemo from SQL Server to DEV Databricks"
    )

    assert result["status"] == "NEEDS_USER_INPUT"
    assert "Production scope must be explicit" in result["blockers"][0]


def test_master_plan_contains_one_authorization_and_four_checkpoints(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)

    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)

    assert plan["status"] == "PENDING_APPROVAL"
    assert plan["scope"]["single_prompt"] is True
    assert plan["scope"]["environments"] == ["DEV", "TEST", "UAT", "PROD"]
    assert plan["authorization"] is None
    assert list(plan["checkpoints"]) == [
        "DEV_MIGRATION", "TEST_PROMOTION", "UAT_PROMOTION", "PROD_PROMOTION"
    ]
    assert db.query(CanonicalRecord).filter_by(
        project_id=project.id, record_type="MASTER_MIGRATION_PLAN"
    ).count() == 1


def test_master_execution_requires_workflow_and_prod_authorization(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)

    with pytest.raises(PermissionError, match="complete workflow"):
        master_orchestration.execute_master_plan(db, project.id, plan["plan_id"])
    with pytest.raises(PermissionError, match="PROD authorization"):
        master_orchestration.execute_master_plan(
            db, project.id, plan["plan_id"], workflow_authorized=True
        )


def test_master_execution_runs_dev_test_uat_prod_in_order(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    calls = []
    _mock_successful_chain(monkeypatch, calls)
    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)

    result = master_orchestration.execute_master_plan(
        db,
        project.id,
        plan["plan_id"],
        actor="release-admin",
        workflow_authorized=True,
        production_authorized=True,
    )

    assert result["status"] == "COMPLETED", result.get("error")
    assert calls == [
        "DEV", "PLAN_TEST", "TEST", "PLAN_UAT", "UAT", "PLAN_PROD", "PROD"
    ]
    assert all(stage["status"] == "PASSED" for stage in result["stages"].values())
    assert result["authorization"]["authorized_by"] == "release-admin"
    assert master_orchestration.get_master_plan(db, project.id)["status"] == "COMPLETED"


def test_master_resume_reuses_passed_checkpoints(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    calls = []
    monkeypatch.setattr(
        master_orchestration.prompt_orchestration,
        "execute_prompt_plan",
        lambda *a, **kw: calls.append("DEV") or {"status": "COMPLETED"},
    )
    monkeypatch.setattr(
        master_orchestration.prompt_promotion,
        "generate_promotion_plan",
        lambda *a, **kw: {
            "status": "PENDING_APPROVAL",
            "plan_id": "PLAN_" + (kw.get("prompt") or a[2]).rsplit(" ", 1)[-1],
        },
    )
    uat_attempts = {"count": 0}

    def execute(*args, **kwargs):
        target = kwargs["plan_id"].replace("PLAN_", "")
        calls.append(target)
        if target == "UAT":
            uat_attempts["count"] += 1
            if uat_attempts["count"] == 1:
                return {
                    "status": "FAILED", "error": "UAT reconciliation mismatch",
                    "errors": [{"recommended_action": "Correct UAT reconciliation and resume."}],
                }
        return {"status": "COMPLETED"}

    monkeypatch.setattr(
        master_orchestration.prompt_promotion, "execute_promotion_plan", execute
    )
    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)

    first = master_orchestration.execute_master_plan(
        db, project.id, plan["plan_id"], workflow_authorized=True, production_authorized=True
    )
    resumed = master_orchestration.execute_master_plan(db, project.id, plan["plan_id"])

    assert first["status"] == "FAILED"
    assert first["failed_stage"] == "UAT_PROMOTION"
    assert resumed["status"] == "COMPLETED"
    assert resumed["stages"]["DEV_MIGRATION"]["checkpoint_reused"] is True
    assert resumed["stages"]["TEST_PROMOTION"]["checkpoint_reused"] is True
    assert calls == ["DEV", "TEST", "UAT", "UAT", "PROD"]


def test_master_migration_api_workflow(client, auth_headers, db, monkeypatch):
    project = client.post(
        "/api/projects", headers=auth_headers, json={"name": "Release 6 API"}
    ).json()
    add_source(db, project["id"], "SQL Server", "localhost", "MigrationDemo")
    _mock_dev_plan(monkeypatch)
    calls = []
    _mock_successful_chain(monkeypatch, calls)

    planned = client.post(
        f"/api/projects/{project['id']}/master-migration/plan",
        headers=auth_headers,
        json={"prompt": MASTER_PROMPT},
    )
    assert planned.status_code == 200, planned.text

    executed = client.post(
        f"/api/projects/{project['id']}/master-migration/execute",
        headers=auth_headers,
        json={
            "plan_id": planned.json()["plan_id"],
            "workflow_authorized": True,
            "production_authorized": True,
        },
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "COMPLETED"

    latest = client.get(
        f"/api/projects/{project['id']}/master-migration/latest",
        headers=auth_headers,
    )
    assert latest.status_code == 200
    assert latest.json()["plan"]["status"] == "COMPLETED"
    assert latest.json()["execution"]["status"] == "COMPLETED"
