# Release Notes - 2.3.0 Semantic Medallion Factory

## Added

- True Source -> Bronze -> Silver -> Gold target-node model.
- Separate Medallion node/edge persistence so one source object can produce multiple Databricks targets.
- SQL Server PK/FK and approximate table statistics discovery for semantic evidence.
- Deterministic fact/dimension inference with confidence and evidence.
- Direct/transitive downstream consumer analysis.
- Explicit registration of downstream consumers not visible in SQL Server metadata.
- Explicit business semantic definitions with approval before Gold generation.
- Automatic Gold FACT, DIMENSION, AGGREGATE, KPI and REPORTING model generation from approved semantics.
- Silver passthrough entities for source tables without fabricating transformations.
- Converted source views as Silver transformations.
- Stored procedures/functions represented as governed logic assets with Databricks implementation routing.
- Stage artifact versioning, validation, review and governed DEV deployment.
- Dedicated Medallion Design UI for consumer analysis, semantic inference, explicit semantics, plan generation, artifact review and DEV deployment.

## Safety behavior

- Inferred semantics do not automatically create Gold objects until approved.
- Unknown business logic is not invented.
- Triggers remain architecture-review items.
- Gold models consume Silver nodes.
- Stage deployment requires APPROVED + PASSED + executable artifacts.
- Destructive DEV replacement requires explicit approval.
- Ollama remains a semantic remediation fallback; it does not define business KPIs automatically.
