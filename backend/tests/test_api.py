def test_health(client):
    r=client.get('/api/health'); assert r.status_code==200 and r.json()['status']=='ok'

def test_api_end_to_end_simulated(client,auth_headers):
    p=client.post('/api/projects',headers=auth_headers,json={'name':'Enterprise Regression'}).json(); pid=p['id']
    s=client.post(f'/api/projects/{pid}/sources',headers=auth_headers,json={'profile_name':'S1','server_name':'sql1','database_name':'AnyDB'}).json()
    snap={'database':'AnyDB','objects':[{'schema':'custom','name':'EntityA','type':'TABLE','columns':[{'name':'Id','type':'int','nullable':False},{'name':'rv','type':'timestamp'}]},{'schema':'custom','name':'EntityReport','type':'VIEW','definition':'CREATE VIEW custom.EntityReport AS SELECT E.Id, COUNT(*) Cnt FROM custom.EntityA E GROUP BY E.Id'}]}
    r=client.post(f'/api/projects/{pid}/discovery/snapshot',headers=auth_headers,json={'source_id':s['id'],'snapshot':snap}); assert r.status_code==200
    assert client.post(f'/api/projects/{pid}/classification',headers=auth_headers).json()['classified']==2
    assert client.post(f'/api/projects/{pid}/mappings',headers=auth_headers,json={'environment':'DEV','catalog':'dev_dynamic'}).json()['mapped']==2
    inv=client.get(f'/api/projects/{pid}/inventory',headers=auth_headers).json(); table=next(x for x in inv if x['name']=='EntityA')
    art=client.post(f'/api/projects/{pid}/artifacts',headers=auth_headers,json={'object_id':table['id'],'environment':'DEV'}); assert 'BINARY' in art.json()['content']
    gate=client.post(f'/api/projects/{pid}/quality-gates',headers=auth_headers,json={'environment':'DEV','status':'PASSED','pass_count':5,'fail_count':0,'blocker_count':0,'deployment_version':'1'}); assert gate.status_code==200
    lc=client.get(f'/api/projects/{pid}/lifecycle',headers=auth_headers).json(); assert lc[0]['status']=='PASSED'

def test_account_lockout(client):
    client.post('/api/bootstrap-admin',json={'username':'admin','password':'correct-password-1234567890'})
    for _ in range(5): client.post('/api/login',json={'username':'admin','password':'wrong'})
    assert client.post('/api/login',json={'username':'admin','password':'correct-password-1234567890'}).status_code==401

def test_dev_logs_endpoints(client,auth_headers):
    p=client.post('/api/projects',headers=auth_headers,json={'name':'Log API'}).json(); pid=p['id']
    r=client.get(f'/api/projects/{pid}/deployments/dev/logs',headers=auth_headers)
    assert r.status_code==200 and r.json()['environment']=='DEV'
    d=client.get(f'/api/projects/{pid}/deployments/dev/logs/download?format=csv',headers=auth_headers)
    assert d.status_code==200 and 'text/csv' in d.headers.get('content-type','')
    assert 'attachment' in d.headers.get('content-disposition','')

def test_issue_governance_actions(client,auth_headers,db):
    from app.models.entities import MigrationProject, MigrationIssue
    from app.services.engine import uid
    p=client.post('/api/projects',headers=auth_headers,json={'name':'Issue Governance'}).json(); pid=p['id']
    issue=MigrationIssue(id=uid('ISS'),project_id=pid,object_id=None,issue_type='DEPLOYMENT',severity='BLOCKER',message='DEV deployment failed at dbo.Customer',technical_details='{"run_id":"RUN_1","failed_object":"dbo.Customer","error":"sample"}',recommended_action='Fix and re-check.',status='OPEN')
    db.add(issue); db.commit()
    rows=client.get(f'/api/projects/{pid}/issues',headers=auth_headers).json()
    assert rows[0]['run_id']=='RUN_1' and rows[0]['status']=='OPEN'
    assert client.post(f'/api/projects/{pid}/issues/{issue.id}/action',headers=auth_headers,json={'action':'RESOLVE','comments':''}).status_code==400
    r=client.post(f'/api/projects/{pid}/issues/{issue.id}/action',headers=auth_headers,json={'action':'RESOLVE','comments':'Underlying failure fixed and validated.'})
    assert r.status_code==200 and r.json()['status']=='RESOLVED' and r.json()['actions'][0]['action']=='RESOLVE'
    r=client.post(f'/api/projects/{pid}/issues/{issue.id}/action',headers=auth_headers,json={'action':'REOPEN','comments':'Regression reproduced.'})
    assert r.status_code==200 and r.json()['status']=='OPEN'

def test_artifact_and_mapping_lists_deduplicate_legacy_rows(client,auth_headers,db):
    from app.models.entities import MigrationArtifact, MigrationArtifactVersion, MigrationMapping
    from app.services.engine import uid, sha
    p=client.post('/api/projects',headers=auth_headers,json={'name':'Duplicate Hardening'}).json(); pid=p['id']
    s=client.post(f'/api/projects/{pid}/sources',headers=auth_headers,json={'profile_name':'S1','server_name':'sql1','database_name':'AnyDB'}).json()
    snap={'database':'AnyDB','objects':[{'schema':'dbo','name':'Orders','type':'TABLE','columns':[{'name':'Id','type':'int','nullable':False}]}]}
    assert client.post(f'/api/projects/{pid}/discovery/snapshot',headers=auth_headers,json={'source_id':s['id'],'snapshot':snap}).status_code==200
    assert client.post(f'/api/projects/{pid}/classification',headers=auth_headers).status_code==200
    assert client.post(f'/api/projects/{pid}/mappings',headers=auth_headers,json={'environment':'DEV','catalog':'migration_dev'}).status_code==200
    obj=client.get(f'/api/projects/{pid}/inventory',headers=auth_headers).json()[0]
    client.post(f'/api/projects/{pid}/artifacts',headers=auth_headers,json={'object_id':obj['id'],'environment':'DEV'})

    # Simulate legacy duplicate rows left by older builds.
    m0=db.query(MigrationMapping).filter_by(project_id=pid,object_id=obj['id'],environment='DEV').first()
    db.add(MigrationMapping(id=uid('MAP'),project_id=pid,object_id=obj['id'],source_fqn=m0.source_fqn,target_fqn=m0.target_fqn,target_layer=m0.target_layer,environment='DEV'))
    dup=MigrationArtifact(id=uid('ART'),project_id=pid,object_id=obj['id'],artifact_type='TABLE',current_version=1); db.add(dup); db.flush()
    content='CREATE TABLE `migration_dev`.`bronze`.`Orders` (`Id` INT) USING DELTA;'
    db.add(MigrationArtifactVersion(id=uid('ARV'),project_id=pid,artifact_id=dup.id,version=1,content=content,source_hash=sha('legacy'),target_hash=sha(content)))
    db.commit()

    mappings=client.get(f'/api/projects/{pid}/mappings',headers=auth_headers).json()
    artifacts=client.get(f'/api/projects/{pid}/artifacts',headers=auth_headers).json()
    assert len(mappings)==1
    assert len(artifacts)==1
    assert artifacts[0]['object_id']==obj['id']

def test_dynamic_compatibility_summary_api(client,auth_headers):
    p=client.post('/api/projects',headers=auth_headers,json={'name':'Compatibility API'}).json(); pid=p['id']
    s=client.post(f'/api/projects/{pid}/sources',headers=auth_headers,json={'profile_name':'S1','server_name':'sql1','database_name':'AnyDB'}).json()
    snap={'database':'AnyDB','objects':[{'schema':'custom','name':'T','type':'TABLE','columns':[
        {'name':'Id','type':'int','nullable':False},
        {'name':'rv','type':'rowversion','nullable':False},
        {'name':'Shape','type':'geometry','nullable':True},
        {'name':'Mystery','type':'customer_udt','nullable':True},
    ]}]}
    assert client.post(f'/api/projects/{pid}/discovery/snapshot',headers=auth_headers,json={'source_id':s['id'],'snapshot':snap}).status_code==200
    r=client.get(f'/api/projects/{pid}/compatibility/summary',headers=auth_headers)
    assert r.status_code==200
    body=r.json()
    assert body['framework_version']=='2.2.0'
    assert body['total_columns']==4
    assert body['deterministic_columns']==2
    assert body['review_required_count']==2
    assert body['unknown_type_count']==1
    assert body['policy']['ai_for_runtime_transport'] is False


def test_compatibility_catalog_api(client,auth_headers):
    r=client.get('/api/compatibility/catalog',headers=auth_headers)
    assert r.status_code==200
    body=r.json()
    assert body['framework_version']=='2.2.0'
    assert any(x['adapter_id']=='binary.hex.v2' for x in body['adapters'])
