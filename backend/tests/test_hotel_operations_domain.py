import pytest
from sqlalchemy import select

from app.models.entities import (
    MigrationDatabricksConfiguration,
    MigrationEnvironmentPlan,
    MigrationStageArtifactVersion,
    PromptSpecificationVersion,
)
from app.services import prompt_specification as service
from app.services.engine import add_source, ensure_project, ingest_snapshot, uid


def test_hotel_operations_domain_grounding_and_function_generation(db, monkeypatch):
    """
    Verifies that the HotelOperationsDemo domain:
    1. Fully and dynamically grounds fn_calculate_booking_amount across Bookings and Rooms.
    2. Has 0 UNKNOWN grounding blockers.
    3. Advances from NEEDS_USER_INPUT to PENDING_PLAN_APPROVAL after clarifications.
    4. Generates multi-table Databricks SQL for the function with correct aliases and joins.
    """
    project = ensure_project(db, "Hotel Operations Migration Project")
    source = add_source(db, project.id, "SQLServer_Hotel", "sql-hotel.internal", "HotelOperationsDemo")

    tables = {
        "Hotels": [
            ("HotelID", "int"), ("HotelName", "varchar"), ("City", "varchar"),
            ("Country", "varchar"), ("StarRating", "int"), ("IsActive", "bit"),
            ("CreatedDate", "datetime"),
        ],
        "Guests": [
            ("GuestID", "int"), ("GuestName", "varchar"), ("EmailAddress", "varchar"),
            ("PhoneNumber", "varchar"), ("Country", "varchar"), ("LoyaltyLevel", "varchar"),
            ("RegisteredDate", "datetime"), ("IsActive", "bit"),
        ],
        "Rooms": [
            ("RoomID", "int"), ("HotelID", "int"), ("RoomNumber", "varchar"),
            ("RoomType", "varchar"), ("MaximumGuests", "int"), ("NightlyRate", "decimal"),
            ("RoomStatus", "varchar"), ("IsActive", "bit"),
        ],
        "Bookings": [
            ("BookingID", "int"), ("GuestID", "int"), ("RoomID", "int"),
            ("BookingReference", "varchar"), ("BookingDate", "date"),
            ("CheckInDate", "date"), ("CheckOutDate", "date"),
            ("NumberOfGuests", "int"), ("DiscountPercent", "decimal"),
            ("BookingStatus", "varchar"), ("LastUpdatedDate", "datetime"),
        ],
        "Payments": [
            ("PaymentID", "int"), ("BookingID", "int"), ("PaymentDate", "datetime"),
            ("PaymentAmount", "decimal"), ("PaymentMethod", "varchar"),
            ("PaymentStatus", "varchar"), ("TransactionCode", "varchar"),
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

    ingest_snapshot(db, project.id, source.id, {"database": "HotelOperationsDemo", "objects": objects})

    db.add(MigrationEnvironmentPlan(
        id=uid("EVP"), project_id=project.id, environment="DEV",
        catalog_name="hotel_dev", status="PROVISIONED",
    ))
    db.add(MigrationDatabricksConfiguration(
        id=uid("DBC"), project_id=project.id,
        workspace_host="hotel.cloud.databricks.com", http_path="/sql/warehouses/hotel",
        token_env_key="HOTEL_DATABRICKS_TOKEN", status="READY",
    ))
    monkeypatch.setenv("HOTEL_DATABRICKS_TOKEN", "hotel-secret-token")
    db.commit()

    prompt = """Migrate the HotelOperationsDemo SQL Server database to Databricks using the Bronze, Silver, and Gold Medallion architecture.

Bronze:
Ingest all discovered source tables, including Hotels, Guests, Rooms, Bookings, and Payments, while preserving source data types and adding migration audit columns.

Silver:
Create cleaned and standardized views for every source table.

Create a Silver transformation view named vw_booking_details that combines Bookings, Guests, Rooms, and Hotels. Include booking reference, guest details, hotel information, room details, check-in date, check-out date, number of nights, nightly rate, discount percentage, booking status, and calculated booking amount.

Create a scalar function named fn_calculate_booking_amount that accepts a booking ID and calculates:

number of nights × nightly room rate × (1 − discount percentage / 100)

Create an idempotent procedure or Databricks workflow named usp_load_hotel_revenue that loads completed hotel revenue using Bookings, Rooms, Hotels, and Payments. The loading strategy and the value representing a completed booking must be clarified before SQL generation.

Gold:
Create a guest dimension, hotel dimension, room dimension, booking fact table, and monthly hotel revenue summary view.

The application must determine or clarify:
- The completed BookingStatus value
- The fact_booking grain
- Natural business keys for every dimension
- SCD Type 1 or Type 2 policy for each dimension
- Whether revenue uses calculated booking amount or completed payment amount
- The idempotent loading strategy for usp_load_hotel_revenue
- The date used for monthly revenue grouping

Validate every table and column against the discovery snapshot. Do not invent identifiers. Show all clarification questions and the complete grounded plan for approval before generating or deploying artifacts."""

    # 1. Submit prompt
    spec = service.submit(db, project.id, prompt, "hotel_architect")
    assert spec["status"] == "NEEDS_USER_INPUT"

    # Verify fn_calculate_booking_amount has 0 grounding errors (no UNKNOWN Bookings.OrderID blockers)
    fn_req = next(item for item in spec["artifacts"] if item["name"] == "fn_calculate_booking_amount")
    assert fn_req["requirements"].get("grounding_errors", []) == []
    assert fn_req["grounding_status"] in {"GROUNDED", "NEEDS_INPUT"}
    assert set(fn_req["source_refs"]) == {"Bookings", "Rooms"}
    assert fn_req["requirements"]["parameters"] == [{"name": "p_booking_id", "type": "INT"}]
    assert "DATEDIFF" in fn_req["requirements"]["calculation"]
    assert "nightly_rate" in fn_req["requirements"]["calculation"]
    assert "discount_percent" in fn_req["requirements"]["calculation"]

    # Verify identifier mappings
    mappings = {item["source"]: item["target"] for item in fn_req["identifier_mappings"]}
    assert "dbo.Bookings.BookingID" in mappings
    assert "dbo.Rooms.NightlyRate" in mappings

    # 2. Answer clarifications
    answers = {q["key"]: q["recommended_answer"] for q in spec["clarifications"]}
    plan = service.answer_clarifications(db, project.id, spec["id"], answers, "hotel_architect")

    # MUST cleanly advance to PENDING_PLAN_APPROVAL with all artifacts fully GROUNDED
    assert plan["status"] == "PENDING_PLAN_APPROVAL"
    fn_plan = next(item for item in plan["artifacts"] if item["name"] == "fn_calculate_booking_amount")
    assert fn_plan["grounding_status"] == "GROUNDED"
    assert fn_plan["requirements"].get("grounding_errors", []) == []

    # 3. Approve plan and generate SQL
    service.approve_plan(db, project.id, spec["id"], "hotel_architect", "APPROVED", "Approved hotel plan")
    gen_result = service.generate(db, project.id, spec["id"], "hotel_architect")
    assert gen_result["status"] == "VALIDATING"

    # 4. Target validation and inspect generated SQL
    monkeypatch.setattr(service, "execute_sql", lambda statement, safe_retry=True: [("plan",)])
    service.validate_target(db, project.id, spec["id"])

    trace = service.trace(db, project.id, spec["id"])
    fn_trace = next(item for item in trace["requirements"] if "fn_calculate_booking_amount" in item["target_fqn"].lower())
    fn_ver = db.get(MigrationStageArtifactVersion, fn_trace["artifact_version_id"])
    fn_sql = fn_ver.content

    # Verify that clean views were generated for all 5 tables
    clean_views = {item["name"] for item in spec["artifacts"] if item["type"] == "VIEW" and "clean" in item["name"]}
    assert clean_views == {"vw_bookings_clean", "vw_guests_clean", "vw_rooms_clean", "vw_hotels_clean", "vw_payments_clean"}

    # Verify fn_calculate_booking_amount upstream dependencies include vw_bookings_clean and vw_rooms_clean
    booking_clean = next(item for item in spec["artifacts"] if item["name"] == "vw_bookings_clean")
    room_clean = next(item for item in spec["artifacts"] if item["name"] == "vw_rooms_clean")
    assert booking_clean["request_id"] in fn_req["dependencies"]
    assert room_clean["request_id"] in fn_req["dependencies"]

    # Assert correct Databricks SQL structure
    assert "CREATE OR REPLACE FUNCTION" in fn_sql
    assert "p_booking_id INT" in fn_sql
    assert "vw_bookings_clean" in fn_sql
    assert "vw_rooms_clean" in fn_sql
    assert "DATEDIFF(day, b.check_in_date, b.check_out_date)" in fn_sql
    assert "r.nightly_rate" in fn_sql
    assert "b.booking_id = p_booking_id" in fn_sql
    assert "OrderID" not in fn_sql
    assert "MigrationDemo" not in fn_sql

    # Verify vw_booking_details has zero duplicate column names and zero 1 = 1 cross joins
    vbd_trace = next(item for item in trace["requirements"] if "vw_booking_details" in item["target_fqn"].lower())
    vbd_ver = db.get(MigrationStageArtifactVersion, vbd_trace["artifact_version_id"])
    vbd_sql = vbd_ver.content
    assert "CREATE OR REPLACE VIEW" in vbd_sql
    assert "vw_booking_details" in vbd_sql
    assert "1 = 1" not in vbd_sql, "Multi-table join should connect via ER graph relationships without cross joins"

    import re
    select_match = re.search(r"SELECT\s+(.*?)\s+FROM", vbd_sql, re.DOTALL | re.IGNORECASE)
    assert select_match is not None
    select_exprs = [e.strip() for e in select_match.group(1).split(",\n")]
    output_cols = []
    for expr in select_exprs:
        if " AS " in expr.upper():
            output_cols.append(re.split(r"\s+AS\s+", expr, flags=re.IGNORECASE)[-1].strip().strip("`"))
        else:
            output_cols.append(expr.split(".")[-1].strip().strip("`"))
    assert len(output_cols) == len(set(output_cols)), f"Duplicate columns found in vw_booking_details: {output_cols}"


    # 5. Approve all artifacts and verify deployment order
    for item in trace["requirements"]:
        service.review_artifact(db, project.id, spec["id"], item["artifact_version_id"], "APPROVED", "hotel_architect")

    from app.services import bronze_ingestion, databricks_client, deployment
    executed_statements = []
    loaded_tables = []

    def mock_loader(*args, **kwargs):
        loaded_tables.append(kwargs["target_fqn"])
        return {"object_id": args[4].id, "target_fqn": kwargs["target_fqn"], "status": "PASSED", "rows_loaded": 1, "target_rows": 1}

    def mock_execute(statement, *args, **kwargs):
        executed_statements.append(statement)
        return []

    monkeypatch.setattr(bronze_ingestion, "_load_table", mock_loader)
    monkeypatch.setattr(databricks_client, "execute_sql", mock_execute)
    monkeypatch.setattr(deployment, "databricks_workspace_identity", lambda: "qa-workspace")
    monkeypatch.setattr(deployment, "run_reconciliation", lambda *a, **k: {"status": "PASSED"})
    monkeypatch.setattr(deployment, "evaluate_dev_gate", lambda *a, **k: {"status": "PASSED"})

    dev_deploy = service.deploy_dev(db, project.id, spec["id"], "hotel_architect")
    assert dev_deploy["status"] == "DEV_GATE_PASSED"

    # Verify that vw_bookings_clean was deployed BEFORE fn_calculate_booking_amount
    booking_clean_idx = next(i for i, stmt in enumerate(executed_statements) if "vw_bookings_clean" in stmt)
    fn_calc_idx = next(i for i, stmt in enumerate(executed_statements) if "fn_calculate_booking_amount" in stmt)
    assert booking_clean_idx < fn_calc_idx, "vw_bookings_clean must be deployed before fn_calculate_booking_amount"
