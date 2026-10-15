from pathlib import Path

import pytest

from app.models.entities import MigrationProject, MigrationSource
from app.services.engine import add_source
from app.services.rules import map_sqlserver_type
from app.services.source_adapters import (
    DEFAULT_PORTS,
    MySQLAdapter,
    OracleAdapter,
    PostgreSQLAdapter,
    SQLServerAdapter,
    adapter_for_source,
    decrypt_password,
    normalize_engine,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("mssql", "SQLSERVER"), ("postgres", "POSTGRESQL"), ("mariadb", "MYSQL"), ("oracle", "ORACLE")],
)
def test_engine_aliases_are_normalized(value, expected):
    assert normalize_engine(value) == expected


def test_source_profiles_preserve_engine_specific_configuration(db):
    db.add(MigrationProject(id="PRJ", name="multi-source"))
    db.commit()
    source = add_source(
        db, "PRJ", "warehouse", "db.example", "analytics",
        engine="POSTGRESQL", schema_name="reporting", username="reader",
        password="not-plain-text", options={"ssl_mode": "require"},
    )
    assert source.port == DEFAULT_PORTS["POSTGRESQL"]
    assert source.credential_ciphertext != "not-plain-text"
    assert decrypt_password(source.credential_ciphertext) == "not-plain-text"
    assert isinstance(adapter_for_source(source), PostgreSQLAdapter)


@pytest.mark.parametrize(
    ("engine", "adapter"),
    [("SQLSERVER", SQLServerAdapter), ("POSTGRESQL", PostgreSQLAdapter),
     ("MYSQL", MySQLAdapter), ("ORACLE", OracleAdapter)],
)
def test_abstract_factory_selects_adapter(engine, adapter):
    source = MigrationSource(id="SRC", project_id="PRJ", profile_name="x", server_name="host",
                             database_name="db", engine=engine, options_json="{}")
    assert isinstance(adapter_for_source(source), adapter)


@pytest.mark.parametrize(
    ("source_type", "target_type"),
    [("integer", "INT"), ("boolean", "BOOLEAN"), ("bytea", "BINARY"),
     ("varchar2", "STRING"), ("number(19,0)", "DECIMAL(19,0)"), ("longblob", "BINARY")],
)
def test_cross_database_types_map_to_canonical_delta_types(source_type, target_type):
    assert map_sqlserver_type(source_type) == target_type


def test_stage_one_ui_exposes_all_engines_and_dynamic_fields():
    app = (Path(__file__).parents[2] / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    for engine in ("SQLSERVER", "POSTGRESQL", "MYSQL", "ORACLE"):
        assert engine in app
    for field in ("ssl_mode", "charset", "service_name", "schema_name"):
        assert field in app
