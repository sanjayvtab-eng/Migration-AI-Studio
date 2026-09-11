from sqlalchemy import select

from app.models.entities import CanonicalRecord, MigrationEnvironmentPlan
from app.services import environment_provisioning as service


def _project(client, auth_headers):
    response=client.post("/api/projects",json={"name":"Provisioning Project"},headers=auth_headers)
    assert response.status_code==200
    return response.json()["id"]


def _configuration():
    return {
        "workspace_host":"https://dbc-example.cloud.databricks.com",
        "http_path":"/sql/1.0/warehouses/abc123",
        "token_env_key":"CLIENT_A_DATABRICKS_TOKEN",
        "catalog_prefix":"client_a_migration",
    }


def test_configuration_stores_secret_reference_not_secret(client,auth_headers,db,monkeypatch):
    project_id=_project(client,auth_headers)
    monkeypatch.setenv("CLIENT_A_DATABRICKS_TOKEN","not-returned-to-browser")
    response=client.put(f"/api/projects/{project_id}/databricks/configuration",
                        json=_configuration(),headers=auth_headers)
    assert response.status_code==200
    payload=response.json()
    assert payload["workspace_host"]=="dbc-example.cloud.databricks.com"
    assert payload["token_env_key"]=="CLIENT_A_DATABRICKS_TOKEN"
    assert payload["token_configured"] is True
    assert "token" not in payload
    rejected=client.put(f"/api/projects/{project_id}/databricks/configuration",
                        json={**_configuration(),"token":"must-not-be-accepted"},headers=auth_headers)
    assert rejected.status_code==422
    audit=db.scalars(select(CanonicalRecord).where(
        CanonicalRecord.project_id==project_id,
        CanonicalRecord.record_type=="ENVIRONMENT_PROVISIONING_AUDIT",
    )).all()
    assert audit
    assert all("not-returned-to-browser" not in row.payload_json for row in audit)


def test_dev_plan_requires_preflight_approval_and_is_idempotent(client,auth_headers,db,monkeypatch):
    project_id=_project(client,auth_headers)
    monkeypatch.setenv("CLIENT_A_DATABRICKS_TOKEN","test-token")
    calls=[]

    def fake_execute(_config,statement,*,safe_retry=True):
        calls.append(statement)
        if statement.startswith("SELECT current_catalog"):
            return [("hive_metastore","default","tester")]
        if statement=="SHOW CATALOGS":
            return [("system",),("hive_metastore",)]
        return []

    monkeypatch.setattr(service,"_execute",fake_execute)
    monkeypatch.setattr(service,"feature_enabled",lambda:True)

    saved=client.put(f"/api/projects/{project_id}/databricks/configuration",
                     json=_configuration(),headers=auth_headers)
    assert saved.status_code==200
    assert client.post(f"/api/projects/{project_id}/databricks/connection-test",headers=auth_headers).status_code==200

    plan=client.post(f"/api/projects/{project_id}/environments/dev/plan",headers=auth_headers)
    assert plan.status_code==200
    assert plan.json()["catalog_name"]=="client_a_migration_dev"
    assert plan.json()["schemas"]==["bronze","silver","gold"]
    blocked=client.post(f"/api/projects/{project_id}/environments/dev/provision",headers=auth_headers)
    assert blocked.status_code==400

    preflight=client.post(f"/api/projects/{project_id}/environments/dev/preflight",headers=auth_headers)
    assert preflight.status_code==200
    assert preflight.json()["status"]=="PREFLIGHT_PASSED"
    assert preflight.json()["preflight"]["destructive_operations"]==0
    assert client.post(f"/api/projects/{project_id}/environments/dev/approve",headers=auth_headers).status_code==200

    calls.clear()
    provisioned=client.post(f"/api/projects/{project_id}/environments/dev/provision",headers=auth_headers)
    assert provisioned.status_code==200
    assert provisioned.json()["status"]=="PROVISIONED"
    assert provisioned.json()["executed"]==4
    assert calls==[
        "CREATE CATALOG IF NOT EXISTS `client_a_migration_dev`",
        "CREATE SCHEMA IF NOT EXISTS `client_a_migration_dev`.`bronze`",
        "CREATE SCHEMA IF NOT EXISTS `client_a_migration_dev`.`silver`",
        "CREATE SCHEMA IF NOT EXISTS `client_a_migration_dev`.`gold`",
    ]

    calls.clear()
    repeated=client.post(f"/api/projects/{project_id}/environments/dev/provision",headers=auth_headers)
    assert repeated.status_code==200
    assert repeated.json()["reused"] is True
    assert repeated.json()["executed"]==0
    assert calls==[]
    persisted=db.scalar(select(MigrationEnvironmentPlan).where(
        MigrationEnvironmentPlan.project_id==project_id,
        MigrationEnvironmentPlan.environment=="DEV",
    ))
    assert persisted.status=="PROVISIONED"


def test_provisioning_feature_flag_blocks_execution(client,auth_headers,monkeypatch):
    project_id=_project(client,auth_headers)
    monkeypatch.setenv("CLIENT_A_DATABRICKS_TOKEN","test-token")
    monkeypatch.setattr(service,"_execute",lambda *_args,**_kwargs: [("x","y","z")])
    monkeypatch.setattr(service,"feature_enabled",lambda:False)
    client.put(f"/api/projects/{project_id}/databricks/configuration",json=_configuration(),headers=auth_headers)
    client.post(f"/api/projects/{project_id}/databricks/connection-test",headers=auth_headers)
    client.post(f"/api/projects/{project_id}/environments/dev/plan",headers=auth_headers)
    client.post(f"/api/projects/{project_id}/environments/dev/preflight",headers=auth_headers)
    client.post(f"/api/projects/{project_id}/environments/dev/approve",headers=auth_headers)
    response=client.post(f"/api/projects/{project_id}/environments/dev/provision",headers=auth_headers)
    assert response.status_code==409
    assert "feature flag" in response.json()["detail"].lower()


def test_connector_error_redacts_project_token(client,auth_headers,monkeypatch):
    project_id=_project(client,auth_headers)
    secret="sensitive-client-token"
    monkeypatch.setenv("CLIENT_A_DATABRICKS_TOKEN",secret)
    client.put(f"/api/projects/{project_id}/databricks/configuration",
               json=_configuration(),headers=auth_headers)

    def fail(*_args,**_kwargs):
        raise RuntimeError(f"provider echoed {secret}")

    monkeypatch.setattr(service,"execute_sql_with_credentials",fail)
    response=client.post(f"/api/projects/{project_id}/databricks/connection-test",headers=auth_headers)
    assert response.status_code==400
    assert secret not in response.text
    assert "[REDACTED]" in response.text
