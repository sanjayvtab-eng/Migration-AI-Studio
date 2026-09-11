from sqlalchemy import select
from app.services.engine import ensure_project, add_source, ingest_snapshot, classify_project, create_mappings, generate_artifact
from app.services.ai_remediation import analyze_remediation, accept_remediation, remediation_plan, remediate_one_artifact, run_remediation_batch, validate_candidate_content
from app.models.entities import MigrationObject, MigrationArtifact, MigrationArtifactVersion, MigrationReview, MigrationMapping, MigrationIssue
from app.services.medallion import build_medallion_plan, generate_medallion_artifacts, list_medallion_artifacts


def _seed(db):
    p=ensure_project(db,'AI remediation')
    s=add_source(db,p.id,'src','server','DB1')
    snapshot={'database':'DB1','objects':[
        {'schema':'dbo','name':'OrderDetail','type':'TABLE','columns':[{'name':'OrderID','type':'int'},{'name':'UnitPrice','type':'decimal','precision':18,'scale':2},{'name':'Quantity','type':'int'}]},
        {'schema':'dbo','name':'fn_OrderTotal','type':'FUNCTION',
         'definition':'''CREATE FUNCTION dbo.fn_OrderTotal(@OrderID int) RETURNS decimal(18,2) AS BEGIN
DECLARE @Total decimal(18,2);
SELECT @Total = SUM(UnitPrice * Quantity) FROM dbo.OrderDetail WHERE OrderID=@OrderID;
RETURN ISNULL(@Total,0);
END''',
         'parameters':[{'name':'@OrderID','ordinal':1,'type':'int'}]},
    ]}
    ingest_snapshot(db,p.id,s.id,snapshot); classify_project(db,p.id); create_mappings(db,p.id,'DEV','migration_dev')
    objs={o.object_name:o for o in db.scalars(select(MigrationObject).where(MigrationObject.project_id==p.id)).all()}
    generate_artifact(db,p.id,objs['OrderDetail'].id)
    initial=generate_artifact(db,p.id,objs['fn_OrderTotal'].id)
    assert '-- NON_EXECUTABLE:' in initial.content
    return p,objs['fn_OrderTotal']


def test_deterministic_first_remediation_creates_valid_candidate(db):
    p,obj=_seed(db)
    r=analyze_remediation(db,p.id,obj.id,'DEV',use_ai=True)
    assert r['provider']=='DETERMINISTIC_REMEDIATION'
    assert r['deterministic_validation']['valid'] is True
    assert 'CREATE OR REPLACE FUNCTION' in r['generated_candidate']
    assert '`migration_dev`.`bronze`.`OrderDetail`' in r['generated_candidate']
    assert r['approval_required'] is True
    assert r['auto_deployed'] is False


def test_accept_remediation_creates_new_unapproved_version(db):
    p,obj=_seed(db)
    r=analyze_remediation(db,p.id,obj.id,'DEV',use_ai=True)
    av=accept_remediation(db,p.id,obj.id,r['ai_run_id'],'architect')
    art=db.scalar(select(MigrationArtifact).where(MigrationArtifact.project_id==p.id,MigrationArtifact.object_id==obj.id))
    assert art.current_version==2
    assert av.version==2
    assert av.ai_provider=='DETERMINISTIC_REMEDIATION'
    review=db.scalar(select(MigrationReview).where(MigrationReview.artifact_version_id==av.id,MigrationReview.status=='APPROVED'))
    assert review is None


def test_batch_remediation_creates_validated_version_but_never_approves(db):
    p,obj=_seed(db)
    plan=remediation_plan(db,p.id,'DEV')
    assert plan['eligible']==1
    result=run_remediation_batch(db,p.id,environment='DEV',use_ai=False,apply_valid_candidates=True,reviewer='architect')
    assert result['status']=='PASSED'
    assert result['ready_for_review']==1
    assert result['auto_approved'] is False
    assert result['auto_deployed'] is False
    art=db.scalar(select(MigrationArtifact).where(MigrationArtifact.project_id==p.id,MigrationArtifact.object_id==obj.id))
    assert art.current_version==2
    av=db.scalar(select(MigrationArtifactVersion).where(MigrationArtifactVersion.artifact_id==art.id,MigrationArtifactVersion.version==2))
    assert av.generator_version=='enterprise-2.0-ai-repair-loop'
    assert db.scalar(select(MigrationReview).where(MigrationReview.artifact_version_id==av.id)) is None


def test_single_artifact_repair_creates_validated_unapproved_version(db):
    p,obj=_seed(db)
    result=remediate_one_artifact(
        db,p.id,obj.id,environment='DEV',use_ai=False,reviewer='architect'
    )
    assert result['status']=='READY_FOR_REVIEW'
    assert result['artifact_version']==2
    assert result['static_validation']['status']=='PASSED'
    assert result['approval_required'] is True
    assert result['auto_approved'] is False
    assert result['auto_deployed'] is False
    assert db.scalar(select(MigrationReview).where(
        MigrationReview.artifact_version_id==result['artifact_version_id'],
        MigrationReview.status=='APPROVED',
    )) is None


def test_confirmed_medallion_blocker_runs_repair_when_legacy_projection_has_no_blocker(db):
    p,obj=_seed(db)
    art=db.scalar(select(MigrationArtifact).where(
        MigrationArtifact.project_id==p.id,MigrationArtifact.object_id==obj.id
    ))
    current=db.scalar(select(MigrationArtifactVersion).where(
        MigrationArtifactVersion.artifact_id==art.id,
        MigrationArtifactVersion.version==art.current_version,
    ))
    current.content='CREATE OR REPLACE FUNCTION `migration_dev`.`silver`.`fn_OrderTotal`(`OrderID` INT) RETURNS DECIMAL(18,2) LANGUAGE SQL RETURN 0;'
    db.commit()
    assert not remediation_plan(db,p.id,'DEV')['items']

    result=remediate_one_artifact(
        db,p.id,obj.id,environment='DEV',use_ai=False,reviewer='architect',
        confirmed_blocker='MEDALLION_STAGE_VALIDATION:MSV_test',
    )
    assert result['status']=='READY_FOR_REVIEW'
    assert result['artifact_version']==2
    assert result['auto_approved'] is False
    assert result['auto_deployed'] is False


def test_medallion_regeneration_uses_latest_approved_repaired_routine(db):
    p,obj=_seed(db)
    build_medallion_plan(db,p.id,environment='DEV',catalog='migration_dev')
    first=generate_medallion_artifacts(db,p.id,environment='DEV')
    first_row=next(x for x in first['artifacts'] if x['target_fqn'].endswith('`fn_OrderTotal`'))
    assert first_row['version']==1
    assert first_row['validation_status']=='FAILED'

    repaired=remediate_one_artifact(
        db,p.id,obj.id,environment='DEV',use_ai=False,reviewer='architect'
    )
    db.add(MigrationReview(
        id='REV_REPAIRED_ROUTINE',project_id=p.id,
        artifact_version_id=repaired['artifact_version_id'],review_type='ARCHITECT_REVIEW',
        status='APPROVED',reviewer='architect',comments='Approved repaired routine',
    ))
    db.commit()

    second=generate_medallion_artifacts(db,p.id,environment='DEV')
    second_row=next(x for x in second['artifacts'] if x['target_fqn'].endswith('`fn_OrderTotal`'))
    assert second_row['version']==2
    assert second_row['validation_status']=='PASSED'
    assert second_row['review_status']=='PENDING_REVIEW'
    listed=next(x for x in list_medallion_artifacts(db,p.id,environment='DEV') if x['target_fqn'].endswith('`fn_OrderTotal`'))
    assert listed['validation']['source_artifact_version_id']==repaired['artifact_version_id']
    assert listed['validation']['source_artifact_version']==2


def test_candidate_guard_rejects_destructive_and_source_references(db):
    p,obj=_seed(db)
    mapping=db.scalar(select(MigrationMapping).where(MigrationMapping.project_id==p.id,MigrationMapping.object_id==obj.id))
    candidate=f"CREATE OR REPLACE FUNCTION {mapping.target_fqn}(`OrderID` INT) RETURNS INT LANGUAGE SQL RETURN (SELECT COUNT(*) FROM dbo.OrderDetail); DROP TABLE x"
    validation=validate_candidate_content(obj,mapping,candidate)
    assert validation['valid'] is False
    assert any('destructive' in x.lower() for x in validation['errors'])
    assert any('unmapped sql server' in x.lower() for x in validation['errors'])


def test_provider_status_and_plan_endpoints(client,auth_headers):
    p=client.post('/api/projects',json={'name':'AI plan endpoint'},headers=auth_headers).json()
    status=client.get('/api/ai/provider-status',headers=auth_headers)
    assert status.status_code==200
    assert status.json()['candidate_auto_approval'] is False
    plan=client.get(f"/api/projects/{p['id']}/remediation/plan",headers=auth_headers)
    assert plan.status_code==200
    assert plan.json()['project_id']==p['id']


def test_review_endpoint_enriches_and_deduplicates(client,auth_headers):
    p=client.post('/api/projects',json={'name':'Review UI'},headers=auth_headers).json()
    pid=p['id']
    # seed via snapshot route
    src=client.post(f'/api/projects/{pid}/sources',json={'profile_name':'s','server_name':'x','database_name':'DB1'},headers=auth_headers).json()
    snapshot={'database':'DB1','objects':[{'schema':'dbo','name':'Customer','type':'TABLE','columns':[{'name':'ID','type':'int'}]}]}
    client.post(f'/api/projects/{pid}/discovery/snapshot',json={'source_id':src['id'],'snapshot':snapshot},headers=auth_headers)
    client.post(f'/api/projects/{pid}/classification',headers=auth_headers)
    client.post(f'/api/projects/{pid}/mappings',json={'environment':'DEV','catalog':'migration_dev'},headers=auth_headers)
    obj=client.get(f'/api/projects/{pid}/inventory',headers=auth_headers).json()[0]
    av=client.post(f'/api/projects/{pid}/artifacts',json={'object_id':obj['id'],'environment':'DEV'},headers=auth_headers).json()
    validated=client.post(f"/api/projects/{pid}/validate/{obj['id']}?environment=DEV",headers=auth_headers)
    assert validated.status_code==200 and validated.json()['valid'] is True
    payload={'artifact_version_id':av['artifact_version_id'],'review_type':'ARCHITECT_REVIEW','status':'APPROVED','reviewer':'admin','comments':'ok'}
    r1=client.post(f'/api/projects/{pid}/reviews',json=payload,headers=auth_headers).json()
    r2=client.post(f'/api/projects/{pid}/reviews',json=payload,headers=auth_headers).json()
    assert r1['duplicate_prevented'] is False
    assert r2['duplicate_prevented'] is True
    rows=client.get(f'/api/projects/{pid}/reviews',headers=auth_headers).json()
    assert len(rows)==1
    assert rows[0]['object_name']=='Customer'
    assert rows[0]['schema']=='dbo'
    assert rows[0]['version']==1


def _seed_table_for_runtime_issue(db):
    p=ensure_project(db,'Runtime remediation')
    s=add_source(db,p.id,'src','server','DB1')
    snapshot={'database':'DB1','objects':[
        {'schema':'dbo','name':'Customer','type':'TABLE','columns':[
            {'name':'CustomerId','type':'int','nullable':False},
            {'name':'VersionBytes','type':'rowversion','nullable':False},
        ]}
    ]}
    ingest_snapshot(db,p.id,s.id,snapshot); classify_project(db,p.id); create_mappings(db,p.id,'DEV','migration_dev')
    obj=db.scalar(select(MigrationObject).where(MigrationObject.project_id==p.id))
    generate_artifact(db,p.id,obj.id)
    return p,obj


def test_deployment_binary_transport_issue_routes_to_compatibility_engine(db):
    import json
    p,obj=_seed_table_for_runtime_issue(db)
    issue=MigrationIssue(
        id='ISS_RUNTIME_BINARY', project_id=p.id, object_id=obj.id, issue_type='DEPLOYMENT', severity='BLOCKER',
        message='DEV deployment failed at dbo.Customer', status='OPEN',
        technical_details=json.dumps({
            'run_id':'RUN_FAILED', 'failure_stage':'BRONZE_LOAD', 'error_category':'LOAD',
            'error_code':'BINARY_TRANSPORT_INVALID_HEX', 'deterministic_remediation_available':True,
            'recommended_action':'Use canonical binary transport adapter',
        }),
    )
    db.add(issue); db.commit()
    plan=remediation_plan(db,p.id,'DEV')
    assert plan['eligible']==1
    item=plan['items'][0]
    assert item['route']=='COMPATIBILITY_ENGINE'
    assert item['effective_category']=='LOAD'
    assert 'BINARY_TRANSPORT_INVALID_HEX' in ' '.join(item['reasons'])

    result=run_remediation_batch(db,p.id,environment='DEV',use_ai=True,apply_valid_candidates=True,reviewer='architect')
    assert result['status']=='PASSED'
    assert result['retry_ready']==1
    assert result['results'][0]['status']=='RETRY_READY'
    assert result['results'][0]['provider']=='DETERMINISTIC_COMPATIBILITY_ENGINE'
    assert result['auto_deployed'] is False


def test_deployment_databricks_syntax_issue_can_route_to_ai(db):
    import json
    p,obj=_seed(db)
    issue=MigrationIssue(
        id='ISS_RUNTIME_SYNTAX', project_id=p.id, object_id=obj.id, issue_type='DEPLOYMENT', severity='BLOCKER',
        message='DEV deployment syntax failed', status='OPEN',
        technical_details=json.dumps({
            'run_id':'RUN_FAILED_2', 'failure_stage':'DEPLOY_DDL', 'error_category':'DATABRICKS_SYNTAX',
            'error_code':'DATABRICKS_SYNTAX', 'deterministic_remediation_available':False,
        }),
    )
    db.add(issue); db.commit()
    plan=remediation_plan(db,p.id,'DEV')
    match=[x for x in plan['items'] if x['object_id']==obj.id][0]
    assert match['route']=='DETERMINISTIC_THEN_AI'
    assert match['eligible'] is True
    assert match['effective_category']=='DATABRICKS_SYNTAX'


def test_legacy_210_binary_deployment_issue_is_reclassified_to_compatibility_engine(db):
    import json
    p,obj=_seed_table_for_runtime_issue(db)
    issue=MigrationIssue(
        id='ISS_LEGACY_BINARY', project_id=p.id, object_id=obj.id, issue_type='DEPLOYMENT', severity='BLOCKER',
        message='DEV deployment failed at dbo.Customer', status='OPEN',
        technical_details=json.dumps({
            'run_id':'RUN_210', 'failure_stage':'BRONZE_LOAD', 'error_category':'CONVERSION',
            'error_code':'UNCLASSIFIED_EXECUTION_ERROR', 'deterministic_remediation_available':False,
            'error':'Binary transport value contains non-hexadecimal characters',
        }),
    )
    db.add(issue); db.commit()
    plan=remediation_plan(db,p.id,'DEV')
    item=plan['items'][0]
    assert item['route']=='COMPATIBILITY_ENGINE'
    assert item['effective_category']=='LOAD'
