# Release 2.1.1 - Runtime Remediation

This patch closes the gap between deployment/runtime failures and the governed remediation center. Deployment issues now expose their underlying classified category to remediation planning. Deterministic load/transport errors use the compatibility engine; semantic SQL failures can use Ollama after deterministic rules.

## Binary transport hardening
SQL Server `binary`, `varbinary`, `image`, `timestamp`, and `rowversion` are projected as explicit VARBINARY-to-hex text and reconstructed with Databricks `unhex(?)`. The normalizer supports bounded connector representations and rejects arbitrary text.

## Governance
Runtime repairs never auto-approve or auto-deploy. `RETRY_READY` means the compatibility rule is available and the operator can use **Resume Failed Run** after reviewing evidence.

## Operational fixes
The normal Windows backend launcher no longer uses Uvicorn reload mode, Ollama configuration deduplicates managed `.env` keys, and Test Ollama status persists in the UI.
