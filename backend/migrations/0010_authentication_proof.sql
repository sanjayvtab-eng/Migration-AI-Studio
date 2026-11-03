-- Apply once when upgrading an existing database without application startup upgrades.
-- Back up the control database first. Restart all API instances after migration.
ALTER TABLE migration_user ADD COLUMN otp_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE migration_user ADD COLUMN password_proof_hash VARCHAR(64);
ALTER TABLE migration_user ADD COLUMN password_proof_expires_at TIMESTAMP;
ALTER TABLE migration_user ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0;
