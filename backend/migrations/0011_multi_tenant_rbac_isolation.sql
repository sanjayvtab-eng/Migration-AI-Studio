-- Release 2.6.0: Multi-Tenant RBAC & Project Privacy Isolation
ALTER TABLE migration_project ADD COLUMN workspace_id VARCHAR(64);
ALTER TABLE migration_project ADD COLUMN visibility VARCHAR(32) NOT NULL DEFAULT 'PRIVATE';

CREATE INDEX IF NOT EXISTS ix_migration_project_workspace_id ON migration_project(workspace_id);

CREATE TABLE IF NOT EXISTS migration_project_member (
    id VARCHAR(64) PRIMARY KEY,
    project_id VARCHAR(64) NOT NULL,
    user_identifier VARCHAR(255) NOT NULL,
    project_role VARCHAR(32) NOT NULL DEFAULT 'VIEWER',
    granted_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_project_member UNIQUE (project_id, user_identifier)
);

CREATE INDEX IF NOT EXISTS ix_migration_project_member_project_id ON migration_project_member(project_id);
CREATE INDEX IF NOT EXISTS ix_migration_project_member_user_identifier ON migration_project_member(user_identifier);
