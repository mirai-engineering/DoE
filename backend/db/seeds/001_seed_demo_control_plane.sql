-- Idempotent bootstrap/backfill for Railway Level 2 demo metadata.
-- Safe to run repeatedly. SQL stores metadata and durable artifact pointers only.

BEGIN;

INSERT INTO workspaces (workspace_id, display_name, status, storage)
VALUES
    (
        'fraunhofer',
        'Fraunhofer',
        'active',
        '{"mode":"s3","bucket":"mirai-fuel-cells-demo","bucket_env_prefix":"MIRAI_FRAUNHOFER_S3","prefix":"workspaces/fraunhofer"}'::jsonb
    ),
    (
        'battery-demo',
        'Battery Demo',
        'active',
        '{"mode":"s3","bucket":"mirai-batteries-demo","bucket_env_prefix":"MIRAI_BATTERY_DEMO_S3","prefix":"workspaces/battery-demo"}'::jsonb
    ),
    (
        'mirai-engineering',
        'Mirai Engineering',
        'active',
        '{"mode":"local","prefix":"workspaces/mirai-engineering"}'::jsonb
    )
ON CONFLICT (workspace_id) DO UPDATE
SET display_name = EXCLUDED.display_name,
    status = EXCLUDED.status,
    storage = EXCLUDED.storage,
    updated_at = now();

INSERT INTO projects (project_id, workspace_id, display_name, lifecycle_contract, schema_version, metadata)
VALUES
    (
        'pem_fuel_cell_real_cathode_degradation',
        'fraunhofer',
        'PEM Fuel Cell Cathode Degradation',
        'generic_tabular_doe',
        'railway-level-2',
        '{"source":"pem_adapter","raw_blobs_in_sql":false,"bucket":"mirai-fuel-cells-demo","prefix":"workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation"}'::jsonb
    ),
    (
        'battery_tabular_doe_demo',
        'battery-demo',
        'Battery Generic Tabular DoE Demo',
        'generic_tabular_doe',
        'railway-level-2',
        '{"source":"battery_dataset_open_question","raw_blobs_in_sql":false,"bucket":"mirai-batteries-demo","prefix":"workspaces/battery-demo/projects/battery_tabular_doe_demo"}'::jsonb
    )
ON CONFLICT (project_id) DO UPDATE
SET workspace_id = EXCLUDED.workspace_id,
    display_name = EXCLUDED.display_name,
    lifecycle_contract = EXCLUDED.lifecycle_contract,
    schema_version = EXCLUDED.schema_version,
    metadata = projects.metadata || EXCLUDED.metadata,
    updated_at = now();

INSERT INTO artifact_objects (workspace_id, project_id, artifact_kind, object_uri, sha256, metadata)
VALUES
    (
        'fraunhofer',
        'pem_fuel_cell_real_cathode_degradation',
        'dataset',
        'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/model_table.csv',
        NULL,
        '{"storage":"object","raw_blob_in_sql":false,"source":"pem_adapter"}'::jsonb
    ),
    (
        'fraunhofer',
        'pem_fuel_cell_real_cathode_degradation',
        'canonical_table',
        'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/canonical/model_table.parquet',
        NULL,
        '{"storage":"object","raw_blob_in_sql":false}'::jsonb
    ),
    (
        'fraunhofer',
        'pem_fuel_cell_real_cathode_degradation',
        'preprocessing_output',
        'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/preprocessing/latest/manifest.json',
        NULL,
        '{"storage":"object","raw_blob_in_sql":false}'::jsonb
    ),
    (
        'fraunhofer',
        'pem_fuel_cell_real_cathode_degradation',
        'mlflow_artifacts',
        'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/mlflow-artifacts/doe_surrogate_pem_fuel_cell_real_cathode_degradation',
        NULL,
        '{"pointer_only":true,"raw_blob_in_sql":false}'::jsonb
    ),
    (
        'fraunhofer',
        'pem_fuel_cell_real_cathode_degradation',
        'onnx_model',
        'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/onnx/model.onnx',
        NULL,
        '{"pointer_only":true,"raw_blob_in_sql":false}'::jsonb
    ),
    (
        'fraunhofer',
        'pem_fuel_cell_real_cathode_degradation',
        'bo_state',
        'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/bo/state.json',
        NULL,
        '{"pointer_only":true,"raw_blob_in_sql":false}'::jsonb
    ),
    (
        'fraunhofer',
        'pem_fuel_cell_real_cathode_degradation',
        'review_file',
        'workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/reviews/latest.json',
        NULL,
        '{"pointer_only":true,"raw_blob_in_sql":false}'::jsonb
    ),
    (
        'battery-demo',
        'battery_tabular_doe_demo',
        'dataset',
        'workspaces/battery-demo/projects/battery_tabular_doe_demo/intake/dataset.csv',
        NULL,
        '{"storage":"object","raw_blob_in_sql":false,"source":"open_question"}'::jsonb
    ),
    (
        'battery-demo',
        'battery_tabular_doe_demo',
        'canonical_table',
        'workspaces/battery-demo/projects/battery_tabular_doe_demo/canonical/model_table.parquet',
        NULL,
        '{"storage":"object","raw_blob_in_sql":false}'::jsonb
    ),
    (
        'battery-demo',
        'battery_tabular_doe_demo',
        'preprocessing_output',
        'workspaces/battery-demo/projects/battery_tabular_doe_demo/preprocessing/latest/manifest.json',
        NULL,
        '{"storage":"object","raw_blob_in_sql":false}'::jsonb
    ),
    (
        'battery-demo',
        'battery_tabular_doe_demo',
        'mlflow_artifacts',
        'workspaces/battery-demo/projects/battery_tabular_doe_demo/mlflow-artifacts/generic_tabular_doe_battery_demo',
        NULL,
        '{"pointer_only":true,"raw_blob_in_sql":false,"source":"deferred_until_dataset_confirmed"}'::jsonb
    ),
    (
        'battery-demo',
        'battery_tabular_doe_demo',
        'onnx_model',
        'workspaces/battery-demo/projects/battery_tabular_doe_demo/onnx/model.onnx',
        NULL,
        '{"pointer_only":true,"raw_blob_in_sql":false,"source":"deferred_until_dataset_confirmed"}'::jsonb
    ),
    (
        'battery-demo',
        'battery_tabular_doe_demo',
        'bo_state',
        'workspaces/battery-demo/projects/battery_tabular_doe_demo/bo/state.json',
        NULL,
        '{"pointer_only":true,"raw_blob_in_sql":false,"source":"deferred_until_dataset_confirmed"}'::jsonb
    ),
    (
        'battery-demo',
        'battery_tabular_doe_demo',
        'review_file',
        'workspaces/battery-demo/projects/battery_tabular_doe_demo/reviews/latest.json',
        NULL,
        '{"pointer_only":true,"raw_blob_in_sql":false,"source":"deferred_until_dataset_confirmed"}'::jsonb
    )
ON CONFLICT DO NOTHING;

COMMIT;
