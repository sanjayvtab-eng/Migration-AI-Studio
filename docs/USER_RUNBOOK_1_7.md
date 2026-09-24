# SQL Server → Databricks Migration Factory — User Runbook

## Roles and operating block diagram

```text
[Administrator]
  Configure root .env + frontend/.env
  Create first admin → start Backend + Frontend
        |
        v
[Migration Engineer]
  Project → SQL Server Source → Test Connection → Discovery
        |
        v
  Inventory → Dependencies → Assessment
        |
        v
[Data Architect / Data Engineer]
  Layer Classification → Mappings → Conversion Plans
        |
        v
  Generate Artifacts → Static Validation
        |
        v
[Reviewer / Approver]
  Review latest artifact version → Approve
        |
        v
[DEV Operator]
  Test Databricks → DEV Precheck
        |
        +---- BLOCKED ----> Fix mapping/artifact/approval/drift → repeat precheck
        |
        v
  Deploy Approved to DEV → Bronze load → Silver/Gold objects
        |
        +---- FAILED -----> View Logs → remediate → Resume Failed Run
        |
        v
[Validator]
  Run Reconciliation → Data Quality / blocker resolution
        |
        v
[Release Approver]
  Evaluate DEV Gate → Lifecycle = PASSED
        |
        v
  TEST → UAT → PROD (independent evidence and approvals)
```

## Starting in VS Code

```text
Terminal 1 — Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010

Terminal 2 — Frontend
cd frontend
npm install
npm run dev
```

Backend Swagger: `http://127.0.0.1:8010/docs`.
Frontend: use the Vite URL, normally `http://localhost:5173` or `5174`.

## Required configuration

Root `.env` contains SQL Server and Databricks connectivity. `frontend/.env` contains:

```text
VITE_API_URL=http://127.0.0.1:8010/api
```

Never paste production tokens into source files or commit `.env`.

## Logs

Deployments provides **View Logs** for project-scoped DEV execution evidence and **Download Log** for CSV export. Logs combine deployment, run-step, validation, reconciliation, target FQN, run ID, failure, and remediation evidence.


## AI-assisted remediation flow

```text
Artifact generation
      ↓
Executable? ── Yes ──→ Static validation → Review
      │
      No
      ↓
AI-assisted remediation
      ↓
Deterministic remediation pattern first
      │
      ├─ matched → validated candidate
      │
      └─ not matched + LLM enabled → AI candidate
                              ↓
                    deterministic safety validation
                              ↓
                    human accepts candidate
                              ↓
                    NEW artifact version
                              ↓
                    explicit review / approval
                              ↓
                    DEV Precheck
```

AI can never auto-approve or auto-deploy the candidate. Review history shows object, version, review type, status, reviewer and timestamp.
