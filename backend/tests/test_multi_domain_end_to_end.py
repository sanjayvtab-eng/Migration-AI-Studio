import pytest
from sqlalchemy import select

from app.models.entities import (
    MigrationDatabricksConfiguration,
    MigrationEnvironmentPlan,
    MigrationStageArtifactVersion,
    PromptSpecificationVersion,
)
from app.services import (
    bronze_ingestion,
    databricks_client,
    deployment,
    master_orchestration,
    prompt_specification as service,
)
from app.services.engine import add_source, ensure_project, ingest_snapshot, uid


def test_domain_1_employee_payroll_full_lifecycle(db, monkeypatch):
    """
    Domain 1: EmployeePayroll (PayrollDB)
    Executes full lifecycle:
    1. Schema ingestion
    2. Prompt submission & dynamic clarification generation
    3. Plan approval & artifact generation
    4. SQL verification (no MigrationDemo leaks, atomic SCD2 MERGE, custom param naming)
    5. Target validation & artifact review
    6. DEV deployment & reconciliation & DEV quality gate
    7. Automated promotion preflight check
    8. Full promotion to TEST -> UAT -> PROD with exact confirmation
    """
    project = ensure_project(db, "Employee Payroll Migration Project")
    source = add_source(db, project.id, "SQLServer_Payroll", "sql-prod.company.local", "PayrollDB")

    tables = {
        "Employees": [
            ("EmployeeID", "int"), ("FirstName", "varchar"), ("LastName", "varchar"),
            ("DepartmentID", "int"), ("HireDate", "date"), ("Status", "varchar"),
            ("CreatedDate", "datetime"), ("ModifiedDate", "datetime"),
        ],
        "Departments": [
            ("DepartmentID", "int"), ("DepartmentName", "varchar"),
            ("Location", "varchar"), ("CreatedDate", "datetime"),
        ],
        "Payroll": [
            ("PayrollID", "int"), ("EmployeeID", "int"), ("PayDate", "date"),
            ("BaseSalary", "decimal"), ("Bonus", "decimal"), ("Deductions", "decimal"),
            ("NetPay", "decimal"), ("CreatedDate", "datetime"),
        ],
        "PaySummary": [
            ("SummaryID", "int"), ("DepartmentID", "int"), ("PayPeriod", "varchar"),
            ("TotalNetPay", "decimal"), ("LoadDate", "datetime"),
        ],
    }

    objects = []
    for table_name, cols in tables.items():
        objects.append({
            "schema": "dbo",
            "name": table_name,
            "type": "TABLE",
            "columns": [{"name": cname, "type": ctype, "nullable": True} for cname, ctype in cols],
        })

    ingest_snapshot(db, project.id, source.id, {"database": "PayrollDB", "objects": objects})

    db.add(MigrationEnvironmentPlan(
        id=uid("EVP"), project_id=project.id, environment="DEV",
        catalog_name="payroll_dev", status="PROVISIONED",
    ))
    db.add(MigrationDatabricksConfiguration(
        id=uid("DBC"), project_id=project.id,
        workspace_host="payroll.cloud.databricks.com", http_path="/sql/warehouses/payroll",
        token_env_key="PAYROLL_DATABRICKS_TOKEN", status="READY",
    ))
    monkeypatch.setenv("PAYROLL_DATABRICKS_TOKEN", "payroll-secret-token")
    db.commit()

    prompt = """Migrate PayrollDB from SQL Server to Databricks DEV catalog payroll_dev.
Bronze:
- Ingest dbo.Employees, dbo.Departments, dbo.Payroll, and dbo.PaySummary.
Silver:
- Create cleaned views for Employees and Payroll using discovered target column names.
- Create vw_EmployeePayHistory by joining Employees, Departments and Payroll.
- Create fn_CalculateNetPay(p_base_salary DECIMAL, p_bonus DECIMAL, p_deductions DECIMAL).
- Create usp_ProcessMonthlyPayroll as an idempotent loader.
Gold:
- Create dim_employee, dim_department, fact_payroll, and vw_department_pay_summary.
Validate every identifier and wait for plan approval before generation."""

    # 1. Submit prompt
    first = service.submit(db, project.id, prompt, "payroll_architect")
    assert first["status"] == "NEEDS_USER_INPUT"
    assert len(first["clarifications"]) > 0

    # Ensure each clarification provides explicit recommended_answer and inference_reason
    answers = {}
    for q in first["clarifications"]:
        assert q["recommended_answer"] is not None
        assert len(q["recommended_answer"]) > 0
        assert q["inference_reason"] is not None
        answers[q["key"]] = q["recommended_answer"]

    # 2. Answer clarifications
    second = service.answer_clarifications(db, project.id, first["id"], answers, "payroll_architect")
    assert second["version"] == 2
    assert second["status"] == "PENDING_PLAN_APPROVAL"
    assert all(a["grounding_status"] == "GROUNDED" for a in second["artifacts"])

    # 3. Approve plan and generate
    service.approve_plan(db, project.id, first["id"], "payroll_architect", "APPROVED", "Payroll migration plan approved")
    gen_result = service.generate(db, project.id, first["id"], "payroll_architect")
    assert gen_result["status"] == "VALIDATING"

    # 4. Target validation
    monkeypatch.setattr(service, "execute_sql", lambda statement, safe_retry=True: [("plan",)])
    val_result = service.validate_target(db, project.id, first["id"])
    assert val_result["status"] == "PENDING_ARTIFACT_REVIEW"

    # Verify generated artifacts SQL contains NO MigrationDemo relics
    trace = service.trace(db, project.id, first["id"])
    for item in trace["requirements"]:
        version = db.get(MigrationStageArtifactVersion, item["artifact_version_id"])
        sql_content = version.content
        assert "MigrationDemo" not in sql_content
        assert "customer_sales" not in sql_content.lower()
        assert "order_items" not in sql_content.lower()

    # Verify function artifact
    fn_art = next(item for item in trace["requirements"] if "fn_calculate_net_pay" in item["target_fqn"].lower())
    fn_ver = db.get(MigrationStageArtifactVersion, fn_art["artifact_version_id"])
    assert "p_base_salary DECIMAL" in fn_ver.content
    assert "p_bonus DECIMAL" in fn_ver.content
    assert "p_deductions DECIMAL" in fn_ver.content

    # 5. Approve all artifacts
    for item in trace["requirements"]:
        service.review_artifact(db, project.id, first["id"], item["artifact_version_id"], "APPROVED", "payroll_architect")
    assert service.detail(db, project.id, first["id"])["status"] == "ARTIFACTS_APPROVED"

    # 6. DEV deployment
    loaded = []
    monkeypatch.setattr(bronze_ingestion, "_load_table", lambda *a, **kw: loaded.append(kw["target_fqn"]) or {"object_id": a[4].id, "target_fqn": kw["target_fqn"], "status": "PASSED", "rows_loaded": 10, "target_rows": 10})
    monkeypatch.setattr(databricks_client, "execute_sql", lambda *a, **k: [("ok",)])
    monkeypatch.setattr(deployment, "databricks_workspace_identity", lambda: "payroll-qa-workspace")

    def mock_dev_recon(db_sess, pid, env="DEV", **kw):
        import json
        from app.models.entities import CanonicalRecord
        rec = CanonicalRecord(
            id=uid("REC"), project_id=pid, environment=env, record_type="RECONCILIATION",
            payload_json=json.dumps({"status": "PASSED", "passed": 4, "failed": 0}),
        )
        db_sess.add(rec)
        db_sess.commit()
        return {"status": "PASSED", "passed": 4, "failed": 0}

    def mock_dev_gate(db_sess, pid):
        import json
        from app.models.entities import CanonicalRecord
        rec = CanonicalRecord(
            id=uid("REC"), project_id=pid, environment="DEV", record_type="QUALITY_GATE",
            payload_json=json.dumps({"status": "PASSED", "gate_id": uid("GAT"), "blockers": []}),
        )
        db_sess.add(rec)
        db_sess.commit()
        return {"status": "PASSED", "gate_id": uid("GAT"), "blockers": []}

    monkeypatch.setattr(deployment, "run_reconciliation", mock_dev_recon)
    monkeypatch.setattr(deployment, "evaluate_dev_gate", mock_dev_gate)

    dev_deploy = service.deploy_dev(db, project.id, first["id"], "payroll_architect")
    assert dev_deploy["status"] == "DEV_GATE_PASSED"

    # 7. Check preflight for automated promotion
    dev_run = dev_deploy["deployment"].get("run_id") or "RUN_PAYROLL_DEV"
    monkeypatch.setattr(master_orchestration.deployment, "test_promotion_precheck", lambda *a, **kw: {"eligible": True, "artifact_count": 4, "source_deployment_run_id": dev_run})

    preflight = master_orchestration.get_automated_promotion_preflight(db, project.id)
    assert preflight["eligible"] is True
    assert preflight["blockers"] == []

    # 8. Full automated promotion through TEST -> UAT -> PROD
    calls = []
    monkeypatch.setattr(master_orchestration.deployment, "test_promotion_precheck", lambda *a, **kw: calls.append("TEST_PRECHECK") or {"eligible": True, "artifact_count": 4, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_test", lambda *a, **kw: calls.append("TEST_PROMOTE") or {"status": "PASSED", "run_id": "RUN_PAYROLL_TEST", "count": 4})
    monkeypatch.setattr(master_orchestration.deployment, "run_reconciliation", lambda db, pid, env, **kw: calls.append(f"{env}_RECON") or {"status": "PASSED", "run_id": f"REC_{env}", "passed": 4, "failed": 0})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_test_gate", lambda *a, **kw: calls.append("TEST_GATE") or {"status": "PASSED", "gate_id": "GAT_PAYROLL_TEST"})

    monkeypatch.setattr(master_orchestration.deployment, "uat_promotion_precheck", lambda *a, **kw: calls.append("UAT_PRECHECK") or {"eligible": True, "artifact_count": 4, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_uat", lambda *a, **kw: calls.append("UAT_PROMOTE") or {"status": "PASSED", "run_id": "RUN_PAYROLL_UAT", "count": 4})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_uat_gate", lambda *a, **kw: calls.append("UAT_GATE") or {"status": "PASSED", "gate_id": "GAT_PAYROLL_UAT"})

    monkeypatch.setattr(master_orchestration.deployment, "prod_promotion_precheck", lambda *a, **kw: calls.append("PROD_PRECHECK") or {"eligible": True, "artifact_count": 4, "source_deployment_run_id": dev_run})
    monkeypatch.setattr(master_orchestration.deployment, "promote_medallion_to_prod", lambda *a, **kw: calls.append("PROD_PROMOTE") or {"status": "PASSED", "run_id": "RUN_PAYROLL_PROD", "count": 4})
    monkeypatch.setattr(master_orchestration.deployment, "evaluate_prod_gate", lambda *a, **kw: calls.append("PROD_GATE") or {"status": "PASSED", "gate_id": "GAT_PAYROLL_PROD"})

    promo_result = master_orchestration.authorize_automated_promotion(db, project.id, confirmation_text="PROMOTE TO PROD")
    assert promo_result["status"] == "COMPLETED"
    assert promo_result["state"] == "COMPLETED"
    assert promo_result["environments"]["TEST"]["status"] == "PASSED"
    assert promo_result["environments"]["UAT"]["status"] == "PASSED"
    assert promo_result["environments"]["PROD"]["status"] == "PASSED"
    assert promo_result["last_successful_checkpoint"] == "PROD_PASSED"


def test_domain_2_healthcare_generation_and_scd2(db, monkeypatch):
    """
    Domain 2: Healthcare (HealthCareDB)
    Tests dynamic generation on medical domain:
    1. Schema with Patients, Doctors, Encounters, EncounterBilling
    2. Prompt requesting SCD Type 2 dimension, procedure, functions, fact, and views
    3. Verifies zero MigrationDemo contamination
    4. Verifies SCD2 Delta MERGE generates staging and hash diff (<=>)
    """
    project = ensure_project(db, "Healthcare Migration Project")
    source = add_source(db, project.id, "SQLServer_Health", "sql-health.internal", "HealthCareDB")

    tables = {
        "Patients": [
            ("PatientID", "int"), ("FullName", "varchar"), ("DateOfBirth", "date"),
            ("Gender", "varchar"), ("City", "varchar"), ("State", "varchar"),
            ("CreatedDate", "datetime"), ("ModifiedDate", "datetime"),
        ],
        "Doctors": [
            ("DoctorID", "int"), ("DoctorName", "varchar"), ("Specialty", "varchar"),
            ("DepartmentID", "int"), ("CreatedDate", "datetime"),
        ],
        "Encounters": [
            ("EncounterID", "int"), ("PatientID", "int"), ("DoctorID", "int"),
            ("EncounterDate", "date"), ("EncounterType", "varchar"), ("Status", "varchar"),
            ("CreatedDate", "datetime"),
        ],
        "EncounterBilling": [
            ("BillingID", "int"), ("EncounterID", "int"), ("Amount", "decimal"),
            ("InsurancePaid", "decimal"), ("PatientCopay", "decimal"), ("CreatedDate", "datetime"),
        ],
    }

    objects = []
    for table_name, cols in tables.items():
        objects.append({
            "schema": "dbo",
            "name": table_name,
            "type": "TABLE",
            "columns": [{"name": cname, "type": ctype, "nullable": True} for cname, ctype in cols],
        })

    ingest_snapshot(db, project.id, source.id, {"database": "HealthCareDB", "objects": objects})

    db.add(MigrationEnvironmentPlan(
        id=uid("EVP"), project_id=project.id, environment="DEV",
        catalog_name="health_dev", status="PROVISIONED",
    ))
    db.add(MigrationDatabricksConfiguration(
        id=uid("DBC"), project_id=project.id,
        workspace_host="health.cloud.databricks.com", http_path="/sql/warehouses/health",
        token_env_key="HEALTH_DATABRICKS_TOKEN", status="READY",
    ))
    monkeypatch.setenv("HEALTH_DATABRICKS_TOKEN", "health-secret-token")
    db.commit()

    prompt = """Migrate HealthCareDB from SQL Server to Databricks DEV catalog health_dev.
Bronze:
- Ingest dbo.Patients, dbo.Doctors, dbo.Encounters, and dbo.EncounterBilling.
Silver:
- Create cleaned views for Patients, Encounters and EncounterBilling.
- Create vw_PatientBillingHistory by joining Patients, Encounters and EncounterBilling.
- Create fn_CalculatePatientPortion(p_amount DECIMAL, p_insurance DECIMAL).
- Create usp_SyncEncounterBilling as an idempotent loader.
Gold:
- Create dim_patient, dim_doctor, fact_billing, and vw_monthly_patient_billing.
Validate every identifier and wait for plan approval before generation."""

    spec = service.submit(db, project.id, prompt, "health_architect")
    assert spec["status"] == "NEEDS_USER_INPUT"

    # Dynamic answers - set dimension_scd_type to TYPE_2
    answers = {}
    for q in spec["clarifications"]:
        if q["key"] == "dimension_scd_type":
            answers[q["key"]] = "TYPE_2"
        else:
            answers[q["key"]] = q["recommended_answer"]

    second = service.answer_clarifications(db, project.id, spec["id"], answers, "health_architect")
    assert second["status"] == "PENDING_PLAN_APPROVAL"

    service.approve_plan(db, project.id, spec["id"], "health_architect", "APPROVED", "Health plan approved")
    service.generate(db, project.id, spec["id"], "health_architect")

    monkeypatch.setattr(service, "execute_sql", lambda statement, safe_retry=True: [("plan",)])
    service.validate_target(db, project.id, spec["id"])

    trace = service.trace(db, project.id, spec["id"])
    assert len(trace["requirements"]) >= 9

    for item in trace["requirements"]:
        version = db.get(MigrationStageArtifactVersion, item["artifact_version_id"])
        sql_content = version.content
        assert "MigrationDemo" not in sql_content
        assert "Customers" not in sql_content
        assert "Orders" not in sql_content

    # Inspect dim_patient SCD Type 2
    dim_patient = next(item for item in trace["requirements"] if "dim_patient" in item["target_fqn"].lower())
    dim_patient_ver = db.get(MigrationStageArtifactVersion, dim_patient["artifact_version_id"])
    dim_sql = dim_patient_ver.content
    assert "MERGE INTO" in dim_sql
    assert "t.is_current = true" in dim_sql
    assert "target.is_current = false" in dim_sql
    assert "target.valid_to = staged.valid_from" in dim_sql
    assert "Stream A" in dim_sql
    assert "Stream B" in dim_sql
    assert "row_hash" in dim_sql
    assert "<=>" in dim_sql


def test_domain_3_inventory_generation_and_validation(db, monkeypatch):
    """
    Domain 3: Supply Chain / Inventory (SupplyChainDB)
    Tests dynamic generation on inventory management domain:
    1. Schema with Warehouses, Suppliers, InventoryItems, StockMovements
    2. Prompt requesting Bronze, Silver views, join view, function, procedure, Gold dimensions, fact, summary
    3. Complete generation and artifact review
    """
    project = ensure_project(db, "Inventory Migration Project")
    source = add_source(db, project.id, "SQLServer_Supply", "sql-supply.internal", "SupplyChainDB")

    tables = {
        "Warehouses": [
            ("WarehouseID", "int"), ("WarehouseName", "varchar"), ("City", "varchar"),
            ("Country", "varchar"), ("Capacity", "int"), ("CreatedDate", "datetime"),
        ],
        "Suppliers": [
            ("SupplierID", "int"), ("SupplierName", "varchar"), ("ContactEmail", "varchar"),
            ("Country", "varchar"), ("CreatedDate", "datetime"),
        ],
        "InventoryItems": [
            ("ItemID", "int"), ("SupplierID", "int"), ("ItemName", "varchar"),
            ("SKU", "varchar"), ("ReorderLevel", "int"), ("UnitPrice", "decimal"),
            ("CreatedDate", "datetime"),
        ],
        "StockMovements": [
            ("MovementID", "int"), ("ItemID", "int"), ("WarehouseID", "int"),
            ("MovementDate", "date"), ("MovementType", "varchar"), ("Quantity", "int"),
            ("CreatedDate", "datetime"),
        ],
    }

    objects = []
    for table_name, cols in tables.items():
        objects.append({
            "schema": "dbo",
            "name": table_name,
            "type": "TABLE",
            "columns": [{"name": cname, "type": ctype, "nullable": True} for cname, ctype in cols],
        })

    ingest_snapshot(db, project.id, source.id, {"database": "SupplyChainDB", "objects": objects})

    db.add(MigrationEnvironmentPlan(
        id=uid("EVP"), project_id=project.id, environment="DEV",
        catalog_name="supply_dev", status="PROVISIONED",
    ))
    db.add(MigrationDatabricksConfiguration(
        id=uid("DBC"), project_id=project.id,
        workspace_host="supply.cloud.databricks.com", http_path="/sql/warehouses/supply",
        token_env_key="SUPPLY_DATABRICKS_TOKEN", status="READY",
    ))
    monkeypatch.setenv("SUPPLY_DATABRICKS_TOKEN", "supply-secret-token")
    db.commit()

    prompt = """Migrate SupplyChainDB from SQL Server to Databricks DEV catalog supply_dev.
Bronze:
- Ingest dbo.Warehouses, dbo.Suppliers, dbo.InventoryItems, and dbo.StockMovements.
Silver:
- Create cleaned views for Warehouses, Suppliers, InventoryItems, and StockMovements.
- Create vw_InventoryStatus by joining InventoryItems, Warehouses and StockMovements.
- Create fn_CalculateReorderAlert(p_quantity INT, p_reorder_level INT).
- Create usp_ProcessStockMovement as an idempotent loader.
Gold:
- Create dim_warehouse, dim_supplier, fact_inventory_movement, and vw_low_stock_summary.
Validate every identifier and wait for plan approval before generation."""

    spec = service.submit(db, project.id, prompt, "supply_architect")
    assert spec["status"] == "NEEDS_USER_INPUT"

    answers = {q["key"]: q["recommended_answer"] for q in spec["clarifications"]}
    second = service.answer_clarifications(db, project.id, spec["id"], answers, "supply_architect")
    assert second["status"] == "PENDING_PLAN_APPROVAL"

    service.approve_plan(db, project.id, spec["id"], "supply_architect", "APPROVED", "Supply plan approved")
    service.generate(db, project.id, spec["id"], "supply_architect")

    monkeypatch.setattr(service, "execute_sql", lambda statement, safe_retry=True: [("plan",)])
    service.validate_target(db, project.id, spec["id"])

    trace = service.trace(db, project.id, spec["id"])
    assert len(trace["requirements"]) >= 9

    # Approve all artifacts
    for item in trace["requirements"]:
        service.review_artifact(db, project.id, spec["id"], item["artifact_version_id"], "APPROVED", "supply_architect")
    assert service.detail(db, project.id, spec["id"])["status"] == "ARTIFACTS_APPROVED"

    # Verify no leaks from other domains
    for item in trace["requirements"]:
        ver = db.get(MigrationStageArtifactVersion, item["artifact_version_id"])
        sql = ver.content
        assert "MigrationDemo" not in sql
        assert "Employees" not in sql
        assert "Patients" not in sql
