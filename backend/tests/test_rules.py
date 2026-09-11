from app.services.rules import *

def test_datatype_mappings():
    assert map_sqlserver_type('bigint')=='BIGINT'
    assert map_sqlserver_type('decimal',18,4)=='DECIMAL(18,4)'
    assert map_sqlserver_type('uniqueidentifier')=='STRING'
    assert map_sqlserver_type('varbinary(max)')=='BINARY'
    assert map_sqlserver_type('decimal(18,4)')=='DECIMAL(18,4)'

def test_rowversion_is_binary():
    assert map_sqlserver_type('rowversion')=='BINARY'
    assert map_sqlserver_type('timestamp')=='BINARY'

def test_classification_not_table_equals_bronze_only():
    assert classify_layer('VIEW','select sum(amount) from x group by k','SalesAggregate')[0]=='GOLD'
    assert classify_layer('VIEW','select a.id,b.name from a join b on a.id=b.id','vw_clean')[0]=='SILVER'

def test_proc_function_trigger_classification():
    assert classify_procedure('begin tran update x set y=1')[0]=='OPERATIONAL_TRANSACTION'
    assert classify_function('returns table as return select 1 x')[0]=='INLINE_TVF'
    assert classify_trigger('create trigger x as insert into AuditLog values(1)')[0]=='AUDIT'

def test_rewrite_common_tsql_string_concatenation():
    sql = "SELECT e.first_name + ' ' + e.last_name AS full_name, e.salary + 500 AS adjusted_salary FROM [employees] e"
    rewritten = rewrite_common_tsql(sql)
    assert "e.first_name || ' ' || e.last_name AS full_name" in rewritten
    assert "e.salary + 500 AS adjusted_salary" in rewritten
    assert "`employees`" in rewritten

def test_rewrite_tsql_concat_edge_cases():
    assert rewrite_tsql_concat("first_name + N' ' + last_name") == "first_name || N' ' || last_name"
    assert rewrite_tsql_concat("first_name + ' ' + middle_name + ' ' + last_name") == "first_name || ' ' || middle_name || ' ' || last_name"
    assert rewrite_tsql_concat("coalesce(a, '') + ' ' + coalesce(b, '')") == "coalesce(a, '') || ' ' || coalesce(b, '')"
    assert rewrite_tsql_concat("CHAR(10) + first_name") == "CHAR(10) || first_name"
    assert rewrite_tsql_concat("1 + 2 + 3") == "1 + 2 + 3"
    assert rewrite_tsql_concat("'A + B'") == "'A + B'"
    assert rewrite_tsql_concat("-- comment with +\nSELECT 1") == "-- comment with +\nSELECT 1"

def test_rewrite_recursive_cte():
    sql = """
    CREATE VIEW [dbo].[employee_org_chart] AS
    WITH OrgChart (emp_id, mgr_id, lvl) AS (
        SELECT employee_id, manager_id, 0 FROM [employees] WHERE manager_id IS NULL
        UNION ALL
        SELECT e.employee_id, e.manager_id, o.lvl + 1 FROM [employees] e INNER JOIN OrgChart o ON e.manager_id = o.emp_id
    )
    SELECT * FROM OrgChart
    """
    rewritten = rewrite_common_tsql(sql)
    assert "WITH RECURSIVE `OrgChart`" in rewritten or "WITH RECURSIVE OrgChart" in rewritten


