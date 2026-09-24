from sqlalchemy import select
from app.services.engine import ensure_project, add_source, ingest_snapshot, classify_project, create_mappings, generate_artifact, uid
from app.services import deployment
from app.models.entities import MigrationArtifactVersion, MigrationIssue, MigrationReview, MigrationRun, MigrationQualityGate
from app.models.canonical import MigrationDeployment


def seed_approved(db, name='Deploy P'):
    p=ensure_project(db,name); s=add_source(db,p.id,'src','server','DB1')
    snap={'database':'DB1','objects':[{'schema':'sales','name':'Orders','type':'TABLE','columns':[{'name':'OrderId','type':'int','nullable':False}]}]}
    ingest_snapshot(db,p.id,s.id,snap); classify_project(db,p.id); create_mappings(db,p.id,'DEV','cat_dev')
    obj=db.scalar(select(deployment.MigrationObject).where(deployment.MigrationObject.project_id==p.id))
    av=generate_artifact(db,p.id,obj.id)
    db.add(MigrationReview(id=uid('REV'),project_id=p.id,artifact_version_id=av.id,review_type='ARCHITECT_REVIEW',status='APPROVED',reviewer='tester'))
    db.commit(); return p,obj,av


def test_dev_precheck_requires_current_approval(db):
    p=ensure_project(db,'No approval'); s=add_source(db,p.id,'src','server','DB1')
    ingest_snapshot(db,p.id,s.id,{'database':'DB1','objects':[{'schema':'dbo','name':'T','type':'TABLE','columns':[{'name':'Id','type':'int'}]}]})
    classify_project(db,p.id); create_mappings(db,p.id,'DEV','cat_dev')
    obj=db.scalar(select(deployment.MigrationObject).where(deployment.MigrationObject.project_id==p.id)); generate_artifact(db,p.id,obj.id)
    r=deployment.dev_precheck(db,p.id,test_databricks=False)
    assert not r['eligible'] and any(x['code']=='APPROVAL' for x in r['blockers'])


def test_dev_deployment_records_evidence_and_can_gate(db,monkeypatch):
    p,obj,av=seed_approved(db)
    monkeypatch.setattr(deployment,'dev_precheck',lambda *a,**k:{'eligible':True,'blockers':[]})
    monkeypatch.setattr(deployment,'execute_sql',lambda *a,**k:[])
    monkeypatch.setattr(deployment,'_apply_table_schema_policy',lambda *a,**k:{'action':'CREATE','schema_status':'MISSING'})
    monkeypatch.setattr(deployment,'_safe_execute_artifact',lambda content,**kwargs:None)
    monkeypatch.setattr(deployment,'load_bronze_table',lambda *a,**k:{'status':'PASSED','rows':7})
    r=deployment.deploy_dev(db,p.id)
    assert r['status']=='PASSED'
    status=deployment.deployment_status(db,p.id)
    assert status['status']=='PASSED' and status['passed']==1
    # add passed reconciliation evidence then gate must pass
    from app.models.canonical import MigrationReconciliation
    db.add(MigrationReconciliation(id=uid('REC'),project_id=p.id,environment='DEV',status='PASSED',payload_json='{}'));db.commit()
    g=deployment.evaluate_dev_gate(db,p.id)
    assert g['status']=='PASSED'


def test_failed_run_preserves_state_for_resume(db,monkeypatch):
    p,obj,av=seed_approved(db,'Resume P')
    monkeypatch.setattr(deployment,'dev_precheck',lambda *a,**k:{'eligible':True,'blockers':[]})
    monkeypatch.setattr(deployment,'execute_sql',lambda *a,**k:[])
    monkeypatch.setattr(deployment,'_apply_table_schema_policy',lambda *a,**k:{'action':'CREATE','schema_status':'MISSING'})
    monkeypatch.setattr(deployment,'_safe_execute_artifact',lambda content,**kwargs:(_ for _ in ()).throw(RuntimeError('simulated dbx failure')))
    r=deployment.deploy_dev(db,p.id)
    assert r['status']=='FAILED' and r['run_id']
    failed=deployment.latest_failed_dev_run(db,p.id)
    assert failed and failed.id==r['run_id'] and failed.checkpoint=='sales.Orders'


def test_destructive_artifact_requires_explicit_approval(monkeypatch):
    executed=[]
    monkeypatch.setattr(deployment,'execute_sql',lambda sql,**kwargs:executed.append(sql))

    try:
        deployment._safe_execute_artifact('DELETE FROM target_table')
        assert False, 'destructive SQL must be blocked without approval'
    except RuntimeError as exc:
        assert 'explicit governed replacement' in str(exc)
    assert executed == []

    deployment._safe_execute_artifact('DELETE FROM target_table', allow_destructive=True)
    assert executed == ['DELETE FROM target_table']


def test_target_ownership_is_scoped_to_databricks_workspace(db, monkeypatch):
    current, obj, _ = seed_approved(db, 'Current workspace project')
    other = ensure_project(db, 'Other workspace project')
    mapping = deployment._mapping(db, current.id, obj.id, 'DEV')
    monkeypatch.setattr(deployment, 'databricks_workspace_identity', lambda: 'new-workspace.cloud.databricks.com')

    # A legacy row has no reliable workspace identity and remains audit-only.
    db.add(MigrationDeployment(id=uid('DPL'), project_id=other.id, object_id=None,
                               environment='DEV', status='PASSED',
                               payload_json=deployment._json({'target_fqn': mapping.target_fqn})))
    # An identical target name in a different physical workspace is not a collision.
    db.add(MigrationDeployment(id=uid('DPL'), project_id=other.id, object_id=None,
                               environment='DEV', status='PASSED',
                               payload_json=deployment._json({
                                   'target_fqn': mapping.target_fqn,
                                   'databricks_workspace': 'old-workspace.cloud.databricks.com',
                               })))
    db.commit()
    assert deployment._target_owner_collision(db, current.id, mapping.target_fqn) is None

    same_workspace = MigrationDeployment(id=uid('DPL'), project_id=other.id, object_id=None,
                                         environment='DEV', status='PASSED',
                                         payload_json=deployment._json({
                                             'target_fqn': mapping.target_fqn,
                                             'databricks_workspace': 'new-workspace.cloud.databricks.com',
                                         }))
    db.add(same_workspace); db.commit()
    assert deployment._target_owner_collision(db, current.id, mapping.target_fqn).id == same_workspace.id


def test_precheck_resolves_legacy_ownership_blocker(db, monkeypatch):
    current, obj, _ = seed_approved(db, 'Legacy ownership issue')
    monkeypatch.setattr(deployment, 'databricks_workspace_identity', lambda: 'new-workspace.cloud.databricks.com')
    issue = MigrationIssue(
        id=uid('ISS'), project_id=current.id, object_id=obj.id,
        issue_type='DEPLOYMENT', severity='BLOCKER', status='OPEN',
        message='DEV deployment failed at sales.Orders',
        technical_details=deployment._json({
            'error': 'Target ownership collision: `cat_dev`.`bronze`.`Orders` is already owned by project old',
        }),
    )
    db.add(issue); db.commit()

    deployment._resolve_stale_ownership_issues(db, current.id)

    db.refresh(issue)
    assert issue.status == 'RESOLVED'
