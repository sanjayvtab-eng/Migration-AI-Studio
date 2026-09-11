# Release 1.6.0 — Executable Routine Converters + Runbook + Logs

- Deterministic SQL Server scalar UDF → Databricks SQL function conversion where safe.
- Deterministic SQL Server procedure → Databricks SQL stored procedure conversion where safe.
- Fail-safe `NON_EXECUTABLE` marking for unsupported dynamic/transactional constructs.
- Known source references are rewritten to project/environment target mappings.
- DEV precheck de-duplicates artifact/blocker evaluation by source object.
- Deployment UI adds View Logs and Download Log.
- New project-scoped log API with CSV/JSON download.
- New Runbook page with role-based operating flow and VS Code quick start.
