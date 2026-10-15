-- Migration 0009: Polymorphic relational source connectivity.
-- Existing rows remain SQL Server sources.
ALTER TABLE migration_source ADD COLUMN engine VARCHAR(32) NOT NULL DEFAULT 'SQLSERVER';
ALTER TABLE migration_source ADD COLUMN port INTEGER;
ALTER TABLE migration_source ADD COLUMN schema_name VARCHAR(255);
ALTER TABLE migration_source ADD COLUMN username VARCHAR(255);
ALTER TABLE migration_source ADD COLUMN credential_ciphertext TEXT;
ALTER TABLE migration_source ADD COLUMN options_json TEXT NOT NULL DEFAULT '{}';
