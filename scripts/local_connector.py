"""Run on the SQL Server network. No inbound listener or arbitrary SQL endpoint."""
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
from urllib.parse import urlsplit
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.discovery import discover_sqlserver, test_sqlserver_connection, connection_diagnostic
from app.services.type_compatibility import source_select_expression


def quoted(value):
    if not isinstance(value, str) or not value or len(value) > 128 or "\x00" in value:
        raise ValueError("Invalid SQL identifier")
    return "[" + value.replace("]", "]]") + "]"


def odbc_value(value):
    return "{" + value.replace("}", "}}") + "}"


def encode_value(value):
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


class LocalAgent:
    def __init__(self, source_id, server, database, connection_string):
        self.source_id, self.server, self.database = source_id, server, database
        self.connection_string = connection_string
        self.streams = {}

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

    def cleanup(self, all_streams=False):
        for key, item in list(self.streams.items()):
            if all_streams or time.monotonic() - item[2] > 150:
                try:
                    item[0].close()
                finally:
                    del self.streams[key]

    def handle(self, task):
        if (task.get("source_id"), task.get("server"), task.get("database")) != (
                self.source_id, self.server, self.database):
            raise ValueError("Source identity mismatch; verify the registered source profile")
        op, data = task["operation"], task.get("payload", {})
        self.cleanup()
        if op == "test":
            return test_sqlserver_connection(self.connection_string)
        if op == "discover":
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
            # Stop below the transport limit without skipping already fetched rows.
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


def validate_url(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Connector requires an HTTPS application URL without embedded credentials or query parameters")
    return url.rstrip("/") + "/api"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--driver", default="ODBC Driver 17 for SQL Server")
    parser.add_argument("--username", help="Omit to use the Windows account running this process")
    parser.add_argument("--trust-server-certificate", action="store_true")
    args = parser.parse_args()
    base = validate_url(args.url)
    token = os.environ.get("CONNECTOR_TOKEN") or getpass.getpass("Connector registration token: ")
    credentials = "Trusted_Connection=yes;"
    if args.username:
        password = os.environ.get("CONNECTOR_SQL_PASSWORD") or getpass.getpass("SQL Server password: ")
        credentials = f"UID={odbc_value(args.username)};PWD={odbc_value(password)};"
    connection = (f"DRIVER={odbc_value(args.driver)};SERVER={odbc_value(args.server)};"
                  f"DATABASE={odbc_value(args.database)};{credentials}Encrypt=yes;"
                  f"TrustServerCertificate={'yes' if args.trust_server_certificate else 'no'};")
    agent = LocalAgent(args.source, args.server, args.database, connection)
    import httpx
    stopped = threading.Event()
    instance_id = secrets.token_hex(16)
    print("Connector started. Keep this process running; SQL credentials stay on this machine.")
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
                        raise SystemExit("Registration rejected, revoked, or another connector is active. Check Sources.")
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
                            # Locally generated validation messages contain no SQL credentials.
                            message = str(error) if isinstance(error, (ValueError, RuntimeError)) else connection_diagnostic(error)
                            result = {"error": message}
                        payload = {"lease": task["lease"], "ok": ok, "result": result}
                        # Retry only delivery, never repeat a fetch that advanced a cursor.
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
                        print(f"{task['operation']}: {'completed' if ok else 'failed'}")
                    else:
                        time.sleep(2)
                except httpx.HTTPError:
                    print("Hosted application unreachable. Retrying in 5 seconds.")
                    time.sleep(5)
    except KeyboardInterrupt:
        print("Connector stopped.")
    finally:
        stopped.set()
        agent.cleanup(all_streams=True)


if __name__ == "__main__":
    main()
