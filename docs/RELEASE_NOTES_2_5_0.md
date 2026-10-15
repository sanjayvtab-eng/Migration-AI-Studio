# Migration AI Studio 2.5.0 Multi Source Connectivity

## Delivered

- Added `BaseDatabaseAdapter` and an adapter factory for SQL Server, PostgreSQL, MySQL/MariaDB, and Oracle Thin mode.
- Added engine-specific connection tests, catalog discovery, identifier quoting, paged full extraction, row counts, and ordered high-watermark extraction.
- Preserved the existing canonical discovery snapshot consumed by inventory, classification, mapping, medallion generation, review, deployment, and scheduled sync.
- Added encrypted per-source credentials and additive source configuration fields with a compatibility upgrade for existing SQLite installations.
- Added the Stage 1 engine selector and dynamic fields for ports, schemas, authentication, SSL, charset, Oracle Service Name/SID, and Oracle connection mode.
- Added PostgreSQL, MySQL, Oracle, and cryptography runtime dependencies.
- Added cross-engine adapter, datatype, persistence, and UI contract tests.

## Compatibility

Existing source records default to `SQLSERVER`. The local outbound connector remains SQL Server-only; PostgreSQL, MySQL, and Oracle use their native direct drivers. Stages 2–8 continue to consume the same normalized metadata entities.

## Upgrade

For an existing database, apply `backend/migrations/0009_multi_source_connectivity.sql`. SQLite installations are also upgraded additively during application startup. Set a stable, strong `JWT_SECRET` before saving source passwords; changing it later prevents previously stored credentials from being decrypted.
