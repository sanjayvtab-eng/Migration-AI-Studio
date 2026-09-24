-- Migration 0008 Rollback: Dynamic clarifications and destructive operation governance
-- Preserves all existing constraints and indexes.

DROP TABLE IF EXISTS migration_destructive_approval;

CREATE TABLE migration_prompt_clarification_backup (
  id VARCHAR(64) PRIMARY KEY,
  project_id VARCHAR(64) NOT NULL,
  spec_version_id VARCHAR(64) NOT NULL,
  question_key VARCHAR(128) NOT NULL,
  question TEXT NOT NULL,
  affected_request_ids_json TEXT NOT NULL,
  choices_json TEXT NOT NULL,
  answer_json TEXT,
  status VARCHAR(32) NOT NULL,
  asked_at TIMESTAMP NOT NULL,
  answered_at TIMESTAMP,
  answered_by VARCHAR(255),
  CONSTRAINT uq_prompt_question_version UNIQUE(spec_version_id, question_key)
);

INSERT INTO migration_prompt_clarification_backup (
  id, project_id, spec_version_id, question_key, question,
  affected_request_ids_json, choices_json, answer_json, status,
  asked_at, answered_at, answered_by
)
SELECT 
  id, project_id, spec_version_id, question_key, question,
  affected_request_ids_json, choices_json, answer_json, status,
  asked_at, answered_at, answered_by
FROM migration_prompt_clarification;

DROP TABLE migration_prompt_clarification;

CREATE TABLE migration_prompt_clarification (
  id VARCHAR(64) PRIMARY KEY,
  project_id VARCHAR(64) NOT NULL,
  spec_version_id VARCHAR(64) NOT NULL,
  question_key VARCHAR(128) NOT NULL,
  question TEXT NOT NULL,
  affected_request_ids_json TEXT NOT NULL,
  choices_json TEXT NOT NULL,
  answer_json TEXT,
  status VARCHAR(32) NOT NULL,
  asked_at TIMESTAMP NOT NULL,
  answered_at TIMESTAMP,
  answered_by VARCHAR(255),
  CONSTRAINT uq_prompt_question_version UNIQUE(spec_version_id, question_key)
);

INSERT INTO migration_prompt_clarification (
  id, project_id, spec_version_id, question_key, question,
  affected_request_ids_json, choices_json, answer_json, status,
  asked_at, answered_at, answered_by
)
SELECT 
  id, project_id, spec_version_id, question_key, question,
  affected_request_ids_json, choices_json, answer_json, status,
  asked_at, answered_at, answered_by
FROM migration_prompt_clarification_backup;

DROP TABLE migration_prompt_clarification_backup;

CREATE INDEX IF NOT EXISTS ix_prompt_clarification_version ON migration_prompt_clarification(spec_version_id);
