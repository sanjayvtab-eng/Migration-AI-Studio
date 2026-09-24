from __future__ import annotations
from typing import Any

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


def _driver_error_hint(message: str) -> str:
    m = message.lower()
    if "data source name not found" in m or "driver" in m and "not found" in m:
        return "Install the configured Microsoft ODBC Driver for SQL Server or correct SQLSERVER_DRIVER in .env."
    if "login failed" in m:
        return "Verify SQL Server authentication mode, username/password, or Windows account permissions."
    if "cannot open database" in m or "4060" in m:
        return "Verify the source database name and that the login has access to it."
    if "server does not exist" in m or "network-related" in m or "timeout" in m:
        return "Verify server/instance name, SQL Server service, TCP/IP, firewall, and network reachability."
    if "certificate" in m or "ssl" in m:
        return "Verify SQL Server certificate settings. Local DEV can use TrustServerCertificate=yes as configured."
    return "Check SQL Server connectivity, credentials, ODBC driver, database access, and backend terminal logs."


def connection_diagnostic(error: Exception) -> str:
    """Do not forward raw driver text, connection strings or credentials to clients."""
    message = str(error).lower()
    if "4060" in message or "cannot open database" in message or "permission" in message:
        return "DATABASE_ACCESS: Verify the database name and grant the connector account read and metadata permissions."
    if "28000" in message or "login failed" in message or "18456" in message:
        return "AUTHENTICATION_FAILED: Verify the SQL login or the Windows account running the local connector."
    if "certificate" in message or "ssl" in message:
        return "TLS_ERROR: Verify the SQL Server certificate and encryption settings."
    if "im002" in message or "driver" in message and ("not found" in message or "can't open" in message):
        return "DRIVER_MISSING: Install the configured Microsoft ODBC Driver on the machine running the connection."
    if any(word in message for word in ("timeout", "hyt00", "08001", "network-related", "server does not exist")):
        return ("NETWORK_UNREACHABLE: The backend could not reach SQL Server. For a local SQL Server with a hosted "
                "backend, register and start a local connector. Otherwise verify hostname, TCP port and firewall access.")
    return "SOURCE_OPERATION_FAILED: Check SQL Server read permissions, supported data types and connector configuration."


def test_sqlserver_connection(connection_string: str) -> dict[str, Any]:
    try:
        import pyodbc
    except Exception as e:
        raise RuntimeError("pyodbc is required for live SQL Server connectivity") from e
    try:
        with pyodbc.connect(connection_string, timeout=10) as conn:
            cur = conn.cursor()
            row = cur.execute("SELECT @@SERVERNAME AS server_name, DB_NAME() AS database_name, CAST(SERVERPROPERTY('ProductVersion') AS varchar(128)) AS product_version").fetchone()
            return {"ok": True, "server": row.server_name, "database": row.database_name, "product_version": row.product_version}
    except Exception as e:
        raise RuntimeError(connection_diagnostic(e)) from e


def discover_sqlserver(connection_string: str) -> dict[str, Any]:
    try:
        import pyodbc
    except Exception as e:
        raise RuntimeError("pyodbc is required for live SQL Server discovery") from e
    try:
        with pyodbc.connect(connection_string, timeout=20) as conn:
            cur=conn.cursor()
            objs=cur.execute(DISCOVERY_SQL).fetchall()
            cols=cur.execute(COLUMN_SQL).fetchall()
            deps=cur.execute(DEPENDENCY_SQL).fetchall()
            params=cur.execute(PARAMETER_SQL).fetchall()
            # Constraint/statistics discovery is best-effort so restricted source accounts
            # can still complete core discovery. Missing optional evidence lowers semantic
            # inference confidence rather than aborting the migration.
            try:
                key_constraints=cur.execute(KEY_CONSTRAINT_SQL).fetchall()
            except Exception:
                key_constraints=[]
            try:
                foreign_keys=cur.execute(FOREIGN_KEY_SQL).fetchall()
            except Exception:
                foreign_keys=[]
            try:
                table_stats=cur.execute(TABLE_STATS_SQL).fetchall()
            except Exception:
                table_stats=[]
            by={(r.schema_name,r.object_name):[] for r in objs}
            for c in cols:
                by.setdefault((c.schema_name,c.object_name),[]).append({
                    "name":c.column_name,"ordinal":c.column_id,
                    "type":(c.system_data_type if bool(c.is_user_defined) and c.system_data_type else c.declared_data_type),
                    "declared_type":c.declared_data_type,"system_type":c.system_data_type,"is_user_defined":bool(c.is_user_defined),
                    "max_length":c.max_length,"precision":c.precision,"scale":c.scale,
                    "nullable":bool(c.is_nullable),"identity":bool(c.is_identity),
                    "computed":bool(c.is_computed),"default":c.default_definition,
                    "collation":c.collation_name
                })
            dep_by: dict[tuple[str,str],list[dict[str,Any]]] = {}
            for d in deps:
                dep_by.setdefault((d.referencing_schema_name,d.referencing_entity_name),[]).append({
                    "server":d.referenced_server_name,
                    "database":d.referenced_database_name,
                    "schema":d.referenced_schema_name,
                    "object":d.referenced_entity_name,
                    "column":d.referenced_column_name,
                    "referenced_minor_id":d.referenced_minor_id,
                    "type":d.dependency_scope,
                    "is_schema_bound_reference":bool(d.is_schema_bound_reference),
                    "is_caller_dependent":bool(d.is_caller_dependent),
                    "is_ambiguous":bool(d.is_ambiguous),
                })
            par_by: dict[tuple[str,str],list[dict[str,Any]]] = {}
            for p in params:
                par_by.setdefault((p.schema_name,p.object_name),[]).append({
                    "name":p.parameter_name,"ordinal":p.parameter_id,"type":p.data_type,
                    "max_length":p.max_length,"precision":p.precision,"scale":p.scale,
                    "is_output":bool(p.is_output)
                })
            constraint_by: dict[tuple[str,str],list[dict[str,Any]]] = {}
            grouped_keys: dict[tuple[str,str,str],dict[str,Any]] = {}
            for k in key_constraints:
                key=(k.schema_name,k.object_name,k.constraint_name)
                row=grouped_keys.setdefault(key,{
                    "name":k.constraint_name,
                    "type":"PRIMARY_KEY" if str(k.constraint_type).upper().startswith("PRIMARY") else "UNIQUE",
                    "columns":[],
                })
                row["columns"].append(k.column_name)
            for (sch,obj,_),row in grouped_keys.items():
                constraint_by.setdefault((sch,obj),[]).append(row)
            grouped_fks: dict[tuple[str,str,str],dict[str,Any]] = {}
            for f in foreign_keys:
                key=(f.schema_name,f.object_name,f.constraint_name)
                row=grouped_fks.setdefault(key,{
                    "name":f.constraint_name,"type":"FOREIGN_KEY","columns":[],
                    "referenced_schema":f.referenced_schema,"referenced_object":f.referenced_object,
                    "referenced_columns":[],
                })
                row["columns"].append(f.column_name); row["referenced_columns"].append(f.referenced_column)
            for (sch,obj,_),row in grouped_fks.items():
                constraint_by.setdefault((sch,obj),[]).append(row)
            stats_by={(r.schema_name,r.object_name):int(r.approx_row_count or 0) for r in table_stats}
            return {
                "database": objs[0].database_name if objs else "",
                "objects":[{
                    "database":r.database_name,"schema":r.schema_name,"name":r.object_name,
                    "type":r.object_type,"definition":r.definition,
                    "columns":by.get((r.schema_name,r.object_name),[]),
                    "dependencies":dep_by.get((r.schema_name,r.object_name),[]),
                    "parameters":par_by.get((r.schema_name,r.object_name),[]),
                    "constraints":constraint_by.get((r.schema_name,r.object_name),[]),
                    "approx_row_count":stats_by.get((r.schema_name,r.object_name))
                } for r in objs]
            }
    except Exception as e:
        raise RuntimeError(connection_diagnostic(e)) from e
