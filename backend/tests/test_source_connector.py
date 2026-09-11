from datetime import datetime, timedelta, date, time
from decimal import Decimal
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from sqlalchemy import select
from app.models.connector import SourceConnector, ConnectorTask
from app.models.entities import MigrationSource
from app.services import source_connector as transport
from app.services.discovery import connection_diagnostic
from app.services.deployment import _source_table_count, _source_rows

spec = importlib.util.spec_from_file_location("local_connector", Path(__file__).parents[2] / "scripts/local_connector.py")
agent_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_module)


def registered(client, db, headers, source_id="SRC", project_id="PROJ"):
    db.add(MigrationSource(id=source_id, project_id=project_id, profile_name="Local", server_name="PC\\SQLEXPRESS", database_name="Demo"))
    db.commit()
    path = f"/api/projects/{project_id}/sources/{source_id}/connector"
    response = client.post(path, headers=headers)
    assert response.status_code == 200
    token = response.json()["token"]
    return path, {"Authorization": "Bearer " + token, "X-Connector-Instance": "agent-1"}, token


def task(db, source_id="SRC", task_id="TASK", expired=False):
    db.add(ConnectorTask(id=task_id, source_id=source_id, operation="test", status="QUEUED", payload="{}",
                        expires_at=datetime.utcnow() + timedelta(seconds=-1 if expired else 120)))
    db.commit()


def test_registration_auth_scope_rotation_and_revocation(client, db, auth_headers):
    path, headers, token = registered(client, db, auth_headers)
    assert db.get(SourceConnector, "SRC").token_hash != token
    assert token not in client.get(path, headers=auth_headers).text
    assert client.post(path).status_code == 401
    from app.core.security import create_access_token
    viewer = {"Authorization": "Bearer " + create_access_token("viewer", "VIEWER")}
    assert client.post(path, headers=viewer).status_code == 403
    assert client.post(path.replace("PROJ", "OTHER"), headers=auth_headers).status_code == 404
    assert client.post("/api/connector/poll", headers=auth_headers).status_code == 401
    assert client.post("/api/connector/poll", headers=headers).status_code == 200
    assert client.get(path, headers=auth_headers).json()["status"] == "ONLINE"
    assert client.post("/api/connector/poll", headers={**headers, "X-Connector-Instance": "agent-2"}).status_code == 409
    assert client.post("/api/connector/heartbeat", headers=headers).status_code == 200
    task(db)
    assert client.post(path, headers=auth_headers).status_code == 200
    assert client.post("/api/connector/poll", headers=headers).status_code == 401
    assert client.delete(path, headers=auth_headers).status_code == 200
    assert client.get(path, headers=auth_headers).json()["status"] == "REVOKED"
    with pytest.raises(RuntimeError, match="CONNECTOR_OFFLINE"):
        transport.request("SRC", "test")


def test_result_source_scope_lease_and_replay(client, db, auth_headers):
    _, headers, _ = registered(client, db, auth_headers)
    _, other, _ = registered(client, db, auth_headers, "OTHER")
    task(db)
    claimed = client.post("/api/connector/poll", headers=headers).json()["task"]
    assert claimed["source_id"] == "SRC"
    assert client.post("/api/connector/poll", headers=headers).json()["task"] is None
    body = {"lease": claimed["lease"], "ok": True, "result": {"ok": True}}
    path = "/api/connector/tasks/TASK/result"
    assert client.post(path, headers=other, json=body).status_code == 404
    assert client.post(path, headers=headers, json={**body, "lease": "wrong"}).status_code == 409
    assert client.post(path, headers=headers, json=body).status_code == 200
    assert client.post(path, headers=headers, json=body).status_code == 409


def test_expired_and_oversized_results(client, db, auth_headers):
    _, headers, _ = registered(client, db, auth_headers)
    task(db, expired=True)
    assert client.post("/api/connector/poll", headers=headers).json()["task"] is None
    response = client.post("/api/connector/tasks/TASK/result", headers=headers, content=b"x" * (4 * 1024 * 1024 + 1))
    assert response.status_code == 413


def test_request_reply_is_consumed_and_deleted(client, db, auth_headers, monkeypatch):
    _, headers, _ = registered(client, db, auth_headers)
    client.post("/api/connector/poll", headers=headers)
    def respond(_):
        claimed = client.post("/api/connector/poll", headers=headers).json()["task"]
        assert claimed["operation"] == "count"
        assert client.post(f"/api/connector/tasks/{claimed['id']}/result", headers=headers,
                           json={"lease": claimed["lease"], "ok": True, "result": {"count": 8}}).status_code == 200
    monkeypatch.setattr(transport.time, "sleep", respond)
    assert transport.request("SRC", "count", {"schema": "dbo", "table": "Orders"}) == {"count": 8}
    assert db.scalar(select(ConnectorTask)) is None


def test_offline_discovery_does_not_ingest(client, db, auth_headers):
    registered(client, db, auth_headers)
    response = client.post("/api/projects/PROJ/discovery/live/SRC", headers=auth_headers)
    assert response.status_code == 400
    assert "CONNECTOR_OFFLINE" in response.text


def test_source_test_and_discovery_use_connector(client, db, auth_headers, monkeypatch):
    registered(client, db, auth_headers)
    from app.api import routes
    called = []
    def reply(source_id, operation):
        called.append((source_id, operation))
        return {"ok": True} if operation == "test" else {"database": "Demo", "objects": []}
    monkeypatch.setattr(routes, "connector_request", reply)
    monkeypatch.setattr(routes, "ingest_snapshot", lambda *args: {})
    monkeypatch.setattr(routes, "test_sqlserver_connection", lambda *args: pytest.fail("Direct connection used"))
    assert client.post("/api/projects/PROJ/sources/SRC/test", headers=auth_headers).status_code == 200
    assert client.post("/api/projects/PROJ/discovery/live/SRC", headers=auth_headers).status_code == 200
    assert called == [("SRC", "test"), ("SRC", "test"), ("SRC", "discover")]


@pytest.mark.parametrize("value", [Decimal("123456789.000000123"), b"\x00\xff", datetime(2026, 1, 2, 3, 4), date(2026, 1, 2), time(3, 4), None, 123, "text"])
def test_value_roundtrip(value):
    assert transport.decode_value(json.loads(json.dumps(agent_module.encode_value(value)))) == value


def test_local_agent_rejects_arbitrary_operations_and_wrong_source():
    agent = agent_module.LocalAgent("SRC", "PC", "Demo", "secret")
    base = {"source_id": "SRC", "server": "PC", "database": "Demo", "operation": "execute_sql", "payload": {"sql": "DROP TABLE Orders"}}
    with pytest.raises(ValueError, match="Unsupported operation"):
        agent.handle(base)
    with pytest.raises(ValueError, match="identity mismatch"):
        agent.handle({**base, "database": "master", "operation": "test"})
    with pytest.raises(ValueError):
        agent_module.validate_url("http://example.com")
    with pytest.raises(ValueError):
        agent_module.validate_url("https://user:secret@example.com")


def test_local_cursor_batches_do_not_skip_rows(monkeypatch):
    agent = agent_module.LocalAgent("SRC", "PC", "Demo", "secret")
    rows = iter([(Decimal("1.25"),), (Decimal("2.50"),), None])
    closed = []
    agent.streams["stream"] = [SimpleNamespace(close=lambda: closed.append(True)),
                               SimpleNamespace(fetchone=lambda: next(rows)), 0, None]
    import time as clock
    agent.streams["stream"][2] = clock.monotonic()
    base = {"source_id": "SRC", "server": "PC", "database": "Demo", "operation": "fetch",
            "payload": {"stream_id": "stream", "size": 1}}
    assert agent.handle(base)["rows"] == [[{"kind": "decimal", "value": "1.25"}]]
    assert agent.handle(base)["rows"] == [[{"kind": "decimal", "value": "2.50"}]]
    assert agent.handle(base)["rows"] == []
    agent.handle({**base, "operation": "close"})
    assert closed == [True]


def test_table_read_uses_local_metadata_and_parameterized_lookup(monkeypatch):
    statements, closed = [], []
    class Cursor:
        def execute(self, sql, *params):
            statements.append((sql, params))
            return self
        def fetchone(self):
            return (42,)
        def fetchall(self):
            return [("Amount", "decimal", 19, 4)]
    conn = SimpleNamespace(cursor=lambda: Cursor(), close=lambda: closed.append(True))
    agent = agent_module.LocalAgent("SRC", "PC", "Demo", "secret")
    monkeypatch.setattr(agent, "connect", lambda: conn)
    task = {"source_id": "SRC", "server": "PC", "database": "Demo", "operation": "open",
            "payload": {"schema": "dbo", "table": "Orders];DROP TABLE X--", "columns": ["Amount"], "max_rows": 5}}
    result = agent.handle(task)
    assert statements[0][1] == ("dbo", "Orders];DROP TABLE X--")
    assert statements[-1][0] == "SELECT TOP (5) [Amount] FROM [dbo].[Orders]];DROP TABLE X--]"
    assert result["stream_id"] in agent.streams
    agent.cleanup(all_streams=True)
    assert closed == [True]
    with pytest.raises(ValueError, match="columns changed"):
        agent.handle({**task, "payload": {**task["payload"], "columns": ["Missing"]}})


def test_source_counts_and_stream_route_through_connector(client, db, auth_headers, monkeypatch):
    registered(client, db, auth_headers)
    from app.services import deployment
    monkeypatch.setattr(deployment, "connector_request", lambda *args: {"count": 8})
    obj = SimpleNamespace(schema_name="dbo", object_name="Orders")
    src = db.get(MigrationSource, "SRC")
    assert _source_table_count(src, obj) == 8
    replies = iter([{"stream_id": "stream"}, {"rows": [[{"kind": "decimal", "value": "1.25"}]]}, {"closed": True}])
    monkeypatch.setattr(transport, "request", lambda *args: next(replies))
    with _source_rows(src, obj, [SimpleNamespace(column_name="Amount")], "unused", None) as stream:
        assert stream.fetchmany(10000) == [(Decimal("1.25"),)]


@pytest.mark.parametrize("message,code", [("HYT00 login timeout expired", "NETWORK_UNREACHABLE"), ("28000 login failed secret", "AUTHENTICATION_FAILED"), ("4060 cannot open database", "DATABASE_ACCESS"), ("SSL certificate", "TLS_ERROR")])
def test_diagnostics_do_not_expose_raw_credentials(message, code):
    result = connection_diagnostic(Exception(message))
    assert result.startswith(code)
    assert "secret" not in result
