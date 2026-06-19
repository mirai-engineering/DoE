# Local training with remote MLflow

This workflow trains a Mirai DoE model locally from an **approved exported training package** while logging runs, metrics, artifacts, models, and ONNX exports to remote MLflow.

It is intentionally local-only after export:

```text
Railway UI → upload → preprocess → approve → export package
MacBook → local training → remote MLflow runs/artifacts/models
```

## What this workflow does not modify

This workflow **does not modify Railway production data**. It does not write to Railway Postgres, does not call back to the Mirai API, does not mutate Railway app object-storage prefixes, and does not use `.object-storage-local`.

The only remote system it writes to is the configured MLflow tracking/artifact backend.

## Where to place exported packages

Export the approved package from the Railway UI, unzip it locally, and place it under the repository root in a gitignored directory:

```text
training-runs/Mirai-DoE-Training-Package-Demo-FuelCell/
  model_table.csv
  schema.json
  training_manifest.json
```

The package directory is treated as immutable input. The trainer copies required files into a local run directory and never writes generated outputs back into the package directory.

Local generated outputs are written under:

```text
backend/.local-training-runs/
```

Both `training-runs/` and `backend/.local-training-runs/` are local-only and gitignored.

## Configure local remote-MLflow environment

Create a local env file from the template:

```bash
cp backend/.env.training.local.example backend/.env.training.local
```

Edit `backend/.env.training.local`:

```bash
MLFLOW_TRACKING_URI=https://<your-remote-mlflow-url>
MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true
MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=true
```

Do not add Railway Postgres credentials, Clerk secrets, Mirai API tokens, or direct app S3 credentials to this file.

If the remote MLflow experiment already has a remote artifact location configured, no artifact-root setting is needed. If MLflow must create a new experiment and requires an explicit artifact location, set only the non-application artifact root needed by your MLflow deployment, for example:

```bash
MLFLOW_ARTIFACT_ROOT=s3://<remote-mlflow-artifact-prefix>
```

## Exact training command

From the repository root:

```bash
cd backend
set -a
source .env.training.local
set +a
uv run python -m ml_lifecycle.training.run_exported_package \
  --package-dir ../training-runs/Mirai-DoE-Training-Package-Demo-FuelCell
```

For a modest smoke run, you may cap MLP epochs:

```bash
cd backend
set -a
source .env.training.local
set +a
uv run python -m ml_lifecycle.training.run_exported_package \
  --package-dir ../training-runs/Mirai-DoE-Training-Package-Demo-FuelCell \
  --max-epochs 10
```

The command also auto-loads `backend/.env.training.local` when present, but sourcing it makes the active configuration explicit in your shell.

## What gets logged to MLflow

The CLI delegates training to the existing generic tabular DoE trainer. Candidate runs use the existing model families and conventions:

- mean baseline;
- multivariate linear regression;
- Ridge candidates;
- MLP candidate;
- ONNX export for the MLP path when supported.

Every candidate run receives package/source tags where available:

```text
workspace_id
project_id
dataset_id
session_id
training_request_id
exported_at
source_checksum
training_source=approved_export_package
```

The run artifacts include the existing trainer outputs plus package provenance artifacts:

```text
schema.json
training_manifest.json
preprocessing.json
metrics_summary.json
metrics.json
metadata.json
predictions.csv
candidate_comparison.csv
model.onnx       # when selected/exported
onnx/*           # candidate ONNX artifacts when supported
sklearn_pipeline # logged model
```

## How to find the run in MLflow

1. Open the remote MLflow UI from `MLFLOW_TRACKING_URI`.
2. Select the experiment named after the package `project_id`.
3. Search or filter runs by tags, for example:
   - `training_source = approved_export_package`;
   - `training_request_id = <value from training_manifest.json>`;
   - `workspace_id = fraunhofer`.
4. The selected challenger is marked with:
   - `selected_candidate = true`;
   - `candidate_role = challenger`;
   - `lifecycle_role = challenger`.
5. The selected model is registered under the existing convention:

```text
doe_surrogate_<project_id>
```

and receives the `challenger` alias when model registration succeeds.

## Validation and safety checks

Before training starts, the CLI validates:

- `training_manifest.json`, `schema.json`, and `model_table.csv` exist;
- manifest/schema identifiers are internally consistent when schema metadata is present;
- required package identifiers are present;
- feature and target columns come from the manifest, with schema fallback only if needed;
- required columns exist in `model_table.csv`;
- data is non-empty;
- the approved preprocessing `split` column exists and has train rows;
- manifest checksum metadata matches `model_table.csv` / `schema.json` when available;
- `MLFLOW_TRACKING_URI` is configured and remote;
- remote MLflow is reachable;
- `MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true` and `MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=true` are enabled.

If these checks fail, the command exits before training. The remote-MLflow guards prevent silent fallback to local `backend/mlruns`.

## Common errors and fixes

### `MLFLOW_TRACKING_URI is required`

Set it in `backend/.env.training.local` or export it in your shell.

### `MLFLOW_TRACKING_URI must be remote, not local`

Do not use `file://`, `localhost`, or `127.0.0.1` for this workflow. Use the remote Railway MLflow URL.

### `Set MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true`

Enable the safety guard in `backend/.env.training.local` so the command cannot fall back to local MLflow.

### `Remote MLflow preflight failed`

The MLflow URL is unreachable or not accepting requests from your machine. Verify the URL, network/VPN, and any MLflow auth/proxy requirements.

### `model_table.csv is missing required split column`

The exported package is not the approved preprocessed package expected by this workflow. Re-export after preprocessing approval.

### `Checksum mismatch for model_table.csv` or `schema.json`

The package file changed after export or does not match the manifest. Re-download/re-export the approved package and avoid editing package files.

### `MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS is enabled, but the MLflow experiment artifact location is not s3://`

The remote MLflow experiment is configured with a local/non-remote artifact location. Configure the remote MLflow server/experiment with remote artifact storage, or set the appropriate remote `MLFLOW_ARTIFACT_ROOT` if experiment creation requires it.

## Tests

Run the focused local workflow tests:

```bash
cd backend
uv run pytest tests/test_local_exported_package_training.py -q
```

These tests do not require Railway Postgres, Clerk, Railway app S3 credentials, or real remote MLflow access.
