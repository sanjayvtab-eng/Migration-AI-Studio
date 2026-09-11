# Testing Guide

## Automated tests
From `backend`:

```text
python -m compileall app
pytest -q
```

Tests cover datatype mappings, rowversion, metadata/layer classification, procedure/function/trigger classification, artifact versioning, mapped references, target schema drift comparison, dependency ordering/cycles, project isolation, lifecycle evidence, authentication/account lockout and a simulated API workflow.

From `frontend`:

```text
npm install
npm run build
```

## Golden database
Run `python golden_db/generate_golden_database.py` to regenerate `GoldenMigrationDB.sql`. Execute that SQL in a non-production SQL Server test instance. It generates 200 tables, relationships, indexes, rowversion/XML/JSON string columns, 30 reporting views, 20+ procedures, 15 functions, 10 triggers and complex syntax examples.

## True E2E checklist
A live E2E test requires external systems and should capture evidence for: source connection, discovery, snapshot/drift, assessment/classification, mappings, Bronze deployment/load, Silver deployment, Gold serving objects, DEV reconciliation, artifact review/approval, TEST deployment and independent TEST reconciliation. Do not mark this passed from mocked tests.
