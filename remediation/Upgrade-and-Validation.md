# Remediation candidate upgrade and validation

Candidate identifier: **2.5.0-remediation.1**. Preserve the existing application and control database before testing this candidate. Use a non-production source and target first.

## Package contents

- The source candidate contains code changes, the consolidated 30-finding register, reproduction notes and regression tests. It excludes original credentials and old binaries.
- The freshly built Windows agent distribution is delivered separately. Its `agent-build-manifest.json` contains SHA256 fingerprints for both agent source and executable. `migration-agent.exe --version` must report `2.5.0-remediation.1`.
- No source database or deployed cloud application was modified during remediation.

## Upgrade behavior that needs review

1. Back up the control database. New authentication fields are added on application startup; `backend/migrations/0010_authentication_proof.sql` is the equivalent apply-once migration for controlled database upgrades. Use either the application upgrade or the migration once, not both blindly. Test upgrades against a restored copy.
2. Preserve the existing encryption key until connection secrets have been re-encrypted through a separate rotation plan. It is coupled to `JWT_SECRET` in the original implementation. Do not simply change it and expect stored credentials to decrypt.
3. Self-registration defaults off. The former preset-password `create_admin.py` now uses interactive `bootstrap_admin.py`. Existing administrators need an account/role audit because the old registration path could create administrators. Authentication now checks current account state and role; invented tokens for nonexistent users will fail.
4. The password endpoint now requires the one-use verification token returned by a successful OTP exchange and a password of at least 12 characters. Frontend and backend must be upgraded together. Existing account roles are preserved. A completed password change invalidates the account's earlier sessions.
5. The generic quality-gates POST can no longer manufacture measured results. Use the actual reconciliation/evaluate-gate workflow. Legacy generic module rows are not release evidence.
6. A completed deployment is distinct from verification. Inspect the returned verification result and current gate. If a genuine check fails, fix the cause and run reconciliation; do not manually insert PASSED records.
7. Resume uses explicit execution identity. Old records missing workspace/source/row-limit evidence can require a controlled revalidation/reload. Do not assume every historic "31 passed" record is reusable.
8. Deploy the new backend and agent together for bulk staging. Older bulk payloads without exact transport metadata are rejected. Do not use the previous archive's EXE with the new application and assume the source fixes are present.
9. To serve the new executable from Studio's download endpoint, place the new EXE and manifest in the deployment's `backend/app/bin` before building the combined image, or distribute the signed/approved agent bundle separately. Never replace the agent with an unrelated old file.
10. `DATABASE_MAX_CONNECTIONS` defaults to 4 per process for NullPool deployments. Multiply by workers/replicas and account for administrative/background clients when setting the managed database budget. NullPool alone is not admission control. Do not rewrite transaction/session pooler endpoints without checking the provider's documented mode and connection allowance.
11. Scheduled and manual incremental sync default to disabled, including existing enabled schedules on startup. `INCREMENTAL_SYNC_ENABLED` is an experimental opt-in for controlled testing until F07/F08 acceptance is complete. Do not enable it in production on the strength of the Medallion resume test; artifact resume and watermark replication are different workflows.

## Validation commands

From `backend`, using the Python environment containing the declared requirements:

```text
python -m pytest tests/test_remediation_regressions.py tests/test_review_governance.py -q
python -m pytest tests/test_sql_preflight.py tests/test_multi_source_connectivity.py -q
```

For a safe local broad suite, add `remediation` to PYTHONPATH and load the opt-in `no_live_services` plugin. It rejects accidental external calls while leaving FastAPI TestClient requests in-process. Keep this result separate from live integration testing.

From `frontend`:

```text
npm ci
npm run build
npm test
node --experimental-strip-types tests/remediation-contract.mjs
```

The last command uses Node's TypeScript stripping support; the candidate was tested on Node 24.18.0. Browser acceptance is still required for the global modal, both stage entry points, hidden-tab polling and rapid project switching.

Agent source/build checks:

```text
python remediation/verify_agent_ports.py
python scripts/build_agent_exe.py
dist/migration-agent.exe --version
```

The port test briefly occupies the agent's preferred loopback ports and releases them on exit. Run it on a test workstation. Building requires PyInstaller plus the connector/runtime dependencies; the build now stops on failure rather than packaging an older executable. Apply the organization's executable signing and endpoint approval process before corporate distribution.

## Live acceptance still needed

- Repeat the colleague's 42-object migration, failing at object 32. Verify exact skipped IDs, executed SQL versions and target results, not only the count label.
- Run a real DEV reconciliation and verify that authorization becomes ready only when checks for that same manifest pass. Introduce a count mismatch and confirm promotion remains blocked.
- Test the new agent on the affected corporate workstation, with an occupied dashboard port, required proxy/CA configuration and a controlled host cold start. Do not disable TLS verification or bypass corporate security controls.
- Load-test Supabase with the intended worker/replica/viewer count. Measure active clients, connection hold times, p95 API latency, warehouse queries and recovery from EMAXCONNSESSION responses.
- Compare binary values across direct/streamed/bulk paths and test 4999/5000/5001 rows. Preserve exact expected values independently.
- Resolve the open items in the combined register before production signoff. Source fixes, successful compilation and a version-only EXE smoke do not establish a safe complete production migration.
