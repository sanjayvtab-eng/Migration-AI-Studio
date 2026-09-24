# Release 2.0.0 — Governed AI Repair Loop

## Added

- A project-scoped **AI Remediation Center** that scans non-executable artifacts, failed static validations, remediable issues, rejected reviews, and change requests.
- A deterministic-first batch repair workflow that creates a new artifact version, reruns static validation, and routes safe results to human review.
- Bounded AI correction attempts. Validation errors from an unsafe candidate are returned to the model for the next attempt, up to `LLM_MAX_ATTEMPTS`.
- Native local Ollama support with no API key requirement, plus OpenAI-compatible provider support.
- Rich AI context: source definition, current artifact, discovered columns, dependencies, project mappings, issue evidence, validation errors, and review comments.
- Stronger candidate guards for destructive SQL, source-system references, dynamic/external SQL, Markdown, placeholders, wrong target FQNs, and trigger auto-conversion.
- Provider readiness and remediation-run evidence in the web UI.

## Governance

- AI output is never approved or deployed automatically.
- Accepted candidates are immutable new artifact versions and invalidate prior-version approval by design.
- Trigger redesign, business-rule ambiguity, security, connectivity, reconciliation, and target-schema decisions remain explicitly governed.
- Every batch has a project-scoped run ID and per-object run-step evidence.

## Configuration

Use `LLM_PROVIDER=OLLAMA`, `LLM_BASE_URL=http://localhost:11434`, and a locally installed model for free local inference. Set `LLM_MAX_ATTEMPTS` from 1 to 5. Deterministic remediation continues to work when `LLM_ENABLED=false`.
