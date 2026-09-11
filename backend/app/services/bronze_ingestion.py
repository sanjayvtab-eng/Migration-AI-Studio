from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    CanonicalRecord,
    MigrationColumn,
    MigrationEnvironmentPlan,
    MigrationObject,
    MigrationProject,
    MigrationRun,
    MigrationSource,
)
from app.services import environment_provisioning
from app.services.engine import uid
from app.services.source_connector import TableStream, connector_info, request as connector_request
from app.services.type_compatibility import (
    normalize_row,
    source_select_expression,
    target_parameter_expression,
    transport_summary,
)
from app.services.rules import map_sqlserver_type
from app.services.databricks_client import TRANSIENT


LOAD_MODES = {"FULL_LOAD", "APPEND"}
MISSING_TARGET_MARKERS = (
    "table_or_view_not_found",
    "table or view not found",
    "does not exist",
    "cannot be found",
    "not found",
)


def _qident(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("Invalid empty or null-containing identifier")
    return f"`{value.replace('`', '``')}`"


def _fqn(catalog: str, schema: str, table: str) -> str:
    return ".".join(_qident(x) for x in (catalog, schema, table))


def _payload(value: str | None) -> dict[str, Any]:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _record(
    db: Session,
    project_id: str,
    *,
    status: str,
    run_id: str | None = None,
    object_id: str | None = None,
    **details: Any,
) -> None:
    db.add(
        CanonicalRecord(
            id=uid("REC"),
            project_id=project_id,
            object_id=object_id,
            environment="DEV",
            record_type="BRONZE_INGESTION",
            payload_json=json.dumps(
                {"status": status, "run_id": run_id, **details},
                default=str,
                sort_keys=True,
            ),
        )
    )
    db.commit()


def _requirements(db: Session, project_id: str) -> tuple[MigrationEnvironmentPlan, list[MigrationObject]]:
    if not db.get(MigrationProject, project_id):
        raise LookupError("Project not found")
    config = environment_provisioning.get_configuration(db, project_id)
    if not config or config.status != "READY":
        raise ValueError("A tested project Databricks configuration is required")
    plan = environment_provisioning.get_dev_plan(db, project_id)
    if not plan or plan.status != "PROVISIONED":
        raise ValueError("Provision the governed DEV environment before Bronze ingestion")
    tables = list(
        db.scalars(
            select(MigrationObject)
            .where(
                MigrationObject.project_id == project_id,
                MigrationObject.object_type == "TABLE",
            )
            .order_by(MigrationObject.schema_name, MigrationObject.object_name)
        ).all()
    )
    if not tables:
        raise ValueError("Run SQL Server discovery before Bronze ingestion")
    return plan, tables


def _selected_tables(
    tables: list[MigrationObject], source_id: str | None
) -> list[MigrationObject]:
    selected = [table for table in tables if not source_id or table.source_id == source_id]
    if source_id and not selected:
        raise ValueError("The selected source has no discovered SQL Server tables")
    names: dict[str, list[str]] = {}
    for table in selected:
        names.setdefault(table.object_name.lower(), []).append(
            f"{table.schema_name}.{table.object_name}"
        )
    collisions = [items for items in names.values() if len(items) > 1]
    if collisions:
        values = ", ".join(" / ".join(items) for items in collisions)
        raise ValueError(
            "Bronze target-name collision across SQL Server schemas: " + values
        )
    return selected


def _columns(db: Session, project_id: str, object_id: str) -> list[MigrationColumn]:
    return list(
        db.scalars(
            select(MigrationColumn)
            .where(
                MigrationColumn.project_id == project_id,
                MigrationColumn.object_id == object_id,
                MigrationColumn.is_computed == False,  # noqa: E712
            )
            .order_by(MigrationColumn.ordinal)
        ).all()
    )


def _target_count(db: Session, project_id: str, target: str) -> int | None:
    try:
        rows = environment_provisioning.project_execute(
            db, project_id, f"SELECT COUNT(*) FROM {target}", safe_retry=True
        )
    except Exception as exc:
        if any(marker in str(exc).lower() for marker in MISSING_TARGET_MARKERS):
            return None
        raise
    return int(rows[0][0]) if rows else 0


def _source_connection_string(source: MigrationSource) -> str:
    settings = get_settings()
    driver = settings.sqlserver_driver.replace("{", "").replace("}", "")
    if settings.sqlserver_username:
        return (
            f"DRIVER={{{driver}}};SERVER={source.server_name};DATABASE={source.database_name};"
            f"UID={settings.sqlserver_username};PWD={settings.sqlserver_password or ''};"
            "TrustServerCertificate=yes;"
        )
    return (
        f"DRIVER={{{driver}}};SERVER={source.server_name};DATABASE={source.database_name};"
        "Trusted_Connection=yes;TrustServerCertificate=yes;"
    )


@contextmanager
def _source_rows(
    source: MigrationSource,
    table: MigrationObject,
    columns: list[MigrationColumn],
    max_rows: int | None,
):
    if connector_info(source.id)["mode"] == "CONNECTOR":
        with TableStream(source.id, table, columns, max_rows) as stream:
            yield stream
        return
    import pyodbc

    projection = ",".join(source_select_expression(column) for column in columns)
    table_name = (
        f"[{table.schema_name.replace(']', ']]')}]."
        f"[{table.object_name.replace(']', ']]')}]"
    )
    top = f"TOP ({int(max_rows)}) " if max_rows else ""
    with pyodbc.connect(_source_connection_string(source), timeout=30) as connection:
        cursor = connection.cursor()
        cursor.execute(f"SELECT {top}{projection} FROM {table_name}")
        yield cursor


def _source_count(source: MigrationSource, table: MigrationObject) -> int:
    if connector_info(source.id)["mode"] == "CONNECTOR":
        return int(
            connector_request(
                source.id,
                "count",
                {"schema": table.schema_name, "table": table.object_name},
            )["count"]
        )
    import pyodbc

    table_name = (
        f"[{table.schema_name.replace(']', ']]')}]."
        f"[{table.object_name.replace(']', ']]')}]"
    )
    with pyodbc.connect(_source_connection_string(source), timeout=30) as connection:
        return int(connection.cursor().execute(f"SELECT COUNT_BIG(*) FROM {table_name}").fetchone()[0])


def preflight(
    db: Session, project_id: str, *, source_id: str | None = None
) -> dict[str, Any]:
    plan, all_tables = _requirements(db, project_id)
    tables = _selected_tables(all_tables, source_id)
    details = []
    blockers = []
    for table in tables:
        source = db.get(MigrationSource, table.source_id)
        columns = _columns(db, project_id, table.id)
        if not source or source.project_id != project_id:
            blockers.append(f"Source profile missing for {table.schema_name}.{table.object_name}")
            continue
        connection = connector_info(source.id)
        if connection["mode"] == "CONNECTOR" and connection["status"] != "ONLINE":
            blockers.append(f"Local connector is offline for source {source.profile_name}")
        if not columns:
            blockers.append(f"No discovered columns for {table.schema_name}.{table.object_name}")
            continue
        target = _fqn(plan.catalog_name, "bronze", table.object_name)
        details.append(
            {
                "object_id": table.id,
                "source": f"{table.schema_name}.{table.object_name}",
                "target_fqn": target,
                "columns": len(columns),
                "connector_status": connection["status"],
                "target_rows": _target_count(db, project_id, target),
            }
        )
    result = {
        "status": "PASSED" if not blockers else "BLOCKED",
        "environment": "DEV",
        "catalog": plan.catalog_name,
        "schema": "bronze",
        "table_count": len(details),
        "blockers": blockers,
        "tables": details,
    }
    _record(db, project_id, status=result["status"], action="PREFLIGHT", details=result)
    return result


def _ddl(columns: list[MigrationColumn]) -> str:
    definitions = [
        f"{_qident(column.column_name)} "
        f"{map_sqlserver_type(column.data_type, column.precision, column.scale)}"
        for column in columns
    ]
    definitions.extend(
        [
            "`_migration_ingested_at` TIMESTAMP",
            "`_migration_source_system` STRING",
        ]
    )
    return ", ".join(definitions)


def _load_table(
    db: Session,
    project_id: str,
    run_id: str,
    plan: MigrationEnvironmentPlan,
    table: MigrationObject,
    *,
    batch_size: int,
    max_rows: int | None,
    load_mode: str,
    replace_existing_data: bool,
) -> dict[str, Any]:
    source = db.get(MigrationSource, table.source_id)
    if not source or source.project_id != project_id:
        raise RuntimeError("Source profile not found")
    columns = _columns(db, project_id, table.id)
    if not columns:
        raise RuntimeError("No discovered source columns")
    connection = connector_info(source.id)
    if connection["mode"] == "CONNECTOR":
        connector_request(source.id, "test")

    target = _fqn(plan.catalog_name, "bronze", table.object_name)
    existing_count = _target_count(db, project_id, target)
    if load_mode == "FULL_LOAD" and existing_count is not None and not replace_existing_data:
        raise RuntimeError(
            f"Target already contains {existing_count} rows; explicitly approve replacement"
        )
    source_total = _source_count(source, table)
    expected_rows = min(source_total, max_rows) if max_rows is not None else source_total

    suffix = re.sub(r"[^A-Za-z0-9_]", "_", run_id[-16:])
    stage = _fqn(plan.catalog_name, "bronze", f"__mf_stage_{suffix}_{table.id[-8:]}")
    write_target = stage if load_mode == "FULL_LOAD" else target
    if load_mode == "FULL_LOAD":
        environment_provisioning.project_execute(
            db, project_id, f"DROP TABLE IF EXISTS {stage}", safe_retry=True
        )
        environment_provisioning.project_execute(
            db, project_id, f"CREATE TABLE {stage} ({_ddl(columns)}) USING DELTA", safe_retry=False
        )
    elif existing_count is None:
        environment_provisioning.project_execute(
            db,
            project_id,
            f"CREATE TABLE IF NOT EXISTS {target} ({_ddl(columns)}) USING DELTA",
            safe_retry=True,
        )

    target_columns = ",".join(
        [_qident(column.column_name) for column in columns]
        + ["`_migration_source_system`"]
    )
    placeholders = ",".join(
        [target_parameter_expression(column) for column in columns] + ["?"]
    )
    insert_sql = (
        f"INSERT INTO {write_target} ({target_columns}, `_migration_ingested_at`) "
        f"VALUES ({placeholders}, current_timestamp())"
    )
    rows_loaded = 0
    try:
        with _source_rows(source, table, columns, max_rows) as source_cursor:
            with environment_provisioning.project_connection(db, project_id) as target_connection:
                target_cursor = target_connection.cursor()
                while True:
                    batch = source_cursor.fetchmany(batch_size)
                    if not batch:
                        break
                    payload = []
                    first_row = rows_loaded + 1
                    for offset, row in enumerate(batch):
                        normalized = normalize_row(
                            columns, tuple(row), row_index=first_row + offset
                        )
                        payload.append(
                            normalized
                            + (f"{source.server_name}/{source.database_name}",)
                        )
                    target_cursor.executemany(insert_sql, payload)
                    rows_loaded += len(payload)
        if load_mode == "FULL_LOAD":
            verb = "CREATE OR REPLACE" if existing_count is not None else "CREATE"
            environment_provisioning.project_execute(
                db,
                project_id,
                f"{verb} TABLE {target} USING DELTA AS SELECT * FROM {stage}",
                safe_retry=False,
            )
    finally:
        if load_mode == "FULL_LOAD":
            try:
                environment_provisioning.project_execute(
                    db, project_id, f"DROP TABLE IF EXISTS {stage}", safe_retry=True
                )
            except Exception:
                pass

    target_rows = _target_count(db, project_id, target)
    expected_target_rows = rows_loaded if load_mode == "FULL_LOAD" else (existing_count or 0) + rows_loaded
    if target_rows != expected_target_rows:
        raise RuntimeError(
            f"Post-load row-count validation failed: expected {expected_target_rows}, found {target_rows}"
        )
    return {
        "object_id": table.id,
        "source": f"{table.schema_name}.{table.object_name}",
        "target_fqn": target,
        "status": "PASSED",
        "rows_loaded": rows_loaded,
        "source_rows": source_total,
        "expected_rows": expected_rows,
        "target_rows": target_rows,
        "load_mode": load_mode,
        "transport": transport_summary(columns),
    }


def run(
    db: Session,
    project_id: str,
    *,
    actor: str,
    source_id: str | None = None,
    load_mode: str = "FULL_LOAD",
    batch_size: int = 1000,
    max_rows: int | None = None,
    replace_existing_data: bool = False,
) -> dict[str, Any]:
    mode = str(load_mode).upper()
    if mode not in LOAD_MODES:
        raise ValueError("Release 2 supports FULL_LOAD or APPEND; watermark-based incremental loading is not configured yet")
    if batch_size < 1 or batch_size > 10000:
        raise ValueError("Batch size must be between 1 and 10000")
    if max_rows is not None and max_rows < 1:
        raise ValueError("Max rows must be positive")
    plan, all_tables = _requirements(db, project_id)
    tables = _selected_tables(all_tables, source_id)
    if mode == "FULL_LOAD" and not replace_existing_data:
        occupied = []
        for table in tables:
            target = _fqn(plan.catalog_name, "bronze", table.object_name)
            count = _target_count(db, project_id, target)
            if count is not None:
                occupied.append(f"{target} ({count} rows)")
        if occupied:
            raise ValueError(
                "FULL_LOAD replacement requires explicit approval for: " + ", ".join(occupied)
            )

    migration_run = MigrationRun(
        id=uid("BRI"),
        project_id=project_id,
        stage="DEV_BRONZE_INGESTION",
        environment="DEV",
        status="RUNNING",
    )
    db.add(migration_run)
    db.commit()
    _record(
        db,
        project_id,
        status="RUNNING",
        run_id=migration_run.id,
        action="INGESTION_STARTED",
        actor=actor,
        load_mode=mode,
        table_count=len(tables),
    )
    results = []
    for table in tables:
        result = None
        failure = None
        attempt_limit = 2 if mode == "FULL_LOAD" else 1
        for attempt in range(1, attempt_limit + 1):
            try:
                result = _load_table(
                    db,
                    project_id,
                    migration_run.id,
                    plan,
                    table,
                    batch_size=batch_size,
                    max_rows=max_rows,
                    load_mode=mode,
                    replace_existing_data=replace_existing_data,
                )
                break
            except Exception as exc:
                transient = any(marker in str(exc).lower() for marker in TRANSIENT)
                if attempt < attempt_limit and transient:
                    _record(
                        db,
                        project_id,
                        status="RETRYING",
                        run_id=migration_run.id,
                        object_id=table.id,
                        action="TABLE_INGESTION_RETRY",
                        source=f"{table.schema_name}.{table.object_name}",
                        attempt=attempt,
                    )
                    time.sleep(2)
                    continue
                failure = exc
                break
        if result is not None:
            results.append(result)
            evidence = {key: value for key, value in result.items() if key not in {"object_id", "status"}}
            _record(
                db,
                project_id,
                status="PASSED",
                run_id=migration_run.id,
                object_id=table.id,
                action="TABLE_INGESTED",
                **evidence,
            )
        else:
            failure = {
                "object_id": table.id,
                "source": f"{table.schema_name}.{table.object_name}",
                "status": "FAILED",
                "error": str(failure),
            }
            results.append(failure)
            _record(
                db,
                project_id,
                status="FAILED",
                run_id=migration_run.id,
                object_id=table.id,
                action="TABLE_INGESTION_FAILED",
                source=failure["source"],
                error=failure["error"],
            )
    passed = sum(1 for item in results if item["status"] == "PASSED")
    failed = len(results) - passed
    status = "PASSED" if not failed else "PARTIAL" if passed else "FAILED"
    migration_run.status = status
    migration_run.ended_at = datetime.utcnow()
    migration_run.checkpoint = next(
        (item["source"] for item in results if item["status"] == "FAILED"),
        "DEV_BRONZE_INGESTION_COMPLETE",
    )
    db.commit()
    _record(
        db,
        project_id,
        status=status,
        run_id=migration_run.id,
        action="INGESTION_COMPLETED",
        actor=actor,
        passed=passed,
        failed=failed,
    )
    return {
        "run_id": migration_run.id,
        "status": status,
        "environment": "DEV",
        "catalog": plan.catalog_name,
        "load_mode": mode,
        "passed": passed,
        "failed": failed,
        "results": results,
    }


def latest(db: Session, project_id: str) -> dict[str, Any]:
    if not db.get(MigrationProject, project_id):
        raise LookupError("Project not found")
    run = db.scalars(
        select(MigrationRun)
        .where(
            MigrationRun.project_id == project_id,
            MigrationRun.stage == "DEV_BRONZE_INGESTION",
        )
        .order_by(MigrationRun.started_at.desc())
    ).first()
    if not run:
        return {"status": "NOT_STARTED", "run_id": None, "results": []}
    records = list(
        db.scalars(
            select(CanonicalRecord)
            .where(
                CanonicalRecord.project_id == project_id,
                CanonicalRecord.record_type == "BRONZE_INGESTION",
            )
            .order_by(CanonicalRecord.created_at)
        ).all()
    )
    results = []
    for record in records:
        payload = _payload(record.payload_json)
        if payload.get("run_id") == run.id and payload.get("action") in {
            "TABLE_INGESTED",
            "TABLE_INGESTION_FAILED",
        }:
            results.append(payload)
    return {
        "run_id": run.id,
        "status": run.status,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "checkpoint": run.checkpoint,
        "passed": sum(1 for item in results if item.get("status") == "PASSED"),
        "failed": sum(1 for item in results if item.get("status") == "FAILED"),
        "results": results,
    }
