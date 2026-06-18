-- Add canonical per-project storage metadata.
-- Buckets are project routing metadata, not secrets; credentials remain in Railway/env.

BEGIN;

ALTER TABLE projects
ADD COLUMN IF NOT EXISTS storage jsonb NOT NULL DEFAULT '{}'::jsonb;

UPDATE projects
SET storage = jsonb_build_object(
    'mode', COALESCE(metadata->>'storage_mode', 's3'),
    'bucket', metadata->>'bucket',
    'prefix', COALESCE(metadata->>'prefix', 'workspaces/' || workspace_id || '/projects/' || project_id)
)
WHERE storage = '{}'::jsonb
  AND metadata ? 'bucket';

UPDATE projects
SET storage = jsonb_build_object(
    'mode', 'local',
    'prefix', 'workspaces/' || workspace_id || '/projects/' || project_id
)
WHERE storage = '{}'::jsonb;

COMMIT;
