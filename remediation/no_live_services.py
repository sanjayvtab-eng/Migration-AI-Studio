"""Opt-in pytest guard: unit/API regressions must mock external integrations.

TestClient's in-process transport is unaffected. No source/target credentials are used.
"""
def pytest_sessionstart(session):
    import httpx
    def denied(*args, **kwargs):
        raise RuntimeError('Live integration disabled in the local regression suite; use an explicit test double')
    httpx.HTTPTransport.handle_request = denied
    for module_name in ('pyodbc','psycopg2','pymysql','oracledb'):
        module=__import__(module_name)
        module.connect=denied
    from databricks import sql
    sql.connect=denied


def pytest_runtest_logstart(nodeid, location):
    import os, json
    from pathlib import Path
    if os.getenv('REVIEW_TEST_PROGRESS'):
        Path(os.environ['REVIEW_TEST_PROGRESS']).write_text(json.dumps({'current_test':nodeid}),encoding='utf-8')
