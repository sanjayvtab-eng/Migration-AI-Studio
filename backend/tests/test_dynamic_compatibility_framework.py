from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from app.services.type_compatibility import (
    TransportNormalizationError,
    adapter_spec,
    classify_execution_error,
    compatibility_catalog,
    normalize_source_value,
    source_select_expression,
    transport_contract,
    transport_plan,
    transport_summary,
)


def col(name, dtype, precision=None, scale=None):
    return SimpleNamespace(column_name=name, data_type=dtype, precision=precision, scale=scale)


def test_registry_covers_core_sqlserver_type_families():
    cases = {
        "bit": "BOOLEAN",
        "int": "INTEGER",
        "bigint": "INTEGER",
        "decimal": "DECIMAL",
        "float": "FLOAT",
        "nvarchar": "STRING",
        "date": "DATE",
        "datetime2": "DATETIME",
        "uniqueidentifier": "UUID",
        "rowversion": "BINARY",
        "xml": "XML",
        "hierarchyid": "HIERARCHYID",
        "geometry": "SPATIAL",
        "sql_variant": "SQL_VARIANT",
    }
    for dtype, family in cases.items():
        assert adapter_spec(dtype).family == family


def test_unknown_udt_uses_governed_reversible_fallback():
    c = col("Custom", "customer_money_type")
    p = transport_plan(c.data_type)
    assert p.strategy == "GOVERNED_TEXT_FALLBACK"
    assert p.review_required is True
    assert p.target_type == "STRING"
    assert "NVARCHAR(MAX)" in source_select_expression(c)


def test_numeric_and_temporal_runtime_normalization():
    assert normalize_source_value(col("B", "bit"), "yes") is True
    assert normalize_source_value(col("I", "tinyint"), "255") == 255
    assert normalize_source_value(col("D", "decimal", 18, 2), "123.45") == Decimal("123.45")
    assert normalize_source_value(col("Dt", "date"), "2026-08-27") == date(2026, 8, 27)
    assert normalize_source_value(col("Ts", "datetime2"), "2026-08-27T10:30:00") == datetime(2026, 8, 27, 10, 30)
    assert normalize_source_value(col("Tm", "time"), time(12, 34, 56)) == "12:34:56"
    dto = datetime(2026, 8, 27, 10, 30, tzinfo=timezone.utc)
    assert normalize_source_value(col("Dto", "datetimeoffset"), dto).endswith("+00:00")


def test_uuid_is_validated_not_blindly_stringified():
    value = UUID("12345678-1234-5678-1234-567812345678")
    assert normalize_source_value(col("Id", "uniqueidentifier"), value) == str(value)
    try:
        normalize_source_value(col("Id", "uniqueidentifier"), "not-a-guid")
        assert False, "invalid UUID should be rejected"
    except TransportNormalizationError as exc:
        assert exc.error_code == "UUID_RUNTIME_INVALID"


def test_binary_accepts_list_tuple_and_tobytes_wrapper():
    c = col("Payload", "varbinary")
    assert normalize_source_value(c, [0, 15, 255]) == "000fff"
    assert normalize_source_value(c, (1, 2, 3)) == "010203"

    class Wrapper:
        def tobytes(self):
            return b"\xaa\xbb"

    assert normalize_source_value(c, Wrapper()) == "aabb"


def test_errors_are_structured_and_do_not_log_source_values():
    c = col("SecretPayload", "varbinary")
    try:
        normalize_source_value(c, "customer-sensitive-not-hex", row_index=42)
        assert False, "expected failure"
    except TransportNormalizationError as exc:
        d = exc.diagnostics()
        assert d["column_name"] == "SecretPayload"
        assert d["runtime_type"] == "str"
        assert d["row_index"] == 42
        assert "customer-sensitive-not-hex" not in str(exc)
        classified = classify_execution_error(exc, "BRONZE_LOAD")
        assert classified["error_category"] == "LOAD"
        assert classified["deterministic_remediation_available"] is True
        assert classified["diagnostics"]["adapter_id"] == "binary.hex.v2"


def test_contract_and_summary_report_real_deterministic_coverage():
    cols = [
        col("Id", "int"),
        col("Version", "rowversion"),
        col("Name", "nvarchar"),
        col("Variant", "sql_variant"),
        col("Mystery", "some_udt"),
    ]
    contract = transport_contract(cols)
    assert len(contract) == 5
    summary = transport_summary(cols)
    assert summary["total_columns"] == 5
    assert summary["deterministic_columns"] == 3
    assert summary["review_required_columns"] == ["Variant", "Mystery"]
    assert summary["unknown_type_columns"] == ["Mystery"]
    assert summary["deterministic_coverage_pct"] == 60.0


def test_catalog_is_registry_driven_and_has_unknown_policy():
    rows = compatibility_catalog()
    ids = {r["adapter_id"] for r in rows}
    assert "binary.hex.v2" in ids
    assert "decimal.native.v2" in ids
    assert "unknown.governed_text.v1" in ids
