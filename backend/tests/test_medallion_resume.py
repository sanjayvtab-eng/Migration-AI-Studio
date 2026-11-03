import pytest
from app.services import medallion, databricks_client
from app.models.canonical import MigrationDeployment
from app.models.entities import MigrationMedallionNode
from tests.test_workflow_deployment_integration import _seed, _approved_medallion


def test_medallion_deployment_resumes_from_failed_object(db, monkeypatch):
    """Verify that when resuming a deployment, already passed objects are skipped
    and only the unexecuted/failed objects are executed.
    """
    project, _, table = _seed(db)
    _approved_medallion(db, project)

    # Fetch nodes in DEV
    nodes = db.scalars(
        medallion.select(MigrationMedallionNode).where(
            MigrationMedallionNode.project_id == project.id,
            MigrationMedallionNode.environment == "DEV",
        )
    ).all()
    assert len(nodes) >= 2, "Need at least 2 nodes to test partial resume"

    node1 = nodes[0]
    node2 = nodes[1]

    from app.services import deployment
    monkeypatch.setattr(deployment,"databricks_workspace_identity",lambda:"workspace-test")
    # Pre-record node1 as PASSED in DEV
    db.add(MigrationDeployment(
        id=medallion.uid("DPL"),
        project_id=project.id,
        object_id=node1.source_object_id,
        environment="DEV",
        status="PASSED",
        payload_json=medallion._json({
            "run_id": "MDR_PRIOR_RUN",
            "medallion_node_id": node1.id,
            "target_fqn": node1.target_fqn,
            "artifact_version_id": "V1",
            "artifact_content_hash": "hash1",
            "layer": node1.layer,
            "databricks_workspace":"workspace-test",
            "source_hash":table.source_hash, "max_rows":None,
        })
    ))
    db.commit()

    # Mock execute_sql and bronze loaders
    executed_statements = []
    def mock_execute_sql(sql, *args, **kwargs):
        executed_statements.append(sql)
        return None

    monkeypatch.setattr(databricks_client, "execute_sql", mock_execute_sql)
    monkeypatch.setattr(medallion, "_revalidate_current_routines", lambda *a: [])
    monkeypatch.setattr(medallion, "list_medallion_artifacts", lambda *a, **k: [
        {
            "node_id": node1.id,
            "target_fqn": node1.target_fqn,
            "version": 1,
            "artifact_version_id": "V1",
            "content_hash": "hash1",
            "content": f"CREATE TABLE IF NOT EXISTS {node1.target_fqn} (id INT);",
            "review_status": "APPROVED",
            "validation_status": "PASSED",
            "executable": True,
            "node_type": "TABLE",
        },
        {
            "node_id": node2.id,
            "target_fqn": node2.target_fqn,
            "version": 1,
            "artifact_version_id": "V2",
            "content_hash": "hash2",
            "content": f"CREATE TABLE IF NOT EXISTS {node2.target_fqn} (id INT);",
            "review_status": "APPROVED",
            "validation_status": "PASSED",
            "executable": True,
            "node_type": "TABLE",
        },
    ])

    # Deploy with resume_from_failed=True
    result = medallion.deploy_medallion_dev(db, project.id, resume_from_failed=True)

    assert result["status"] == "PASSED"
    # Node 1 should be skipped because it was already passed with identical version & hash
    skipped_items = [x for x in result["deployed"] if x.get("skipped")]
    assert len(skipped_items) == 1
    assert skipped_items[0]["target_fqn"] == node1.target_fqn

    # Node 2 should be executed normally
    executed_items = [x for x in result["deployed"] if not x.get("skipped")]
    assert len(executed_items) == 1
    assert executed_items[0]["target_fqn"] == node2.target_fqn
