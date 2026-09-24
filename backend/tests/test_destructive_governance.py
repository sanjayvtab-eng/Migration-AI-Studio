import hashlib
import pytest
from app.models.entities import MigrationDestructiveApproval
from app.services.prompt_specification import (
    scan_destructive_operations,
    record_destructive_approval,
    validate_destructive_approval,
    invalidate_destructive_approvals_on_change,
    PROD_CONFIRMATION_TOKEN,
)
from app.services.engine import ensure_project


def test_destructive_operations_scanner():
    # 1. TRUNCATE statement
    assert scan_destructive_operations("TRUNCATE TABLE `catalog`.`silver`.`orders`;") == ["TRUNCATE TABLE `catalog`.`silver`.`orders`"]
    assert scan_destructive_operations("truncate employees;") == ["truncate employees"]

    # 2. DELETE statement
    assert scan_destructive_operations("DELETE FROM `catalog`.`gold`.`dim_customer` WHERE 1=1;") == ["DELETE FROM `catalog`.`gold`.`dim_customer`"]

    # 3. Unrestricted UPDATE (no WHERE clause)
    unrestricted_1 = "UPDATE employees SET status = 'INACTIVE';"
    findings_1 = scan_destructive_operations(unrestricted_1)
    assert any("UNRESTRICTED UPDATE employees" in f for f in findings_1)

    # 4. Unrestricted UPDATE with trivial WHERE 1=1
    unrestricted_2 = "UPDATE employees SET salary = salary * 1.05 WHERE 1=1;"
    findings_2 = scan_destructive_operations(unrestricted_2)
    assert any("UNRESTRICTED UPDATE employees" in f for f in findings_2)

    # 5. Non-destructive statements
    assert scan_destructive_operations("SELECT * FROM employees WHERE id = 1;") == []
    assert scan_destructive_operations("INSERT INTO logs VALUES (1, 'info');") == []
    assert scan_destructive_operations("UPDATE employees SET salary = 50000 WHERE employee_id = 42;") == []
    assert scan_destructive_operations("MERGE INTO dim_customer target USING source ON target.id = source.id WHEN MATCHED THEN UPDATE SET target.v = source.v;") == []


def test_destructive_approval_dev_and_prod_tokens(db):
    project = ensure_project(db, "Destructive Governance Project")
    sql_dev = "TRUNCATE TABLE `dev_catalog`.`bronze`.`staged_logs`;"
    hash_dev = hashlib.sha256(sql_dev.encode("utf-8")).hexdigest()

    # DEV approval: succeeds without PROD confirmation token
    app_dev = record_destructive_approval(
        db,
        project_id=project.id,
        artifact_id="ART_001",
        artifact_version=1,
        sql_content_hash=hash_dev,
        environment="DEV",
        actor="lead_dev",
        reason="Routine table reset before migration testing",
        run_id="run_101",
    )
    assert app_dev.id.startswith("MDA_")
    assert app_dev.is_valid is True
    assert validate_destructive_approval(db, project.id, "ART_001", 1, hash_dev, "DEV") is True

    # PROD approval: rejects without exact token
    sql_prod = "TRUNCATE TABLE `prod_catalog`.`silver`.`transactions`;"
    hash_prod = hashlib.sha256(sql_prod.encode("utf-8")).hexdigest()

    with pytest.raises(ValueError, match="PROD destructive operations require typed confirmation token"):
        record_destructive_approval(
            db,
            project_id=project.id,
            artifact_id="ART_002",
            artifact_version=1,
            sql_content_hash=hash_prod,
            environment="PROD",
            actor="sysadmin",
            reason="Emergency maintenance",
            confirmed_token="YES_DO_IT",
        )

    # PROD approval: succeeds with exact typed confirmation token
    app_prod = record_destructive_approval(
        db,
        project_id=project.id,
        artifact_id="ART_002",
        artifact_version=1,
        sql_content_hash=hash_prod,
        environment="PROD",
        actor="sysadmin",
        reason="Approved incident remediation per change ticket CHG-9901",
        confirmed_token=PROD_CONFIRMATION_TOKEN,
    )
    assert app_prod.is_valid is True
    assert validate_destructive_approval(db, project.id, "ART_002", 1, hash_prod, "PROD") is True


def test_destructive_approval_invalidated_when_sql_changes(db):
    project = ensure_project(db, "Content Invalidation Project")
    original_sql = "DELETE FROM `dev_catalog`.`silver`.`temp_stage`;"
    original_hash = hashlib.sha256(original_sql.encode("utf-8")).hexdigest()

    # Create valid approval for original SQL
    record_destructive_approval(
        db,
        project_id=project.id,
        artifact_id="ART_STAGE",
        artifact_version=1,
        sql_content_hash=original_hash,
        environment="DEV",
        actor="dev_operator",
        reason="Clean staging partition",
    )
    assert validate_destructive_approval(db, project.id, "ART_STAGE", 1, original_hash, "DEV") is True

    # Modified SQL content changes digest
    modified_sql = "DELETE FROM `dev_catalog`.`silver`.`temp_stage` WHERE partition_id = '2026-09';"
    modified_hash = hashlib.sha256(modified_sql.encode("utf-8")).hexdigest()

    # Prior approval must NOT validate against modified SQL
    assert validate_destructive_approval(db, project.id, "ART_STAGE", 1, modified_hash, "DEV") is False

    # Invalidate approvals whose content hash does not match current version
    count = invalidate_destructive_approvals_on_change(db, project.id, "ART_STAGE", modified_hash)
    db.commit()
    assert count == 1

    # Approval is now explicitly marked invalid
    assert validate_destructive_approval(db, project.id, "ART_STAGE", 1, original_hash, "DEV") is False
