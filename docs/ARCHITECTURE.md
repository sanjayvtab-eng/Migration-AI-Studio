# Architecture

## Control flow
SQL Server → Connection Validation → Discovery → Canonical Metadata → Dependency Graph → Assessment → Layer Classification → Target Mapping → Conversion Plan → Versioned Artifact → Static Validation → Human/AI Remediation → Review/Approval → DEV → TEST → UAT → PROD → Cutover → Hypercare → Decommission Governance.

## Canonical metadata
Dedicated tables exist for high-traffic entities such as project, source, object, column, dependency, classification, mapping, artifacts/versions, reviews, issues, runs, quality gates and schema drift. Remaining required canonical entities are represented as explicitly named project-scoped evidence tables with immutable JSON payloads so the schema can evolve without destroying historical evidence.

Every project-controlled record carries `project_id`; environment evidence also carries `environment`. The API never falls back to the latest or first project.

## Medallion model
Classification is deterministic and signal based. Tables are normally Bronze candidates but can be overridden. Reusable transformations are Silver candidates. Aggregation, reporting, dimensional and semantic signals can produce Gold recommendations. A recommendation is not a business definition: KPI/fact/dimension generation must remain review-required when source semantics do not provide enough evidence.

## Conversion safety
Datatype mappings are deterministic. SQL Server `timestamp`/`rowversion` map to `BINARY`, never Databricks `TIMESTAMP`. Object references are replaced only when a known mapping exists; the implementation avoids unrestricted global string substitution. Static alias/column checks create blocker issues before deployment.

## Promotion model
Promotion uses artifact versions and project-specific quality gates. DEV, TEST, UAT and PROD evidence are independent. Source drift should be rechecked before a deploy operation. Destructive target operations are policy driven and PROD requires explicit approval.

## AI boundary
`LLM_ENABLED=false` is the default. AI is intended only for semantic ambiguity or complex remediation; AI output must be treated as a candidate and sent through validation, DEV execution/reconciliation and human approval. It must not deploy to PROD or approve itself.
