# Release 2.0.1 — Deterministic Compatibility Engine

## Why this patch exists

A live DEV load exposed a generic connector-transport defect: SQL Server `rowversion` was correctly mapped to Databricks `BINARY`, but the Python/Databricks connector path inferred the runtime value as an array, producing `ARRAY<VOID> -> BINARY` failure. The fix is deliberately metadata-driven and is not specific to `dbo.Customer`, `RowVersion`, or the sample database.

## Added

- Central SQL Server → Databricks **transport compatibility registry** (`type_compatibility.py`).
- Binary-safe transport for `binary`, `varbinary`, `image`, SQL Server `timestamp`, and `rowversion`:
  - SQL Server extraction: hexadecimal text with `CONVERT(..., 2)`.
  - Databricks binding: `unhex(?)` into target `BINARY`.
  - Python fallback normalization for `bytes`, `bytearray`, `memoryview`, and hex strings.
- Deterministic value normalization for `bit`, integer families, float/real, decimal/numeric/money, UUIDs, date/datetime, time, datetimeoffset, XML, hierarchyid and strings.
- Governed representation for `sql_variant`, geography/geometry and unknown/user-defined types, with precheck review warnings instead of silent semantic assumptions.
- Metadata-driven deployment error classification with stable category/code, failing stage, retryability and recommended remediation.
- Load evidence now records transport strategy counts, binary-safe columns and review-required columns without logging data values.
- Artifact generator/rule version markers updated for new generated versions.

## Governance retained

- SQL Server `timestamp` / `rowversion` remains `BINARY`; it is never treated as a date/time timestamp.
- No AI is used for deterministic datatype/transport corrections.
- No source objects are dropped.
- No production destructive behavior was introduced.
- Existing project, review, deployment and issue evidence remain project-scoped.
- Failed DEV runs remain resumable; later successful deployment evidence resolves the deployment issue.

## Upgrade behavior

No control-plane schema migration is required by this patch. Existing 2.0.0 `migration_factory.db` can be reused. The clean package excludes that runtime database and `.env`; copy them from the existing local installation if you want to continue the same project/run.
