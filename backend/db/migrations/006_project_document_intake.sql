BEGIN;

CREATE TABLE IF NOT EXISTS document_intake_sessions (
    id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'draft',
    title text,
    user_instruction text,
    target_contract_id text NOT NULL DEFAULT 'fraunhofer2miraicontract-full',
    created_by text,
    updated_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS document_intake_files (
    id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    session_id text NOT NULL REFERENCES document_intake_sessions(id) ON DELETE CASCADE,
    filename text NOT NULL,
    content_type text,
    file_type text NOT NULL,
    object_uri text NOT NULL,
    sha256 text,
    size_bytes bigint,
    parse_status text NOT NULL DEFAULT 'uploaded',
    parse_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_extraction_runs (
    id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    session_id text NOT NULL REFERENCES document_intake_sessions(id) ON DELETE CASCADE,
    status text NOT NULL,
    provider text,
    model text,
    prompt_version text,
    contract_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    error text,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS document_table_drafts (
    id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    session_id text NOT NULL REFERENCES document_intake_sessions(id) ON DELETE CASCADE,
    extraction_run_id text REFERENCES document_extraction_runs(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'draft',
    table_kind text NOT NULL,
    schema_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    issues_text_object_uri text,
    source_refs_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_at timestamptz,
    approved_by text
);

CREATE TABLE IF NOT EXISTS document_intake_exports (
    id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    session_id text NOT NULL REFERENCES document_intake_sessions(id) ON DELETE CASCADE,
    draft_id text REFERENCES document_table_drafts(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'created',
    package_object_uri text,
    manifest_object_uri text,
    data_dictionary_object_uri text,
    model_table_object_uri text,
    fixed_source_tables_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS document_intake_sessions_workspace_project_idx
    ON document_intake_sessions(workspace_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS document_intake_files_session_idx
    ON document_intake_files(workspace_id, project_id, session_id);
CREATE INDEX IF NOT EXISTS document_extraction_runs_session_idx
    ON document_extraction_runs(workspace_id, project_id, session_id, started_at DESC);
CREATE INDEX IF NOT EXISTS document_table_drafts_session_idx
    ON document_table_drafts(workspace_id, project_id, session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS document_intake_exports_session_idx
    ON document_intake_exports(workspace_id, project_id, session_id, created_at DESC);

ALTER TABLE document_intake_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_intake_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_extraction_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_table_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_intake_exports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS document_intake_sessions_rls ON document_intake_sessions;
CREATE POLICY document_intake_sessions_rls ON document_intake_sessions
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS document_intake_files_rls ON document_intake_files;
CREATE POLICY document_intake_files_rls ON document_intake_files
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS document_extraction_runs_rls ON document_extraction_runs;
CREATE POLICY document_extraction_runs_rls ON document_extraction_runs
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS document_table_drafts_rls ON document_table_drafts;
CREATE POLICY document_table_drafts_rls ON document_table_drafts
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS document_intake_exports_rls ON document_intake_exports;
CREATE POLICY document_intake_exports_rls ON document_intake_exports
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

COMMIT;
