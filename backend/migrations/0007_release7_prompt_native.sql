-- Release 7 prompt-native design schema.
-- Apply after backing up the control database. All changes are additive.

CREATE TABLE IF NOT EXISTS migration_metadata_snapshot (
  id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL,
  source_id VARCHAR(64) NOT NULL, content_hash VARCHAR(64) NOT NULL,
  payload_json TEXT NOT NULL, created_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_metadata_snapshot_project ON migration_metadata_snapshot(project_id);

CREATE TABLE IF NOT EXISTS migration_prompt_specification (
  id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL,
  source_id VARCHAR(64) NOT NULL, target_environment VARCHAR(16) NOT NULL,
  current_status VARCHAR(48) NOT NULL, current_version_id VARCHAR(64),
  created_by VARCHAR(255) NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_prompt_spec_project ON migration_prompt_specification(project_id);

CREATE TABLE IF NOT EXISTS migration_prompt_specification_version (
  id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL,
  specification_id VARCHAR(64) NOT NULL, version INTEGER NOT NULL,
  original_prompt TEXT NOT NULL, parsed_json TEXT NOT NULL,
  metadata_snapshot_id VARCHAR(64) NOT NULL, parser_provider VARCHAR(64) NOT NULL,
  parser_model VARCHAR(128), checksum VARCHAR(64) NOT NULL,
  created_by VARCHAR(255) NOT NULL, created_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_prompt_specification_version UNIQUE(specification_id, version)
);

CREATE TABLE IF NOT EXISTS migration_prompt_artifact_request (
  id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL,
  spec_version_id VARCHAR(64) NOT NULL, request_id VARCHAR(96) NOT NULL,
  name VARCHAR(255) NOT NULL, artifact_type VARCHAR(48) NOT NULL,
  layer VARCHAR(16) NOT NULL, structured_json TEXT NOT NULL,
  grounding_status VARCHAR(32) NOT NULL, source_refs_json TEXT NOT NULL,
  dependencies_json TEXT NOT NULL, identifier_mappings_json TEXT NOT NULL,
  assumptions_json TEXT NOT NULL, created_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_prompt_request_version UNIQUE(spec_version_id, request_id)
);

CREATE TABLE IF NOT EXISTS migration_prompt_clarification (
  id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL,
  spec_version_id VARCHAR(64) NOT NULL, question_key VARCHAR(128) NOT NULL,
  question TEXT NOT NULL, affected_request_ids_json TEXT NOT NULL,
  choices_json TEXT NOT NULL, answer_json TEXT, status VARCHAR(32) NOT NULL,
  asked_at TIMESTAMP NOT NULL, answered_at TIMESTAMP, answered_by VARCHAR(255),
  CONSTRAINT uq_prompt_question_version UNIQUE(spec_version_id, question_key)
);

CREATE TABLE IF NOT EXISTS migration_prompt_plan_approval (
  id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL,
  spec_version_id VARCHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
  reviewer VARCHAR(255) NOT NULL, comment TEXT, reviewed_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS migration_requirement_artifact_trace (
  id VARCHAR(64) PRIMARY KEY, project_id VARCHAR(64) NOT NULL,
  specification_id VARCHAR(64) NOT NULL, spec_version_id VARCHAR(64) NOT NULL,
  request_id VARCHAR(96) NOT NULL, node_id VARCHAR(64), artifact_id VARCHAR(64),
  artifact_version_id VARCHAR(64), evidence_json TEXT NOT NULL, created_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_requirement_trace_version UNIQUE(spec_version_id, request_id)
);

CREATE INDEX IF NOT EXISTS ix_prompt_version_spec ON migration_prompt_specification_version(specification_id);
CREATE INDEX IF NOT EXISTS ix_prompt_request_version ON migration_prompt_artifact_request(spec_version_id);
CREATE INDEX IF NOT EXISTS ix_prompt_clarification_version ON migration_prompt_clarification(spec_version_id);
CREATE INDEX IF NOT EXISTS ix_prompt_approval_version ON migration_prompt_plan_approval(spec_version_id);
CREATE INDEX IF NOT EXISTS ix_requirement_trace_spec ON migration_requirement_artifact_trace(specification_id, spec_version_id);
