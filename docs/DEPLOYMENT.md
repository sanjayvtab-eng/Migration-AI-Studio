# Deployment and Configuration

## Environment separation
Use separate Databricks catalogs for DEV/TEST/UAT/PROD and keep the control catalog/schema separate. Do not embed environment names in generated business SQL; resolve them through mapping/configuration.

## Secrets
For local development use `.env`, excluded from source control. For production inject credentials through a platform secret manager. Production startup rejects the documented default JWT secret. Tokens/passwords/API keys must never be placed in source files, generated SQL or release archives.

## Docker
Copy `.env.example` to `.env`, populate values locally and run `docker compose up --build`. For enterprise deployment, replace local SQLite with a managed relational control-plane database and mount no secrets into the image layer.

## Database evolution
For production, introduce Alembic migrations before changing canonical schema. Historical artifact versions, reviews, reconciliation and audit evidence should be append-only.
