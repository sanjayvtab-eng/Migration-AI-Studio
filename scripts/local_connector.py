"""Run on the SQL Server network. No inbound listener or arbitrary SQL endpoint.
Supports Standalone Binary execution, Smart Configuration (.env / agent.env), and CLI arguments.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time as time_type
from decimal import Decimal
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID


def quoted(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or "\x00" in value:
        raise ValueError("Invalid SQL identifier")
    return "[" + value.replace("]", "]]") + "]"


def odbc_value(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return {"kind": "decimal", "value": str(value)}
    if isinstance(value, (bytes, bytearray)):
        return {"kind": "bytes", "value": bytes(value).hex()}
    if isinstance(value, (datetime, date, time_type)):
        return {"kind": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, UUID):
        return str(value)
    raise ValueError("Unsupported source value type")


DISCOVERY_SQL = r"""
SELECT DB_NAME() AS database_name, s.name AS schema_name, o.name AS object_name,
       CASE o.type WHEN 'U' THEN 'TABLE' WHEN 'V' THEN 'VIEW' WHEN 'P' THEN 'PROCEDURE'
                   WHEN 'FN' THEN 'FUNCTION' WHEN 'IF' THEN 'FUNCTION' WHEN 'TF' THEN 'FUNCTION'
                   WHEN 'TR' THEN 'TRIGGER' ELSE o.type_desc END AS object_type,
       m.definition
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id=o.schema_id
LEFT JOIN sys.sql_modules m ON m.object_id=o.object_id
WHERE o.is_ms_shipped=0 AND o.type IN ('U','V','P','FN','IF','TF','TR');
"""

COLUMN_SQL = r"""
SELECT s.name schema_name,o.name object_name,c.name column_name,c.column_id,
       t.name declared_data_type, TYPE_NAME(c.system_type_id) system_data_type, t.is_user_defined,
       c.max_length,c.precision,c.scale,c.is_nullable,c.is_identity,c.is_computed,
       dc.definition default_definition, c.collation_name
FROM sys.objects o JOIN sys.schemas s ON o.schema_id=s.schema_id
JOIN sys.columns c ON c.object_id=o.object_id JOIN sys.types t ON c.user_type_id=t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id=dc.object_id
WHERE o.is_ms_shipped=0 AND o.type IN ('U','V');
"""

DEPENDENCY_SQL = r"""
SELECT
    d.referencing_id,
    OBJECT_SCHEMA_NAME(d.referencing_id) AS referencing_schema_name,
    OBJECT_NAME(d.referencing_id) AS referencing_entity_name,
    d.referenced_id,
    d.referenced_server_name,
    d.referenced_database_name,
    d.referenced_schema_name,
    d.referenced_entity_name,
    d.referenced_minor_id,
    c.name AS referenced_column_name,
    CASE
        WHEN d.referenced_server_name IS NOT NULL THEN 'EXTERNAL_SERVER'
        WHEN d.referenced_database_name IS NOT NULL AND d.referenced_database_name <> DB_NAME() THEN 'CROSS_DATABASE'
        WHEN d.referenced_schema_name IS NOT NULL AND d.referenced_schema_name <> OBJECT_SCHEMA_NAME(d.referencing_id) THEN 'CROSS_SCHEMA'
        ELSE 'LOCAL'
    END AS dependency_scope,
    d.is_schema_bound_reference,
    d.is_caller_dependent,
    d.is_ambiguous
FROM sys.sql_expression_dependencies AS d
LEFT JOIN sys.columns AS c
    ON c.object_id = d.referenced_id
   AND c.column_id = d.referenced_minor_id
WHERE d.referenced_entity_name IS NOT NULL;
"""

KEY_CONSTRAINT_SQL = r"""
SELECT s.name AS schema_name, o.name AS object_name, kc.name AS constraint_name,
       kc.type_desc AS constraint_type, ic.key_ordinal, c.name AS column_name
FROM sys.key_constraints kc
JOIN sys.objects o ON o.object_id=kc.parent_object_id
JOIN sys.schemas s ON s.schema_id=o.schema_id
JOIN sys.index_columns ic ON ic.object_id=o.object_id AND ic.index_id=kc.unique_index_id
JOIN sys.columns c ON c.object_id=o.object_id AND c.column_id=ic.column_id
WHERE o.is_ms_shipped=0 AND kc.type IN ('PK','UQ')
ORDER BY s.name,o.name,kc.name,ic.key_ordinal;
"""

FOREIGN_KEY_SQL = r"""
SELECT ps.name AS schema_name, po.name AS object_name, fk.name AS constraint_name,
       fkc.constraint_column_id AS ordinal, pc.name AS column_name,
       rs.name AS referenced_schema, ro.name AS referenced_object, rc.name AS referenced_column
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id
JOIN sys.objects po ON po.object_id=fk.parent_object_id
JOIN sys.schemas ps ON ps.schema_id=po.schema_id
JOIN sys.columns pc ON pc.object_id=po.object_id AND pc.column_id=fkc.parent_column_id
JOIN sys.objects ro ON ro.object_id=fk.referenced_object_id
JOIN sys.schemas rs ON rs.schema_id=ro.schema_id
JOIN sys.columns rc ON rc.object_id=ro.object_id AND rc.column_id=fkc.referenced_column_id
WHERE po.is_ms_shipped=0
ORDER BY ps.name,po.name,fk.name,fkc.constraint_column_id;
"""

TABLE_STATS_SQL = r"""
SELECT s.name AS schema_name,o.name AS object_name,
       SUM(CASE WHEN p.index_id IN (0,1) THEN p.row_count ELSE 0 END) AS approx_row_count
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id=o.schema_id
JOIN sys.dm_db_partition_stats p ON p.object_id=o.object_id
WHERE o.is_ms_shipped=0 AND o.type='U'
GROUP BY s.name,o.name;
"""

PARAMETER_SQL = r"""
SELECT s.name AS schema_name,o.name AS object_name,p.name AS parameter_name,p.parameter_id,
       t.name AS data_type,p.max_length,p.precision,p.scale,p.is_output
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id=o.schema_id
JOIN sys.parameters p ON p.object_id=o.object_id
JOIN sys.types t ON t.user_type_id=p.user_type_id
WHERE o.is_ms_shipped=0 AND o.type IN ('P','FN','IF','TF');
"""


def connection_diagnostic(error: Exception) -> str:
    message = str(error).lower()
    if "4060" in message or "cannot open database" in message or "permission" in message:
        return "DATABASE_ACCESS: Verify the database name and grant the connector account read and metadata permissions."
    if "28000" in message or "login failed" in message or "18456" in message:
        return "AUTHENTICATION_FAILED: Verify the SQL login or the Windows account running the local connector."
    if "certificate" in message or "ssl" in message:
        return "TLS_ERROR: Verify the SQL Server certificate and encryption settings."
    if any(word in message for word in ("timeout", "hyt00", "08001", "network-related", "server does not exist", "server is not found", "not accessible", "error locating server")):
        return ("NETWORK_UNREACHABLE: The backend or connector could not reach SQL Server. "
                "Check if the server/instance name is correct (e.g. SHANJI\\SQLEXPRESS or .\\SQLEXPRESS), if the service is running, and if TCP/IP or Named Pipes are enabled.")
    if "im002" in message or "data source name not found" in message or ("driver" in message and ("can't open lib" in message or "failed to load" in message)):
        return "DRIVER_MISSING: Install the configured Microsoft ODBC Driver on the machine running the connection."
    return "SOURCE_OPERATION_FAILED: Check SQL Server read permissions, supported data types and connector configuration."


def test_sqlserver_connection(connection_string: str) -> dict[str, Any]:
    import pyodbc
    with pyodbc.connect(connection_string, timeout=10) as conn:
        cur = conn.cursor()
        row = cur.execute("SELECT @@SERVERNAME AS server_name, DB_NAME() AS database_name, CAST(SERVERPROPERTY('ProductVersion') AS varchar(128)) AS product_version").fetchone()
        return {"ok": True, "server": row.server_name, "database": row.database_name, "product_version": row.product_version}


def discover_sqlserver(connection_string: str) -> dict[str, Any]:
    import pyodbc
    try:
        with pyodbc.connect(connection_string, timeout=20) as conn:
            cur = conn.cursor()
            objs = cur.execute(DISCOVERY_SQL).fetchall()
            cols = cur.execute(COLUMN_SQL).fetchall()
            deps = cur.execute(DEPENDENCY_SQL).fetchall()
            params = cur.execute(PARAMETER_SQL).fetchall()
            try:
                key_constraints = cur.execute(KEY_CONSTRAINT_SQL).fetchall()
            except Exception:
                key_constraints = []
            try:
                foreign_keys = cur.execute(FOREIGN_KEY_SQL).fetchall()
            except Exception:
                foreign_keys = []
            try:
                table_stats = cur.execute(TABLE_STATS_SQL).fetchall()
            except Exception:
                table_stats = []
            by = {(r.schema_name, r.object_name): [] for r in objs}
            for c in cols:
                by.setdefault((c.schema_name, c.object_name), []).append({
                    "name": c.column_name, "ordinal": c.column_id,
                    "type": (c.system_data_type if bool(c.is_user_defined) and c.system_data_type else c.declared_data_type),
                    "declared_type": c.declared_data_type, "system_type": c.system_data_type, "is_user_defined": bool(c.is_user_defined),
                    "max_length": c.max_length, "precision": c.precision, "scale": c.scale,
                    "nullable": bool(c.is_nullable), "identity": bool(c.is_identity),
                    "computed": bool(c.is_computed), "default": c.default_definition,
                    "collation": c.collation_name
                })
            dep_by: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for d in deps:
                dep_by.setdefault((d.referencing_schema_name, d.referencing_entity_name), []).append({
                    "server": d.referenced_server_name, "database": d.referenced_database_name,
                    "schema": d.referenced_schema_name, "object": d.referenced_entity_name,
                    "column": d.referenced_column_name, "referenced_minor_id": d.referenced_minor_id,
                    "type": d.dependency_scope, "is_schema_bound_reference": bool(d.is_schema_bound_reference),
                    "is_caller_dependent": bool(d.is_caller_dependent), "is_ambiguous": bool(d.is_ambiguous),
                })
            par_by: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for p in params:
                par_by.setdefault((p.schema_name, p.object_name), []).append({
                    "name": p.parameter_name, "ordinal": p.parameter_id, "type": p.data_type,
                    "max_length": p.max_length, "precision": p.precision, "scale": p.scale,
                    "is_output": bool(p.is_output)
                })
            constraint_by: dict[tuple[str, str], list[dict[str, Any]]] = {}
            grouped_keys: dict[tuple[str, str, str], dict[str, Any]] = {}
            for k in key_constraints:
                key = (k.schema_name, k.object_name, k.constraint_name)
                row = grouped_keys.setdefault(key, {
                    "name": k.constraint_name,
                    "type": "PRIMARY_KEY" if str(k.constraint_type).upper().startswith("PRIMARY") else "UNIQUE",
                    "columns": [],
                })
                row["columns"].append(k.column_name)
            for (sch, obj, _), row in grouped_keys.items():
                constraint_by.setdefault((sch, obj), []).append(row)
            grouped_fks: dict[tuple[str, str, str], dict[str, Any]] = {}
            for f in foreign_keys:
                key = (f.schema_name, f.object_name, f.constraint_name)
                row = grouped_fks.setdefault(key, {
                    "name": f.constraint_name, "type": "FOREIGN_KEY", "columns": [],
                    "referenced_schema": f.referenced_schema, "referenced_object": f.referenced_object,
                    "referenced_columns": [],
                })
                row["columns"].append(f.column_name)
                row["referenced_columns"].append(f.referenced_column)
            for (sch, obj, _), row in grouped_fks.items():
                constraint_by.setdefault((sch, obj), []).append(row)
            stats_by = {(r.schema_name, r.object_name): int(r.approx_row_count or 0) for r in table_stats}
            return {
                "database": objs[0].database_name if objs else "",
                "objects": [{
                    "database": r.database_name, "schema": r.schema_name, "name": r.object_name,
                    "type": r.object_type, "definition": r.definition,
                    "columns": by.get((r.schema_name, r.object_name), []),
                    "dependencies": dep_by.get((r.schema_name, r.object_name), []),
                    "parameters": par_by.get((r.schema_name, r.object_name), []),
                    "constraints": constraint_by.get((r.schema_name, r.object_name), []),
                    "approx_row_count": stats_by.get((r.schema_name, r.object_name))
                } for r in objs]
            }
    except Exception as e:
        raise RuntimeError(connection_diagnostic(e)) from e


def source_select_expression(column: Any) -> str:
    name = quoted(str(column.column_name))
    raw_type = (getattr(column, "data_type", "") or "").lower().strip()
    if raw_type in {"binary", "varbinary", "image", "timestamp", "rowversion"}:
        return f"CONVERT(VARCHAR(MAX), CONVERT(VARBINARY(MAX), {name}), 2) AS {name}"
    if raw_type in {"uniqueidentifier"}:
        return f"CONVERT(VARCHAR(36), {name}) AS {name}"
    if raw_type in {"xml", "sql_variant", "time", "datetimeoffset"}:
        return f"CONVERT(NVARCHAR(MAX), {name}) AS {name}"
    if raw_type in {"hierarchyid"}:
        return f"CASE WHEN {name} IS NULL THEN NULL ELSE {name}.ToString() END AS {name}"
    if raw_type in {"geography", "geometry"}:
        return (
            f"CASE WHEN {name} IS NULL THEN NULL ELSE "
            f"CONCAT('SRID=', {name}.STSrid, ';', {name}.STAsText()) END AS {name}"
        )
    return name


class LocalAgent:
    def __init__(self, source_id: str, server: str, database: str, connection_string: str):
        self.source_id, self.server, self.database = source_id, server, database
        self.connection_string = connection_string
        self.streams: dict[str, list[Any]] = {}

    def connect(self):
        import pyodbc
        try:
            conn = pyodbc.connect(self.connection_string, timeout=10, autocommit=True)
            conn.timeout = 60
            return conn
        except pyodbc.Error as exc:
            if "IM002" in str(exc):
                installed = [d for d in pyodbc.drivers() if "SQL Server" in d]
                for alt in ["ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server", "SQL Server"]:
                    if alt in installed and alt not in self.connection_string:
                        alt_cs = re.sub(r"DRIVER=\{[^}]+\}", f"DRIVER={{{alt}}}", self.connection_string)
                        try:
                            conn = pyodbc.connect(alt_cs, timeout=10, autocommit=True)
                            conn.timeout = 60
                            self.connection_string = alt_cs
                            return conn
                        except Exception:
                            continue
            raise

    def cleanup(self, all_streams: bool = False):
        for key, item in list(self.streams.items()):
            if all_streams or time.monotonic() - item[2] > 150:
                try:
                    item[0].close()
                finally:
                    del self.streams[key]

    def handle(self, task: dict[str, Any]) -> dict[str, Any]:
        if (task.get("source_id"), task.get("server"), task.get("database")) != (
                self.source_id, self.server, self.database):
            raise ValueError("Source identity mismatch; verify the registered source profile")
        op, data = task["operation"], task.get("payload", {})
        self.cleanup()
        if op == "test":
            conn = self.connect()
            conn.close()
            return test_sqlserver_connection(self.connection_string)
        if op == "discover":
            conn = self.connect()
            conn.close()
            return discover_sqlserver(self.connection_string)
        if op == "close":
            item = self.streams.pop(data.get("stream_id"), None)
            if item:
                item[0].close()
            return {"closed": True}
        if op == "fetch":
            stream = self.streams.get(data.get("stream_id"))
            if not stream:
                raise ValueError("Source stream expired; restart the deployment after reviewing partial target data")
            stream[2] = time.monotonic()
            size = min(max(int(data.get("size", 1000)), 1), 1000)
            rows, byte_count = [], 0
            for _ in range(size):
                row = stream[3] if stream[3] is not None else stream[1].fetchone()
                stream[3] = None
                if row is None:
                    break
                encoded = [encode_value(v) for v in row]
                length = len(json.dumps(encoded, allow_nan=False).encode())
                if length > 3 * 1024 * 1024:
                    raise ValueError("Source row exceeds connector 3 MiB row limit")
                if rows and byte_count + length > 3 * 1024 * 1024:
                    stream[3] = row
                    break
                rows.append(encoded)
                byte_count += length
            return {"rows": rows}
        if op not in {"count", "open"}:
            raise ValueError("Unsupported operation")
        schema, table = data.get("schema"), data.get("table")
        table_sql = quoted(schema) + "." + quoted(table)
        if len(self.streams) >= 4 and op == "open":
            raise ValueError("Connector stream capacity reached")
        conn = self.connect()
        try:
            cur = conn.cursor()
            found = cur.execute("SELECT t.object_id FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id "
                                "WHERE s.name=? AND t.name=? AND t.is_ms_shipped=0", schema, table).fetchone()
            if not found:
                raise ValueError("Source table not found or read permission missing")
            if op == "count":
                return {"count": int(cur.execute("SELECT COUNT_BIG(*) FROM " + table_sql).fetchone()[0])}
            metadata = cur.execute("SELECT c.name, CASE WHEN t.is_user_defined=1 THEN TYPE_NAME(c.system_type_id) "
                                   "ELSE t.name END, c.precision, c.scale FROM sys.columns c "
                                   "JOIN sys.types t ON t.user_type_id=c.user_type_id "
                                   "WHERE c.object_id=? AND c.is_computed=0", found[0]).fetchall()
            columns = {r[0]: SimpleNamespace(column_name=r[0], data_type=r[1], precision=r[2], scale=r[3]) for r in metadata}
            requested = data.get("columns")
            if not isinstance(requested, list) or not requested or any(name not in columns for name in requested):
                raise ValueError("Source columns changed; repeat discovery before deployment")
            limit = data.get("max_rows")
            if limit is not None and (type(limit) is not int or limit < 1):
                raise ValueError("Invalid source row limit")
            top = f"TOP ({limit}) " if limit is not None else ""
            projection = ",".join(source_select_expression(columns[name]) for name in requested)
            cur.execute("SELECT " + top + projection + " FROM " + table_sql)
            stream_id = secrets.token_hex(24)
            self.streams[stream_id] = [conn, cur, time.monotonic(), None]
            conn = None
            return {"stream_id": stream_id}
        finally:
            if conn is not None:
                conn.close()


def validate_url(url: str) -> str:
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower()
    loopback = hostname in {"localhost", "127.0.0.1", "::1"}
    secure_transport = parts.scheme == "https" or (parts.scheme == "http" and loopback)
    if not secure_transport or not hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(
            "Connector requires HTTPS; HTTP is allowed only for localhost/127.0.0.1/::1 development URLs. "
            "Embedded credentials and query parameters are not allowed"
        )
    return url.rstrip("/") + "/api"


def load_config_file(filepath: Path | None) -> dict[str, str]:
    config: dict[str, str] = {}
    if not filepath or not filepath.is_file():
        return config
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip("'\"")
    except Exception:
        pass
    return config


def find_config_path(cli_path: str | None = None) -> Path | None:
    if cli_path:
        p = Path(cli_path)
        if p.is_file():
            return p
    for name in ["agent.env", "connector.env", ".env"]:
        p = Path.cwd() / name
        if p.is_file():
            return p
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    for name in ["agent.env", "connector.env", ".env"]:
        p = base_dir / name
        if p.is_file():
            return p
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Migration AI Studio URL (e.g. https://databricks-migration-factory-819s.onrender.com)")
    parser.add_argument("--source", help="Migration source profile ID (e.g. SRC_xxxx)")
    parser.add_argument("--server", help="Local SQL Server instance (e.g. localhost\\SQLEXPRESS or SHANJI\\SQLEXPRESS)")
    parser.add_argument("--database", help="Target source database name")
    parser.add_argument("--driver", default=None, help="ODBC Driver (default: ODBC Driver 17 for SQL Server)")
    parser.add_argument("--username", help="SQL login (omit to use current Windows account)")
    parser.add_argument("--password", help="SQL login password")
    parser.add_argument("--trust-server-certificate", dest="trust_cert", action="store_true", default=None, help="Trust SQL Server certificate")
    parser.add_argument("--no-trust-server-certificate", dest="trust_cert", action="store_false", help="Do not trust SQL Server certificate")
    parser.add_argument("--token", help="Connector registration token")
    parser.add_argument("--config", help="Path to custom agent.env file")
    args = parser.parse_args()

    config_path = find_config_path(args.config)
    file_cfg = load_config_file(config_path)

    url = args.url or os.environ.get("CONNECTOR_URL") or file_cfg.get("CONNECTOR_URL")
    source = args.source or os.environ.get("CONNECTOR_SOURCE") or os.environ.get("CONNECTOR_SOURCE_ID") or file_cfg.get("CONNECTOR_SOURCE") or file_cfg.get("CONNECTOR_SOURCE_ID")
    server = args.server or os.environ.get("CONNECTOR_SERVER") or file_cfg.get("CONNECTOR_SERVER")
    database = args.database or os.environ.get("CONNECTOR_DATABASE") or file_cfg.get("CONNECTOR_DATABASE")
    token = args.token or os.environ.get("CONNECTOR_TOKEN") or file_cfg.get("CONNECTOR_TOKEN")
    driver = args.driver or os.environ.get("CONNECTOR_DRIVER") or file_cfg.get("CONNECTOR_DRIVER") or "ODBC Driver 17 for SQL Server"

    if args.trust_cert is not None:
        trust_cert = args.trust_cert
    elif "CONNECTOR_TRUST_CERT" in os.environ:
        trust_cert = os.environ.get("CONNECTOR_TRUST_CERT", "").lower() in ("1", "true", "yes")
    elif "CONNECTOR_TRUST_CERT" in file_cfg:
        trust_cert = file_cfg.get("CONNECTOR_TRUST_CERT", "").lower() in ("1", "true", "yes")
    else:
        trust_cert = True

    username = args.username or os.environ.get("CONNECTOR_USERNAME") or file_cfg.get("CONNECTOR_USERNAME")
    password = args.password or os.environ.get("CONNECTOR_SQL_PASSWORD") or os.environ.get("CONNECTOR_PASSWORD") or file_cfg.get("CONNECTOR_PASSWORD")

    is_interactive = sys.stdin.isatty()
    need_save = False

    if not url:
        if is_interactive:
            url = input("Migration Studio Application URL (e.g. https://...): ").strip()
            need_save = True
        else:
            raise SystemExit("Error: --url or CONNECTOR_URL is required.")

    if not source:
        if is_interactive:
            source = input("Source Profile ID (from Studio UI, e.g. SRC_xxxx): ").strip()
            need_save = True
        else:
            raise SystemExit("Error: --source or CONNECTOR_SOURCE is required.")

    if not server:
        if is_interactive:
            server = input(r"SQL Server instance name (e.g. localhost\SQLEXPRESS): ").strip()
            need_save = True
        else:
            raise SystemExit("Error: --server or CONNECTOR_SERVER is required.")

    if not database:
        if is_interactive:
            database = input("Database name to migrate: ").strip()
            need_save = True
        else:
            raise SystemExit("Error: --database or CONNECTOR_DATABASE is required.")

    if not token:
        if is_interactive:
            token = getpass.getpass("Connector registration token: ").strip()
            need_save = True
        else:
            raise SystemExit("Error: Registration token is required via --token, CONNECTOR_TOKEN or interactive prompt.")

    if need_save and is_interactive and not config_path:
        save_choice = input("\nSave these settings to 'agent.env' for automatic connection next time? [Y/n]: ").strip().lower()
        if save_choice in ("", "y", "yes"):
            save_target = Path.cwd() / "agent.env"
            try:
                with open(save_target, "w", encoding="utf-8") as f:
                    f.write("# Databricks Migration AI Studio - Saved Agent Configuration\n")
                    f.write(f"CONNECTOR_URL={url}\n")
                    f.write(f"CONNECTOR_SOURCE={source}\n")
                    f.write(f"CONNECTOR_SERVER={server}\n")
                    f.write(f"CONNECTOR_DATABASE={database}\n")
                    f.write(f"CONNECTOR_TOKEN={token}\n")
                    f.write(f"CONNECTOR_DRIVER={driver}\n")
                    f.write(f"CONNECTOR_TRUST_CERT={'true' if trust_cert else 'false'}\n")
                    if username:
                        f.write(f"CONNECTOR_USERNAME={username}\n")
                print(f"[OK] Configuration saved to {save_target.name}")
            except Exception as e:
                print(f"[Notice] Could not save agent.env: {e}")

    base = validate_url(url)
    credentials = "Trusted_Connection=yes;"
    if username:
        if not password and is_interactive:
            password = getpass.getpass("SQL Server password: ")
        credentials = f"UID={odbc_value(username)};PWD={odbc_value(password or '')};"

    clean_driver = driver.strip("\"'{}")
    connection = (f"DRIVER={odbc_value(clean_driver)};SERVER={odbc_value(server)};"
                  f"DATABASE={odbc_value(database)};{credentials}Encrypt=yes;"
                  f"TrustServerCertificate={'yes' if trust_cert else 'no'};")

    agent = LocalAgent(source, server, database, connection)
    import httpx
    stopped = threading.Event()
    instance_id = secrets.token_hex(16)

    print("\n" + "=" * 68)
    print("      Databricks Migration AI Studio - Local Agent Online")
    print("=" * 68)
    print(f"  Target Studio: {url}")
    print(f"  Source Profile: {source}")
    print(f"  SQL Server:     {server}")
    print(f"  Database:       {database}")
    print(f"  Driver:         {clean_driver}")
    print(f"  Authentication: {'SQL Login (' + username + ')' if username else 'Windows Authentication'}")
    print(f"  SSL Cert:       {'TrustServerCertificate=yes' if trust_cert else 'Standard validation'}")
    print("-" * 68)
    print("Connector started. Keep this process running; SQL credentials stay on this machine.")
    print("Press Ctrl+C to stop.")
    print("=" * 68 + "\n")

    try:
        with httpx.Client(headers={"Authorization": "Bearer " + token, "X-Connector-Instance": instance_id}, timeout=30, follow_redirects=False) as client:
            def keep_alive():
                while not stopped.wait(15):
                    try:
                        heartbeat = client.post(base + "/connector/heartbeat")
                        if heartbeat.status_code in {401, 403, 409}:
                            print("Connector registration revoked or another instance is active. Stopping.")
                            stopped.set()
                    except httpx.HTTPError:
                        pass
            worker = threading.Thread(target=keep_alive, daemon=True)
            worker.start()
            while not stopped.is_set():
                agent.cleanup()
                try:
                    response = client.post(base + "/connector/poll")
                    if response.status_code in {401, 403, 409}:
                        raise SystemExit("Registration rejected, revoked, or another connector is active. Check Sources in Studio.")
                    response.raise_for_status()
                    task = response.json().get("task")
                    if task:
                        try:
                            result = agent.handle(task)
                            ok = True
                            if len(json.dumps(result, allow_nan=False).encode()) > 3500000:
                                raise ValueError("Result exceeds connector payload limit; reduce the source scope")
                        except Exception as error:
                            ok = False
                            message = str(error) if isinstance(error, (ValueError, RuntimeError)) else connection_diagnostic(error)
                            result = {"error": message}
                        payload = {"lease": task["lease"], "ok": ok, "result": result}
                        for attempt in range(3):
                            try:
                                reply = client.post(base + f"/connector/tasks/{task['id']}/result", json=payload)
                                if reply.status_code in {404, 409}:
                                    break
                                reply.raise_for_status()
                                break
                            except httpx.HTTPError:
                                if attempt == 2:
                                    raise
                                time.sleep(1)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {task['operation']}: {'completed' if ok else 'failed'}")
                    else:
                        time.sleep(2)
                except httpx.HTTPError:
                    print("Hosted application unreachable. Retrying in 5 seconds...")
                    time.sleep(5)
    except KeyboardInterrupt:
        print("\nConnector stopped by user.")
    except SystemExit as e:
        print(f"\n[Connector Stopped] {e}")
        print("Tip: If you re-registered or replaced registration in Studio, open 'agent.env' in Notepad and update CONNECTOR_TOKEN.")
    except Exception as e:
        print(f"\n[Error] {e}")
    finally:
        stopped.set()
        agent.cleanup(all_streams=True)
        if getattr(sys, "frozen", False):
            input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
