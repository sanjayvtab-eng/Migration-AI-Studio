# Migration AI Studio 2.5.0 Multi Source Connectivity

## Implemented scope

- Added a polymorphic source adapter contract and factory for SQL Server, PostgreSQL, MySQL or MariaDB, and Oracle Thin mode.
- Added engine-specific connection testing, catalog discovery, identifier quoting, full-load reads, row counts, and ordered high-watermark reads.
- Kept the normalized migration object and column model unchanged for downstream Stages 2 through 8.
- Added encrypted per-source passwords and engine-specific connection settings.
- Added an additive database migration plus automatic compatibility upgrade for existing SQLite installations.
- Added Stage 1 database engine tiles and dynamic SQL Server, PostgreSQL, MySQL, and Oracle form fields.
- Added the required Python drivers and updated the frontend production build.

## Main implementation files

- `backend/app/services/source_adapters.py`
- `backend/app/models/entities.py`
- `backend/app/api/routes.py`
- `backend/app/services/bronze_ingestion.py`
- `backend/app/services/watermark_service.py`
- `backend/app/services/deployment.py`
- `backend/migrations/0009_multi_source_connectivity.sql`
- `frontend/src/App.tsx`
- `frontend/src/SourceConnectorControl.tsx`
- `frontend/src/styles.css`

## Verification

- Python source compilation passed.
- Frontend TypeScript compilation and Vite production build passed.
- Multi-source adapter and contract tests passed.
- Existing Bronze ingestion regression tests passed.
- Combined verified result: 28 tests passed.

## Deployment notes

- Keep `JWT_SECRET` stable and strong because it protects saved source passwords.
- Apply `backend/migrations/0009_multi_source_connectivity.sql` when upgrading a non-SQLite deployment. SQLite is upgraded additively at startup.
- The outbound local connector remains SQL Server-only. PostgreSQL, MySQL, and Oracle use direct native drivers.
- Live database end-to-end tests still require reachable source databases and credentials for each engine.
