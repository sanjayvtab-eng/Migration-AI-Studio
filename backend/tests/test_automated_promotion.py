import json
import pytest
from unittest.mock import MagicMock

from app.models.entities import CanonicalRecord, MigrationProject
from app.services import master_orchestration, deployment
from app.services.engine import ensure_project, uid


def _setup_dev_passed(db, monkeypatch, project_name="Automated Promotion Test"):
    project = ensure_project(db, project_name)
    dev_run_id = uid("MDR")

    dep1 = MagicMock(object_id="OBJ_1")
    dep2 = MagicMock(object_id="OBJ_2")
    manifest_items = [
        (dep1, {
            "target_fqn": "sqlmigration_dev.bronze.customers",
            "layer": "BRONZE",
            "artifact_version_id": "VER_1",
            "artifact_version": 1,
            "artifact_content_hash": "hash_1",
        }),
        (dep2, {
            "target_fqn": "sqlmigration_dev.silver.vw_customers",
            "layer": "SILVER",
            "artifact_version_id": "VER_2",
            "artifact_version": 1,
            "artifact_content_hash": "hash_2",
        }),
    ]

    monkeypatch.setattr(
        master_orchestration.deployment,
        "_latest_successful_medallion_run",
        lambda db, pid, env: (dev_run_id, manifest_items) if env == "DEV" else None,
    )

    # DEV gate
    gate = CanonicalRecord(
        id=uid("REC"),
        project_id=project.id,
        environment="DEV",
        record_type="QUALITY_GATE",
        payload_json=json.dumps({"status": "PASSED", "gate_id": uid("GAT"), "blockers": []}),
    )
    db.add(gate)

    # DEV reconciliation
    recon = CanonicalRecord(
        id=uid("REC"),
        project_id=project.id,
        environment="DEV",
        record_type="RECONCILIATION",
        payload_json=json.dumps({"status": "PASSED", "passed": 2, "failed": 0}),
    )
    db.add(recon)
    db.commit()
    return project, dev_run_id


def test_authorize_requires_exact_confirmation(db, monkeypatch):
    project, dev_run = _setup_dev_passed(db, monkeypatch, "Test Exact Confirmation")

    monkeypatch.setattr(
        master_orchestration.deployment,
        "test_promotion_precheck",
        lambda *a, **kw: {"eligible": True, "blockers": []},
    )

    # Rejection of wrong confirmation
    for bad_text in ["", "promote", "PROMOTE", "PROMOTE TO PRODUCTION", "yes"]:
        with pytest.raises(ValueError, match="Explicit confirmation 'PROMOTE TO PROD' is required"):
            master_orchestration.authorize_automated_promotion(db, project.id, confirmation_text=bad_text)

    # Acceptance of exact confirmation
    monkeypatch.setattr(
        master_orchestration,
        "run_automated_promotion",
        lambda db, pid, run_id, **kw: {"run_id": run_id, "status": "RUNNING"},
    )
    res = master_orchestration.authorize_automated_promotion(db, project.id, confirmation_text="PROMOTE TO PROD")
    assert res["status"] == "RUNNING"


def test_preflight_blocks_when_dev_not_passed(db, monkeypatch):
    project = ensure_project(db, "Test Unpassed DEV")

    pre = master_orchestration.get_automated_promotion_preflight(db, project.id)
    assert pre["eligible"] is False
    assert any("DEV deployment" in b for b in pre["blockers"])

    with pytest.raises(ValueError, match="Automated promotion preflight blocked"):
        master_orchestration.authorize_automated_promotion(db, project.id, confirmation_text="PROMOTE TO PROD")


def test_full_automated_promotion_sequence(db, monkeypatch):
    project, dev_run = _setup_dev_passed(db, monkeypatch, "Test Full Promotion")

    calls = []
    monkeypatch.setattr(master_orchestration.deployment, "test_promotion_precheck", lambda *a, **kw: calls.append("TEST_PRECHECK") or {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_test", lambda *a, **kw: calls.append("TEST_PROMOTE") or {"status": "PASSED", "run_id": "RUN_TEST", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "run_reconciliation", lambda db, pid, env, **kw: calls.append(f"{env}_RECON") or {"status": "PASSED", "run_id": f"REC_{env}", "passed": 2, "failed": 0})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_test_gate", lambda *a, **kw: calls.append("TEST_GATE") or {"status": "PASSED", "gate_id": "GAT_TEST"})

    monkeypatch.setattr(master_orchestration.deployment, "uat_promotion_precheck", lambda *a, **kw: calls.append("UAT_PRECHECK") or {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_uat", lambda *a, **kw: calls.append("UAT_PROMOTE") or {"status": "PASSED", "run_id": "RUN_UAT", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_uat_gate", lambda *a, **kw: calls.append("UAT_GATE") or {"status": "PASSED", "gate_id": "GAT_UAT"})

    monkeypatch.setattr(master_orchestration.deployment, "prod_promotion_precheck", lambda *a, **kw: calls.append("PROD_PRECHECK") or {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_prod", lambda *a, **kw: calls.append("PROD_PROMOTE") or {"status": "PASSED", "run_id": "RUN_PROD", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_prod_gate", lambda *a, **kw: calls.append("PROD_GATE") or {"status": "PASSED", "gate_id": "GAT_PROD"})

    result = master_orchestration.authorize_automated_promotion(db, project.id, confirmation_text="PROMOTE TO PROD")

    assert result["status"] == "COMPLETED"
    assert result["state"] == "COMPLETED"
    assert result["environments"]["TEST"]["status"] == "PASSED"
    assert result["environments"]["UAT"]["status"] == "PASSED"
    assert result["environments"]["PROD"]["status"] == "PASSED"
    assert result["last_successful_checkpoint"] == "PROD_PASSED"

    expected_calls = [
        "TEST_PRECHECK", "TEST_PROMOTE", "TEST_RECON", "TEST_GATE",
        "UAT_PRECHECK", "UAT_PROMOTE", "UAT_RECON", "UAT_GATE",
        "PROD_PRECHECK", "PROD_PROMOTE", "PROD_RECON", "PROD_GATE",
    ]
    for exp in expected_calls:
        assert exp in calls


def test_test_failure_blocks_uat_and_prod(db, monkeypatch):
    project, dev_run = _setup_dev_passed(db, monkeypatch, "Test Failure Blocking")

    monkeypatch.setattr(master_orchestration.deployment, "test_promotion_precheck", lambda *a, **kw: {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_test", lambda *a, **kw: {"status": "FAILED", "error": "Databricks cluster timeout"})

    result = master_orchestration.authorize_automated_promotion(db, project.id, confirmation_text="PROMOTE TO PROD")

    assert result["status"] == "FAILED"
    assert result["state"] == "FAILED"
    assert result["is_resumable"] is True
    assert result["environments"]["TEST"]["status"] == "FAILED"
    assert result["environments"]["UAT"]["status"] == "PENDING"
    assert result["environments"]["PROD"]["status"] == "PENDING"


def test_pause_and_resume_execution(db, monkeypatch):
    project, dev_run = _setup_dev_passed(db, monkeypatch, "Test Pause and Resume")

    monkeypatch.setattr(master_orchestration.deployment, "test_promotion_precheck", lambda *a, **kw: {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_test", lambda *a, **kw: {"status": "PASSED", "run_id": "RUN_TEST", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "run_reconciliation", lambda db, pid, env, **kw: {"status": "PASSED", "run_id": f"REC_{env}", "passed": 2, "failed": 0})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_test_gate", lambda *a, **kw: {"status": "PASSED", "gate_id": "GAT_TEST"})

    # Setup pause right after TEST gate
    original_save = master_orchestration._save_automated_run
    def pause_on_test_passed(db, rec, run):
        if run.get("state") == "TEST_PASSED":
            run["pause_requested"] = True
        original_save(db, rec, run)

    monkeypatch.setattr(master_orchestration, "_save_automated_run", pause_on_test_passed)

    result = master_orchestration.authorize_automated_promotion(db, project.id, confirmation_text="PROMOTE TO PROD")
    assert result["status"] == "PAUSED"
    assert result["state"] == "PAUSED"
    assert result["is_resumable"] is True
    assert result["environments"]["TEST"]["status"] == "PASSED"
    assert result["environments"]["UAT"]["status"] == "PENDING"

    # Now Resume
    monkeypatch.setattr(master_orchestration, "_save_automated_run", original_save)
    monkeypatch.setattr(master_orchestration.deployment, "uat_promotion_precheck", lambda *a, **kw: {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_uat", lambda *a, **kw: {"status": "PASSED", "run_id": "RUN_UAT", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_uat_gate", lambda *a, **kw: {"status": "PASSED", "gate_id": "GAT_UAT"})
    monkeypatch.setattr(master_orchestration.deployment, "prod_promotion_precheck", lambda *a, **kw: {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_prod", lambda *a, **kw: {"status": "PASSED", "run_id": "RUN_PROD", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_prod_gate", lambda *a, **kw: {"status": "PASSED", "gate_id": "GAT_PROD"})

    resumed = master_orchestration.resume_automated_promotion(db, project.id, result["run_id"])
    assert resumed["status"] == "COMPLETED"
    assert resumed["environments"]["UAT"]["status"] == "PASSED"
    assert resumed["environments"]["PROD"]["status"] == "PASSED"


def test_cancel_retains_successful_environments(db, monkeypatch):
    project, dev_run = _setup_dev_passed(db, monkeypatch, "Test Cancel Retain")

    monkeypatch.setattr(master_orchestration.deployment, "test_promotion_precheck", lambda *a, **kw: {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_test", lambda *a, **kw: {"status": "PASSED", "run_id": "RUN_TEST", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "run_reconciliation", lambda db, pid, env, **kw: {"status": "PASSED", "run_id": f"REC_{env}", "passed": 2, "failed": 0})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_test_gate", lambda *a, **kw: {"status": "PASSED", "gate_id": "GAT_TEST"})

    # Fail in UAT
    monkeypatch.setattr(master_orchestration.deployment, "uat_promotion_precheck", lambda *a, **kw: {"eligible": False, "blockers": ["Missing approval"]})

    result = master_orchestration.authorize_automated_promotion(db, project.id, confirmation_text="PROMOTE TO PROD")
    assert result["status"] == "FAILED"
    assert result["environments"]["TEST"]["status"] == "PASSED"

    cancelled = master_orchestration.cancel_automated_promotion(db, project.id, result["run_id"])
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["environments"]["TEST"]["status"] == "PASSED"
    assert cancelled["environments"]["UAT"]["status"] == "CANCELLED"
    assert cancelled["environments"]["PROD"]["status"] == "CANCELLED"


def test_api_routes_for_master_orchestration(db, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.security import create_access_token

    project, dev_run = _setup_dev_passed(db, monkeypatch, "Test API Routes Project")
    monkeypatch.setattr(master_orchestration.deployment, "test_promotion_precheck", lambda *a, **kw: {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_test", lambda *a, **kw: {"status": "PASSED", "run_id": "RUN_TEST", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "run_reconciliation", lambda db, pid, env, **kw: {"status": "PASSED", "run_id": f"REC_{env}", "passed": 2, "failed": 0})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_test_gate", lambda *a, **kw: {"status": "PASSED", "gate_id": "GAT_TEST"})
    monkeypatch.setattr(master_orchestration.deployment, "uat_promotion_precheck", lambda *a, **kw: {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_uat", lambda *a, **kw: {"status": "PASSED", "run_id": "RUN_UAT", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_uat_gate", lambda *a, **kw: {"status": "PASSED", "gate_id": "GAT_UAT"})
    monkeypatch.setattr(master_orchestration.deployment, "prod_promotion_precheck", lambda *a, **kw: {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_prod", lambda *a, **kw: {"status": "PASSED", "run_id": "RUN_PROD", "count": 2})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_prod_gate", lambda *a, **kw: {"status": "PASSED", "gate_id": "GAT_PROD"})

    client = TestClient(app)
    token = create_access_token("admin", "admin")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET status
    res = client.get(f"/api/projects/{project.id}/master-orchestration/current", headers=headers)
    assert res.status_code == 200
    assert res.json()["preflight"]["eligible"] is True
    assert res.json()["preflight"]["artifact_count"] == 2

    # 2. POST authorize with bad confirmation
    res = client.post(
        f"/api/projects/{project.id}/master-orchestration/authorize",
        headers=headers,
        json={"confirmation_text": "wrong"},
    )
    assert res.status_code in {400, 500}

    # 3. POST authorize with exact confirmation
    res = client.post(
        f"/api/projects/{project.id}/master-orchestration/authorize",
        headers=headers,
        json={"confirmation_text": "PROMOTE TO PROD"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "COMPLETED"


def test_stale_artifact_version_blocks_promotion(db, monkeypatch):
    project, dev_run = _setup_dev_passed(db, monkeypatch, "Test Stale Artifact")

    monkeypatch.setattr(
        master_orchestration.deployment,
        "test_promotion_precheck",
        lambda *a, **kw: {"eligible": True, "artifact_count": 2, "source_deployment_run_id": dev_run},
    )
    real_run = master_orchestration.run_automated_promotion
    monkeypatch.setattr(
        master_orchestration,
        "run_automated_promotion",
        lambda db, pid, run_id, **kw: {"run_id": run_id, "status": "AUTHORIZED"},
    )
    res = master_orchestration.authorize_automated_promotion(db, project.id, confirmation_text="PROMOTE TO PROD")
    run_id = res["run_id"]

    # Now mutate manifest versions before runner executes
    dep1 = MagicMock(object_id="OBJ_1")
    dep2 = MagicMock(object_id="OBJ_2")
    mutated_items = [
        (dep1, {
            "target_fqn": "sqlmigration_dev.bronze.customers",
            "layer": "BRONZE",
            "artifact_version_id": "STALE_VERSION_CHANGED",
            "artifact_version": 2,
            "artifact_content_hash": "hash_different",
        }),
    ]
    monkeypatch.setattr(
        master_orchestration.deployment,
        "_latest_successful_medallion_run",
        lambda db, pid, env: (dev_run, mutated_items) if env == "DEV" else None,
    )

    failed_run = real_run(db, project.id, run_id)
    assert failed_run["status"] == "FAILED"
    assert any("version changed" in err["message"] or "missing" in err["message"] for err in failed_run.get("errors", []))


def test_execute_promoted_sql_splits_multi_statement_batches(monkeypatch):
    from app.services.deployment import _execute_promoted_sql

    executed = []
    monkeypatch.setattr("app.services.deployment.execute_sql", lambda sql, safe_retry=False: executed.append(sql))

    # Multi-statement SQL with bootstrap CREATE TABLE and idempotent MERGE
    sql = """
    CREATE TABLE IF NOT EXISTS `sqlmigration_test`.`silver`.`customer_sales_summary` USING DELTA AS
    SELECT * FROM (SELECT 1 AS id) WHERE 1 = 0;
    MERGE INTO `sqlmigration_test`.`silver`.`customer_sales_summary` target
    USING (SELECT 1 AS id) source
    ON target.id = source.id
    WHEN MATCHED THEN UPDATE SET target.id = source.id
    WHEN NOT MATCHED THEN INSERT (id) VALUES (source.id);
    """

    _execute_promoted_sql(sql)

    assert len(executed) == 2
    assert executed[0].startswith("CREATE TABLE IF NOT EXISTS")
    assert executed[0].endswith(";")
    assert executed[1].startswith("MERGE INTO")
    assert executed[1].endswith(";")
