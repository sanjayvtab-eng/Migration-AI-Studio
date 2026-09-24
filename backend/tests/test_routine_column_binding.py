import hashlib
import json
import sqlite3

import pytest

from app.models.canonical import MigrationDeployment
from app.models.entities import MigrationStageArtifactVersion
from app.services import databricks_client, deployment, medallion
from app.services.routine_columns import bind_columns
from test_routine_runtime_contract import FQN, OVERQUALIFIED_SQL, _seed


ITEMS = ('migration_dev', 'silver', 'orderitems')
SCHEMA = {'orderid': 'order_id', 'order_id': 'order_id', 'unitprice': 'unit_price',
          'unit_price': 'unit_price', 'quantity': 'quantity',
          'discountpercent': 'discount_percent', 'discount_percent': 'discount_percent'}
SCHEMA_SQL = OVERQUALIFIED_SQL.replace('(OrderID INT)', '(`p_order_id` INT)').replace(
    FQN + '.`OrderID`', '`p_order_id`'
)


def test_function_columns_bind_without_renaming_parameters_values_or_output_aliases():
    sql = SCHEMA_SQL.replace('oi.UnitPrice', 'oi.`UnitPrice`') + "\n-- oi.UnitPrice\n/* oi.OrderID */"
    sql = sql.replace('), 0);', "), CAST('oi.UnitPrice' AS DECIMAL(18,2)));")
    fixed, errors = bind_columns(sql, {ITEMS: SCHEMA})
    assert not errors
    assert '(`p_order_id` INT)' in fixed
    assert 'oi.`unit_price`' in fixed
    assert 'oi.`order_id` = `p_order_id`' in fixed
    assert 'oi.`discount_percent`' in fixed
    assert "'oi.UnitPrice'" in fixed and fixed.endswith('-- oi.UnitPrice\n/* oi.OrderID */')
    assert bind_columns(fixed, {ITEMS: SCHEMA}) == (fixed, [])


def test_unqualified_query_uses_silver_columns_and_keeps_aggregate_alias():
    query = 'SELECT SUM(Quantity * UnitPrice * (1 - DiscountPercent / 100.0)) AS UnitPrice FROM OrderItems WHERE OrderID = 1'
    fixed, errors = bind_columns(query, {('orderitems',): SCHEMA})
    assert not errors and 'AS UnitPrice' in fixed
    conn = sqlite3.connect(':memory:')
    try:
        conn.execute('CREATE TABLE OrderItems(order_id INT, quantity INT, unit_price DECIMAL, discount_percent DECIMAL)')
        conn.executemany('INSERT INTO OrderItems VALUES (?, ?, ?, ?)', [(1, 2, 10, 10), (2, 1, 100, 0)])
        assert conn.execute(fixed).fetchone()[0] == 18
        assert conn.execute(fixed.replace('= 1', '= 2')).fetchone()[0] == 100
    finally:
        conn.close()


def test_inline_return_query_preserves_declaration_and_order_by_output_alias():
    sql = f'''CREATE OR REPLACE FUNCTION {FQN}(`p_order_id` INT)
RETURNS TABLE LANGUAGE SQL RETURN SELECT UnitPrice * 2 AS UnitPrice
FROM `migration_dev`.`silver`.`OrderItems` WHERE OrderID = `p_order_id`
ORDER BY UnitPrice;'''
    fixed, errors = bind_columns(sql, {ITEMS: SCHEMA})
    assert not errors
    assert '(`p_order_id` INT)' in fixed and 'SELECT `unit_price` * 2 AS UnitPrice' in fixed
    assert 'WHERE `order_id` = `p_order_id`' in fixed
    assert 'ORDER BY UnitPrice' in fixed


def test_routine_parameter_qualifier_is_preserved_when_relation_name_matches():
    sql = '''CREATE OR REPLACE FUNCTION `migration_dev`.`silver`.`OrderItems`(`p_order_id` INT)
RETURNS INT LANGUAGE SQL RETURN (SELECT COUNT(*) FROM `migration_dev`.`silver`.`OrderItems`
WHERE order_id = `p_order_id`);'''
    assert bind_columns(sql, {ITEMS: SCHEMA}) == (sql, [])


def test_comma_join_is_ambiguous_and_local_query_columns_precede_outer_columns():
    ambiguous = 'SELECT UnitPrice FROM `migration_dev`.`silver`.`OrderItems` a, `migration_dev`.`silver`.`OrderItems` b'
    fixed, errors = bind_columns(ambiguous, {ITEMS: SCHEMA})
    assert fixed == ambiguous and errors
    sql = '''SELECT a.UnitPrice FROM `migration_dev`.`silver`.`OrderItems` a
WHERE EXISTS (SELECT UnitPrice FROM `migration_dev`.`silver`.`OrderItems` b WHERE b.OrderID = a.OrderID)'''
    fixed, errors = bind_columns(sql, {ITEMS: SCHEMA})
    assert not errors
    assert 'SELECT `unit_price` FROM' in fixed and 'b.`order_id` = a.`order_id`' in fixed


def test_bronze_source_columns_keep_their_names_and_other_projects_remain_unbound():
    sql = 'SELECT a.UnitPrice FROM `migration_dev`.`bronze`.`OrderItems` a'
    assert bind_columns(sql, {ITEMS: SCHEMA}) == (sql, [])
    bronze_schema = {'unitprice': 'UnitPrice', 'quantity': 'Quantity'}
    assert bind_columns(sql, {('migration_dev', 'bronze', 'orderitems'): bronze_schema}) == (sql, [])


def test_procedure_insert_columns_and_joins_bind_to_each_relation():
    query = '''INSERT INTO `migration_dev`.`silver`.`CustomerSales` (CustomerID, TotalSales)
SELECT c.CustomerID, SUM(oi.Quantity * oi.UnitPrice) AS TotalSales
FROM `migration_dev`.`silver`.`Customers` c
JOIN `migration_dev`.`silver`.`Orders` o ON c.CustomerID = o.CustomerID
JOIN `migration_dev`.`silver`.`OrderItems` oi ON o.OrderID = oi.OrderID
WHERE o.OrderStatus = 'COMPLETED' GROUP BY c.CustomerID;'''
    schemas = {ITEMS: SCHEMA,
               ('migration_dev', 'silver', 'customers'): {'customerid': 'customer_id', 'customer_id': 'customer_id'},
               ('migration_dev', 'silver', 'orders'): {'orderid': 'order_id', 'customerid': 'customer_id', 'orderstatus': 'order_status'},
               ('migration_dev', 'silver', 'customersales'): {'customerid': 'customer_id', 'totalsales': 'total_sales'}}
    fixed, errors = bind_columns(query, schemas)
    assert not errors
    assert '(`customer_id`, `total_sales`)' in fixed
    assert 'c.`customer_id` = o.`customer_id`' in fixed
    assert 'o.`order_id` = oi.`order_id`' in fixed
    assert "o.`order_status` = 'COMPLETED'" in fixed
    assert 'AS TotalSales' in fixed


def test_procedure_insert_overwrite_columns_and_joins_bind_to_each_relation():
    for prefix in ['INSERT OVERWRITE', 'INSERT OVERWRITE TABLE']:
        query = f'''{prefix} `migration_dev`.`silver`.`OrderSummary`
(OrderID, CustomerID, OrderDate, OrderAmount, LoadDate)
SELECT o.OrderID, o.CustomerID, CAST(o.OrderDate AS DATE),
SUM(oi.Quantity * oi.UnitPrice * (1 - (oi.DiscountPercent / 100))),
current_timestamp()
FROM `migration_dev`.`silver`.`Orders` o
INNER JOIN `migration_dev`.`silver`.`OrderItems` oi ON o.OrderID = oi.OrderID
WHERE o.OrderStatus = 'COMPLETED'
GROUP BY o.OrderID, o.CustomerID, CAST(o.OrderDate AS DATE);'''
        schemas = {
            ITEMS: SCHEMA,
            ('migration_dev', 'silver', 'orders'): {
                'orderid': 'order_id', 'order_id': 'order_id',
                'customerid': 'customer_id', 'customer_id': 'customer_id',
                'orderdate': 'order_date', 'order_date': 'order_date',
                'orderstatus': 'order_status', 'order_status': 'order_status',
            },
            ('migration_dev', 'silver', 'ordersummary'): {
                'orderid': 'order_id', 'order_id': 'order_id',
                'customerid': 'customer_id', 'customer_id': 'customer_id',
                'orderdate': 'order_date', 'order_date': 'order_date',
                'orderamount': 'order_amount', 'order_amount': 'order_amount',
                'loaddate': 'load_date', 'load_date': 'load_date',
            },
        }
        fixed, errors = bind_columns(query, schemas)
        assert not errors, f"Failed for {prefix}: {errors}"
        assert '(`order_id`, `customer_id`, `order_date`, `order_amount`, `load_date`)' in fixed
        assert 'o.`order_id` = oi.`order_id`' in fixed
        assert 'o.`order_id`' in fixed


def test_alias_reuse_does_not_leak_between_statements_subqueries_or_union_branches():
    sql = '''SELECT oi.UnitPrice FROM `migration_dev`.`silver`.`OrderItems` oi
WHERE EXISTS (SELECT oi.UnitPrice FROM `other`.`bronze`.`OrderItems` oi);
SELECT oi.UnitPrice FROM `other`.`bronze`.`OrderItems` oi;
SELECT oi.UnitPrice FROM `migration_dev`.`silver`.`OrderItems` oi
UNION ALL SELECT oi.UnitPrice FROM `other`.`bronze`.`OrderItems` oi;'''
    fixed, errors = bind_columns(sql, {ITEMS: SCHEMA})
    assert not errors
    assert fixed.count('oi.`unit_price`') == 2 and fixed.count('oi.UnitPrice') == 3


def test_derived_relation_alias_shadows_parent_and_correlated_reference_keeps_binding():
    sql = '''SELECT oi.UnitPrice FROM `migration_dev`.`silver`.`OrderItems` oi
WHERE EXISTS (SELECT oi.UnitPrice FROM (SELECT 1 AS UnitPrice) oi)
AND EXISTS (SELECT 1 WHERE oi.OrderID = 1);'''
    fixed, errors = bind_columns(sql, {ITEMS: SCHEMA})
    assert not errors
    assert 'SELECT oi.UnitPrice FROM (SELECT 1 AS UnitPrice) oi' in fixed
    assert 'WHERE oi.`order_id` = 1' in fixed


def test_ambiguous_bare_column_and_unknown_qualified_column_are_not_guessed():
    ambiguous = 'SELECT UnitPrice FROM `migration_dev`.`silver`.`OrderItems` a JOIN `migration_dev`.`silver`.`OrderItems` b ON a.OrderID = b.OrderID'
    fixed, errors = bind_columns(ambiguous, {ITEMS: SCHEMA})
    assert errors and 'Ambiguous routine column' in errors[0]
    assert 'SELECT UnitPrice' in fixed
    missing = 'SELECT oi.DiscountPercent FROM `migration_dev`.`silver`.`OrderItems` oi'
    schema = {key: value for key, value in SCHEMA.items() if value != 'discount_percent'}
    fixed, errors = bind_columns(missing, {ITEMS: schema})
    assert fixed == missing and 'Unknown routine column DiscountPercent' in errors[0]


@pytest.mark.parametrize('use_ai', [False, True])
def test_approved_v5_schema_mismatch_requires_new_approval_and_executes_current_version(db, monkeypatch, use_ai):
    project, old = _seed(db)
    old.content = SCHEMA_SQL
    old.content_hash = hashlib.sha256(old.content.encode()).hexdigest()
    db.commit()
    statements = []
    monkeypatch.setattr(databricks_client, 'execute_sql', lambda sql, **kw: statements.append(sql))
    with pytest.raises(ValueError, match='column names do not match'):
        medallion.deploy_medallion_dev(db, project.id)
    assert not statements and old.validation_status == 'FAILED' and old.content == SCHEMA_SQL
    from app.services import ai_remediation
    monkeypatch.setattr(ai_remediation, '_call_llm', lambda *a, **kw: pytest.fail('Schema-only repair must preserve current SQL deterministically'))
    repaired = medallion.remediate_medallion_artifact(db, project.id, old.id, use_ai=use_ai)
    current = db.get(MigrationStageArtifactVersion, repaired['artifact_version_id'])
    assert current.version == old.version + 1 and current.review_status == 'PENDING_REVIEW'
    assert current.content == bind_columns(SCHEMA_SQL, {ITEMS: SCHEMA})[0]
    assert not medallion.medallion_routine_issues(db, project.id, 'DEV', current.content, 'FUNCTION')
    with pytest.raises(ValueError, match='not approved'):
        medallion.deploy_medallion_dev(db, project.id)
    medallion.review_medallion_artifact(db, project.id, current.id, status='APPROVED', reviewer='architect')
    medallion.generate_medallion_artifacts(db, project.id)
    effective = next(row for row in medallion.list_medallion_artifacts(db, project.id) if row['target_fqn'] == FQN)
    assert effective['artifact_version_id'] == current.id
    for row in medallion.list_medallion_artifacts(db, project.id):
        medallion.review_medallion_artifact(db, project.id, row['artifact_version_id'], status='APPROVED', reviewer='architect')
    monkeypatch.setattr(medallion, '_deploy_legacy_bronze', lambda *a: {'action': 'QA_BRONZE'})
    monkeypatch.setattr(deployment, 'databricks_workspace_identity', lambda: 'qa-workspace')
    result = medallion.deploy_medallion_dev(db, project.id, reuse_bronze=False)
    assert result['status'] == 'PASSED'
    assert current.content in statements and old.content not in statements
    silver = next(sql for sql in statements if sql.startswith('CREATE OR REPLACE VIEW `migration_dev`.`silver`.`OrderItems`'))
    assert statements.index(silver) < statements.index(current.content)
    evidence = [json.loads(row.payload_json) for row in db.query(MigrationDeployment).filter_by(project_id=project.id)]
    assert any(row.get('artifact_version_id') == current.id and row.get('artifact_content_hash') == current.content_hash for row in evidence)


def test_current_sql_dependency_cycle_blocks_before_any_artifact_execution(db, monkeypatch):
    project, old = _seed(db)
    old.content = bind_columns(SCHEMA_SQL, {ITEMS: SCHEMA})[0]
    old.content_hash = hashlib.sha256(old.content.encode()).hexdigest()
    for row in medallion.list_medallion_artifacts(db, project.id):
        version = db.get(MigrationStageArtifactVersion, row['artifact_version_id'])
        version.review_status = 'APPROVED'
        if row['target_fqn'] == '`migration_dev`.`silver`.`OrderItems`':
            version.content = f'''CREATE OR REPLACE VIEW {row['target_fqn']} AS
SELECT {FQN}(OrderID) AS order_id FROM `migration_dev`.`bronze`.`OrderItems`;'''
            version.content_hash = hashlib.sha256(version.content.encode()).hexdigest()
    db.commit()
    statements = []
    monkeypatch.setattr(databricks_client, 'execute_sql', lambda sql, **kw: statements.append(sql))
    with pytest.raises(ValueError, match='dependency cycle'):
        medallion.deploy_medallion_dev(db, project.id, reuse_bronze=False)
    assert not statements
