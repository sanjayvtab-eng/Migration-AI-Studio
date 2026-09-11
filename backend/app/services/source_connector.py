"""Bounded, persisted request/reply queue for outbound local connectors."""
import hashlib
import json
import secrets
import time
from threading import BoundedSemaphore
from datetime import datetime, timedelta
from decimal import Decimal
from app.core.database import SessionLocal
from app.models.connector import SourceConnector, ConnectorTask

OPERATIONS = {"test", "discover", "count", "open", "fetch", "close"}
TASK_TIMEOUT = 120
_waiting = BoundedSemaphore(8)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def connector_info(source_id):
    with SessionLocal() as db:
        row = db.get(SourceConnector, source_id)
        if row is None:
            return {"mode": "DIRECT", "status": "DIRECT"}
        online = row.last_seen and datetime.utcnow() - row.last_seen < timedelta(seconds=45)
        return {"mode": "CONNECTOR", "status": ("ONLINE" if online else "OFFLINE")
                if row.enabled == "ENABLED" else "REVOKED", "last_seen": row.last_seen}


def request(source_id, operation, payload=None):
    # Leave API worker capacity available for agent polls and result delivery.
    if not _waiting.acquire(blocking=False):
        raise RuntimeError("CONNECTOR_BUSY: Too many source operations are active. Retry when an operation finishes.")
    try:
        return _request(source_id, operation, payload)
    finally:
        _waiting.release()


def _request(source_id, operation, payload=None):
    if operation not in OPERATIONS:
        raise ValueError("Unsupported connector operation")
    if connector_info(source_id)["status"] != "ONLINE":
        raise RuntimeError("CONNECTOR_OFFLINE: Start the registered local connector, then test the source again.")
    task_id = secrets.token_hex(16)
    with SessionLocal() as db:
        db.add(ConnectorTask(id=task_id, source_id=source_id, operation=operation,
                            payload=json.dumps(payload or {}), status="QUEUED",
                            expires_at=datetime.utcnow() + timedelta(seconds=TASK_TIMEOUT)))
        db.commit()
    deadline = time.monotonic() + TASK_TIMEOUT
    try:
        while time.monotonic() < deadline:
            with SessionLocal() as db:
                task = db.get(ConnectorTask, task_id)
                if task is None or task.status == "CANCELLED":
                    raise RuntimeError("CONNECTOR_CANCELLED: The connector was revoked or the task expired.")
                if task.status == "FAILED":
                    raise RuntimeError(json.loads(task.result)["error"])
                if task.status == "COMPLETED":
                    return json.loads(task.result)
            time.sleep(0.25)
        raise RuntimeError("CONNECTOR_TIMEOUT: No result received. Check the local connector and retry the operation.")
    finally:
        # Source rows are transient transport data, not permanent application logs.
        with SessionLocal() as db:
            task = db.get(ConnectorTask, task_id)
            if task:
                db.delete(task)
                db.commit()


def decode_value(value):
    if not isinstance(value, dict):
        return value
    kind, raw = value.get("kind"), value.get("value")
    if kind == "decimal":
        return Decimal(raw)
    if kind == "bytes":
        return bytes.fromhex(raw)
    if kind == "datetime":
        return datetime.fromisoformat(raw)
    if kind == "date":
        from datetime import date
        return date.fromisoformat(raw)
    if kind == "time":
        from datetime import time as time_type
        return time_type.fromisoformat(raw)
    raise ValueError("Unsupported connector value type")


class TableStream:
    """Maintain one local SQL cursor; fetches never repeat OFFSET queries."""
    def __init__(self, source_id, obj, columns, max_rows=None):
        self.source_id = source_id
        self.payload = {"schema": obj.schema_name, "table": obj.object_name,
                        "columns": [c.column_name for c in columns], "max_rows": max_rows}
        self.stream_id = None

    def __enter__(self):
        self.stream_id = request(self.source_id, "open", self.payload)["stream_id"]
        return self

    def fetchmany(self, size):
        result = request(self.source_id, "fetch", {"stream_id": self.stream_id,
                                                 "size": min(max(int(size), 1), 1000)})
        return [tuple(decode_value(v) for v in row) for row in result["rows"]]

    def __exit__(self, *args):
        try:
            request(self.source_id, "close", {"stream_id": self.stream_id})
        except RuntimeError:
            pass  # Agent also closes abandoned cursors after its idle deadline.
