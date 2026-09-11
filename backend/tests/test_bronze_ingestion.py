from contextlib import contextmanager

import pytest
from sqlalchemy import select

from app.models.entities import (
    CanonicalRecord,
    MigrationDatabricksConfiguration,
    MigrationEnvironmentPlan,
    MigrationObject,
)
from app.services import bronze_ingestion
from app.services.engine import add_source, ensure_project, ingest_snapshot, uid


def _seed(db, *, provisioned=True):
    project = ensure_project(db, "Release 2 ingestion")
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
    db.add(
        MigrationEnvironmentPlan(
            id=uid("EVP"),
            project_id=project.id,
            environment="DEV",
            catalog_name="migration_dev",
            status="PROVISIONED" if provisioned else "APPROVED",
        )
    )
    db.commit()
    table = db.scalar(
        select(MigrationObject).where(MigrationObject.project_id == project.id)
    )
    return project, source, table


def test_preflight_requires_provisioned_dev(db, monkeypatch):
    project, _, _ = _seed(db, provisioned=False)
    with pytest.raises(ValueError, match="Provision"):
        bronze_ingestion.preflight(db, project.id)


def test_preflight_is_project_scoped(db, monkeypatch):
    project, _, _ = _seed(db)
    statements = []

    def execute(_db, project_id, statement, **_kwargs):
        statements.append((project_id, statement))
        raise RuntimeError("TABLE_OR_VIEW_NOT_FOUND")

    monkeypatch.setattr(bronze_ingestion.environment_provisioning, "project_execute", execute)
    monkeypatch.setattr(
        bronze_ingestion, "connector_info", lambda _source_id: {"mode": "DIRECT", "status": "DIRECT"}
    )
    result = bronze_ingestion.preflight(db, project.id)
    assert result["status"] == "PASSED"
    assert result["tables"][0]["target_fqn"] == "`migration_dev`.`bronze`.`Customers`"
    assert statements[0][0] == project.id


def test_full_load_requires_explicit_replacement(db, monkeypatch):
    project, _, _ = _seed(db)
    monkeypatch.setattr(bronze_ingestion, "_target_count", lambda *_args, **_kwargs: 0)
    with pytest.raises(ValueError, match="explicit approval"):
        bronze_ingestion.run(db, project.id, actor="admin")


def test_full_load_records_per_table_evidence(db, monkeypatch):
    project, _, _ = _seed(db)
    statements = []

    def execute(_db, project_id, statement, **_kwargs):
        assert project_id == project.id
        statements.append(statement)
        return []

    class SourceCursor:
        def __init__(self):
            self.calls = 0

        def fetchmany(self, _size):
            self.calls += 1
            return [(1, "Alice"), (2, "Bob")] if self.calls == 1 else []

    class TargetCursor:
        def __init__(self):
            self.rows = []

        def executemany(self, statement, rows):
            self.rows.extend(rows)
            assert "__mf_stage_" in statement

    target_cursor = TargetCursor()

    class TargetConnection:
        def cursor(self):
            return target_cursor

    @contextmanager
    def source_rows(*_args, **_kwargs):
        yield SourceCursor()

    @contextmanager
    def target_connection(*_args, **_kwargs):
        yield TargetConnection()

    monkeypatch.setattr(bronze_ingestion.environment_provisioning, "project_execute", execute)
    monkeypatch.setattr(bronze_ingestion.environment_provisioning, "project_connection", target_connection)
    monkeypatch.setattr(bronze_ingestion, "_source_rows", source_rows)
    monkeypatch.setattr(bronze_ingestion, "_source_count", lambda *_args: 2)
    target_counts = iter([None, None, 2])
    monkeypatch.setattr(bronze_ingestion, "_target_count", lambda *_args, **_kwargs: next(target_counts))
    monkeypatch.setattr(
        bronze_ingestion, "connector_info", lambda _source_id: {"mode": "DIRECT", "status": "DIRECT"}
    )

    result = bronze_ingestion.run(db, project.id, actor="admin")
    assert result["status"] == "PASSED"
    assert result["passed"] == 1 and result["failed"] == 0
    assert result["results"][0]["rows_loaded"] == 2
    assert len(target_cursor.rows) == 2
    assert any("CREATE TABLE `migration_dev`.`bronze`.`Customers`" in item for item in statements)
    evidence = db.scalars(
        select(CanonicalRecord).where(
            CanonicalRecord.project_id == project.id,
            CanonicalRecord.record_type == "BRONZE_INGESTION",
        )
    ).all()
    assert evidence
    latest = bronze_ingestion.latest(db, project.id)
    assert latest["status"] == "PASSED" and latest["passed"] == 1
