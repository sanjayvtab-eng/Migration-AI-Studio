# Release 3 — Governed Prompt-Based Migration Orchestration

Release 3 connects natural language prompt interaction to the governed migration pipeline, enabling operators to initiate, review, approve, and observe end-to-end migrations into Databricks DEV through intuitive prompts such as:

> **“Migrate MigrationDemo from SQL Server to DEV Databricks.”**

## Delivered Scope

- **Natural-Language Intent Parsing**: Interprets migration requests, identifying source database, source type, target environment (`DEV`), load mode, and table scope.
- **Prerequisite Validation & Guardrails**: Evaluates source registration, Databricks connection status (`READY`), and DEV catalog provisioning (`PROVISIONED`). Rejects ambiguous or incomplete commands with `NEEDS_USER_INPUT` instead of guessing.
- **Pre-Execution Impact Assessment**: Previews discovered tables, estimated row volume, risk level, destination mapping (`<catalog>_dev.bronze`, `.silver`, `.gold`), and planned execution stages.
- **Mandatory Approval Gate**: Prompts initiate and plan, but no data moves and no artifacts are deployed until explicit human approval is granted.
- **Governed Multi-Step Orchestrator**: Sequentially executes:
  1. Discovery Verification
  2. DEV Bronze Ingestion (`bronze_ingestion.py` in `FULL_LOAD` mode)
  3. Medallion Semantic Modeling & Artifact Generation (`medallion.py`)
  4. Static Validation & Governed AI Remediation (`ai_remediation.py`)
  5. DEV Medallion Deployment (`deployment.py`)
  6. Source-to-Target Data & Schema Reconciliation (`deployment.py`)
- **Prompt Migration Studio UI**: Embedded in the Migration Workflow view with quick prompt templates, real-time impact cards, explicit approval actions, and step-by-step progress tracking.
- **Audit Logging**: Every prompt-initiated plan and execution run records complete audit evidence in `CanonicalRecord`.

## Operator Flow

1. In **Migration Workflow**, navigate to the **AI Prompt Migration Studio**.
2. Enter or select a prompt (e.g. `Migrate MigrationDemo from SQL Server to DEV Databricks`).
3. Click **Generate Plan**.
4. If prerequisites are missing, review the blockers and actionable next steps.
5. Once validated, inspect the **Impact Assessment** (tables, row volume, risk rating, destination mappings).
6. Click **Approve & Execute Migration**.
7. Observe real-time progress across each stage (Bronze Ingestion, Medallion Modeling, Remediation, Deployment, Reconciliation).
8. Inspect deployed artifacts and reconciliation diffs directly from the dashboard.

## Safety & Governance Boundary

- AI interprets user intent and plans execution; AI **never** directly executes raw DDL/DML or drops objects.
- Prompt execution is restricted to the **DEV** environment. Promotion to `TEST`, `UAT`, and `PROD` remains strictly governed by formal promotion gates in Release 5.
- Overwriting existing populated Bronze tables requires explicit operator confirmation.
- Destructive operations (`DROP CATALOG`, `DROP SCHEMA`) remain strictly blocked by default.
