from __future__ import annotations
import time
from contextvars import ContextVar
from functools import wraps
from app.core.config import get_settings

_project_scope = ContextVar("databricks_project_scope", default=None)


def with_project_databricks(function):
    """Keep nested SQL calls scoped to this request's project, including retries."""
    @wraps(function)
    def scoped(db, project_id, *args, **kwargs):
        scope_token = _project_scope.set((db, project_id))
        try:
            return function(db, project_id, *args, **kwargs)
        finally:
            _project_scope.reset(scope_token)
    return scoped


def _project_configuration():
    scope = _project_scope.get()
    if scope is None:
        return None
    from app.services.environment_provisioning import get_configuration
    db, project_id = scope
    return get_configuration(db, project_id)


def workspace_host():
    row = _project_configuration()
    return row.workspace_host if row else get_settings().databricks_host

TRANSIENT = ("warehouse is starting","connection reset","temporary service unavailable","gateway timeout","rate limit","deadlock")

def execute_sql(statement: str, safe_retry: bool=True):
    if _project_configuration() is not None:
        from app.services.environment_provisioning import project_execute
        db, project_id = _project_scope.get()
        return project_execute(db, project_id, statement, safe_retry=safe_retry)
    s=get_settings()
    if not all([s.databricks_host,s.databricks_http_path,s.databricks_token]): raise RuntimeError("Databricks connection is not configured")
    from databricks import sql
    delays=[2,4,8,16]
    for attempt in range(len(delays)+1):
        try:
            with sql.connect(server_hostname=s.databricks_host,http_path=s.databricks_http_path,access_token=s.databricks_token) as conn:
                with conn.cursor() as cur:
                    cur.execute(statement)
                    try: return cur.fetchall()
                    except Exception: return []
        except Exception as e:
            msg=str(e).lower(); transient=any(x in msg for x in TRANSIENT)
            if not (safe_retry and transient and attempt < len(delays)): raise
            time.sleep(delays[attempt])


def execute_sql_with_credentials(
    statement: str,
    *,
    server_hostname: str,
    http_path: str,
    access_token: str,
    safe_retry: bool = True,
):
    """Execute project-scoped SQL without changing the legacy global connector."""
    from databricks import sql
    delays=[2,4,8,16]
    for attempt in range(len(delays)+1):
        try:
            with sql.connect(server_hostname=server_hostname,http_path=http_path,access_token=access_token) as conn:
                with conn.cursor() as cur:
                    cur.execute(statement)
                    try: return cur.fetchall()
                    except Exception: return []
        except Exception as e:
            msg=str(e).lower(); transient=any(x in msg for x in TRANSIENT)
            if not (safe_retry and transient and attempt < len(delays)): raise
            time.sleep(delays[attempt])


def databricks_connection():
    if _project_configuration() is not None:
        from app.services.environment_provisioning import project_connection
        db, project_id = _project_scope.get()
        return project_connection(db, project_id)
    s=get_settings()
    if not all([s.databricks_host,s.databricks_http_path,s.databricks_token]):
        raise RuntimeError("Databricks connection is not configured")
    from databricks import sql
    return sql.connect(server_hostname=s.databricks_host,http_path=s.databricks_http_path,access_token=s.databricks_token)
