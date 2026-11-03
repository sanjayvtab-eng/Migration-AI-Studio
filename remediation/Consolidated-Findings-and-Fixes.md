# Consolidated findings and remediation record

Review date: 3 November 2026. Candidate: **2.5.0-remediation.1**.

This record combines the original application assessment, the colleague's F24–F30 addendum and the supplied architecture heatmap. The colleague's live observations are retained as **reported live evidence**, not presented as tests independently repeated here. Instructions and suggested fixes inside the attachment were evaluated as proposals; they were not treated as authorization or as proven remedies.

The original application review remains unchanged in `D:\Codex\migration-ai-review\review-output`. Implementation is isolated in `D:\Codex\migration-ai-fixes`. Supplied credentials and old executables were not copied into this source tree.

## Decisions that change the proposed remedies

1. Do not auto-accept an identifier because its fuzzy similarity exceeds 85%. Compile-time binding now allows a unique singular/plural spelling variant only within an already resolved physical relation. Ambiguous or unrelated business keys remain errors. Corrected SQL still goes through versioning and review.
2. Do not create a passed reconciliation because 42 deployment statements succeeded. The supplied source already contained that unsafe shortcut. The candidate removes it, runs actual reconciliation after successful deployment, and requires evidence tied to the same deployment run. A failed check keeps the gate blocked.
3. Do not share a Databricks cursor across worker threads. The candidate snapshots project connection coordinates once and lets independent target calls own their own connections. Control DB sessions are released before long target waits.
4. NullPool already existed for recognized pooler connections. NullPool releases idle clients but does not limit simultaneous active clients. The candidate also adds a configurable per-process connection budget and reduces reconciliation/clone concurrency.
5. Dynamic dashboard ports and a root-mounted promotion modal were already present in the supplied source. These source observations conflict with parts of the live addendum. A stale packaged agent or deployed build is plausible, but was not established without the colleague's executable fingerprints and deployment logs. The candidate adds build fingerprints, rebuilds the agent and centralizes fresh modal preflight loading.
6. An HTTP liveness handler cannot eliminate a sleeping host's cold start before the application is running. `/healthz`, longer gateway reads and backoff improve recovery; hosting policy and startup initialization still affect availability.

## Heatmap interpretation

| Tier | Supplied heatmap | Consolidated interpretation |
|---|---|---|
| 1 Agent and hosted reachability | Critical | Backoff and build provenance addressed locally. Preferred-port exhaustion was tested against a real loopback dashboard. Corporate firewall/VPN/proxy reachability and a live hosted cold start still require deployment tests. Do not disable TLS or corporate security controls to make a test pass. |
| 2 Control state and database limits | Critical | Deployment, reconciliation and release authorization must reference the same run. Fake reconciliation is removed. Connection lifetime/concurrency are reduced. Supabase capacity across all workers/replicas still needs a load test. |
| 3 SQL translation and schema variance | Moderate | Unique metadata-bound spelling correction is implemented before artifact approval. Semantic equivalence, complex routines and the earlier domain-generation failures remain separate acceptance work. |
| 4 Catalog promotion and permissions | Moderate | Fresh prerequisite display, exact release confirmation and backend roles improve authorization. IAM grants, target quotas, deep-clone cost and rollback must be tested in the real workspace. |
| 5 Medallion and incremental resume | Green in the image | This rating is premature for the entire tier. The 31-of-42 deployment resume scenario now passes locally with mocked target execution. It does not close the earlier watermark/CDC/scheduler problems or certify live data accuracy. |

## Findings register

Status vocabulary: **Implemented and locally tested** means a source change has focused regression evidence. **Partial** means a meaningful change exists but the original finding is not fully closed. **Open** means additional implementation or external action remains. None of these labels substitutes for live production acceptance.

| ID | Issue | Candidate status and remaining work |
|---|---|---|
| F01 | Password reset and automatic ADMIN creation | Implemented and locally tested: expiring account-bound proof, atomic consumption, role preservation, session version revocation, secure OTP generation, bounded attempts and no delivery-failure code disclosure. Self-registration defaults off. Review previously created administrator accounts separately. |
| F02 | Cross-owner project access | Implemented and locally tested for owner-only projects. Central authorization enforces ownership and current account state. Team collaboration/membership sharing requires an explicit future model rather than silently granting access. |
| F03 | Roles, review identity and production permission | Implemented role/current-user checks and server-derived reviewer identity. Direct PROD calls now require the exact current UAT release ID and confirmation. Full role/action coverage and production authorization audit still need independent acceptance. |
| F04 | Anonymous schedules | Authentication/ownership now protect read, update and trigger routes. Schedule validation, read-side mutation and execution safety remain partial/open. |
| F05 | Forged quality gates | Client-created measured gates are rejected. Generic module records no longer substitute for typed gate/reconciliation evidence in automated promotion. Regression tests verify that a deployment without measured reconciliation stays blocked. |
| F06 | Secret distribution | Source release filtering improved; fixed administrator provisioning passwords removed. Previously distributed real credentials require owner-led revocation and account review; no external credential rotation was performed. |
| F07 | Watermark comparison, identity and delta correctness | Open; scheduled/manual incremental sync now defaults off. Typed/composite watermarking, approved unique keys, source-object scoping, timestamp ties, late changes and declared delete policy must be implemented/tested before enabling it. |
| F08 | Scheduler ownership and crash recovery | Open. Database leases, cross-worker deduplication, heartbeat/expiry and crash-safe ownership remain required. |
| F09 | Count-only reuse and APPEND skip | Count-only early success was removed. Dedicated APPEND/retry/content-equivalence acceptance remains required. |
| F10 | Engine datatype/transport disagreement | Partial: common binary, boolean, numeric and string aliases were added; binary round-trip normalization is tested. This does not establish complete engine-specific LOB/JSON/timezone/precision support. |
| F11 | Agent bulk binary encoding | Exact transport metadata is sent to the agent; binary values use hex in staged Parquet instead of Python byte representation. New agent rejects unversioned bulk metadata. Live COPY round trips and large-file acceptance remain required. |
| F12 | Missing source metadata | Open: FK/dependency/routine/view definition parity across engines and direct/agent paths. |
| F13 | Unreviewed runtime SQL repair | Runtime suggestions are recorded as REVIEW_REQUIRED; patched SQL is not executed or written over an approved version. Regeneration, validation and approval are required. |
| F14 | Weak content reconciliation | Open beyond the removal of fake evidence. Existing measured checks still primarily establish counts/existence, not full value or business equivalence. |
| F15 | Misleading status/progress | Partial: fake source minimum, fixed 42-object fallback, untested-connected label and status-based 50% project progress were removed. Full readiness/phase presentation requires browser acceptance. |
| F16 | 500-object inventory boundary | Open: server-side pagination, search and accurate totals still needed. |
| F17 | Deployment profile inconsistencies | Open: Compose routing, ODBC and persistence validation. Hosted liveness now targets `/healthz`. |
| F18 | Regression coverage and failing legacy tests | New focused regressions cover the repaired paths. Broad suite outcome is retained separately; this candidate is not represented as a clean production release. |
| F19 | Coupled encryption/signing key and session lifecycle | Partial: password resets revoke prior tokens and current lockout/role is enforced. Separate encryption keys and re-encryption/rotation tooling remain open. |
| F20 | Dependency advisories | Open: this candidate preserves the original runtime pins to avoid an untested dependency migration. The freshly built agent uses that same dependency set. Update and audit dependencies before production release. |
| F21 | Durable jobs and reliable cancellation | Open: durable leased workers, cooperative target-query cancellation and restart recovery. |
| F22 | Empty discovery retains stale objects | Open: authoritative/partial snapshot semantics and deletion policy require implementation. |
| F23 | Oracle identifier case | Direct Oracle quoting now preserves discovered case; live quoted-identifier extraction remains to be verified. |
| F24 | Singular/plural SQL identifiers | Implemented unique metadata-scoped compile-time binding and ambiguity tests. Do not infer unrelated key equivalence or rely on execution-time repair. |
| F25 | Partial deployment resume and NaN counts | Exact workspace/target/version/content/source/row-limit identity is recorded and checked for Medallion resume. A local failure at artifact 32 resumes with 31 skips and 11 executions. Numeric counters reject NaN/Infinity/negative values and use eligible checkpoints. Legacy checkpoints without enough identity evidence are intentionally not trusted automatically. The older non-Medallion deployment resume path still needs equivalent hardening; a metadata source hash does not establish unchanged source data. |
| F26 | DEV gate/promotion deadlock | Successful deployment invokes real reconciliation and gate evaluation. Missing, failed, fabricated or wrong-run evidence cannot pass. Each new reconciliation attempt has its own identity so repeated checks cannot mix detail rows. Historical pending artifact versions no longer block a reviewed current version. Actual Databricks/Supabase acceptance remains required. |
| F27 | Agent port collision | Source already had fallback. Range validation/configurable dashboard port and identifiable build were added. Loopback smoke test occupied every preferred port and verified an ephemeral dashboard. Fresh EXE version smoke passed; corporate endpoint execution remains unverified. |
| F28 | Cold-start retry thrashing | Capped jittered backoff, Retry-After handling, success reset, 90-second read/10-second connect timeout and suppressed heartbeat traffic during reconnect. `/healthz` has no per-request DB/provider dependency. Live host wakeup/health timings remain unverified. |
| F29 | Managed PostgreSQL client exhaustion | Existing pooler NullPool retained; active clients bounded, target credentials detached from worker DB sessions and SQL concurrency reduced to two for reconciliation/cloning. UI polling is single-flight by scope, skips hidden tabs and polls active jobs every ten seconds; idle remains quiet. Cross-process capacity and Supabase load acceptance remain open. |
| F30 | Promotion modal scope | Root mount already existed. Both entry points now call one opener that resets stale state, fetches current prerequisites and disables authorization until fresh eligibility arrives. Placeholder catalog/artifact claims removed. Frontend build/contracts pass; Stage 7/8 browser acceptance remains required. |

## What the local tests establish

The focused tests use synthetic accounts, isolated SQLite databases and mocked target services. They include account takeover rejection, one-use proof binding, old-token revocation, role enforcement, owner isolation, anonymous schedule rejection, fake-gate rejection, scoped SQL binding, no runtime repair execution, 31-of-42 resume, checkpoint mismatch rejection, actual NullPool budget mechanics, detached connection lifetime, binary transport and agent backoff/port policy.

The loopback port smoke uses actual local sockets without connecting to a source or launching a registered connector. The executable smoke runs `--version` only. Neither validates corporate firewall traversal, real source data extraction, cloud credentials, Databricks COPY/MERGE or a sleeping Render host.

## Update order

1. Review and merge the candidate's security and operational changes after the required test/upgrade review. Revoke any real leaked credentials and inspect existing administrator accounts.
2. Close F07/F08/F14 before calling incremental synchronization stable. Close F12 and the remaining transport matrix before advertising complete multi-engine migration parity.
3. Resolve broad regression failures, dependency advisories and installation profiles. Run the original live acceptance matrix plus the new 42-object, cold-start, port-collision and Supabase concurrency cases.
4. Release only with a measured manifest: source/build hashes, exact artifact versions, actual reconciliation results, current approvals, agent fingerprint and deployment configuration.

The candidate is reviewable code and test evidence. It has not been deployed to the colleague's environment and does not close every finding in the combined register.
