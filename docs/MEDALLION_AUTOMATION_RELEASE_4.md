# Release 4 — Automated Medallion Generation and Governed Remediation

## Outcome

Release 4 turns the Bronze output produced by the prompt migration workflow into deterministic Silver and governed Gold artifacts. Generated SQL is validated before review, ordered by recorded lineage, and cannot be deployed until a person approves the current immutable version.

## Silver policy

- Column names are standardized to `snake_case` with collision detection.
- String values are trimmed and empty strings are normalized to null.
- SQL Server timestamp values are converted to UTC using `SOURCE_TIMESTAMP_TIMEZONE` (default: `UTC`). The operator must set this value when the source stores local wall-clock time.
- Tables with a discovered primary key use `ROW_NUMBER` to retain the latest ingested record for each key.
- Transformations are generated only from discovered metadata; business rules are not inferred in Silver.

## Gold policy

- Gold artifacts are generated only from approved FACT, DIMENSION, AGGREGATE, KPI, or REPORTING semantics.
- Dimension surrogate keys are deterministic SHA-256 values derived from approved business keys.
- Fact grain, dimension keys, measures, and aggregation functions come from the approved semantic definition.
- Unknown columns, unsafe expressions, and incomplete semantic structures block generation.

## Static validation and dependency order

Before a stage version becomes reviewable, Release 4 checks its planned target, SQL delimiters, SQL Server bracket leakage, destructive operations, and duplicate aliases. Recorded Medallion edges are topologically sorted; dependency cycles block the generation run before any new artifact is accepted.

Use:

- `GET /api/projects/{id}/medallion/validation-report`
- `GET /api/projects/{id}/medallion/artifacts/{version_id}`

The artifact detail response contains the current SQL, a unified diff against the previous immutable version, validation evidence, review state, and upstream/downstream lineage.

## Governed AI remediation

- Deterministic repair runs first.
- Gemini receives object-scoped SQL, discovered columns, the relevant error, and required mappings—never source data or credentials.
- An idempotency fingerprint prevents a duplicate provider request for the same unaccepted, validated candidate.
- HTTP 429 responses enter a provider/model cooldown; transient 5xx responses use bounded backoff.
- A successful repair creates version `v+1` in `PENDING_REVIEW`.
- AI never approves or deploys a candidate. Deployment requires deterministic validation and human approval of every current version.

## Operator sequence

1. Complete Release 3 discovery and Bronze ingestion.
2. Infer or explicitly define semantics.
3. Human-approve eligible Gold semantics.
4. Build the Medallion plan and generate artifacts.
5. Confirm the Release 4 validation report is `PASSED`.
6. Inspect lineage and SQL diffs; remediate failed artifacts when eligible.
7. Human-approve current artifact versions.
8. Deploy the governed set to DEV and reconcile source-to-target results.

## Prompt workflow hardening

The prompt migration workflow now enforces the same Release 4 controls instead of
reporting a run as completed when a downstream stage was skipped or failed.

- A plan cannot be approved when discovery contains zero SQL Server tables.
- A latest successful Bronze run is reused only when its complete source-table set
  exactly matches the newly generated plan.
- Prompt-triggered full loads pass the Bronze service's governed
  `replace_existing_data` approval correctly.
- `PARTIAL` Bronze results, empty Medallion output, unresolved static validation,
  deployment failures, and reconciliation failures stop the run.
- Failed executions record the exact stage, sanitized error, and operator action;
  the Migration Workflow UI displays all three.
- A prompt plan is persisted as `EXECUTING`, `COMPLETED`, or `FAILED`, preserving
  the final checkpoint as audit evidence.
