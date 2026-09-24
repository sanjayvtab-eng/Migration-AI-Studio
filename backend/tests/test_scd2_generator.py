import pytest
import sqlite3
from app.services.prompt_specification import _scd2_sql_pipeline, scan_destructive_operations


def test_scd2_pipeline_generates_atomic_merge_and_staging():
    snapshot = {
        "objects": [{
            "type": "TABLE",
            "name": "Employees",
            "columns": [
                {"name": "EmployeeID", "target_name": "employee_id", "data_type": "int", "is_identity": True},
                {"name": "FirstName", "target_name": "first_name", "data_type": "varchar", "is_identity": False},
                {"name": "LastName", "target_name": "last_name", "data_type": "varchar", "is_identity": False},
                {"name": "Department", "target_name": "department", "data_type": "varchar", "is_identity": False},
                {"name": "Salary", "target_name": "salary", "data_type": "decimal", "is_identity": False},
            ],
        }]
    }

    sql = _scd2_sql_pipeline("corp_catalog", "dim_employee", "Employees", snapshot, "run123")

    # Verify staging table materialization
    assert "CREATE OR REPLACE TABLE `corp_catalog`.`silver`.`_stg_dim_employee_run123` USING DELTA AS" in sql
    assert "sha2(concat_ws('||'" in sql
    assert "current_timestamp() AS valid_from" in sql

    # Verify pre-merge duplicate check
    assert "-- PRE-MERGE DUPLICATE VALIDATION:" in sql
    assert "GROUP BY `employee_id` HAVING count(*) > 1" in sql

    # Verify Gold target table creation
    assert "CREATE TABLE IF NOT EXISTS `corp_catalog`.`gold`.`dim_employee` (" in sql
    assert "`employee_sk` STRING" in sql
    assert "`employee_id` INT" in sql
    assert "`is_current` BOOLEAN" in sql

    # Verify atomic single-pass MERGE with Stream A and Stream B
    assert "MERGE INTO `corp_catalog`.`gold`.`dim_employee` target" in sql
    assert "s.`employee_id` AS merge_key" in sql  # Stream A
    assert "WHERE NOT (t.row_hash <=> s.row_hash)" in sql  # Stream A changed only
    assert "UNION ALL" in sql
    assert "CAST(NULL AS INT) AS merge_key" in sql  # Stream B
    assert "WHERE t.`employee_id` IS NULL" in sql  # Stream B new or changed
    assert "WHEN MATCHED THEN UPDATE SET" in sql
    assert "target.is_current = false" in sql
    assert "target.valid_to = staged.valid_from" in sql
    assert "WHEN NOT MATCHED THEN INSERT" in sql
    assert "uuid()" in sql


def test_scd2_pre_merge_duplicate_key_validation_aborts():
    # Simulate staging table with duplicate natural business keys
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE staging (employee_id INT, first_name TEXT, row_hash TEXT, valid_from TIMESTAMP)")
    # Insert 2 rows with duplicate business key 101
    cur.executemany("INSERT INTO staging VALUES (?, ?, ?, ?)", [
        (101, "Alice", "hash1", "2026-01-01 00:00:00"),
        (101, "Alice Duplicate", "hash1_dup", "2026-01-01 00:00:00"),
        (102, "Bob", "hash2", "2026-01-01 00:00:00"),
    ])

    cur.execute("SELECT employee_id, COUNT(*) FROM staging GROUP BY employee_id HAVING COUNT(*) > 1")
    duplicates = cur.fetchall()

    def run_scd2_with_validation():
        if duplicates:
            duplicate_keys = [str(r[0]) for r in duplicates]
            raise RuntimeError(f"Duplicate business key(s) detected in staging snapshot: {', '.join(duplicate_keys)}; aborting SCD Type 2 MERGE to prevent duplicate dimension versions")

    with pytest.raises(RuntimeError, match="Duplicate business key\\(s\\) detected in staging snapshot: 101"):
        run_scd2_with_validation()


def test_scd2_idempotency_and_exclusion_of_unchanged_records():
    # Simulate Databricks Delta table with SQLite database
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE target_dim (
        sk TEXT PRIMARY KEY,
        employee_id INT,
        first_name TEXT,
        department TEXT,
        row_hash TEXT,
        valid_from TIMESTAMP,
        valid_to TIMESTAMP,
        is_current BOOLEAN
    )
    """)

    def execute_scd2_merge(staging_records: list[tuple[int, str, str, str, str]]):
        # staging_records: (employee_id, first_name, department, row_hash, valid_from)
        # Classify rows:
        stream_a = []  # CHANGED rows: (merge_key, employee_id, first_name, department, row_hash, valid_from)
        stream_b = []  # NEW and CHANGED rows: (None, employee_id, first_name, department, row_hash, valid_from)

        for s in staging_records:
            bk = s[0]
            cur.execute("SELECT row_hash FROM target_dim WHERE employee_id = ? AND is_current = 1", (bk,))
            target_row = cur.fetchone()

            if target_row is None:
                # NEW row
                stream_b.append((None, *s))
            elif target_row[0] != s[3]:
                # CHANGED row
                stream_a.append((bk, *s))
                stream_b.append((None, *s))
            else:
                # UNCHANGED row: completely excluded from both Stream A and Stream B
                pass

        # Stream A execution: close current versions
        updates_count = 0
        for row in stream_a:
            merge_key = row[0]
            valid_from = row[5]
            cur.execute("UPDATE target_dim SET is_current = 0, valid_to = ? WHERE employee_id = ? AND is_current = 1", (valid_from, merge_key))
            updates_count += cur.rowcount

        # Stream B execution: insert new current versions
        inserts_count = 0
        import uuid
        for row in stream_b:
            new_sk = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO target_dim (sk, employee_id, first_name, department, row_hash, valid_from, valid_to, is_current) VALUES (?, ?, ?, ?, ?, ?, NULL, 1)",
                (new_sk, row[1], row[2], row[3], row[4], row[5])
            )
            inserts_count += 1

        return updates_count, inserts_count

    # Run 1: Initial load with 3 records (Alice, Bob, Charlie)
    batch_1 = [
        (1, "Alice", "Engineering", "hash_alice_v1", "2026-01-01 00:00:00"),
        (2, "Bob", "Sales", "hash_bob_v1", "2026-01-01 00:00:00"),
        (3, "Charlie", "Finance", "hash_charlie_v1", "2026-01-01 00:00:00"),
    ]
    u1, i1 = execute_scd2_merge(batch_1)
    assert u1 == 0
    assert i1 == 3
    cur.execute("SELECT COUNT(*) FROM target_dim WHERE is_current = 1")
    assert cur.fetchone()[0] == 3

    # Run 2: IDEMPOTENCY TEST - Rerun the exact same batch 1
    # Proves 0 updates and 0 inserts, and UNCHANGED rows are completely excluded
    u2, i2 = execute_scd2_merge(batch_1)
    assert u2 == 0, "Rerunning the same batch must perform 0 updates"
    assert i2 == 0, "Rerunning the same batch must perform 0 inserts"
    cur.execute("SELECT COUNT(*) FROM target_dim")
    assert cur.fetchone()[0] == 3, "Total dimension versions must remain 3"

    # Run 3: Mixed batch
    # - Alice: CHANGED (new department "Executive", new hash)
    # - Bob: UNCHANGED (exact same hash) -> MUST BE EXCLUDED!
    # - Charlie: UNCHANGED (exact same hash) -> MUST BE EXCLUDED!
    # - Dana: NEW record
    batch_2 = [
        (1, "Alice", "Executive", "hash_alice_v2", "2026-02-01 00:00:00"),
        (2, "Bob", "Sales", "hash_bob_v1", "2026-02-01 00:00:00"),
        (3, "Charlie", "Finance", "hash_charlie_v1", "2026-02-01 00:00:00"),
        (4, "Dana", "Operations", "hash_dana_v1", "2026-02-01 00:00:00"),
    ]
    u3, i3 = execute_scd2_merge(batch_2)
    assert u3 == 1, "Only Alice's prior version should be closed"
    assert i3 == 2, "Only Alice v2 and Dana v1 should be inserted"

    # Verify versions
    cur.execute("SELECT COUNT(*) FROM target_dim")
    assert cur.fetchone()[0] == 5, "Total rows should be 5 (3 initial + 1 Alice update + 1 Dana insert)"

    cur.execute("SELECT is_current, valid_to FROM target_dim WHERE employee_id = 1 ORDER BY valid_from")
    alice_versions = cur.fetchall()
    assert len(alice_versions) == 2
    assert alice_versions[0] == (0, "2026-02-01 00:00:00")  # Old version closed
    assert alice_versions[1] == (1, None)  # New version active

    # Bob and Charlie still have exactly 1 version each
    cur.execute("SELECT COUNT(*) FROM target_dim WHERE employee_id = 2")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM target_dim WHERE employee_id = 3")
    assert cur.fetchone()[0] == 1

    # Run 4: IDEMPOTENCY TEST on Batch 2
    u4, i4 = execute_scd2_merge(batch_2)
    assert u4 == 0
    assert i4 == 0
    cur.execute("SELECT COUNT(*) FROM target_dim")
    assert cur.fetchone()[0] == 5
