# Candidate validation results

Candidate **2.5.0-remediation.1** — 3 November 2026.

**Decision: engineering review and controlled non-production acceptance; production signoff remains on hold.** Priority security and operational changes are implemented. This is not a claim that all 30 findings are closed.

## Measured results

| Check | Result | Evidence |
|---|---|---|
| Complete isolated backend run | **410 passed, 4 failed**, 414 tests, 784.39 seconds | `final-regression.log` / `.xml` |
| Final focused security, governance and Medallion resume run | **33 passed**, 82.89 seconds | `final-focused.log` / `.xml` |
| Final reconciliation correction, deployment and connection-lifetime run | **21 passed**, 50.09 seconds | `final-reconciliation.log` / `.xml` |
| Frontend TypeScript and production build | Passed; 655.34 kB JS, 177.88 kB gzip; large-chunk warning remains | `frontend-build-final.log` and final command verification |
| Frontend contracts | Original seven-check contract and remediation contracts passed | Source checks; browser behavior remains separate |
| Agent port collision | Actual loopback dashboard succeeded on an OS-assigned port with all preferred ports occupied | `agent-port-smoke.log` |
| Fresh Windows EXE | Build succeeded; `--version` reports `2.5.0-remediation.1` | `agent-build.log`, `agent-exe-version.log`, build manifest |
| Source/EXE provenance | SHA256 values verified against the manifest; bundle includes matching source and EXE | `agent-build-manifest.json` |
| Python compilation and whitespace check | Passed | `compileall` and `git diff --check` |

The complete run was started before the final reconciliation-attempt correction. One of its four failures exposed a real defect: repeated reconciliation of the same deployment mixed older and newer detail rows (24 returned where the current attempt had 12). The candidate now stamps and filters an independent reconciliation identity. The previously failing test and 20 related tests passed in the final targeted run. The full suite was **not** rerun after this correction; do not relabel its result as 411 passed / 3 failed.

The final focused run also includes the default-disabled incremental-sync check and the stricter Medallion checkpoint identity guard. A later collection inventory found 415 tests, including the newly added disabled-sync test; it is a collection count, not another full test result.

## Three broader failures still unresolved

1. `test_hotel_operations_domain_grounding_and_function_generation`: a function's inferred source references contain `Bookings` but omit required `Rooms`. This is incomplete dependency/business grounding.
2. `test_domain_1_employee_payroll_full_lifecycle`: the lifecycle returns `DEV_DEPLOYMENT_FAILED` where the test requires `DEV_GATE_PASSED`. The full failure cause and generator/runtime contract need further diagnosis; it is not certified as a successful payroll migration.
3. `test_domain_4_educational_university_full_lifecycle`: generated GPA logic references `vw_students_clean` instead of the expected `vw_enrollments_clean`. This can change business meaning even when SQL appears syntactically plausible.

These failures were also present during the earlier source assessment. Their assertions have been preserved. They remain release blockers for the corresponding advertised scenarios; the candidate does not silently guess replacement business logic.

## Meaning and limits of the evidence

The backend checks used disposable SQLite databases, synthetic accounts and mocked cloud/source services. The opt-in `no_live_services` plugin blocked accidental synchronous external HTTP/database connections. No supplied real credentials were exercised. No email was sent, and no colleague deployment or source/target database was modified.

The 31-of-42 test establishes application checkpoint selection and execution counts against mocked targets. It does not prove unchanged source data, persisted target accuracy, restart durability or watermark replication correctness. The fresh executable was only run with `--version`; the actual local dashboard socket test used Python agent source without registering a connector.

Frontend contracts inspect source and numeric handling; they do not replace browser acceptance of both promotion entry points, project switching and hidden-tab polling. The supplied source already had a root-mounted modal and dynamic dashboard fallback, so the original live observations may involve a different packaged/deployed build. That mismatch remains a hypothesis until fingerprints and deployed logs are compared.

Live Databricks/Supabase/source-engine integration, corporate network/proxy behavior, sleeping-host recovery, connection-capacity load tests, catalog permissions and value/business reconciliation remain required. Incremental sync stays disabled by default while F07/F08 remain open. Dependency advisories and other open register items are not resolved by these test results.

Earlier exploratory logs such as `full-regression.log`, `targeted-integration.log` and initial focused failures are working history, not final passing evidence. The evidence bundle deliberately selects the final named runs above, including the complete run's failures.
