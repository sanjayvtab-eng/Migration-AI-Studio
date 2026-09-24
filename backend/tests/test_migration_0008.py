import sqlite3
from pathlib import Path


def test_migration_0008_upgrade_and_rollback_preserves_schema():
    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    upgrade_0007 = migrations_dir / "0007_release7_prompt_native.sql"
    upgrade_0008 = migrations_dir / "0008_dynamic_clarifications_and_destructive_approvals.sql"
    rollback_0008 = migrations_dir / "0008_dynamic_clarifications_and_destructive_approvals_rollback.sql"

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    # 1. Apply baseline migration 0007
    cur.executescript(upgrade_0007.read_text(encoding="utf-8"))

    # Insert a pre-existing clarification record to ensure data preservation
    cur.execute(
        """
        INSERT INTO migration_prompt_clarification (
            id, project_id, spec_version_id, question_key, question,
            affected_request_ids_json, choices_json, answer_json, status,
            asked_at
        ) VALUES (
            'test-clar-1', 'prj-1', 'ver-1', 'q_key_1', 'Is this test?',
            '[]', '["A","B"]', NULL, 'OPEN', '2026-09-24 12:00:00'
        )
        """
    )
    conn.commit()

    # 2. Apply Migration 0008 Upgrade
    cur.executescript(upgrade_0008.read_text(encoding="utf-8"))

    # Verify new columns
    cols = [r[1] for r in cur.execute("PRAGMA table_info(migration_prompt_clarification)").fetchall()]
    assert "recommended_answer" in cols
    assert "inference_reason" in cols

    # Verify destructive approval table exists
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "migration_destructive_approval" in tables

    # Verify pre-existing data is preserved after upgrade
    row = cur.execute("SELECT id, question_key, status FROM migration_prompt_clarification WHERE id='test-clar-1'").fetchone()
    assert row == ("test-clar-1", "q_key_1", "OPEN")

    # 3. Apply Migration 0008 Rollback
    cur.executescript(rollback_0008.read_text(encoding="utf-8"))

    # Verify destructive approval table is dropped
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "migration_destructive_approval" not in tables

    # Verify columns dropped
    cols = [r[1] for r in cur.execute("PRAGMA table_info(migration_prompt_clarification)").fetchall()]
    assert "recommended_answer" not in cols

    # Verify pre-existing data and unique constraints are preserved after rollback
    row = cur.execute("SELECT id, question_key, status FROM migration_prompt_clarification WHERE id='test-clar-1'").fetchone()
    assert row == ("test-clar-1", "q_key_1", "OPEN")

    # Verify index preserved
    indexes = [r[1] for r in cur.execute("PRAGMA index_list(migration_prompt_clarification)").fetchall()]
    assert "ix_prompt_clarification_version" in indexes
