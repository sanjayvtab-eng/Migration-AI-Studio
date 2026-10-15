from sqlalchemy import inspect, text


SOURCE_COLUMNS = {
    "engine": "VARCHAR(32) NOT NULL DEFAULT 'SQLSERVER'",
    "port": "INTEGER",
    "schema_name": "VARCHAR(255)",
    "username": "VARCHAR(255)",
    "credential_ciphertext": "TEXT",
    "options_json": "TEXT NOT NULL DEFAULT '{}'",
}


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
