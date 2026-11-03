import hashlib
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api import routes
from app.core.security import hash_password, create_access_token
from app.models.entities import (User, MigrationProject, MigrationMedallionNode,
    MigrationDatabricksConfiguration, MigrationReview)
from app.models.canonical import MigrationDeployment, MigrationReconciliation
from app.services import medallion, deployment, databricks_client, watermark_service
from app.services.sql_preflight import bind_physical_columns, validate_databricks_sql
from app.services.type_compatibility import normalize_source_value, transport_plan

spec = importlib.util.spec_from_file_location('fixed_agent', Path(__file__).parents[2]/'scripts/local_connector.py')
agent = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent)


def test_direct_password_replacement_and_fresh_admin_are_rejected(client, auth_headers):
    for email in ['admin', 'new@example.test']:
        response = client.post('/api/register/set-password',json={'email':email,'password':'New-Synthetic-Password-123!'})
        assert response.status_code == 400
    assert client.post('/api/login',json={'username':'admin','password':'A-Strong-Test-Password-123!'}).status_code == 200


def test_password_proof_is_bound_single_use_preserves_role_and_revokes_sessions(client, db):
    email='engineer@example.test'
    db.add(User(id='U',username=email,email=email,role='ENGINEER',password_hash=hash_password('Old-Password-123!'),
        otp=routes._otp_digest(email,'123456'),otp_expires_at=datetime.utcnow()+timedelta(minutes=5)))
    db.commit()
    old=create_access_token(email,'ENGINEER')
    proof=client.post('/api/register/verify-otp',json={'email':email,'otp':'123456'}).json()['verification_token']
    assert client.post('/api/register/verify-otp',json={'email':email,'otp':'123456'}).status_code==400
    body={'email':email,'password':'Updated-Synthetic-123!','verification_token':proof}
    assert client.post('/api/register/set-password',json={**body,'email':'different@example.test'}).status_code==400
    response=client.post('/api/register/set-password',json=body)
    assert response.status_code==200 and response.json()['role']=='ENGINEER'
    assert client.post('/api/register/set-password',json=body).status_code==400
    assert client.get('/api/projects',headers={'Authorization':'Bearer '+old}).status_code==401
    assert client.get('/api/projects',headers={'Authorization':'Bearer '+response.json()['access_token']}).status_code==200


def test_failed_email_delivery_does_not_expose_code_or_assign_admin_email(client, auth_headers, db, monkeypatch):
    from app.services import email_service
    sender=AsyncMock(return_value=(False,'delivery unavailable'))
    monkeypatch.setattr(email_service,'send_otp_email',sender)
    unknown=client.post('/api/auth/forgot-password',json={'email':'stranger@example.test'})
    assert unknown.status_code==200 and not sender.called
    user=db.scalar(select(User).where(User.username=='admin'));user.email='owner@example.test';db.commit()
    result=client.post('/api/auth/forgot-password',json={'email':'owner@example.test'})
    code=sender.call_args.args[1]
    assert result.status_code==200 and code not in result.text
    db.refresh(user);assert user.otp is None and user.email=='owner@example.test'


def test_cross_project_viewer_and_anonymous_schedule_are_denied(client,auth_headers,db,monkeypatch):
    pid=client.post('/api/projects',headers=auth_headers,json={'name':'Private'}).json()['id']
    db.add(User(id='viewer',username='viewer',password_hash=hash_password('Viewer-Test-123!'),role='VIEWER'))
    db.commit();viewer={'Authorization':'Bearer '+create_access_token('viewer','VIEWER')}
    assert client.get(f'/api/projects/{pid}/sources',headers=viewer).status_code==404
    assert client.post(f'/api/projects/{pid}/sources',headers=viewer,json={'profile_name':'x','server_name':'x','database_name':'x'}).status_code==404
    target=AsyncMock();monkeypatch.setattr(watermark_service,'run_incremental_sync_for_project',target)
    assert client.get(f'/api/projects/{pid}/schedule').status_code==401
    assert client.put(f'/api/projects/{pid}/schedule',json={}).status_code==401
    assert client.post(f'/api/projects/{pid}/schedule/trigger-now').status_code==401
    assert not target.called
    assert client.post(f'/api/projects/{pid}/quality-gates',headers=auth_headers,json={'environment':'PROD','status':'PASSED'}).status_code==403


def test_auth_uses_current_role_and_rejects_disabled_user(client,auth_headers,db):
    user=db.scalar(select(User).where(User.username=='admin'));user.role='VIEWER';db.commit()
    assert client.post('/api/projects',headers=auth_headers,json={'name':'Denied'}).status_code==403
    user.locked=True;db.commit()
    assert client.get('/api/projects',headers=auth_headers).status_code==401


def test_production_route_requires_exact_release_and_confirmation(client,auth_headers,monkeypatch):
    from unittest.mock import Mock
    pid=client.post('/api/projects',headers=auth_headers,json={'name':'Production confirmation'}).json()['id']
    promoter=Mock(return_value={'status':'PASSED'})
    monkeypatch.setattr(routes,'promote_medallion_to_prod',promoter)
    monkeypatch.setattr(deployment,'_latest_successful_medallion_run',lambda *a,**k:('UAT_RELEASE',[]))
    path=f'/api/projects/{pid}/promotions/prod/deploy'
    assert client.post(path,headers=auth_headers).status_code==422
    assert client.post(path,headers=auth_headers,json={'confirmation_text':'yes','release_id':'UAT_RELEASE'}).status_code==409
    assert client.post(path,headers=auth_headers,json={'confirmation_text':'PROMOTE TO PROD','release_id':'stale'}).status_code==409
    promoter.assert_not_called()
    assert client.post(path,headers=auth_headers,json={'confirmation_text':'PROMOTE TO PROD','release_id':'UAT_RELEASE'}).status_code==200
    assert promoter.call_count==1


def test_review_uses_authenticated_actor(client,auth_headers,db):
    from tests.test_review_governance import _seed_artifact
    pid,obj,artifact=_seed_artifact(client,auth_headers)
    client.post(f'/api/projects/{pid}/validate/{obj["id"]}',headers=auth_headers)
    response=client.post(f'/api/projects/{pid}/reviews',headers=auth_headers,
        json={'artifact_version_id':artifact['artifact_version_id'],'status':'APPROVED','reviewer':'Someone Else'})
    assert response.status_code==200
    review=db.get(MigrationReview,response.json()['id'])
    assert review.reviewer=='admin'


def test_singular_plural_binding_is_compile_time_qualified_and_unambiguous():
    sql="SELECT sd.sale_detail_id, 'sale_detail_id' AS label FROM cat.bronze.details sd"
    schemas={'cat.bronze.details':['sales_detail_id']}
    fixed=bind_physical_columns(sql,schemas)
    assert 'sd.`sales_detail_id`' in fixed and "'sale_detail_id'" in fixed
    assert validate_databricks_sql(fixed,schemas)==[]
    # Different business keys are not spelling variants.
    assert bind_physical_columns('SELECT t.order_id FROM cat.bronze.t t',{'cat.bronze.t':['sale_id']})=='SELECT t.order_id FROM cat.bronze.t t'
    with pytest.raises(ValueError,match='Ambiguous'):
        bind_physical_columns('SELECT t.order_item_id FROM cat.bronze.t t',{'cat.bronze.t':['orders_item_id','order_items_id']})


def test_runtime_compiler_suggestion_cannot_change_approved_execution(db):
    calls=[]
    def execute(sql,**kwargs):
        calls.append(sql)
        raise RuntimeError("[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column with name `t`.`item_id` cannot be resolved. Did you mean one of the following? [`t`.`ItemID`]")
    with pytest.raises(ValueError,match='new artifact version'):
        deployment._safe_execute_with_auto_healing(db,'SELECT t.item_id FROM cat.bronze.t t',project_id='P',run_id='R',executor=execute)
    assert len(calls)==1


def test_31_of_42_resume_executes_only_remaining_11(db,monkeypatch):
    db.add(MigrationProject(id='P',name='42-artifact resume'));db.commit()
    nodes=[];artifacts=[]
    for n in range(42):
        node=MigrationMedallionNode(id=f'N{n}',project_id='P',environment='DEV',layer='SILVER',node_type='VIEW',
            model_role='VIEW',target_name=f'v{n:02d}',target_fqn=f'cat.silver.v{n:02d}',transformation_json='{}',generation_strategy='DETERMINISTIC')
        nodes.append(node);db.add(node)
        content=f'CREATE OR REPLACE VIEW cat.silver.v{n:02d} AS SELECT 1 AS id'
        artifacts.append({'node_id':node.id,'target_fqn':node.target_fqn,'version':1,'artifact_version_id':f'V{n}',
            'content_hash':hashlib.sha256(content.encode()).hexdigest(),'content':content,'node_type':'VIEW',
            'executable':True,'review_status':'APPROVED','validation_status':'PASSED'})
    db.commit()
    monkeypatch.setattr(medallion,'list_medallion_artifacts',lambda *a,**k:artifacts)
    monkeypatch.setattr(medallion,'_revalidate_current_routines',lambda *a:[])
    monkeypatch.setattr(deployment,'databricks_workspace_identity',lambda:'workspace-A')
    monkeypatch.setattr(deployment,'run_reconciliation',lambda *a,**k:{'status':'PASSED'})
    monkeypatch.setattr(deployment,'evaluate_dev_gate',lambda *a,**k:{'status':'PASSED'})
    calls=[];fail=[True]
    def execute(sql,**kwargs):
        calls.append(sql)
        if fail[0] and 'cat.silver.v31 ' in sql:raise RuntimeError('Synthetic interruption at object 32')
    monkeypatch.setattr(databricks_client,'execute_sql',execute)
    first=medallion.deploy_medallion_dev(db,'P')
    assert first['status']=='FAILED' and len(first['deployed'])==31
    fail[0]=False;calls.clear()
    resumed=medallion.deploy_medallion_dev(db,'P')
    assert resumed['status']=='PASSED' and resumed['skipped']==31
    assert len(calls)==11 and len(resumed['deployed'])==42
    assert resumed['verification']['reconciliation_status']=='PASSED'


@pytest.mark.parametrize('change',[{'artifact_content_hash':'different'},{'databricks_workspace':'elsewhere'},{'source_hash':'changed'},{'target_fqn':'other.silver.v'},{'max_rows':5}])
def test_resume_rejects_changed_execution_identity(change):
    item={'node_id':'N','artifact_version_id':'V','content_hash':'H'}
    node=NS(source_object_id='O',target_fqn='cat.silver.v')
    evidence={'medallion_node_id':'N','artifact_version_id':'V','artifact_content_hash':'H','target_fqn':'cat.silver.v','databricks_workspace':'W','source_hash':'S','max_rows':None}
    evidence.update(change)
    assert medallion.matching_resume_evidence([item],{'N':node},{'O':NS(source_hash='S')},[NS(id='D',status='PASSED',payload_json=json.dumps(evidence))],'W',None)=={}


def test_gate_never_fabricates_reconciliation(db,monkeypatch):
    monkeypatch.setattr(deployment,'medallion_deployment_status',lambda *a,**k:{'status':'PASSED'})
    monkeypatch.setattr(deployment,'_latest_successful_medallion_run',lambda *a,**k:('R',[]))
    result=deployment.evaluate_dev_gate(db,'P')
    assert result['status']=='BLOCKED'
    assert db.scalars(select(MigrationReconciliation)).all()==[]


def test_target_executor_does_not_retain_control_connection(db,monkeypatch):
    db.add(MigrationProject(id='P',name='Detached'))
    db.add(MigrationDatabricksConfiguration(id='C',project_id='P',workspace_host='synthetic.invalid',http_path='/sql/test',token_env_key='SYNTHETIC_TOKEN',status='READY'))
    db.commit();monkeypatch.setenv('SYNTHETIC_TOKEN','unused-synthetic-secret')
    def execute(sql,**kwargs):
        assert not db.in_transaction()
        assert kwargs['server_hostname']=='synthetic.invalid'
        return [(42,)]
    monkeypatch.setattr(databricks_client,'execute_sql_with_credentials',execute)
    detached=deployment.detached_target_executor(db,'P');db.commit()
    assert detached('SELECT COUNT(*)',safe_retry=True)==[(42,)]


def test_nullpool_budget_limits_active_clients_and_releases_on_close():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from sqlalchemy.exc import TimeoutError
    from app.core.database import install_connection_budget
    engine=create_engine('sqlite://',poolclass=NullPool)
    install_connection_budget(engine,limit=1,timeout=0.01)
    first=engine.connect()
    with pytest.raises(TimeoutError,match='budget exhausted'):engine.connect()
    first.close()
    with engine.connect() as replacement:replacement.invalidate()
    with engine.connect():pass
    engine.dispose()


def test_agent_collision_falls_back_to_ephemeral_port(monkeypatch):
    attempted=[]
    def bind(address,handler):
        attempted.append(address)
        if address[1]!=0:raise OSError('Synthetic occupied port')
        return NS(server_address=('127.0.0.1',41234),serve_forever=lambda:None)
    monkeypatch.setattr(agent,'ReusableTCPServer',bind)
    monkeypatch.setattr(agent.threading,'Thread',lambda **kw:NS(start=lambda:None))
    assert agent.start_dashboard_server(8585)==41234
    assert attempted[-1]==('127.0.0.1',0)


def test_agent_backoff_is_capped_and_resets(monkeypatch):
    monkeypatch.setattr(agent.random,'uniform',lambda *a:1)
    backoff=agent.ReconnectBackoff()
    assert [backoff.next_delay() for _ in range(7)]==[3,5,9,17,33,60,60]
    backoff.reset();assert backoff.next_delay()==3
    assert backoff.next_delay('45')==45


@pytest.mark.parametrize('source_type',['bytea','raw','blob','longblob','varbinary'])
def test_binary_transport_and_agent_staging_match(source_type):
    col=NS(column_name='payload',data_type=source_type,precision=None,scale=None)
    assert transport_plan(source_type).target_type=='BINARY'
    assert normalize_source_value(col,memoryview(b'\x00\xff'))=='00ff'
    assert agent.encode_staging_value(b'\x00\xff',{'strategy':'HEX_STRING_TO_BINARY'})=='00ff'


def test_healthz_is_database_and_provider_independent(client,monkeypatch):
    monkeypatch.setattr(routes,'test_provider_connection',lambda:pytest.fail('Provider must not be probed'))
    response=client.get('/healthz')
    assert response.status_code==200 and response.json()['status']=='ok'


def test_connector_gzip_expansion_is_bounded(client, db, auth_headers):
    import gzip
    from tests.test_source_connector import registered
    _, headers, _=registered(client, db, auth_headers)
    compressed=gzip.compress(b'x'*(5*1024*1024))
    response=client.post('/api/connector/tasks/unused/result',
        headers={**headers,'Content-Encoding':'gzip'},content=compressed)
    assert response.status_code==413


def test_disabled_incremental_sync_rejects_schedules_and_work_before_source_access(client, db, auth_headers, monkeypatch):
    monkeypatch.setattr(routes.get_settings(), 'incremental_sync_enabled', False)
    monkeypatch.setattr(watermark_service, '_requirements', lambda *a: pytest.fail('Disabled sync must not access sources'))
    db.add(MigrationProject(id='P', name='Disabled incremental', created_by='admin')); db.commit()
    response=client.put('/api/projects/P/schedule',headers=auth_headers,
        json={'is_enabled':True,'frequency':'DAILY','scheduled_time':'01:00'})
    assert response.status_code==409
    import asyncio
    with pytest.raises(ValueError,match='disabled'):
        asyncio.run(watermark_service.run_incremental_sync_for_project(db,'P'))
