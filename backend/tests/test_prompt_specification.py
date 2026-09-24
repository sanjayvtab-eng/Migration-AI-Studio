import pytest
from sqlalchemy import select

from app.models.entities import (
    MigrationDatabricksConfiguration,
    MigrationEnvironmentPlan,
    MigrationStageArtifactVersion,
    PromptPlanApproval,
    PromptSpecificationVersion,
)
from app.services import (bronze_ingestion, databricks_client, deployment,
                          medallion, prompt_specification as service)
from app.services.engine import add_source, ensure_project, ingest_snapshot, uid


PROMPT = """Migrate MigrationDemo from SQL Server to Databricks DEV catalog migration_dev.
Bronze:
- Ingest dbo.Customers, dbo.CustomerSales, dbo.OrderItems, dbo.Orders, dbo.OrderSummary and dbo.Products.
Silver:
- Create cleaned views for Customers, Orders, OrderItems and Products using discovered target column names.
- Create vw_CustomerSales by joining Customers, Orders and OrderItems for completed orders.
- Create fn_CalculateOrderAmount(p_order_id INT).
- Create usp_LoadCustomerSales as an idempotent loader using MERGE.
- Create usp_LoadOrderSummary as an idempotent loader.
Gold:
- Create dim_customer, dim_product, fact_sales, vw_customer_sales_summary and vw_product_sales_summary.
Validate every identifier and wait for plan approval before generation."""


TABLES = {
    "Customers": ["CustomerID", "CustomerName", "Email", "Phone", "City", "State", "Country", "CustomerStatus", "CreatedDate", "ModifiedDate"],
    "CustomerSales": ["CustomerID", "CustomerName", "Country", "OrderCount", "TotalSales", "LoadDate"],
    "OrderItems": ["OrderItemID", "OrderID", "ProductID", "Quantity", "UnitPrice", "DiscountPercent"],
    "Orders": ["OrderID", "CustomerID", "OrderDate", "OrderStatus", "PaymentStatus", "ShippingCity", "ShippingCountry", "CreatedDate", "ModifiedDate"],
    "OrderSummary": ["OrderID", "CustomerID", "OrderDate", "OrderAmount", "LoadDate"],
    "Products": ["ProductID", "ProductName", "Category", "SubCategory", "UnitPrice", "CostPrice", "StockQuantity", "ProductStatus", "CreatedDate"],
}


def _seed(db, monkeypatch):
    project = ensure_project(db, "Release 7 Prompt Native")
    source = add_source(db, project.id, "SQLServer1", "localhost", "MigrationDemo")
    objects = []
    for table, columns in TABLES.items():
        objects.append({
            "schema": "dbo", "name": table, "type": "TABLE",
            "columns": [
                {"name": column, "type": "decimal" if column in {"UnitPrice", "CostPrice", "DiscountPercent", "TotalSales", "OrderAmount"} else "datetime" if column in {"CreatedDate", "ModifiedDate", "LoadDate"} else "date" if column == "OrderDate" else "varchar" if column in {"CustomerName", "Country", "Email", "Phone", "City", "State", "CustomerStatus", "PaymentStatus", "ShippingCity", "ShippingCountry", "ProductName", "Category", "SubCategory", "ProductStatus"} else "int", "nullable": True}
                for column in columns
            ],
        })
    ingest_snapshot(db, project.id, source.id, {"database": "MigrationDemo", "objects": objects})
    db.add(MigrationEnvironmentPlan(
        id=uid("EVP"), project_id=project.id, environment="DEV",
        catalog_name="migration_dev", status="PROVISIONED",
    ))
    db.add(MigrationDatabricksConfiguration(
        id=uid("DBC"), project_id=project.id,
        workspace_host="example.cloud.databricks.com", http_path="/sql/warehouses/test",
        token_env_key="PROMPT_TEST_TOKEN", status="READY",
    ))
    monkeypatch.setenv("PROMPT_TEST_TOKEN", "test-secret")
    db.commit()
    return project


def _answers(spec):
    recommended = {
        "completed_order_value": "COMPLETED",
        "customer_sales_target": "customer_sales_derived",
        "order_summary_target": "order_summary_derived",
        "dimension_scd_type": "TYPE_1",
        "fact_sales_grain": "ORDER_ITEM",
    }
    return {question["key"]: recommended[question["key"]] for question in spec["clarifications"]}


def test_prompt_is_versioned_grounded_and_requires_clarification(db, monkeypatch):
    project = _seed(db, monkeypatch)
    first = service.submit(db, project.id, PROMPT, "architect")
    assert first["status"] == "NEEDS_USER_INPUT"
    assert first["metadata_snapshot_id"]
    assert {item["type"] for item in first["artifacts"]} >= {
        "TABLE_COPY", "VIEW", "FUNCTION", "PROCEDURE_OR_WORKFLOW", "DIMENSION", "FACT", "SUMMARY_VIEW",
    }
    assert {question["key"] for question in first["clarifications"]} == {
        "completed_order_value", "customer_sales_target", "order_summary_target",
        "dimension_scd_type", "fact_sales_grain",
    }

    second = service.answer_clarifications(db, project.id, first["id"], _answers(first), "architect")
    assert second["version"] == 2
    assert second["status"] == "PENDING_PLAN_APPROVAL"
    assert all(item["grounding_status"] == "GROUNDED" for item in second["artifacts"])
    function = next(item for item in second["artifacts"] if item["name"].lower() == "fn_calculateorderamount")
    mappings = {item["source"]: item["target"] for item in function["identifier_mappings"]}
    assert mappings["dbo.OrderItems.UnitPrice"] == "order_items.unit_price"
    assert mappings["dbo.OrderItems.OrderID"] == "order_items.order_id"
    bronze_customers = next(item for item in second["artifacts"] if item["type"] == "TABLE_COPY" and item["name"] == "Customers")
    clean_customers = next(item for item in second["artifacts"] if item["name"] == "vw_customers_clean")
    assert bronze_customers["dependencies"] == []
    assert clean_customers["dependencies"] == [bronze_customers["request_id"]]
    versions = db.scalars(select(PromptSpecificationVersion).where(PromptSpecificationVersion.specification_id == first["id"])).all()
    assert len(versions) == 2


def test_plan_approval_generation_target_validation_and_review_are_separate(db, monkeypatch):
    project = _seed(db, monkeypatch)
    first = service.submit(db, project.id, PROMPT, "architect")
    current = service.answer_clarifications(db, project.id, first["id"], _answers(first), "architect")

    with pytest.raises(ValueError, match="approved before generation"):
        service.generate(db, project.id, first["id"], "architect")
    service.approve_plan(db, project.id, first["id"], "architect", "APPROVED", "Exact plan reviewed")
    generated = service.generate(db, project.id, first["id"], "architect")
    assert generated["status"] == "VALIDATING"
    assert all(item["validation_status"] == "TARGET_VALIDATION_REQUIRED" for item in generated["generated"])
    assert all(item["executable"] is False for item in generated["generated"])
    assert db.scalars(select(PromptPlanApproval).where(PromptPlanApproval.spec_version_id == current["version_id"])).first()

    monkeypatch.setattr(service, "execute_sql", lambda statement, safe_retry=True: [("plan",)])
    validated = service.validate_target(db, project.id, first["id"])
    assert validated["status"] == "PENDING_ARTIFACT_REVIEW"
    assert all(item["status"] == "PASSED" for item in validated["artifacts"])

    trace = service.trace(db, project.id, first["id"])
    function = next(item for item in trace["requirements"] if "fn_calculate_order_amount" in item["target_fqn"].lower())
    version = db.get(MigrationStageArtifactVersion, function["artifact_version_id"])
    assert "p_order_id INT" in version.content
    assert "oi.order_id = p_order_id" in version.content
    assert "fn_CalculateOrderAmount`.`OrderID" not in version.content

    loader = next(item for item in trace["requirements"] if "usp_load_customer_sales" in item["target_fqn"].lower())
    loader_version = db.get(MigrationStageArtifactVersion, loader["artifact_version_id"])
    assert "MERGE INTO" in loader_version.content
    assert "WHEN NOT MATCHED BY SOURCE" not in loader_version.content

    for item in trace["requirements"]:
        service.review_artifact(db, project.id, first["id"], item["artifact_version_id"], "APPROVED", "architect")
    assert service.detail(db, project.id, first["id"])["status"] == "ARTIFACTS_APPROVED"


def test_unknown_required_column_blocks_plan_approval(db, monkeypatch):
    project = _seed(db, monkeypatch)
    # Remove UnitPrice from the bound discovery before creating the snapshot.
    from app.models.entities import MigrationColumn, MigrationObject
    order_items = db.scalar(select(MigrationObject).where(
        MigrationObject.project_id == project.id,
        MigrationObject.object_name == "OrderItems",
    ))
    unit_price = db.scalar(select(MigrationColumn).where(
        MigrationColumn.object_id == order_items.id,
        MigrationColumn.column_name == "UnitPrice",
    ))
    db.delete(unit_price)
    db.commit()
    first = service.submit(db, project.id, PROMPT, "architect")
    second = service.answer_clarifications(db, project.id, first["id"], _answers(first), "architect")
    assert second["status"] == "NEEDS_USER_INPUT"
    blocked = [item for item in second["artifacts"] if item["grounding_status"] == "UNKNOWN"]
    assert blocked
    assert any("UnitPrice" in error for item in blocked for error in item["requirements"]["grounding_errors"])
    with pytest.raises(ValueError, match="fully grounded"):
        service.approve_plan(db, project.id, first["id"], "architect", "APPROVED")


def test_deployment_requires_all_current_artifacts_approved(db, monkeypatch):
    project = _seed(db, monkeypatch)
    first = service.submit(db, project.id, PROMPT, "architect")
    service.answer_clarifications(db, project.id, first["id"], _answers(first), "architect")
    service.approve_plan(db, project.id, first["id"], "architect", "APPROVED")
    service.generate(db, project.id, first["id"], "architect")
    with pytest.raises(ValueError, match="validated, executable, and approved"):
        service.deploy_dev(db, project.id, first["id"], "architect")


def test_prompt_native_api_exposes_versioned_plan(client, auth_headers, db, monkeypatch):
    project = _seed(db, monkeypatch)
    created = client.post(
        f"/api/projects/{project.id}/prompt-specifications",
        json={"prompt": PROMPT}, headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["version"] == 1 and body["status"] == "NEEDS_USER_INPUT"
    plan = client.get(
        f"/api/projects/{project.id}/prompt-specifications/{body['id']}/plan",
        headers=auth_headers,
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["metadata_snapshot_id"] == body["metadata_snapshot_id"]


def test_prompt_native_dev_uses_every_approved_canonical_bronze_target(db, monkeypatch):
    project = _seed(db, monkeypatch)
    first = service.submit(db, project.id, PROMPT, "architect")
    service.answer_clarifications(db, project.id, first["id"], _answers(first), "architect")
    service.approve_plan(db, project.id, first["id"], "architect", "APPROVED")
    service.generate(db, project.id, first["id"], "architect")
    monkeypatch.setattr(service, "execute_sql", lambda *a, **k: [("plan",)])
    service.validate_target(db, project.id, first["id"])
    trace = service.trace(db, project.id, first["id"])
    for item in trace["requirements"]:
        service.review_artifact(
            db, project.id, first["id"], item["artifact_version_id"],
            "APPROVED", "architect",
        )

    loaded = []
    def loader(*args, **kwargs):
        loaded.append(kwargs["target_fqn"])
        return {"object_id": args[4].id, "target_fqn": kwargs["target_fqn"],
                "status": "PASSED", "rows_loaded": 1, "target_rows": 1}

    monkeypatch.setattr(bronze_ingestion, "_load_table", loader)
    monkeypatch.setattr(databricks_client, "execute_sql", lambda *a, **k: [])
    monkeypatch.setattr(deployment, "databricks_workspace_identity", lambda: "qa-workspace")
    monkeypatch.setattr(deployment, "run_reconciliation", lambda *a, **k: {"status": "PASSED"})
    monkeypatch.setattr(deployment, "evaluate_dev_gate", lambda *a, **k: {"status": "PASSED"})

    result = service.deploy_dev(db, project.id, first["id"], "architect")

    assert result["status"] == "DEV_GATE_PASSED"
    assert set(loaded) == {
        "`migration_dev`.`bronze`.`customers`",
        "`migration_dev`.`bronze`.`customer_sales`",
        "`migration_dev`.`bronze`.`order_items`",
        "`migration_dev`.`bronze`.`orders`",
        "`migration_dev`.`bronze`.`order_summary`",
        "`migration_dev`.`bronze`.`products`",
    }
