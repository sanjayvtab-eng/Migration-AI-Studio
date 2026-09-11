# Semantic Medallion Framework 2.3.0

## Purpose

Build 2.3.0 replaces the one-source-object/one-layer planning limitation with an explicit multi-target graph. A SQL Server table can now create distinct Source, Bronze, Silver and approved Gold nodes without changing source code for each customer.

## True multi-stage generation

For every discovered SQL Server table the planner creates:

`SOURCE -> BRONZE Delta table -> SILVER reusable entity`

Gold nodes are added only when a business semantic definition is explicitly approved. This prevents the system from inventing KPIs, dimensions or facts.

SQL Server views are converted as Silver transformation nodes. Stored procedures and functions are modeled as logic assets and converted/routed independently from data nodes. SQL Server triggers remain architecture-review assets.

## Fact/dimension semantic inference

Inference evaluates evidence including:
- PK/FK metadata discovered from SQL Server
- incoming and outgoing relationship counts
- numeric/date/descriptive column mix
- table naming signals
- downstream reporting consumers
- approximate row-count metadata when source permissions allow it

Inference produces a recommendation and confidence score. It does not automatically authorize Gold generation. A user must approve the semantic definition or create an explicit definition.

## Downstream consumer analysis

The engine reverses discovered SQL dependencies to identify direct and transitive consumers, depth, consumer type and usage intent. External consumers that are not visible in SQL Server metadata (for example Power BI reports, applications or files) can be registered explicitly through the API/UI.

The application does not pretend that SQL Server metadata can reveal consumers that are not present in SQL Server.

## Explicit business semantics and Gold generation

Supported approved Gold semantic roles:
- FACT
- DIMENSION
- AGGREGATE
- KPI
- REPORTING

A FACT requires explicit grain and measures. A DIMENSION requires an explicit business key. Aggregate/KPI models require explicit measures. Column references are validated against discovered metadata before approval and again during artifact generation.

Generated Gold models read from Silver targets, never directly from the source database or Bronze when a Silver entity exists.

## Review and deployment governance

Every generated Medallion stage artifact is versioned and receives deterministic validation. DEV deployment is blocked unless every current stage artifact is executable, validation has PASSED and review status is APPROVED.

Deployment order is enforced as Bronze -> Silver -> Gold. Bronze loading reuses the deterministic compatibility framework. Target schema drift continues to use governed schema policy; destructive DEV replacement requires explicit approval.
