-- Migration 0008: Dynamic clarifications and destructive operation governance
-- All changes are additive and backward-compatible.

ALTER TABLE migration_prompt_clarification ADD COLUMN recommended_answer VARCHAR(255);
ALTER TABLE migration_prompt_clarification ADD COLUMN inference_reason TEXT;

CREATE TABLE IF NOT EXISTS migration_destructive_approval (
  id VARCHAR(64) PRIMARY KEY,
  project_id VARCHAR(64) NOT NULL,
  artifact_id VARCHAR(64) NOT NULL,
  artifact_version INTEGER NOT NULL,
  sql_content_hash VARCHAR(64) NOT NULL,
  environment VARCHAR(16) NOT NULL,
  run_id VARCHAR(64) NOT NULL,
  actor VARCHAR(255) NOT NULL,
  reason TEXT NOT NULL,
  confirmed_token VARCHAR(64) NOT NULL,
  destructive_operations_json TEXT NOT NULL,
  is_valid BOOLEAN NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_destructive_approval_project ON migration_destructive_approval(project_id, artifact_id);
CREATE INDEX IF NOT EXISTS ix_destructive_approval_hash ON migration_destructive_approval(artifact_id, sql_content_hash, environment);
