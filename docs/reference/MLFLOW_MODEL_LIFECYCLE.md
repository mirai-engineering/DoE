# MLflow Model Lifecycle

This document is the product/reference view of Mirai's current MLflow workflow. The implementation-level companion is:

```text
backend/ml_lifecycle/MLFLOW_README.md
```

Both documents follow the same policy:

```text
one candidate model = one MLflow run
only the selected best candidate is registered
challenger is set automatically
champion is manual only
baseline is optional/manual
```

## Current MVP scope

Mirai currently uses a local MLflow file store for development and MVP workflows:

```text
backend/mlruns/
```

This path is local-only runtime state and should not be treated as the long-term deployment architecture. Future Docker/production deployments should use an MLflow tracking server with a database backend and object-store artifacts.

The active MLflow-backed project families are:

```text
pem_fuel_cell_real_cathode_degradation
fraunhofer_demo_39e89ec9 or other uploaded generic_tabular_doe projects
```

## MLflow concepts in Mirai

| MLflow concept | Mirai meaning | Example |
|---|---|---|
| Experiment | Project-level training workspace containing all model attempts | `fraunhofer_demo_39e89ec9` |
| Run | One candidate model training attempt | `ridge_alpha_10.0`, `mvlr`, `mlp` |
| Logged model artifact | Deployable payload inside a run, named by flavor/type | `sklearn_pipeline`, `onnx` |
| Registered Model | Stable deployable surrogate family for a project | `doe_surrogate_fraunhofer_demo_39e89ec9` |
| Model Version | One selected registered artifact from one run | Version 1 from selected ridge run |
| Alias | Mutable governance/serving role pointer | `challenger`, `champion`, `baseline` |

The registered model is a project-level surrogate family. It should not include algorithm names, run names, or lifecycle roles.

## Naming conventions

Experiment name:

```text
<project_id>
```

Registered model name:

```text
doe_surrogate_<project_id>
```

Examples:

```text
Experiment:        fraunhofer_demo_39e89ec9
Registered Model:  doe_surrogate_fraunhofer_demo_39e89ec9

Experiment:        pem_fuel_cell_real_cathode_degradation
Registered Model:  doe_surrogate_pem_fuel_cell_real_cathode_degradation
```

Logged model artifact names are flavor/type names because the model identity already lives in run metadata:

```text
sklearn_pipeline   # generic_tabular_doe sklearn/joblib candidates
onnx               # PEM fuel-cell ONNX candidates
```

Do not use ambiguous logged model names like `model`. Do not duplicate algorithm details in the artifact name, e.g. avoid `ridge_alpha_10.0_sklearn_pipeline`; the run already has `tags.model_name=ridge_alpha_10.0`.

## Training and registry policy

Automatic training behavior:

1. Train all configured candidate models.
2. Log **every candidate** as an MLflow experiment run.
3. Compare validation metrics.
4. Select the best candidate using `validation_weighted_normalized_rmse`.
5. Register **only the selected best candidate** as a new Model Registry version.
6. Set the `challenger` alias on that selected version.
7. Never set or overwrite `champion` automatically.
8. Leave `baseline` manual/optional.

Manual governance behavior:

1. Open MLflow UI.
2. Compare candidate runs inside the experiment.
3. Inspect the registered `challenger` version.
4. If approved, manually assign/move `champion` to that version.
5. Optionally assign `baseline` to a stable reference version.

## Generic Mirai Contract / `generic_tabular_doe` flow

Generic uploaded projects use:

```text
backend/ml_lifecycle/training/generic_tabular_doe/train.py
```

Default generic candidates:

```text
mean_baseline
mvlr
ridge_alpha_0.01
ridge_alpha_0.1
ridge_alpha_1.0
ridge_alpha_10.0
mlp
```

Expected default MLflow result:

```text
7 MLflow experiment runs
1 new registered model version
1 challenger alias pointing at selected best version
0 automatic champion changes
```

For the current working Fraunhofer demo:

```text
Experiment: fraunhofer_demo_39e89ec9
Registered Model: doe_surrogate_fraunhofer_demo_39e89ec9
Logged model artifact inside each run: sklearn_pipeline
```

Each generic run carries searchable metadata such as:

```text
tags.project_id
tags.template_id=generic_tabular_doe
tags.phase_scope=generic_tabular_doe
tags.model_family
tags.model_name
tags.candidate_role=candidate|challenger
tags.lifecycle_role=candidate|challenger
tags.selected_candidate=true|false
params.model_name
params.model_family
params.input_dim
params.output_dim
params.split_strategy
params.selection_metric
```

The selected registered version carries lineage/governance metadata such as:

```text
project_id
schema_project_id
source_run_id
source_experiment_name
model_family
model_name
candidate_role=challenger
lifecycle_role=challenger
validation_status=pending_review
created_by_pipeline=true
selected_candidate=true
selection_metric=validation_weighted_normalized_rmse
selection_score
input_schema_hash
output_schema_hash
```

## PEM fuel-cell flow

PEM/fuel-cell training uses:

```text
backend/ml_lifecycle/training/fuel_cell_doe_demo/train.py
backend/ml_lifecycle/training/fuel_cell_doe_demo/mlflow.py
```

It follows the same governance policy as generic training:

```text
every deployable candidate -> one MLflow run
selected best candidate -> one registered model version
challenger -> selected best version
champion -> manual only
```

PEM candidates log deployable ONNX artifacts under the flavor name:

```text
onnx
```

The algorithm identity is stored in run tags/params and model-version tags, not in the logged artifact name.

The real PEM project is:

```text
pem_fuel_cell_real_cathode_degradation
```

with registered model:

```text
doe_surrogate_pem_fuel_cell_real_cathode_degradation
```

## Metrics

Regression metrics are logged per split and per output where available:

- R², with explicit handling for undefined values
- RMSE and MAE in each output's physical unit
- normalized RMSE using the train-target range
- MAE as percent of the split mean
- RMSE as percent of the train-target range/std
- train-mean baseline MAE/RMSE
- improvement versus the train-mean baseline
- validation weighted normalized RMSE for model selection

The selection metric is:

```text
validation_weighted_normalized_rmse
```

Lower is better.

## Runtime loading and fallback policy

Backend registry helpers live in:

```text
backend/app/services/mlflow_registry.py
backend/app/services/project_registry.py
backend/app/services/model_loader.py
```

Alias resolution order is:

```text
champion -> challenger -> baseline -> legacy Production fallback
```

Governance still treats `champion` as the only approved production pointer, but MVP/local serving can use `challenger` when no champion exists so newly trained projects remain usable during review.

Artifact handling differs by model flavor:

- PEM/fuel-cell deployable models are ONNX artifacts.
- Generic `generic_tabular_doe` MVP models are sklearn/joblib pipelines, with local runtime artifacts under `backend/data-minio/intake/projects/<project_id>/.../training_artifacts/latest/models/` and MLflow logged artifacts named `sklearn_pipeline`.
- Docker/offline fallback can use packaged local artifacts from `backend/data-minio/intake/projects/<project_id>/.../training_artifacts/latest/` when MLflow model loading is disabled or unavailable.

Local MLflow cache for downloaded MLflow artifacts is ignored runtime state:

```text
backend/.mlflow-cache/<project_id>/<alias>/
```

## Model Quality UI relationship to MLflow

Model Quality combines local training artifacts with MLflow metadata.

Local artifacts used by Model Quality include:

```text
backend/data-minio/intake/projects/<project_id>/.../training_artifacts/latest/metrics_summary.json
backend/data-minio/intake/projects/<project_id>/.../training_artifacts/latest/candidate_comparison.csv
backend/data-minio/intake/projects/<project_id>/.../training_artifacts/latest/predictions.csv
backend/data-minio/intake/projects/<project_id>/.../training_artifacts/latest/schema.json
backend/data-minio/intake/projects/<project_id>/.../training_artifacts/latest/preprocessing.json
```

MLflow metadata used by Model Quality includes:

```text
latest experiment runs
registered model versions
champion/challenger/baseline aliases
selected candidate tags
```

For a healthy default generic run, Model Quality should see:

```text
latest_runs: 7
candidate_comparison: 7 rows
challenger: present
champion: none unless manually assigned
baseline: none unless manually assigned
```

Prediction diagnostics are generated from:

```text
training_artifacts/latest/predictions.csv
```

and then activated into:

```text
backend/data-minio/intake/projects/<project_id>/.../training_artifacts/latest/predictions.csv
```

The UI uses these rows for fuel-cell polarization overlays, generic parity plots, residual plots, and export packages.

## Scientist review state

Scientist review state is stored locally as JSON:

```text
backend/data/model_quality_reviews/{project_id}.json
```

This is independent of MLflow aliases. MLflow aliases are registry governance pointers; review JSON stores app/UI review workflow state.

## Opening MLflow locally

```bash
cd backend
uv run mlflow ui --backend-store-uri ./mlruns --host 127.0.0.1 --port 5000
```

Open:

```text
http://127.0.0.1:5000
```

Useful filters:

```text
tags.project_id = 'fraunhofer_demo_39e89ec9'
tags.selected_candidate = 'true'
tags.model_family = 'ridge'
params.model_name = 'ridge_alpha_10.0'
metrics.validation_weighted_normalized_rmse < 0.2
```

## Docker / production direction

Do **not** copy `backend/mlruns/` into the backend Docker image as a long-term solution. Baking MLflow runs into the runtime image makes model history stale, bloats images, and mixes training/registry state with API serving.

Preferred local/professional architecture:

```text
backend container
  ├─ serves FastAPI
  ├─ loads packaged artifacts for demo/offline fallback
  └─ resolves approved/challenger models from MLflow when enabled

mlflow container
  ├─ tracking server on :5000
  ├─ SQLite/Postgres backend store
  └─ persistent artifact volume or object store
```

Recommended Docker Compose follow-up:

- Add an `mlflow` service running `mlflow server`.
- Add persistent storage for MLflow metadata/artifacts.
- Set backend/training env vars:

```text
MLFLOW_TRACKING_URI=http://mlflow:5000
DOE_DISABLE_MLFLOW_MODEL_LOADING=0
```

- Train/register models against the MLflow service, not a local `backend/mlruns/` folder.
- Let the Model Quality API fetch latest runs, aliases, versions, and artifacts from the MLflow server.
- Keep packaged local artifacts only as demo/offline fallback.

Production target:

```text
MLflow tracking URI: https://mlflow.<company-domain>
Backend store: Postgres / Cloud SQL / RDS
Artifact store: S3 / GCS / Azure Blob
Model routing: train to challenger; manually promote reviewed versions to champion
```

## Validation commands

Backend MLflow/generic/PEM validation:

```bash
cd backend
uv run pytest tests/test_generic_contract_pipeline.py tests/test_real_fuel_cell_data_pipeline.py -q
```

Frontend validation:

```bash
cd frontend
npm run build
```
