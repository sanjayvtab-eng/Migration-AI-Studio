import json
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.routes import auth
from app.models.entities import MigrationSource
from app.models.connector import SourceConnector, ConnectorTask
from app.services.source_connector import digest, connector_info

router = APIRouter(prefix="/api")


def admin(user=Depends(auth)):
    if user.get("role") != "ADMIN":
        raise HTTPException(403, "Administrator permission required")
    return user


def source(db, project_id, source_id):
    row = db.get(MigrationSource, source_id)
    if not row or row.project_id != project_id:
        raise HTTPException(404, "Source not found in project")
    return row


@router.get("/projects/{project_id}/sources/{source_id}/connector")
def status(project_id: str, source_id: str, db: Session = Depends(get_db), _=Depends(auth)):
    source(db, project_id, source_id)
    return connector_info(source_id)


@router.post("/projects/{project_id}/sources/{source_id}/connector")
def register(project_id: str, source_id: str, db: Session = Depends(get_db), _=Depends(admin)):
    source(db, project_id, source_id)
    token = secrets.token_urlsafe(48)
    row = db.get(SourceConnector, source_id)
    if not row:
        row = SourceConnector(source_id=source_id, project_id=project_id)
        db.add(row)
    row.token_hash = digest(token)
    row.enabled = "ENABLED"
    row.last_seen = None
    row.instance_id = None
    db.execute(update(ConnectorTask).where(ConnectorTask.source_id == source_id).values(status="CANCELLED", result=None))
    db.commit()
    return {"source_id": source_id, "token": token}


@router.delete("/projects/{project_id}/sources/{source_id}/connector")
def revoke(project_id: str, source_id: str, db: Session = Depends(get_db), _=Depends(admin)):
    source(db, project_id, source_id)
    row = db.get(SourceConnector, source_id)
    if not row:
        raise HTTPException(404, "Connector not registered")
    row.enabled = "REVOKED"
    row.last_seen = None
    db.execute(update(ConnectorTask).where(ConnectorTask.source_id == source_id).values(status="CANCELLED", result=None))
    db.commit()
    return {"status": "REVOKED"}


def agent(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Connector authentication required")
    row = db.scalar(select(SourceConnector).where(SourceConnector.token_hash == digest(authorization[7:]),
                                                  SourceConnector.enabled == "ENABLED"))
    if not row:
        raise HTTPException(401, "Connector token invalid or revoked")
    return row


def claim_instance(db, connector, instance):
    if not instance or len(instance) > 64:
        raise HTTPException(400, "Connector instance ID required")
    now = datetime.utcnow()
    # A compare-and-set prevents two agents from sharing cursor tasks.
    changed = db.execute(update(SourceConnector).where(
        SourceConnector.source_id == connector.source_id,
        SourceConnector.enabled == "ENABLED",
        SourceConnector.token_hash == connector.token_hash,
        (SourceConnector.instance_id == None) | (SourceConnector.instance_id == instance) |
        (SourceConnector.last_seen < now - timedelta(seconds=45)),
    ).values(instance_id=instance, last_seen=now))
    if not changed.rowcount:
        raise HTTPException(409, "Another connector instance is online for this source")


@router.post("/connector/heartbeat")
def heartbeat(x_connector_instance: str = Header(default=""), db: Session = Depends(get_db), connector=Depends(agent)):
    claim_instance(db, connector, x_connector_instance)
    db.commit()
    return {"online": True}


@router.post("/connector/poll")
def poll(x_connector_instance: str = Header(default=""), db: Session = Depends(get_db), connector=Depends(agent)):
    now = datetime.utcnow()
    claim_instance(db, connector, x_connector_instance)
    db.execute(delete(ConnectorTask).where(ConnectorTask.source_id == connector.source_id,
                                           ConnectorTask.expires_at < now))
    task = db.scalar(select(ConnectorTask).where(ConnectorTask.source_id == connector.source_id,
                                                ConnectorTask.status == "QUEUED",
                                                ConnectorTask.expires_at > now).order_by(ConnectorTask.expires_at))
    result = None
    if task:
        lease = secrets.token_hex(24)
        changed = db.execute(update(ConnectorTask).where(ConnectorTask.id == task.id,
                              ConnectorTask.status == "QUEUED").values(status="RUNNING", lease=lease))
        if changed.rowcount:
            src = db.get(MigrationSource, connector.source_id)
            result = {"id": task.id, "lease": lease, "operation": task.operation,
                      "payload": json.loads(task.payload), "source_id": src.id,
                      "server": src.server_name, "database": src.database_name}
    db.commit()
    return {"task": result}


class ResultIn(BaseModel):
    lease: str
    ok: bool
    result: dict


@router.post("/connector/tasks/{task_id}/result")
async def complete(task_id: str, request: Request, x_connector_instance: str = Header(default=""), db: Session = Depends(get_db), connector=Depends(agent)):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4 * 1024 * 1024:
            raise HTTPException(413, "Connector response exceeds 4 MiB; reduce source row size")
    try:
        data = ResultIn.model_validate_json(body)
    except ValueError:
        raise HTTPException(422, "Invalid connector result")
    task = db.get(ConnectorTask, task_id)
    if not task or task.source_id != connector.source_id:
        raise HTTPException(404, "Task not found")
    if connector.instance_id != x_connector_instance:
        raise HTTPException(409, "Connector instance has changed")
    if task.status != "RUNNING" or task.expires_at <= datetime.utcnow() or task.lease != data.lease:
        raise HTTPException(409, "Task expired or already completed")
    changed = db.execute(update(ConnectorTask).where(ConnectorTask.id == task_id,
        ConnectorTask.status == "RUNNING", ConnectorTask.lease == data.lease,
        ConnectorTask.expires_at > datetime.utcnow()).values(
        status="COMPLETED" if data.ok else "FAILED",
        result=json.dumps(data.result if data.ok else {"error": str(data.result.get("error", "Connector operation failed"))[:2000]})))
    if not changed.rowcount:
        raise HTTPException(409, "Task expired or already completed")
    connector.last_seen = datetime.utcnow()
    db.commit()
    return {"accepted": True}
