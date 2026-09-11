# Hybrid V2 Gemini Semantic Inference

## What changed

- Existing deterministic V1 inference remains the first and fallback engine.
- Gemini is invoked only for semantic definitions left as `REVIEW_REQUIRED`.
- Requests contain discovered columns, PK/FK metadata, source definition and V1 evidence.
- Gemini must return JSON and may reference only discovered columns.
- Invalid, low-confidence (`< 0.75`) or incomplete results are discarded safely.
- Accepted candidates use `AI_RECOMMENDED`; they are never auto-approved or auto-deployed.
- Existing approved semantic definitions are never overwritten.

## Local configuration

Add these values to the root `.env`:

```text
LLM_ENABLED=true
LLM_PROVIDER=GEMINI
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta
LLM_API_KEY=<your-gemini-api-key>
LLM_MODEL=gemini-2.5-flash
```

Never commit or share the real API key. Restart the backend after changing `.env`.

## Test sequence

1. Administration -> Test AI Provider.
2. Confirm `provider=GEMINI`, `reachable=true`, `model_available=true`, and `ready=true`.
3. Medallion Design -> Analyze consumers.
4. Medallion Design -> Infer fact/dimension.
5. Inspect `AI_RECOMMENDED` rows and their confidence/evidence.
6. Approve only valid business semantics before Gold plan/artifact generation.

If Gemini is unavailable, misconfigured, or returns invalid content, the V1 result remains `REVIEW_REQUIRED` and the rest of the application continues safely.
