-- Fraunhofer-only runtime seed/backfill for Railway Postgres/S3 cutover.
-- Battery is intentionally omitted from the runtime query path for this phase.

BEGIN;

INSERT INTO workspaces (workspace_id, display_name, status, storage)
VALUES (
    'fraunhofer',
    'Fraunhofer',
    'active',
    '{"mode":"s3","bucket":"mirai-fuel-cells-demo","bucket_env_prefix":"MIRAI_FRAUNHOFER_S3","prefix":"workspaces/fraunhofer"}'::jsonb
)
ON CONFLICT (workspace_id) DO UPDATE
SET display_name = EXCLUDED.display_name,
    status = EXCLUDED.status,
    storage = EXCLUDED.storage,
    updated_at = now();

INSERT INTO projects (project_id, workspace_id, display_name, lifecycle_contract, schema_version, metadata)
VALUES (
    'pem_fuel_cell_real_cathode_degradation',
    'fraunhofer',
    'PEM Fuel Cell Cathode Degradation',
    'generic_tabular_doe',
    'railway-runtime-v1',
    '{"source":"pem_adapter","domain":"pem_fuel_cell","raw_blobs_in_sql":false,"bucket":"mirai-fuel-cells-demo","prefix":"workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation"}'::jsonb
)
ON CONFLICT (project_id) DO UPDATE
SET workspace_id = EXCLUDED.workspace_id,
    display_name = EXCLUDED.display_name,
    lifecycle_contract = EXCLUDED.lifecycle_contract,
    schema_version = EXCLUDED.schema_version,
    metadata = projects.metadata || EXCLUDED.metadata,
    updated_at = now();

INSERT INTO datasets (
    dataset_id,
    workspace_id,
    project_id,
    filename,
    object_uri,
    schema_hash,
    manifest_version,
    row_count,
    column_count,
    uploaded_by,
    status,
    metadata
)
VALUES (
    'ds_fraunhofer_fuel_cell_seed_v1',
    'fraunhofer',
    'pem_fuel_cell_real_cathode_degradation',
    'model_table.csv',
    'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/model_table.csv',
    NULL,
    'seed-v1',
    NULL,
    NULL,
    'seed',
    'validated',
    '{"source":"seeded_uploaded_s3_artifact","companion_files":["cell_metadata.csv","ast_trace_manifest.csv"],"raw_blob_in_sql":false}'::jsonb
)
ON CONFLICT (dataset_id) DO UPDATE
SET object_uri = EXCLUDED.object_uri,
    status = EXCLUDED.status,
    metadata = EXCLUDED.metadata,
    updated_at = now();

INSERT INTO schema_manifests (
    schema_id,
    workspace_id,
    project_id,
    manifest_object_uri,
    input_columns,
    output_columns,
    unit_map,
    schema_json,
    validation_status
)
VALUES (
    'schema_fraunhofer_fuel_cell_seed_v1',
    'fraunhofer',
    'pem_fuel_cell_real_cathode_degradation',
    'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/schema.json',
    '["pt_c_ratio","i_c_ratio","ionomer_ew","operating_rh","operating_voltage","ast_rh","ast_upl"]'::jsonb,
    '["bol_current_density","eol_current_density","bol_ecsa","ecsa_loss"]'::jsonb,
    '{"operating_rh":"%","operating_voltage":"V","ast_rh":"%","ast_upl":"V"}'::jsonb,
    '{"project_id":"pem_fuel_cell_real_cathode_degradation","source":"seeded_training_artifacts_latest"}'::jsonb,
    'validated'
)
ON CONFLICT (schema_id) DO UPDATE
SET manifest_object_uri = EXCLUDED.manifest_object_uri,
    input_columns = EXCLUDED.input_columns,
    output_columns = EXCLUDED.output_columns,
    unit_map = EXCLUDED.unit_map,
    schema_json = EXCLUDED.schema_json,
    validation_status = EXCLUDED.validation_status,
    updated_at = now();

INSERT INTO training_runs (
    training_run_id,
    workspace_id,
    project_id,
    dataset_id,
    mlflow_run_id,
    status,
    started_at,
    finished_at,
    best_model_type,
    metrics_json,
    artifact_s3_prefix,
    created_by
)
VALUES (
    'run_fraunhofer_fuel_cell_seed_latest',
    'fraunhofer',
    'pem_fuel_cell_real_cathode_degradation',
    'ds_fraunhofer_fuel_cell_seed_v1',
    NULL,
    'completed',
    now(),
    now(),
    'seeded_current_model',
    '{"source":"seeded_existing_training_artifacts"}'::jsonb,
    'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/',
    'seed'
)
ON CONFLICT (training_run_id) DO UPDATE
SET status = EXCLUDED.status,
    finished_at = EXCLUDED.finished_at,
    best_model_type = EXCLUDED.best_model_type,
    metrics_json = EXCLUDED.metrics_json,
    artifact_s3_prefix = EXCLUDED.artifact_s3_prefix,
    updated_at = now();

UPDATE models
SET is_champion = false,
    status = CASE WHEN status = 'champion' THEN 'archived' ELSE status END,
    updated_at = now()
WHERE workspace_id = 'fraunhofer'
  AND project_id = 'pem_fuel_cell_real_cathode_degradation'
  AND model_id <> 'mdl_fraunhofer_fuel_cell_seed_champion';

INSERT INTO models (
    model_id,
    workspace_id,
    project_id,
    training_run_id,
    model_name,
    version,
    status,
    artifact_s3_uri,
    preprocessing_s3_uri,
    schema_s3_uri,
    is_champion,
    metrics_json
)
VALUES (
    'mdl_fraunhofer_fuel_cell_seed_champion',
    'fraunhofer',
    'pem_fuel_cell_real_cathode_degradation',
    'run_fraunhofer_fuel_cell_seed_latest',
    'doe_surrogate_pem_fuel_cell_real_cathode_degradation',
    'seed-latest',
    'champion',
    'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/model.onnx',
    'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/preprocessing.json',
    'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/schema.json',
    true,
    '{"source":"seeded_existing_training_artifacts"}'::jsonb
)
ON CONFLICT (model_id) DO UPDATE
SET training_run_id = EXCLUDED.training_run_id,
    model_name = EXCLUDED.model_name,
    version = EXCLUDED.version,
    status = EXCLUDED.status,
    artifact_s3_uri = EXCLUDED.artifact_s3_uri,
    preprocessing_s3_uri = EXCLUDED.preprocessing_s3_uri,
    schema_s3_uri = EXCLUDED.schema_s3_uri,
    is_champion = EXCLUDED.is_champion,
    metrics_json = EXCLUDED.metrics_json,
    updated_at = now();

INSERT INTO artifact_objects (workspace_id, project_id, artifact_kind, object_uri, sha256, metadata)
VALUES
    ('fraunhofer','pem_fuel_cell_real_cathode_degradation','dataset','workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/model_table.csv',NULL,'{"source":"seed_runtime_control_plane"}'::jsonb),
    ('fraunhofer','pem_fuel_cell_real_cathode_degradation','dataset_companion','workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/cell_metadata.csv',NULL,'{"source":"seed_runtime_control_plane"}'::jsonb),
    ('fraunhofer','pem_fuel_cell_real_cathode_degradation','dataset_companion','workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/ast_trace_manifest.csv',NULL,'{"source":"seed_runtime_control_plane"}'::jsonb),
    ('fraunhofer','pem_fuel_cell_real_cathode_degradation','schema_manifest','workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/schema.json',NULL,'{"source":"seed_runtime_control_plane"}'::jsonb),
    ('fraunhofer','pem_fuel_cell_real_cathode_degradation','preprocessing_output','workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/preprocessing.json',NULL,'{"source":"seed_runtime_control_plane"}'::jsonb),
    ('fraunhofer','pem_fuel_cell_real_cathode_degradation','onnx_model','workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/model.onnx',NULL,'{"source":"seed_runtime_control_plane","current":"champion"}'::jsonb),
    ('fraunhofer','pem_fuel_cell_real_cathode_degradation','mlflow_artifacts','workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/mlflow-artifacts/',NULL,'{"pointer_only":true,"source":"seed_runtime_control_plane"}'::jsonb)
ON CONFLICT DO NOTHING;

INSERT INTO audit_logs (workspace_id, user_id, action, resource_type, resource_id, metadata)
VALUES (
    'fraunhofer',
    'seed',
    'runtime_seed_applied',
    'project',
    'pem_fuel_cell_real_cathode_degradation',
    '{"seed":"002_seed_fraunhofer_fuel_cell_runtime.sql"}'::jsonb
);

COMMIT;
