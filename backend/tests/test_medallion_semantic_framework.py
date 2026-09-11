
def _project_with_semantics(client, auth_headers):
    p=client.post('/api/projects',headers=auth_headers,json={'name':'Medallion Semantic Regression'}).json(); pid=p['id']
    s=client.post(f'/api/projects/{pid}/sources',headers=auth_headers,json={'profile_name':'S1','server_name':'sql1','database_name':'SalesDB'}).json()
    snap={'database':'SalesDB','objects':[
        {'schema':'sales','name':'Customer','type':'TABLE','columns':[
            {'name':'CustomerId','type':'int','nullable':False},{'name':'CustomerName','type':'nvarchar','nullable':False},{'name':'Region','type':'nvarchar','nullable':True}
        ],'constraints':[{'name':'PK_Customer','type':'PRIMARY_KEY','columns':['CustomerId']}], 'approx_row_count':1000},
        {'schema':'sales','name':'Product','type':'TABLE','columns':[
            {'name':'ProductId','type':'int','nullable':False},{'name':'ProductName','type':'nvarchar','nullable':False},{'name':'Category','type':'nvarchar','nullable':True}
        ],'constraints':[{'name':'PK_Product','type':'PRIMARY_KEY','columns':['ProductId']}], 'approx_row_count':100},
        {'schema':'sales','name':'Sales','type':'TABLE','columns':[
            {'name':'SaleId','type':'bigint','nullable':False},{'name':'CustomerId','type':'int','nullable':False},{'name':'ProductId','type':'int','nullable':False},
            {'name':'SaleDate','type':'date','nullable':False},{'name':'Quantity','type':'int','nullable':False},{'name':'Amount','type':'decimal','precision':18,'scale':2,'nullable':False}
        ],'constraints':[
            {'name':'PK_Sales','type':'PRIMARY_KEY','columns':['SaleId']},
            {'name':'FK_Sales_Customer','type':'FOREIGN_KEY','columns':['CustomerId'],'referenced_schema':'sales','referenced_object':'Customer','referenced_columns':['CustomerId']},
            {'name':'FK_Sales_Product','type':'FOREIGN_KEY','columns':['ProductId'],'referenced_schema':'sales','referenced_object':'Product','referenced_columns':['ProductId']}
        ], 'approx_row_count':1000000},
        {'schema':'sales','name':'vw_SalesSummary','type':'VIEW','definition':'SET ANSI_NULLS ON\nGO\nSET QUOTED_IDENTIFIER ON\nGO\nCREATE VIEW [sales].[vw_SalesSummary] AS SELECT CustomerId, SUM(Amount) TotalAmount FROM [sales].[Sales] GROUP BY CustomerId',
         'columns':[{'name':'CustomerId','type':'int','nullable':False},{'name':'TotalAmount','type':'decimal','precision':18,'scale':2,'nullable':True}],
         'dependencies':[{'schema':'sales','object':'Sales','type':'LOCAL'}]},
        {'schema':'sales','name':'usp_LoadSales','type':'PROCEDURE','definition':'CREATE PROCEDURE sales.usp_LoadSales AS UPDATE sales.Sales SET Amount=Amount WHERE 1=0',
         'dependencies':[{'schema':'sales','object':'Sales','type':'LOCAL'}]},
        {'schema':'sales','name':'fn_SalesAmount','type':'FUNCTION','definition':'CREATE FUNCTION sales.fn_SalesAmount() RETURNS int AS BEGIN RETURN 1 END'},
    ]}
    assert client.post(f'/api/projects/{pid}/discovery/snapshot',headers=auth_headers,json={'source_id':s['id'],'snapshot':snap}).status_code==200
    assert client.post(f'/api/projects/{pid}/classification',headers=auth_headers).status_code==200
    assert client.post(f'/api/projects/{pid}/mappings',headers=auth_headers,json={'environment':'DEV','catalog':'migration_dev'}).status_code==200
    return pid


def test_fact_dimension_inference_and_downstream_consumers(client,auth_headers):
    pid=_project_with_semantics(client,auth_headers)
    c=client.post(f'/api/projects/{pid}/consumers/analyze',headers=auth_headers)
    assert c.status_code==200
    rows=client.get(f'/api/projects/{pid}/consumers',headers=auth_headers).json()
    sales=client.get(f'/api/projects/{pid}/inventory',headers=auth_headers).json()
    sales_id=next(x['id'] for x in sales if x['name']=='Sales')
    assert any(x['producer_object_id']==sales_id and x['consumer_name']=='sales.vw_SalesSummary' and x['usage_type']=='REPORTING_READ' for x in rows)

    r=client.post(f'/api/projects/{pid}/semantics/infer',headers=auth_headers)
    assert r.status_code==200
    defs=r.json()['definitions']
    assert next(x for x in defs if x['name']=='sales.Sales')['role']=='FACT'
    assert next(x for x in defs if x['name']=='sales.Customer')['role']=='DIMENSION'
    assert next(x for x in defs if x['name']=='sales.Product')['role']=='DIMENSION'


def test_true_multistage_plan_and_gold_generation_from_approved_semantics(client,auth_headers):
    pid=_project_with_semantics(client,auth_headers)
    inventory=client.get(f'/api/projects/{pid}/inventory',headers=auth_headers).json()
    sales_id=next(x['id'] for x in inventory if x['name']=='Sales')
    customer_id=next(x['id'] for x in inventory if x['name']=='Customer')

    # Explicit semantics are the source of truth for automatic Gold generation.
    fact=client.post(f'/api/projects/{pid}/semantics',headers=auth_headers,json={
        'object_id':sales_id,'semantic_role':'FACT','target_name':'fact_sales','grain':['SaleId'],
        'dimension_keys':['CustomerId','ProductId'],'measures':[
            {'name':'quantity','source_column':'Quantity','aggregation':'NONE'},
            {'name':'amount','source_column':'Amount','aggregation':'NONE'}
        ]
    }); assert fact.status_code==200, fact.text
    dim=client.post(f'/api/projects/{pid}/semantics',headers=auth_headers,json={
        'object_id':customer_id,'semantic_role':'DIMENSION','target_name':'dim_customer','business_keys':['CustomerId'],
        'attributes':['CustomerName','Region'],'scd_type':'1'
    }); assert dim.status_code==200, dim.text
    assert client.post(f"/api/projects/{pid}/semantics/{fact.json()['id']}/approve",headers=auth_headers,json={'actor':'architect'}).status_code==200
    assert client.post(f"/api/projects/{pid}/semantics/{dim.json()['id']}/approve",headers=auth_headers,json={'actor':'architect'}).status_code==200

    plan=client.post(f'/api/projects/{pid}/medallion/plan',headers=auth_headers,json={'environment':'DEV','catalog':'migration_dev'})
    assert plan.status_code==200, plan.text
    body=plan.json()
    sales_nodes=[x for x in body['nodes'] if x['source_object_id']==sales_id]
    assert {'SOURCE','BRONZE','SILVER','GOLD'}.issubset({x['layer'] for x in sales_nodes})
    assert any(x['layer']=='GOLD' and x['model_role']=='FACT' and x['target_name']=='fact_sales' for x in sales_nodes)
    customer_nodes=[x for x in body['nodes'] if x['source_object_id']==customer_id]
    assert {'SOURCE','BRONZE','SILVER','GOLD'}.issubset({x['layer'] for x in customer_nodes})

    gen=client.post(f'/api/projects/{pid}/medallion/generate?environment=DEV',headers=auth_headers)
    assert gen.status_code==200, gen.text
    arts=client.get(f'/api/projects/{pid}/medallion/artifacts?environment=DEV',headers=auth_headers).json()
    view_art=next(x for x in arts if x['target_fqn'].endswith('`vw_SalesSummary`'))
    assert view_art['content'].startswith('CREATE OR REPLACE VIEW `migration_dev`.`silver`.`vw_SalesSummary`')
    fact_art=next(x for x in arts if x['target_fqn'].endswith('`fact_sales`'))
    dim_art=next(x for x in arts if x['target_fqn'].endswith('`dim_customer`'))
    assert fact_art['validation_status']=='PASSED' and fact_art['executable'] is True
    assert '`migration_dev`.`silver`.`Sales`' in fact_art['content']
    assert '`migration_dev`.`bronze`.`Sales`' not in fact_art['content']
    assert dim_art['validation_status']=='PASSED' and '`migration_dev`.`silver`.`Customer`' in dim_art['content']


def test_gold_is_not_created_from_unapproved_inference(client,auth_headers):
    pid=_project_with_semantics(client,auth_headers)
    client.post(f'/api/projects/{pid}/semantics/infer',headers=auth_headers)
    plan=client.post(f'/api/projects/{pid}/medallion/plan',headers=auth_headers,json={'environment':'DEV','catalog':'migration_dev'}).json()
    assert not [x for x in plan['nodes'] if x['layer']=='GOLD']
    assert plan['policy']['gold_requires_approved_business_semantics'] is True


def test_semantic_definition_blocks_unknown_columns(client,auth_headers):
    pid=_project_with_semantics(client,auth_headers)
    inventory=client.get(f'/api/projects/{pid}/inventory',headers=auth_headers).json()
    sales_id=next(x['id'] for x in inventory if x['name']=='Sales')
    r=client.post(f'/api/projects/{pid}/semantics',headers=auth_headers,json={
        'object_id':sales_id,'semantic_role':'FACT','target_name':'fact_bad','grain':['DoesNotExist'],
        'measures':[{'name':'amount','source_column':'Amount','aggregation':'SUM'}]
    })
    assert r.status_code==400 and 'unknown column' in r.text.lower()


def test_routines_are_planned_as_logic_assets(client,auth_headers):
    pid=_project_with_semantics(client,auth_headers)
    plan=client.post(f'/api/projects/{pid}/medallion/plan',headers=auth_headers,json={'environment':'DEV','catalog':'migration_dev'}).json()
    proc=next(x for x in plan['nodes'] if x['target_name']=='usp_LoadSales' and x['layer']=='SILVER')
    func=next(x for x in plan['nodes'] if x['target_name']=='fn_SalesAmount' and x['layer']=='SILVER')
    assert proc['node_type'] in {'SQL_PROCEDURE','ROUTINE_PLAN'}
    assert proc['transformation']['intent']=='ETL_LOAD'
    assert func['node_type'] in {'SQL_FUNCTION','FUNCTION_PLAN'}


def test_failed_medallion_routine_repair_creates_new_validated_unapproved_version(
    client, auth_headers, db, monkeypatch
):
    from app.models.entities import (
        MigrationArtifact,
        MigrationArtifactVersion,
        MigrationMedallionNode,
        MigrationObject,
        MigrationReview,
        MigrationStageArtifact,
        MigrationStageArtifactVersion,
    )
    from app.services.engine import uid
    import app.services.ai_remediation as ai_remediation
    import app.services.engine as engine_service

    pid = _project_with_semantics(client, auth_headers)
    client.post(
        f'/api/projects/{pid}/medallion/plan', headers=auth_headers,
        json={'environment':'DEV','catalog':'migration_dev'},
    )
    assert client.post(
        f'/api/projects/{pid}/medallion/generate?environment=DEV', headers=auth_headers,
    ).status_code == 200

    node = db.query(MigrationMedallionNode).filter_by(
        project_id=pid, environment='DEV', target_name='usp_LoadSales', layer='SILVER'
    ).one()
    stage_artifact = db.query(MigrationStageArtifact).filter_by(
        project_id=pid, node_id=node.id
    ).one()
    failed = db.query(MigrationStageArtifactVersion).filter_by(
        project_id=pid, artifact_id=stage_artifact.id,
        version=stage_artifact.current_version,
    ).one()
    failed.executable = False
    failed.validation_status = 'FAILED'
    failed.validation_json = '{"errors":["unsupported procedure"]}'

    obj = db.get(MigrationObject, node.source_object_id)
    legacy_artifact = MigrationArtifact(
        id=uid('ART'), project_id=pid, object_id=obj.id,
        artifact_type=obj.object_type, current_version=1,
    )
    candidate = MigrationArtifactVersion(
        id=uid('ARV'), project_id=pid, artifact_id=legacy_artifact.id, version=1,
        content='CREATE OR REPLACE PROCEDURE placeholder() LANGUAGE SQL AS BEGIN SELECT 1; END;',
        source_hash='source', target_hash='target', generator_version='test', rule_version='test',
    )
    db.add_all([legacy_artifact, candidate])
    db.commit()

    monkeypatch.setattr(engine_service, 'generate_artifact', lambda *args, **kwargs: candidate)
    monkeypatch.setattr(
        engine_service, 'static_validate',
        lambda *args, **kwargs: {'valid':False, 'status':'FAILED', 'issues':['seed failure']},
    )
    repair_call = {}
    def fake_repair(*args, **kwargs):
        repair_call.update(kwargs)
        return {
            'status':'READY_FOR_REVIEW', 'artifact_version_id':candidate.id,
            'artifact_version':candidate.version, 'ai_run_id':'AIR_test', 'provider':'GEMINI',
        }
    monkeypatch.setattr(ai_remediation, 'remediate_one_artifact', fake_repair)

    response = client.post(
        f'/api/projects/{pid}/medallion/artifacts/{failed.id}/remediate',
        headers=auth_headers,
        json={'environment':'DEV','use_ai':True,'reviewer':'architect'},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'READY_FOR_REVIEW'
    assert body['validation_status'] == 'PASSED'
    assert body['review_status'] == 'PENDING_REVIEW'
    assert body['auto_approved'] is False and body['auto_deployed'] is False
    assert repair_call['confirmed_blocker'] == f'MEDALLION_STAGE_VALIDATION:{failed.id}'

    repaired = db.get(MigrationStageArtifactVersion, body['artifact_version_id'])
    assert repaired.version == failed.version + 1
    assert repaired.content.startswith(f'CREATE OR REPLACE PROCEDURE {node.target_fqn}')
    assert 'LANGUAGE SQL\nSQL SECURITY INVOKER\nAS BEGIN' in repaired.content
    db.expire_all()
    assert db.get(MigrationStageArtifact, stage_artifact.id).current_version == repaired.version

    approved = client.post(
        f'/api/projects/{pid}/medallion/artifacts/{repaired.id}/review',
        headers=auth_headers,
        json={'status':'APPROVED','reviewer':'architect'},
    )
    assert approved.status_code == 200, approved.text
    mirrored = db.query(MigrationReview).filter_by(
        project_id=pid, artifact_version_id=candidate.id,
        review_type='ARCHITECT_REVIEW', status='APPROVED',
    ).one()
    assert mirrored.reviewer == 'architect'

def test_medallion_dev_deployment_is_review_gated_and_layer_ordered(client,auth_headers,db,monkeypatch):
    from app.services.medallion import deploy_medallion_dev
    from app.models.entities import MigrationStageArtifactVersion
    import app.services.databricks_client as dc
    import app.services.deployment as dep

    pid=_project_with_semantics(client,auth_headers)
    inventory=client.get(f'/api/projects/{pid}/inventory',headers=auth_headers).json()
    customer_id=next(x['id'] for x in inventory if x['name']=='Customer')
    dim=client.post(f'/api/projects/{pid}/semantics',headers=auth_headers,json={
        'object_id':customer_id,'semantic_role':'DIMENSION','target_name':'dim_customer',
        'business_keys':['CustomerId'],'attributes':['CustomerName','Region'],'scd_type':'1'
    }).json()
    client.post(f"/api/projects/{pid}/semantics/{dim['id']}/approve",headers=auth_headers,json={'actor':'architect'})
    client.post(f'/api/projects/{pid}/medallion/plan',headers=auth_headers,json={'environment':'DEV','catalog':'migration_dev'})
    client.post(f'/api/projects/{pid}/medallion/generate?environment=DEV',headers=auth_headers)

    # Deployment is blocked until every current Medallion artifact is human approved.
    try:
        deploy_medallion_dev(db,pid)
        assert False, 'expected review gate blocker'
    except ValueError as e:
        assert 'not approved' in str(e).lower()

    for row in db.query(MigrationStageArtifactVersion).filter_by(project_id=pid).all():
        if row.executable and row.validation_status=='PASSED':
            row.review_status='APPROVED'; row.reviewer='architect'
    db.commit()

    executed=[]
    monkeypatch.setattr(dc,'execute_sql',lambda sql,safe_retry=False: executed.append(sql) or [])
    monkeypatch.setattr(dep,'_apply_table_schema_policy',lambda *a,**k:{'action':'CREATE','schema_status':'MISSING'})
    monkeypatch.setattr(dep,'load_bronze_table',lambda *a,**k:{'status':'PASSED','rows':10})
    result=deploy_medallion_dev(db,pid)
    assert result['status']=='PASSED'
    layers=[x['layer'] for x in result['deployed']]
    assert layers==sorted(layers,key=lambda x:{'BRONZE':1,'SILVER':2,'GOLD':3}[x])
    assert 'GOLD' in layers and layers.index('GOLD')>layers.index('SILVER')>layers.index('BRONZE')

    logs=client.get(f"/api/projects/{pid}/medallion/deployments/{result['run_id']}/logs",headers=auth_headers)
    assert logs.status_code==200
    assert logs.json()['count']==len(result['deployed'])
    assert logs.json()['passed']==len(result['deployed'])
    assert logs.json()['failed']==0
    download=client.get(f"/api/projects/{pid}/medallion/deployments/{result['run_id']}/logs/download",headers=auth_headers)
    assert download.status_code==200
    assert 'text/csv' in download.headers['content-type']
    assert 'target_fqn' in download.text


def test_medallion_deployment_preflight_rejects_approved_procedure_missing_security_clause(
    client, auth_headers, db
):
    from app.services.medallion import deploy_medallion_dev
    from app.models.entities import MigrationStageArtifactVersion

    pid = _project_with_semantics(client, auth_headers)
    client.post(
        f'/api/projects/{pid}/medallion/plan', headers=auth_headers,
        json={'environment':'DEV','catalog':'migration_dev'},
    )
    generated = client.post(
        f'/api/projects/{pid}/medallion/generate?environment=DEV', headers=auth_headers,
    )
    assert generated.status_code == 200, generated.text

    versions = db.query(MigrationStageArtifactVersion).filter_by(project_id=pid).all()
    for version in versions:
        if version.executable and version.validation_status == 'PASSED':
            version.review_status = 'APPROVED'
            version.reviewer = 'architect'
    procedure = next(version for version in versions if 'CREATE OR REPLACE PROCEDURE' in version.content)
    procedure.content = procedure.content.replace('\nSQL SECURITY INVOKER', '')
    db.commit()

    try:
        deploy_medallion_dev(db, pid)
        assert False, 'expected Databricks routine preflight blocker'
    except ValueError as exc:
        message = str(exc)
        assert 'routine preflight' in message
        assert 'SQL SECURITY INVOKER' in message


def test_reconciliation_uses_exact_medallion_manifest_and_type_aware_checks(client,auth_headers,db,monkeypatch):
    from app.services.medallion import deploy_medallion_dev
    from app.services.deployment import run_reconciliation, latest_reconciliation, evaluate_dev_gate
    from app.models.entities import MigrationStageArtifactVersion
    from app.models.canonical import MigrationDeployment
    import app.services.databricks_client as dc
    import app.services.deployment as dep
    import json

    pid=_project_with_semantics(client,auth_headers)
    client.post(f'/api/projects/{pid}/semantics/infer',headers=auth_headers)
    semantics=client.get(f'/api/projects/{pid}/semantics',headers=auth_headers).json()
    for semantic in semantics:
        if semantic['status']!='APPROVED' and semantic['semantic_role'] in {'FACT','DIMENSION','AGGREGATE'}:
            client.post(f"/api/projects/{pid}/semantics/{semantic['id']}/approve",headers=auth_headers,json={'actor':'architect'})
    client.post(f'/api/projects/{pid}/medallion/plan',headers=auth_headers,json={'environment':'DEV','catalog':'migration_dev'})
    client.post(f'/api/projects/{pid}/medallion/generate?environment=DEV',headers=auth_headers)
    for row in db.query(MigrationStageArtifactVersion).filter_by(project_id=pid).all():
        if row.executable and row.validation_status=='PASSED':
            row.review_status='APPROVED'; row.reviewer='architect'
    db.commit()

    monkeypatch.setattr(dc,'execute_sql',lambda sql,safe_retry=False: [])
    monkeypatch.setattr(dep,'_apply_table_schema_policy',lambda *a,**k:{'action':'CREATE','schema_status':'MISSING'})
    monkeypatch.setattr(dep,'load_bronze_table',lambda *a,**k:{'status':'PASSED','rows':10})
    deployed=deploy_medallion_dev(db,pid)
    assert deployed['status']=='PASSED'

    # Simulate duplicate immutable evidence from a retry. Reconciliation must still emit
    # one row per Medallion node and must not re-introduce historical artifact duplicates.
    first=db.query(MigrationDeployment).filter_by(project_id=pid).first()
    db.add(MigrationDeployment(id='DPL_duplicate',project_id=pid,object_id=first.object_id,
        environment='DEV',status='PASSED',payload_json=first.payload_json));db.commit()

    statements=[]
    def fake_execute(sql,safe_retry=True):
        statements.append(sql)
        return [[10]] if sql.startswith('SELECT COUNT(*)') else [['exists']]
    monkeypatch.setattr(dep,'execute_sql',fake_execute)

    monkeypatch.setattr(dep,'_source_table_count',lambda *a,**k:10)

    result=run_reconciliation(db,pid,'DEV')
    assert result['workflow']=='MEDALLION'
    assert result['run_id']==deployed['run_id']
    assert result['status']=='PASSED' and result['failed']==0
    assert len(result['details'])==len(deployed['deployed'])
    assert len({x['medallion_node_id'] for x in result['details']})==len(result['details'])
    assert any(x['layer']=='GOLD' for x in result['details'])
    assert any(x['reconciliation_type']=='FUNCTION_EXISTENCE' for x in result['details'])
    assert any(x['reconciliation_type']=='PROCEDURE_EXISTENCE' for x in result['details'])
    assert any(sql.startswith('DESCRIBE FUNCTION') for sql in statements)
    assert any(sql.startswith('DESCRIBE PROCEDURE') for sql in statements)
    latest=latest_reconciliation(db,pid,'DEV')
    assert latest and latest['run_id']==deployed['run_id'] and len(latest['details'])==len(result['details'])
    gate=evaluate_dev_gate(db,pid)
    assert gate['status']=='PASSED' and gate['deployment_run_id']==deployed['run_id']


def test_dev_manifest_promotes_to_test_and_passes_test_gate(client,auth_headers,db,monkeypatch):
    from app.services.medallion import deploy_medallion_dev
    from app.services.deployment import (
        evaluate_dev_gate, evaluate_test_gate, evaluate_uat_gate, evaluate_prod_gate,
        promote_medallion_to_test, promote_medallion_to_uat, promote_medallion_to_prod,
        run_reconciliation, test_promotion_precheck, uat_promotion_precheck, prod_promotion_precheck,
    )
    from app.models.entities import MigrationStageArtifactVersion
    import app.services.databricks_client as dc
    import app.services.deployment as dep

    pid=_project_with_semantics(client,auth_headers)
    client.post(f'/api/projects/{pid}/semantics/infer',headers=auth_headers)
    for semantic in client.get(f'/api/projects/{pid}/semantics',headers=auth_headers).json():
        if semantic['status']!='APPROVED' and semantic['semantic_role'] in {'FACT','DIMENSION','AGGREGATE'}:
            client.post(f"/api/projects/{pid}/semantics/{semantic['id']}/approve",headers=auth_headers,json={'actor':'architect'})
    client.post(f'/api/projects/{pid}/medallion/plan',headers=auth_headers,json={'environment':'DEV','catalog':'migration_dev'})
    client.post(f'/api/projects/{pid}/medallion/generate?environment=DEV',headers=auth_headers)
    for row in db.query(MigrationStageArtifactVersion).filter_by(project_id=pid).all():
        if row.executable and row.validation_status=='PASSED':
            row.review_status='APPROVED'; row.reviewer='architect'
    db.commit()

    monkeypatch.setattr(dc,'execute_sql',lambda *a,**k:[])
    monkeypatch.setattr(dep,'_apply_table_schema_policy',lambda *a,**k:{'action':'CREATE','schema_status':'MISSING'})
    monkeypatch.setattr(dep,'load_bronze_table',lambda *a,**k:{'status':'PASSED','rows':10})
    dev=deploy_medallion_dev(db,pid)
    assert dev['status']=='PASSED'

    statements=[]
    def fake_execute(sql,safe_retry=True):
        statements.append(sql)
        if sql.startswith('SELECT current_catalog'):
            return [['migration_dev','default','tester']]
        return [[10]] if sql.startswith('SELECT COUNT(*)') else [['exists']]
    monkeypatch.setattr(dep,'execute_sql',fake_execute)
    monkeypatch.setattr(dep,'_source_table_count',lambda *a,**k:10)
    assert run_reconciliation(db,pid,'DEV')['status']=='PASSED'
    assert evaluate_dev_gate(db,pid)['status']=='PASSED'

    precheck=test_promotion_precheck(db,pid)
    assert precheck['eligible'] and precheck['source_deployment_run_id']==dev['run_id']
    promoted=promote_medallion_to_test(db,pid)
    assert promoted['status']=='PASSED' and promoted['count']==dev['count']
    assert any('DEEP CLONE' in sql and 'migration_test' in sql for sql in statements)
    assert all('migration_test' in row['target_fqn'] for row in promoted['deployed'])
    test_status=dep.deployment_status(db,pid,'TEST')
    assert test_status['total']==promoted['count'] and test_status['passed']==promoted['count']

    test_recon=run_reconciliation(db,pid,'TEST')
    assert test_recon['status']=='PASSED' and test_recon['failed']==0
    test_gate=evaluate_test_gate(db,pid)
    assert test_gate['status']=='PASSED' and test_gate['deployment_run_id']==promoted['run_id']
    lifecycle_rows=client.get(f'/api/projects/{pid}/lifecycle',headers=auth_headers).json()
    assert next(row for row in lifecycle_rows if row['environment']=='TEST')['status']=='PASSED'

    uat_precheck=uat_promotion_precheck(db,pid)
    assert uat_precheck['eligible'] and uat_precheck['source_deployment_run_id']==promoted['run_id']
    promoted_uat=promote_medallion_to_uat(db,pid)
    assert promoted_uat['status']=='PASSED' and promoted_uat['count']==promoted['count']
    assert any('DEEP CLONE' in sql and 'migration_test' in sql and 'migration_uat' in sql for sql in statements)
    assert all('migration_uat' in row['target_fqn'] for row in promoted_uat['deployed'])
    uat_status=dep.deployment_status(db,pid,'UAT')
    assert uat_status['total']==promoted_uat['count'] and uat_status['passed']==promoted_uat['count']

    uat_recon=run_reconciliation(db,pid,'UAT')
    assert uat_recon['status']=='PASSED' and uat_recon['failed']==0
    uat_gate=evaluate_uat_gate(db,pid)
    assert uat_gate['status']=='PASSED' and uat_gate['deployment_run_id']==promoted_uat['run_id']
    lifecycle_rows=client.get(f'/api/projects/{pid}/lifecycle',headers=auth_headers).json()
    assert next(row for row in lifecycle_rows if row['environment']=='UAT')['status']=='PASSED'

    prod_precheck=prod_promotion_precheck(db,pid)
    assert prod_precheck['eligible'] and prod_precheck['source_deployment_run_id']==promoted_uat['run_id']
    promoted_prod=promote_medallion_to_prod(db,pid)
    assert promoted_prod['status']=='PASSED' and promoted_prod['count']==promoted_uat['count']
    assert any('DEEP CLONE' in sql and 'migration_uat' in sql and 'migration_prod' in sql for sql in statements)
    assert all('migration_prod' in row['target_fqn'] for row in promoted_prod['deployed'])
    prod_status=dep.deployment_status(db,pid,'PROD')
    assert prod_status['total']==promoted_prod['count'] and prod_status['passed']==promoted_prod['count']

    prod_recon=run_reconciliation(db,pid,'PROD')
    assert prod_recon['status']=='PASSED' and prod_recon['failed']==0
    prod_gate=evaluate_prod_gate(db,pid)
    assert prod_gate['status']=='PASSED' and prod_gate['deployment_run_id']==promoted_prod['run_id']
    lifecycle_rows=client.get(f'/api/projects/{pid}/lifecycle',headers=auth_headers).json()
    assert next(row for row in lifecycle_rows if row['environment']=='PROD')['status']=='PASSED'
