# Release Notes — 2.2.0 DYNAMIC_COMPATIBILITY_FRAMEWORK

## Goal
Replace one-off datatype/load fixes with a reusable runtime compatibility framework selected entirely from discovered SQL Server metadata.

## What changed
- Added a central adapter registry covering binary, boolean, integer, floating point, decimal/money, UUID, string, date/datetime, time/datetimeoffset, XML, sql_variant, hierarchyid and spatial families.
- `timestamp` / `rowversion` maps to Databricks `BINARY`, never `TIMESTAMP`.
- Binary source projection uses SQL Server style-2 hex and Databricks `unhex(?)`.
- Binary normalization supports common lossless Python/ODBC representations and validates rowversion length.
- Runtime conversion errors are structured and data-safe: diagnostics include metadata/runtime shape but never the source value.
- Batch rows are normalized before `executemany`, so deterministic transport errors occur before the target batch write.
- Unknown/user-defined types use governed textual preservation plus review instead of silent guessing.
- Discovery now records the declared and underlying SQL Server type for alias/user-defined columns without requiring a control-database schema change.
- Added project compatibility summary APIs and a **Compatibility** UI page showing measured deterministic coverage.
- Ollama remains for semantic conversion/remediation only. It does not own datatype transport or bypass deterministic validation.

## Governance
This build does not promise that every proprietary CLR/UDT or business-semantic transformation can be automatically converted. Unsupported or ambiguous semantics are explicitly marked for review. This is intentional fail-safe behavior.
