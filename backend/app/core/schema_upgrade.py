from sqlalchemy import inspect, text


SOURCE_COLUMNS = {
    "engine": "VARCHAR(32) NOT NULL DEFAULT 'SQLSERVER'",
    "port": "INTEGER",
    "schema_name": "VARCHAR(255)",
    "username": "VARCHAR(255)",
    "credential_ciphertext": "TEXT",
    "options_json": "TEXT NOT NULL DEFAULT '{}'",
}


def ensure_auth_columns(engine) -> None:
    inspector = inspect(engine)
    if "migration_user" not in inspector.get_table_names():
        return
    existing = {c['name'] for c in inspector.get_columns('migration_user')}
    fields = {'otp_attempts': 'INTEGER NOT NULL DEFAULT 0',
              'password_proof_hash': 'VARCHAR(64)', 'password_proof_expires_at': 'TIMESTAMP',
              'session_version': 'INTEGER NOT NULL DEFAULT 0'}
    with engine.begin() as conn:
        for name, ddl in fields.items():
            if name not in existing:
                conn.execute(text(f'ALTER TABLE migration_user ADD COLUMN {name} {ddl}'))


def ensure_source_columns(engine) -> None:
    """Apply the additive v2.5 source fields for existing SQLite installations."""
    inspector = inspect(engine)
    if "migration_source" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("migration_source")}
    missing = [(name, ddl) for name, ddl in SOURCE_COLUMNS.items() if name not in existing]
    if not missing:
        return
    with engine.begin() as connection:
        for name, ddl in missing:
            connection.execute(text(f"ALTER TABLE migration_source ADD COLUMN {name} {ddl}"))



def ensure_project_columns(engine) -> None:
    """Ensure created_by, workspace_id, visibility, per-owner/ws uniqueness, and token_ciphertext exist."""
    inspector = inspect(engine)
    if "migration_project" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("migration_project")}
        with engine.begin() as connection:
            if "created_by" not in existing:
                connection.execute(text("ALTER TABLE migration_project ADD COLUMN created_by VARCHAR(255) DEFAULT 'admin'"))
            if "workspace_id" not in existing:
                connection.execute(text("ALTER TABLE migration_project ADD COLUMN workspace_id VARCHAR(64)"))
            if "visibility" not in existing:
                connection.execute(text("ALTER TABLE migration_project ADD COLUMN visibility VARCHAR(32) NOT NULL DEFAULT 'PRIVATE'"))
            connection.execute(text("UPDATE migration_project SET created_by = 'admin' WHERE created_by IS NULL OR created_by = ''"))
            connection.execute(text("UPDATE migration_project SET visibility = 'PRIVATE' WHERE visibility IS NULL OR visibility = ''"))

        if engine.dialect.name == "sqlite":
            with engine.begin() as connection:
                idx_rows = connection.execute(text("PRAGMA index_list('migration_project')")).fetchall()
                needs_rebuild = False
                for idx in idx_rows:
                    idx_name = idx[1]
                    is_unique = bool(idx[2])
                    if not is_unique:
                        continue
                    cols = [r[2] for r in connection.execute(text(f"PRAGMA index_info('{idx_name}')")).fetchall()]
                    if cols == ["name"] or cols == ["name", "created_by"]:
                        needs_rebuild = True
                        break
                if needs_rebuild:
                    connection.execute(text(
                        "CREATE TABLE migration_project_new ("
                        "id VARCHAR(64) NOT NULL PRIMARY KEY, "
                        "name VARCHAR(255) NOT NULL, "
                        "status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', "
                        "created_by VARCHAR(255) DEFAULT 'admin', "
                        "workspace_id VARCHAR(64), "
                        "visibility VARCHAR(32) NOT NULL DEFAULT 'PRIVATE', "
                        "created_at DATETIME NOT NULL, "
                        "CONSTRAINT uq_project_name_owner_ws UNIQUE (name, created_by, workspace_id)"
                        ")"
                    ))
                    connection.execute(text(
                        "INSERT INTO migration_project_new (id, name, status, created_by, workspace_id, visibility, created_at) "
                        "SELECT id, name, status, COALESCE(NULLIF(created_by, ''), 'admin'), workspace_id, COALESCE(NULLIF(visibility, ''), 'PRIVATE'), created_at FROM migration_project"
                    ))
                    connection.execute(text("DROP TABLE migration_project"))
                    connection.execute(text("ALTER TABLE migration_project_new RENAME TO migration_project"))
                    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_migration_project_created_by ON migration_project (created_by)"))
                    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_migration_project_workspace_id ON migration_project (workspace_id)"))

    if "migration_databricks_configuration" in inspector.get_table_names():
        dbc_cols = {column["name"] for column in inspector.get_columns("migration_databricks_configuration")}
        if "token_ciphertext" not in dbc_cols:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE migration_databricks_configuration ADD COLUMN token_ciphertext TEXT"))
