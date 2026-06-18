-- Workspace-scoped control plane for Railway Level 2 pilot isolation.
-- Raw datasets/model blobs stay in object/file storage; SQL stores metadata and pointers only.

BEGIN;

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id text PRIMARY KEY,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    storage jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clerk_user_workspaces (
    clerk_user_id text NOT NULL,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    role text NOT NULL DEFAULT 'member',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (clerk_user_id, workspace_id)
);

CREATE TABLE IF NOT EXISTS projects (
    project_id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
    display_name text NOT NULL,
    lifecycle_contract text NOT NULL DEFAULT 'generic_tabular_doe',
    schema_version text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    storage jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS artifact_objects (
    artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text REFERENCES projects(project_id) ON DELETE CASCADE,
    artifact_kind text NOT NULL,
    object_uri text NOT NULL,
    sha256 text,
    size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT artifact_objects_workspace_prefix CHECK (
        object_uri LIKE ('workspaces/' || workspace_id || '/%')
        OR object_uri LIKE ('s3://%/' || workspace_id || '/%')
        OR object_uri LIKE ('s3://%/workspaces/' || workspace_id || '/%')
    )
);

CREATE INDEX IF NOT EXISTS idx_projects_workspace_id ON projects(workspace_id);
CREATE INDEX IF NOT EXISTS idx_artifact_objects_workspace_project ON artifact_objects(workspace_id, project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifact_objects_unique_pointer ON artifact_objects(workspace_id, project_id, artifact_kind, object_uri);
CREATE INDEX IF NOT EXISTS idx_clerk_user_workspaces_workspace ON clerk_user_workspaces(workspace_id);

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE clerk_user_workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_objects ENABLE ROW LEVEL SECURITY;

ALTER TABLE workspaces FORCE ROW LEVEL SECURITY;
ALTER TABLE clerk_user_workspaces FORCE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
ALTER TABLE artifact_objects FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS workspace_rls ON workspaces;
CREATE POLICY workspace_rls ON workspaces
    USING (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS clerk_user_workspaces_rls ON clerk_user_workspaces;
CREATE POLICY clerk_user_workspaces_rls ON clerk_user_workspaces
    USING (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS projects_rls ON projects;
CREATE POLICY projects_rls ON projects
    USING (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS artifact_objects_rls ON artifact_objects;
CREATE POLICY artifact_objects_rls ON artifact_objects
    USING (workspace_id = current_setting('app.workspace_id', true));

COMMIT;
