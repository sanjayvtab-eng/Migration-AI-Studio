# Enterprise 1.2 Release Notes

## Discovery reliability
- Added per-source SQL Server **Test Connection** action.
- Added ODBC driver diagnostics and SQL authentication/Windows Trusted Connection visibility.
- Added actionable errors for driver, login, database access, network and certificate failures.
- Discovery now captures SQL-expression dependencies and routine parameters in addition to objects/columns.
- Discovery remains dynamic: the source server/database come from the selected source profile; credentials/driver come from environment configuration.

## Control-plane coverage
- Wired deterministic Assessment and Conversion Plans.
- Wired project-scoped records for Data Quality, Reconciliation, Deployments, Waves, Cutover, Decommission, Governance, Audit and Administration.
- Added Users view and account unlock action.
- Added system diagnostics page.

## Packaging/setup
- Added setup_windows.bat and validate_backend.bat.
- Removed relative DATABASE_URL from the sample env so the application default uses a stable project-root SQLite database.
- Allowed both Vite ports 5173 and 5174 by default.
- Removed the SQLAlchemy duplicate-class warning in dynamically generated canonical models.
