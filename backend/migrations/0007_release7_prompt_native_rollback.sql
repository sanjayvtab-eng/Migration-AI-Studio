-- Release 7 rollback. Back up audit evidence before executing.
DROP TABLE IF EXISTS migration_requirement_artifact_trace;
DROP TABLE IF EXISTS migration_prompt_plan_approval;
DROP TABLE IF EXISTS migration_prompt_clarification;
DROP TABLE IF EXISTS migration_prompt_artifact_request;
DROP TABLE IF EXISTS migration_prompt_specification_version;
DROP TABLE IF EXISTS migration_prompt_specification;
DROP TABLE IF EXISTS migration_metadata_snapshot;
