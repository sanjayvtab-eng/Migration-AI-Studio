# Release 1.7.0 — AI Remediation & Review Traceability

## AI-assisted remediation
- Deterministic remediation always executes before AI.
- Common SQL Server scalar-UDF `DECLARE -> SELECT assignment -> RETURN` patterns are collapsed into a Databricks SQL function candidate.
- When no deterministic remediation matches and `LLM_ENABLED=true`, an OpenAI-compatible Chat Completions endpoint may propose a structured candidate.
- Required structured evidence: object_id, issue_id, source_logic, conversion_strategy, generated_candidate, confidence, assumptions, risks and validation_plan.
- Every candidate is rechecked by deterministic safety validation.
- Accepting a candidate creates a new artifact version only. It does not approve or deploy it.
- Human approval remains mandatory and deployment prechecks continue to enforce current-version approval.
- Prompt/run evidence is written project-scoped to migration_prompt and migration_ai_run.

## Review history
- Review history now shows source object, artifact version, review type, status, reviewer and timestamp.
- Repeating the exact same approval for the same version/reviewer is idempotent and no longer creates duplicate history rows.

## Configuration
AI is optional. Deterministic migration remains available with `LLM_ENABLED=false`.

```env
LLM_ENABLED=false
LLM_PROVIDER=OPENAI_COMPATIBLE
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=60
```

Do not commit API keys into source control. AI output remains a proposal and must never bypass validation/review.
