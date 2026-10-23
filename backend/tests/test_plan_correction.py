"""Regression coverage for versioned edits and local deployment preparation."""
import pytest
from sqlalchemy import event, select

from app.models.entities import PromptSpecificationVersion, MigrationMedallionNode, MigrationStageArtifactVersion
from app.services import prompt_specification as service, medallion
from test_prompt_specification import _seed, _answers, PROMPT


def ready(db, monkeypatch):
    project = _seed(db, monkeypatch)
    spec = service.submit(db, project.id, PROMPT, 'architect')
    spec = service.answer_clarifications(db, project.id, spec['id'], _answers(spec), 'architect')
    return project.id, spec


def test_add_move_delete_version_and_regenerate(db, monkeypatch):
    pid, spec = ready(db, monkeypatch)
    count = len(spec['artifacts'])
    added = service.add_plan_artifact(db, pid, spec['id'], {
        'name': 'vw_order_items_extra', 'type': 'VIEW', 'layer': 'SILVER', 'source_refs': ['dbo.OrderItems']}, 'editor')
    item = next(i for i in added['artifacts'] if i['name'] == 'vw_order_items_extra')
    assert len(added['artifacts']) == count + 1
    assert item['source_refs'] == ['OrderItems']
    assert item['grounding_status'] == 'GROUNDED'
    moved = service.update_plan_artifact(db, pid, spec['id'], item['request_id'], {'layer': 'GOLD'}, 'editor')
    item = next(i for i in moved['artifacts'] if i['request_id'] == item['request_id'])
    assert item['target_fqn'] == '`migration_dev`.`gold`.`vw_order_items_extra`'
    assert moved['version'] == spec['version'] + 2
    assert moved['approval'] is None
    service.approve_plan(db, pid, spec['id'], 'editor', 'APPROVED')
    generated = service.generate(db, pid, spec['id'], 'editor')
    row = next(i for i in generated['generated'] if i['request_id'] == item['request_id'])
    sql = db.get(MigrationStageArtifactVersion, row['artifact_version_id']).content
    assert 'CREATE OR REPLACE VIEW `migration_dev`.`gold`.`vw_order_items_extra`' in sql
    deleted = service.delete_plan_artifact(db, pid, spec['id'], item['request_id'], 'editor')
    assert len(deleted['artifacts']) == count
    assert deleted['status'] == 'PENDING_PLAN_APPROVAL'
    assert not medallion.list_medallion_artifacts(db, pid)
    assert service.trace(db, pid, spec['id'])['requirements'] == []
    with pytest.raises(ValueError, match='approved before generation'):
        service.generate(db, pid, spec['id'], 'editor')
    service.approve_plan(db, pid, spec['id'], 'editor', 'APPROVED')
    regenerated = service.generate(db, pid, spec['id'], 'editor')
    assert len(regenerated['generated']) == count
    assert len(medallion.list_medallion_artifacts(db, pid)) == count
    assert db.get(PromptSpecificationVersion, spec['version_id']) is not None


def test_clean_add_and_delete_rewires_dependencies(db, monkeypatch):
    pid, spec = ready(db, monkeypatch)
    clean = next(i for i in spec['artifacts'] if i['name'] == 'vw_order_items_clean')
    removed = service.delete_plan_artifact(db, pid, spec['id'], clean['request_id'])
    assert all(clean['request_id'] not in i['dependencies'] for i in removed['artifacts'])
    added = service.add_plan_artifact(db, pid, spec['id'], {'name': 'vw_order_items_clean', 'type': 'VIEW', 'layer': 'SILVER'})
    new = next(i for i in added['artifacts'] if i['name'] == 'vw_order_items_clean')
    assert new['source_refs'] == ['OrderItems']
    assert new['requirements']['view_kind'] == 'CLEAN'
    assert any(new['request_id'] in i['dependencies'] for i in added['artifacts'])


def test_sixteen_artifacts_add_order_items_clean_to_seventeen(db, monkeypatch):
    project = _seed(db, monkeypatch)
    prompt = PROMPT.replace('cleaned views for Customers, Orders, OrderItems and Products', 'cleaned views for Customers')
    spec = service.submit(db, project.id, prompt, 'architect')
    spec = service.answer_clarifications(db, project.id, spec['id'], _answers(spec), 'architect')
    assert len(spec['artifacts']) == 16
    spec = service.add_plan_artifact(db, project.id, spec['id'], {'name': 'vw_order_items_clean', 'type': 'VIEW', 'layer': 'SILVER'})
    assert len(spec['artifacts']) == 17
    added = next(i for i in spec['artifacts'] if i['name'] == 'vw_order_items_clean')
    assert added['source_refs'] == ['OrderItems']
    assert added['grounding_status'] == 'GROUNDED'


def test_manual_function_uses_existing_calculation_contract(db, monkeypatch):
    pid, spec = ready(db, monkeypatch)
    spec = service.add_plan_artifact(db, pid, spec['id'], {
        'name': 'fn_calculate_discounted_order_amount', 'type': 'FUNCTION', 'layer': 'SILVER', 'source_refs': ['OrderItems']})
    item = next(i for i in spec['artifacts'] if i['name'] == 'fn_calculate_discounted_order_amount')
    assert 'SUM(' in item['requirements']['calculation']
    assert item['requirements']['parameters']
    service.approve_plan(db, pid, spec['id'], 'architect', 'APPROVED')
    generated = service.generate(db, pid, spec['id'], 'architect')
    row = next(i for i in generated['generated'] if i['request_id'] == item['request_id'])
    sql = db.get(MigrationStageArtifactVersion, row['artifact_version_id']).content
    assert 'SUM(' in sql
    assert 'WHERE' in sql


@pytest.mark.parametrize('patch', [
    {'name': ''}, {'layer': 'INVALID'}, {'type': 'INVALID'}, {'source_refs': ['dbo.DoesNotExist']},
    {'name': None}, {'dependencies': ['not-a-request']},
])
def test_invalid_edits_are_atomic(db, monkeypatch, patch):
    pid, spec = ready(db, monkeypatch)
    item = next(i for i in spec['artifacts'] if i['name'] == 'vw_order_items_clean')
    with pytest.raises(ValueError):
        service.update_plan_artifact(db, pid, spec['id'], item['request_id'], patch)
    assert service.detail(db, pid, spec['id'])['checksum'] == spec['checksum']


def test_cycle_cross_layer_and_required_delete_blocked(db, monkeypatch):
    pid, spec = ready(db, monkeypatch)
    clean = next(i for i in spec['artifacts'] if i['name'] == 'vw_order_items_clean')
    with pytest.raises(ValueError, match='cycle'):
        service.update_plan_artifact(db, pid, spec['id'], clean['request_id'], {'dependencies': [clean['request_id']]})
    with pytest.raises(ValueError, match='later Medallion layer'):
        service.update_plan_artifact(db, pid, spec['id'], clean['request_id'], {'layer': 'GOLD'})
    bronze = next(i for i in spec['artifacts'] if i['type'] == 'TABLE_COPY' and i['name'] == 'OrderItems')
    with pytest.raises(ValueError, match='dependent artifacts'):
        service.delete_plan_artifact(db, pid, spec['id'], bronze['request_id'])


def test_refinement_preserves_identity_and_is_atomic(db, monkeypatch):
    pid, spec = ready(db, monkeypatch)
    refined = service.refine_prompt_plan(db, pid, spec['id'], 'Add vw_extra_customers to Silver; move vw_extra_customers to Gold', 'editor')
    assert refined['id'] == spec['id']
    assert refined['version'] == spec['version'] + 1
    assert all(any(i['request_id'] == old['request_id'] for i in refined['artifacts']) for old in spec['artifacts'])
    assert next(i for i in refined['artifacts'] if i['name'] == 'vw_extra_customers')['layer'] == 'GOLD'
    with pytest.raises(ValueError, match='Use commands'):
        service.refine_prompt_plan(db, pid, spec['id'], 'delete vw_extra_customers; make the pipeline wonderful')
    assert service.detail(db, pid, spec['id'])['checksum'] == refined['checksum']


def test_analysis_is_read_only_and_not_artificially_floored(db, monkeypatch):
    project = _seed(db, monkeypatch)
    result = service.analyze_prompt(db, project.id, 'Silver: create vw_unobtainium.')
    assert result['accuracy_score'] < 85
    assert result['status'] == 'REVIEW_RECOMMENDED'
    assert not list(db.scalars(select(PromptSpecificationVersion)).all())


def test_metadata_loading_uses_three_queries_for_multiple_tables(db, monkeypatch):
    from app.models.entities import MigrationSource
    project = _seed(db, monkeypatch)
    source = db.scalar(select(MigrationSource).where(MigrationSource.project_id == project.id))
    statements = []
    def capture(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        payload = service._metadata_payload(db, project.id, source.id)
    finally:
        event.remove(db.bind, 'before_cursor_execute', capture)
    assert len(payload['objects']) == 6
    assert len(statements) == 3


def test_api_validation_authorization_and_scoping(client, auth_headers, db, monkeypatch):
    pid, spec = ready(db, monkeypatch)
    base = f'/api/projects/{pid}/prompt-specifications'
    assert client.post(base + '/analyze', json={'prompt': PROMPT}, headers=auth_headers).status_code == 200
    body = {'name': 'vw_extra_customers', 'type': 'VIEW', 'layer': 'SILVER', 'source_refs': ['Customers']}
    assert client.post(base + f'/{spec["id"]}/artifacts', json=body).status_code == 401
    created = client.post(base + f'/{spec["id"]}/artifacts', json=body, headers=auth_headers)
    assert created.status_code == 200, created.text
    item = next(i for i in created.json()['artifacts'] if i['name'] == body['name'])
    url = base + f'/{spec["id"]}/artifacts/{item["request_id"]}'
    assert client.patch(url, json={'name': None}, headers=auth_headers).status_code == 400
    assert client.patch(url, json={'extra': 1}, headers=auth_headers).status_code == 422
    assert client.delete(url.replace(pid, 'another-project'), headers=auth_headers).status_code == 404
    assert client.patch(url, json={'layer': 'GOLD'}, headers=auth_headers).status_code == 200
    assert client.delete(url, headers=auth_headers).status_code == 200
    assert client.post(base + f'/{spec["id"]}/refine', json={'refinement_prompt': 'Add vw_extra_customers to Silver'}, headers=auth_headers).status_code == 200
