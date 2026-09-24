import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.canonical import MigrationDeployment
from app.models.entities import (CanonicalRecord, MigrationDatabricksConfiguration,
                                 MigrationMedallionNode, MigrationRun,
                                 MigrationStageArtifactVersion)
from app.services import bronze_ingestion, databricks_client, deployment, environment_provisioning, medallion
from app.services.engine import ensure_project, uid
from test_bronze_ingestion import _seed


SCHEMA = [("CustomerId", "int"), ("CustomerName", "string"),
          ("_migration_ingested_at", "timestamp"), ("_migration_source_system", "string")]


def _completed_ingestion(db, project, table):
    run = MigrationRun(id=uid("BRI"), project_id=project.id, stage="DEV_BRONZE_INGESTION",
                       environment="DEV", status="PASSED")
    db.add(run)
    db.add(CanonicalRecord(id=uid("REC"), project_id=project.id, object_id=table.id,
                           environment="DEV", record_type="BRONZE_INGESTION",
                           payload_json=json.dumps({
                               "action": "TABLE_INGESTED", "status": "PASSED", "run_id": run.id,
                               "source": "dbo.Customers",
                               "target_fqn": "`migration_dev`.`bronze`.`Customers`",
                               "rows_loaded": 5, "target_rows": 5, "source_hash": table.source_hash,
                               "workspace_host": "dbc-example.cloud.databricks.com",
                           })))
    db.commit()
    return run


def _approved_medallion(db, project):
    medallion.build_medallion_plan(db, project.id, environment="DEV", catalog="migration_dev")
    medallion.generate_medallion_artifacts(db, project.id, environment="DEV")
    for version in db.query(MigrationStageArtifactVersion).filter_by(project_id=project.id):
        assert version.validation_status == "PASSED"
        version.review_status = "APPROVED"
    db.commit()


@pytest.mark.parametrize("changed", [None, "source_count", "target_count", "schema", "workspace", "source_hash"])
def test_checkpoint_rechecks_live_source_target_and_schema(db, monkeypatch, changed):
    project, _, table = _seed(db)
    _completed_ingestion(db, project, table)
    monkeypatch.setattr(bronze_ingestion, "_source_count", lambda *a: 6 if changed == "source_count" else 5)
    monkeypatch.setattr(bronze_ingestion, "_target_count", lambda *a: 4 if changed == "target_count" else 5)
    execute = Mock(return_value=SCHEMA[:-1] if changed == "schema" else SCHEMA)
    monkeypatch.setattr(environment_provisioning, "project_execute", execute)
    if changed == "workspace":
        environment_provisioning.get_configuration(db, project.id).workspace_host = "another.cloud.databricks.com"
    if changed == "source_hash":
        table.source_hash = "different-discovery-hash"
    db.commit()

    result = bronze_ingestion.verified_checkpoint(db, project.id, [table])

    assert bool(result) == (changed is None)
    assert all(call.args[2].startswith("DESCRIBE TABLE") for call in execute.call_args_list)


def test_checkpoint_reuses_matching_approved_canonical_target(db, monkeypatch):
    project, _, table = _seed(db)
    run = _completed_ingestion(db, project, table)
    table.object_name = "CustomerSales"
    record = db.scalar(select(CanonicalRecord).where(
        CanonicalRecord.project_id == project.id,
        CanonicalRecord.object_id == table.id,
        CanonicalRecord.record_type == "BRONZE_INGESTION",
    ))
    payload = json.loads(record.payload_json)
    payload["source"] = "dbo.CustomerSales"
    payload["target_fqn"] = "`migration_dev`.`bronze`.`customer_sales`"
    record.payload_json = json.dumps(payload)
    db.commit()
    monkeypatch.setattr(bronze_ingestion, "_source_count", lambda *a: 5)
    monkeypatch.setattr(bronze_ingestion, "_target_count", lambda *a: 5)
    monkeypatch.setattr(environment_provisioning, "project_execute", lambda *a, **k: SCHEMA)

    result = bronze_ingestion.verified_checkpoint(
        db, project.id, [table],
        approved_targets={table.id: "`MIGRATION_DEV` . `BRONZE` . `customer_sales`"},
        decision_run_id="MDR_CURRENT",
    )

    assert result and result["checkpoint_reused"] is True
    assert result["run_id"] == run.id
    assert result["results"][0]["target_fqn"] == "`migration_dev`.`bronze`.`customer_sales`"
    assert result["rejections"] == []


def test_medallion_reuses_bronze_and_reconciles_with_saved_project_connection(db, monkeypatch):
    project, _, table = _seed(db)
    ingestion = _completed_ingestion(db, project, table)
    _approved_medallion(db, project)
    statements = []

    def execute(session, project_id, statement, **kw):
        assert session is db and project_id == project.id
        statements.append(statement)
        return SCHEMA if statement.startswith("DESCRIBE") else [(5,)] if statement.startswith("SELECT COUNT") else []

    monkeypatch.setattr(environment_provisioning, "project_execute", execute)
    monkeypatch.setattr(bronze_ingestion, "_source_count", lambda *a: 5)
    monkeypatch.setattr(deployment, "_source_table_count", lambda *a: 5)
    loader = Mock(side_effect=AssertionError("Verified Bronze must not be loaded twice"))
    monkeypatch.setattr(bronze_ingestion, "_load_table", loader)

    result = medallion.deploy_medallion_dev(db, project.id)
    reconciliation = deployment.run_reconciliation(db, project.id)

    assert result["status"] == "PASSED", result.get("error")
    assert reconciliation["status"] == "PASSED"
    assert deployment.evaluate_dev_gate(db, project.id)["status"] == "PASSED"
    loader.assert_not_called()
    assert not any("TRUNCATE" in sql or "DROP TABLE" in sql or "INSERT INTO" in sql for sql in statements)
    rows = deployment._latest_successful_medallion_run(db, project.id, "DEV")[1]
    bronze = next(payload for _, payload in rows if payload["layer"] == "BRONZE")
    assert bronze["checkpoint_reused"] is True and bronze["bronze_run_id"] == ingestion.id
    assert bronze["databricks_workspace"] == "dbc-example.cloud.databricks.com"


@pytest.mark.parametrize("source_name, canonical_name", [
    ("CustomerSales", "customer_sales"),
    ("OrderSummary", "order_summary"),
])
def test_medallion_loads_exact_approved_canonical_bronze_target(
    db, monkeypatch, source_name, canonical_name
):
    project, _, table = _seed(db)
    table.object_name = source_name
    db.commit()
    _approved_medallion(db, project)
    bronze = db.scalar(select(MigrationMedallionNode).where(
        MigrationMedallionNode.project_id == project.id,
        MigrationMedallionNode.layer == "BRONZE",
    ))
    approved = f"`migration_dev`.`bronze`.`{canonical_name}`"
    bronze.target_name = canonical_name
    bronze.target_fqn = approved
    db.commit()
    loads = []

    def loader(*args, **kwargs):
        loads.append(kwargs)
        return {"object_id": table.id, "target_fqn": kwargs["target_fqn"],
                "status": "PASSED", "rows_loaded": 1, "target_rows": 1}

    monkeypatch.setattr(bronze_ingestion, "verified_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(bronze_ingestion, "_load_table", loader)
    monkeypatch.setattr(databricks_client, "execute_sql", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "databricks_workspace_identity", lambda: "qa-workspace")

    result = medallion.deploy_medallion_dev(db, project.id)

    assert result["status"] == "PASSED", result.get("error")
    assert loads[0]["target_fqn"] == approved
    evidence = [json.loads(row.payload_json) for row in db.query(MigrationDeployment).filter_by(
        project_id=project.id, object_id=table.id, status="PASSED"
    )]
    bronze_evidence = next(row for row in evidence if row.get("layer") == "BRONZE")
    assert bronze_evidence["target_fqn"] == approved
    assert bronze_evidence["approved_target_fqn"] == approved
    assert bronze_evidence["load"]["target_fqn"] == approved


def test_stale_checkpoint_target_is_audited_then_fresh_approved_target_is_loaded(db, monkeypatch):
    project, _, table = _seed(db)
    checkpoint_run = _completed_ingestion(db, project, table)
    table.object_name = "CustomerSales"
    db.commit()
    _approved_medallion(db, project)
    bronze = db.scalar(select(MigrationMedallionNode).where(
        MigrationMedallionNode.project_id == project.id,
        MigrationMedallionNode.layer == "BRONZE",
    ))
    approved = "`migration_dev`.`bronze`.`customer_sales`"
    bronze.target_name = "customer_sales"
    bronze.target_fqn = approved
    db.commit()
    loads = []

    def loader(*args, **kwargs):
        loads.append(kwargs)
        return {"object_id": table.id, "target_fqn": kwargs["target_fqn"],
                "status": "PASSED", "rows_loaded": 5, "target_rows": 5}

    monkeypatch.setattr(bronze_ingestion, "_load_table", loader)
    monkeypatch.setattr(databricks_client, "execute_sql", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "databricks_workspace_identity", lambda: "qa-workspace")

    result = medallion.deploy_medallion_dev(db, project.id)

    assert result["status"] == "PASSED", result.get("error")
    assert loads and loads[0]["target_fqn"] == approved
    records = [json.loads(row.payload_json) for row in db.query(CanonicalRecord).filter_by(
        project_id=project.id, object_id=table.id, record_type="BRONZE_INGESTION"
    )]
    rejection = next(row for row in records if row.get("action") == "CHECKPOINT_TARGET_MISMATCH")
    assert rejection["run_id"] == result["run_id"]
    assert rejection["checkpoint_run_id"] == checkpoint_run.id
    assert rejection["recorded_target_fqn"] == "`migration_dev`.`bronze`.`Customers`"
    assert rejection["approved_target_fqn"] == approved
    deployment_rows = [json.loads(row.payload_json) for row in db.query(MigrationDeployment).filter_by(
        project_id=project.id, object_id=table.id, status="PASSED"
    )]
    bronze_evidence = next(row for row in deployment_rows if row.get("layer") == "BRONZE")
    assert bronze_evidence["checkpoint_reused"] is False
    assert bronze_evidence["checkpoint_decision"] == "CHECKPOINT_TARGET_MISMATCH"


def test_failed_reload_keeps_data_and_exposes_failure_in_status_and_logs(db, client, auth_headers, monkeypatch):
    project, _, table = _seed(db)
    _completed_ingestion(db, project, table)
    _approved_medallion(db, project)
    statements = []

    def execute(session, project_id, statement, **kw):
        statements.append(statement)
        return SCHEMA if statement.startswith("DESCRIBE") else [(4,)]

    monkeypatch.setattr(environment_provisioning, "project_execute", execute)
    monkeypatch.setattr(bronze_ingestion, "_source_count", lambda *a: 5)
    monkeypatch.setattr(bronze_ingestion, "connector_info", lambda *a: {"mode": "DIRECT"})

    result = medallion.deploy_medallion_dev(db, project.id)
    status = client.get(f"/api/projects/{project.id}/medallion/deployments/dev/status", headers=auth_headers).json()
    logs = client.get(f"/api/projects/{project.id}/medallion/deployments/{result['run_id']}/logs", headers=auth_headers).json()

    assert result["status"] == status["status"] == "FAILED"
    assert status["run_id"] == result["run_id"] and status["failed_target"]
    assert logs["failed"] == 1
    assert any("approve replacement" in (row["message"] or "") for row in logs["logs"])
    assert all(sql.startswith(("SELECT", "DESCRIBE")) for sql in statements)
    with pytest.raises(ValueError, match="Latest DEV Medallion deployment is FAILED"):
        deployment.run_reconciliation(db, project.id)
    assert deployment.evaluate_dev_gate(db, project.id)["status"] == "BLOCKED"
    precheck = deployment.test_promotion_precheck(db, project.id, test_databricks=False)
    assert any(blocker["code"] == "DEV_LATEST_ATTEMPT" for blocker in precheck["blockers"])


def test_preflight_failure_has_a_persisted_run_and_log(db, client, auth_headers):
    project, _, _ = _seed(db)
    response = client.post(f"/api/projects/{project.id}/medallion/deploy-dev", headers=auth_headers, json={})
    assert response.status_code == 400
    status = client.get(f"/api/projects/{project.id}/medallion/deployments/dev/status", headers=auth_headers).json()
    logs = client.get(f"/api/projects/{project.id}/medallion/deployments/{status['run_id']}/logs", headers=auth_headers).json()
    assert status["status"] == "FAILED" and "No Medallion artifacts" in status["error"]
    assert logs["failed"] == 1 and logs["count"] == 2


def test_project_sql_is_isolated_between_concurrent_workflows(db, monkeypatch):
    ids = []
    for index in range(2):
        project = ensure_project(db, f"Concurrent workspace {index}")
        ids.append(project.id)
        db.add(MigrationDatabricksConfiguration(id=uid("DBC"), project_id=project.id,
               workspace_host=f"client{index}.cloud.databricks.com", http_path=f"/sql/warehouses/{index}",
               token_env_key=f"CLIENT_{index}_TOKEN", status="READY"))
        monkeypatch.setenv(f"CLIENT_{index}_TOKEN", f"test-secret-{index}")
    db.commit()
    barrier = Barrier(2)

    def provider(statement, **credentials):
        return [(credentials["server_hostname"], credentials["access_token"])]

    monkeypatch.setattr(environment_provisioning, "execute_sql_with_credentials", provider)

    @databricks_client.with_project_databricks
    def workflow(session, project_id):
        barrier.wait(timeout=5)
        return databricks_client.execute_sql("SELECT 1")

    def run(project_id):
        with SessionLocal() as session:
            return workflow(session, project_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ids))
    assert results == [[("client0.cloud.databricks.com", "test-secret-0")],
                       [("client1.cloud.databricks.com", "test-secret-1")]]
    # Scope must reset even when a request fails; another call remains independent.
    with pytest.raises(LookupError):
        _failing_scope(db, ids[0])
    monkeypatch.setattr(databricks_client, "get_settings", lambda: SimpleNamespace(
        databricks_host="global.cloud.databricks.com", databricks_http_path="/sql/global", databricks_token="global-test"))
    assert databricks_client.workspace_host() == "global.cloud.databricks.com"


@databricks_client.with_project_databricks
def _failing_scope(db, project_id):
    raise LookupError("test failure")


def test_untested_project_connection_cannot_fall_back_to_global_credentials(db, monkeypatch):
    project, _, _ = _seed(db)
    environment_provisioning.get_configuration(db, project.id).status = "NOT_TESTED"
    db.commit()
    provider = Mock()
    monkeypatch.setattr(environment_provisioning, "execute_sql_with_credentials", provider)
    monkeypatch.setattr(databricks_client, "get_settings", lambda: SimpleNamespace(
        databricks_host="global.cloud.databricks.com", databricks_http_path="/sql/global", databricks_token="global-test"))

    @databricks_client.with_project_databricks
    def workflow(db, project_id):
        return databricks_client.execute_sql("SELECT 1")

    with pytest.raises(ValueError, match="Test the project Databricks connection"):
        workflow(db, project.id)
    provider.assert_not_called()


def test_provider_secret_is_redacted_before_failure_logs_are_saved(db, client, auth_headers, monkeypatch):
    project, _, _ = _seed(db)
    _approved_medallion(db, project)
    config = environment_provisioning.get_configuration(db, project.id)
    config.token_env_key = "QA_WORKSPACE_TOKEN"
    db.commit()
    secret = "synthetic-test-token-must-never-appear-in-logs"
    monkeypatch.setenv(config.token_env_key, secret)
    monkeypatch.setattr(bronze_ingestion, "connector_info", lambda *a: {"mode": "DIRECT"})
    monkeypatch.setattr(environment_provisioning, "execute_sql_with_credentials",
                        Mock(side_effect=RuntimeError(f"Provider rejected {secret}")))

    result = medallion.deploy_medallion_dev(db, project.id, parent_run_id="PROMPT_TEST_RUN")
    logs = client.get(f"/api/projects/{project.id}/medallion/deployments/{result['run_id']}/logs", headers=auth_headers)

    assert result["status"] == "FAILED" and "[REDACTED]" in result["error"]
    assert secret not in logs.text
    assert all(row["details"]["parent_run_id"] == "PROMPT_TEST_RUN" for row in logs.json()["logs"])
