# Migration AI Studio 2.5.0 application assessment

**Independent technical and product review for release planning**
**Review date:** 3 November 2026
**Audience:** Product owner, engineering lead, QA team and migration architects
**Decision:** Hold production and shared customer deployment until the release blockers below are fixed and retested.

## 1 Executive assessment

Migration AI Studio is a substantial migration control platform with a useful product direction. It combines source discovery, metadata inventory, Databricks SQL generation, Bronze/Silver/Gold planning, artifact review, data loading, reconciliation and environment promotion. There is real implementation behind these features, including deterministic conversion rules, versioned artifacts, dependency ordering, staging-based full loads and project-specific target configuration.

**The supplied build is not ready for production or untrusted multi-user access.** Local tests reproduced an unauthenticated password replacement that issues an administrator token, access to another owner's project, unauthenticated schedule operations, reviewer impersonation, fabricated quality-gate evidence and several data synchronization errors. These are material failures in the controls on which the product depends.

The highest business risk is **incorrect confidence**: an operation can look approved, synchronized, connected or complete without corresponding trustworthy evidence. A new project displayed 50% completion; an empty Sources page displayed one source configured; a count-only reuse path returned success without extracting data; and a client-submitted gate made PROD appear passed without a production deployment.

The next updates should prioritize security boundaries and data correctness before adding more engines, AI models or automation. After those fixes, the strongest initial positioning would be **a supervised migration assistant with a clearly tested compatibility matrix**. Broad claims of production readiness, complete multi-engine modernization, continuous synchronization and automatic business correctness exceed the evidence available in this package.

### Release recommendation

| Intended use | Assessment | Required condition |
|---|---|---|
| Code evaluation and synthetic demonstrations | Suitable in an isolated review setup | Remove supplied secrets and use disposable data |
| Supervised non-production pilot | Conditional after blocker fixes | Explicit test source/target, verified access controls and reconciliation |
| Shared internal service with multiple users | Hold | Account, project and role authorization must pass adversarial tests |
| Customer production migration | Hold | All security and data-integrity blockers closed; live acceptance suite passed |
| Ongoing incremental replication | Hold | Watermark, key selection, overlap and restart correctness demonstrated |

These judgments apply to this archive, not to an unseen newer build or the colleague's deployed environment. This is a detailed engineering assessment, not a compliance certification or a complete penetration test.

## 2 Scope and evidence

The original ZIP was preserved. Review work used an extracted copy at `D:\Codex\migration-ai-review`. Application source was not patched to make checks pass. The root and frontend supplied `.env` files in the review copy were renamed so testing would not use their configuration. Test databases and credentials were synthetic. Bundled executable agents were inspected as package contents but were not executed.

| Item | Evidence |
|---|---|
| Supplied file | Migration-AI-Studio-2.5.0-Multi-Source-Connectivity (4).zip |
| ZIP size | 280,245,105 bytes, approximately 267.3 MiB |
| SHA256 | `2c80a90b9e90a513b722b9114ef48b9789a56acb2c25f91a13b46905856b3942` |
| Archive entries | 259, including 56 Git metadata entries |
| Product identity | Backend/package version 2.5.0; UI build marker 2.4.1 BRONZE_TARGET_CONSISTENCY; lockfile root version 2.4.1 |
| Runtime used | Windows, Python 3.12.14, Node 24.18.0; exact declared backend and frontend packages installed |
| Frontend production build | Passed; 654.22 kB JavaScript chunk, 177.44 kB gzip; build emitted a large-chunk warning |
| Included frontend test | Passed, but checks only seven source-code strings |
| Backend regression suite | 370 passed, 17 failed, 0 errors, 0 skipped out of 387 tests; 3358.9 seconds |
| Backend statement coverage | 74.9% statement coverage (9346 of 12481 measured statements). Coverage is execution evidence, not proof of correctness. |
| Focused review probes | 18 recorded observations across API security, data behavior, identifiers and agent staging |
| Browser review | Landing page, sign-in, project creation, environment setup, source setup and PostgreSQL/Oracle fields |
| Dependency audits | npm: two affected package entries rated high. Python declared requirements: 28 advisory records, 23 distinct IDs across four packages; exploitability requires context |

Evidence labels used below:

- **Reproduced:** Observed using actual local application handlers or functions and disposable data. External systems were replaced where stated.
- **Code confirmed:** The implementation directly shows the behavior; its live operational consequence was not exercised.
- **Risk:** A reasoned architectural or operational concern needing measurement or live validation.
- **Not verified:** The necessary external service, representative dataset or approved live test environment was not exercised.

**Scope boundary:** No live SQL Server, PostgreSQL, MySQL, Oracle, Databricks, Gemini, Ollama, Supabase or Brevo integration was certified. No supplied credential was tested for validity. No email was sent. A mocked lifecycle test is useful evidence of application orchestration, but cannot establish target SQL execution, migration accuracy or production performance.

The machine initially prevented local networking in restricted test processes. Those attempts were diagnosed and replaced with runs that permitted local execution. Their initial hangs and incomplete installation/build attempts are not classified as product defects. The final frontend build and focused results are the relevant evidence.

## 3 What this application is and does

The application helps a migration team turn existing relational schemas and SQL logic into a Databricks lakehouse implementation. It maintains a control database containing projects, source metadata, mappings, artifact versions, approvals, issues, deployments and validation evidence. Data is read from source databases and loaded into Databricks through direct connections or a local outbound agent.

Its intended users are migration engineers, solution architects and release reviewers. It can reduce repetitive discovery, SQL scaffolding, dependency planning and deployment tracking. Its generated output still requires review of business meaning, source-specific behavior and target runtime compatibility.

### Main workflow

1. Create a project and configure a Databricks workspace, warehouse and target catalog plan.
2. Register a source connection and discover available database objects and columns.
3. Assess compatibility, classify objects and establish source-to-target mappings.
4. Define a medallion design through inferred semantics, explicit definitions or natural-language requirements.
5. Generate versioned Bronze, Silver and Gold SQL or workflow artifacts.
6. Validate and review the exact artifact versions.
7. Load/deploy to DEV and reconcile the results.
8. Promote an approved manifest through TEST, UAT and PROD, subject to implementation-specific gates.
9. Optionally configure scheduled incremental synchronization and review operational evidence.

### Architecture in plain language

Source databases feed an engine adapter or local connector. The adapter converts discovery results into a common metadata model. FastAPI services use this model to generate and govern SQL. React presents the workflow and evidence. SQLAlchemy persists the control state in SQLite by default, with configuration paths for other relational stores. Databricks SQL connections execute artifacts and load data; larger loads can stage Parquet in a Unity Catalog Volume and use COPY INTO. Promotions clone Bronze data and retarget downstream SQL.

**Bronze** represents source-aligned data. **Silver** provides cleaned, standardized or historical data. **Gold** provides business-facing facts, dimensions, summaries and reporting views. The layers are generated structures; their names alone do not prove data quality or business correctness.

## 4 Feature inventory and realistic capability

| Capability | Implemented behavior | Practical boundary |
|---|---|---|
| Project workspaces | Projects, source profiles and project-scoped evidence | Project ownership filtering exists in lists but is not reliably enforced on direct access |
| Four source engines | SQL Server, PostgreSQL, MySQL/MariaDB alias and Oracle adapters | Connectivity support is broader than complete logic-migration support |
| Local connector | Outbound polling, source token hashing, task leases, rotation/revocation and streaming | Agent source contains all four engine branches, while release documentation says SQL Server-only; binary parity is defective |
| Discovery and drift | Object/column snapshots, hashes and metadata evidence | Non-SQL Server discovery omits important routines, definitions and relationships |
| Compatibility analysis | Type mapping and a transport registry; governed unknown types | DDL type mapping and runtime transport disagree for some added engines |
| Assessment and classification | Rules identify layers and routine intent | Heuristics are planning aids, not proof of a correct analytical model |
| SQL conversion | Tables, views and bounded SQL Server functions/procedures | Dynamic SQL, procedural side effects and unsupported syntax need redesign/review |
| Semantic medallion design | Consumer analysis, fact/dimension suggestions, explicit definitions, dependency graph | Incomplete source metadata and domain heuristics limit inference quality |
| Prompt-native design | Grounding, clarifications, plan edits, exact-plan approval and traceability | Requires precise business inputs; parser/generator behavior must be tested against each source domain |
| AI assistance | Deterministic-first remediation and provider-specific paths, including Ollama/Gemini | AI availability, rate limits, privacy and semantic accuracy remain external dependencies |
| Artifact governance | Version records, validation status, review decisions and change requests | Legacy endpoints permit role/reviewer bypass; some runtime repairs alter executed SQL |
| Bronze loading | FULL_LOAD/APPEND, private stages, count checks, Parquet/COPY option and batching | Equal-count reuse, agent binary encoding and content validation need correction |
| DEV deployment and resume | Ordered execution, recorded attempts and checkpoint reuse | Multiple legacy/new paths have different safeguards; cancellation is not consistently worker cancellation |
| Promotion | Manifest-based DEV/TEST/UAT/PROD paths; Bronze deep clones | No migration-wide transaction or demonstrated complete rollback; some direct endpoints lack confirmation/role enforcement |
| Reconciliation and gates | Bronze row-count comparisons; target/routine existence checks | Does not establish equal values, correct aggregates or routine result equivalence |
| Scheduled sync | Time-based polling, detected watermark, delta reads and MERGE/INSERT | Not safe to treat as complete CDC or reliable continuous replication in this build |
| Operational modules | Waves, cutover, decommission, governance and other records | Several modules are generic records/checklists; labels do not establish automated cutover or safe rollback |

### Engine support is uneven

| Engine | Direct discovery visible in code | Migration interpretation |
|---|---|---|
| SQL Server | Broad objects, definitions, parameters, dependencies, PK/unique/FK and table statistics, subject to source permissions | Most developed conversion path; still requires representative live tests |
| PostgreSQL | Tables/views, columns and PK/unique metadata for a selected schema | No view definition, routine or FK discovery in the new direct adapter; cannot claim full PostgreSQL modernization |
| MySQL/MariaDB | Tables/views, columns and primary-key metadata for a database | Missing view definitions, routine discovery and FK evidence in that adapter |
| Oracle | Tables/views, columns and PK/unique metadata for an owner | No routine/view SQL/FK discovery in that adapter; mixed-case identifiers need correction |

Both adapter and agent implementations must be covered by the compatibility matrix. They contain separate discovery/transport code and should not be assumed equivalent. The packaged executable's correspondence to the supplied agent source was not established.

## 5 Detailed findings and required fixes

Severity considers business impact and likely deployment exposure. **P0** means fix before shared or customer deployment; **P1** means fix before relying on the affected migration function; **P2** means an operational or maintainability improvement. These are review priorities, not externally calculated CVSS scores.

### F01 Unauthenticated password replacement and administrator issuance

**Critical · P0 · Reproduced**

`POST /api/register/set-password` accepts an email and password without requiring a verified, account-bound reset/registration token. Against an existing synthetic account it returned HTTP 200 and an ADMIN access token. It also created a fresh ADMIN account without an OTP exchange. Updating an existing account explicitly sets its role to ADMIN and clears lockout.

**Impact:** An unauthenticated caller can take over a known account or create administrator access. The visible OTP screens do not protect this final endpoint.

**Fix and acceptance:** Require a short-lived, single-use proof bound to the intended account and action; consume it atomically; preserve existing roles; restrict self-registration; invalidate affected sessions. Test direct endpoint calls, replay, wrong account, expiry, locked accounts and concurrent requests. Every attempt without valid proof must fail without changing credentials or issuing a token. OWASP's [password reset guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) provides the relevant token requirements.

**Source:** `backend/app/api/routes.py`, `register_set_password`; `supabase_auth_service.py`, password/OTP functions. Related weaknesses include OTP values printed to logs and returned when delivery fails, ordinary random-number generation, no visible OTP attempt throttling, and a separate Supabase login path that does not apply local lockout rules.

### F02 Project ownership is not an authorization boundary

**Critical · P0 · Reproduced**

A synthetic VIEWER could not see another owner's project in the project list, but could read its sources and create a new source by calling the project-ID endpoints directly. The auth dependency validates a token; it does not establish membership or ownership for the requested project. Many services check project existence or that an object belongs to that project, which is different from checking the caller's access.

**Impact:** Metadata and project state can be accessed across accounts. Administrator operations on another owner's project also need membership checks; an ADMIN role should not implicitly mean ownership of every customer's project.

**Fix and acceptance:** Apply one deny-by-default project membership/permission dependency to every project endpoint and subordinate lookup, including exports, connector registration, configuration, deletion and promotion. Test an owner, collaborator, viewer, unrelated administrator and anonymous caller against the same object IDs. This is the class of defect described by [OWASP object-level authorization guidance](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

**Source:** `routes.py`, `auth`, `projects_list`, `sources_list`, `source_create`; project service lookups.

### F03 Role restrictions and reviewer identity can be bypassed

**High · P0 · Reproduced locally**

A VIEWER approved a statically valid artifact using a different reviewer name supplied in the request body. A separate probe showed the same role could reach the production promotion service with no confirmation payload; the promotion service was mocked, so no production action occurred. The real service has additional manifest/precheck requirements, but the route itself lacks the necessary operator authorization and confirmation.

**Impact:** UI role restrictions and typed-confirmation dialogs do not consistently protect backend actions. Attribution can identify someone who did not approve the artifact.

**Fix and acceptance:** Define server-enforced permissions for generation, review, deployment and production release. Derive actor identity from the authenticated principal. Bind production authorization to project, environment, immutable manifest/hash and expiry. Verify that viewers cannot approve, unlock accounts or invoke deployment services, regardless of valid workflow state.

**Source:** `routes.py`, `review`, `user_unlock`, `prod_promotion_deploy_api`; newer `_admin_actor` protections are present on some routes and should become consistent.

### F04 Schedule endpoints allow unauthenticated operations

**Critical · P0 · Reproduced locally**

Schedule GET and PUT requests succeeded without authentication. An anonymous trigger-now request reached the incremental-sync service in a mocked probe. Reading a missing schedule also creates one, so GET is not consistently read-only.

**Impact:** Someone with a project ID can inspect sync metadata, change or disable scheduling, or initiate target work. Actual cloud writes were not performed in this review.

**Fix and acceptance:** Require project permission and appropriate execution roles for all schedule routes; make reads free of mutations; validate frequency, time, timezone and notification fields. An anonymous request must fail before database changes or worker invocation.

**Source:** `routes.py`, `get_project_schedule`, `update_project_schedule`, `trigger_schedule_now`.

### F05 Clients can fabricate quality-gate results

**High · P0 · Reproduced**

A VIEWER submitted PROD status PASSED with 999 passes and no measured checks. The lifecycle endpoint then showed PROD PASSED while DEV, TEST and UAT had not started. This does not prove every newer manifest-based deployment gate can be bypassed, but it proves displayed lifecycle evidence can be forged. Legacy promotion precheck consumes quality-gate evidence.

**Impact:** Audit records and release dashboards are not trustworthy evidence of testing.

**Fix and acceptance:** Make measured gate records internal outputs derived from immutable deployment/reconciliation manifests. If manual overrides are needed, store them as separately labeled, authorized exceptions with a reason and approver. A submitted status/count must never create a measured production pass.

**Source:** `routes.py`, `quality_gate`; `engine.py`, `lifecycle`, `promotion_precheck`.

### F06 The release archive contains populated sensitive configuration

**High with potentially critical exposure · P0 · Package inspection**

The supplied root `.env` has populated fields for Supabase service-role/anonymous keys, JWT secret, Databricks token, LLM key, a prompt test token and Brevo key. Values are intentionally omitted from this report. Their validity was not tested. The archive also contains Git metadata. The bundled backend database is a zero-byte file; no populated application records were found there.

**Impact:** Any real secrets in the ZIP should be treated as disclosed to its recipients. README statements that no credentials are included do not match the package. `render.yaml` also supplies a fixed bootstrap administrator password rather than requiring an operator-generated value.

**Fix and acceptance:** Have the owner determine which values are real and revoke/rotate those credentials; replacing the JWT secret alone is not a safe credential-migration plan because it also encrypts stored source/target secrets. Create release archives from an allowlist and scan both artifacts and history. Remove `.env`, Git internals and fixed bootstrap credentials. Deliver only examples containing unmistakable placeholders.

**Evidence:** `package-inventory.json`, `.env` variable names, `render.yaml`, README release claims.

### F07 Incremental synchronization can miss or replay records

**High · P1 · Reproduced and code confirmed**

For integer rows 8, 9 and 10, the sync function persisted watermark **9**, not 10, because it compares string representations. Trackers for `dbo.Orders` and `archive.Orders` reused the same record because the identity is project plus table name rather than source/schema/object identity.

The SQL Server delta adapter reads TOP 1000 by default and orders only by the watermark, then resumes with strict `watermark > previous`. A boundary shared by more than 1000 equal timestamps can leave rows behind permanently. This scenario is code-derived; it was not run against SQL Server. Rows arriving late at an older watermark and source deletions are also not captured by this strategy.

Key and watermark selection rely on names/identity heuristics rather than authoritative PK/unique evidence. A created-date watermark cannot capture later updates; an identity may not be the real merge key; composite keys are not reliably derived. SQL Server `timestamp` is binary rowversion but is also listed among datetime watermark candidates.

**Fix and acceptance:** Persist typed watermarks scoped to a unique source object; require approved non-null ordering and merge keys; use stable composite pagination `(watermark, unique key)` with an upper bound, or an appropriate CDC/change-tracking design. Add overlap/deduplication policy where needed. Test numeric boundaries, timestamp ties, late changes, deletes, composite keys and identical names across sources. Never silently select the first column for a production sync policy.

**Source:** `watermark_service.py`, detection/tracking/sync functions; `source_adapters.py`, `open_delta_cursor`.

### F08 The scheduler can claim an already running job again

**High · P1 · Reproduced**

Calling the due-schedule claim function twice returned the same project twice. Claiming changes `last_run_status` but does not atomically acquire a lease or move the due timestamp. A job that outlives the poll interval remains eligible. Multiple server processes can each start a scheduler.

**Impact:** Overlapping syncs can race on watermarks, duplicate inserts, increase warehouse cost and overwrite operational state. The async project sync performs synchronous database/connector work before reaching its email await, which can block the event loop; observed overlap timing will therefore vary by deployment. Neither condition makes the claim safe.

**Fix and acceptance:** Use database-backed leases with atomic claim/expiry, one active job per project, heartbeats and controlled retries. Advance scheduling under the same ownership model. Test two schedulers, slow jobs, process crashes and lease expiry; only one worker may execute a given occurrence.

**Source:** `scheduler_service.py`, `_check_and_claim_due_schedules`, worker loop; `watermark_service.py`, `run_incremental_sync_for_project`.

### F09 Equal row counts can silently skip extraction and APPEND

**High · P1 · Reproduced**

The private table loader returns PASSED/reused when existing target count equals expected source count and replacement is false. In the APPEND probe, it returned success without calling the extractor. Equality of counts also cannot detect changed values, different keys or schema mismatch.

**Impact:** APPEND may append nothing, and reuse may keep incorrect data. The public FULL_LOAD path has a separate replacement guard, so exposure depends on the workflow and loader entry point; this is not a claim that every full load skips data.

**Fix and acceptance:** Separate APPEND semantics, explicit checkpoint reuse and replacement. Require a verified manifest tied to object identity, target schema, data snapshot/watermark and content checks. Test equal counts with changed values, disjoint keys, changed schemas and repeated APPEND calls. Return a clear reused/no-op result only when the requested semantics permit it.

**Source:** `bronze_ingestion.py`, `_load_table`, `run`, `verified_checkpoint`.

### F10 New engine datatype mappings disagree with runtime transport

**High · P1 · Reproduced**

The DDL mapper recognizes PostgreSQL `bytea` as BINARY, but the runtime transport registry classifies it as unknown STRING and normalizes bytes to Python representation text such as `b'\\x00\\xff'`. This is not the hexadecimal transport expected by the binary reconstruction path. Similar parity concerns apply to added BLOB/RAW families and other native driver objects.

**Impact:** A successful connection or correct table DDL does not establish correct value transport. Data may fail conversion or lose its original representation.

**Fix and acceptance:** Build one engine-aware canonical type contract covering source type, driver value, DDL type, normalization, bind/COPY expression and validation. Test actual round trips for byte arrays/memoryviews, LOBs, booleans, JSON, timestamps with offsets, decimal extremes and unknown types. Assert byte-for-byte equality, not just type names.

**Source:** `rules.py`, `TYPE_MAP`; `type_compatibility.py`, `ADAPTER_SPECS`, `transport_plan`, `normalize_source_value`; `source_adapters.py`.

### F11 Agent bulk staging bypasses canonical binary normalization

**High · P1 · Reproduced with mocked upload**

The agent's `stage_and_upload` operation writes raw driver values through `str()` into string-typed Parquet columns. A local probe inspected the actual Parquet: bytes `00ff` became `b'\\x00\\xff'`, not `00ff`. The backend COPY projection uses its canonical bind expressions, including `unhex` for SQL Server binary types.

**Impact:** Binary/image/rowversion behavior differs between small streaming and bulk agent loads. A row-count check cannot detect value corruption. No live COPY was run; the incompatible staging representation itself was reproduced.

**Fix and acceptance:** Share or version the exact transport contract between server and agent. Have the agent declare the produced encoding and validate it before COPY. Run byte-for-byte round trips below and above the 5000-row bulk threshold and compare direct, streaming-agent and bulk-agent outputs.

**Source:** `scripts/local_connector.py`, `UniversalLocalAgent.handle`; `bronze_ingestion.py`, `_load_table_via_parquet_copy_into`.

### F12 Non-SQL Server discovery is incomplete for downstream generation

**High · P1 · Code confirmed**

The new adapters discover tables/views and column/key subsets but do not retrieve view SQL, routines or foreign keys. Their canonical snapshot sets `definition` to null and dependencies/parameters to empty lists. Missing relationships weaken semantic inference and join planning; missing definitions prevent faithful view conversion.

**Fix and acceptance:** Declare discovery capabilities per engine and object type. Implement routine/view definition and FK/dependency discovery where supported. Distinguish permission-denied metadata from absent metadata. Test a schema containing views, composite FKs, generated/identity columns and routines on every advertised engine; show unsupported items explicitly and block dependent generation.

**Source:** `source_adapters.py`, engine discovery functions and `_canonical_snapshot`; separate agent discovery implementation.

### F13 Runtime auto-healing can execute SQL that was not approved

**High · P1 · Reproduced transformation and code confirmed execution path**

Compiler repair changed `t.order_id` to `t.sale_id` based on a configured synonym pair. The deployment helper retries patched SQL and records original/patched hashes, but does not require a new artifact version and approval before executing it. The helper is also used in environment promotion.

**Impact:** Runtime behavior can diverge from the reviewed artifact. A suggested column and a name synonym do not prove business equivalence, particularly across financial or customer keys. Audit logging is helpful but occurs after the decision to execute.

**Fix and acceptance:** Restrict automatic corrections to provably equivalent identifier spelling under an approved policy. Route semantic substitutions through a new artifact version, validation and review, especially for PROD. A test must show executed SQL hash equals the authorized manifest hash, or a separately approved transformation hash.

**Source:** `sql_preflight.py`, `SYNONYM_PAIRS`, `compiler_identifier_repair`; `deployment.py`, `_safe_execute_with_auto_healing`, promotion methods.

### F14 Reconciliation is too weak for the claims made

**High · P1 · Code confirmed**

Bronze reconciliation compares row counts. Most non-Bronze objects receive count/existence checks; functions and procedures receive metadata existence checks rather than business-result comparisons. Hashes elsewhere mainly identify SQL or metadata, not migrated row contents. The landing page claims checksum verification between source and target, which was not found in the reviewed reconciliation paths.

**Impact:** Incorrect amounts, shifted timestamps, broken joins, duplicate keys, missing updates and wrong routine results can pass available checks.

**Fix and acceptance:** Add per-partition key counts, null/duplicate checks, canonical data hashes, numeric aggregates, timestamp/binary round trips and domain-specific result comparisons. Compare at a defined consistent source point. Keep existence, structural, data and business checks visibly separate; do not label an existence check as data reconciliation.

**Source:** `deployment.py`, `_reconcile_medallion_run`, `run_reconciliation`; `frontend/src/LandingPage.tsx`.

### F15 Readiness and progress indicators are misleading

**Medium · P1 · Browser reproduced**

A newly created project displayed 50% complete. With no target configuration, the header displayed DEV: Connected and environment footer said configured. With zero sources, the Sources footer said one SQL Server source configured. Code derives progress from project status buckets and uses `sources.length || 1`; connection status defaults to connected when no failure/running condition applies.

**Impact:** Operators can misread prerequisites and release readiness. The error state must not be the only alternative to connected.

**Fix and acceptance:** Derive indicators from measured stage evidence; use explicit not configured, not tested, testing, ready, stale and failed states. Completion requires defined outputs. An empty project must show zero completed migration stages, zero sources and no connected target.

**Evidence:** `ui-source-status.png`; `App.tsx`, header status, project progress calculation and stage context.

### F16 The interface silently limits inventory to 500 objects

**Medium · P1 · Code confirmed**

The inventory API caps page size at 500. The main frontend refresh requests one page with `limit=500` and does not paginate that collection. Other metadata collections can be fetched without meaningful pagination. At larger schemas this creates incomplete selections and inconsistent totals, alongside unnecessary payload cost.

**Fix and acceptance:** Implement server-side filtering, totals, cursor/page navigation and selective loading. Test at least 1001 mixed objects and verify every object is discoverable and selectable without loading all SQL/version content into the browser.

**Source:** `routes.py`, `inventory`; `App.tsx`, `refresh`.

### F17 Docker and hosted deployment paths have inconsistent assumptions

**High operational risk · P1 · Code confirmed, containers not executed**

Compose runs a separate nginx frontend, but its Dockerfile provides no `/api` reverse-proxy configuration; the frontend default uses `/api` and the supplied frontend environment points to browser-local port 8010. The Compose backend is exposed on port 8000. The backend-only image also does not install SQL Server ODBC system dependencies, unlike the root combined Dockerfile.

The Compose data volume is mounted at `/app/data`, but the configured default database path is derived from the code root and is not that directory unless `DATABASE_URL` is explicitly corrected. The free hosted example itself notes local SQLite loss on restart/redeploy. The combined image is a separate deployment route and should not be conflated with the broken Compose assumptions.

**Fix and acceptance:** Pick supported deployment profiles; give each explicit API routing, database persistence, migration/bootstrap, health and ODBC requirements. Run clean-room Windows and container smoke tests. Create a project, restart/redeploy, and verify it survives. Browser API calls must reach the correct service from a separate client machine.

**Source:** root/backend/frontend Dockerfiles, `docker-compose.yml`, `render.yaml`, `config.py`, frontend environment example.

### F18 The regression suite does not provide a clean release signal

**High release risk · P1 · Executed suite evidence**

**Result:** 370 passed, 17 failed, 0 errors, 0 skipped out of 387 tests; 3358.9 seconds. Failures include stale mocks, changed API contracts and generation/governance expectation mismatches. Individual failures and classification are listed in the test appendix below; unresolved failures remain release work.

The test collection includes useful governance, orchestration, type and deployment cases, but also outdated mocking assumptions and tests that check generated strings or mock away the external engine. The seven-string frontend contract cannot catch the reproduced UI contradictions, account-flow defects or role bypasses. A test named end-to-end may still replace loading, target execution and reconciliation with canned results.

The 17 failures need differentiated triage: eight involve stale or incomplete test doubles, four depend on SQL punctuation, UI wording/whitespace or exact error text, two expose health/payload-policy contract mismatches, and three concern domain behavior. The hospitality test omitted Rooms from the expected function inputs; the university GPA generator did not reference the expected enrollment relation; and the payroll lifecycle returned DEV_DEPLOYMENT_FAILED rather than DEV_GATE_PASSED. These three warrant priority functional investigation. The suite does not establish the final business outputs against live data, and 17 failures should not be presented as 17 independently verified production defects.

**Fix and acceptance:** Repair failures based on intended behavior, not by weakening assertions. Add negative permission/account tests and the reproduced transport/sync cases. Separate unit, API, browser, adapter-integration and live migration suites with clearly different reports. Block releases on a clean required suite and validated source/target compatibility matrix.

**Evidence:** `backend-tests.xml`, `backend-tests-network.log`, `backend-coverage.json`, frontend test source and focused probes.

### F19 Secret encryption and session lifecycle need separation

**Medium · P1 · Code confirmed**

Source and direct target credentials use Fernet encryption with a key derived from `JWT_SECRET`. Rotating the signing secret therefore prevents decryption of existing stored credentials. There is no key-versioned re-encryption workflow in the reviewed path. Target token lookup can silently fall back to an environment token when direct-token decryption fails.

The auth dependency trusts JWT claims until expiry without consulting current user lockout or membership state. The default access lifetime is 24 hours and the frontend stores the token in localStorage. These choices need a defined session revocation and browser threat model; no XSS exploit was demonstrated.

**Fix and acceptance:** Separate signing and encryption keys, add key IDs/rotation, use managed secret storage where possible, fail clearly on decryption errors, and enforce membership/role changes on active sessions. Test key rotation and disabled-user access without losing stored connection profiles.

**Source:** `source_adapters.py`, encryption functions; `security.py`; `environment_provisioning.py`, `_token`; `config.py`; frontend `api.ts`.

### F20 Declared dependencies have current advisories

**High dependency severity with context-dependent product exposure · P1 · Registry audit**

The npm audit reported two affected package entries rated high, including Vite 8.2.2 and source-map-js. The [reviewed Windows editor advisory](https://github.com/advisories/GHSA-587h-7wmj-h5pm) includes this Vite range; the [source-map advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q) concerns denial of service from crafted indexed maps. The raw audit contains additional Vite advisories.

These findings do not establish that the same vulnerabilities are exploitable in a static nginx production bundle. Vite development-server exposure and ingestion of untrusted source maps have different preconditions.

A separate audit of the directly declared Python requirements reported 28 advisory records, representing 23 distinct advisory IDs across pydantic-settings 2.13.1, PyJWT 2.13.0, pytest 9.0.2 and cryptography 44.0.1. Duplicate records were retained in the raw evidence rather than counted as additional distinct IDs. This was a direct-requirement scan with dependency resolution disabled, not an audit of all resolved transitive packages. Package advisories are not demonstrated application exploits: for example, the reviewed JWT decode uses a single configured algorithm with default signature verification, while several returned PyJWT advisories require different options or mixed algorithms; the pytest advisory describes UNIX temporary-directory behavior, whereas these tests ran on Windows. Each advisory needs an applicability decision.

**Fix and acceptance:** Update to supported patched versions, regenerate the lockfile and rebuild/retest. Keep build tools out of the production runtime where feasible. Add software composition analysis for Python, npm, container base images and the packaged executable; evaluate actual exposure rather than counting advisories as demonstrated exploits.

**Evidence:** `frontend-audit.json`, `python-audit.json`; package and lock manifests; advisories checked on the review date.

### F21 Long operations lack a consistent durable worker model

**High operational risk · P1 · Code confirmed and architectural inference**

Many route handlers execute migration services synchronously. Some orchestration state is persisted, but there is no common external job queue with leased worker ownership, restart recovery and consistent cancellation. The schedule's async function performs blocking sync work. The medallion cancel/status helpers can record FAILED/CANCELLED without proving a running worker or target query has stopped; status reads can also write timeout evidence and later delete it.

**Impact:** Slow migrations can consume request capacity, outlive request timeouts and continue while an operator starts a retry. Restart and horizontal scaling behavior is difficult to reason about. This was not load-tested, so no concurrency ceiling is claimed.

**Fix and acceptance:** Submit durable jobs and return job IDs promptly; let workers own execution through leases. Support cooperative cancellation and target-query cancellation, crash recovery, idempotent publication and explicit uncertain-commit states. Test killing an API process/worker during extraction, upload, COPY, MERGE and promotion.

**Source:** synchronous deployment routes; `scheduler_service.py`; `watermark_service.py`; `deployment.py`, status/cancel helpers; orchestration services.

### F22 An empty rediscovery does not remove stale inventory

**Medium · P1 · Reproduced**

After existing objects were present, ingesting an empty snapshot left them in the inventory. Stale-object pruning runs only when the new snapshot has at least one seen object. A database whose objects were all removed, or a source account that can no longer see them, can therefore retain misleading old evidence.

**Fix and acceptance:** Define whether empty discovery is authoritative or an error/permission state. Apply a transactional snapshot generation with explicit completeness and deletion semantics. Do not silently retain old objects as current; do not delete valid metadata after a failed/partial discovery. Test empty, partial, failed and permission-restricted snapshots.

**Source:** `engine.py`, `ingest_snapshot`.

### F23 Oracle quoting changes case-sensitive identifiers

**Medium · P1 · Reproduced function behavior**

The direct Oracle adapter turns `MixedCase` into `"MIXEDCASE"` when quoting. Oracle objects intentionally created with quoted mixed-case names require their exact spelling. The agent's quoting helper preserves case, introducing another direct/agent difference.

**Fix and acceptance:** Preserve the exact discovered identifier in quoted SQL and distinguish quoted/unquoted discovery semantics. Test lowercase, mixed case, embedded quote and reserved-word names through discovery, extraction and delta reads.

**Source:** `source_adapters.py`, `OracleAdapter.quote_identifier`; `scripts/local_connector.py`, identifier quoting.

## 6 Performance bottlenecks and capacity limits

No representative source/target performance benchmark was run. The following mechanisms identify where to measure; they are not invented throughput numbers or proof of a particular maximum database size.

| Area | Bottleneck or limit visible in code | Consequence and next measurement |
|---|---|---|
| PostgreSQL extraction | Ordinary psycopg2 cursor rather than a named server-side cursor | Large results may be buffered despite fetchmany; measure peak process memory across table sizes |
| Full-load consistency | Source count and extraction use separate operations/connections | A changing source can fail count validation or represent no single consistent point; test under concurrent writes |
| Direct bulk staging | One local Parquet file per table; direct upload guard at 5 GiB | Large/wide tables need disk capacity, chunked staging and cleanup guarantees; test near and above limits |
| Bulk representation | Parquet columns are strings; conversion occurs on load | Extra serialization/casting and weaker native type fidelity; measure CPU, file size and conversion failures |
| Insert fallback | SQL VALUES strings built in chunks of 2500 rows | Wide/LOB-heavy rows can exceed practical statement/HTTP limits; size by bytes as well as rows |
| Incremental writes | Inline MERGE/INSERT chunks of 500; per-table source/target work | Many small statements and commits can dominate warehouse latency; profile execution counts and elapsed time |
| Table concurrency | Several paths hard-code up to four workers; connector paths can serialize | `PARALLELISM` configuration is not consistently the actual concurrency control; measure backend and warehouse saturation |
| Connector transport | Eight waiting operations per process, task polling, 120-second ordinary/900-second staging timeout | Throughput and failure behavior depend on polling, service capacity and result size; test slow/offline agents |
| Connector result size | 16 MiB compressed request-body guard; gzip decompression lacks a second expanded-size guard | Row limits are not byte limits; decompression can amplify memory use; enforce both bounds |
| Metadata store | Frequent evidence writes; SQLite default and concurrent sessions | Writer contention and evidence growth; benchmark concurrency, retention and database migration behavior |
| API/UI refresh | Many collections refetched; active work triggers refresh every three seconds | Request fan-out, redundant large payloads and overlapping refreshes; profile 1/10/50 viewers and stale response ordering |
| Frontend | App.tsx exceeds 11000 lines; main compiled chunk exceeds 650 kB | Harder maintenance and broad rerenders; measure first load and split by workflow/module |
| Promotion | Deep clone copies Bronze data across environments | Additional storage, warehouse use and elapsed time; measure representative three-hop promotion cost |
| AI fallback | Provider timeout default 120 seconds; bounded attempt/cooldown behavior | Interactive repair latency and cost vary widely; record prompt bytes, attempt counts, token usage and provider errors |

The PostgreSQL memory concern follows the library's documented distinction between ordinary and named cursors; it remains a workload-dependent inference. See the [psycopg2 connection documentation](https://www.psycopg.org/docs/connection.html) and [server-side cursor guidance](https://www.psycopg.org/docs/usage).

The most urgent bottleneck is engineering confidence: multiple control paths and duplicated adapter/agent logic make every feature addition harder to validate. Reducing those variations will improve correctness and performance tuning together.

## 7 Functional boundaries to communicate honestly

- **Connectivity is not conversion parity.** Registering four engine types does not establish support for their full SQL dialects, routines, dependencies or special types.
- **Incremental loading is not complete CDC.** This build does not demonstrate reliable delete propagation, late-change capture, boundary-safe timestamp pagination or transactional replication.
- **Static validation is not business validation.** Parsed SQL and successful EXPLAIN/existence checks cannot prove that joins, formulas, SCD2 histories or procedure side effects match the source.
- **A medallion design needs business ownership.** Generated grain, keys, measures, discounts, status filters and temporal assumptions must be reviewed against actual requirements. Domain examples are not universal correctness evidence.
- **Triggers, operational transactions, dynamic SQL, CLR and encrypted routines require redesign or manual handling.** Databricks is an analytical target, so source operational semantics cannot simply be assumed to transfer.
- **Multiple sources can produce naming collisions.** Several target paths use the source table leaf name. Some ingestion paths block collisions, which is helpful, but a clear source/schema-aware namespace policy is still necessary.
- **Promotion is not an atomic cutover.** Per-object execution and deep clones do not provide all-or-nothing release behavior across a database or dependent consumers.
- **Cutover/decommission records are not a proven cutover engine.** Consumer repointing, rollback rehearsals, lag measurement, acceptance and retention need explicit operational procedures.
- **External AI is a data-governance choice.** Source definitions, column metadata and prompts can leave the deployment when a remote provider is enabled. The package does not establish a complete organizational consent, retention or sensitive-metadata policy.
- **Production hardening is incomplete.** SSO/MFA, centralized authorization, durable execution, backup/restore evidence, observability and incident-response procedures were not demonstrated as a complete operational system.

## 8 Strengths worth preserving

There is useful engineering here that should survive remediation. Deterministic rules run before AI in important paths; generated candidates generally become reviewable artifact versions; approved semantic definitions are protected in the intended inference flow; dependency and SQL-reference checks can block unsupported work; transport errors contain metadata rather than source values; and source adapter identifiers are mostly quoted rather than directly concatenated unescaped.

The newer Bronze loader uses a private stage and publishes a full-load target after checks, reducing the risk of exposing partially loaded live tables. Project-scoped Databricks execution avoids a global-target fallback in important ingestion paths. Connector tokens are hashed, leases mitigate replay, and rotation/revocation are implemented. Tests cover several of these behaviors.

The appropriate response is to consolidate and complete these safeguards, then make them mandatory across every route and execution path. Adding UI confirmation or documenting a safe path will not fix an unsafe alternative API.

## 9 Recommended update sequence

### Release A Establish a trustworthy security boundary

**Owners:** Backend/security lead, release engineer and QA.

Close F01–F06 first. Remove credentials from distribution, replace fixed bootstrap secrets, enforce project membership and backend roles, repair registration/reset, protect schedules and stop client-created measured gates. Review Supabase and local authentication as one security model. Patch dependency advisories as part of the same release preparation.

**Exit criteria:** Direct endpoint attacks fail; unrelated accounts cannot read/mutate a project; a viewer cannot review/deploy/unlock users; no OTP or usable secret appears in logs/artifacts; all required regression checks pass. Do not resume shared deployment on the strength of a successful UI walkthrough alone.

### Release B Prove data correctness and recovery

**Owners:** Data platform/connector engineers, migration architect and QA.

Address watermark/key policy, scheduler leases, type parity, agent bulk encoding, reuse semantics, discovery completeness, runtime repair policy and reconciliation. Create a single versioned transport contract and a release manifest that binds approved code, source snapshot, target and validation evidence.

**Exit criteria:** Byte/value comparisons and business aggregates match on representative datasets; boundary/late/duplicate/delete cases have explicit expected behavior; process termination and retries do not duplicate or lose data; executed SQL corresponds to approved artifacts. Gate enabling of scheduled sync on this evidence.

### Release C Make scale and operations predictable

**Owners:** Platform engineer, frontend lead, product/UX and operations.

Adopt a durable worker model, verify cancellation, implement PostgreSQL streaming and chunked staging, standardize deployment profiles, add pagination and truthful status, split the frontend and introduce operational telemetry. Automate clean packaging and compatibility reports.

**Exit criteria:** Published scale envelope, measured throughput/memory/warehouse cost, tested restart/restore, reliable UI with large schemas, and a clean installation on every supported profile. Choose acceptance targets from actual user workload and business requirements rather than an arbitrary tables-per-hour claim.

## 10 Live acceptance suite still required

Before a production decision, run the following in a designated non-production source/target setup with synthetic or approved representative data. Record engine/runtime versions, warehouse configuration, object counts, data sizes and cost. Preserve raw evidence and independently calculated expected results.

| Test family | Minimum scenarios | Required evidence |
|---|---|---|
| Installation and upgrades | Clean Windows, combined container, Compose if retained, existing DB migrations | Startup, browser API routing, successful schema upgrade and retained projects |
| Security | Owner/collaborator/viewer/unrelated admin/anonymous; OTP replay/expiry; disabled user | Denied unauthorized operations and unchanged state; correct audit actor |
| Discovery per engine | Tables, views, routines, PK/composite FK, identities, quoted identifiers, permission limits | Complete supported metadata and explicit unsupported/partial status |
| Type fidelity | Empty/null, Unicode, max decimal, date/time/offset, binary/LOB/JSON/unknown types | Byte-for-byte or documented canonical value equality |
| Load sizes and paths | 0, 1, 4999, 5000, 5001 rows; large/wide tables; agent/direct | Equal results across threshold and transport paths; bounded memory/disk |
| Repeatability | Same-count changed data, APPEND rerun, empty rediscovery, schema drift | Correct state transition; no count-only false success |
| Incremental safety | More than 1000 equal timestamps, 9→10 and 99→100, late rows, updates, deletes, composite keys | No skipped/duplicated committed changes under the declared policy |
| Source consistency | Continuous concurrent inserts/updates during count/extraction | Defined snapshot/cutoff behavior and meaningful reconciliation |
| Recovery | Stop API/worker/agent during fetch, upload, COPY, MERGE and publication | No data loss; idempotent resume; uncertain commits clearly reported |
| Scheduler | Two workers, a job longer than 30 seconds, crash and clock/timezone boundaries | One owner per run, correct next occurrence, no uncontrolled overlap |
| SQL/business semantics | Representative views/functions/procedures, SCD2 updates, joins and aggregate fixtures | Expected rows, amounts, histories and side effects match agreed requirements |
| Promotion and rollback | Approved version change, revoked review, wrong catalog, partial failure, retry, rollback rehearsal | Exact approved manifest; no accidental cross-environment writes; documented rollback |
| Load and UI scale | 1001+ objects, wide schemas, growing evidence, multiple viewers and concurrent projects | Full visibility, responsive UI, measured p50/p95 latency and resource use |
| Operations | Backup/restore, secret rotation, log retention, staging cleanup, health/readiness, alerts | Demonstrated recovery and actionable monitoring without secret disclosure |

For a release-quality performance result, collect rows/sec and MiB/sec alongside peak memory, local staging disk, source CPU/locks, statement count, warehouse duration/cost, job recovery time and UI/API latency. Report results per engine and path; a single small SQL Server demo cannot represent every supported source.

## 11 Evidence package and how to use it

The accompanying update backlog maps each finding to a proposed owner, priority, source location and acceptance condition. It is intended for grooming into engineering work, not as an automatic estimate of effort.

The focused verification script uses disposable databases and synthetic credentials. Its output records HTTP statuses and behavioral results without real tokens or secret values. It deliberately demonstrates vulnerable behavior; after fixes, convert each observation into a regression test that asserts the secure/correct result. Do not treat the current probe's successful execution as a security pass.

Included evidence files:

- `focused-findings.json` and `focused-findings-final.log` — 18 focused observations.
- `verify_findings.py` — reproducible local probes with external operations mocked where required.
- `backend-tests.xml`, `backend-tests-network.log`, `backend-coverage.json` — full-suite outcome and statement coverage.
- `frontend-build-final.log`, `frontend-test-final.log`, `frontend-audit.json`, `python-audit.json` — build, limited contract test and advisory results.
- `package-inventory.json` — archive fingerprint and sensitive variable names; no secret values.
- `ui-source-status.png` — browser evidence of zero sources alongside configured/connected claims.
- `Update-Backlog.csv` — prioritized work items and acceptance criteria.

### Final decision for planning

Keep the product direction and the useful generation/governance foundation. Treat this build as a development-stage migration platform with serious release blockers. Allocate the next engineering work to trustworthy identity/authorization, correct data movement and independently measured validation. Expand advertised capabilities only when each engine and execution path has reproducible acceptance evidence.


## 12 Backend regression failure appendix

The complete suite was run without modifying application source or the supplied tests. This appendix preserves failed test identities. A stale mock is a test-maintenance failure; it is not automatically evidence that a source connection is broken. Other failures need engineering triage against the intended product contract.

- **tests.test_360::test_source_connection_endpoint_mocked** — AttributeError: <module 'app.api.routes' from 'D:\\Codex\\migration-ai-review\\backend\\app\\api\\routes.py'> has no attribute 'test_sqlserver_connection'
- **tests.test_api::test_health** — AssertionError: assert (200 == 200 and 'degraded' == 'ok'  +  where 200 = <Response [200 OK]>.status_code      - ok   + degraded)
- **tests.test_deployment_execution::test_destructive_artifact_requires_explicit_approval** — AssertionError: assert ['DELETE FROM target_table;'] == ['DELETE FROM target_table']      At index 0 diff: 'DELETE FROM target_table;' != 'DELETE FROM target_table'   Use -v to get more diff
- **tests.test_frontend_contract::test_frontend_has_no_recovery_placeholder** — assert 'Run discovery' in 'import { useEffect, useMemo, useState, useCallback, useRef } from "react";\nimport { api, downloadApi, subscribeApiAc...\n          </tr>\n        ))}\n      </tbody>\n    </table>\n  ) : (\n    <Empty text="No records yet." />\n  );\n}\n'
- **tests.test_frontend_contract::test_frontend_api_uses_same_origin_api_for_production** — assert "import.meta.env.VITE_API_URL /  / '/api'" in "const API = import.meta.env.VITE_API_URL  /  /  '/api';\nexport const token = () => localStorage.getItem('mf_token')  /  /  '...(a);\n    a.click();\n    a.remove();\n    URL.revokeObjectURL(url);\n  } finally {\n    notifyActivity(-1);\n  }\n}\n"
- **tests.test_hotel_operations_domain::test_hotel_operations_domain_grounding_and_function_generation** — AssertionError: assert {'Bookings'} == {'Bookings', 'Rooms'}      Extra items in the right set:   'Rooms'   Use -v to get more diff
- **tests.test_multi_domain_end_to_end::test_domain_1_employee_payroll_full_lifecycle** — AssertionError: assert 'DEV_DEPLOYMENT_FAILED' == 'DEV_GATE_PASSED'      - DEV_GATE_PASSED   + DEV_DEPLOYMENT_FAILED
- **tests.test_multi_domain_end_to_end::test_domain_4_educational_university_full_lifecycle** — AssertionError: assert 'vw_enrollments_clean' in 'CREATE OR REPLACE FUNCTION `university_dev`.`silver`.`fn_calculate_student_gpa`(p_student_id INT)\nRETURNS DECIMAL(18...OM `university_dev`.`silver`.`vw_students_clean` s\n  WHERE s.student_id = p_student_id\n), CAST(0 AS DECIMAL(18,2)));'  +  where 'CREATE OR REPLACE FUNCTION `university_dev`.`silver`.`fn_calculate_student_gpa`(p_student_id INT)\nRETURNS DECIMAL(18...OM `university_dev`.`silver`.`vw_students_clean` s\n  WHERE s.student_id = p_student_id\n), CAST(0 AS DECIMAL(18,2)));' = <app.models.entities.MigrationStageArtifactVersion object at 0x000001CE52396DE0>.content
- **tests.test_pass2_pass3_optimization::test_copy_restores_types_and_cleans_files** — TypeError: test_copy_restores_types_and_cleans_files.<locals>.<lambda>() got an unexpected keyword argument 'on_progress'
- **tests.test_plan_correction::test_cycle_cross_layer_and_required_delete_blocked** — AssertionError: Regex pattern did not match.   Expected regex: 'dependent artifacts'   Actual message: 'vw_order_items_clean requires a Bronze copy of OrderItems'
- **tests.test_source_connector::test_expired_and_oversized_results** — assert 422 == 413  +  where 422 = <Response [422 Unprocessable Entity]>.status_code
- **tests.test_source_connector::test_source_test_and_discovery_use_connector** — AttributeError: <module 'app.api.routes' from 'D:\\Codex\\migration-ai-review\\backend\\app\\api\\routes.py'> has no attribute 'test_sqlserver_connection'
- **tests.test_source_connector::test_local_agent_rejects_arbitrary_operations_and_wrong_source** — AttributeError: module 'local_connector' has no attribute 'LocalAgent'
- **tests.test_source_connector::test_local_cursor_batches_do_not_skip_rows** — AttributeError: module 'local_connector' has no attribute 'LocalAgent'
- **tests.test_source_connector::test_table_read_uses_local_metadata_and_parameterized_lookup** — AttributeError: module 'local_connector' has no attribute 'LocalAgent'
- **tests.test_type_compatibility::test_bronze_loader_builds_binary_safe_source_and_target_sql** — AttributeError: 'SourceCursor' object has no attribute 'close'
- **tests.test_workflow_deployment_integration::test_provider_secret_is_redacted_before_failure_logs_are_saved** — AttributeError: <module 'app.services.medallion' from 'D:\\Codex\\migration-ai-review\\backend\\app\\services\\medallion.py'> has no attribute 'execute_sql'
