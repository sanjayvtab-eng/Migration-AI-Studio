# Release Notes — 2.1.0 OLLAMA_AI

## Added

- First-class `OLLAMA` provider for local AI remediation.
- Default local endpoint `http://127.0.0.1:11434` when Ollama is selected.
- Provider health/version probe and installed-model discovery.
- Configured-model availability check before semantic remediation.
- AI Remediation UI panel showing endpoint, model, reachability and installed-model status.
- **Test Ollama** and **Refresh models** UI actions.
- Authenticated `/api/ai/provider-test` and `/api/ai/models` endpoints.
- Windows helpers to configure, pull and test Ollama.
- Governed prompt-size/context/output settings.
- Local Ollama HTTP calls ignore ambient proxy variables to prevent localhost traffic from being routed via a corporate proxy.
- Explicit prompt-injection guidance treating source SQL/error content as untrusted data.

## Retained controls

- Deterministic rules always execute before AI fallback.
- AI candidates are JSON-structured and statically validated.
- AI cannot auto-approve or auto-deploy.
- AI cannot modify PROD.
- AI cannot bypass mapping/reference checks or reconciliation.
- Triggers remain architecture-review objects rather than blind AI conversions.
- Artifact-version approval remains mandatory after AI remediation.

## Compatibility

All 2.0.1 datatype/transport compatibility behavior is retained, including metadata-driven binary-family handling that prevents `ARRAY<VOID> → BINARY` load failures.

## Upgrade

Copy the existing root `.env` and `migration_factory.db` into the new extracted folder. Run `scripts\configure_ollama.py` or `scripts\setup_ollama_windows.bat`, restart the backend, then use **AI Remediation → Test Ollama**.
