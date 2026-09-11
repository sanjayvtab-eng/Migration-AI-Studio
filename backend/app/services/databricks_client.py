from __future__ import annotations
import time
from app.core.config import get_settings

TRANSIENT = ("warehouse is starting","connection reset","temporary service unavailable","gateway timeout","rate limit","deadlock")

def execute_sql(statement: str, safe_retry: bool=True):
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


def databricks_connection():
    s=get_settings()
    if not all([s.databricks_host,s.databricks_http_path,s.databricks_token]):
        raise RuntimeError("Databricks connection is not configured")
    from databricks import sql
    return sql.connect(server_hostname=s.databricks_host,http_path=s.databricks_http_path,access_token=s.databricks_token)
