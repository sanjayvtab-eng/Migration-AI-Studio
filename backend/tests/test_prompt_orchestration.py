import pytest
from sqlalchemy import select

from app.models.entities import (
    CanonicalRecord,
    MigrationDatabricksConfiguration,
    MigrationEnvironmentPlan,
    MigrationObject,
    MigrationProject,
    MigrationSource,
)
from app.services import prompt_orchestration
from app.services.engine import add_source, ensure_project, ingest_snapshot, uid


def _seed(db, *, provisioned=True, db_ready=True):
    project = ensure_project(db, "Release 3 Prompt Orchestration")
    source = add_source(db, project.id, "SQL Server", "localhost", "MigrationDemo")
    ingest_snapshot(
        db,
        project.id,
        source.id,
        {
            "database": "MigrationDemo",
            "objects": [
                {
                    "schema": "dbo",
                    "name": "Customers",
                    "type": "TABLE",
                    "columns": [
                        {"name": "CustomerId", "type": "int", "nullable": False},
                        {"name": "CustomerName", "type": "nvarchar", "max_length": 200},
                    ],
                }
            ],
        },
    )
    if db_ready:
        db.add(
            MigrationDatabricksConfiguration(
                id=uid("DBC"),
                project_id=project.id,
                workspace_host="dbc-example.cloud.databricks.com",
                http_path="/sql/1.0/warehouses/test",
                token_env_key="DATABRICKS_TOKEN",
                catalog_prefix="migration",
                status="READY",
            )
        )
    if provisioned:
        db.add(
            MigrationEnvironmentPlan(
                id=uid("EVP"),
                project_id=project.id,
                environment="DEV",
                catalog_name="migration_dev",
                status="PROVISIONED",
            )
        )
    db.commit()
    return project, source


def test_parse_prompt_needs_user_input_unprovisioned(db):
    project, source = _seed(db, provisioned=False)
    res = prompt_orchestration.parse_and_validate_prompt(
        db, project.id, "Migrate MigrationDemo from SQL Server to DEV Databricks"
    )
    assert res["status"] == "NEEDS_USER_INPUT"
    assert any("provisioned" in b.lower() for b in res["blockers"])
    assert len(res["actionable_steps"]) > 0


def test_parse_prompt_rejects_empty(db):
    project, _ = _seed(db)
    with pytest.raises(ValueError, match="prompt is required"):
        prompt_orchestration.parse_and_validate_prompt(db, project.id, "")


def test_parse_prompt_valid_intent(db):
    project, source = _seed(db, provisioned=True, db_ready=True)
    res = prompt_orchestration.parse_and_validate_prompt(
        db, project.id, "Migrate MigrationDemo from SQL Server to DEV Databricks"
    )
    assert res["status"] == "VALIDATED"
    assert res["intent"]["source_database"] == "MigrationDemo"
    assert res["intent"]["target_environment"] == "DEV"
    assert res["intent"]["target_catalog"] == "migration_dev"


def test_generate_prompt_plan_creates_impact_and_stages(db):
    project, source = _seed(db, provisioned=True, db_ready=True)
    plan = prompt_orchestration.generate_prompt_plan(
        db, project.id, "Migrate MigrationDemo to DEV Databricks"
    )
    assert plan["status"] == "PENDING_APPROVAL"
    assert plan["impact"]["table_count"] == 1
    assert len(plan["stages"]) == 6
    assert plan["destinations"][0]["source_fqn"] == "dbo.Customers"
    assert plan["destinations"][0]["bronze"] == "migration_dev.bronze.customers"
    assert plan["destinations"][0]["silver"] == "migration_dev.silver.customers"
    assert plan["destinations"][0]["gold"] == "migration_dev.gold.dim_customers"


def test_generate_prompt_plan_reuses_matching_bronze_checkpoint(db, monkeypatch):
    project, _ = _seed(db)
    monkeypatch.setattr(
        prompt_orchestration.bronze_ingestion,
        "latest",
        lambda *a, **kw: {
            "status": "PASSED", "run_id": "BRI_COMPLETE", "ended_at": "2026-09-15T08:00:00",
            "results": [{"status": "PASSED", "source": "dbo.Customers", "rows_loaded": 5}],
        },
    )

    plan = prompt_orchestration.generate_prompt_plan(
        db, project.id, "Migrate MigrationDemo to DEV Databricks"
    )

    assert plan["impact"]["bronze_checkpoint"]["reusable"] is True
    assert plan["impact"]["bronze_checkpoint"]["run_id"] == "BRI_COMPLETE"
    assert plan["impact"]["estimated_rows"] == 5


def test_generate_prompt_plan_blocks_when_discovery_has_no_tables(db):
    project = ensure_project(db, "Prompt Plan Without Discovery")
    add_source(db, project.id, "SQL Server", "localhost", "MigrationDemo")
    db.add(
        MigrationDatabricksConfiguration(
            id=uid("DBC"), project_id=project.id,
            workspace_host="dbc-example.cloud.databricks.com",
            http_path="/sql/1.0/warehouses/test",
            token_env_key="DATABRICKS_TOKEN", catalog_prefix="migration", status="READY",
        )
    )
    db.add(
        MigrationEnvironmentPlan(
            id=uid("EVP"), project_id=project.id, environment="DEV",
            catalog_name="migration_dev", status="PROVISIONED",
        )
    )
    db.commit()

    plan = prompt_orchestration.generate_prompt_plan(
        db, project.id, "Migrate MigrationDemo to DEV Databricks"
    )

    assert plan["status"] == "NEEDS_USER_INPUT"
    assert any("no discovered" in blocker.lower() for blocker in plan["blockers"])


def test_execute_prompt_plan_requires_approval(db):
    project, _ = _seed(db)
    with pytest.raises(LookupError, match="not found"):
        prompt_orchestration.execute_prompt_plan(db, project.id, "NON_EXISTENT_PLAN")


def test_execute_prompt_plan_end_to_end_governed(db, monkeypatch):
    project, source = _seed(db, provisioned=True, db_ready=True)
    plan = prompt_orchestration.generate_prompt_plan(
        db, project.id, "Migrate MigrationDemo from SQL Server to DEV Databricks"
    )
    plan_id = plan["plan_id"]

    # Mock bronze_ingestion.run
    bronze_call = {}

    def successful_bronze(*args, **kwargs):
        bronze_call.update(kwargs)
        return {
            "status": "PASSED",
            "passed": 1,
            "failed": 0,
            "results": [{"status": "PASSED", "rows_loaded": 50}],
            "run_id": "RUN_BRONZE_TEST",
        }

    monkeypatch.setattr(
        prompt_orchestration.bronze_ingestion,
        "run",
        successful_bronze,
    )

    # Mock medallion calls
    monkeypatch.setattr(prompt_orchestration.medallion, "infer_semantics_hybrid", lambda *a, **kw: {})
    monkeypatch.setattr(prompt_orchestration.medallion, "approve_all_semantics", lambda *a, **kw: {})
    monkeypatch.setattr(prompt_orchestration.medallion, "build_medallion_plan", lambda *a, **kw: {"node_count": 3})
    monkeypatch.setattr(prompt_orchestration.medallion, "generate_medallion_artifacts", lambda *a, **kw: {"generated_count": 3})
    monkeypatch.setattr(prompt_orchestration.medallion, "medallion_validation_report", lambda *a, **kw: {"status": "PASSED", "passed_count": 3, "failed_count": 0})
    monkeypatch.setattr(prompt_orchestration.medallion, "approve_all_medallion_artifacts", lambda *a, **kw: {})
    monkeypatch.setattr(prompt_orchestration.medallion, "deploy_medallion_dev", lambda *a, **kw: {"status": "PASSED", "deployed_count": 3})

    # Mock ai_remediation
    monkeypatch.setattr(prompt_orchestration.ai_remediation, "run_remediation_batch", lambda *a, **kw: {"applied_count": 0})

    # Mock deployment & reconciliation
    monkeypatch.setattr(prompt_orchestration.deployment, "run_reconciliation", lambda *a, **kw: {"status": "PASSED"})
    monkeypatch.setattr(prompt_orchestration.deployment, "evaluate_dev_gate", lambda *a, **kw: {"status": "PASSED"})

    # Execute plan
    res = prompt_orchestration.execute_prompt_plan(
        db, project.id, plan_id=plan_id, actor="admin"
    )
    assert res["status"] == "COMPLETED"
    assert res["stages"]["BRONZE_INGESTION"]["status"] == "PASSED"
    assert res["stages"]["MEDALLION_GENERATION"]["status"] == "PASSED"
    assert res["stages"]["RECONCILIATION"]["status"] == "PASSED"
    assert bronze_call["replace_existing_data"] is False
    assert "overwrite_confirmed" not in bronze_call

    # Check latest execution query
    latest = prompt_orchestration.latest_prompt_execution(db, project.id)
    assert latest is not None
    assert latest["status"] == "COMPLETED"


def test_execute_prompt_plan_reports_partial_bronze_failure(db, monkeypatch):
    project, _ = _seed(db)
    plan = prompt_orchestration.generate_prompt_plan(
        db, project.id, "Migrate MigrationDemo to DEV Databricks"
    )
    monkeypatch.setattr(
        prompt_orchestration.bronze_ingestion,
        "run",
        lambda *a, **kw: {
            "status": "PARTIAL", "passed": 1, "failed": 1, "run_id": "BRI_PARTIAL",
            "results": [
                {"object_id": "one", "source": "dbo.Customers", "status": "PASSED", "rows_loaded": 5},
                {"object_id": "two", "source": "dbo.Orders", "status": "FAILED", "error": "warehouse timeout"},
            ],
        },
    )

    result = prompt_orchestration.execute_prompt_plan(db, project.id, plan["plan_id"])

    assert result["status"] == "FAILED"
    assert result["failed_stage"] == "BRONZE_INGESTION"
    assert result["stages"]["BRONZE_INGESTION"]["status"] == "FAILED"
    assert "dbo.Orders" in result["error"]
    assert result["errors"][0]["recommended_action"]


def test_prompt_api_workflow(client, auth_headers, db, monkeypatch):
    p = client.post("/api/projects", headers=auth_headers, json={"name": "Prompt API Project"}).json()
    pid = p["id"]
    s = client.post(
        f"/api/projects/{pid}/sources",
        headers=auth_headers,
        json={"profile_name": "SQL1", "server_name": "sql1", "database_name": "MigrationDemo"},
    ).json()

    # Plan when unprovisioned should return NEEDS_USER_INPUT
    res = client.post(
        f"/api/projects/{pid}/prompt-migration/plan",
        headers=auth_headers,
        json={"prompt": "Migrate MigrationDemo from SQL Server to DEV Databricks"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "NEEDS_USER_INPUT"

    # Now configure Databricks and DEV environment
    client.put(
        f"/api/projects/{pid}/databricks/configuration",
        headers=auth_headers,
        json={
            "workspace_host": "dbc-test.cloud.databricks.com",
            "http_path": "/sql/1.0/warehouses/test",
            "token_env_key": "DATABRICKS_TOKEN",
            "catalog_prefix": "migration",
        },
    )
    from app.models.entities import MigrationDatabricksConfiguration, MigrationEnvironmentPlan
    cfg = db.scalar(select(MigrationDatabricksConfiguration).where(MigrationDatabricksConfiguration.project_id == pid))
    cfg.status = "READY"
    db.add(
        MigrationEnvironmentPlan(
            id="EVP_TEST_API",
            project_id=pid,
            environment="DEV",
            catalog_name="migration_dev",
            status="PROVISIONED",
        )
    )
    db.commit()
    ingest_snapshot(
        db,
        pid,
        s["id"],
        {
            "database": "MigrationDemo",
            "objects": [{
                "schema": "dbo", "name": "Customers", "type": "TABLE",
                "columns": [{"name": "CustomerId", "type": "int", "nullable": False}],
            }],
        },
    )

    # Plan when provisioned
    res = client.post(
        f"/api/projects/{pid}/prompt-migration/plan",
        headers=auth_headers,
        json={"prompt": "Migrate MigrationDemo from SQL Server to DEV Databricks"},
    )
    assert res.status_code == 200
    plan_data = res.json()
    assert plan_data["status"] == "PENDING_APPROVAL"
    plan_id = plan_data["plan_id"]

    # Mock pipeline for execute
    monkeypatch.setattr(prompt_orchestration.discovery, "discover_sqlserver", lambda *a, **kw: {"discovered": 1})
    monkeypatch.setattr(
        prompt_orchestration.bronze_ingestion,
        "run",
        lambda *args, **kwargs: {
            "status": "PASSED",
            "passed": 1,
            "failed": 0,
            "results": [{"status": "PASSED", "rows_loaded": 5}],
            "run_id": "RUN_API_TEST",
        },
    )
    monkeypatch.setattr(prompt_orchestration.medallion, "infer_semantics_hybrid", lambda *a, **kw: {})
    monkeypatch.setattr(prompt_orchestration.medallion, "approve_all_semantics", lambda *a, **kw: {})
    monkeypatch.setattr(prompt_orchestration.medallion, "build_medallion_plan", lambda *a, **kw: {"node_count": 0})
    monkeypatch.setattr(prompt_orchestration.medallion, "generate_medallion_artifacts", lambda *a, **kw: {"generated_count": 1})
    monkeypatch.setattr(prompt_orchestration.medallion, "medallion_validation_report", lambda *a, **kw: {"status": "PASSED", "passed_count": 1, "failed_count": 0})
    monkeypatch.setattr(prompt_orchestration.medallion, "approve_all_medallion_artifacts", lambda *a, **kw: {})
    monkeypatch.setattr(prompt_orchestration.medallion, "deploy_medallion_dev", lambda *a, **kw: {"status": "PASSED", "deployed_count": 1})
    monkeypatch.setattr(prompt_orchestration.ai_remediation, "run_remediation_batch", lambda *a, **kw: {"applied_count": 0})
    monkeypatch.setattr(prompt_orchestration.deployment, "run_reconciliation", lambda *a, **kw: {"status": "PASSED"})
    monkeypatch.setattr(prompt_orchestration.deployment, "evaluate_dev_gate", lambda *a, **kw: {"status": "PASSED"})

    # Execute
    exec_res = client.post(
        f"/api/projects/{pid}/prompt-migration/execute",
        headers=auth_headers,
        json={"plan_id": plan_id},
    )
    assert exec_res.status_code == 200
    assert exec_res.json()["status"] == "COMPLETED"

    # Latest endpoint
    latest_res = client.get(
        f"/api/projects/{pid}/prompt-migration/latest",
        headers=auth_headers,
    )
    assert latest_res.status_code == 200
    assert latest_res.json()["execution"]["status"] == "COMPLETED"
