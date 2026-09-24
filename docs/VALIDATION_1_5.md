# Validation Report — 1.5.0 DEV_EXECUTION

## Executed in build environment

- Python compile validation: PASS.
- Backend unit/API/regression suite: 28 tests PASS.
- Deployment precheck approval blocking: PASS.
- Deployment evidence persistence: PASS.
- Failed-run checkpoint/resume discoverability: PASS.
- DEV gate project-scoped evidence logic: PASS.
- Existing metadata, mapping, artifact, lifecycle, security and project-isolation tests: PASS.
- Frontend TypeScript/TSX syntax transpilation check: PASS.
- Discovery dependency SQL/Python contract updated for referenced_minor_id / referenced_column_name.

## Not executable in this build environment

- Live SQL Server discovery against the user's Windows SQL Server.
- Live Databricks SQL Warehouse connection.
- Actual Databricks DDL execution.
- Real Source → Bronze transfer of customer data.
- Live Source → Bronze row-count reconciliation.
- Frontend production npm build: dependency retrieval is unavailable/timed out in the build sandbox. The package is intended to run `npm install` on the user's connected workstation.

These items are intentionally not reported as passed.
