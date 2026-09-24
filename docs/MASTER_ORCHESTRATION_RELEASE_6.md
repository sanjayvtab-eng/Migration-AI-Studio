# Release 6 — Master End-to-End Prompt Orchestration

## Outcome

Release 6 connects the governed DEV migration and Release 5 environment
promotions into one operator request:

`SQL Server → DEV → TEST → UAT → PROD`

One prompt creates the complete plan. One authenticated administrator grants
up-front authorization for the defined workflow and explicit PROD scope. The
authorization is persisted with the actor, timestamp and environment scope.

## Example prompt

`Migrate MigrationDemo from SQL Server through DEV, TEST, UAT, and PROD Databricks`

PROD scope must be explicit. A DEV-only prompt cannot silently become a
production deployment.

## Execution policy

1. Execute the existing governed DEV prompt migration.
2. Run automatic static validation and bounded AI remediation inside DEV.
3. Require successful DEV reconciliation and quality gate.
4. Promote the exact approved manifest from DEV to TEST.
5. Reconcile TEST and require its quality gate.
6. Repeat the governed promotion for UAT.
7. Promote the approved UAT manifest to PROD.
8. Reconcile PROD and require the final quality gate.

AI does not approve itself. The initial administrator authorization permits the
policy engine to continue only when deterministic validation, reconciliation
and environment gates pass.

## Checkpoints and resume

The master plan stores independent checkpoints for DEV, TEST, UAT and PROD.
When a stage fails, later stages are not started. An administrator can resume
the same plan; already passed checkpoints are reused and the failed stage is
retried. Each stage is limited to three master attempts. Existing lower-level
Gemini retry, rate-limit and idempotency controls remain unchanged.

## Safe-stop conditions

The workflow stops on unresolved validation, failed remediation, connection or
permission errors, deployment failure, reconciliation mismatch, quality-gate
failure, manifest drift, or exhausted attempts. The UI shows the exact failed
stage and recommended recovery action.

## API

- `POST /api/projects/{id}/master-migration/plan`
- `POST /api/projects/{id}/master-migration/execute`
- `GET /api/projects/{id}/master-migration/latest`

Execution requires both `workflow_authorized=true` and
`production_authorized=true` the first time. The UI also records explicit
FULL_LOAD replacement authorization so a partial Bronze run can be resumed
safely without silently granting destructive scope. Resume uses the persisted
authorization.

## UI

Open **Migration Workflow** and use **Release 6 · Master End-to-End
Orchestrator**. Generate the plan, inspect its scope and impact, then select
**Authorize & Run Full Migration**. The previous Release 3 and Release 5 tools
remain available for investigation and controlled manual recovery.
