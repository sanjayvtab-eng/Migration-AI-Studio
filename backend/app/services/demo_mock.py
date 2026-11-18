"""
Demo Mock Provider for vtabpublicuser@gmail.com
Provides reliable, zero-dependency mock data for presentations
mirroring the real SQL Server Express LogisticsMiniDemo database.
"""

from datetime import datetime
from typing import Any, Dict

DEMO_MOCK_USER = "vtabpublicuser@gmail.com"


def _snake(value: str) -> str:
    import re
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value or "")
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()


def is_demo_user(username_or_email: str | None) -> bool:
    # Mockups disabled: vtabpublicuser@gmail.com now runs full real logic just like all other accounts
    return False


def get_demo_mock_snapshot(database_name: str = "LogisticsMiniDemo") -> Dict[str, Any]:
    objects = [
            {
                "schema": "dbo",
                "name": "Branches",
                "type": "TABLE",
                "approx_row_count": 100,
                "columns": [
                    {"name": "BranchID", "type": "int", "precision": 10, "scale": 0, "nullable": False, "identity": True},
                    {"name": "BranchName", "type": "nvarchar", "max_length": 100, "nullable": False},
                    {"name": "City", "type": "nvarchar", "max_length": 80, "nullable": False},
                    {"name": "StateName", "type": "nvarchar", "max_length": 80, "nullable": False},
                    {"name": "Country", "type": "nvarchar", "max_length": 60, "nullable": False},
                    {"name": "ServiceRadiusKM", "type": "int", "precision": 10, "scale": 0, "nullable": False},
                    {"name": "BranchStatus", "type": "nvarchar", "max_length": 20, "nullable": False},
                ],
                "constraints": [
                    {"name": "PK_Branches_BranchID", "type": "PRIMARY KEY", "columns": ["BranchID"]},
                ],
            },
            {
                "schema": "dbo",
                "name": "Drivers",
                "type": "TABLE",
                "approx_row_count": 300,
                "columns": [
                    {"name": "DriverID", "type": "int", "precision": 10, "scale": 0, "nullable": False, "identity": True},
                    {"name": "DriverName", "type": "nvarchar", "max_length": 100, "nullable": False},
                    {"name": "Email", "type": "nvarchar", "max_length": 150, "nullable": False},
                    {"name": "Phone", "type": "nvarchar", "max_length": 20, "nullable": False},
                    {"name": "HireDate", "type": "date", "nullable": False},
                    {"name": "DriverStatus", "type": "nvarchar", "max_length": 20, "nullable": False},
                    {"name": "BranchID", "type": "int", "precision": 10, "scale": 0, "nullable": False},
                ],
                "constraints": [
                    {"name": "PK_Drivers_DriverID", "type": "PRIMARY KEY", "columns": ["DriverID"]},
                    {"name": "UQ_Drivers_Email", "type": "UNIQUE", "columns": ["Email"]},
                    {"name": "FK_Drivers_BranchID", "type": "FOREIGN KEY", "columns": ["BranchID"], "referenced_table": "Branches"},
                ],
            },
            {
                "schema": "dbo",
                "name": "Vehicles",
                "type": "TABLE",
                "approx_row_count": 300,
                "columns": [
                    {"name": "VehicleID", "type": "int", "precision": 10, "scale": 0, "nullable": False, "identity": True},
                    {"name": "RegistrationNo", "type": "nvarchar", "max_length": 30, "nullable": False},
                    {"name": "VehicleType", "type": "nvarchar", "max_length": 40, "nullable": False},
                    {"name": "LoadCapacityKG", "type": "decimal", "precision": 10, "scale": 2, "nullable": False},
                    {"name": "OdometerKM", "type": "int", "precision": 10, "scale": 0, "nullable": False},
                    {"name": "PurchaseDate", "type": "date", "nullable": False},
                    {"name": "VehicleStatus", "type": "nvarchar", "max_length": 20, "nullable": False},
                    {"name": "BranchID", "type": "int", "precision": 10, "scale": 0, "nullable": False},
                ],
                "constraints": [
                    {"name": "PK_Vehicles_VehicleID", "type": "PRIMARY KEY", "columns": ["VehicleID"]},
                    {"name": "UQ_Vehicles_RegistrationNo", "type": "UNIQUE", "columns": ["RegistrationNo"]},
                    {"name": "FK_Vehicles_BranchID", "type": "FOREIGN KEY", "columns": ["BranchID"], "referenced_table": "Branches"},
                ],
            },
            {
                "schema": "dbo",
                "name": "Shipments",
                "type": "TABLE",
                "approx_row_count": 1300,
                "columns": [
                    {"name": "ShipmentID", "type": "int", "precision": 10, "scale": 0, "nullable": False, "identity": True},
                    {"name": "CustomerName", "type": "nvarchar", "max_length": 120, "nullable": False},
                    {"name": "CustomerEmail", "type": "nvarchar", "max_length": 150, "nullable": False},
                    {"name": "DriverID", "type": "int", "precision": 10, "scale": 0, "nullable": False},
                    {"name": "VehicleID", "type": "int", "precision": 10, "scale": 0, "nullable": False},
                    {"name": "BranchID", "type": "int", "precision": 10, "scale": 0, "nullable": False},
                    {"name": "TrackingNo", "type": "nvarchar", "max_length": 40, "nullable": False},
                    {"name": "ShipmentDate", "type": "date", "nullable": False},
                    {"name": "ShipmentWeightKG", "type": "decimal", "precision": 10, "scale": 2, "nullable": False},
                    {"name": "ShipmentStatus", "type": "nvarchar", "max_length": 20, "nullable": False},
                    {"name": "ShippingCharge", "type": "decimal", "precision": 10, "scale": 2, "nullable": False},
                ],
                "constraints": [
                    {"name": "PK_Shipments_ShipmentID", "type": "PRIMARY KEY", "columns": ["ShipmentID"]},
                    {"name": "UQ_Shipments_TrackingNo", "type": "UNIQUE", "columns": ["TrackingNo"]},
                    {"name": "FK_Shipments_DriverID", "type": "FOREIGN KEY", "columns": ["DriverID"], "referenced_table": "Drivers"},
                    {"name": "FK_Shipments_VehicleID", "type": "FOREIGN KEY", "columns": ["VehicleID"], "referenced_table": "Vehicles"},
                    {"name": "FK_Shipments_BranchID", "type": "FOREIGN KEY", "columns": ["BranchID"], "referenced_table": "Branches"},
                ],
            },
            {
                "schema": "dbo",
                "name": "Customers",
                "type": "TABLE",
                "approx_row_count": 500,
                "columns": [
                    {"name": "CustomerID", "type": "int", "precision": 10, "scale": 0, "nullable": False, "identity": True},
                    {"name": "CustomerName", "type": "nvarchar", "max_length": 120, "nullable": False},
                    {"name": "Email", "type": "nvarchar", "max_length": 150, "nullable": False},
                    {"name": "Phone", "type": "nvarchar", "max_length": 20, "nullable": False},
                    {"name": "City", "type": "nvarchar", "max_length": 80, "nullable": False},
                    {"name": "Country", "type": "nvarchar", "max_length": 60, "nullable": False},
                    {"name": "CustomerType", "type": "nvarchar", "max_length": 30, "nullable": False},
                ],
                "constraints": [
                    {"name": "PK_Customers_CustomerID", "type": "PRIMARY KEY", "columns": ["CustomerID"]},
                    {"name": "UQ_Customers_Email", "type": "UNIQUE", "columns": ["Email"]},
                ],
            },
            {
                "schema": "dbo",
                "name": "DeliveryRoutes",
                "type": "TABLE",
                "approx_row_count": 250,
                "columns": [
                    {"name": "RouteID", "type": "int", "precision": 10, "scale": 0, "nullable": False, "identity": True},
                    {"name": "RouteName", "type": "nvarchar", "max_length": 100, "nullable": False},
                    {"name": "OriginBranchID", "type": "int", "precision": 10, "scale": 0, "nullable": False},
                    {"name": "DestinationCity", "type": "nvarchar", "max_length": 80, "nullable": False},
                    {"name": "DistanceKM", "type": "decimal", "precision": 8, "scale": 2, "nullable": False},
                    {"name": "EstimatedHours", "type": "decimal", "precision": 4, "scale": 1, "nullable": False},
                ],
                "constraints": [
                    {"name": "PK_DeliveryRoutes_RouteID", "type": "PRIMARY KEY", "columns": ["RouteID"]},
                    {"name": "FK_DeliveryRoutes_OriginBranchID", "type": "FOREIGN KEY", "columns": ["OriginBranchID"], "referenced_table": "Branches"},
                ],
            },
        ]

    # Normalize every column with both type and data_type, target_name, ordinal, nullable, identity
    for obj in objects:
        for idx, col in enumerate(obj.get("columns", []), 1):
            dtype = col.get("data_type") or col.get("type", "nvarchar")
            col["data_type"] = dtype
            col["type"] = dtype
            col["target_name"] = col.get("target_name") or _snake(col["name"])
            col["ordinal"] = col.get("ordinal", idx)
            is_ident = bool(col.get("is_identity") or col.get("identity", False))
            col["is_identity"] = is_ident
            col["identity"] = is_ident
            if "nullable" not in col:
                col["nullable"] = False if is_ident else True

    return {
        "database": database_name,
        "engine": "SQLSERVER",
        "captured_at": datetime.utcnow().isoformat(),
        "objects": objects,
    }


def get_demo_mock_test_result(source: Any) -> Dict[str, Any]:
    return {
        "ok": True,
        "status": "SUCCESS",
        "latency_ms": 12,
        "message": f"Connected to SQL Server 2022 Express ({getattr(source, 'database_name', 'LogisticsMiniDemo')}) • Demo Mock Runtime Verified",
        "engine": getattr(source, "engine", "SQLSERVER") or "SQLSERVER",
        "server_name": getattr(source, "server_name", r"localhost\SQLEXPRESS"),
        "database_name": getattr(source, "database_name", "LogisticsMiniDemo"),
        "profile_name": getattr(source, "profile_name", "SQLServer1"),
        "tables_count": 6,
        "version": "Microsoft SQL Server 2022 (RTM) - 16.0.1000.6 (X64) Express Edition (Demo Mode)",
    }


def get_demo_connector_info(source_id: str) -> Dict[str, Any]:
    return {
        "mode": "CONNECTOR",
        "status": "ONLINE",
        "last_seen": datetime.utcnow().isoformat(),
        "source_id": source_id,
        "mock": True,
        "note": "Demo Presentation Agent - Simulated Active Heartbeat",
    }


def submit_demo_prompt_specification(db: Any, project_id: str, prompt: str, actor: str) -> Dict[str, Any]:
    """
    Submits a 100% grounded, pre-satisfied prompt specification for LogisticsMiniDemo.
    Prevents clarification questions and produces 20 Medallion artifacts ready for approval.
    """
    import json
    from app.models.entities import (
        MigrationSource,
        MigrationMetadataSnapshot,
        MigrationEnvironmentPlan,
        PromptSpecification,
        PromptSpecificationVersion,
        PromptArtifactRequest,
        PromptClarification,
        MigrationObject,
    )
    from app.services.engine import uid, ingest_snapshot, classify_project, create_mappings
    from app.services import prompt_specification

    # 1. Ensure source
    source = db.query(MigrationSource).filter(MigrationSource.project_id == project_id).first()
    if not source:
        source = MigrationSource(
            id=uid("SRC"),
            project_id=project_id,
            profile_name="SQLServer1",
            engine="SQLSERVER",
            server_name=r"localhost\SQLEXPRESS",
            database_name="LogisticsMiniDemo",
        )
        db.add(source)
        db.flush()

    # 2. Ensure snapshot & discovery objects are hydrated with full schema
    snap_payload = get_demo_mock_snapshot("LogisticsMiniDemo")

    existing_objs = db.query(MigrationObject).filter(MigrationObject.project_id == project_id).count()
    if existing_objs == 0:
        ingest_snapshot(db, project_id, source.id, snap_payload)
        try:
            classify_project(db, project_id)
            create_mappings(db, project_id, "DEV", "logistics_demo_dev")
        except Exception:
            pass

    objs = db.query(MigrationObject).filter(MigrationObject.project_id == project_id).all()
    obj_by_name = {o.object_name.lower(): o.id for o in objs}
    for item in snap_payload.get("objects", []):
        if item.get("name", "").lower() in obj_by_name:
            item["object_id"] = obj_by_name[item["name"].lower()]

    snapshot_row = db.query(MigrationMetadataSnapshot).filter(
        MigrationMetadataSnapshot.project_id == project_id,
        MigrationMetadataSnapshot.source_id == source.id,
    ).order_by(MigrationMetadataSnapshot.created_at.desc()).first()

    if not snapshot_row:
        snapshot_row = MigrationMetadataSnapshot(
            id=uid("SNP"),
            project_id=project_id,
            source_id=source.id,
            content_hash="demo_hash_logistics",
            payload_json=json.dumps(snap_payload),
            created_at=datetime.utcnow(),
        )
        db.add(snapshot_row)
        db.flush()
    else:
        snapshot_row.payload_json = json.dumps(snap_payload)
        db.flush()

    # 3. Ensure dev environment plan
    plan_row = db.query(MigrationEnvironmentPlan).filter(
        MigrationEnvironmentPlan.project_id == project_id,
        MigrationEnvironmentPlan.environment == "DEV",
    ).first()
    if not plan_row:
        plan_row = MigrationEnvironmentPlan(
            id=uid("ENV"),
            project_id=project_id,
            environment="DEV",
            catalog_name="logistics_demo_dev",
            schemas_json=json.dumps(["bronze", "silver", "gold"]),
            status="PROVISIONED",
            created_at=datetime.utcnow(),
        )
        db.add(plan_row)
        db.flush()
    else:
        plan_row.status = "PROVISIONED"
        db.flush()

    # 4. Create PromptSpecification
    spec = PromptSpecification(
        id=uid("PSP"),
        project_id=project_id,
        source_id=source.id,
        target_environment="DEV",
        current_status="PENDING_PLAN_APPROVAL",
        created_by=actor,
        created_at=datetime.utcnow(),
    )
    db.add(spec)
    db.flush()

    # 5. Create Version with closed clarifications
    answers = {
        "dimension_scd_type": "TYPE_1",
        "fact_shipments_grain": "SHIPMENTS_LINE",
    }
    version = PromptSpecificationVersion(
        id=uid("PSV"),
        specification_id=spec.id,
        project_id=project_id,
        version=1,
        original_prompt=prompt.strip(),
        metadata_snapshot_id=snapshot_row.id,
        checksum="demo_logistics_checksum_100",
        parsed_json=json.dumps({"answers": answers}),
        created_by=actor,
        created_at=datetime.utcnow(),
    )
    db.add(version)
    db.flush()

    spec.current_version_id = version.id

    # 6. Create 20 Artifact Requests (6 Bronze, 8 Silver, 6 Gold)
    artifact_definitions = [
        # Bronze Layer (6)
        ("REQ-B-TAB-001", "Branches", "TABLE_COPY", "BRONZE", "Traceable raw copy of dbo.Branches", ["Branches"], []),
        ("REQ-B-TAB-002", "Customers", "TABLE_COPY", "BRONZE", "Traceable raw copy of dbo.Customers", ["Customers"], []),
        ("REQ-B-TAB-003", "DeliveryRoutes", "TABLE_COPY", "BRONZE", "Traceable raw copy of dbo.DeliveryRoutes", ["DeliveryRoutes"], []),
        ("REQ-B-TAB-004", "Drivers", "TABLE_COPY", "BRONZE", "Traceable raw copy of dbo.Drivers", ["Drivers"], []),
        ("REQ-B-TAB-005", "Shipments", "TABLE_COPY", "BRONZE", "Traceable raw copy of dbo.Shipments", ["Shipments"], []),
        ("REQ-B-TAB-006", "Vehicles", "TABLE_COPY", "BRONZE", "Traceable raw copy of dbo.Vehicles", ["Vehicles"], []),
        # Silver Layer (8)
        ("REQ-S-VIE-007", "vw_branches_clean", "VIEW", "SILVER", "Cleaned and conformed Branches entity", ["Branches"], ["REQ-B-TAB-001"]),
        ("REQ-S-VIE-008", "vw_customers_clean", "VIEW", "SILVER", "Cleaned and conformed Customers entity", ["Customers"], ["REQ-B-TAB-002"]),
        ("REQ-S-VIE-009", "vw_deliveryroutes_clean", "VIEW", "SILVER", "Cleaned and conformed DeliveryRoutes entity", ["DeliveryRoutes"], ["REQ-B-TAB-003"]),
        ("REQ-S-VIE-010", "vw_drivers_clean", "VIEW", "SILVER", "Cleaned and conformed Drivers entity", ["Drivers"], ["REQ-B-TAB-004"]),
        ("REQ-S-VIE-011", "vw_shipments_clean", "VIEW", "SILVER", "Cleaned and conformed Shipments entity", ["Shipments"], ["REQ-B-TAB-005"]),
        ("REQ-S-VIE-012", "vw_vehicles_clean", "VIEW", "SILVER", "Cleaned and conformed Vehicles entity", ["Vehicles"], ["REQ-B-TAB-006"]),
        ("REQ-S-FUN-013", "fn_calculate_shipping_charges_per_kg", "FUNCTION", "SILVER", "Calculate shipping charge per kilogram", ["Shipments"], ["REQ-S-VIE-011"]),
        ("REQ-S-PRC-014", "usp_mergedailysummary", "PROCEDURE_OR_WORKFLOW", "SILVER", "Idempotent daily summary merge loader keyed by primary keys", ["Shipments"], ["REQ-S-VIE-011", "REQ-S-VIE-010", "REQ-S-VIE-007"]),
        # Gold Layer (6)
        ("REQ-G-DIM-015", "dim_branches", "DIMENSION", "GOLD", "Conformed branches dimension table", ["Branches"], ["REQ-S-VIE-007"]),
        ("REQ-G-DIM-016", "dim_drivers", "DIMENSION", "GOLD", "Conformed drivers dimension table", ["Drivers"], ["REQ-S-VIE-010"]),
        ("REQ-G-DIM-017", "dim_vehicles", "DIMENSION", "GOLD", "Conformed vehicles dimension table", ["Vehicles"], ["REQ-S-VIE-012"]),
        ("REQ-G-DIM-018", "dim_customers", "DIMENSION", "GOLD", "Conformed customers dimension table", ["Customers"], ["REQ-S-VIE-008"]),
        ("REQ-G-FAC-019", "fact_shipments", "FACT", "GOLD", "Logistics shipments fact table with dimensional foreign keys", ["Shipments"], ["REQ-S-VIE-011", "REQ-G-DIM-015", "REQ-G-DIM-016", "REQ-G-DIM-017", "REQ-G-DIM-018"]),
        ("REQ-G-SUM-020", "monthly_executive_kpi_aggregation_marts", "SUMMARY_VIEW", "GOLD", "Monthly executive KPI logistics aggregation mart", ["Shipments"], ["REQ-G-FAC-019", "REQ-G-DIM-015"]),
    ]

    for req_id, name, kind, layer, purpose, src_refs, deps in artifact_definitions:
        req = PromptArtifactRequest(
            id=uid("PAR"),
            project_id=project_id,
            spec_version_id=version.id,
            request_id=req_id,
            name=name,
            artifact_type=kind,
            layer=layer,
            grounding_status="GROUNDED",
            source_refs_json=json.dumps(src_refs),
            dependencies_json=json.dumps(deps),
            structured_json=json.dumps({"purpose": purpose, "load_strategy": "FULL_LOAD", "view_kind": "CLEAN" if kind == "VIEW" else None}),
            identifier_mappings_json=json.dumps([]),
            assumptions_json=json.dumps(["Preserves SQL Server data fidelity and Unity Catalog naming standards"]),
        )
        db.add(req)

    db.commit()
    return get_demo_prompt_specification_detail(db, project_id, spec.id)


def get_demo_prompt_specification_detail(db: Any, project_id: str, specification_id: str) -> Dict[str, Any]:
    """Returns 100% Grounding Match analysis and clean metadata for demo presentation."""
    from app.services import prompt_specification
    detail = prompt_specification.detail(db, project_id, specification_id)

    detail["analysis"] = {
        "accuracy_score": 100.0,
        "score_basis": "100% Grounded against SQL Server source metadata • Demo presentation mode",
        "coverage_percent": 100.0,
        "explicit_entities_count": 6,
        "inferred_additions_count": 14,
        "total_source_tables": 6,
        "grounded_sources": [
            "Branches",
            "Customers",
            "DeliveryRoutes",
            "Drivers",
            "Shipments",
            "Vehicles",
        ],
        "missing_keys": [],
        "blocking_artifacts_count": 0,
        "warnings": [],
        "status": "GROUNDED",
    }
    detail["clarifications"] = []
    return detail


def validate_demo_target(db: Any, project_id: str, specification_id: str) -> Dict[str, Any]:
    """Validates the 20 artifacts against simulated Databricks DEV control plane."""
    import json
    from app.models.entities import PromptSpecification, RequirementArtifactTrace, MigrationStageArtifactVersion, MigrationMedallionNode
    from app.services import prompt_specification

    spec = db.get(PromptSpecification, specification_id)
    if not spec:
        raise LookupError("Prompt specification not found")

    version = prompt_specification._current_version(db, spec)
    traces = list(db.query(RequirementArtifactTrace).filter(
        RequirementArtifactTrace.project_id == project_id,
        RequirementArtifactTrace.spec_version_id == version.id,
    ).all())

    results = []
    for trace in traces:
        av = db.get(MigrationStageArtifactVersion, trace.artifact_version_id) if trace.artifact_version_id else None
        node = db.get(MigrationMedallionNode, trace.node_id) if trace.node_id else None
        if av:
            av.validation_status = "PASSED"
            av.executable = True
            av.validation_json = json.dumps({"errors": [], "target_validated_at": datetime.utcnow().isoformat()})
        if node:
            node.status = "ARTIFACT_READY"
        results.append({
            "request_id": trace.request_id,
            "artifact_version_id": av.id if av else None,
            "status": "PASSED",
            "errors": [],
        })

    spec.current_status = "PENDING_ARTIFACT_REVIEW"
    db.commit()

    return {
        "specification_id": specification_id,
        "status": "PENDING_ARTIFACT_REVIEW",
        "target_validation": {
            "catalog": "logistics_demo_dev",
            "status": "PASSED",
            "schemas_verified": ["bronze", "silver", "gold"],
            "artifacts_tested": len(traces),
            "passed_count": len(traces),
            "failed_count": 0,
            "errors": [],
        },
        "results": results,
    }


def deploy_demo_dev(db: Any, project_id: str, specification_id: str, actor: str) -> Dict[str, Any]:
    """Deploys approved Medallion artifacts to mock Databricks DEV with realistic logs."""
    import json
    from app.models.entities import PromptSpecification
    from app.models.canonical import MigrationDeployment, MigrationReconciliation
    from app.services.engine import uid

    spec = db.get(PromptSpecification, specification_id)
    if not spec:
        raise LookupError("Prompt specification not found")

    run_id = uid("DEP")
    now = datetime.utcnow()

    # 1. Start marker
    db.add(MigrationDeployment(
        id=uid("DPL"),
        project_id=project_id,
        environment="DEV",
        status="RUNNING",
        created_at=now,
        payload_json=json.dumps({"run_id": run_id, "medallion_run_started": True, "actor": actor}),
    ))

    # 2. Artifact deployments
    artifacts = [
        ("branches", "BRONZE", "logistics_demo_dev.bronze.branches", "Delta table ingested (100 rows)"),
        ("customers", "BRONZE", "logistics_demo_dev.bronze.customers", "Delta table ingested (500 rows)"),
        ("deliveryroutes", "BRONZE", "logistics_demo_dev.bronze.deliveryroutes", "Delta table ingested (250 rows)"),
        ("drivers", "BRONZE", "logistics_demo_dev.bronze.drivers", "Delta table ingested (300 rows)"),
        ("shipments", "BRONZE", "logistics_demo_dev.bronze.shipments", "Delta table ingested (1,300 rows)"),
        ("vehicles", "BRONZE", "logistics_demo_dev.bronze.vehicles", "Delta table ingested (300 rows)"),
        ("vw_branches_clean", "SILVER", "logistics_demo_dev.silver.vw_branches_clean", "Cleaned view created"),
        ("vw_customers_clean", "SILVER", "logistics_demo_dev.silver.vw_customers_clean", "Cleaned view created"),
        ("vw_deliveryroutes_clean", "SILVER", "logistics_demo_dev.silver.vw_deliveryroutes_clean", "Cleaned view created"),
        ("vw_drivers_clean", "SILVER", "logistics_demo_dev.silver.vw_drivers_clean", "Cleaned view created"),
        ("vw_shipments_clean", "SILVER", "logistics_demo_dev.silver.vw_shipments_clean", "Cleaned view created"),
        ("vw_vehicles_clean", "SILVER", "logistics_demo_dev.silver.vw_vehicles_clean", "Cleaned view created"),
        ("fn_calculate_shipping_charges_per_kg", "SILVER", "logistics_demo_dev.silver.fn_calculate_shipping_charges_per_kg", "UDF function compiled"),
        ("usp_mergedailysummary", "SILVER", "logistics_demo_dev.silver.usp_mergedailysummary", "Idempotent MERGE loader deployed"),
        ("dim_branches", "GOLD", "logistics_demo_dev.gold.dim_branches", "Dimension table materialized"),
        ("dim_drivers", "GOLD", "logistics_demo_dev.gold.dim_drivers", "Dimension table materialized"),
        ("dim_vehicles", "GOLD", "logistics_demo_dev.gold.dim_vehicles", "Dimension table materialized"),
        ("dim_customers", "GOLD", "logistics_demo_dev.gold.dim_customers", "Dimension table materialized"),
        ("fact_shipments", "GOLD", "logistics_demo_dev.gold.fact_shipments", "Fact table partitioned and loaded"),
        ("monthly_executive_kpi_aggregation_marts", "GOLD", "logistics_demo_dev.gold.monthly_executive_kpi_aggregation_marts", "KPI aggregation mart materialized"),
    ]

    for name, layer, fqn, desc in artifacts:
        db.add(MigrationDeployment(
            id=uid("DPL"),
            project_id=project_id,
            environment="DEV",
            status="PASSED",
            created_at=now,
            payload_json=json.dumps({
                "run_id": run_id,
                "medallion_node_id": f"node_{name}",
                "target_fqn": fqn,
                "layer": layer,
                "step": f"DEPLOY_{layer}_{name}",
                "message": f"Successfully deployed {fqn} • {desc}",
                "status": "PASSED",
            }),
        ))

    # 3. Finish marker
    db.add(MigrationDeployment(
        id=uid("DPL"),
        project_id=project_id,
        environment="DEV",
        status="PASSED",
        created_at=now,
        payload_json=json.dumps({"run_id": run_id, "medallion_run_complete": True, "medallion_run_finished": True, "duration_seconds": 12.4}),
    ))

    # 4. Reconciliation passed
    db.add(MigrationReconciliation(
        id=uid("REC"),
        project_id=project_id,
        environment="DEV",
        status="PASSED",
        created_at=now,
        payload_json=json.dumps({"run_id": run_id, "match_rate": 100.0, "total_source": 2750, "total_target": 2750}),
    ))

    spec.current_status = "DEV_GATE_PASSED"
    db.commit()

    return {
        "specification_id": specification_id,
        "status": "PASSED",
        "run_id": run_id,
        "deployment": {
            "id": run_id,
            "status": "PASSED",
            "environment": "DEV",
            "deployed_artifacts": 20,
            "reconciliation_status": "PASSED",
            "reconciliation_score": 100.0,
        },
    }


def get_demo_medallion_validation_report(environment: str = "DEV") -> Dict[str, Any]:
    return {
        "environment": environment,
        "status": "PASSED",
        "total_artifacts": 20,
        "valid_artifacts": 20,
        "invalid_artifacts": 0,
        "blocking_errors": [],
        "warnings": [],
        "catalog": "logistics_demo_dev",
        "generated_at": datetime.utcnow().isoformat(),
    }


def reset_demo_project_studio(db: Any, project_id: str) -> Dict[str, Any]:
    """Resets the demo project back to initial step (pre-discovery / pre-parse) for repeated presentations."""
    from app.models.entities import (
        PromptSpecification,
        PromptSpecificationVersion,
        PromptArtifactRequest,
        PromptClarification,
        PromptPlanApproval,
        RequirementArtifactTrace,
        MigrationStageArtifact,
        MigrationStageArtifactVersion,
        MigrationMedallionNode,
        MigrationMedallionEdge,
        MigrationMetadataSnapshot,
        MigrationObject,
        MigrationColumn,
        MigrationDependency,
        MigrationClassification,
        MigrationMapping,
        MigrationSource,
        MigrationEnvironmentPlan,
        MigrationQualityGate,
        MigrationRun,
        CanonicalRecord,
    )
    from app.models.canonical import (
        MigrationDeployment,
        MigrationReconciliation,
        MigrationRunStep,
        MigrationValidation,
        MigrationReconciliationDetail,
    )
    from app.services.engine import uid
    from datetime import datetime
    import json

    # 1. Clear deployments, reconciliations, run steps, validations, quality gates, runs, and automated promotion records
    db.query(MigrationDeployment).filter(MigrationDeployment.project_id == project_id).delete()
    db.query(MigrationReconciliation).filter(MigrationReconciliation.project_id == project_id).delete()
    db.query(MigrationRunStep).filter(MigrationRunStep.project_id == project_id).delete()
    db.query(MigrationValidation).filter(MigrationValidation.project_id == project_id).delete()
    db.query(MigrationReconciliationDetail).filter(MigrationReconciliationDetail.project_id == project_id).delete()
    db.query(MigrationQualityGate).filter(MigrationQualityGate.project_id == project_id).delete()
    db.query(MigrationRun).filter(MigrationRun.project_id == project_id).delete()
    db.query(CanonicalRecord).filter(
        CanonicalRecord.project_id == project_id,
        CanonicalRecord.record_type.in_(["AUTOMATED_PROMOTION_RUN", "MASTER_MIGRATION_PLAN", "PROMPT_PROMOTION_PLAN"])
    ).delete(synchronize_session=False)

    # 2. Clear artifacts, nodes, edges & traces
    db.query(RequirementArtifactTrace).filter(RequirementArtifactTrace.project_id == project_id).delete()
    db.query(MigrationStageArtifactVersion).filter(MigrationStageArtifactVersion.project_id == project_id).delete()
    db.query(MigrationStageArtifact).filter(MigrationStageArtifact.project_id == project_id).delete()
    db.query(MigrationMedallionEdge).filter(MigrationMedallionEdge.project_id == project_id).delete()
    db.query(MigrationMedallionNode).filter(MigrationMedallionNode.project_id == project_id).delete()

    # 3. Clear specs, versions, requests, clarifications, approvals
    db.query(PromptPlanApproval).filter(PromptPlanApproval.project_id == project_id).delete()
    db.query(PromptClarification).filter(PromptClarification.project_id == project_id).delete()
    db.query(PromptArtifactRequest).filter(PromptArtifactRequest.project_id == project_id).delete()
    db.query(PromptSpecificationVersion).filter(PromptSpecificationVersion.project_id == project_id).delete()
    db.query(PromptSpecification).filter(PromptSpecification.project_id == project_id).delete()

    # 4. Clear discovery progress (objects, columns, dependencies, classifications, mappings, snapshots)
    db.query(MigrationMapping).filter(MigrationMapping.project_id == project_id).delete()
    db.query(MigrationClassification).filter(MigrationClassification.project_id == project_id).delete()
    db.query(MigrationDependency).filter(MigrationDependency.project_id == project_id).delete()
    db.query(MigrationColumn).filter(MigrationColumn.project_id == project_id).delete()
    db.query(MigrationObject).filter(MigrationObject.project_id == project_id).delete()
    db.query(MigrationMetadataSnapshot).filter(MigrationMetadataSnapshot.project_id == project_id).delete()

    # 5. Ensure Source and Environment Setup are preserved & active
    source = db.query(MigrationSource).filter(MigrationSource.project_id == project_id).first()
    if not source:
        source = MigrationSource(
            id=uid("SRC"),
            project_id=project_id,
            profile_name="SQLServer1",
            engine="SQLSERVER",
            server_name=r"localhost\SQLEXPRESS",
            database_name="LogisticsMiniDemo",
        )
        db.add(source)

    plan_row = db.query(MigrationEnvironmentPlan).filter(
        MigrationEnvironmentPlan.project_id == project_id,
        MigrationEnvironmentPlan.environment == "DEV",
    ).first()
    if not plan_row:
        plan_row = MigrationEnvironmentPlan(
            id=uid("ENV"),
            project_id=project_id,
            environment="DEV",
            catalog_name="logistics_demo_dev",
            schemas_json=json.dumps(["bronze", "silver", "gold"]),
            status="PROVISIONED",
            created_at=datetime.utcnow(),
        )
        db.add(plan_row)
    else:
        plan_row.status = "PROVISIONED"

    db.commit()
    return {"ok": True, "message": "Demo project reset: sources & env preserved, discovery & downstream progress cleared"}


