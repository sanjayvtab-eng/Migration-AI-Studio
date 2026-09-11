# 360 Functional Validation Report — Enterprise 1.2

Validation date: 2026-08-19

## Scope exercised locally

- Python compile validation: PASS
- Backend unit/API tests: PASS — 23 tests
- Authentication, lockout, JWT and user administration: PASS
- Project creation and project isolation: PASS
- Source profile creation: PASS
- SQL Server connection-test API contract: PASS with mocked SQL Server transport
- Discovery snapshot ingestion: PASS
- Dependency ingestion: PASS
- Inventory: PASS
- Deterministic assessment: PASS
- Bronze/Silver/Gold classification and override: PASS
- Mapping generation: PASS
- Conversion-plan generation: PASS
- Artifact version generation: PASS
- rowversion/timestamp -> BINARY: PASS
- Static validation / unresolved-column issue creation: PASS
- Review/approval: PASS
- Generic Data Quality/Reconciliation/Deployment/Wave/Cutover/Decommission/Governance/Audit control records: PASS
- Lifecycle and quality gates: PASS
- TEST promotion project isolation: PASS
- System diagnostics endpoint: PASS
- Frontend TS/TSX syntax transpilation: PASS
- OpenAPI route registration: PASS — 29 paths / 36 operations
- ZIP integrity: performed before release

## Live infrastructure validation status

The build environment used to create this ZIP does not have access to the user's Windows SQL Server or Databricks workspace. Therefore these items are intentionally NOT claimed as passed here:

- Live SQL Server ODBC connection to the user's server
- Live discovery against MigrationE2ETest or any customer database
- Live Databricks warehouse authentication
- Live DEV/TEST/UAT/PROD deployment
- 1M/10M-row performance tests against real infrastructure
- Browser production build using fetched npm packages (network package retrieval timed out in the build sandbox)

The application now exposes **Test Connection** before **Run Discovery** and returns actionable ODBC/login/database/network diagnostics. This is specifically intended to make live discovery failures diagnosable instead of appearing as a non-working button.

## Important product boundary

Enterprise 1.2 provides a functional migration control plane for discovery through governed artifact planning and metadata/control evidence. Later-stage pages such as Deployment, Cutover, and Reconciliation now persist project-scoped control evidence and are no longer empty placeholders; however, a stored control record is not equivalent to executing a production Databricks deployment. Live deployment remains dependent on real Databricks configuration and environment-specific validation.
