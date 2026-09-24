# Release 2 — SQL Server to DEV Bronze Ingestion

Release 2 connects the existing SQL Server discovery/connector path to the governed,
project-scoped Databricks DEV environment created in Release 1.

## Delivered scope

- Requires a tested project Databricks configuration and a `PROVISIONED` DEV plan.
- Loads discovered SQL Server `TABLE` objects into `<catalog>_dev.bronze`.
- Uses the registered outbound local connector when present; SQL credentials remain local.
- Supports `FULL_LOAD` and explicit `APPEND` modes.
- Uses staging Delta tables for full loads, so a failed transfer does not replace the current target.
- Requires explicit confirmation before replacing a populated Bronze table.
- Performs deterministic type normalization and post-load row-count validation.
- Records project/run/table-scoped audit evidence, failures, checkpoints and retry attempts.
- Retries a full-table load once only for transient Databricks errors. APPEND is not
  automatically retried because doing so could duplicate rows.

## Operator flow

1. Complete SQL Server discovery.
2. Provision the governed DEV environment in **Environment Setup**.
3. Run **Ingestion preflight**.
4. Select `FULL_LOAD` for a repeatable snapshot, or `APPEND` only when duplicate handling
   is governed outside this release.
5. Start DEV Bronze ingestion and review every table result.
6. Continue to Medallion generation only after all required Bronze tables pass.

## Safety boundary

- The loader uses only the project-scoped Databricks host, warehouse and token reference.
- It never falls back to another globally configured Databricks account.
- A source table name collision across SQL Server schemas blocks the run rather than
  silently overwriting a target.
- `FULL_LOAD` replacement is explicit; staging tables are cleaned after each attempt.
- Raw tokens and SQL passwords are never stored in ingestion evidence.

## Deferred scope

- Watermark/CDC-based incremental ingestion requires per-table key and watermark
  configuration and is intentionally not represented by `APPEND`.
- Natural-language prompt orchestration will call this governed API in Release 3; AI will
  not execute arbitrary SQL or bypass preflight/approval controls.
- TEST/UAT/PROD ingestion and promotion remain separate governed releases.
