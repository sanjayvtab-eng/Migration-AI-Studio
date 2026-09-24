import hashlib
import json
from types import SimpleNamespace

import pytest

from app.models.canonical import MigrationDeployment
from app.models.entities import MigrationObject, MigrationStageArtifactVersion
from app.services import databricks_client, deployment, medallion
from app.services.ai_remediation import validate_candidate_content
from app.services.engine import (
    add_source, classify_project, create_mappings, databricks_routine_contract_issues,
    ensure_project, generate_artifact, ingest_snapshot, normalize_databricks_routine_contract,
    _replace_parameters,
)


FQN = '`migration_dev`.`silver`.`fn_CalculateOrderAmount`'
BAD_SQL = f'''CREATE OR REPLACE FUNCTION {FQN}(OrderID INT)
RETURNS DECIMAL(18,2)
LANGUAGE SQL
READS SQL DATA
AS RETURN COALESCE((SELECT SUM(Quantity * UnitPrice * (1 - DiscountPercent / 100))
FROM `migration_dev`.`silver`.`OrderItems` WHERE OrderID = OrderID), 0);'''

# The AI-repaired, approved v3 that failed on the user's live warehouse.
OVERQUALIFIED_SQL = f'''CREATE OR REPLACE FUNCTION {FQN}(OrderID INT)
RETURNS DECIMAL(18,2)
LANGUAGE SQL
READS SQL DATA
RETURN COALESCE(
    (SELECT SUM(oi.Quantity * oi.UnitPrice * (1 - (oi.DiscountPercent / 100)))
     FROM `migration_dev`.`silver`.`OrderItems` AS oi
     WHERE oi.OrderID = {FQN}.`OrderID`), 0);'''

QUALIFIED_DECLARATION_SQL = OVERQUALIFIED_SQL.replace(
    '(OrderID INT)', '(\n    `fn_CalculateOrderAmount`.`OrderID` INT\n)'
).replace(FQN + '.`OrderID`', '`fn_CalculateOrderAmount`.`OrderID`')

PROC_FQN = '`migration_dev`.`silver`.`usp_LoadCustomerSales`'
BAD_PROCEDURE_SQL = f'''CREATE OR REPLACE PROCEDURE {PROC_FQN}()
LANGUAGE SQL
READS SQL DATA
SQL SECURITY INVOKER
AS BEGIN
CREATE OR REPLACE TABLE `migration_dev`.`silver`.`CustomerSales` AS
SELECT CustomerID, SUM(Amount) AS TotalAmount
FROM `migration_dev`.`bronze`.`Orders` GROUP BY CustomerID;
END;'''


@pytest.mark.parametrize('clause', ['READS SQL DATA', 'CONTAINS SQL'])
@pytest.mark.parametrize('has_security', [True, False])
def test_invalid_procedure_data_access_clause_is_blocked_and_repaired(clause, has_security):
    sql = BAD_PROCEDURE_SQL.replace('READS SQL DATA', clause)
    if not has_security:
        sql = sql.replace('SQL SECURITY INVOKER\n', '')
    assert any(clause in issue for issue in databricks_routine_contract_issues(sql, 'PROCEDURE'))
    result = validate_candidate_content(SimpleNamespace(object_type='PROCEDURE'),
                                        SimpleNamespace(target_fqn=PROC_FQN), sql)
    assert result['valid'], result['errors']
    fixed = result['normalized_candidate']
    assert clause not in fixed
    assert fixed.count('SQL SECURITY INVOKER') == 1
    assert fixed.split('AS BEGIN', 1)[1] == sql.split('AS BEGIN', 1)[1]
    assert normalize_databricks_routine_contract(fixed, 'PROCEDURE') == fixed


def test_procedure_clause_repair_preserves_function_clauses_literals_comments_and_body():
    extra = "\n-- READS SQL DATA\n/* CONTAINS SQL */\n"
    sql = BAD_PROCEDURE_SQL.replace('LANGUAGE SQL', "LANGUAGE SQL\nCOMMENT 'READS SQL DATA'")
    sql = sql.replace('END;', "SELECT 'CONTAINS SQL' AS message;\nEND;") + extra
    fixed = normalize_databricks_routine_contract(sql, 'PROCEDURE')
    assert fixed == sql.replace('\nREADS SQL DATA\n', '\n\n')
    assert not databricks_routine_contract_issues(fixed, 'PROCEDURE')
    function = OVERQUALIFIED_SQL.replace(FQN + '.`OrderID`', '`fn_CalculateOrderAmount`.`OrderID`')
    normalized = normalize_databricks_routine_contract(function, 'FUNCTION')
    assert '`p_order_id` INT' in normalized and 'oi.OrderID = `p_order_id`' in normalized
    assert not databricks_routine_contract_issues(normalized, 'FUNCTION')


@pytest.mark.parametrize('use_ai', [False, True])
def test_approved_procedure_is_repaired_as_new_reviewable_version_and_deployed(db, monkeypatch, use_ai):
    project = ensure_project(db, 'Procedure clause repair')
    source = add_source(db, project.id, 'source', 'server', 'MigrationDemo')
    ingest_snapshot(db, project.id, source.id, {'database': 'MigrationDemo', 'objects': [
        {'schema': 'dbo', 'name': 'usp_LoadCustomerSales', 'type': 'PROCEDURE',
         'definition': 'CREATE PROCEDURE dbo.usp_LoadCustomerSales AS BEGIN SELECT 1 AS result; END',
         'parameters': []},
    ]})
    classify_project(db, project.id)
    create_mappings(db, project.id, 'DEV', 'migration_dev')
    medallion.build_medallion_plan(db, project.id, environment='DEV', catalog='migration_dev')
    medallion.generate_medallion_artifacts(db, project.id)
    item = next(x for x in medallion.list_medallion_artifacts(db, project.id) if x['target_fqn'] == PROC_FQN)
    old = db.get(MigrationStageArtifactVersion, item['artifact_version_id'])
    old.content = BAD_PROCEDURE_SQL
    old.content_hash = hashlib.sha256(old.content.encode()).hexdigest()
    old.validation_status = 'PASSED'
    old.review_status = 'APPROVED'
    old.executable = True
    db.commit()
    statements = []
    monkeypatch.setattr(databricks_client, 'execute_sql', lambda sql, **kw: statements.append(sql))
    with pytest.raises(ValueError, match='READS SQL DATA'):
        medallion.deploy_medallion_dev(db, project.id)
    assert not statements and old.validation_status == 'FAILED'
    report = medallion.medallion_validation_report(db, project.id)
    assert any(x['artifact_version_id'] == old.id for x in report['failed_artifacts'])
    from app.services import ai_remediation
    if use_ai:
        monkeypatch.setattr(ai_remediation, '_deterministic_procedure_remediation', lambda *a, **kw: None)
        monkeypatch.setattr(ai_remediation, '_call_llm', lambda *a, **kw: (
            {'generated_candidate': BAD_PROCEDURE_SQL, 'confidence': 0.9}, 'GEMINI', 'qa-model'
        ))
    repaired = medallion.remediate_medallion_artifact(db, project.id, old.id, use_ai=use_ai, reviewer='architect')
    current = db.get(MigrationStageArtifactVersion, repaired['artifact_version_id'])
    assert current.version == old.version + 1 and current.review_status == 'PENDING_REVIEW'
    assert 'READS SQL DATA' not in current.content
    assert current.content.split('AS BEGIN', 1)[1] == BAD_PROCEDURE_SQL.split('AS BEGIN', 1)[1]
    assert old.content == BAD_PROCEDURE_SQL
    with pytest.raises(ValueError, match='not approved'):
        medallion.deploy_medallion_dev(db, project.id)
    medallion.review_medallion_artifact(db, project.id, current.id, status='APPROVED', reviewer='architect')
    medallion.generate_medallion_artifacts(db, project.id)
    effective = next(x for x in medallion.list_medallion_artifacts(db, project.id) if x['target_fqn'] == PROC_FQN)
    assert effective['artifact_version_id'] == current.id
    monkeypatch.setattr(deployment, 'databricks_workspace_identity', lambda: 'qa-workspace')
    result = medallion.deploy_medallion_dev(db, project.id)
    assert result['status'] == 'PASSED', result.get('error')
    assert statements == [current.content]
    records = [json.loads(row.payload_json) for row in db.query(MigrationDeployment).filter_by(project_id=project.id)]
    evidence = next(x for x in records if x.get('artifact_version_id') == current.id)
    assert evidence['artifact_content_hash'] == current.content_hash


def _seed(db):
    project = ensure_project(db, 'Runtime function repair')
    source = add_source(db, project.id, 'source', 'server', 'MigrationDemo')
    ingest_snapshot(db, project.id, source.id, {'database': 'MigrationDemo', 'objects': [
        {'schema': 'dbo', 'name': 'OrderItems', 'type': 'TABLE', 'columns': [
            {'name': 'OrderID', 'type': 'int'}, {'name': 'Quantity', 'type': 'int'},
            {'name': 'UnitPrice', 'type': 'decimal', 'precision': 18, 'scale': 2},
            {'name': 'DiscountPercent', 'type': 'decimal', 'precision': 5, 'scale': 2},
        ]},
        {'schema': 'dbo', 'name': 'fn_CalculateOrderAmount', 'type': 'FUNCTION',
         'definition': '''CREATE FUNCTION dbo.fn_CalculateOrderAmount(@OrderID int)
RETURNS decimal(18,2) AS BEGIN
DECLARE @Amount decimal(18,2);
SELECT @Amount = SUM(Quantity * UnitPrice * (1 - DiscountPercent / 100))
FROM dbo.OrderItems WHERE OrderID = @OrderID;
RETURN ISNULL(@Amount, 0); END''',
         'parameters': [{'name': '@OrderID', 'ordinal': 1, 'type': 'int'}],
         'dependencies': [{'schema': 'dbo', 'object': 'OrderItems', 'type': 'LOCAL'}]},
    ]})
    classify_project(db, project.id)
    create_mappings(db, project.id, 'DEV', 'migration_dev')
    medallion.build_medallion_plan(db, project.id, environment='DEV', catalog='migration_dev')
    medallion.generate_medallion_artifacts(db, project.id)
    item = next(x for x in medallion.list_medallion_artifacts(db, project.id) if x['target_fqn'] == FQN)
    version = db.get(MigrationStageArtifactVersion, item['artifact_version_id'])
    # Model an already-approved artifact that passed the older, incomplete checks.
    version.content = BAD_SQL
    version.content_hash = hashlib.sha256(BAD_SQL.encode()).hexdigest()
    version.executable = True
    version.validation_status = 'PASSED'
    version.review_status = 'APPROVED'
    db.commit()
    return project, version


def test_screenshot_sql_is_rejected_by_current_contract():
    issues = databricks_routine_contract_issues(BAD_SQL, 'FUNCTION')
    assert any('AS RETURN' in issue for issue in issues)
    assert any('Ambiguous function filter' in issue for issue in issues)


def test_ai_candidate_repairs_as_return_but_rejects_ambiguous_filter():
    obj = SimpleNamespace(object_type='FUNCTION')
    mapping = SimpleNamespace(target_fqn=FQN)
    bad = validate_candidate_content(obj, mapping, BAD_SQL)
    assert not bad['valid']
    assert 'AS RETURN' not in bad['normalized_candidate']
    good = validate_candidate_content(obj, mapping, BAD_SQL.replace(
        'WHERE OrderID = OrderID',
        'WHERE OrderItems.OrderID = fn_CalculateOrderAmount.OrderID',
    ))
    assert good['valid'], good['errors']
    assert good['normalized_candidate'].count('READS SQL DATA') == 1


def test_ai_v3_parameter_scope_is_rejected_and_safely_normalized():
    assert any('parameter qualification' in issue for issue in
               databricks_routine_contract_issues(OVERQUALIFIED_SQL, 'FUNCTION'))
    result = validate_candidate_content(SimpleNamespace(object_type='FUNCTION'),
                                        SimpleNamespace(target_fqn=FQN), OVERQUALIFIED_SQL)
    assert result['valid'], result['errors']
    sql = result['normalized_candidate']
    assert 'WHERE oi.OrderID = `p_order_id`' in sql
    assert '`p_order_id` INT' in sql
    assert normalize_databricks_routine_contract(sql, 'FUNCTION') == sql


@pytest.mark.parametrize('prefix', [
    '`fn_CalculateOrderAmount`', 'fn_CalculateOrderAmount',
    '`migration_dev`.`silver`.`fn_CalculateOrderAmount`',
])
def test_ai_v4_qualified_declaration_is_rejected_and_normalized(prefix):
    sql = QUALIFIED_DECLARATION_SQL.replace(
        '`fn_CalculateOrderAmount`.`OrderID` INT', prefix + '.`OrderID` INT'
    )
    assert any('parameter declaration' in issue for issue in
               databricks_routine_contract_issues(sql, 'FUNCTION'))
    fixed = normalize_databricks_routine_contract(sql, 'FUNCTION')
    assert '`p_order_id` INT' in fixed
    assert 'WHERE oi.OrderID = `p_order_id`' in fixed
    assert not databricks_routine_contract_issues(fixed, 'FUNCTION')
    assert normalize_databricks_routine_contract(fixed, 'FUNCTION') == fixed


def test_declaration_repair_does_not_guess_foreign_scope_and_blocks_duplicate_names():
    foreign = QUALIFIED_DECLARATION_SQL.replace(
        '`fn_CalculateOrderAmount`.`OrderID` INT', '`OtherFunction`.`OrderID` INT'
    )
    assert '`OtherFunction`.`OrderID` INT' in normalize_databricks_routine_contract(foreign, 'FUNCTION')
    assert databricks_routine_contract_issues(foreign, 'FUNCTION')
    duplicate = QUALIFIED_DECLARATION_SQL.replace(
        '`fn_CalculateOrderAmount`.`OrderID` INT', '`fn_CalculateOrderAmount`.`OrderID` INT, OrderID INT'
    )
    fixed = normalize_databricks_routine_contract(duplicate, 'FUNCTION')
    assert any('Duplicate function parameter' in issue for issue in
               databricks_routine_contract_issues(fixed, 'FUNCTION'))


def test_declaration_repair_preserves_nested_types_defaults_and_comments():
    sql = QUALIFIED_DECLARATION_SQL.replace(
        '`fn_CalculateOrderAmount`.`OrderID` INT',
        "`fn_CalculateOrderAmount`.`OrderID` INT, amount DECIMAL(18,2) DEFAULT 0, "
        "payload STRUCT<x: INT, y: ARRAY<INT>>, text STRING DEFAULT 'fn_CalculateOrderAmount.x'"
    ) + '\n-- fn_CalculateOrderAmount.OrderID INT\n'
    fixed = normalize_databricks_routine_contract(sql, 'FUNCTION')
    assert '`p_order_id` INT' in fixed and '`p_amount` DECIMAL(18,2)' in fixed
    assert "DEFAULT 'fn_CalculateOrderAmount.x'" in fixed
    assert not databricks_routine_contract_issues(fixed, 'FUNCTION')


def test_declaration_parser_keeps_quoted_commas_and_nested_types_separate():
    sql = QUALIFIED_DECLARATION_SQL.replace(
        '`fn_CalculateOrderAmount`.`OrderID` INT',
        '`a,b` DECIMAL(18,2), payload STRUCT<x: INT, y: INT>, '
        '`fn_CalculateOrderAmount`.`OrderID` INT'
    )
    assert databricks_routine_contract_issues(sql, 'FUNCTION')
    fixed = normalize_databricks_routine_contract(sql, 'FUNCTION')
    assert '`p_a_b` DECIMAL(18,2)' in fixed and '`p_payload` STRUCT<x: INT, y: INT>' in fixed
    assert '`p_order_id` INT' in fixed
    assert not databricks_routine_contract_issues(fixed, 'FUNCTION')


def test_tsql_parameter_reference_rewrite_does_not_qualify_declarations():
    source = '''CREATE FUNCTION dbo.fn_CalculateOrderAmount(@OrderID INT)
RETURNS INT AS BEGIN RETURN (SELECT COUNT(*) FROM dbo.OrderItems
WHERE OrderID = @OrderID); END'''
    fixed = _replace_parameters(source, [{'name': '@OrderID'}], routine_name='fn_CalculateOrderAmount')
    assert 'fn_CalculateOrderAmount(@OrderID INT)' in fixed
    assert 'WHERE OrderID = `p_order_id`' in fixed


@pytest.mark.parametrize('scope', [
    'migration_dev.silver.fn_CalculateOrderAmount.OrderID',
    '`MIGRATION_DEV` . silver . `fn_CalculateOrderAmount` . OrderID',
])
def test_parameter_scope_accepts_mixed_quoting_spacing_and_case(scope):
    sql = OVERQUALIFIED_SQL.replace(FQN + '.`OrderID`', scope)
    assert databricks_routine_contract_issues(sql, 'FUNCTION')
    fixed = normalize_databricks_routine_contract(sql, 'FUNCTION')
    assert not databricks_routine_contract_issues(fixed, 'FUNCTION')
    assert 'WHERE oi.OrderID = ' in fixed
    assert 'silver' not in fixed.split('WHERE')[1]


def test_parameter_normalization_preserves_literals_comments_and_unrelated_fields():
    extra = f"\n-- {FQN}.`OrderID`\n/* {FQN}.`OrderID` */\n"
    sql = OVERQUALIFIED_SQL.replace('), 0);', f"), CAST('{FQN}.`OrderID`' AS INT));") + extra
    fixed = normalize_databricks_routine_contract(sql, 'FUNCTION')
    assert f"'{FQN}.`OrderID`'" in fixed and fixed.endswith(extra)
    other_scope = OVERQUALIFIED_SQL.replace(
        FQN + '.`OrderID`', 'other.silver.fn_CalculateOrderAmount.OrderID'
    )
    assert 'oi.OrderID = `p_order_id`' in normalize_databricks_routine_contract(other_scope, 'FUNCTION')
    for reference in ['`migration_dev`.`silver`.`OrderItems`.`OrderID`',
                      FQN + '.`UnknownParameter`',
                      FQN + '.`OrderID`.`nested_field`']:
        sql = OVERQUALIFIED_SQL.replace(FQN + '.`OrderID`', reference)
        fixed = normalize_databricks_routine_contract(sql, 'FUNCTION')
        assert reference in fixed and '`p_order_id` INT' in fixed


@pytest.mark.parametrize('bad_sql', [OVERQUALIFIED_SQL, QUALIFIED_DECLARATION_SQL])
def test_approved_ai_sql_is_blocked_until_new_version_repaired_and_approved(db, monkeypatch, bad_sql):
    project, old = _seed(db)
    old.content = bad_sql
    old.content_hash = hashlib.sha256(bad_sql.encode()).hexdigest()
    db.commit()
    statements = []
    monkeypatch.setattr(databricks_client, 'execute_sql', lambda sql, **kw: statements.append(sql))
    with pytest.raises(ValueError, match='parameter (qualification|declaration)'):
        medallion.deploy_medallion_dev(db, project.id)
    assert not statements and old.validation_status == 'FAILED'
    assert old.content == bad_sql
    report = medallion.medallion_validation_report(db, project.id)
    assert any(x['artifact_version_id'] == old.id for x in report['failed_artifacts'])
    with pytest.raises(ValueError, match='Approval blocked'):
        medallion.review_medallion_artifact(db, project.id, old.id, status='APPROVED', reviewer='architect')
    # Simulate the provider returning the exact faulty v3 again: candidate
    # normalization must fix it before it becomes a new reviewable version.
    from app.services import ai_remediation
    monkeypatch.setattr(ai_remediation, '_deterministic_function_remediation', lambda *a, **kw: None)
    monkeypatch.setattr(ai_remediation, '_call_llm', lambda *a, **kw: (
        {'generated_candidate': bad_sql, 'confidence': 0.9}, 'GEMINI', 'qa-model'
    ))
    repaired = medallion.remediate_medallion_artifact(db, project.id, old.id, use_ai=True, reviewer='architect')
    current = db.get(MigrationStageArtifactVersion, repaired['artifact_version_id'])
    assert current.id != old.id and current.version == old.version + 1
    assert current.review_status == 'PENDING_REVIEW'
    assert not any('parameter declaration' in issue for issue in
                   databricks_routine_contract_issues(current.content, 'FUNCTION'))
    assert 'WHERE oi.`order_id` = `p_order_id`' in current.content
    assert not databricks_routine_contract_issues(current.content, 'FUNCTION')
    medallion.review_medallion_artifact(db, project.id, current.id, status='APPROVED', reviewer='architect')
    medallion.generate_medallion_artifacts(db, project.id)
    item = next(x for x in medallion.list_medallion_artifacts(db, project.id) if x['target_fqn'] == FQN)
    assert item['artifact_version_id'] == current.id
    for item in medallion.list_medallion_artifacts(db, project.id):
        medallion.review_medallion_artifact(db, project.id, item['artifact_version_id'], status='APPROVED', reviewer='architect')
    monkeypatch.setattr(medallion, '_deploy_legacy_bronze', lambda *a: {'action': 'QA_BRONZE'})
    monkeypatch.setattr(deployment, 'databricks_workspace_identity', lambda: 'qa-workspace')
    result = medallion.deploy_medallion_dev(db, project.id, reuse_bronze=False)
    assert result['status'] == 'PASSED', result.get('error')
    assert current.content in statements and old.content not in statements
    records = [json.loads(row.payload_json) for row in db.query(MigrationDeployment).filter_by(project_id=project.id)]
    evidence = next(x for x in records if x.get('artifact_version_id') == current.id)
    assert evidence['artifact_content_hash'] == current.content_hash


@pytest.mark.parametrize('payload', ["'AS RETURN FROM JOIN'", "'it''s AS RETURN'", "'OrderID = OrderID'"])
def test_function_checks_preserve_string_literals(payload):
    sql = f'CREATE OR REPLACE FUNCTION {FQN}() RETURNS STRING LANGUAGE SQL RETURN {payload};'
    assert normalize_databricks_routine_contract(sql, 'FUNCTION') == sql
    assert not databricks_routine_contract_issues(sql, 'FUNCTION')


def test_comments_do_not_supply_a_missing_function_body():
    sql = f'CREATE OR REPLACE FUNCTION {FQN}() RETURNS INT LANGUAGE SQL -- RETURN 1'
    assert any('missing RETURN' in x for x in databricks_routine_contract_issues(sql, 'FUNCTION'))


def test_comment_cannot_supply_language_and_same_column_comparison_is_rejected():
    sql = f'CREATE OR REPLACE FUNCTION {FQN}() RETURNS INT /* LANGUAGE SQL */ RETURN 1;'
    assert any('missing LANGUAGE SQL' in x for x in databricks_routine_contract_issues(sql, 'FUNCTION'))
    sql = f'CREATE OR REPLACE FUNCTION {FQN}() RETURNS INT LANGUAGE SQL RETURN (SELECT COUNT(*) FROM t WHERE x = x);'
    assert any('Ambiguous function filter' in x for x in databricks_routine_contract_issues(sql, 'FUNCTION'))


def test_function_conversion_keeps_parameter_separate_from_column(db):
    project, _ = _seed(db)
    obj = db.query(MigrationObject).filter_by(project_id=project.id, object_name='fn_CalculateOrderAmount').one()
    obj.definition = '''CREATE FUNCTION dbo.fn_CalculateOrderAmount(@OrderID int)
RETURNS decimal(18,2) AS BEGIN
RETURN (SELECT SUM(UnitPrice) FROM dbo.OrderItems WHERE OrderID = @OrderID); END'''
    db.commit()
    version = generate_artifact(db, project.id, obj.id)
    assert 'WHERE OrderID = `p_order_id`' in version.content
    assert not databricks_routine_contract_issues(version.content, 'FUNCTION')


def test_old_approval_is_revalidated_before_deployment(db, monkeypatch):
    project, old = _seed(db)
    executed = []
    monkeypatch.setattr(databricks_client, 'execute_sql', lambda sql, **kw: executed.append(sql))
    with pytest.raises(ValueError) as failure:
        medallion.deploy_medallion_dev(db, project.id)
    assert 'AS RETURN' in str(failure.value) and old.id in str(failure.value)
    assert not executed
    assert old.validation_status == 'FAILED' and not old.executable
    report = medallion.medallion_validation_report(db, project.id)
    assert any(x['artifact_version_id'] == old.id for x in report['failed_artifacts'])
    with pytest.raises(ValueError, match='Approval blocked'):
        medallion.review_medallion_artifact(db, project.id, old.id, status='APPROVED', reviewer='architect')


def test_repaired_current_version_survives_regeneration_and_is_deployed(db, monkeypatch):
    project, old = _seed(db)
    # Repair must also accept an older PASSED artifact proven invalid by new checks.
    repaired = medallion.remediate_medallion_artifact(db, project.id, old.id, use_ai=False, reviewer='architect')
    assert repaired['review_status'] == 'PENDING_REVIEW'
    assert repaired['version'] == old.version + 1
    current = db.get(MigrationStageArtifactVersion, repaired['artifact_version_id'])
    assert 'AS RETURN' not in current.content
    assert 'WHERE OrderID = `p_order_id`' in current.content
    medallion.review_medallion_artifact(db, project.id, current.id, status='APPROVED', reviewer='architect')
    medallion.generate_medallion_artifacts(db, project.id)
    effective = next(x for x in medallion.list_medallion_artifacts(db, project.id) if x['target_fqn'] == FQN)
    assert effective['artifact_version_id'] == current.id
    for item in medallion.list_medallion_artifacts(db, project.id):
        medallion.review_medallion_artifact(db, project.id, item['artifact_version_id'], status='APPROVED', reviewer='architect')
    statements = []
    monkeypatch.setattr(databricks_client, 'execute_sql', lambda sql, **kw: statements.append(sql))
    monkeypatch.setattr(medallion, '_deploy_legacy_bronze', lambda *a: {'action': 'QA_BRONZE'})
    monkeypatch.setattr(deployment, 'databricks_workspace_identity', lambda: 'qa-workspace')
    result = medallion.deploy_medallion_dev(db, project.id, reuse_bronze=False)
    assert result['status'] == 'PASSED', result.get('error')
    assert current.content in statements
    records = [json.loads(row.payload_json) for row in db.query(MigrationDeployment).filter_by(project_id=project.id)]
    evidence = next(x for x in records if x.get('artifact_version_id') == current.id)
    assert evidence['artifact_version'] == current.version
    assert evidence['artifact_content_hash'] == current.content_hash
