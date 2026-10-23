import json

import pytest
import sqlglot
from sqlglot import exp
from sqlalchemy import select

from app.models.canonical import MigrationRunStep
from app.models.entities import MigrationMedallionNode, MigrationMedallionEdge
from app.services import deployment, medallion, prompt_specification as service
from app.services.sql_preflight import (
    bind_physical_columns, compile_probes, compiler_identifier_repair,
    split_sql, validate_databricks_sql,
)


def snapshot():
    names = ['ServiceEntryID', 'QTY', 'UnitPrice', 'DiscountPercent', 'StateCode']
    return {'objects': [{'type': 'TABLE', 'schema': 'dbo', 'name': 'ServiceEntries',
                         'columns': [{'name': name, 'target_name': service._snake(name), 'data_type': 'int', 'nullable': True} for name in names]}]}


def function_request(calculation='SUM(qty)'):
    return {'name': 'fn_net_amount', 'type': 'FUNCTION', 'layer': 'SILVER', 'source_refs': ['ServiceEntries'],
            'requirements': {'parameters': [{'name': 'p_entry_id', 'type': 'INT'}], 'returns': 'DECIMAL(18,2)',
                             'calculation': calculation, 'filter': 'service_entry_id = p_entry_id'}}


@pytest.mark.parametrize('relation,expected', [
    ('`cat`.`bronze`.`service_entries`', 'ServiceEntryID'),
    ('CAT . BRONZE . service_entries', 'ServiceEntryID'),
    ('`cat`.`silver`.`vw_service_entries_clean`', 'service_entry_id'),
    ('`cat`.`gold`.`dim_service_entries`', 'service_entry_id'),
])
def test_physical_resolver_handles_quoted_layers(relation, expected):
    assert service._col_name_for_rel(relation, snapshot()['objects'][0], 'service_entry_id') == expected


@pytest.mark.parametrize('clean', [set(), {'vw_service_entries_clean'}])
@pytest.mark.parametrize('generator', ['function', 'view', 'dimension', 'fact', 'workflow'])
def test_all_generators_use_physical_schema(clean, generator):
    data = snapshot()
    if generator == 'function':
        sql = service._generate_generic_function_sql('cat', function_request(), data, clean)
    else:
        name = {'view': 'vw_service_entries', 'dimension': 'dim_service_entries', 'fact': 'fact_service_entries', 'workflow': 'usp_load_service_entries'}[generator]
        request = {'name': name, 'type': generator.upper(), 'layer': 'SILVER' if generator in {'view', 'workflow'} else 'GOLD', 'source_refs': ['ServiceEntries'], 'requirements': {}}
        functions = {'view': service._generate_generic_view_sql, 'dimension': service._generate_generic_dimension_sql,
                     'fact': service._generate_generic_fact_sql, 'workflow': service._generate_procedure_or_workflow_sql}
        result = functions[generator]('cat', request, data, {}, clean)
        sql = result[0] if isinstance(result, tuple) else result
    schemas = service._physical_schemas('cat', data)
    assert validate_databricks_sql(sql, schemas) == [], sql
    if clean:
        assert 'vw_service_entries_clean' in sql
        assert 'service_entry_id' in sql
    else:
        assert '`bronze`.`service_entries`' in sql
        assert '`ServiceEntryID`' in sql


@pytest.mark.parametrize('quantity,price,discount', [('Quantity', 'UnitPrice', 'DiscountPercent'), ('Qty', 'RATE', 'Discount'), ('QTY', 'Price', None)])
def test_metric_inference_uses_quantity_price_and_optional_discount(quantity, price, discount):
    data = snapshot()
    names = ['ServiceEntryID', quantity, price] + ([discount] if discount else [])
    data['objects'][0]['columns'] = [{'name': name, 'target_name': service._snake(name), 'data_type': 'int'} for name in names]
    request = function_request('')
    sql = service._generate_generic_function_sql('cat', request, data, set())
    assert f'`{quantity}`' in sql and f'`{price}`' in sql and '*' in sql
    if discount:
        assert f'`{discount}`' in sql and 'COALESCE' in sql and '/ 100' in sql
    else:
        assert '/ 100' not in sql
    assert 'DECIMAL(18, 2)' in sql or 'DECIMAL(18,2)' in sql


def test_explicit_formula_and_parameters_are_preserved():
    sql = service._generate_generic_function_sql('cat', function_request('SUM(qty * unit_price) + 7'), snapshot(), set())
    assert '+ 7' in sql
    assert 'DiscountPercent' not in sql
    assert 'p_entry_id' in sql and '.p_entry_id' not in sql


def test_source_calculation_can_aggregate_without_a_filter():
    request = function_request('')
    request['requirements'].update({'parameters': [], 'filter': ''})
    sql = service._generate_generic_function_sql('cat', request, snapshot(), set())
    assert 'SUM(' in sql and 'FROM `cat`.`bronze`.`service_entries`' in sql
    assert 'WHERE TRUE' in sql


def test_parameter_only_arithmetic_remains_a_scalar_expression():
    request = function_request('p_amount + 2')
    request['requirements'].update({'parameters': [{'name': 'p_amount', 'type': 'INT'}], 'filter': ''})
    sql = service._generate_generic_function_sql('cat', request, snapshot(), set())
    assert 'FROM ' not in sql and 'p_amount + 2' in sql


def test_binder_preserves_literals_parameters_and_output_aliases():
    sql = "CREATE FUNCTION cat.silver.f(p_id INT) RETURNS INT RETURN (SELECT SUM(t.unit_price) FROM cat.bronze.t t WHERE t.item_id = p_id AND t.state = 'unit_price');"
    result = bind_physical_columns(sql, {'cat.bronze.t': ['UnitPrice', 'ItemID', 'State']})
    assert "'unit_price'" in result
    assert 'p_id' in result and 't.`UnitPrice`' in result and 't.`ItemID`' in result
    view = bind_physical_columns('CREATE VIEW cat.silver.v AS SELECT item_id FROM cat.bronze.t', {'cat.bronze.t': ['ItemID']})
    assert '`ItemID` AS `item_id`' in view


@pytest.mark.parametrize('sql', ['SELECT (', 'CREATE VIEW x AS SELECT a FROM', ''])
def test_invalid_sql_is_rejected(sql):
    assert validate_databricks_sql(sql)


def test_unknown_columns_and_scalar_function_aggregation_are_rejected():
    assert validate_databricks_sql('SELECT t.missing FROM cat.bronze.t t', {'cat.bronze.t': ['Id']})
    assert validate_databricks_sql('CREATE FUNCTION f(p INT) RETURNS INT RETURN (SELECT ROUND(t.x, 2) FROM cat.bronze.t t WHERE t.id=p)')
    assert validate_databricks_sql('SELECT * FROM cat.silver.unknown', {}, require_known_relations=True)


def test_function_compile_probe_binds_parameters_without_running_ddl():
    sql = service._generate_generic_function_sql('cat', function_request(), snapshot(), set())
    probes = compile_probes(sql)
    assert len(probes) == 1 and probes[0].startswith('EXPLAIN SELECT')
    assert 'p_entry_id' not in probes[0]
    assert 'CAST(NULL AS INT)' in probes[0]
    assert 'CREATE FUNCTION' not in probes[0]


def compiler_error(suggestions="'c'.'ClaimServiceID'"):
    return f"[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column with name 'c'.'claim_service_id' cannot be resolved. Did you mean one of the following? [{suggestions}]"


def test_compiler_repair_is_qualified_and_preserves_literals():
    sql = "SELECT c.claim_service_id, d.claim_service_id, 'claim_service_id' FROM cat.bronze.c c JOIN cat.bronze.d d ON c.claim_service_id=d.claim_service_id"
    patched, metadata = compiler_identifier_repair(sql, compiler_error())
    assert 'c.`ClaimServiceID`' in patched and 'd.claim_service_id' in patched and "'claim_service_id'" in patched
    assert metadata['replacement_count'] == 2


@pytest.mark.parametrize('error', [
    '[UNRESOLVED_COLUMN.WITH_SUGGESTION] unknown error format',
    compiler_error("'c'.'OtherID'"), compiler_error("'d'.'ClaimServiceID'"),
    compiler_error("'c'.'ClaimServiceID', 'c'.'Claim_Service_ID'"),
    'Connection timed out',
])
def test_ambiguous_or_unrelated_compiler_errors_are_not_repaired(error):
    assert compiler_identifier_repair('SELECT c.claim_service_id FROM cat.bronze.t c', error) is None


def test_healing_audits_one_retry_without_replaying_prior_statement(db):
    calls = []
    def execute(sql, **kwargs):
        calls.append(sql)
        if 'c.claim_service_id' in sql:
            raise RuntimeError(compiler_error())
    sql = 'CREATE TABLE cat.silver.bootstrap (id INT); SELECT c.claim_service_id FROM cat.bronze.t c;'
    repaired = deployment._safe_execute_with_auto_healing(db, sql, project_id='P', run_id='R', executor=execute)
    assert len(calls) == 3
    assert sum('CREATE TABLE' in call for call in calls) == 1
    assert len(repaired) == 1
    rows = list(db.scalars(select(MigrationRunStep).where(MigrationRunStep.project_id == 'P')).all())
    assert {row.status for row in rows} == {'RUNNING', 'PASSED'}
    evidence = json.loads(rows[-1].payload_json)
    assert evidence['run_id'] == 'R' and evidence['original_sql_hash'] != evidence['patched_sql_hash']


def test_failed_retry_is_bounded_and_audited(db):
    calls = []
    def execute(sql, **kwargs):
        calls.append(sql)
        raise RuntimeError(compiler_error())
    with pytest.raises(RuntimeError):
        deployment._safe_execute_with_auto_healing(db, 'SELECT c.claim_service_id FROM cat.bronze.t c', project_id='P', run_id='R', executor=execute)
    assert len(calls) == 2
    assert 'FAILED' in {row.status for row in db.scalars(select(MigrationRunStep)).all()}


def test_destructive_sql_is_not_executed_without_approval(db):
    calls = []
    with pytest.raises(RuntimeError, match='explicit governed replacement'):
        deployment._safe_execute_with_auto_healing(db, 'DELETE FROM cat.silver.t', project_id='P', run_id='R', executor=lambda *a, **k: calls.append(a))
    assert not calls


def test_statement_splitting_preserves_semicolons_in_literals():
    assert split_sql("SELECT 'a;b'; SELECT 2;") == ["SELECT 'a;b'", 'SELECT 2']


def test_nested_scopes_do_not_expose_unrelated_aliases():
    schemas = {'cat.bronze.t': ['Id']}
    assert validate_databricks_sql('SELECT source.Id FROM (SELECT Id FROM cat.bronze.t) source', schemas) == []
    assert validate_databricks_sql('SELECT wrong.Id FROM cat.bronze.t t', schemas)
    assert validate_databricks_sql('SELECT FROM cat.bronze.t', schemas)


def test_merge_physical_columns_are_checked():
    sql = 'MERGE INTO cat.silver.target t USING cat.silver.source s ON t.id=s.id WHEN MATCHED THEN UPDATE SET t.missing=s.id'
    assert validate_databricks_sql(sql, {'cat.silver.target': ['id'], 'cat.silver.source': ['id']})


def test_alias_shadowing_declines_global_runtime_repair():
    sql = 'SELECT c.claim_service_id FROM cat.bronze.one c WHERE EXISTS (SELECT 1 FROM cat.bronze.two c WHERE c.claim_service_id=1)'
    assert compiler_identifier_repair(sql, compiler_error()) is None


def test_dag_priorities_respect_real_dependencies():
    kinds = [('B', 'BRONZE', 'TABLE_COPY', 'DELTA_TABLE'), ('F', 'SILVER', 'FUNCTION', 'SQL_FUNCTION'),
             ('C', 'SILVER', 'VIEW', 'VIEW'), ('V', 'SILVER', 'VIEW', 'VIEW'), ('W', 'SILVER', 'PROCEDURE_OR_WORKFLOW', 'WORKFLOW_SQL'),
             ('D', 'GOLD', 'DIMENSION', 'SEMANTIC_MODEL'), ('T', 'GOLD', 'FACT', 'SEMANTIC_MODEL'), ('R', 'GOLD', 'SUMMARY_VIEW', 'VIEW')]
    nodes = [MigrationMedallionNode(id=id, layer=layer, model_role=role, node_type=kind, target_name='vw_t_clean' if id == 'C' else id,
                                   target_fqn=f'cat.{layer.lower()}.{id}', transformation_json='{}') for id, layer, role, kind in kinds]
    ordered, cycles = medallion._topological_stage_order(list(reversed(nodes)), [])
    assert [node.id for node in ordered] == ['B', 'F', 'C', 'V', 'W', 'D', 'T', 'R'] and not cycles
    edge = MigrationMedallionEdge(from_node_id='C', to_node_id='F')
    ordered, _ = medallion._topological_stage_order(nodes, [edge])
    assert [node.id for node in ordered].index('C') < [node.id for node in ordered].index('F')
