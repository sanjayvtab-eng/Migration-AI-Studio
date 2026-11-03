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
    """Ensure created_by column exists on migration_project and token_ciphertext on databricks config."""
    inspector = inspect(engine)
    if "migration_project" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("migration_project")}
        with engine.begin() as connection:
            if "created_by" not in existing:
                connection.execute(text("ALTER TABLE migration_project ADD COLUMN created_by VARCHAR(255) DEFAULT 'admin'"))
            connection.execute(text("UPDATE migration_project SET created_by = 'admin' WHERE created_by IS NULL OR created_by = ''"))
    if "migration_databricks_configuration" in inspector.get_table_names():
        dbc_cols = {column["name"] for column in inspector.get_columns("migration_databricks_configuration")}
        if "token_ciphertext" not in dbc_cols:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE migration_databricks_configuration ADD COLUMN token_ciphertext TEXT"))
