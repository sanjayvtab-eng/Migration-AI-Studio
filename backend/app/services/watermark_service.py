from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    MigrationColumn,
    MigrationEnvironmentPlan,
    MigrationObject,
    MigrationProject,
    MigrationRun,
    MigrationSchedule,
    MigrationSource,
    MigrationWatermark,
)
from app.services import environment_provisioning
from app.services.engine import uid
from app.services.source_connector import TableStream, connector_info
from app.services.type_compatibility import (
    format_sql_literal,
    normalize_row,
    source_select_expression,
    target_parameter_expression,
    transport_summary,
)
from app.services.bronze_ingestion import (
    _columns,
    _ddl,
    _fqn,
    _parse_fqn,
    _qident,
    _requirements,
    _source_connection_string,
    _target_count,
    validate_approved_bronze_target,
)
from app.services.email_service import send_migration_schedule_digest
from app.services.source_adapters import adapter_for_source

logger = logging.getLogger(__name__)

WATERMARK_CANDIDATE_NAMES = [
    "modifieddate",
    "modified_date",
    "updatedat",
    "updated_at",
    "lastmodified",
    "last_modified",
    "change_date",
    "changed_at",
    "createddate",
    "created_date",
    "createdat",
    "created_at",
    "creationdate",
    "timestamp",
]

DATETIME_DATA_TYPES = {
    "datetime",
    "datetime2",
    "smalldatetime",
    "date",
    "datetimeoffset",
    "timestamp",
}

INTEGER_DATA_TYPES = {
    "int",
    "bigint",
    "smallint",
    "tinyint",
    "numeric",
    "decimal",
}


def detect_watermark_column(columns: list[MigrationColumn]) -> tuple[str, str]:
    """
    Detect the most appropriate watermark column and type (DATETIME or INTEGER).
    Returns (column_name, watermark_type).
    """
    col_by_name = {c.column_name.lower(): c for c in columns}

    # 1. Look for known modification/creation column names with datetime types
    for cand in WATERMARK_CANDIDATE_NAMES:
        if cand in col_by_name:
            col = col_by_name[cand]
            if col.data_type.lower() in DATETIME_DATA_TYPES:
                return col.column_name, "DATETIME"

    # 2. Look for any datetime column
    for col in columns:
        if col.data_type.lower() in DATETIME_DATA_TYPES:
            return col.column_name, "DATETIME"

    # 3. Look for identity column
    for col in columns:
        if col.is_identity:
            return col.column_name, "INTEGER"

    # 4. Look for id or *_id integer column
    for col in columns:
        c_lower = col.column_name.lower()
        if (c_lower == "id" or c_lower.endswith("_id") or c_lower.endswith("id")) and col.data_type.lower() in INTEGER_DATA_TYPES:
            return col.column_name, "INTEGER"

    # 5. Fallback to the first column
    fallback_col = columns[0]
    w_type = "INTEGER" if fallback_col.data_type.lower() in INTEGER_DATA_TYPES else "DATETIME"
    return fallback_col.column_name, w_type


def detect_primary_keys(columns: list[MigrationColumn], table_name: str) -> list[str]:
    """Detect candidate primary key columns for MERGE INTO join condition."""
    identities = [c.column_name for c in columns if c.is_identity]
    if identities:
        return identities

    t_lower = table_name.lower()
    for c in columns:
        c_lower = c.column_name.lower()
        if c_lower in ("id", f"{t_lower}_id", f"{t_lower}id"):
            return [c.column_name]

    # If no obvious PK, check for column with 'id' in name and integer type
    for c in columns:
        c_lower = c.column_name.lower()
        if ("id" in c_lower) and c.data_type.lower() in INTEGER_DATA_TYPES:
            return [c.column_name]

    return []


def get_or_create_watermark(
    db: Session,
    project_id: str,
    table: MigrationObject,
    columns: list[MigrationColumn],
) -> MigrationWatermark:
    """Retrieve existing watermark tracker or initialize from discovered schema."""
    watermark = (
        db.query(MigrationWatermark)
        .filter(
            MigrationWatermark.project_id == project_id,
            MigrationWatermark.table_name == table.object_name,
        )
        .first()
    )

    if not watermark:
        col_name, w_type = detect_watermark_column(columns)
        watermark = MigrationWatermark(
            id=uid("WMK"),
            project_id=project_id,
            table_name=table.object_name,
            watermark_column=col_name,
            watermark_type=w_type,
            last_watermark_value=None,
            last_synced_rows=0,
            updated_at=datetime.utcnow(),
        )
        db.add(watermark)
        db.commit()
        db.refresh(watermark)

    return watermark


def fetch_incremental_rows(
    source: MigrationSource,
    table: MigrationObject,
    columns: list[MigrationColumn],
    watermark: MigrationWatermark,
    max_rows: int | None = None,
):
    """
    Open an engine-specific incremental cursor while preserving the canonical row contract.
    """
    adapter = adapter_for_source(source)
    context = adapter.open_delta_cursor(
        table, columns, watermark.watermark_column, watermark.last_watermark_value,
        batch_size=max_rows or 1000, max_rows=max_rows,
    )
    cursor = context.__enter__()
    return context, cursor


def run_incremental_table_sync(
    db: Session,
    project_id: str,
    run_id: str,
    plan: MigrationEnvironmentPlan,
    table: MigrationObject,
    *,
    batch_size: int = 1000,
    max_rows: int | None = None,
) -> dict[str, Any]:
    """
    Executes incremental synchronization for a single table:
    1. Reads new delta records from SQL Server since last watermark.
    2. Writes into staging Delta table.
    3. Merges into target Delta Lake table (Unity Catalog) using MERGE INTO.
    4. Advances watermark on successful commit.
    """
    source = db.get(MigrationSource, table.source_id)
    if not source or source.project_id != project_id:
        raise RuntimeError(f"Source profile not found for table {table.object_name}")

    columns = _columns(db, project_id, table.id)
    if not columns:
        raise RuntimeError(f"No discovered columns for table {table.object_name}")

    watermark = get_or_create_watermark(db, project_id, table, columns)
    target = validate_approved_bronze_target(
        _fqn(plan.catalog_name, "bronze", table.object_name),
        expected_catalog=plan.catalog_name,
    )
    target_catalog, target_schema, _ = _parse_fqn(target)

    # Check if target table exists in Databricks
    existing_count = _target_count(db, project_id, target)
    if existing_count is None:
        # Create baseline target table if it doesn't exist
        environment_provisioning.project_execute(
            db,
            project_id,
            f"CREATE TABLE IF NOT EXISTS {target} ({_ddl(columns)}) USING DELTA",
            safe_retry=True,
        )

    # Initialize watermark from target if we have never set one and target already has data
    if watermark.last_watermark_value is None and existing_count and existing_count > 0:
        try:
            with environment_provisioning.project_connection(db, project_id) as conn:
                cur = conn.cursor()
                cur.execute(f"SELECT MAX(`{watermark.watermark_column}`) FROM {target}")
                row = cur.fetchone()
                if row and row[0] is not None:
                    watermark.last_watermark_value = str(row[0])
                    watermark.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"Initialized high-watermark for {table.object_name} from target: {watermark.last_watermark_value}")
        except Exception as e:
            logger.warning(f"Could not initialize watermark from target: {e}")

    # Fetch delta rows from source
    source_context, source_cursor = fetch_incremental_rows(source, table, columns, watermark, max_rows=max_rows)
    try:
        suffix = re.sub(r"[^A-Za-z0-9_]", "_", run_id[-16:])
        stage = _fqn(target_catalog, target_schema, f"__mf_stage_delta_{suffix}_{table.id[-8:]}")

        # Drop and create staging table
        environment_provisioning.project_execute(
            db, project_id, f"DROP TABLE IF EXISTS {stage}", safe_retry=True
        )
        environment_provisioning.project_execute(
            db, project_id, f"CREATE TABLE {stage} ({_ddl(columns)}) USING DELTA", safe_retry=False
        )

        rows_loaded = 0
        new_max_watermark = watermark.last_watermark_value

        # Find watermark column index in projection
        wm_idx = None
        for idx, col in enumerate(columns):
            if col.column_name.lower() == watermark.watermark_column.lower():
                wm_idx = idx
                break

        target_columns = ",".join(
            [_qident(column.column_name) for column in columns]
            + ["`_migration_source_system`"]
        )

        with environment_provisioning.project_connection(db, project_id) as target_connection:
            target_cursor = target_connection.cursor()
            while True:
                batch = source_cursor.fetchmany(batch_size)
                if not batch:
                    break

                payload = []
                for offset, row in enumerate(batch):
                    normalized = normalize_row(columns, tuple(row), row_index=rows_loaded + offset + 1)
                    payload.append(normalized + (f"{source.server_name}/{source.database_name}",))

                    # Track new maximum watermark
                    if wm_idx is not None and row[wm_idx] is not None:
                        val_str = str(row[wm_idx])
                        if new_max_watermark is None or val_str > str(new_max_watermark):
                            new_max_watermark = val_str

                CHUNK_SIZE = 500
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
                        f"INSERT INTO {stage} ({target_columns}, `_migration_ingested_at`) "
                        f"VALUES {','.join(row_sql_items)}"
                    )
                    target_cursor.execute(multi_insert_sql)
                rows_loaded += len(payload)

        # Merge or append into target Delta table
        if rows_loaded > 0:
            pk_cols = detect_primary_keys(columns, table.object_name)
            if pk_cols:
                join_cond = " AND ".join(f"t.`{col}` = s.`{col}`" for col in pk_cols)
                update_cols = ", ".join(f"`{col.column_name}` = s.`{col.column_name}`" for col in columns)
                all_cols = ", ".join([f"`{c.column_name}`" for c in columns] + ["`_migration_ingested_at`", "`_migration_source_system`"])
                insert_vals = ", ".join([f"s.`{c.column_name}`" for c in columns] + ["s.`_migration_ingested_at`", "s.`_migration_source_system`"])

                merge_sql = f"""
                MERGE INTO {target} AS t
                USING {stage} AS s
                ON {join_cond}
                WHEN MATCHED THEN
                    UPDATE SET {update_cols}, t.`_migration_ingested_at` = s.`_migration_ingested_at`
                WHEN NOT MATCHED THEN
                    INSERT ({all_cols}) VALUES ({insert_vals})
                """
                logger.info(f"Merging {rows_loaded} rows into {target} on {join_cond}")
                environment_provisioning.project_execute(db, project_id, merge_sql, safe_retry=False)
            else:
                publication_cols = ",".join(
                    [_qident(column.column_name) for column in columns]
                    + ["`_migration_ingested_at`", "`_migration_source_system`"]
                )
                append_sql = f"INSERT INTO {target} ({publication_cols}) SELECT {publication_cols} FROM {stage}"
                logger.info(f"Appending {rows_loaded} rows into {target}")
                environment_provisioning.project_execute(db, project_id, append_sql, safe_retry=False)

            # Advance watermark
            if new_max_watermark:
                watermark.last_watermark_value = str(new_max_watermark)
            watermark.last_synced_rows = rows_loaded
            watermark.updated_at = datetime.utcnow()
            db.commit()

        # Cleanup stage table
        try:
            environment_provisioning.project_execute(db, project_id, f"DROP TABLE IF EXISTS {stage}", safe_retry=True)
        except Exception:
            pass

        final_target_count = _target_count(db, project_id, target)
        return {
            "table": table.object_name,
            "status": "PASSED",
            "delta_rows": rows_loaded,
            "watermark_column": watermark.watermark_column,
            "watermark_value": watermark.last_watermark_value,
            "target_count": final_target_count,
        }
    finally:
        try:
            source_context.__exit__(None, None, None)
        except Exception:
            pass


async def run_incremental_sync_for_project(
    db: Session,
    project_id: str,
    *,
    actor: str = "SCHEDULER",
) -> dict[str, Any]:
    """
    Executes incremental sync across all tables configured in the project,
    updates schedule metadata, and sends email summary if enabled.
    """
    start_time = time.time()
    plan, tables = _requirements(db, project_id)
    project = db.get(MigrationProject, project_id)
    project_name = project.name if project else project_id

    run_id = uid("IRU")
    migration_run = MigrationRun(
        id=run_id,
        project_id=project_id,
        stage="INCREMENTAL_SYNC",
        environment="DEV",
        status="RUNNING",
        started_at=datetime.utcnow(),
    )
    db.add(migration_run)
    db.commit()

    table_results = []
    total_delta = 0
    overall_status = "SUCCESS"

    for table in tables:
        try:
            res = run_incremental_table_sync(db, project_id, run_id, plan, table)
            table_results.append(res)
            total_delta += res.get("delta_rows", 0)
        except Exception as exc:
            logger.error(f"Incremental sync failed for {table.object_name}: {exc}", exc_info=True)
            overall_status = "FAILED"
            table_results.append({
                "table": table.object_name,
                "status": "FAILED",
                "delta_rows": 0,
                "error": str(exc),
            })

    duration = time.time() - start_time
    migration_run.status = overall_status
    migration_run.completed_at = datetime.utcnow()
    db.commit()

    summary = {
        "status": overall_status,
        "run_id": run_id,
        "project_id": project_id,
        "project_name": project_name,
        "executed_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "duration_seconds": round(duration, 2),
        "total_delta_rows": total_delta,
        "tables": table_results,
    }

    # Update schedule status
    schedule = db.query(MigrationSchedule).filter(MigrationSchedule.project_id == project_id).first()
    if schedule:
        schedule.last_run_at = datetime.utcnow()
        schedule.last_run_status = overall_status
        import json
        schedule.last_run_summary_json = json.dumps(summary)
        # Advance next_run_at
        from app.services.scheduler_service import compute_next_run_at
        schedule.next_run_at = compute_next_run_at(schedule.frequency, schedule.scheduled_time, schedule.timezone_offset or 0)
        db.commit()

        # Send digest email if configured
        if schedule.notification_email:
            try:
                await send_migration_schedule_digest(schedule.notification_email, project_name, summary)
            except Exception as mail_err:
                logger.error(f"Failed to send email digest: {mail_err}")

    return summary
