from app.api import routes


def _project_source(client, headers):
    p=client.post('/api/projects',headers=headers,json={'name':'360 Project'}).json()
    s=client.post(f"/api/projects/{p['id']}/sources",headers=headers,json={'profile_name':'S1','server_name':'localhost','database_name':'AnyDB'}).json()
    return p['id'],s['id']


def test_source_connection_endpoint_mocked(client,auth_headers,monkeypatch):
    pid,sid=_project_source(client,auth_headers)
    monkeypatch.setattr(routes,'test_sqlserver_connection',lambda c:{'ok':True,'server':'LOCAL','database':'AnyDB','product_version':'16.0'})
    r=client.post(f'/api/projects/{pid}/sources/{sid}/test',headers=auth_headers)
    assert r.status_code==200 and r.json()['ok'] is True


def test_discovery_snapshot_captures_dependencies(client,auth_headers):
    pid,sid=_project_source(client,auth_headers)
    snap={'database':'AnyDB','objects':[
      {'schema':'sales','name':'Orders','type':'TABLE','columns':[{'name':'Id','type':'int'}]},
      {'schema':'report','name':'VOrders','type':'VIEW','definition':'select * from sales.Orders','dependencies':[{'database':'AnyDB','schema':'sales','object':'Orders','column':'Id','type':'CROSS_SCHEMA'}]}
    ]}
    assert client.post(f'/api/projects/{pid}/discovery/snapshot',headers=auth_headers,json={'source_id':sid,'snapshot':snap}).status_code==200
    deps=client.get(f'/api/projects/{pid}/dependencies',headers=auth_headers).json()
    assert len(deps)==1 and deps[0]['referenced_object']=='Orders'


def test_assessment_and_conversion_plan_workflow(client,auth_headers):
    pid,sid=_project_source(client,auth_headers)
    snap={'database':'AnyDB','objects':[{'schema':'dbo','name':'T','type':'TABLE','columns':[{'name':'Id','type':'int'}]},{'schema':'dbo','name':'P','type':'PROCEDURE','definition':'CREATE PROC dbo.P AS INSERT INTO dbo.T(Id) SELECT 1'}]}
    client.post(f'/api/projects/{pid}/discovery/snapshot',headers=auth_headers,json={'source_id':sid,'snapshot':snap})
    a=client.post(f'/api/projects/{pid}/assessment/run',headers=auth_headers).json(); assert a['assessed']==2
    client.post(f'/api/projects/{pid}/classification',headers=auth_headers)
    cp=client.post(f'/api/projects/{pid}/conversion-plans/generate',headers=auth_headers).json(); assert cp['planned']==2
    rows=client.get(f'/api/projects/{pid}/module/conversion-plans',headers=auth_headers).json(); assert len(rows)==2


def test_generic_control_plane_modules_are_project_scoped(client,auth_headers):
    p1=client.post('/api/projects',headers=auth_headers,json={'name':'P1'}).json()['id']
    p2=client.post('/api/projects',headers=auth_headers,json={'name':'P2'}).json()['id']
    client.post(f'/api/projects/{p1}/module/waves',headers=auth_headers,json={'title':'Wave 1','status':'PLANNED','environment':'DEV','details':{}})
    assert len(client.get(f'/api/projects/{p1}/module/waves',headers=auth_headers).json())==1
    assert len(client.get(f'/api/projects/{p2}/module/waves',headers=auth_headers).json())==0


def test_users_unlock_and_diagnostics(client,auth_headers):
    users=client.get('/api/users',headers=auth_headers); assert users.status_code==200 and users.json()
    d=client.get('/api/system/diagnostics',headers=auth_headers); assert d.status_code==200 and 'sqlserver_driver' in d.json()


def test_all_control_plane_module_endpoints(client,auth_headers):
    pid=client.post('/api/projects',headers=auth_headers,json={'name':'Module Sweep'}).json()['id']
    modules=['assessment','conversion-plans','data-quality','reconciliation','deployments','waves','cutover','decommission','governance','audit','administration']
    for module in modules:
        r=client.post(f'/api/projects/{pid}/module/{module}',headers=auth_headers,json={'title':f'{module} record','status':'OPEN','environment':'DEV','details':{'sweep':True}})
        assert r.status_code==200, (module,r.text)
        g=client.get(f'/api/projects/{pid}/module/{module}',headers=auth_headers)
        assert g.status_code==200 and len(g.json())==1


def test_promotion_precheck_isolated_by_project(client,auth_headers):
    p1=client.post('/api/projects',headers=auth_headers,json={'name':'Promote A'}).json()['id']
    p2=client.post('/api/projects',headers=auth_headers,json={'name':'Promote B'}).json()['id']
    client.post(f'/api/projects/{p1}/quality-gates',headers=auth_headers,json={'environment':'DEV','status':'PASSED','pass_count':1,'fail_count':0,'blocker_count':0})
    a=client.get(f'/api/projects/{p1}/promotion-precheck/TEST',headers=auth_headers).json()
    b=client.get(f'/api/projects/{p2}/promotion-precheck/TEST',headers=auth_headers).json()
    assert a['eligible'] is True
    assert b['eligible'] is False and any('DEV quality gate' in x for x in b['blockers'])


def test_databricks_connection_endpoint_mocked(client,auth_headers,monkeypatch):
    monkeypatch.setattr(routes,'execute_sql',lambda statement,safe_retry=True:[('catalog','schema','user')])
    r=client.post('/api/system/databricks-test',headers=auth_headers)
    assert r.status_code==200 and r.json()['ok'] is True
