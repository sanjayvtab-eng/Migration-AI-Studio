import json
import pytest

from app.models.entities import (CanonicalRecord, MigrationSource, MigrationStageArtifact,
                                 MigrationStageArtifactVersion)
from app.models.canonical import MigrationDeployment
from app.services import master_orchestration, medallion, databricks_client, deployment
from app.services.engine import (add_source, ensure_project, classify_project, create_mappings,
                                 ingest_snapshot, sha, uid)


MASTER_PROMPT = (
    "Migrate MigrationDemo from SQL Server through DEV, TEST, UAT, and PROD Databricks"
)


def _project(db, name="Release 6 master workflow"):
    project = ensure_project(db, name)
    add_source(db, project.id, "SQL Server", "localhost", "MigrationDemo")
    return project


def _mock_dev_plan(monkeypatch):
    dev_plan = {
        "plan_id": "DEV_PLAN_1",
        "status": "PENDING_APPROVAL",
        "impact": {"table_count": 6, "estimated_rows": 32, "requires_overwrite": False},
    }
    monkeypatch.setattr(
        master_orchestration.prompt_orchestration,
        "generate_prompt_plan",
        lambda *a, **kw: dict(dev_plan),
    )
    monkeypatch.setattr(
        master_orchestration.prompt_orchestration,
        "get_prompt_plan",
        lambda *a, **kw: dict(dev_plan),
    )
    return dev_plan


def _mock_successful_chain(monkeypatch, calls):
    monkeypatch.setattr(
        master_orchestration.prompt_orchestration,
        "execute_prompt_plan",
        lambda *a, **kw: calls.append("DEV") or {"status": "COMPLETED", "run_id": "DEV_RUN"},
    )

    def promotion_plan(*args, **kwargs):
        prompt = kwargs.get("prompt") or args[2]
        target = prompt.rsplit(" ", 1)[-1]
        calls.append(f"PLAN_{target}")
        return {"status": "PENDING_APPROVAL", "plan_id": f"PLAN_{target}"}

    def promotion_execute(*args, **kwargs):
        target = kwargs["plan_id"].replace("PLAN_", "")
        calls.append(target)
        return {"status": "COMPLETED", "run_id": f"RUN_{target}"}

    monkeypatch.setattr(
        master_orchestration.prompt_promotion, "generate_promotion_plan", promotion_plan
    )
    monkeypatch.setattr(
        master_orchestration.prompt_promotion, "execute_promotion_plan", promotion_execute
    )


def _procedure_artifact(db, project, *, invalid=True):
    source = db.query(MigrationSource).filter_by(project_id=project.id).one()
    ingest_snapshot(db, project.id, source.id, {'database': 'MigrationDemo', 'objects': [
        {'schema': 'dbo', 'name': 'usp_LoadCustomerSales', 'type': 'PROCEDURE',
         'definition': 'CREATE PROCEDURE dbo.usp_LoadCustomerSales AS BEGIN SELECT 1 AS result; END',
         'parameters': []},
    ]})
    classify_project(db, project.id)
    create_mappings(db, project.id, 'DEV', 'migration_dev')
    medallion.build_medallion_plan(db, project.id, environment='DEV', catalog='migration_dev')
    medallion.generate_medallion_artifacts(db, project.id)
    item = medallion.list_medallion_artifacts(db, project.id)[0]
    version = db.get(MigrationStageArtifactVersion, item['artifact_version_id'])
    if invalid:
        version.content = version.content.replace('LANGUAGE SQL', 'LANGUAGE SQL\nREADS SQL DATA')
        version.content_hash = sha(version.content)
    version.review_status = 'APPROVED'
    db.commit()
    return item, version


def _fail_dev_three_times(db, project, plan, monkeypatch, calls, stage_runner=None):
    monkeypatch.setattr(master_orchestration, '_run_stage', stage_runner or (
        lambda *a, **kw: calls.append('DEV') or {'status': 'FAILED', 'error': 'DEV deployment failed'}
    ))
    for attempt in range(3):
        result = master_orchestration.execute_master_plan(
            db, project.id, plan['plan_id'], workflow_authorized=attempt == 0,
            production_authorized=attempt == 0,
        )
        assert result['status'] == 'FAILED'
    assert len(calls) == 3


@pytest.mark.parametrize('legacy', [False, True])
def test_capped_master_resume_runs_new_approved_sql_without_losing_authorization(db, monkeypatch, legacy):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    item, old = _procedure_artifact(db, project)
    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)
    calls = []
    original_runner = master_orchestration._run_stage
    _fail_dev_three_times(db, project, plan, monkeypatch, calls)
    capped = master_orchestration.execute_master_plan(db, project.id, plan['plan_id'])
    assert len(calls) == 3 and 'maximum of 3' in capped['error']
    saved = master_orchestration.get_master_plan(db, project.id, plan['plan_id'])
    authorization = saved['authorization']
    if legacy:
        saved['checkpoints']['DEV_MIGRATION'].pop('retry_evidence')
        saved['checkpoints']['DEV_MIGRATION'].pop('total_attempts')
        record = master_orchestration._master_plan_record(db, project.id, plan['plan_id'])
        master_orchestration._save_plan(db, record, saved)
        db.add(MigrationDeployment(id=uid('DPL'), project_id=project.id, environment='DEV', status='FAILED',
            payload_json=json.dumps({'target_fqn': item['target_fqn'], 'artifact_version_id': old.id,
                                     'artifact_content_hash': old.content_hash})))
        db.commit()
    repaired = medallion.remediate_medallion_artifact(db, project.id, old.id, use_ai=False, reviewer='architect')
    # A repair candidate alone cannot renew an exhausted budget.
    still_blocked = master_orchestration.execute_master_plan(db, project.id, plan['plan_id'])
    assert still_blocked['status'] == 'FAILED' and len(calls) == 3
    assert not db.query(CanonicalRecord).filter_by(record_type='MASTER_STAGE_RETRY_RENEWAL').count()
    medallion.review_medallion_artifact(db, project.id, repaired['artifact_version_id'],
                                      status='APPROVED', reviewer='architect')
    monkeypatch.setattr(master_orchestration, '_run_stage', original_runner)
    _mock_successful_chain(monkeypatch, calls)
    executed_sql = []
    monkeypatch.setattr(databricks_client, 'execute_sql', lambda sql, **kw: executed_sql.append(sql))
    monkeypatch.setattr(deployment, 'databricks_workspace_identity', lambda: 'qa-workspace')
    def execute_dev(*args, **kwargs):
        calls.append('DEV')
        deployment_result = medallion.deploy_medallion_dev(db, project.id)
        return {**deployment_result, 'status': 'COMPLETED' if deployment_result['status'] == 'PASSED' else 'FAILED'}
    monkeypatch.setattr(master_orchestration.prompt_orchestration, 'execute_prompt_plan', execute_dev)
    result = master_orchestration.execute_master_plan(db, project.id, plan['plan_id'])
    assert result['status'] == 'COMPLETED', result.get('error')
    checkpoint = result['stages']['DEV_MIGRATION']
    assert checkpoint['attempts'] == 1 and checkpoint['total_attempts'] == 4
    assert checkpoint['retry_renewals'] == 1
    assert result['authorization'] == authorization
    assert checkpoint['retry_evidence'][item['target_fqn']]['artifact_version_id'] == repaired['artifact_version_id']
    assert executed_sql == [db.get(MigrationStageArtifactVersion, repaired['artifact_version_id']).content]
    logs = db.query(MigrationDeployment).filter_by(project_id=project.id, status='PASSED').all()
    assert any(json.loads(log.payload_json).get('artifact_version_id') == repaired['artifact_version_id'] for log in logs)
    audit = db.query(CanonicalRecord).filter_by(project_id=project.id, record_type='MASTER_STAGE_RETRY_RENEWAL').one()
    evidence = json.loads(audit.payload_json)
    assert evidence['previous_checkpoint']['attempts'] == 3
    assert evidence['corrections'][item['target_fqn']]['previous'].get('artifact_version_id') == old.id
    assert len(calls) == 10  # three failed DEV runs, then DEV and all three promotion pairs


def test_new_version_with_identical_sql_does_not_renew_retries(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    item, old = _procedure_artifact(db, project, invalid=False)
    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)
    calls = []
    _fail_dev_three_times(db, project, plan, monkeypatch, calls)
    artifact = db.get(MigrationStageArtifact, old.artifact_id)
    new = MigrationStageArtifactVersion(id=uid('MSV'), project_id=project.id, artifact_id=old.artifact_id,
        node_id=old.node_id, version=old.version + 1, content=old.content, content_hash=sha(old.content),
        validation_status='PASSED', executable=True, review_status='PENDING_REVIEW')
    db.add(new)
    artifact.current_version = new.version
    db.commit()
    medallion.review_medallion_artifact(db, project.id, new.id, status='APPROVED', reviewer='architect')
    result = master_orchestration.execute_master_plan(db, project.id, plan['plan_id'])
    assert result['status'] == 'FAILED' and 'maximum of 3' in result['error']
    assert len(calls) == 3
    assert not db.query(CanonicalRecord).filter_by(record_type='MASTER_STAGE_RETRY_RENEWAL').count()


def test_internal_artifact_changes_do_not_refresh_the_next_resume_budget(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    item, old = _procedure_artifact(db, project, invalid=False)
    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)
    calls = []
    def generate_and_fail(*args, **kwargs):
        calls.append('DEV')
        old.content = old.content.replace(f'SELECT {len(calls)} ', f'SELECT {len(calls) + 1} ')
        old.content_hash = sha(old.content)
        db.commit()
        return {'status': 'FAILED', 'error': 'Deployment failed after in-stage remediation'}
    _fail_dev_three_times(db, project, plan, monkeypatch, calls, stage_runner=generate_and_fail)
    blocked = master_orchestration.execute_master_plan(db, project.id, plan['plan_id'])
    assert 'maximum of 3' in blocked['error'] and len(calls) == 3


def test_master_plan_requires_explicit_full_production_scope(db):
    project = _project(db)

    result = master_orchestration.generate_master_plan(
        db, project.id, "Migrate MigrationDemo from SQL Server to DEV Databricks"
    )

    assert result["status"] == "NEEDS_USER_INPUT"
    assert "Production scope must be explicit" in result["blockers"][0]


def test_master_plan_contains_one_authorization_and_four_checkpoints(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)

    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)

    assert plan["status"] == "PENDING_APPROVAL"
    assert plan["scope"]["single_prompt"] is True
    assert plan["scope"]["environments"] == ["DEV", "TEST", "UAT", "PROD"]
    assert plan["authorization"] is None
    assert list(plan["checkpoints"]) == [
        "DEV_MIGRATION", "TEST_PROMOTION", "UAT_PROMOTION", "PROD_PROMOTION"
    ]
    assert db.query(CanonicalRecord).filter_by(
        project_id=project.id, record_type="MASTER_MIGRATION_PLAN"
    ).count() == 1


def test_master_execution_requires_workflow_and_prod_authorization(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)

    with pytest.raises(PermissionError, match="complete workflow"):
        master_orchestration.execute_master_plan(db, project.id, plan["plan_id"])
    with pytest.raises(PermissionError, match="PROD authorization"):
        master_orchestration.execute_master_plan(
            db, project.id, plan["plan_id"], workflow_authorized=True
        )


def test_master_execution_runs_dev_test_uat_prod_in_order(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    calls = []
    _mock_successful_chain(monkeypatch, calls)
    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)

    result = master_orchestration.execute_master_plan(
        db,
        project.id,
        plan["plan_id"],
        actor="release-admin",
        workflow_authorized=True,
        production_authorized=True,
    )

    assert result["status"] == "COMPLETED", result.get("error")
    assert calls == [
        "DEV", "PLAN_TEST", "TEST", "PLAN_UAT", "UAT", "PLAN_PROD", "PROD"
    ]
    assert all(stage["status"] == "PASSED" for stage in result["stages"].values())
    assert result["authorization"]["authorized_by"] == "release-admin"
    assert master_orchestration.get_master_plan(db, project.id)["status"] == "COMPLETED"


def test_master_resume_reuses_passed_checkpoints(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    calls = []
    monkeypatch.setattr(
        master_orchestration.prompt_orchestration,
        "execute_prompt_plan",
        lambda *a, **kw: calls.append("DEV") or {"status": "COMPLETED"},
    )
    monkeypatch.setattr(
        master_orchestration.prompt_promotion,
        "generate_promotion_plan",
        lambda *a, **kw: {
            "status": "PENDING_APPROVAL",
            "plan_id": "PLAN_" + (kw.get("prompt") or a[2]).rsplit(" ", 1)[-1],
        },
    )
    uat_attempts = {"count": 0}

    def execute(*args, **kwargs):
        target = kwargs["plan_id"].replace("PLAN_", "")
        calls.append(target)
        if target == "UAT":
            uat_attempts["count"] += 1
            if uat_attempts["count"] == 1:
                return {
                    "status": "FAILED", "error": "UAT reconciliation mismatch",
                    "errors": [{"recommended_action": "Correct UAT reconciliation and resume."}],
                }
        return {"status": "COMPLETED"}

    monkeypatch.setattr(
        master_orchestration.prompt_promotion, "execute_promotion_plan", execute
    )
    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)

    first = master_orchestration.execute_master_plan(
        db, project.id, plan["plan_id"], workflow_authorized=True, production_authorized=True
    )
    resumed = master_orchestration.execute_master_plan(db, project.id, plan["plan_id"])

    assert first["status"] == "FAILED"
    assert first["failed_stage"] == "UAT_PROMOTION"
    assert resumed["status"] == "COMPLETED"
    assert resumed["stages"]["DEV_MIGRATION"]["checkpoint_reused"] is True
    assert resumed["stages"]["TEST_PROMOTION"]["checkpoint_reused"] is True
    assert calls == ["DEV", "TEST", "UAT", "UAT", "PROD"]


def test_master_migration_api_workflow(client, auth_headers, db, monkeypatch):
    project = client.post(
        "/api/projects", headers=auth_headers, json={"name": "Release 6 API"}
    ).json()
    add_source(db, project["id"], "SQL Server", "localhost", "MigrationDemo")
    _mock_dev_plan(monkeypatch)
    calls = []
    _mock_successful_chain(monkeypatch, calls)

    planned = client.post(
        f"/api/projects/{project['id']}/master-migration/plan",
        headers=auth_headers,
        json={"prompt": MASTER_PROMPT},
    )
    assert planned.status_code == 200, planned.text

    executed = client.post(
        f"/api/projects/{project['id']}/master-migration/execute",
        headers=auth_headers,
        json={
            "plan_id": planned.json()["plan_id"],
            "workflow_authorized": True,
            "production_authorized": True,
        },
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "COMPLETED"

    latest = client.get(
        f"/api/projects/{project['id']}/master-migration/latest",
        headers=auth_headers,
    )
    assert latest.status_code == 200
    assert latest.json()["plan"]["status"] == "COMPLETED"
    assert latest.json()["execution"]["status"] == "COMPLETED"


def test_promotion_exhausted_retries_can_renew_when_resumed(db, monkeypatch):
    project = _project(db)
    _mock_dev_plan(monkeypatch)
    calls = []
    _mock_successful_chain(monkeypatch, calls)

    plan = master_orchestration.generate_master_plan(db, project.id, MASTER_PROMPT)

    # Simulate 3 failures in TEST_PROMOTION
    attempt_count = 0
    def failing_promotion(db, pid, plan_id, **kw):
        nonlocal attempt_count
        attempt_count += 1
        calls.append("TEST_FAIL")
        return {
            "status": "FAILED",
            "failed_stage": "DEPLOYMENT",
            "error": "Table dependency failure",
            "stages": {
                "PREFLIGHT": {"status": "PASSED", "source_deployment_run_id": "MDR_DEV_1"},
                "DEPLOYMENT": {"status": "FAILED", "failed_target": "`migration_test`.`silver`.`fn_CalculateOrderAmount`"},
            },
        }

    monkeypatch.setattr(master_orchestration.prompt_promotion, "execute_promotion_plan", failing_promotion)
    monkeypatch.setattr(master_orchestration.deployment, "_latest_successful_medallion_run", lambda *a: ("MDR_DEV_1", []))

    for i in range(3):
        res = master_orchestration.execute_master_plan(
            db, project.id, plan["plan_id"],
            workflow_authorized=i == 0, production_authorized=i == 0,
        )
        assert res["status"] == "FAILED"

    # Now simulate fix (subsequent promotion attempt succeeds)
    def successful_promotion(db, pid, plan_id, **kw):
        calls.append("TEST_SUCCESS")
        return {"status": "COMPLETED", "stages": {}}

    monkeypatch.setattr(master_orchestration.prompt_promotion, "execute_promotion_plan", successful_promotion)

    resumed = master_orchestration.execute_master_plan(db, project.id, plan["plan_id"])
    assert resumed["status"] == "COMPLETED"
    test_cp = resumed["stages"]["TEST_PROMOTION"]
    assert test_cp["retry_renewals"] == 1
    assert test_cp["total_attempts"] == 4
