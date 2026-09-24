# Release Notes 1.9.1 — Duplicate Hardening

## Fixed
- Artifacts API now returns exactly one effective current artifact per source object, even when older databases contain duplicate artifact rows.
- Mappings API now returns exactly one effective DEV mapping per source object/environment.
- Generate All DEV Artifacts de-duplicates object IDs before generation, preventing repeated generation calls from duplicated mappings.
- Review grid inherits the de-duplicated current-artifact list, eliminating repeated rows for the same object/version.
- Historical duplicate database rows are preserved for audit; only the effective current row is surfaced/executed.
- Existing deployment precheck de-duplication remains in place.

## Validation
- Full backend regression: 40 tests passed.
- Added regression coverage that injects legacy duplicate mapping/artifact rows and verifies one mapping + one artifact are returned.
