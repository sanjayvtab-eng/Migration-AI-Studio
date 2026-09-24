from sqlalchemy import select
from app.models.entities import MigrationReview


def _seed_artifact(client, auth_headers, name='Customer', definition=None, object_type='TABLE'):
    p=client.post('/api/projects',json={'name':f'Governance {name}'},headers=auth_headers).json(); pid=p['id']
    src=client.post(f'/api/projects/{pid}/sources',json={'profile_name':'s','server_name':'x','database_name':'DB1'},headers=auth_headers).json()
    obj={'schema':'dbo','name':name,'type':object_type,'columns':[{'name':'ID','type':'int'}]}
    if definition is not None: obj['definition']=definition
    client.post(f'/api/projects/{pid}/discovery/snapshot',json={'source_id':src['id'],'snapshot':{'database':'DB1','objects':[obj]}},headers=auth_headers)
    client.post(f'/api/projects/{pid}/classification',headers=auth_headers)
    client.post(f'/api/projects/{pid}/mappings',json={'environment':'DEV','catalog':'migration_dev'},headers=auth_headers)
    inv=client.get(f'/api/projects/{pid}/inventory',headers=auth_headers).json()[0]
    av=client.post(f'/api/projects/{pid}/artifacts',json={'object_id':inv['id'],'environment':'DEV'},headers=auth_headers).json()
    return pid,inv,av


def test_approval_blocked_until_static_validation_passes(client,auth_headers):
    pid,obj,av=_seed_artifact(client,auth_headers)
    payload={'artifact_version_id':av['artifact_version_id'],'review_type':'ARCHITECT_REVIEW','status':'APPROVED','reviewer':'admin','comments':'approve'}
    r=client.post(f'/api/projects/{pid}/reviews',json=payload,headers=auth_headers)
    assert r.status_code==400
    assert 'validation' in r.json()['detail'].lower()
    v=client.post(f"/api/projects/{pid}/validate/{obj['id']}?environment=DEV",headers=auth_headers)
    assert v.status_code==200 and v.json()['status']=='PASSED'
    r=client.post(f'/api/projects/{pid}/reviews',json=payload,headers=auth_headers)
    assert r.status_code==200 and r.json()['effective_status']=='APPROVED'


def test_non_executable_artifact_cannot_be_approved(client,auth_headers):
    definition='CREATE FUNCTION dbo.BadFn(@x int) RETURNS int AS BEGIN DECLARE @y int; SET @y=@x; RETURN @y; END'
    pid,obj,av=_seed_artifact(client,auth_headers,'BadFn',definition,'FUNCTION')
    v=client.post(f"/api/projects/{pid}/validate/{obj['id']}?environment=DEV",headers=auth_headers)
    assert v.status_code==200 and v.json()['status']=='FAILED'
    payload={'artifact_version_id':av['artifact_version_id'],'review_type':'ARCHITECT_REVIEW','status':'APPROVED','reviewer':'admin','comments':'approve'}
    r=client.post(f'/api/projects/{pid}/reviews',json=payload,headers=auth_headers)
    assert r.status_code==400
    assert 'not executable' in r.json()['detail'].lower()


def test_revoke_reject_and_request_changes_are_audited_and_latest_state_effective(client,auth_headers):
    pid,obj,av=_seed_artifact(client,auth_headers,'Orders')
    client.post(f"/api/projects/{pid}/validate/{obj['id']}?environment=DEV",headers=auth_headers)
    base={'artifact_version_id':av['artifact_version_id'],'review_type':'ARCHITECT_REVIEW','reviewer':'admin'}
    assert client.post(f'/api/projects/{pid}/reviews',json={**base,'status':'APPROVED','comments':'approved'},headers=auth_headers).status_code==200
    assert client.post(f'/api/projects/{pid}/reviews',json={**base,'status':'REVOKED','comments':'approved by mistake'},headers=auth_headers).status_code==200
    arts=client.get(f'/api/projects/{pid}/artifacts',headers=auth_headers).json()
    assert arts[0]['review_status']=='REVOKED'
    assert client.post(f'/api/projects/{pid}/reviews',json={**base,'status':'CHANGES_REQUESTED','comments':'adjust target logic'},headers=auth_headers).status_code==200
    arts=client.get(f'/api/projects/{pid}/artifacts',headers=auth_headers).json()
    assert arts[0]['review_status']=='CHANGES_REQUESTED'
    assert client.post(f'/api/projects/{pid}/reviews',json={**base,'status':'REJECTED','comments':'not acceptable'},headers=auth_headers).status_code==200
    rows=client.get(f'/api/projects/{pid}/reviews',headers=auth_headers).json()
    statuses=[x['status'] for x in rows]
    assert 'APPROVED' in statuses and 'REVOKED' in statuses and 'CHANGES_REQUESTED' in statuses and 'REJECTED' in statuses


def test_revoke_requires_reason_and_prior_approval(client,auth_headers):
    pid,obj,av=_seed_artifact(client,auth_headers,'Product')
    base={'artifact_version_id':av['artifact_version_id'],'review_type':'ARCHITECT_REVIEW','reviewer':'admin'}
    r=client.post(f'/api/projects/{pid}/reviews',json={**base,'status':'REVOKED','comments':'x'},headers=auth_headers)
    assert r.status_code==400
    r=client.post(f'/api/projects/{pid}/reviews',json={**base,'status':'REJECTED','comments':''},headers=auth_headers)
    assert r.status_code==400
