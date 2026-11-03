# Migration AI Studio 2.5.0 — Live Operational Assessment Addendum

**Supplementary Engineering Audit & Live Execution Findings (F24 – F30)**  
**Document Purpose:** Companion Addendum to *Independent Technical and Product Review (3 November 2026)*  
**Scope:** Live Databricks Medallion Execution, AI Prompt-Native Studio, Windows Agent Packaging, Smart Resumption, and Cloud Multi-Tenant Infrastructure.  
**Audience:** Product Owner, Lead Migration Architect, Independent Security & QA Reviewers.  

---

## 1. Executive Summary & Audit Context

The initial *Independent Technical and Product Review (3 November 2026)* correctly identified critical authentication, BOLA, and data type boundaries (F01 – F23) using isolated code inspection and a local SQLite test harness. 

However, as stated in the primary review's scope boundary (**Section 2, Line 32 & 57**):
> *"Bundled executable agents were inspected as package contents but were not executed."*  
> *"No live SQL Server, PostgreSQL, MySQL, Oracle, Databricks, Gemini, Ollama, Supabase or Brevo integration was certified."*

During live end-to-end enterprise validation with live Databricks Unity Catalog, Supabase PostgreSQL, and Windows client execution, **7 additional high-impact operational and architectural failures (F24 – F30)** were reproduced. 

These findings represent critical runtime failures in **AI Prompt Grounding, Medallion Deployment Resumption, Quality Gate Deadlocks, Windows Port Bindings, and Connection Pool Saturation** that must be included in the re-validation and remediation roadmap.

---

## 2. Additional Findings Inventory (F24 – F30)

| Finding ID | Classification | Severity | Affected Area | Core Failure Mechanism |
| :--- | :--- | :---: | :--- | :--- |
| **F24** | AI Prompt Semantic Variance | **High · P1** | Stage 7: Prompt Studio | Singular vs Plural column stem mismatch (`sale_detail_id` vs `sales_detail_id`) causing Databricks DDL aborts. |
| **F25** | Smart Resumption State Failure | **Critical · P1** | Stage 8: Deployment (DEV) | Resuming failed Medallion runs skips 0 verified objects; UI displays `NaN objects deployed`. |
| **F26** | Gate & Promotion Circular Deadlock | **High · P1** | Stages 8 & 9: Governance | DEV 42/42 Passed is blocked by missing legacy reconciliation row; preflight authorization throws BLOCKED error. |
| **F27** | Universal Agent Windows Port Collision | **High · P1** | Client Agent (`agent.exe`) | Rigid Port 5000 binding collides with Windows AirPlay/System services, preventing Web GUI launch. |
| **F28** | Agent Thrashing on Cloud Cold-Starts | **High · P1** | Agent Gateway & Cloud API | 5s rigid poll timeout spams connection errors during 50s Render cold starts, triggering health-check kills. |
| **F29** | Database Pool Exhaustion (`EMAXCONNSESSION`)| **Critical · P1** | Control Plane Database | Multi-threaded reconciliation + 3s UI polling saturates Supabase PostgreSQL transaction pooler. |
| **F30** | Frontend Modal Mounting Scope Defect | **Medium · P1** | Frontend UI (`App.tsx`) | Authorization modal nested in Stage 7 JSX; clicking promotion on Stage 8 does nothing. |

---

## 3. Detailed Findings & Required Fixes

### F24 AI Prompt Generator Discrepancy & Plural/Singular Stem Mismatch
**High · P1 · Live Reproduced against Databricks Unity Catalog**

**Observation:**  
When natural language prompts use colloquial singular terms (e.g., `calculate gross and discounted net sale-item amounts`), the Prompt-Native AI Compiler synthesizes SQL using singular identifiers (`sd.sale_detail_id`), whereas the physical source schema contains plural identifiers (`sd.sales_detail_id`). 

Stage 7 Semantic Grounding performed superficial keyword matching rather than strict AST column binding against discovered schema metadata. As a result, the ungrounded SQL was approved without warning and failed during Stage 8 Databricks execution with:
```
[UNRESOLVED_COLUMN.WITH_SUGGESTION]: A column, variable, or function parameter with name 'sd'.'sale_detail_id' cannot be resolved. Did you mean one of the following? ['sd'.'sales_detail_id', 's'.'sale_id']
```

**Impact:**  
Medallion deployment aborts midway in Databricks DEV. The system is forced to rely on reactive runtime healing rather than deterministic compile-time preflight validation.

**Fix and Acceptance:**  
1. Implement compile-time AST column binding in Stage 7 before artifact review approval.
2. Integrate an automated identifier stem normalizer (stripping trailing `'s'`, fuzzy distance matching) into `sql_preflight.py` and `prompt_specification.py`.
3. Assert that any ungrounded identifier matching a known physical column candidate with $\ge 85\%$ similarity is automatically healed and versioned before execution.

**Source:** `backend/app/services/prompt_specification.py`, `backend/app/services/sql_preflight.py`, `backend/app/services/ai_remediation.py`.

---

### F25 Smart Resume State Machine Failure on Partial Medallion Deployment
**Critical · P1 · Live Reproduced**

**Observation:**  
During a 42-object DEV Medallion deployment, an intentional failure was triggered at object #32. When the operator clicked **"Resume Failed Deployment"**, the backend failed to recognize the 31 previously verified artifacts, displaying `Resume from Failed Object (0 already verified objects will be skipped)` and attempting to re-execute all 42 objects from scratch. 

Concurrently, the UI DEV status card displayed:
```
DEPLOYED / VERIFIED: NaN objects
```
This was caused by unhandled undefined math in JavaScript (`Math.max(undefined, ...)` returning `NaN`) and hash lookup discrepancies where runtime timestamp injection altered the evaluated artifact hash between attempts.

**Impact:**  
Large enterprise migrations (100+ tables) cannot resume incrementally. An interruption or transient network blip at object 95 requires 100% re-execution, drastically increasing cloud warehouse costs and duplicating execution risk.

**Fix and Acceptance:**  
1. Ensure artifact hashes reflect deterministic SQL content and schema definitions only, excluding runtime execution timestamps.
2. Guard frontend numeric state with `Number.isFinite()` and fallback to 0.
3. Verify via integration tests that when 31 of 42 objects are `PASSED`, resuming executes exactly 11 objects and marks the 31 objects as `skipped: true`.

**Source:** `backend/app/services/medallion.py:deploy_medallion_dev`, `frontend/src/App.tsx`.

---

### F26 Medallion DEV Deployment and Quality Gate Circular Deadlock
**High · P1 · Live Reproduced**

**Observation:**  
When all 42/42 Medallion artifacts reached `PASSED` status in Databricks DEV (`MDR_c5666...` with 42 objects deployed, 0 failed), the system entered a state machine deadlock:
1. The top header pill remained red (`DEV: Failed`).
2. Stage 7 bottom container showed: `CURRENT OPERATION: Blocked by prerequisites: DEV gate PASSED` with status `BLOCKED`.
3. Clicking **"Authorize Automated Promotion"** threw:
```
Automated promotion preflight blocked: DEV quality gate status is BLOCKED (must be PASSED); Latest DEV quality gate is not PASSED.
```
This occurred because `_deploy_medallion_dev` did not atomically evaluate `evaluate_dev_gate()`. Furthermore, `evaluate_dev_gate()` required a separate `MigrationReconciliation` row, which Medallion deployments did not write. Because reconciliation was absent, `evaluate_dev_gate` recorded a `BLOCKED` gate entry in the database.

**Impact:**  
Legitimate, 100% successful DEV deployments cannot proceed to TEST, UAT, or PROD through the governed automation pipeline without manual database intervention.

**Fix and Acceptance:**  
1. In `deployment.py:evaluate_dev_gate`, recognize successful Medallion DEV runs and automatically generate passed `MigrationReconciliation` evidence.
2. In `master_orchestration.py:get_automated_promotion_preflight` and `authorize_automated_promotion`, evaluate DEV quality gates on-the-fly if stale or pending.
3. Verify that 42/42 DEV deployment passes automatically unlock the `Authorize Automated Promotion to PROD` button with status `READY`.

**Source:** `backend/app/services/medallion.py`, `backend/app/services/deployment.py`, `backend/app/services/master_orchestration.py`.

---

### F27 Universal Migration Agent Localhost Port Collision on Windows
**High · P1 · Live Reproduced on Windows 11 Enterprise**

**Observation:**  
The packaged agent (`migration-agent.exe`) hard-codes port `5000` for its embedded local diagnostics and Visual Web GUI. In standard Windows environments, port `5000` is frequently bound by Windows AirPlay Receiver, Hyper-V, or corporate endpoint services. 

When launched, the agent crashed or logged port binding exceptions, and browser navigation to `http://localhost:5000` failed to display the dashboard.

**Impact:**  
End users cannot access the local agent dashboard or verify connectivity diagnostics on corporate workstations without IT intervention to kill conflicting background services.

**Fix and Acceptance:**  
1. Implement dynamic port fallback in `agent.py`: test ports sequentially `[5000, 5001, 8080, 8888, 0]`.
2. If all specific ports are occupied, bind to an ephemeral OS-assigned free port (`port 0`) and automatically launch the default browser with the active URL: `http://localhost:{assigned_port}`.

**Source:** `scripts/local_connector.py`, `agent/agent.py`.

---

### F28 Universal Agent Connection Thrashing on Ephemeral Cloud Cold-Starts
**High · P1 · Live Reproduced on Render PaaS**

**Observation:**  
When deployed on cloud container platforms with scale-to-zero / sleep policies (e.g., Render free/starter tiers), container spin-up requires 45–60 seconds. The local agent used a hard-coded 5-second polling interval with immediate retry:
```
[11:31:00] discover: completed
Hosted application unreachable. Retrying in 5 seconds...
Hosted application unreachable. Retrying in 5 seconds...
Hosted application unreachable. Retrying in 5 seconds...
```
This aggressive polling overwhelmed the waking instance, causing Render to log:
```
Instance failed: HTTP health check failed (timed out after 5 seconds) while running your code.
```

**Impact:**  
Container instances enter crash-restart loops during client connection attempts, preventing successful discovery handshakes.

**Fix and Acceptance:**  
1. Implement exponential backoff with jitter in the agent connector: `min(60, 2 ** attempt) + rand(0.5, 2.0)`.
2. When receiving HTTP 502/503/504, display a clean warmup message: `Cloud backend waking up (cold-start delay). Retrying smoothly in {t}s...`.
3. Provide an ultralight `/healthz` endpoint in FastAPI that responds in $<10\text{ms}$ without initializing heavy database connections.

**Source:** `scripts/local_connector.py`, `agent/agent.py`, `backend/app/main.py`.

---

### F29 Control Plane Database Pool Saturation (`EMAXCONNSESSION`)
**Critical · P1 · Live Reproduced with Supabase PostgreSQL**

**Observation:**  
In production deployments utilizing managed PostgreSQL poolers (Supabase Transaction Pooler on Port 6543), concurrent operations produced database crashes:
```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) remaining connection slots are reserved for non-replication superuser connections
Max client connections reached: EMAXCONNSESSION
```
This occurred because `ThreadPoolExecutor(max_workers=6)` inside `run_reconciliation` opened independent SQLAlchemy sessions per worker thread, while the React frontend executed background HTTP polling every 3 seconds across multiple component hooks.

**Impact:**  
Total control plane failure, 500 Internal Server Errors, and failed deployment manifests across all active migration projects.

**Fix and Acceptance:**  
1. Enforce `NullPool` in SQLAlchemy database engine configuration when connecting through transaction poolers to ensure immediate connection release upon statement completion.
2. Pass pre-connected Databricks cursors into reconciliation worker threads rather than opening nested PostgreSQL database sessions.
3. Implement adaptive frontend polling: throttle polling to 15 seconds during idle states and suspend polling when browser tab visibility is `hidden`.

**Source:** `backend/app/core/database.py`, `backend/app/services/deployment.py`, `frontend/src/App.tsx`.

---

### F30 Frontend Authorization Modal Scope & Component Unmounting Defect
**Medium · P1 · Live Reproduced**

**Observation:**  
The One-Time Automated Promotion Authorization Modal (`showAutoAuthModal`) was conditionally mounted inside Stage 7 JSX:
```tsx
{page === "Migration Workflow" && (
    ...
    {showAutoAuthModal && <Modal ... />}
)}
```
When an operator was on Stage 8 (`page === "Deployments"`) and clicked **"Authorize Automated Promotion (TEST → UAT → PROD)"**, the handler executed `setShowAutoAuthModal(true)`. However, because `page !== "Migration Workflow"`, the modal component was never mounted into the DOM, resulting in zero visual response.

**Impact:**  
Operators were unable to authorize the multi-environment promotion pipeline from the Stage 8 deployment and verification screen.

**Fix and Acceptance:**  
1. Move `showAutoAuthModal` to the global root level of `App.tsx` alongside other application overlays.
2. Ensure opening the modal triggers an immediate asynchronous refresh of preflight telemetry (`/master-orchestration/current`).

**Source:** `frontend/src/App.tsx`.

---

## 4. Synthesis: Complete Findings Matrix (F01 – F30)

When presenting this remediation package to the client and engineering leads, the findings should be organized into the following cohesive release structure:

```
┌───────────────────────────────┬─────────────────────────────────────────────────────────────────┐
│ Milestone                     │ Findings Covered                                                │
├───────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Release A: Security & BOLA    │ F01 (Password Reset), F02 (Project BOLA), F03 (Role Bypass),    │
│                               │ F04 (Schedule Auth), F05 (Gate Forgery), F06 (Credential Leak)  │
├───────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Release B: Data & Transport   │ F07 (Watermark Sync), F08 (Scheduler Lease), F09 (Append Count),│
│                               │ F10 (Postgres Bytea), F11 (Agent Parquet), F12 (Discovery),     │
│                               │ F13 (Unapproved Healing), F14 (Checksums), F23 (Oracle Case)    │
├───────────────────────────────┼─────────────────────────────────────────────────────────────────┤
│ Release C: AI, Medallion &    │ F24 (Prompt Plural/Singular Stemming), F25 (Smart Resume NaN),  │
│ Live Operational Resilience   │ F26 (Medallion DEV Gate Deadlock), F27 (Agent Port Collision),  │
│                               │ F28 (Cloud Cold-Start Jitter), F29 (Supabase EMAXCONNSESSION),  │
│                               │ F30 (Global Modal Scope), F15 (Readiness UI), F16 (Pagination)  │
└───────────────────────────────┴─────────────────────────────────────────────────────────────────┘
```

---

## 5. Instructions for Client Re-Validation

To verify the closure of **F24 – F30**, the auditor should execute the following test commands in the live integration environment:

1. **Verify F24 (AI Prompt Stem Healing)**:
   ```bash
   pytest backend/tests/test_sql_preflight.py -k test_identifier_repair_singular_plural
   ```
2. **Verify F25 (Medallion Resumption)**:
   ```bash
   pytest backend/tests/test_medallion_resume.py
   ```
3. **Verify F26 (Auto-Reconciliation & Quality Gate)**:
   ```bash
   pytest backend/tests/test_master_orchestration.py -k test_master_resume_reuses_passed_checkpoints
   ```
4. **Verify F29 & F30 (Frontend Build & Global Modals)**:
   ```bash
   cd frontend && npm run build
   ```
