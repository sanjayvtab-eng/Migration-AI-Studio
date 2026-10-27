from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import tempfile
from urllib.parse import quote
import re
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
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
    format_sql_literal,
    normalize_row,
    source_select_expression,
    target_parameter_expression,
    transport_summary,
)
from app.services.rules import map_sqlserver_type
from app.services.databricks_client import TRANSIENT
from app.services.source_adapters import adapter_for_source


BULK_THRESHOLD = 5000
logger = logging.getLogger(__name__)

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


_FQN_IDENTIFIER = r"(?:`(?:``|[^`])+`|[A-Za-z_][A-Za-z0-9_]*)"
_FQN_PATTERN = re.compile(
    rf"^\s*({_FQN_IDENTIFIER})\s*\.\s*({_FQN_IDENTIFIER})\s*\.\s*({_FQN_IDENTIFIER})\s*$"
)


def _parse_fqn(value: str) -> tuple[str, str, str]:
    """Parse exactly one safe Databricks catalog.schema.object identifier."""
    match = _FQN_PATTERN.fullmatch(str(value or ""))
    if not match:
        raise ValueError(f"Target FQN must be exactly catalog.schema.object: {value}")

    def unquote(identifier: str) -> str:
        if identifier.startswith("`"):
            identifier = identifier[1:-1].replace("``", "`")
        if not identifier or "\x00" in identifier:
            raise ValueError("Target FQN contains an invalid identifier")
        return identifier

    return tuple(unquote(item) for item in match.groups())


def _same_fqn(left: str | None, right: str | None) -> bool:
    try:
        return tuple(item.casefold() for item in _parse_fqn(str(left or ""))) == tuple(
            item.casefold() for item in _parse_fqn(str(right or ""))
        )
    except ValueError:
        return False


def validate_approved_bronze_target(target_fqn: str, *, expected_catalog: str) -> str:
    """Validate a persisted approved target without deriving or renaming it."""
    catalog, schema, _ = _parse_fqn(target_fqn)
    if catalog.casefold() != str(expected_catalog).casefold():
        raise ValueError(
            f"Approved Bronze target catalog {catalog} does not match provisioned DEV catalog {expected_catalog}"
        )
    if schema.casefold() != "bronze":
        raise ValueError("Approved Bronze target must use the bronze schema")
    return str(target_fqn).strip()


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
        raise ValueError("Run source discovery before Bronze ingestion")
    return plan, tables


def _selected_tables(
    tables: list[MigrationObject], source_id: str | None
) -> list[MigrationObject]:
    selected = [table for table in tables if not source_id or table.source_id == source_id]
    if source_id and not selected:
        raise ValueError("The selected source has no discovered tables")
    names: dict[str, list[str]] = {}
    for table in selected:
        names.setdefault(table.object_name.lower(), []).append(
            f"{table.schema_name}.{table.object_name}"
        )
    collisions = [items for items in names.values() if len(items) > 1]
    if collisions:
        values = ", ".join(" / ".join(items) for items in collisions)
        raise ValueError(
            "Bronze target-name collision across source schemas: " + values
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
    adapter = adapter_for_source(source)
    with adapter.open_table_cursor(table, columns, batch_size=get_settings().batch_size, max_rows=max_rows) as cursor:
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
    return adapter_for_source(source).count_rows(table)


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


def _load_via_direct_batch_insert(db, project_id, source, table, columns, write_target,
                                *, batch_size, max_rows):
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
    with environment_provisioning.project_connection(db, project_id) as target_connection:
        target_cursor = target_connection.cursor()
        with _source_rows(source, table, columns, max_rows) as source_cursor:
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
                CHUNK_SIZE = 500
                if hasattr(target_cursor, "execute") and callable(target_cursor.execute):
                    for c_idx in range(0, len(payload), CHUNK_SIZE):
                        sub_batch = payload[c_idx:c_idx + CHUNK_SIZE]
                        row_sql_items = []
                        for row_tuple in sub_batch:
                            col_lits = [
                                format_sql_literal(val, col)
                                for val, col in zip(row_tuple[:-1], columns)
                            ]
                            col_lits.append(format_sql_literal(row_tuple[-1]))
                            row_sql_items.append(f"({', '.join(col_lits)}, current_timestamp())")
                        multi_insert_sql = (
                            f"INSERT INTO {write_target} ({target_columns}, `_migration_ingested_at`) "
                            f"VALUES {','.join(row_sql_items)}"
                        )
                        target_cursor.execute(multi_insert_sql)
                else:
                    for c_idx in range(0, len(payload), CHUNK_SIZE):
                        target_cursor.executemany(insert_sql, payload[c_idx:c_idx + CHUNK_SIZE])
                rows_loaded += len(payload)
    return rows_loaded


def _export_table_to_parquet(source, table, columns, max_rows=None):
    """Stream canonical transport values to Parquet; COPY restores target types."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    handle = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    path = handle.name
    handle.close()
    count = 0
    schema = pa.schema([(column.column_name, pa.string()) for column in columns])
    try:
        with pq.ParquetWriter(path, schema, compression="snappy") as writer:
            with _source_rows(source, table, columns, max_rows) as cursor:
                while True:
                    batch = cursor.fetchmany(10000)
                    if not batch:
                        break
                    rows = [normalize_row(columns, tuple(row), row_index=count + i + 1)
                            for i, row in enumerate(batch)]
                    data = {column.column_name: [None if row[i] is None else str(row[i])
                                                for row in rows]
                            for i, column in enumerate(columns)}
                    writer.write_table(pa.Table.from_pydict(data, schema=schema))
                    count += len(rows)
        return path, count
    except Exception:
        os.unlink(path)
        raise


def _volume_file_request(db, project_id, method, volume_path, *, local_path=None):
    import httpx

    config = environment_provisioning.get_configuration(db, project_id)
    if not config or config.status != "READY":
        raise RuntimeError("A tested project Databricks configuration is required")
    token = environment_provisioning._token(config)
    if not token:
        raise RuntimeError("Project Databricks token is not configured")
    url = f"https://{config.workspace_host}/api/2.0/fs/files{quote(volume_path, safe='/')}"
    # Do not include provider responses or credentials in load evidence.
    with httpx.Client(timeout=httpx.Timeout(600, connect=30), follow_redirects=False) as client:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}
        if local_path:
            size = os.path.getsize(local_path)
            if size > 5 * 1024 ** 3:
                raise RuntimeError("Staging file exceeds the Files API upload limit")
            headers["Content-Length"] = str(size)
            with open(local_path, "rb") as stream:
                response = client.request(method, url, headers=headers, content=stream)
        else:
            response = client.request(method, url, headers=headers)
        if response.status_code >= 300:
            raise RuntimeError(f"Staging file {method} failed (HTTP {response.status_code})")


def _upload_to_uc_volume(db, project_id, local_path, volume_path):
    _volume_file_request(db, project_id, "PUT", volume_path, local_path=local_path)
    return volume_path


def _load_table_via_parquet_copy_into(db, project_id, source, table, columns, write_target,
                                    *, max_rows, expected_rows):
    catalog, _, _ = _parse_fqn(write_target)
    path = None
    volume_path = f"/Volumes/{catalog}/bronze/_migration_staging/{uid('bulk')}.parquet"
    try:
        path, count = _export_table_to_parquet(source, table, columns, max_rows)
        if count != expected_rows:
            raise RuntimeError("Source row count changed during Parquet extraction")
        _upload_to_uc_volume(db, project_id, path, volume_path)
        projection = []
        for column in columns:
            name = _qident(column.column_name)
            expression = target_parameter_expression(column).replace("?", name)
            target_type = map_sqlserver_type(column.data_type, column.precision, column.scale)
            projection.append(f"CAST({expression} AS {target_type}) AS {name}")
        projection += [f"{format_sql_literal(source.server_name + '/' + source.database_name)} AS `_migration_source_system`",
                       "current_timestamp() AS `_migration_ingested_at`"]
        sql = (f"COPY INTO {write_target} FROM (SELECT {', '.join(projection)} "
               f"FROM {format_sql_literal(volume_path)}) FILEFORMAT = PARQUET")
        # A unique path and private stage isolate retries from live target data.
        environment_provisioning.project_execute(db, project_id, sql, safe_retry=True)
        if _target_count(db, project_id, write_target) != count:
            raise RuntimeError("Bulk staging row-count validation failed")
        return count
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                logger.warning("Could not remove local migration staging file")
        try:
            _volume_file_request(db, project_id, "DELETE", volume_path)
        except Exception:
            logger.warning("Could not remove temporary migration staging file")


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
    target_fqn: str | None = None,
) -> dict[str, Any]:
    source = db.get(MigrationSource, table.source_id)
    if not source or source.project_id != project_id:
        raise RuntimeError("Source profile not found")
    columns = _columns(db, project_id, table.id)
    if not columns:
        raise RuntimeError("No discovered source columns")
    target = validate_approved_bronze_target(
        target_fqn or _fqn(plan.catalog_name, "bronze", table.object_name),
        expected_catalog=plan.catalog_name,
    )
    target_catalog, target_schema, _ = _parse_fqn(target)
    try:
        environment_provisioning.project_execute(
            db, project_id, f"CREATE CATALOG IF NOT EXISTS `{target_catalog}`", safe_retry=True
        )
        environment_provisioning.project_execute(
            db, project_id, f"CREATE SCHEMA IF NOT EXISTS `{target_catalog}`.`{target_schema}`", safe_retry=True
        )
    except Exception:
        pass
    connection = connector_info(source.id)
    if connection["mode"] == "CONNECTOR":
        connector_request(source.id, "test")

    existing_count = _target_count(db, project_id, target)
    if load_mode == "FULL_LOAD" and existing_count is not None and not replace_existing_data:
        raise RuntimeError(
            f"Target already contains {existing_count} rows; explicitly approve replacement"
        )
    source_total = _source_count(source, table)
    expected_rows = min(source_total, max_rows) if max_rows is not None else source_total

    suffix = re.sub(r"[^A-Za-z0-9_]", "_", run_id[-16:])
    stage = _fqn(target_catalog, target_schema, f"__mf_stage_{suffix}_{table.id[-8:]}")
    bulk_candidate = expected_rows >= BULK_THRESHOLD
    write_target = stage if load_mode == "FULL_LOAD" or bulk_candidate else target
    if write_target == stage:
        environment_provisioning.project_execute(
            db, project_id, f"DROP TABLE IF EXISTS {stage}", safe_retry=True
        )
        environment_provisioning.project_execute(
            db, project_id, f"CREATE TABLE {stage} ({_ddl(columns)}) USING DELTA", safe_retry=False
        )
    if load_mode == "APPEND" and existing_count is None:
        environment_provisioning.project_execute(
            db,
            project_id,
            f"CREATE TABLE IF NOT EXISTS {target} ({_ddl(columns)}) USING DELTA",
            safe_retry=True,
        )

    rows_loaded = 0
    try:
        if bulk_candidate:
            try:
                environment_provisioning.ensure_staging_volume(db, project_id, target_catalog)
                rows_loaded = _load_table_via_parquet_copy_into(
                    db, project_id, source, table, columns, write_target,
                    max_rows=max_rows, expected_rows=expected_rows,
                )
            except Exception:
                logger.warning("Bulk staging failed; restarting with batch inserts")
                # COPY may have committed before a connection failure. Reset only
                # our private stage before fallback, never the live APPEND table.
                environment_provisioning.project_execute(
                    db, project_id, f"DROP TABLE IF EXISTS {stage}", safe_retry=True)
                environment_provisioning.project_execute(
                    db, project_id, f"CREATE TABLE {stage} ({_ddl(columns)}) USING DELTA", safe_retry=False)
                rows_loaded = _load_via_direct_batch_insert(
                    db, project_id, source, table, columns, write_target,
                    batch_size=batch_size, max_rows=max_rows)
        else:
            rows_loaded = _load_via_direct_batch_insert(
                db, project_id, source, table, columns, write_target,
                batch_size=batch_size, max_rows=max_rows)
        if rows_loaded != expected_rows:
            raise RuntimeError(f"Source row-count validation failed: expected {expected_rows}, extracted {rows_loaded}")
        if bulk_candidate and _target_count(db, project_id, stage) != rows_loaded:
            raise RuntimeError("Staging row-count validation failed before publication")
        if load_mode == "FULL_LOAD":
            verb = "CREATE OR REPLACE" if existing_count is not None else "CREATE"
            environment_provisioning.project_execute(
                db,
                project_id,
                f"{verb} TABLE {target} USING DELTA AS SELECT * FROM {stage}",
                safe_retry=False,
            )
        elif bulk_candidate:
            publication_columns = ",".join(
                [_qident(column.column_name) for column in columns]
                + ["`_migration_ingested_at`", "`_migration_source_system`"])
            environment_provisioning.project_execute(
                db, project_id,
                f"INSERT INTO {target} ({publication_columns}) SELECT {publication_columns} FROM {stage}",
                safe_retry=False)
    finally:
        if write_target == stage:
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
        "source_hash": table.source_hash,
        "workspace_host": environment_provisioning.get_configuration(db, project_id).workspace_host,
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
    if len(tables) <= 1:
        for table in tables:
            result = None
            failure = None
            attempt_limit = 3 if mode == "FULL_LOAD" else 1
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
                        time.sleep(2 * attempt)
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
                failure_dict = {
                    "object_id": table.id,
                    "source": f"{table.schema_name}.{table.object_name}",
                    "status": "FAILED",
                    "error": str(failure),
                }
                results.append(failure_dict)
                _record(
                    db,
                    project_id,
                    status="FAILED",
                    run_id=migration_run.id,
                    object_id=table.id,
                    action="TABLE_INGESTION_FAILED",
                    source=failure_dict["source"],
                    error=failure_dict["error"],
                )
    else:
        def _worker_ingest(table_id: str):
            worker_db = SessionLocal()
            try:
                worker_table = worker_db.get(MigrationObject, table_id)
                worker_plan, _ = _requirements(worker_db, project_id)
                attempt_limit = 3 if mode == "FULL_LOAD" else 1
                for attempt in range(1, attempt_limit + 1):
                    try:
                        res = _load_table(
                            worker_db,
                            project_id,
                            migration_run.id,
                            worker_plan,
                            worker_table,
                            batch_size=batch_size,
                            max_rows=max_rows,
                            load_mode=mode,
                            replace_existing_data=replace_existing_data,
                        )
                        return (table_id, res, None)
                    except Exception as exc:
                        transient = any(marker in str(exc).lower() for marker in TRANSIENT)
                        if attempt < attempt_limit and transient:
                            time.sleep(2 * attempt)
                            continue
                        return (table_id, None, exc)
                return (table_id, None, RuntimeError("Unknown ingestion failure"))
            finally:
                worker_db.close()

        is_connector = False
        for t in tables:
            try:
                from app.services.source_connector import connector_info
                if connector_info(t.source_id).get("mode") == "CONNECTOR":
                    is_connector = True
                    break
            except Exception:
                pass
        max_workers = 1 if is_connector else min(len(tables), 4)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {executor.submit(_worker_ingest, table.id): table.id for table in tables}
            table_outcomes = {}
            for future in concurrent.futures.as_completed(future_to_id):
                t_id, res, err = future.result()
                table_outcomes[t_id] = (res, err)

        for table in tables:
            result, failure = table_outcomes.get(table.id, (None, RuntimeError("Missing worker outcome")))
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
                failure_dict = {
                    "object_id": table.id,
                    "source": f"{table.schema_name}.{table.object_name}",
                    "status": "FAILED",
                    "error": str(failure),
                }
                results.append(failure_dict)
                _record(
                    db,
                    project_id,
                    status="FAILED",
                    run_id=migration_run.id,
                    object_id=table.id,
                    action="TABLE_INGESTION_FAILED",
                    source=failure_dict["source"],
                    error=failure_dict["error"],
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
            results.append({"object_id": record.object_id, **payload})
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


def verified_checkpoint(
    db: Session,
    project_id: str,
    tables: list[MigrationObject],
    approved_targets: dict[str, str] | None = None,
    decision_run_id: str | None = None,
) -> dict[str, Any] | None:
    """Reuse completed ingestion only after checking the current source and target."""
    evidence = latest(db, project_id)
    if evidence.get("status") != "PASSED" or not evidence.get("run_id") or not tables:
        return None
    plan = environment_provisioning.get_dev_plan(db, project_id)
    if not plan or plan.status != "PROVISIONED":
        return None
    results = {item.get("object_id"): item for item in evidence.get("results", [])}
    verified = []
    rejections = []
    from app.services.engine import compare_schema
    for table in tables:
        item = results.get(table.id)
        target = (approved_targets or {}).get(
            table.id, _fqn(plan.catalog_name, "bronze", table.object_name)
        )
        target = validate_approved_bronze_target(target, expected_catalog=plan.catalog_name)
        if item and item.get("status") == "PASSED" and not _same_fqn(item.get("target_fqn"), target):
            rejection = {
                "object_id": table.id,
                "action": "CHECKPOINT_TARGET_MISMATCH",
                "checkpoint_reused": False,
                "recorded_target_fqn": item.get("target_fqn"),
                "approved_target_fqn": target,
                "reason": "Verified checkpoint target differs from the current approved Bronze target",
            }
            rejections.append(rejection)
            _record(
                db, project_id, status="SKIPPED", run_id=decision_run_id,
                object_id=table.id, checkpoint_run_id=evidence.get("run_id"),
                **{key: value for key, value in rejection.items() if key != "object_id"},
            )
            continue
        if (not item or item.get("status") != "PASSED"
                or item.get("source") != f"{table.schema_name}.{table.object_name}"):
            return None
        source = db.get(MigrationSource, table.source_id)
        if not source or source.project_id != project_id:
            return None
        # Newly recorded fingerprints invalidate checkpoints after discovery/config changes.
        config = environment_provisioning.get_configuration(db, project_id)
        if item.get("workspace_host") and (not config or item["workspace_host"] != config.workspace_host):
            return None
        if item.get("source_hash") and item["source_hash"] != table.source_hash:
            return None
        source_rows = _source_count(source, table)
        target_rows = _target_count(db, project_id, target)
        if target_rows != source_rows or target_rows != item.get("target_rows"):
            return None
        columns = _columns(db, project_id, table.id)
        expected = [{"name": c.column_name, "type": map_sqlserver_type(c.data_type, c.precision, c.scale)} for c in columns]
        expected += [{"name": "_migration_ingested_at", "type": "TIMESTAMP"},
                     {"name": "_migration_source_system", "type": "STRING"}]
        rows = environment_provisioning.project_execute(db, project_id, f"DESCRIBE TABLE {target}")
        actual = [{"name": str(row[0]), "type": str(row[1])} for row in rows
                  if row and row[0] and not str(row[0]).startswith("#")]
        if compare_schema(expected, actual)["status"] != "IDENTICAL":
            return None
        verified.append({**item, "checkpoint_reused": True})
    return {
        **evidence,
        "results": verified,
        "checkpoint_reused": bool(verified),
        "rejections": rejections,
    }
