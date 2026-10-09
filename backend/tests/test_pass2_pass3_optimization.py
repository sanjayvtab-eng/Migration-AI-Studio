from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Lock, get_ident
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

from app.services import bronze_ingestion as bronze, deployment, environment_provisioning
from app.services.databricks_client import _project_scope
from test_bronze_ingestion import _seed


@pytest.mark.parametrize('mode', ['FULL_LOAD', 'APPEND'])
@pytest.mark.parametrize('bulk_failure', [False, True])
def test_bulk_staging_fallback_and_publication(db, monkeypatch, mode, bulk_failure):
    project, _, table = _seed(db)
    plan, _ = bronze._requirements(db, project.id)
    state = {'stage': 0, 'target': 12, 'bulk': 0, 'direct': 0}
    statements = []
    monkeypatch.setattr(bronze, 'connector_info', lambda _: {'mode': 'DIRECT'})
    monkeypatch.setattr(bronze, '_source_count', lambda *_: 5000)
    monkeypatch.setattr(environment_provisioning, 'ensure_staging_volume', lambda *_: None)
    monkeypatch.setattr(bronze, '_target_count', lambda _db, _pid, target:
                        state['stage' if '__mf_stage_' in target else 'target'])

    def execute(_db, _pid, sql, **kwargs):
        statements.append(sql)
        if sql.startswith('DROP TABLE'):
            state['stage'] = 0
        if 'AS SELECT * FROM' in sql:
            state['target'] = state['stage']
        if sql.startswith('INSERT INTO'):
            assert kwargs['safe_retry'] is False
            state['target'] += state['stage']
        return []

    def bulk(*args, **kwargs):
        assert '__mf_stage_' in args[5]
        state['bulk'] += 1
        state['stage'] = 5000
        if bulk_failure:
            raise RuntimeError('Connection failed after COPY committed')
        return 5000

    def direct(*args, **kwargs):
        assert '__mf_stage_' in args[5]
        assert state['stage'] == 0
        state['direct'] += 1
        state['stage'] = 5000
        return 5000

    monkeypatch.setattr(environment_provisioning, 'project_execute', execute)
    monkeypatch.setattr(bronze, '_load_table_via_parquet_copy_into', bulk)
    monkeypatch.setattr(bronze, '_load_via_direct_batch_insert', direct)
    result = bronze._load_table(db, project.id, 'RUN_BULK', plan, table, batch_size=500,
                               max_rows=None, load_mode=mode, replace_existing_data=True)
    assert result['status'] == 'PASSED'
    assert state['target'] == (5012 if mode == 'APPEND' else 5000)
    assert state['bulk'] == 1 and state['direct'] == int(bulk_failure)
    assert statements[-1].startswith('DROP TABLE')


@pytest.mark.parametrize('total,limit', [(4999, None), (10000, 100)])
def test_small_or_limited_load_uses_existing_insert(db, monkeypatch, total, limit):
    project, _, table = _seed(db)
    plan, _ = bronze._requirements(db, project.id)
    expected = min(total, limit) if limit is not None else total
    monkeypatch.setattr(bronze, 'connector_info', lambda _: {'mode': 'DIRECT'})
    monkeypatch.setattr(bronze, '_source_count', lambda *_: total)
    monkeypatch.setattr(bronze, '_target_count', lambda *_: expected)
    monkeypatch.setattr(environment_provisioning, 'project_execute', lambda *_args, **_kw: [])
    monkeypatch.setattr(bronze, '_load_table_via_parquet_copy_into', lambda *_args, **_kw: pytest.fail('bulk called'))
    monkeypatch.setattr(bronze, '_load_via_direct_batch_insert', lambda *_args, **_kw: expected)
    assert bronze._load_table(db, project.id, 'RUN_SMALL', plan, table, batch_size=500,
                             max_rows=limit, load_mode='FULL_LOAD', replace_existing_data=True)['rows_loaded'] == expected


def test_parquet_keeps_canonical_values_and_nulls(monkeypatch):
    columns = [SimpleNamespace(column_name=name, data_type=typ, precision=18, scale=4)
               for name, typ in [('id','bigint'),('amount','decimal'),('flag','bit'),
                                ('bin','varbinary'),('day','date'),('stamp','datetime2'),('text','nvarchar')]]
    rows = [(9007199254740993, Decimal('1234567890.1200'), True, b'\x00\xff', date(2026,1,2),
             datetime(2026,1,2,3,4,5,123456), None)]
    class Cursor:
        def fetchmany(self, size):
            assert size == 10000
            result = rows[:]
            rows.clear()
            return result
    @contextmanager
    def source_rows(*_args):
        yield Cursor()
    monkeypatch.setattr(bronze, '_source_rows', source_rows)
    path, count = bronze._export_table_to_parquet(None, None, columns)
    try:
        values = pq.read_table(path).to_pydict()
        assert count == 1
        assert values['id'] == ['9007199254740993']
        assert values['amount'] == ['1234567890.1200']
        assert values['flag'] == ['True']
        assert values['bin'][0].lower() == '00ff'
        assert values['stamp'] == ['2026-01-02 03:04:05.123456']
        assert values['text'] == [None]
    finally:
        Path(path).unlink()


def test_parallel_clones_use_distinct_sessions_and_project_context(db, monkeypatch):
    barrier = Barrier(4)
    lock = Lock()
    observed = []
    def execute(sql, **kwargs):
        session, project_id = _project_scope.get()
        with lock:
            observed.append((id(session), project_id, get_ident(), sql))
        barrier.wait(timeout=10)
        return []
    monkeypatch.setattr(deployment, 'execute_sql', execute)
    prepared = [(None,None,f'`dev`.`bronze`.`t{i}`',f'`test`.`bronze`.`t{i}`',
                 SimpleNamespace(layer='BRONZE',node_type='DELTA_TABLE'),None) for i in range(4)]
    result = deployment._parallel_bronze_clones(db, 'project_a', prepared)
    assert all(value is None for value in result.values())
    assert len({item[0] for item in observed}) == 4
    assert len({item[2] for item in observed}) == 4
    assert all(item[1] == 'project_a' and 'DEEP CLONE' in item[3] for item in observed)


def test_clone_failure_remains_an_error(db, monkeypatch):
    monkeypatch.setattr(deployment, 'execute_sql', lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('clone failed')))
    prepared = [(None,None,'`dev`.`bronze`.`t`','`test`.`bronze`.`t`',
                 SimpleNamespace(layer='BRONZE',node_type='DELTA_TABLE'),None)]
    assert isinstance(deployment._parallel_bronze_clones(db, 'p', prepared)[prepared[0][3]], RuntimeError)


def test_copy_restores_types_and_cleans_files(db, monkeypatch, tmp_path):
    project, source, table = _seed(db)
    columns = [SimpleNamespace(column_name='bytes',data_type='varbinary',precision=None,scale=None),
               SimpleNamespace(column_name='amount',data_type='decimal',precision=18,scale=4)]
    path = tmp_path / 'bulk.parquet'
    path.write_bytes(b'parquet-placeholder')
    calls = []
    monkeypatch.setattr(bronze, '_export_table_to_parquet', lambda *_: (str(path),5000))
    monkeypatch.setattr(bronze, '_upload_to_uc_volume', lambda *args: calls.append(('upload',args[-1])))
    monkeypatch.setattr(bronze, '_volume_file_request', lambda *args: calls.append(('delete',args[-1])))
    monkeypatch.setattr(bronze, '_target_count', lambda *_: 5000)
    monkeypatch.setattr(environment_provisioning, 'project_execute',
                        lambda _db,_pid,sql,**kwargs: calls.append(('sql',sql)))
    assert bronze._load_table_via_parquet_copy_into(
        db,project.id,source,table,columns,'`migration_dev`.`bronze`.`stage`',
        max_rows=None,expected_rows=5000) == 5000
    sql = next(value for kind,value in calls if kind == 'sql')
    assert 'CAST(unhex(`bytes`) AS BINARY)' in sql
    assert 'CAST(`amount` AS DECIMAL(18,4))' in sql
    assert '_migration_source_system' in sql and '_migration_ingested_at' in sql
    assert '/Volumes/migration_dev/bronze/_migration_staging/' in sql
    assert not path.exists() and calls[-1][0] == 'delete'


def test_reconciliation_parallel_counts_record_ordered_failures(monkeypatch):
    barrier = Barrier(6)
    main_thread = get_ident()
    nodes = {f'n{i}': SimpleNamespace(id=f'n{i}',node_type='DELTA_TABLE',layer='SILVER',
                                     source_object_id=None,target_fqn=f'c.s.t{i}',target_name=f't{i}')
             for i in range(6)}
    records = []
    def get(model, key):
        assert get_ident() == main_thread
        return nodes.get(key)
    fake_db = SimpleNamespace(get=get, get_bind=lambda: None,
                              add=lambda row: records.append(row),commit=lambda: None)
    def query(_bind, _pid, sql, **kwargs):
        assert get_ident() != main_thread
        barrier.wait(timeout=10)
        if sql.endswith('t2'):
            raise RuntimeError('count failed')
        return [(10,)]
    monkeypatch.setattr(deployment, '_isolated_execute', query)
    manifest = [(SimpleNamespace(object_id=None), {'medallion_node_id':f'n{i}',
                  'target_fqn':f'c.s.t{i}','layer':'SILVER'}) for i in reversed(range(6))]
    result = deployment._reconcile_medallion_run(fake_db,'p','TEST','run',manifest)
    assert result['status'] == 'FAILED' and result['passed'] == 5 and result['failed'] == 1
    assert [item['target_fqn'] for item in result['details']] == [f'c.s.t{i}' for i in range(6)]
    assert result['details'][2]['error'] == 'count failed'
    assert len(records) == 7


@pytest.mark.parametrize('environment', ['test','uat','prod'])
def test_failed_clone_blocks_dependent_artifacts(db, monkeypatch, environment):
    from app.models.entities import MigrationMedallionNode, MigrationStageArtifactVersion
    project, _, _ = _seed(db)
    bronze_node = SimpleNamespace(id='bn',layer='BRONZE',node_type='DELTA_TABLE')
    silver_node = SimpleNamespace(id='sn',layer='SILVER',node_type='VIEW')
    version = SimpleNamespace(id='v',version=1,content='CREATE VIEW c.s.v AS SELECT * FROM c.s.t')
    original_get = db.get
    def get(model, key):
        if model is MigrationMedallionNode:
            return bronze_node if key == 'bn' else silver_node
        if model is MigrationStageArtifactVersion:
            return version
        return original_get(model,key)
    monkeypatch.setattr(db,'get',get)
    source_env = {'test':'dev','uat':'test','prod':'uat'}[environment]
    manifest = [(SimpleNamespace(object_id=None),{'target_fqn':f'`migration_{source_env}`.`bronze`.`t`',
                 'medallion_node_id':'bn','artifact_version_id':'v'}),
                (SimpleNamespace(object_id=None),{'target_fqn':f'`migration_{source_env}`.`silver`.`v`',
                 'medallion_node_id':'sn','artifact_version_id':'v'})]
    monkeypatch.setattr(deployment,environment+'_promotion_precheck',lambda *_args,**_kw:{'eligible':True})
    monkeypatch.setattr(deployment,'_latest_successful_medallion_run',lambda *_:('source_run',manifest))
    monkeypatch.setattr(deployment,'_promoted_manifest_order',lambda *_:manifest)
    monkeypatch.setattr(deployment,'_target_owner_collision',lambda *_:None)
    monkeypatch.setattr(deployment,'_project_catalogs',lambda *_:tuple('migration_'+e for e in ('dev','test','uat','prod')))
    def execute(sql,**kwargs):
        if 'DEEP CLONE' in sql:
            raise RuntimeError('clone failed')
        return []
    monkeypatch.setattr(deployment,'execute_sql',execute)
    monkeypatch.setattr(deployment,'_execute_promoted_sql',lambda *_args,**_kw:pytest.fail('dependent artifact ran after clone failure'))
    result = getattr(deployment,'promote_medallion_to_'+environment)(db,project.id)
    assert result['status'] == 'FAILED' and 'clone failed' in result['error']

