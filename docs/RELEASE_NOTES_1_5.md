# Release 1.5.0 — Governed DEV Execution

This release turns the DEV Deployments page from a generic record screen into an execution workflow.

## Implemented

- Test Databricks from the selected project deployment context.
- DEV precheck for current artifact approvals, project scope, source-hash drift, target mappings, blocker issues and Databricks connectivity.
- Dependency-aware DEV deployment with Bronze → Silver → Gold ordering where dependency metadata exists, with layer-ranked fallback ordering.
- Target object ownership protection across migration projects.
- Target schema inspection and drift classification before table deployment.
- Safe schema additions when policy allows; destructive replacement only when DEV policy and explicit user approval both allow it.
- Source → Bronze batch loading with configurable batch size, max rows and FULL_LOAD / APPEND modes.
- FULL_LOAD refuses to clear existing data unless replacement is explicitly approved.
- Persistent migration_run, migration_run_step, migration_deployment, migration_validation, migration_reconciliation, migration_reconciliation_detail and migration_quality_gate evidence.
- Failed-run resume using the same run identity and already-passed object evidence.
- DEV reconciliation and formal DEV quality-gate evaluation.
- Lifecycle reads project-specific quality-gate evidence.
- Deployment UI now shows status, run ID, passed/failed counts, checkpoint, execution evidence, precheck result, reconciliation and gate result.
- Discovery dependency query corrected to resolve column names through referenced_minor_id + sys.columns.
- Generated views now create the mapped Databricks target FQN.

## Safety behavior

- No PROD deployment endpoint was added.
- Source SQL Server objects are never dropped or disabled.
- Cross-project target ownership collisions are blocked.
- Destructive target operations require both policy permission and an explicit user choice.
- Review-only stored-procedure/function/trigger candidates are blocked from execution until they become executable Databricks artifacts.
- Transient retries remain limited to safe/idempotent operations.

## Live infrastructure validation

Automated tests mock external SQL Server / Databricks operations. A real Databricks SQL Warehouse and SQL Server source are required to prove live DDL, loading and reconciliation in the customer's environment.
