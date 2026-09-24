from sqlalchemy import select
from app.services.engine import *
from app.models.entities import *

def seed(db,name='P1'):
    p=ensure_project(db,name); s=add_source(db,p.id,'src','server','DB1')
    snap={'database':'DB1','objects':[
      {'schema':'sales','name':'Orders','type':'TABLE','columns':[{'name':'OrderId','type':'int','nullable':False},{'name':'RV','type':'rowversion'}]},
      {'schema':'sales','name':'vw_OrderAgg','type':'VIEW','definition':'CREATE VIEW sales.vw_OrderAgg AS SELECT O.OrderId, COUNT(*) Cnt FROM sales.Orders O GROUP BY O.OrderId','columns':[]}
    ]}
    ingest_snapshot(db,p.id,s.id,snap); classify_project(db,p.id); create_mappings(db,p.id,'DEV','cat_dev'); return p

def test_project_isolation(db):
    p1=seed(db,'P1');p2=seed(db,'P2')
    assert db.scalar(select(MigrationObject).where(MigrationObject.project_id==p1.id,MigrationObject.object_name=='Orders'))
    assert len(db.scalars(select(MigrationObject).where(MigrationObject.project_id==p2.id)).all())==2

def test_artifact_versioning_and_rowversion(db):
    p=seed(db); o=db.scalar(select(MigrationObject).where(MigrationObject.project_id==p.id,MigrationObject.object_name=='Orders'))
    a1=generate_artifact(db,p.id,o.id);a2=generate_artifact(db,p.id,o.id)
    assert a1.version==1 and a2.version==2 and '`RV` BINARY' in a2.content

def test_view_reference_mapping(db):
    p=seed(db); o=db.scalar(select(MigrationObject).where(MigrationObject.project_id==p.id,MigrationObject.object_name=='vw_OrderAgg'))
    a=generate_artifact(db,p.id,o.id)
    assert '`cat_dev`.`bronze`.`Orders`' in a.content

def test_schema_drift_compare():
    same=compare_schema([{'name':'id','type':'INT'}],[{'name':'id','type':'INT'}]); assert same['status']=='IDENTICAL'
    br=compare_schema([{'name':'id','type':'BIGINT'}],[{'name':'id','type':'INT'}]); assert br['status']=='BREAKING'

def test_dependency_order_and_cycle():
    assert topo_order([('silver','bronze'),('gold','silver')])==['bronze','silver','gold']
    import pytest
    with pytest.raises(ValueError): topo_order([('a','b'),('b','a')])

def test_lifecycle_specific_project(db):
    p1=ensure_project(db,'P1');p2=ensure_project(db,'P2')
    r=MigrationRun(id=uid('RUN'),project_id=p1.id,stage='QUALITY_GATE',environment='DEV',status='PASSED');db.add(r);db.flush()
    db.add(MigrationQualityGate(id=uid('GAT'),project_id=p1.id,run_id=r.id,environment='DEV',status='PASSED',pass_count=10,fail_count=0,blocker_count=0));db.commit()
    assert lifecycle(db,p1.id)[0]['status']=='PASSED'
    assert lifecycle(db,p2.id)[0]['status']=='NOT_STARTED'

def test_layer_override(db):
    p=seed(db);o=db.scalar(select(MigrationObject).where(MigrationObject.project_id==p.id,MigrationObject.object_name=='Orders'))
    c=override_layer(db,p.id,o.id,'SILVER','architect','Curated entity required')
    assert c.selected_layer=='SILVER' and c.classification_method=='USER_OVERRIDE'

def test_test_promotion_requires_dev_and_approvals(db):
    p=seed(db);o=db.scalar(select(MigrationObject).where(MigrationObject.project_id==p.id,MigrationObject.object_name=='Orders'));generate_artifact(db,p.id,o.id)
    pre=promotion_precheck(db,p.id,'TEST');assert not pre['eligible'] and any('DEV' in x for x in pre['blockers'])
