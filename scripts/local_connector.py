"""Universal Local Connector Agent for Databricks Migration AI Studio.
Runs on the customer network. No inbound listener, open ports, or public IP needed.
Connects outward over HTTPS to Migration AI Studio.
Supports: SQL Server, MySQL, PostgreSQL, Oracle.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time as time_type
from decimal import Decimal
import getpass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import gzip
import http.server
import socket
import socketserver
import sys
import tempfile
import threading
import webbrowser
import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

# Explicit imports so PyInstaller bundles all drivers into migration-agent.exe
try:
    import pyodbc
except ImportError:
    pyodbc = None
try:
    import pymysql
    import pymysql.cursors
except ImportError:
    pymysql = None
try:
    import psycopg2
except ImportError:
    psycopg2 = None
try:
    import oracledb
except ImportError:
    oracledb = None

try:
    import cryptography
    import cryptography.hazmat.primitives.kdf.pbkdf2
    import cryptography.hazmat.primitives.ciphers
    import cryptography.hazmat.primitives.hashes
except ImportError:
    pass


def normalize_engine(value: str | None) -> str:
    aliases = {
        "POSTGRES": "POSTGRESQL",
        "PG": "POSTGRESQL",
        "MARIADB": "MYSQL",
        "MSSQL": "SQLSERVER",
        "SQL_SERVER": "SQLSERVER",
    }
    raw = str(value or "SQLSERVER").strip().upper()
    return aliases.get(raw, raw)


def quote_identifier(name: str, engine: str = "SQLSERVER") -> str:
    engine = normalize_engine(engine)
    clean = str(name).replace("\x00", "")
    if engine == "SQLSERVER":
        return "[" + clean.replace("]", "]]") + "]"
    if engine == "MYSQL":
        return "`" + clean.replace("`", "``") + "`"
    return '"' + clean.replace('"', '""') + '"'


def qualified_table(schema: str | None, table: str, engine: str = "SQLSERVER") -> str:
    t = quote_identifier(table, engine)
    if schema and str(schema).strip():
        return f"{quote_identifier(schema, engine)}.{t}"
    return t


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
    return str(value)


# ==============================================================================
# SQL SERVER DISCOVERY QUERIES
# ==============================================================================
SQLSERVER_DISCOVERY = r"""
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

SQLSERVER_COLUMNS = r"""
SELECT s.name schema_name,o.name object_name,c.name column_name,c.column_id,
       t.name declared_data_type, TYPE_NAME(c.system_type_id) system_data_type, t.is_user_defined,
       c.max_length,c.precision,c.scale,c.is_nullable,c.is_identity,c.is_computed,
       dc.definition default_definition, c.collation_name
FROM sys.objects o JOIN sys.schemas s ON o.schema_id=s.schema_id
JOIN sys.columns c ON c.object_id=o.object_id JOIN sys.types t ON c.user_type_id=t.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id=dc.object_id
WHERE o.is_ms_shipped=0 AND o.type IN ('U','V');
"""

SQLSERVER_KEYS = r"""
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

SQLSERVER_STATS = r"""
SELECT s.name AS schema_name,o.name AS object_name,
       SUM(CASE WHEN p.index_id IN (0,1) THEN p.row_count ELSE 0 END) AS approx_row_count
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id=o.schema_id
JOIN sys.dm_db_partition_stats p ON p.object_id=o.object_id
WHERE o.is_ms_shipped=0 AND o.type='U'
GROUP BY s.name,o.name;
"""


def connection_diagnostic(error: Exception, engine: str = "SQLSERVER") -> str:
    message = str(error).lower()
    if "access denied" in message or "28000" in message or "18456" in message or "password authentication failed" in message:
        return "AUTHENTICATION_FAILED: Verify database username and password in agent.env."
    if "unknown database" in message or "does not exist" in message or "4060" in message:
        return "DATABASE_NOT_FOUND: Verify database name in agent.env."
    if any(k in message for k in ("connection refused", "timeout", "hyt00", "08001", "not accessible", "network-related")):
        return f"NETWORK_UNREACHABLE: Could not reach {engine} server on specified host and port. Verify service is running."
    return f"{type(error).__name__}: {error}"


# ==============================================================================
# UNIVERSAL LOCAL AGENT CLASS
# ==============================================================================

# ==============================================================================
# EMBEDDED REAL-TIME WEB DASHBOARD & TELEMETRY
# ==============================================================================
AGENT_TELEMETRY = {
    "status": "ONLINE & STREAMING",
    "source_id": "-",
    "engine": "-",
    "database": "-",
    "server": "-",
    "studio_url": "-",
    "current_table": "Idle",
    "current_operation": "Awaiting batch requests...",
    "total_rows": 0,
    "speed": 0,
    "compression_ratio": "85%",
    "total_bytes_sent": 0,
    "total_compressed_bytes": 0,
    "last_calc_time": time.time(),
    "last_rows_count": 0,
    "logs": [],
}

def log_telemetry(op: str, status: str, details: str = ""):
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "op": op,
        "status": status,
        "details": details,
    }
    AGENT_TELEMETRY["logs"].append(entry)
    if len(AGENT_TELEMETRY["logs"]) > 60:
        AGENT_TELEMETRY["logs"].pop(0)

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Databricks Migration AI Studio - Agent Hub</title>
<style>
  :root {
    --bg-main: #0c1017;
    --bg-card: #151b26;
    --bg-hover: #1e2638;
    --accent-blue: #3b82f6;
    --accent-indigo: #6366f1;
    --accent-emerald: #10b981;
    --accent-amber: #f59e0b;
    --accent-rose: #f43f5e;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --border-color: #273142;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background-color: var(--bg-main);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.5;
    padding: 24px;
  }
  .container { max-width: 1200px; margin: 0 auto; }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 24px;
  }
  .brand { display: flex; align-items: center; gap: 14px; }
  .logo-icon {
    width: 44px;
    height: 44px;
    background: linear-gradient(135deg, #ff3621 0%, #ff5a36 100%);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 900;
    font-size: 20px;
    color: #fff;
    box-shadow: 0 4px 14px rgba(255, 54, 33, 0.4);
  }
  .brand-title { font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }
  .brand-subtitle { font-size: 13px; color: var(--text-secondary); }
  .status-pill {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 16px;
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.4);
    color: #34d399;
    border-radius: 9999px;
    font-weight: 600;
    font-size: 13px;
  }
  .pulse-dot {
    width: 8px;
    height: 8px;
    background: #10b981;
    border-radius: 50%;
    box-shadow: 0 0 10px #10b981;
    animation: pulse 1.5s infinite;
  }
  @keyframes pulse {
    0% { transform: scale(0.9); opacity: 0.8; }
    50% { transform: scale(1.3); opacity: 1; }
    100% { transform: scale(0.9); opacity: 0.8; }
  }
  .grid-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 14px;
    padding: 20px;
    position: relative;
    overflow: hidden;
  }
  .stat-label { font-size: 12px; color: var(--text-secondary); text-transform: uppercase; font-weight: 600; margin-bottom: 6px; }
  .stat-value { font-size: 26px; font-weight: 800; color: #fff; letter-spacing: -0.5px; }
  .stat-sub { font-size: 12px; color: #34d399; margin-top: 4px; display: flex; align-items: center; gap: 4px; }
  .active-card {
    border-color: #3b82f6;
    background: linear-gradient(180deg, rgba(59, 130, 246, 0.08) 0%, var(--bg-card) 100%);
  }
  .main-layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 24px;
  }
  @media(max-width: 900px) { .main-layout { grid-template-columns: 1fr; } }
  .panel-title { font-size: 15px; font-weight: 700; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; }
  .info-list { list-style: none; }
  .info-item {
    display: flex;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid var(--border-color);
    font-size: 13px;
  }
  .info-item:last-child { border-bottom: none; }
  .info-key { color: var(--text-secondary); }
  .info-val { font-weight: 600; font-family: monospace; color: #e2e8f0; }
  .console-box {
    background: #06090e;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 14px;
    font-family: Consolas, monospace;
    font-size: 12px;
    height: 280px;
    overflow-y: auto;
    color: #cbd5e1;
  }
  .log-line { margin-bottom: 6px; display: flex; gap: 8px; }
  .log-time { color: #64748b; }
  .log-op { color: #38bdf8; font-weight: 600; }
  .log-ok { color: #4ade80; font-weight: 600; }
  .progress-wrap {
    margin-top: 14px;
  }
  .progress-bar-bg {
    width: 100%;
    height: 8px;
    background: #1e293b;
    border-radius: 999px;
    overflow: hidden;
  }
  .progress-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #10b981);
    width: 0%;
    transition: width 0.3s ease;
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">
      <div class="logo-icon">DB</div>
      <div>
        <div class="brand-title">Databricks Migration AI Studio</div>
        <div class="brand-subtitle">Universal High-Speed Local Agent Hub</div>
      </div>
    </div>
    <div class="status-pill">
      <div class="pulse-dot"></div>
      <span id="agent-status">ONLINE & STREAMING</span>
    </div>
  </header>

  <div class="grid-stats">
    <div class="card active-card">
      <div class="stat-label">Active Migration Target</div>
      <div class="stat-value" id="current-table" style="font-size: 20px;">Idle</div>
      <div class="stat-sub" id="current-op">Awaiting batch requests...</div>
    </div>
    <div class="card">
      <div class="stat-label">Total Rows Migrated</div>
      <div class="stat-value" id="total-rows">0</div>
      <div class="stat-sub">Streaming in real-time</div>
    </div>
    <div class="card">
      <div class="stat-label">Instantaneous Speed</div>
      <div class="stat-value" id="transfer-speed">0 rows/s</div>
      <div class="stat-sub" id="compression-savings">Gzip Acceleration: Active</div>
    </div>
    <div class="card">
      <div class="stat-label">Bandwidth Efficiency</div>
      <div class="stat-value" id="bandwidth-saved">85%</div>
      <div class="stat-sub">In-Flight Compression</div>
    </div>
  </div>

  <div class="main-layout">
    <div class="card">
      <div class="panel-title">
        <span>Connection Profile</span>
        <span style="font-size: 11px; color: #38bdf8; font-weight: normal;">TLS 1.3 Outbound</span>
      </div>
      <ul class="info-list">
        <li class="info-item"><span class="info-key">Source Profile:</span><span class="info-val" id="source-id">-</span></li>
        <li class="info-item"><span class="info-key">Database Engine:</span><span class="info-val" id="db-engine">-</span></li>
        <li class="info-item"><span class="info-key">Local Database:</span><span class="info-val" id="db-name">-</span></li>
        <li class="info-item"><span class="info-key">Server Host:</span><span class="info-val" id="db-server">-</span></li>
        <li class="info-item"><span class="info-key">Target Studio URL:</span><span class="info-val" id="studio-url" style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">-</span></li>
      </ul>
      <div class="progress-wrap">
        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;">
          <span style="color: var(--text-secondary);">Batch Throughput</span>
          <span id="batch-progress" style="font-weight: 600; color: #38bdf8;">Optimal</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar-fill" id="progress-fill" style="width: 100%;"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="panel-title">
        <span>Real-Time Operation Feed</span>
        <span style="font-size: 11px; color: #94a3b8; font-weight: normal;">Auto-refreshing</span>
      </div>
      <div class="console-box" id="log-box">
        <div class="log-line"><span class="log-time">[Init]</span> <span class="log-op">Universal Agent initialized successfully</span></div>
      </div>
    </div>
  </div>
</div>

<script>
async function updateHUD() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();
    
    document.getElementById('current-table').textContent = data.current_table || 'Idle';
    document.getElementById('current-op').textContent = data.current_operation || 'Ready for tasks';
    document.getElementById('total-rows').textContent = Number(data.total_rows || 0).toLocaleString();
    document.getElementById('transfer-speed').textContent = `${Number(data.speed || 0).toLocaleString()} rows/s`;
    document.getElementById('source-id').textContent = data.source_id || '-';
    document.getElementById('db-engine').textContent = data.engine || '-';
    document.getElementById('db-name').textContent = data.database || '-';
    document.getElementById('db-server').textContent = data.server || '-';
    document.getElementById('studio-url').textContent = data.studio_url || '-';
    document.getElementById('bandwidth-saved').textContent = data.compression_ratio || '85%';

    if (data.logs && data.logs.length) {
      const box = document.getElementById('log-box');
      box.innerHTML = data.logs.map(l => 
        `<div class="log-line"><span class="log-time">[${l.time}]</span> <span class="log-op">${l.op}:</span> <span class="${l.status === 'completed' ? 'log-ok' : 'log-time'}">${l.status}</span> ${l.details || ''}</div>`
      ).join('');
      box.scrollTop = box.scrollHeight;
    }
  } catch(e) {}
}
setInterval(updateHUD, 1000);
updateHUD();
</script>
</body>
</html>
"""

class AgentDashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(AGENT_TELEMETRY).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def start_dashboard_server(start_port=8585):
    for p in range(start_port, start_port + 20):
        try:
            server = socketserver.TCPServer(("127.0.0.1", p), AgentDashboardHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            return p
        except OSError:
            continue
    return None

class UniversalLocalAgent:
    def __init__(
        self,
        source_id: str,
        engine: str,
        server: str,
        port: int | None,
        database: str,
        schema: str | None = None,
        username: str | None = None,
        password: str | None = None,
        connection_string: str | None = None,
        driver: str | None = None,
        trust_cert: bool = True,
    ):
        self.source_id = source_id
        self.engine = normalize_engine(engine)
        self.server = server
        self.port = port or {"SQLSERVER": 1433, "MYSQL": 3306, "POSTGRESQL": 5432, "ORACLE": 1521}.get(self.engine, 3306)
        self.database = database
        self.schema = schema or ("public" if self.engine == "POSTGRESQL" else database if self.engine == "MYSQL" else "")
        self.username = username
        self.password = password
        self.connection_string = connection_string
        self.driver = driver or "ODBC Driver 18 for SQL Server"
        self.trust_cert = trust_cert
        self.streams: dict[str, list[Any]] = {}

    def connect(self):
        eng = self.engine
        if eng == "SQLSERVER":
            try:
                import pyodbc
            except ImportError:
                raise RuntimeError("pyodbc module missing. Install with: pip install pyodbc")
            return self._connect_sqlserver(pyodbc)

        if eng == "MYSQL":
            try:
                import pymysql
                import pymysql.cursors
            except ImportError:
                raise RuntimeError("pymysql module missing. Install with: pip install pymysql")
            return pymysql.connect(
                host=self.server,
                port=int(self.port or 3306),
                user=self.username or "root",
                password=self.password or "",
                database=self.database,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.Cursor,
                connect_timeout=10,
                autocommit=True,
            )

        if eng == "POSTGRESQL":
            try:
                import psycopg2
            except ImportError:
                raise RuntimeError("psycopg2 module missing. Install with: pip install psycopg2-binary")
            return psycopg2.connect(
                host=self.server,
                port=int(self.port or 5432),
                user=self.username or "postgres",
                password=self.password or "",
                dbname=self.database,
                connect_timeout=10,
            )

        if eng == "ORACLE":
            try:
                import oracledb
            except ImportError:
                raise RuntimeError("oracledb module missing. Install with: pip install oracledb")
            candidates = [self.database] if self.database else []
            for default_candidate in ["freepdb1", "FREE", "orclpdb", "XEPDB1", "ORCL", "XE"]:
                if default_candidate.lower() not in [c.lower() for c in candidates]:
                    candidates.append(default_candidate)
            last_err = None
            for cand in candidates:
                if not cand:
                    continue
                try:
                    dsn = oracledb.makedsn(self.server, int(self.port or 1521), service_name=cand)
                    conn = oracledb.connect(user=self.username, password=self.password or "", dsn=dsn)
                    if cand != self.database:
                        print(f"[Oracle] Service '{self.database}' not registered with listener; auto-connected via '{cand}'.")
                        self.database = cand
                    return conn
                except Exception as e:
                    last_err = e
                    try:
                        dsn = oracledb.makedsn(self.server, int(self.port or 1521), sid=cand)
                        conn = oracledb.connect(user=self.username, password=self.password or "", dsn=dsn)
                        if cand != self.database:
                            print(f"[Oracle] SID '{self.database}' not registered with listener; auto-connected via SID '{cand}'.")
                            self.database = cand
                        return conn
                    except Exception as e_sid:
                        last_err = e_sid
                        continue
            raise last_err

        raise ValueError(f"Unsupported database engine: {eng}")

    def _connect_sqlserver(self, pyodbc):
        cs = self.connection_string
        if not cs:
            credentials = "Trusted_Connection=yes;"
            if self.username:
                credentials = f"UID={odbc_value(self.username)};PWD={odbc_value(self.password or '')};"
            clean_driver = self.driver.strip("\"'{}")
            port_str = f",{self.port}" if self.port and "\\" not in self.server else ""
            cs = (f"DRIVER={odbc_value(clean_driver)};SERVER={odbc_value(self.server + port_str)};"
                  f"DATABASE={odbc_value(self.database)};{credentials}Encrypt=yes;"
                  f"TrustServerCertificate={'yes' if self.trust_cert else 'no'};")
            self.connection_string = cs

        try:
            conn = pyodbc.connect(cs, timeout=10, autocommit=True)
            conn.timeout = 60
            return conn
        except pyodbc.Error as exc:
            err_str = str(exc)
            if "IM002" in err_str:
                installed = [d for d in pyodbc.drivers() if "SQL Server" in d]
                for alt in ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"]:
                    if alt in installed and alt not in cs:
                        alt_cs = re.sub(r"DRIVER=\{[^}]+\}", lambda _, a=alt: f"DRIVER={{{a}}}", cs)
                        try:
                            conn = pyodbc.connect(alt_cs, timeout=10, autocommit=True)
                            conn.timeout = 60
                            self.connection_string = alt_cs
                            return conn
                        except Exception:
                            continue
            if any(k in err_str for k in ("08001", "HYT00", "network-related", "not accessible", "server is not found")):
                if self.server.lower() in ("localhost", "127.0.0.1", ".", "localhost:1433"):
                    for candidate in [r"localhost\SQLEXPRESS", r".\SQLEXPRESS"]:
                        alt_cs = re.sub(r"SERVER=\{?[^;}]+\}?", lambda _, c=candidate: f"SERVER={{{c}}}", cs)
                        try:
                            conn = pyodbc.connect(alt_cs, timeout=10, autocommit=True)
                            conn.timeout = 60
                            self.connection_string = alt_cs
                            self.server = candidate
                            return conn
                        except Exception:
                            continue
            raise

    def cleanup(self, all_streams: bool = False):
        timeout = int(os.environ.get("CONNECTOR_STREAM_TIMEOUT_SECONDS", "3600"))
        for key, item in list(self.streams.items()):
            if all_streams or time.monotonic() - item[2] > timeout:
                try:
                    item[0].close()
                finally:
                    self.streams.pop(key, None)

    def handle(self, task: dict[str, Any]) -> dict[str, Any]:
        op = task["operation"]
        data = task.get("payload", {})
        self.cleanup()

        # Dynamically adapt to target engine and port if specified in task from Studio
        if task.get("engine"):
            task_engine = normalize_engine(task["engine"])
            if task_engine != self.engine:
                self.engine = task_engine
                if not self.port or self.port in {1433, 3306, 5432, 1521}:
                    self.port = int(task.get("port") or {"SQLSERVER": 1433, "MYSQL": 3306, "POSTGRESQL": 5432, "ORACLE": 1521}.get(self.engine, 5432))
        if task.get("schema") and not self.schema:
            self.schema = task["schema"]

        # Operation 1: TEST CONNECTION
        if op == "test":
            conn = self.connect()
            try:
                if self.engine == "SQLSERVER":
                    cur = conn.cursor()
                    cur.execute("SELECT DB_NAME(), SUSER_SNAME(), @@VERSION")
                    row = cur.fetchone()
                    return {"ok": True, "engine": "SQLSERVER", "database": row[0], "user": row[1], "product_version": row[2]}
                elif self.engine == "MYSQL":
                    cur = conn.cursor()
                    cur.execute("SELECT DATABASE(), CURRENT_USER(), VERSION()")
                    row = cur.fetchone()
                    return {"ok": True, "engine": "MYSQL", "database": row[0], "user": row[1], "product_version": row[2]}
                elif self.engine == "POSTGRESQL":
                    cur = conn.cursor()
                    cur.execute("SELECT current_database(), current_user, version()")
                    row = cur.fetchone()
                    return {"ok": True, "engine": "POSTGRESQL", "database": row[0], "user": row[1], "product_version": row[2]}
                elif self.engine == "ORACLE":
                    cur = conn.cursor()
                    cur.execute("SELECT SYS_CONTEXT('USERENV','DB_NAME'), USER FROM dual")
                    row = cur.fetchone()
                    return {"ok": True, "engine": "ORACLE", "database": row[0], "user": row[1], "product_version": "Oracle"}
            finally:
                conn.close()

        # Operation 2: DISCOVER CATALOG
        if op == "discover":
            return self.discover_catalog()

        # Operation 3: COUNT ROWS
        if op == "count":
            schema = data.get("schema") or self.schema
            table = data.get("table")
            table_sql = qualified_table(schema, table, self.engine)
            conn = self.connect()
            try:
                cur = conn.cursor()
                count_sql = f"SELECT COUNT(*) FROM {table_sql}"
                cur.execute(count_sql)
                row = cur.fetchone()
                return {"count": int(row[0]) if row else 0}
            finally:
                conn.close()

        # Operation 4: OPEN STREAM
        if op == "open":
            schema = data.get("schema") or self.schema
            table = data.get("table")
            table_key = f"{schema}.{table}"
            # Smart eviction of old stream on same table
            for existing_id, existing_item in list(self.streams.items()):
                if len(existing_item) > 4 and existing_item[4] == table_key:
                    try:
                        existing_item[0].close()
                    finally:
                        self.streams.pop(existing_id, None)

            if len(self.streams) >= 32:
                raise ValueError("Connector stream capacity reached")

            conn = self.connect()
            try:
                cur = conn.cursor()
                requested = data.get("columns") or ["*"]
                proj = ",".join(quote_identifier(c, self.engine) for c in requested) if requested != ["*"] else "*"
                limit = data.get("max_rows")
                table_sql = qualified_table(schema, table, self.engine)

                if self.engine == "SQLSERVER":
                    top = f"TOP ({int(limit)}) " if limit else ""
                    sql = f"SELECT {top}{proj} FROM {table_sql}"
                elif self.engine in {"MYSQL", "POSTGRESQL"}:
                    lim = f" LIMIT {int(limit)}" if limit else ""
                    sql = f"SELECT {proj} FROM {table_sql}{lim}"
                elif self.engine == "ORACLE":
                    lim = f" FETCH FIRST {int(limit)} ROWS ONLY" if limit else ""
                    sql = f"SELECT {proj} FROM {table_sql}{lim}"
                else:
                    sql = f"SELECT {proj} FROM {table_sql}"

                cur.execute(sql)
                stream_id = secrets.token_hex(24)
                self.streams[stream_id] = [conn, cur, time.monotonic(), None, table_key]
                conn = None  # Handed off to streams
                return {"stream_id": stream_id}
            finally:
                if conn is not None:
                    conn.close()

        # Operation 5: FETCH BATCH
        if op == "fetch":
            stream = self.streams.get(data.get("stream_id"))
            if not stream:
                raise ValueError("Source stream expired; restart operation")
            stream[2] = time.monotonic()
            size = min(max(int(data.get("size", 20000)), 1), 20000)
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

        # Operation 6: DIRECT STAGE AND UPLOAD TO DATABRICKS VOLUME
        if op == "stage_and_upload":
            import pyarrow as pa
            import pyarrow.parquet as pq
            from urllib.parse import quote
            import httpx

            schema = data.get("source_schema") or self.schema
            table = data.get("table")
            columns = data.get("columns") or ["*"]
            max_rows = data.get("max_rows")
            target_volume_file = data.get("target_volume_file")
            databricks_host = data.get("databricks_host")
            databricks_token = data.get("databricks_token")

            if not (target_volume_file and databricks_host and databricks_token):
                raise ValueError("Missing direct staging parameters: target_volume_file, databricks_host, or databricks_token")

            table_sql = qualified_table(schema, table, self.engine)
            proj = ",".join(quote_identifier(c, self.engine) for c in columns) if columns != ["*"] else "*"

            if self.engine == "SQLSERVER":
                top = f"TOP ({int(max_rows)}) " if max_rows else ""
                sql = f"SELECT {top}{proj} FROM {table_sql}"
            elif self.engine in {"MYSQL", "POSTGRESQL"}:
                lim = f" LIMIT {int(max_rows)}" if max_rows else ""
                sql = f"SELECT {proj} FROM {table_sql}{lim}"
            elif self.engine == "ORACLE":
                lim = f" FETCH FIRST {int(max_rows)} ROWS ONLY" if max_rows else ""
                sql = f"SELECT {proj} FROM {table_sql}{lim}"
            else:
                sql = f"SELECT {proj} FROM {table_sql}"

            handle = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
            local_parquet_path = handle.name
            handle.close()

            count = 0
            file_size = 0
            conn = self.connect()
            try:
                cur = conn.cursor()
                cur.execute(sql)
                col_names = [desc[0] for desc in cur.description]
                arrow_schema = pa.schema([(c, pa.string()) for c in col_names])

                with pq.ParquetWriter(local_parquet_path, arrow_schema, compression="snappy") as writer:
                    while True:
                        rows = cur.fetchmany(50000)
                        if not rows:
                            break
                        data_dict = {
                            col_names[idx]: [None if r[idx] is None else str(r[idx]) for r in rows]
                            for idx in range(len(col_names))
                        }
                        writer.write_table(pa.Table.from_pydict(data_dict, schema=arrow_schema))
                        count += len(rows)

                file_size = os.path.getsize(local_parquet_path)
                upload_url = f"https://{databricks_host}/api/2.0/fs/files{quote(target_volume_file, safe='/')}"
                headers = {
                    "Authorization": f"Bearer {databricks_token}",
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(file_size),
                }

                with httpx.Client(timeout=httpx.Timeout(900, connect=30), follow_redirects=False) as upload_client:
                    with open(local_parquet_path, "rb") as f_stream:
                        resp = upload_client.put(upload_url, headers=headers, content=f_stream)
                    if resp.status_code >= 300:
                        raise RuntimeError(f"Databricks Volume upload failed (HTTP {resp.status_code}): {resp.text}")

                return {
                    "ok": True,
                    "row_count": count,
                    "volume_path": target_volume_file,
                    "file_size_bytes": file_size,
                    "manifest": {
                        "table": table,
                        "row_count": count,
                        "volume_path": target_volume_file,
                        "file_size": file_size,
                    }
                }
            finally:
                conn.close()
                if os.path.exists(local_parquet_path):
                    try:
                        os.unlink(local_parquet_path)
                    except OSError:
                        pass

        # Operation 7: CLOSE STREAM
        if op == "close":
            item = self.streams.pop(data.get("stream_id"), None)
            if item:
                item[0].close()
            return {"closed": True}

        raise ValueError(f"Unsupported connector operation: {op}")

    def discover_catalog(self) -> dict[str, Any]:
        eng = self.engine
        conn = self.connect()
        try:
            cur = conn.cursor()
            if eng == "SQLSERVER":
                cur.execute(SQLSERVER_DISCOVERY)
                objs = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]
                cur.execute(SQLSERVER_COLUMNS)
                cols = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]
                cur.execute(SQLSERVER_KEYS)
                keys = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]
                cur.execute(SQLSERVER_STATS)
                stats = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]
                return self._build_canonical(self.database, objs, cols, keys, stats)

            elif eng == "MYSQL":
                cur.execute(
                    """SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name,
                       CASE TABLE_TYPE WHEN 'BASE TABLE' THEN 'TABLE' ELSE 'VIEW' END AS object_type
                       FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME""",
                    (self.database,),
                )
                objs = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]

                cur.execute(
                    """SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name, COLUMN_NAME AS column_name,
                       ORDINAL_POSITION AS ordinal, DATA_TYPE AS data_type, CHARACTER_MAXIMUM_LENGTH AS max_length,
                       NUMERIC_PRECISION AS `precision`, NUMERIC_SCALE AS `scale`, IS_NULLABLE AS is_nullable,
                       COLUMN_DEFAULT AS column_default, COLUMN_KEY AS column_key, EXTRA AS extra
                       FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME, ORDINAL_POSITION""",
                    (self.database,),
                )
                cols = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]

                cur.execute(
                    """SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name, CONSTRAINT_NAME AS constraint_name,
                       'PRIMARY KEY' AS constraint_type, COLUMN_NAME AS column_name, ORDINAL_POSITION AS ordinal
                       FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND CONSTRAINT_NAME='PRIMARY'""",
                    (self.database,),
                )
                keys = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]
                return self._build_canonical(self.database, objs, cols, keys, [])

            elif eng == "POSTGRESQL":
                schema = self.schema or "public"
                cur.execute(
                    """SELECT table_schema AS schema_name, table_name AS object_name,
                       CASE table_type WHEN 'BASE TABLE' THEN 'TABLE' ELSE 'VIEW' END AS object_type
                       FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name""",
                    (schema,),
                )
                objs = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]

                cur.execute(
                    """SELECT table_schema AS schema_name, table_name AS object_name, column_name,
                       ordinal_position AS ordinal, data_type, character_maximum_length AS max_length,
                       numeric_precision AS "precision", numeric_scale AS "scale", is_nullable, column_default
                       FROM information_schema.columns WHERE table_schema=%s ORDER BY table_name, ordinal_position""",
                    (schema,),
                )
                cols = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]

                cur.execute(
                    """SELECT tc.table_schema AS schema_name, tc.table_name AS object_name, tc.constraint_name AS constraint_name,
                       tc.constraint_type AS constraint_type, kcu.column_name AS column_name, kcu.ordinal_position AS ordinal
                       FROM information_schema.table_constraints tc
                       JOIN information_schema.key_column_usage kcu
                         ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
                       WHERE tc.table_schema=%s AND tc.constraint_type IN ('PRIMARY KEY','UNIQUE')""",
                    (schema,),
                )
                keys = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]
                return self._build_canonical(self.database, objs, cols, keys, [])

            elif eng == "ORACLE":
                schema = (self.schema or self.username or "").upper()
                cur.execute(
                    """SELECT OWNER AS schema_name, TABLE_NAME AS object_name, 'TABLE' AS object_type
                       FROM ALL_TABLES WHERE OWNER=:schema
                       UNION ALL
                       SELECT OWNER, VIEW_NAME, 'VIEW' FROM ALL_VIEWS WHERE OWNER=:schema ORDER BY 2""",
                    {"schema": schema},
                )
                objs = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]

                cur.execute(
                    """SELECT OWNER AS schema_name, TABLE_NAME AS object_name, COLUMN_NAME AS column_name,
                       COLUMN_ID AS ordinal, DATA_TYPE AS data_type, DATA_LENGTH AS max_length,
                       DATA_PRECISION AS "precision", DATA_SCALE AS "scale", NULLABLE AS is_nullable,
                       DATA_DEFAULT AS column_default
                       FROM ALL_TAB_COLUMNS WHERE OWNER=:schema ORDER BY TABLE_NAME, COLUMN_ID""",
                    {"schema": schema},
                )
                cols = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]

                cur.execute(
                    """SELECT c.OWNER AS schema_name, c.TABLE_NAME AS object_name, c.CONSTRAINT_NAME AS constraint_name,
                       CASE c.CONSTRAINT_TYPE WHEN 'P' THEN 'PRIMARY KEY' ELSE 'UNIQUE' END AS constraint_type,
                       cc.COLUMN_NAME AS column_name, cc.POSITION AS ordinal
                       FROM ALL_CONSTRAINTS c
                       JOIN ALL_CONS_COLUMNS cc ON c.OWNER=cc.OWNER AND c.CONSTRAINT_NAME=cc.CONSTRAINT_NAME
                       WHERE c.OWNER=:schema AND c.CONSTRAINT_TYPE IN ('P','U')""",
                    {"schema": schema},
                )
                keys = [dict(zip([d[0].lower() for d in cur.description], r)) for r in cur.fetchall()]
                return self._build_canonical(self.database, objs, cols, keys, [])

        finally:
            conn.close()

    def _build_canonical(self, database: str, objs: list[dict], cols: list[dict], keys: list[dict], stats: list[dict]) -> dict[str, Any]:
        by_object: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for column in cols:
            key = (str(column["schema_name"]), str(column["object_name"]))
            data_type = str(column.get("data_type") or column.get("declared_data_type") or "").lower()
            if self.engine in {"POSTGRESQL", "MYSQL", "ORACLE"} and data_type.startswith("timestamp"):
                data_type = "datetime"
            default = column.get("column_default") or column.get("default_definition")
            extra_val = str(column.get("extra") or "").lower()
            is_ident = bool(column.get("is_identity")) or "auto_increment" in extra_val or "nextval" in str(default or "").lower()
            by_object.setdefault(key, []).append({
                "name": str(column["column_name"]),
                "ordinal": int(column.get("ordinal") or column.get("column_id") or 0),
                "type": data_type,
                "declared_type": data_type,
                "system_type": data_type,
                "max_length": column.get("max_length"),
                "precision": column.get("precision"),
                "scale": column.get("scale"),
                "nullable": str(column.get("is_nullable", "YES")).upper() in {"YES", "Y", "TRUE", "1"},
                "identity": is_ident,
                "computed": bool(column.get("is_computed")),
                "default": None if default is None else str(default),
            })

        grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        for item in keys:
            k = (str(item["schema_name"]), str(item["object_name"]))
            name = str(item["constraint_name"])
            target = grouped.setdefault(k, {}).setdefault(name, {
                "name": name,
                "type": "PRIMARY_KEY" if str(item.get("constraint_type", "")).upper().startswith("P") else "UNIQUE",
                "columns": [],
            })
            target["columns"].append(str(item["column_name"]))

        stats_by = {(r["schema_name"], r["object_name"]): int(r.get("approx_row_count") or 0) for r in stats}

        return {
            "database": database,
            "objects": [{
                "database": database,
                "schema": str(obj["schema_name"]),
                "name": str(obj["object_name"]),
                "type": str(obj["object_type"]).upper(),
                "definition": obj.get("definition") or "",
                "columns": by_object.get((str(obj["schema_name"]), str(obj["object_name"])), []),
                "dependencies": [],
                "parameters": [],
                "constraints": list(grouped.get((str(obj["schema_name"]), str(obj["object_name"])), {}).values()),
                "approx_row_count": stats_by.get((str(obj["schema_name"]), str(obj["object_name"]))),
            } for obj in objs]
        }


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

    dirs = [Path.cwd()]
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    if base_dir not in dirs:
        dirs.append(base_dir)

    for d in dirs:
        all_env = list(d.glob("agent*.env")) + list(d.glob("connector*.env")) + list(d.glob(".env*"))
        existing_env = [f for f in all_env if f.is_file() and f.stat().st_size > 0]
        if existing_env:
            existing_env.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return existing_env[0]

    return None


def fetch_studio_profile(url: str, token: str) -> dict:
    if not (url and token):
        return {}
    try:
        import httpx
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.get(
                f"{url.rstrip('/')}/api/connector/info",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {}


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Migration AI Studio URL (e.g. https://databricks-migration-factory-9ym2.onrender.com)")
    parser.add_argument("--source", help="Migration source profile ID (e.g. SRC_xxxx)")
    parser.add_argument("--engine", default=None, help="Source database engine: SQLSERVER, MYSQL, POSTGRESQL, ORACLE")
    parser.add_argument("--server", help="Local database host/server (e.g. localhost, 127.0.0.1, or localhost\\SQLEXPRESS)")
    parser.add_argument("--port", type=int, help="Database port (e.g. 3306, 5432, 1433, 1521)")
    parser.add_argument("--database", help="Target source database name")
    parser.add_argument("--schema", help="Source schema name (e.g. public)")
    parser.add_argument("--driver", default=None, help="ODBC Driver for SQL Server (default: ODBC Driver 18 for SQL Server)")
    parser.add_argument("--username", help="Database login username")
    parser.add_argument("--password", help="Database login password")
    parser.add_argument("--trust-server-certificate", dest="trust_cert", action="store_true", default=None, help="Trust SQL Server certificate")
    parser.add_argument("--no-trust-server-certificate", dest="trust_cert", action="store_false", help="Do not trust SQL Server certificate")
    parser.add_argument("--token", help="Connector registration token")
    parser.add_argument("--config", help="Path to custom agent.env file")
    args = parser.parse_args()

    is_interactive = sys.stdin.isatty()
    need_save = False

    config_path = find_config_path(args.config)
    file_cfg = load_config_file(config_path)

    url = args.url or os.environ.get("CONNECTOR_URL") or file_cfg.get("CONNECTOR_URL")
    if not url:
        if is_interactive:
            url = input("Migration Studio Application URL (e.g. https://...): ").strip()
            need_save = True
        else:
            raise SystemExit("Error: --url or CONNECTOR_URL is required.")

    source = (
        args.source
        or os.environ.get("CONNECTOR_SOURCE")
        or os.environ.get("CONNECTOR_SOURCE_ID")
        or file_cfg.get("CONNECTOR_SOURCE")
        or file_cfg.get("CONNECTOR_SOURCE_ID")
    )
    if not source:
        if is_interactive:
            source = input("Source Profile ID (from Studio UI, e.g. SRC_xxxx): ").strip()
            need_save = True
        else:
            raise SystemExit("Error: --source or CONNECTOR_SOURCE is required.")

    token = args.token or os.environ.get("CONNECTOR_TOKEN") or file_cfg.get("CONNECTOR_TOKEN")
    if not token:
        if is_interactive:
            token = getpass.getpass("Connector registration token (from Studio UI): ").strip()
            need_save = True
        else:
            raise SystemExit("Error: Registration token is required via --token or CONNECTOR_TOKEN.")

    # 1. Fetch official source profile configuration from Migration AI Studio
    studio_info = fetch_studio_profile(url, token)
    studio_engine = studio_info.get("engine")
    studio_db = studio_info.get("database_name")
    studio_server = studio_info.get("server_name")
    studio_port = studio_info.get("port")
    studio_schema = studio_info.get("schema_name")

    # 2. Check if local configuration file belongs to a different source
    env_source = file_cfg.get("CONNECTOR_SOURCE") or file_cfg.get("CONNECTOR_SOURCE_ID")
    source_mismatch = bool(env_source and env_source != source)
    if source_mismatch:
        print(f"\n[Notice] Local configuration ({config_path.name if config_path else 'agent.env'}) belongs to source '{env_source}'.")
        print(f"         Syncing official configuration from Studio for active source '{source}'.\n")

    # 3. Resolve engine accurately
    engine_val = args.engine or studio_engine
    if not engine_val and not source_mismatch:
        engine_val = os.environ.get("CONNECTOR_ENGINE") or file_cfg.get("CONNECTOR_ENGINE")

    if not engine_val:
        if is_interactive:
            engine_prompt = input("Database Engine [SQLSERVER / MYSQL / POSTGRESQL / ORACLE] (default: SQLSERVER): ").strip()
            engine_val = engine_prompt if engine_prompt else "SQLSERVER"
            need_save = True
        else:
            engine_val = "SQLSERVER"
    engine = normalize_engine(engine_val)

    # 4. Resolve server
    server = (
        args.server
        or studio_server
        or (None if source_mismatch else (os.environ.get("CONNECTOR_SERVER") or file_cfg.get("CONNECTOR_SERVER")))
        or "localhost"
    )
    if engine == "SQLSERVER":
        server = server.replace("/", "\\")

    # 5. Default ports by engine
    default_ports = {"SQLSERVER": 1433, "MYSQL": 3306, "POSTGRESQL": 5432, "ORACLE": 1521}

    # 6. Resolve port
    port_val = (
        args.port
        or studio_port
        or (None if source_mismatch else (os.environ.get("CONNECTOR_PORT") or file_cfg.get("CONNECTOR_PORT")))
        or default_ports.get(engine, 1433)
    )
    port = int(port_val) if port_val and str(port_val).isdigit() else default_ports.get(engine, 1433)

    # 7. Resolve database
    database = (
        args.database
        or (None if source_mismatch else (os.environ.get("CONNECTOR_DATABASE") or file_cfg.get("CONNECTOR_DATABASE")))
        or studio_db
    )
    if not database:
        if is_interactive:
            database = input(f"Target {engine} Database name: ").strip()
            need_save = True
        else:
            raise SystemExit(f"Error: Target database name is required for {engine}.")

    # 8. Resolve schema
    schema = (
        args.schema
        or (None if source_mismatch else (os.environ.get("CONNECTOR_SCHEMA") or file_cfg.get("CONNECTOR_SCHEMA")))
        or studio_schema
    )
    if not schema and engine == "POSTGRESQL":
        schema = "public"

    # 9. Resolve driver & cert
    driver = args.driver or os.environ.get("CONNECTOR_DRIVER") or file_cfg.get("CONNECTOR_DRIVER") or "ODBC Driver 18 for SQL Server"
    if args.trust_cert is not None:
        trust_cert = args.trust_cert
    elif "CONNECTOR_TRUST_CERT" in os.environ:
        trust_cert = os.environ.get("CONNECTOR_TRUST_CERT", "").lower() in ("1", "true", "yes")
    elif "CONNECTOR_TRUST_CERT" in file_cfg:
        trust_cert = file_cfg.get("CONNECTOR_TRUST_CERT", "").lower() in ("1", "true", "yes")
    else:
        trust_cert = True

    # 10. Resolve username
    username = args.username
    if not username and not source_mismatch:
        username = os.environ.get("CONNECTOR_USERNAME") or file_cfg.get("CONNECTOR_USERNAME")
    if not username:
        if engine == "MYSQL":
            username = "root"
        elif engine == "POSTGRESQL":
            username = "postgres"

    # 11. Resolve password
    password = args.password
    if not password and not source_mismatch:
        password = os.environ.get("CONNECTOR_PASSWORD") or os.environ.get("CONNECTOR_SQL_PASSWORD") or file_cfg.get("CONNECTOR_PASSWORD")

    # Prompt for password if in interactive mode and none was provided
    if password is None and is_interactive and engine in ("MYSQL", "POSTGRESQL", "ORACLE"):
        pwd_input = getpass.getpass(f"Database password for user '{username}' (leave blank if none): ")
        password = pwd_input if pwd_input else ""
        need_save = True

    if need_save and is_interactive and not config_path:
        save_choice = input(f"\nSave these settings to 'agent.env' for source {source} ({engine})? [Y/n]: ").strip().lower()
        if save_choice in ("", "y", "yes"):
            save_target = Path.cwd() / "agent.env"
            try:
                with open(save_target, "w", encoding="utf-8") as f:
                    f.write("# Databricks Migration AI Studio - Saved Agent Configuration\n")
                    f.write(f"CONNECTOR_URL={url}\n")
                    f.write(f"CONNECTOR_SOURCE={source}\n")
                    f.write(f"CONNECTOR_ENGINE={engine}\n")
                    f.write(f"CONNECTOR_SERVER={server}\n")
                    if port:
                        f.write(f"CONNECTOR_PORT={port}\n")
                    f.write(f"CONNECTOR_DATABASE={database}\n")
                    if schema:
                        f.write(f"CONNECTOR_SCHEMA={schema}\n")
                    f.write(f"CONNECTOR_TOKEN={token}\n")
                    if username:
                        f.write(f"CONNECTOR_USERNAME={username}\n")
                    if password:
                        f.write(f"CONNECTOR_PASSWORD={password}\n")
                    if engine == "SQLSERVER":
                        f.write(f"CONNECTOR_DRIVER={driver}\n")
                        f.write(f"CONNECTOR_TRUST_CERT={'true' if trust_cert else 'false'}\n")
                print(f"[OK] Configuration saved to {save_target.name}")
            except Exception as e:
                print(f"[Notice] Could not save agent.env: {e}")

    base = validate_url(url)

    agent = UniversalLocalAgent(
        source_id=source,
        engine=engine,
        server=server,
        port=port,
        database=database,
        schema=schema,
        username=username,
        password=password,
        driver=driver,
        trust_cert=trust_cert,
    )

    try:
        import httpx
    except ImportError:
        raise SystemExit("httpx module missing. Install with: pip install httpx")

    stopped = threading.Event()
    instance_id = hashlib.sha256(f"{source}_{socket.gethostname()}_{platform.node()}_{os.getpid()}".encode()).hexdigest()[:32]

    # Single-instance mutex lock per source to prevent duplicate agents conflicting on same machine
    lock_file = None
    try:
        lock_path = Path(tempfile.gettempdir()) / f"migration_agent_{re.sub(r'[^A-Za-z0-9_]', '_', source)}.lock"
        if os.name == "nt":
            import msvcrt
            lock_file = open(lock_path, "w")
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            lock_file = open(lock_path, "w")
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        print("\n" + "!" * 68)
        print(" [WARNING] Another migration-agent process is ALREADY RUNNING for this source!")
        print(" Only ONE agent instance is permitted per source profile to avoid conflicts.")
        print(" Please close any other open migration-agent windows before continuing.")
        print("!" * 68 + "\n")
        if getattr(sys, "frozen", False):
            input("Press Enter to exit...")
        sys.exit(1)

    print("\n" + "=" * 68)
    print("      Databricks Migration AI Studio - Universal Agent Online")
    print("=" * 68)
    print(f"  Target Studio:   {url}")
    print(f"  Source Profile:  {source}")
    print(f"  Database Engine: {engine}")
    print(f"  Host / Server:   {server}:{agent.port}")
    print(f"  Database Name:   {database}")
    if schema:
        print(f"  Target Schema:   {schema}")
    print(f"  Authentication:  {'User (' + username + ')' if username else 'Default / Trusted'}")
    print("-" * 68)
    # Initialize Telemetry
    AGENT_TELEMETRY["source_id"] = source
    AGENT_TELEMETRY["engine"] = engine
    AGENT_TELEMETRY["database"] = database
    AGENT_TELEMETRY["server"] = f"{server}:{agent.port}"
    AGENT_TELEMETRY["studio_url"] = url
    AGENT_TELEMETRY["status"] = "ONLINE & STREAMING"

    # Launch Local Embedded Visual Web Dashboard
    dashboard_port = start_dashboard_server(8585)
    if dashboard_port:
        dashboard_url = f"http://localhost:{dashboard_port}"
        print(f"  Visual Web GUI:  {dashboard_url}")
        print("-" * 68)
        print("Universal Connector started. Keep this process running.")
        print(f"Opening Local Dashboard at: {dashboard_url}")
        print("Press Ctrl+C to stop.")
        print("=" * 68 + "\n")
        try:
            webbrowser.open(dashboard_url)
        except Exception:
            pass
    else:
        print("Universal Connector started. Keep this process running.")
        print("Press Ctrl+C to stop.")
        print("=" * 68 + "\n")

    try:
        with httpx.Client(
            headers={"Authorization": "Bearer " + token, "X-Connector-Instance": instance_id},
            timeout=30,
            follow_redirects=False,
        ) as client:
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
                            message = str(error) if isinstance(error, (ValueError, RuntimeError)) else connection_diagnostic(error, engine)
                            result = {"error": message}

                        payload = {"lease": task["lease"], "ok": ok, "result": result}
                        json_bytes = json.dumps(payload, allow_nan=False).encode("utf-8")
                        raw_size = len(json_bytes)
                        headers = {"Content-Type": "application/json"}

                        # In-Flight Gzip Payload Compression (5x - 10x Bandwidth Reduction)
                        if raw_size > 1024:
                            compressed = gzip.compress(json_bytes, compresslevel=6)
                            if len(compressed) < raw_size:
                                json_bytes = compressed
                                headers["Content-Encoding"] = "gzip"

                        comp_size = len(json_bytes)
                        AGENT_TELEMETRY["total_bytes_sent"] += raw_size
                        AGENT_TELEMETRY["total_compressed_bytes"] += comp_size
                        if AGENT_TELEMETRY["total_bytes_sent"] > 0:
                            saved = 100 - int((AGENT_TELEMETRY["total_compressed_bytes"] / AGENT_TELEMETRY["total_bytes_sent"]) * 100)
                            AGENT_TELEMETRY["compression_ratio"] = f"{max(saved, 0)}% saved"

                        for attempt in range(3):
                            try:
                                reply = client.post(base + f"/connector/tasks/{task['id']}/result", content=json_bytes, headers=headers)
                                if reply.status_code in {404, 409}:
                                    break
                                reply.raise_for_status()
                                break
                            except httpx.HTTPError:
                                if attempt == 2:
                                    raise
                                time.sleep(1)
                        status_str = "completed" if ok else "failed"
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {task['operation']}: {status_str}")

                        # Update Live Telemetry
                        op = task.get("operation")
                        p = task.get("payload") or {}
                        detail_msg = ""
                        if op == "open":
                            tbl = f"{p.get('schema', '')}.{p.get('table', '')}"
                            AGENT_TELEMETRY["current_table"] = tbl
                            AGENT_TELEMETRY["current_operation"] = f"Streaming {tbl}"
                            detail_msg = tbl
                        elif op == "stage_and_upload" and ok:
                            rows_cnt = result.get("row_count", 0)
                            AGENT_TELEMETRY["total_rows"] += rows_cnt
                            AGENT_TELEMETRY["current_table"] = p.get("table", "")
                            AGENT_TELEMETRY["current_operation"] = f"Direct Staged {p.get('table', '')} ({rows_cnt} rows)"
                            detail_msg = f"{rows_cnt} rows direct staged to Databricks"
                        elif op == "fetch" and ok:
                            rows_cnt = len(result.get("rows", []))
                            AGENT_TELEMETRY["total_rows"] += rows_cnt
                            detail_msg = f"{rows_cnt} rows"
                            now = time.time()
                            dt = now - AGENT_TELEMETRY["last_calc_time"]
                            if dt >= 1.0:
                                AGENT_TELEMETRY["speed"] = int((AGENT_TELEMETRY["total_rows"] - AGENT_TELEMETRY["last_rows_count"]) / dt)
                                AGENT_TELEMETRY["last_rows_count"] = AGENT_TELEMETRY["total_rows"]
                                AGENT_TELEMETRY["last_calc_time"] = now
                        elif op == "close":
                            AGENT_TELEMETRY["current_operation"] = "Table stream closed"

                        log_telemetry(op, status_str, detail_msg)
                    else:
                        time.sleep(2)
                except httpx.HTTPError:
                    print("Hosted application unreachable. Retrying in 5 seconds...")
                    time.sleep(5)
    except KeyboardInterrupt:
        print("\nConnector stopped by user.")
    except SystemExit as e:
        print(f"\n[Connector Stopped] {e}")
        print("Tip: If you re-registered in Studio, update CONNECTOR_TOKEN in 'agent.env'.")
    except Exception as e:
        print(f"\n[Error] {e}")
    finally:
        stopped.set()
        agent.cleanup(all_streams=True)
        if getattr(sys, "frozen", False):
            input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
