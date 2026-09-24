from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    CanonicalRecord,
    MigrationDatabricksConfiguration,
    MigrationEnvironmentPlan,
    MigrationProject,
)
from app.services.databricks_client import execute_sql_with_credentials
from app.services.engine import uid

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,254}$")
ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,254}$")
DEFAULT_SCHEMAS = ("bronze", "silver", "gold")


def _identifier(value: str, label: str) -> str:
    value=(value or "").strip()
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid {label}. Use letters, numbers and underscores; do not start with a number.")
    return value.lower()


def _host(value: str) -> str:
    value=(value or "").strip().rstrip("/")
    if not value:
        raise ValueError("Databricks workspace host is required")
    parsed=urlparse(value if "://" in value else f"https://{value}")
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Databricks workspace host must be a valid HTTPS workspace hostname")
    return parsed.hostname


def _project(db: Session, project_id: str) -> MigrationProject:
    row=db.get(MigrationProject,project_id)
    if not row:
        raise LookupError("Project not found")
    return row


def _audit(db: Session, project_id: str, action: str, actor: str, details: dict) -> None:
    db.add(CanonicalRecord(
        id=uid("REC"), project_id=project_id, record_type="ENVIRONMENT_PROVISIONING_AUDIT",
        environment=details.get("environment"), payload_json=json.dumps({
            "title": action, "status": details.get("status", "RECORDED"),
            "details": details, "actor": actor,
        }),
    ))


def feature_enabled() -> bool:
    return get_settings().databricks_environment_provisioning_enabled


def save_configuration(
    db: Session, project_id: str, *, workspace_host: str, http_path: str,
    token_env_key: str, catalog_prefix: str, actor: str,
) -> MigrationDatabricksConfiguration:
    _project(db,project_id)
    env_key=(token_env_key or "").strip().upper()
    if not ENV_KEY.fullmatch(env_key):
        raise ValueError("Token secret reference must be an uppercase environment-variable name")
    path=(http_path or "").strip()
    if not path.startswith("/sql/"):
        raise ValueError("Databricks SQL warehouse HTTP path must start with /sql/")
    row=db.scalar(select(MigrationDatabricksConfiguration).where(
        MigrationDatabricksConfiguration.project_id==project_id
    ))
    if not row:
        row=MigrationDatabricksConfiguration(id=uid("DBC"),project_id=project_id,
                                             workspace_host="",http_path="")
        db.add(row)
    row.workspace_host=_host(workspace_host)
    row.http_path=path
    row.token_env_key=env_key
    row.catalog_prefix=_identifier(catalog_prefix,"catalog prefix")
    row.status="NOT_TESTED"
    row.last_tested_at=None
    plan=db.scalar(select(MigrationEnvironmentPlan).where(
        MigrationEnvironmentPlan.project_id==project_id,
        MigrationEnvironmentPlan.environment=="DEV",
    ))
    if plan:
        plan.catalog_name=f"{row.catalog_prefix}_dev"
        plan.status="DRAFT"; plan.preflight_json="{}"
        plan.approved_by=None; plan.approved_at=None; plan.provisioned_at=None
    _audit(db,project_id,"DATABRICKS_CONFIGURATION_SAVED",actor,{"status":"NOT_TESTED"})
    db.commit(); db.refresh(row)
    return row


def get_configuration(db: Session, project_id: str) -> MigrationDatabricksConfiguration | None:
    _project(db,project_id)
    return db.scalar(select(MigrationDatabricksConfiguration).where(
        MigrationDatabricksConfiguration.project_id==project_id
    ))


def configuration_view(row: MigrationDatabricksConfiguration | None) -> dict:
    if not row:
        return {"configured":False,"feature_enabled":feature_enabled(),"token_configured":False}
    return {
        "configured":True,"feature_enabled":feature_enabled(),"id":row.id,
        "workspace_host":row.workspace_host,"http_path":row.http_path,
        "token_env_key":row.token_env_key,"token_configured":bool(_token(row)),
        "catalog_prefix":row.catalog_prefix,"status":row.status,
        "last_tested_at":row.last_tested_at,
    }


def _token(row: MigrationDatabricksConfiguration) -> str | None:
    if row.token_env_key == "DATABRICKS_TOKEN":
        return get_settings().databricks_token or os.getenv("DATABRICKS_TOKEN")
    return os.getenv(row.token_env_key)


def _execute(row: MigrationDatabricksConfiguration, statement: str, *, safe_retry: bool=True):
    token=_token(row)
    if not token:
        raise RuntimeError(f"Databricks token secret {row.token_env_key} is not configured")
    try:
        return execute_sql_with_credentials(statement,server_hostname=row.workspace_host,
                                            http_path=row.http_path,access_token=token,safe_retry=safe_retry)
    except Exception as exc:
        # Connector/provider messages are useful, but a provider must never be able
        # to reflect the configured credential into an API response or audit row.
        message=str(exc).replace(token,"[REDACTED]")
        raise RuntimeError(message or "Databricks request failed") from None


def project_execute(
    db: Session, project_id: str, statement: str, *, safe_retry: bool = True
):
    """Execute SQL with the project's tested Databricks configuration.

    Release 2 callers must not fall back to process-wide Databricks coordinates:
    doing so could send a client's data to a different workspace.
    """
    row = get_configuration(db, project_id)
    if not row:
        raise ValueError("Save the project Databricks configuration first")
    if row.status != "READY":
        raise ValueError("Test the project Databricks connection before data ingestion")
    return _execute(row, statement, safe_retry=safe_retry)


@contextmanager
def project_connection(db: Session, project_id: str):
    """Open a project-scoped Databricks SQL connection without exposing its token."""
    row = get_configuration(db, project_id)
    if not row:
        raise ValueError("Save the project Databricks configuration first")
    if row.status != "READY":
        raise ValueError("Test the project Databricks connection before data ingestion")
    token = _token(row)
    if not token:
        raise RuntimeError(f"Databricks token secret {row.token_env_key} is not configured")
    try:
        from databricks import sql
        with sql.connect(
            server_hostname=row.workspace_host,
            http_path=row.http_path,
            access_token=token,
        ) as connection:
            yield connection
    except Exception as exc:
        message = str(exc).replace(token, "[REDACTED]")
        raise RuntimeError(message or "Databricks request failed") from None


def test_connection(db: Session, project_id: str, actor: str) -> dict:
    row=get_configuration(db,project_id)
    if not row:
        raise ValueError("Save the project Databricks configuration first")
    try:
        result=_execute(row,"SELECT current_catalog(), current_schema(), current_user()")
    except Exception:
        row.status="FAILED"; row.last_tested_at=datetime.utcnow()
        _audit(db,project_id,"DATABRICKS_CONNECTION_TEST",actor,{"status":"FAILED"})
        db.commit()
        raise
    row.status="READY"; row.last_tested_at=datetime.utcnow()
    _audit(db,project_id,"DATABRICKS_CONNECTION_TEST",actor,{"status":"READY"})
    db.commit()
    return {"ok":True,"status":"READY","result":[list(x) for x in result]}


def create_dev_plan(db: Session, project_id: str, actor: str) -> MigrationEnvironmentPlan:
    cfg=get_configuration(db,project_id)
    if not cfg:
        raise ValueError("Save the project Databricks configuration first")
    catalog=_identifier(f"{cfg.catalog_prefix}_dev","DEV catalog")
    row=db.scalar(select(MigrationEnvironmentPlan).where(
        MigrationEnvironmentPlan.project_id==project_id,
        MigrationEnvironmentPlan.environment=="DEV",
    ))
    if not row:
        row=MigrationEnvironmentPlan(id=uid("EVP"),project_id=project_id,environment="DEV",
                                     catalog_name=catalog)
        db.add(row)
    row.catalog_name=catalog
    row.schemas_json=json.dumps(DEFAULT_SCHEMAS)
    row.status="DRAFT"; row.preflight_json="{}"
    row.approved_by=None; row.approved_at=None; row.provisioned_at=None
    _audit(db,project_id,"DEV_ENVIRONMENT_PLAN_CREATED",actor,{"environment":"DEV","status":"DRAFT","catalog":catalog})
    db.commit(); db.refresh(row)
    return row


def plan_view(row: MigrationEnvironmentPlan | None) -> dict:
    if not row:
        return {"exists":False,"release_scope":"DEV_ONLY"}
    schemas=json.loads(row.schemas_json)
    return {
        "exists":True,"id":row.id,"environment":row.environment,"catalog_name":row.catalog_name,
        "schemas":schemas,"status":row.status,"preflight":json.loads(row.preflight_json or "{}"),
        "approved_by":row.approved_by,"approved_at":row.approved_at,
        "provisioned_at":row.provisioned_at,"release_scope":"DEV_ONLY",
        "operations":[f"CREATE CATALOG IF NOT EXISTS {row.catalog_name}"] +
                     [f"CREATE SCHEMA IF NOT EXISTS {row.catalog_name}.{s}" for s in schemas],
    }


def get_dev_plan(db: Session, project_id: str) -> MigrationEnvironmentPlan | None:
    _project(db,project_id)
    return db.scalar(select(MigrationEnvironmentPlan).where(
        MigrationEnvironmentPlan.project_id==project_id,
        MigrationEnvironmentPlan.environment=="DEV",
    ))


def preflight_dev_plan(db: Session, project_id: str, actor: str) -> MigrationEnvironmentPlan:
    cfg=get_configuration(db,project_id); plan=get_dev_plan(db,project_id)
    if not cfg or not plan:
        raise ValueError("Databricks configuration and DEV plan are required")
    if cfg.status!="READY":
        raise ValueError("Test the project Databricks connection before preflight")
    catalogs={str(x[0]).lower() for x in _execute(cfg,"SHOW CATALOGS") if x}
    catalog_exists=plan.catalog_name.lower() in catalogs
    existing_schemas=set()
    if catalog_exists:
        existing_schemas={str(x[0]).lower() for x in _execute(cfg,f"SHOW SCHEMAS IN `{plan.catalog_name}`") if x}
    schemas=json.loads(plan.schemas_json)
    result={"catalog":{"name":plan.catalog_name,"action":"SKIP" if catalog_exists else "CREATE"},
            "schemas":[{"name":s,"action":"SKIP" if s.lower() in existing_schemas else "CREATE"} for s in schemas],
            "destructive_operations":0,"connection_status":"READY"}
    plan.preflight_json=json.dumps(result); plan.status="PREFLIGHT_PASSED"
    plan.approved_by=None; plan.approved_at=None
    _audit(db,project_id,"DEV_ENVIRONMENT_PREFLIGHT",actor,{"environment":"DEV","status":"PREFLIGHT_PASSED"})
    db.commit(); db.refresh(plan)
    return plan


def approve_dev_plan(db: Session, project_id: str, actor: str) -> MigrationEnvironmentPlan:
    plan=get_dev_plan(db,project_id)
    if not plan:
        raise LookupError("DEV environment plan not found")
    if plan.status!="PREFLIGHT_PASSED":
        raise ValueError("A successful preflight is required before approval")
    plan.status="APPROVED"; plan.approved_by=actor; plan.approved_at=datetime.utcnow()
    _audit(db,project_id,"DEV_ENVIRONMENT_PLAN_APPROVED",actor,{"environment":"DEV","status":"APPROVED"})
    db.commit(); db.refresh(plan)
    return plan


def provision_dev(db: Session, project_id: str, actor: str) -> dict:
    if not feature_enabled():
        raise PermissionError("Databricks environment provisioning is disabled by feature flag")
    cfg=get_configuration(db,project_id); plan=get_dev_plan(db,project_id)
    if not cfg or not plan:
        raise ValueError("Databricks configuration and DEV plan are required")
    if plan.status=="PROVISIONED":
        return {**plan_view(plan),"reused":True,"executed":0}
    if plan.status!="APPROVED":
        raise ValueError("The DEV environment plan must be approved before provisioning")
    statements=[f"CREATE CATALOG IF NOT EXISTS `{plan.catalog_name}`"]
    statements += [f"CREATE SCHEMA IF NOT EXISTS `{plan.catalog_name}`.`{s}`" for s in json.loads(plan.schemas_json)]
    for statement in statements:
        _execute(cfg,statement,safe_retry=True)
    plan.status="PROVISIONED"; plan.provisioned_at=datetime.utcnow()
    _audit(db,project_id,"DEV_ENVIRONMENT_PROVISIONED",actor,{"environment":"DEV","status":"PROVISIONED","executed":len(statements)})
    db.commit(); db.refresh(plan)
    return {**plan_view(plan),"reused":False,"executed":len(statements)}
