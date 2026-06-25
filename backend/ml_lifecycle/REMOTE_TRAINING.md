# Remote/local training runbook

Use this runbook when training an approved Mirai package outside the app container while logging to remote MLflow.

## Railway/object-storage variables

Configure variables by name only; do not commit values:

- `MLFLOW_TRACKING_URI`
- `OBJECT_STORAGE_BACKEND`
- `MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW`
- `MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS`
- `MIRAI_REQUIRE_S3_OBJECT_STORAGE`
- `MIRAI_<WORKSPACE>_S3_BUCKET`
- `MIRAI_<WORKSPACE>_S3_ENDPOINT`
- `MIRAI_<WORKSPACE>_S3_ACCESS_KEY_ID`
- `MIRAI_<WORKSPACE>_S3_SECRET_ACCESS_KEY`
- `MIRAI_<WORKSPACE>_S3_REGION`
- generic S3 fallbacks, when intentionally shared: `OBJECT_STORAGE_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`

## Local `backend/.env.training.local`

Create this local-only file with the same remote MLflow/S3 settings:

```dotenv
MLFLOW_TRACKING_URI=https://<remote-mlflow-host>
MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true
MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=true
OBJECT_STORAGE_BACKEND=s3
# plus the workspace S3 variables listed above
```

## UI export-package workflow

1. Upload and preprocess the project dataset in Mirai.
2. Approve Metadata & Plot Setup.
3. Approve preprocessing for training.
4. Create a training request.
5. Download the approved training package from the UI export-package action.
6. Unzip it locally and inspect `training_manifest.json` for identity fields.

## Local training command

Run from `backend/` and pass explicit attribution flags. These must match `training_manifest.json` or the CLI fails before training.

```bash
cd backend
uv run python -m ml_lifecycle.training.run_exported_package \
  --package-dir /path/to/unzipped/exported-package \
  --workspace-id fraunhofer \
  --project-id ccm_degradation_029a2f61 \
  --dataset-id <dataset_id> \
  --session-id <session_id> \
  --training-request-id <training_request_id>
```

The CLI prints the remote tracking URI, MLflow experiment `<project_id>`, registered model `doe_surrogate_<project_id>`, run identity, expected alias `challenger`, and next manual steps.

## MLflow promotion and Mirai activation

1. In MLflow, open experiment `<project_id>`.
2. Review candidate runs and the selected challenger.
3. Open registered model `doe_surrogate_<project_id>`.
4. Confirm the selected version has alias `challenger` and the correct tags/manifest.
5. Manually assign alias `champion` to the approved version.
6. In Mirai, click **Load champion model** for the same workspace/project.

Mirai verifies the champion alias, source run identity, required artifacts, `training_manifest.json`, and ONNX serving artifact before Model Quality/Design Studio use it.

## Troubleshooting: “Model quality is not available yet”

Check these in order:

- Was **Load champion model** run after the MLflow alias was promoted?
- Does registered model `doe_surrogate_<project_id>` have alias `champion`?
- Does the champion source run have tags `workspace_id`, `project_id`, `dataset_id`, `session_id`, and `training_request_id` matching the Mirai project?
- Does the run contain `schema.json`, `preprocessing.json`, `metadata.json`, `metrics_summary.json`, `candidate_comparison.csv`, `predictions.csv`, and `training_manifest.json`?
- Does the registered model version contain the ONNX artifact logged from `onnx_model`?
- If object storage is involved, confirm project keys under `canonical/latest/`, `preprocessing/latest/`, `eda/latest/`, `training_packages/<training_request_id>/`, and `training_artifacts/latest/`.
