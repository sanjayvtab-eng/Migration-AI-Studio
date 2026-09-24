# Release 5 — Governed Prompt-Based Environment Promotion

## Outcome

Release 5 promotes the exact approved Medallion release through Databricks
environments without returning to SQL Server or regenerating SQL with AI.

The enforced path is:

`DEV → TEST → UAT → PROD`

Each prompt creates a plan for exactly one transition. The application never
skips an environment and never chains automatically into PROD.

## Prompt examples

- `Promote approved DEV release to TEST`
- `Promote approved TEST release to UAT`
- `Promote approved UAT release to PROD`

Prompt parsing is deterministic and consumes no Gemini quota.

## Governed execution

1. Validate the upstream environment quality gate.
2. Lock the exact upstream deployment manifest in the plan.
3. Require an authenticated administrator to approve execution.
4. Recheck the manifest and preflight immediately before deployment.
5. Deep-clone Bronze tables and replay the approved Silver/Gold SQL with the
   target catalog substituted by the existing promotion service.
6. Reconcile the target environment.
7. Evaluate and persist the target quality gate.

PROD additionally requires `production_confirmed=true`; the UI presents a
separate confirmation dialog before sending this authorization.

If the source deployment manifest changes after planning, execution stops and
requires a new plan. Failed runs record the exact stage, sanitized error, and
recommended operator action.

## API

- `POST /api/projects/{id}/prompt-promotion/plan`
- `POST /api/projects/{id}/prompt-promotion/execute`
- `GET /api/projects/{id}/prompt-promotion/latest`

## UI

Open **Waves** and use **Release 5 · Prompt Promotion Studio**. Existing manual
preflight, deployment, reconciliation, gate, and log controls remain available
below the prompt workflow as operational evidence and recovery controls.
