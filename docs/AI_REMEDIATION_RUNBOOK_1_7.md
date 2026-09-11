# AI Remediation Runbook

> Updated for build 2.1.0. Local Ollama is the recommended first AI provider; the original single-object workflow remains available.

## Project-wide repair loop

1. Open **AI Remediation**.
2. Choose **Scan review blockers** to build a project-scoped plan.
3. Confirm which items are eligible for deterministic-then-AI repair and which require architectural review.
4. Choose **Run safe repair loop**.
5. The application attempts deterministic remediation first, uses configured AI only as fallback, rejects unsafe candidates, and retries with validation feedback within the configured bound.
6. Each safe candidate is stored as a new version and statically validated.
7. Review results in **Reviews** and explicitly approve the intended version.
8. Continue with DEV precheck, deployment, reconciliation, and the DEV quality gate.

AI never approves or deploys its own output. A repair run is successful when a candidate is ready for review; migration success still requires deployment and reconciliation evidence.

## Single-object workflow

1. Generate artifacts using deterministic converters.
2. If an artifact is marked `REMEDIATION_REQUIRED`, open **Artifacts** and choose **AI-assisted remediation**.
3. The factory first attempts a deterministic remediation pattern.
4. If no deterministic pattern matches and AI is configured/enabled, the provider is called with project/object/mapping/issue context.
5. Review the proposed candidate, confidence, assumptions, risks and validation plan.
6. Only candidates that pass deterministic safety validation can be accepted.
7. **Accept as new version** creates a new artifact version. It is not approved and is not deployed.
8. Go to **Reviews**, inspect the new version and explicitly approve it.
9. Run **DEV Precheck** again.
10. Only after precheck is eligible should **Deploy Approved to DEV** be used.
11. After deployment, run reconciliation and the DEV quality gate.

Safety: AI cannot auto-approve, auto-deploy PROD, override reconciliation, or invent business rules.


## Local Ollama

For build 2.1.0 setup, provider testing, installed-model discovery and local privacy controls, see `OLLAMA_LOCAL_AI.md`.
