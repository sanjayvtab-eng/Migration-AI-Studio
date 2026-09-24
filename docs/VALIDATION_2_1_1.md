# Validation 2.1.1

- `python -m compileall -q backend/app scripts`: PASS
- `pytest -q`: PASS, 59 tests
- New regression tests cover binary connector text forms, rejection of arbitrary binary text, exact non-hex error classification, runtime deployment issue routing to COMPATIBILITY_ENGINE, and semantic deployment syntax routing to AI.
- Fresh frontend production build: NOT RUN in packaging sandbox because dependencies/node_modules are excluded and unavailable.
- Live SQL Server/Databricks/Ollama end-to-end: requires user's environment and is not claimed as executed here.
