BEGIN;

ALTER TABLE models
    DROP CONSTRAINT IF EXISTS models_workspace_prefix;

ALTER TABLE models
    ADD CONSTRAINT models_workspace_prefix CHECK (
        artifact_s3_uri LIKE ('workspaces/' || workspace_id || '/%')
        OR artifact_s3_uri LIKE ('s3://%/' || workspace_id || '/%')
        OR artifact_s3_uri LIKE ('s3://%/workspaces/' || workspace_id || '/%')
        OR artifact_s3_uri LIKE ('models:/doe_surrogate_' || project_id || '/%')
        OR artifact_s3_uri LIKE ('models:/doe_surrogate_' || project_id || '@%')
    );

COMMIT;
