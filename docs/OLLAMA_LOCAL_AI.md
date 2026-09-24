# Local Ollama AI — Setup and Governance

## Purpose

Build 2.1.0 supports Ollama as the initial local AI provider for semantic migration remediation. Ollama is **fallback only**: deterministic conversion, metadata mapping, static validation, deployment governance, and reconciliation remain authoritative.

The AI flow is:

```text
Migration issue / non-executable artifact
        ↓
Deterministic remediation rules
        ↓
Matched? ── Yes → deterministic candidate → static validation
        │
        No
        ↓
Local Ollama candidate
        ↓
Structured-response validation
        ↓
Safety / reference / destructive-SQL guards
        ↓
New DEV artifact version
        ↓
Human review / approval
        ↓
DEV deployment + reconciliation
```

Ollama output never approves itself, never deploys itself, never modifies PROD, and never overrides failed deterministic reconciliation.

## Windows setup

### Option A — automated helper

Install Ollama for Windows first. Then, from the Migration Factory project root:

```bat
scripts\setup_ollama_windows.bat qwen2.5-coder:3b
```

The helper:

1. Verifies `ollama` is on `PATH`.
2. Verifies/starts the local Ollama service.
3. Pulls the requested model.
4. Backs up the existing `.env`.
5. Enables the Ollama provider in `.env`.
6. Verifies the Ollama model list.

You can provide a different installed Ollama model name as the first argument.

### Option B — configure an existing model only

```bat
backend\.venv\Scripts\python.exe scripts\configure_ollama.py --model qwen2.5-coder:3b
```

The script creates a timestamped `.env.backup_YYYYMMDD_HHMMSS` before making changes.

### Option C — configure manually

```text
LLM_ENABLED=true
LLM_PROVIDER=OLLAMA
LLM_BASE_URL=http://127.0.0.1:11434
LLM_API_KEY=
LLM_MODEL=qwen2.5-coder:3b
LLM_TIMEOUT_SECONDS=120
LLM_MAX_ATTEMPTS=3
LLM_NUM_CTX=8192
LLM_NUM_PREDICT=4096
LLM_MAX_PROMPT_CHARS=160000
OLLAMA_KEEP_ALIVE=5m
```

Restart the backend after changing `.env`; application settings are intentionally loaded at process startup.

## Validate the provider

You can validate Ollama outside the application:

```bat
scripts\test_ollama_windows.bat
```

Or inside the application:

1. Open **AI Remediation**.
2. Click **Test Ollama**.
3. Confirm:
   - Provider = `OLLAMA`
   - Reachable = `READY`
   - Model installed = `YES`
4. **Refresh models** lists models returned by the local `/api/tags` endpoint.

The backend also exposes governed authenticated endpoints:

- `GET /api/ai/provider-status`
- `POST /api/ai/provider-test`
- `GET /api/ai/models`

The provider test does **not** send source SQL or migration metadata. It only checks provider health/model availability.

## How AI remediation is invoked

The factory builds a project-scoped prompt containing only the relevant object definition, mappings, dependency metadata, validation state, and open remediation issue. The prompt requires one JSON object with:

- `object_id`
- `issue_id`
- `source_logic`
- `conversion_strategy`
- `generated_candidate`
- `confidence`
- `assumptions`
- `risks`
- `validation_plan`

The generated SQL candidate is rejected when it:

- contains destructive SQL such as `DROP`, `TRUNCATE`, or `DELETE`
- changes catalog/schema security context
- retains unmapped SQL Server references
- invents unsupported external/dynamic SQL behavior
- fails required target-FQN validation
- contains Markdown instead of executable SQL
- attempts trigger auto-conversion

## Prompt-injection resistance

Source SQL, issue text, and metadata are treated as untrusted data. The system prompt explicitly prevents source content from overriding migration governance. Deterministic candidate validation remains authoritative after every Ollama response.

## Local privacy boundary

With `LLM_PROVIDER=OLLAMA` and `LLM_BASE_URL=http://127.0.0.1:11434`, the application sends AI remediation requests to the local Ollama service. The Ollama HTTP client disables ambient proxy inheritance so localhost traffic is not unintentionally routed through a corporate proxy.

This does not change SQL Server/Databricks networking; only the AI-provider call uses this local behavior.

## Model sizing

The package defaults to `qwen2.5-coder:3b` as a practical local coding model. If the machine is resource constrained, configure another installed Ollama model. The migration factory does not couple its logic to a particular model name.

Larger/stronger models can improve complex semantic conversion, but every candidate is still governed by the same deterministic controls.

## Failure behavior

If Ollama is stopped, the model is missing, the request times out, or the provider returns invalid JSON:

- the migration run fails safely for that AI-only candidate
- no artifact is approved or deployed
- the error is returned to the remediation UI
- deterministic migration functionality remains available

## Production position

Local Ollama is intended as the first provider for development/private deployment. Future enterprise providers can use the existing OpenAI-compatible abstraction. Provider changes must not alter approval, validation, promotion, or production governance.
