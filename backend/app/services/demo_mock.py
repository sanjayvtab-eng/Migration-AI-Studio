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
    """Submits prompt dynamically against connected source metadata."""
    from app.services import prompt_specification
    return prompt_specification.submit(db, project_id, prompt, actor)


def get_demo_prompt_specification_detail(db: Any, project_id: str, specification_id: str) -> Dict[str, Any]:
    """Returns dynamic specification detail grounded against connected source metadata."""
    from app.services import prompt_specification
    return prompt_specification.detail(db, project_id, specification_id)


def validate_demo_target(db: Any, project_id: str, specification_id: str) -> Dict[str, Any]:
    """Validates the 20 artifacts against simulated Databricks DEV control plane."""
    import json
    from app.models.entities import PromptSpecification, RequirementArtifactTrace, MigrationStageArtifactVersion, MigrationMedallionNode
    from app.services import prompt_specification

    from app.services import environment_provisioning
    dev_plan = environment_provisioning.get_dev_plan(db, project_id)
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
            "catalog": dev_plan.catalog_name if dev_plan else "demo_dev",
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
    """Deploys approved Medallion artifacts dynamically to mock Databricks DEV with realistic logs."""
    import json
    from app.models.entities import (
        PromptSpecification,
        PromptSpecificationVersion,
        PromptArtifactRequest,
        RequirementArtifactTrace,
        MigrationMedallionNode,
        MigrationStageArtifactVersion,
        MigrationEnvironmentPlan,
    )
    from app.models.canonical import MigrationDeployment, MigrationReconciliation
    from app.services.engine import uid
    from app.services import prompt_specification

    spec = db.get(PromptSpecification, specification_id)
    if not spec:
        raise LookupError("Prompt specification not found")

    version = prompt_specification._current_version(db, spec)
    run_id = uid("DEP")
    now = datetime.utcnow()

    # Determine catalog
    plan_row = db.query(MigrationEnvironmentPlan).filter(
        MigrationEnvironmentPlan.project_id == project_id,
        MigrationEnvironmentPlan.environment == "DEV",
    ).first()
    catalog = plan_row.catalog_name if plan_row else "demo_dev"

    # 1. Start marker
    db.add(MigrationDeployment(
        id=uid("DPL"),
        project_id=project_id,
        environment="DEV",
        status="RUNNING",
        created_at=now,
        payload_json=json.dumps({"run_id": run_id, "medallion_run_started": True, "actor": actor}),
    ))

    # Fetch traces and nodes for this spec version
    traces = list(db.query(RequirementArtifactTrace).filter(
        RequirementArtifactTrace.project_id == project_id,
        RequirementArtifactTrace.spec_version_id == version.id,
    ).all())

    deployed_count = 0
    if traces:
        for tr in traces:
            node = db.get(MigrationMedallionNode, tr.node_id) if tr.node_id else None
            av = db.get(MigrationStageArtifactVersion, tr.artifact_version_id) if tr.artifact_version_id else None
            if av:
                av.review_status = "APPROVED"
                av.validation_status = "PASSED"
                av.executable = True
            if node:
                node.status = "DEPLOYED"

            art_name = tr.request_id
            layer = "SILVER"
            fqn = f"{catalog}.silver.{art_name}"
            if node and node.target_fqn:
                fqn = node.target_fqn
                parts = fqn.split(".")
                art_name = parts[-1]
                if len(parts) >= 2:
                    layer = parts[-2].upper()
            elif node and node.layer:
                layer = node.layer
                art_name = node.name or art_name

            if layer == "BRONZE":
                desc = "Delta table ingested"
            elif "clean" in art_name:
                desc = "Cleaned view created"
            elif art_name.startswith("fn_"):
                desc = "UDF function compiled"
            elif art_name.startswith("usp_"):
                desc = "Idempotent MERGE loader deployed"
            elif layer == "GOLD" and art_name.startswith("dim_"):
                desc = "Dimension table materialized"
            elif layer == "GOLD" and art_name.startswith("fact_"):
                desc = "Fact table partitioned and loaded"
            elif layer == "GOLD":
                desc = "KPI aggregation mart materialized"
            else:
                desc = f"Artifact {art_name} deployed successfully"

            db.add(MigrationDeployment(
                id=uid("DPL"),
                project_id=project_id,
                environment="DEV",
                status="PASSED",
                created_at=now,
                payload_json=json.dumps({
                    "run_id": run_id,
                    "medallion_node_id": tr.node_id or f"node_{art_name}",
                    "target_fqn": fqn,
                    "layer": layer,
                    "step": f"DEPLOY_{layer}_{art_name}",
                    "message": f"Successfully deployed {fqn} • {desc}",
                    "status": "PASSED",
                }),
            ))
            deployed_count += 1
    else:
        reqs = list(db.query(PromptArtifactRequest).filter(
            PromptArtifactRequest.project_id == project_id,
            PromptArtifactRequest.spec_version_id == version.id,
        ).all())
        for req in reqs:
            layer = req.layer
            name = req.name
            fqn = f"{catalog}.{layer.lower()}.{name}"
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
                    "message": f"Successfully deployed {fqn} • Artifact deployed",
                    "status": "PASSED",
                }),
            ))
            deployed_count += 1

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
            "deployed_artifacts": deployed_count or 20,
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


def reset_demo_workspace(db: Any, workspace_id: str | None = None) -> Dict[str, Any]:
    """Delete all projects created in the current demo/embed workspace so every iframe refresh starts clean."""
    from sqlalchemy import select, func
    from app.core.database import Base
    from app.models.entities import MigrationProject

    stmt = select(MigrationProject).where(func.lower(MigrationProject.created_by) == DEMO_MOCK_USER)
    if workspace_id:
        stmt = stmt.where(MigrationProject.workspace_id == workspace_id)
    projects = list(db.scalars(stmt).all())
    deleted_ids = [p.id for p in projects]

    if deleted_ids:
        for table in reversed(Base.metadata.sorted_tables):
            if "project_id" in table.c:
                db.execute(table.delete().where(table.c.project_id.in_(deleted_ids)))
        for p in projects:
            db.delete(p)
        db.commit()

    return {"reset": True, "deleted_count": len(deleted_ids), "deleted_ids": deleted_ids}


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


