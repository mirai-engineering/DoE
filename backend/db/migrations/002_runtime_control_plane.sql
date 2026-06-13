-- Runtime control-plane metadata for Railway Level 2 Postgres/S3/MLflow cutover.
-- Heavy artifacts stay in object storage; SQL stores state, ownership, and pointers.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    filename text NOT NULL,
    object_uri text NOT NULL,
    schema_hash text,
    manifest_version text,
    row_count integer CHECK (row_count IS NULL OR row_count >= 0),
    column_count integer CHECK (column_count IS NULL OR column_count >= 0),
    uploaded_by text,
    status text NOT NULL DEFAULT 'uploaded',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT datasets_workspace_prefix CHECK (
        object_uri LIKE ('workspaces/' || workspace_id || '/%')
        OR object_uri LIKE ('s3://%/' || workspace_id || '/%')
        OR object_uri LIKE ('s3://%/workspaces/' || workspace_id || '/%')
    )
);

CREATE TABLE IF NOT EXISTS schema_manifests (
    schema_id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    manifest_object_uri text NOT NULL,
    input_columns jsonb NOT NULL DEFAULT '[]'::jsonb,
    output_columns jsonb NOT NULL DEFAULT '[]'::jsonb,
    unit_map jsonb NOT NULL DEFAULT '{}'::jsonb,
    schema_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation_status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT schema_manifests_workspace_prefix CHECK (
        manifest_object_uri LIKE ('workspaces/' || workspace_id || '/%')
        OR manifest_object_uri LIKE ('s3://%/' || workspace_id || '/%')
        OR manifest_object_uri LIKE ('s3://%/workspaces/' || workspace_id || '/%')
    )
);

CREATE TABLE IF NOT EXISTS training_runs (
    training_run_id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    dataset_id text REFERENCES datasets(dataset_id) ON DELETE SET NULL,
    mlflow_run_id text,
    status text NOT NULL DEFAULT 'queued',
    started_at timestamptz,
    finished_at timestamptz,
    best_model_type text,
    metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    artifact_s3_prefix text,
    created_by text,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT training_runs_workspace_prefix CHECK (
        artifact_s3_prefix IS NULL
        OR artifact_s3_prefix LIKE ('workspaces/' || workspace_id || '/%')
        OR artifact_s3_prefix LIKE ('s3://%/' || workspace_id || '/%')
        OR artifact_s3_prefix LIKE ('s3://%/workspaces/' || workspace_id || '/%')
    )
);

CREATE TABLE IF NOT EXISTS models (
    model_id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    training_run_id text REFERENCES training_runs(training_run_id) ON DELETE SET NULL,
    model_name text NOT NULL,
    version text NOT NULL,
    status text NOT NULL DEFAULT 'candidate',
    artifact_s3_uri text NOT NULL,
    preprocessing_s3_uri text,
    schema_s3_uri text,
    is_champion boolean NOT NULL DEFAULT false,
    metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT models_workspace_prefix CHECK (
        artifact_s3_uri LIKE ('workspaces/' || workspace_id || '/%')
        OR artifact_s3_uri LIKE ('s3://%/' || workspace_id || '/%')
        OR artifact_s3_uri LIKE ('s3://%/workspaces/' || workspace_id || '/%')
    )
);

CREATE TABLE IF NOT EXISTS recommendations (
    candidate_id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    model_id text REFERENCES models(model_id) ON DELETE SET NULL,
    input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    predicted_outputs_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    score double precision,
    rank integer,
    status text NOT NULL DEFAULT 'suggested',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id text PRIMARY KEY,
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id text NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    candidate_id text REFERENCES recommendations(candidate_id) ON DELETE SET NULL,
    dataset_id text REFERENCES datasets(dataset_id) ON DELETE SET NULL,
    input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    observed_outputs_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    source text,
    created_at timestamptz NOT NULL DEFAULT now(),
    validated_by text
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id text NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    user_id text,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text,
    ip_address inet,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    timestamp timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_datasets_workspace_project ON datasets(workspace_id, project_id);
CREATE INDEX IF NOT EXISTS idx_datasets_project_status ON datasets(project_id, status);
CREATE INDEX IF NOT EXISTS idx_schema_manifests_workspace_project ON schema_manifests(workspace_id, project_id);
CREATE INDEX IF NOT EXISTS idx_training_runs_workspace_project ON training_runs(workspace_id, project_id);
CREATE INDEX IF NOT EXISTS idx_training_runs_project_status ON training_runs(project_id, status);
CREATE INDEX IF NOT EXISTS idx_models_workspace_project ON models(workspace_id, project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_models_one_champion ON models(workspace_id, project_id) WHERE is_champion;
CREATE INDEX IF NOT EXISTS idx_recommendations_workspace_project ON recommendations(workspace_id, project_id);
CREATE INDEX IF NOT EXISTS idx_observations_workspace_project ON observations(workspace_id, project_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_workspace_time ON audit_logs(workspace_id, timestamp DESC);

ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE models ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

ALTER TABLE datasets FORCE ROW LEVEL SECURITY;
ALTER TABLE schema_manifests FORCE ROW LEVEL SECURITY;
ALTER TABLE training_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE models FORCE ROW LEVEL SECURITY;
ALTER TABLE recommendations FORCE ROW LEVEL SECURITY;
ALTER TABLE observations FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS datasets_rls ON datasets;
CREATE POLICY datasets_rls ON datasets
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS schema_manifests_rls ON schema_manifests;
CREATE POLICY schema_manifests_rls ON schema_manifests
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS training_runs_rls ON training_runs;
CREATE POLICY training_runs_rls ON training_runs
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS models_rls ON models;
CREATE POLICY models_rls ON models
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS recommendations_rls ON recommendations;
CREATE POLICY recommendations_rls ON recommendations
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS observations_rls ON observations;
CREATE POLICY observations_rls ON observations
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

DROP POLICY IF EXISTS audit_logs_rls ON audit_logs;
CREATE POLICY audit_logs_rls ON audit_logs
    USING (workspace_id = current_setting('app.workspace_id', true))
    WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

COMMIT;
