# Local Training with Remote MLflow

Use this flow when training an exported Mirai package locally/on-prem while logging runs, artifacts, and registered models to the remote Railway MLflow service.

## 1. Configure local-only environment

Create or update:

```bash
backend/.env.training.local
```

Required values:

```bash
MLFLOW_TRACKING_URI=https://<remote-mlflow-domain>
MLFLOW_TRACKING_USERNAME=<mlflow-basic-auth-user>
MLFLOW_TRACKING_PASSWORD=<mlflow-basic-auth-password>
MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true
MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=true
```

Notes:

- `backend/.env.training.local` is local-only and must stay gitignored.
- Do not add local S3 credentials for normal exported-package training.
- Remote MLflow should serve artifacts through `mlflow-artifacts:/...`.
- Use `direnv`; do not manually `source` this file.

Load/check env:

```bash
direnv allow
```

## 2. Run exported-package training

From the repo root, preferred with `direnv exec`:

```bash
direnv exec . bash -lc 'cd backend && uv run python -m ml_lifecycle.training.run_exported_package ../../training-runs/Mirai-DoE-Training-Package-Demo-FuelCell'
```

Equivalent raw command once the direnv environment is already loaded:

```bash
cd backend && uv run python -m ml_lifecycle.training.run_exported_package ../../training-runs/Mirai-DoE-Training-Package-Demo-FuelCell
```

Replace the package path with the exported training package you want to train.

## 3. Expected result

Training should:

- fail closed if `MLFLOW_TRACKING_URI` is empty or local;
- log run artifacts to remote MLflow;
- export/register the selected model as ONNX for serving;
- register a model named like:

```text
doe_surrogate_<project_id>
```

- attach project identity metadata/tags so the app can safely resolve the model for the matching workspace/project.

After training, promote the intended model version to MLflow alias `champion`, then in Mirai use the app-dev **Load champion model** step. This single action verifies artifacts and identity, loads the ONNX champion, backfills runtime schema state when needed, and unlocks Model Quality/Design Studio serving.

## 4. Verify locally

Example:

```bash
direnv exec . bash -lc 'cd backend && uv run python - <<"PY"
from app.services.project_registry import clear_registry_cache, get_project_schema
from app.services.model_quality import get_predictions

project_id = "demo_ccm_degradation_cff1d4ae"
clear_registry_cache()
schema = get_project_schema(project_id)
print([item["name"] for item in schema["inputs"]])
print([item["name"] for item in schema["outputs"]])
print(get_predictions(project_id, limit=1)["total_row_count"])
PY'
```

You should see the project schema and a non-zero prediction row count if quality artifacts were logged.
