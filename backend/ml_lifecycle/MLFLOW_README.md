# Local MLflow workflow

This file summarizes the intended MLflow workflow for Mirai's DoE surrogate training. The source-of-truth implementation is split across:

```text
backend/ml_lifecycle/training/fuel_cell_doe_demo/train.py
backend/ml_lifecycle/training/fuel_cell_doe_demo/mlflow.py
backend/ml_lifecycle/training/generic_tabular_doe/train.py
backend/app/services/mlflow_registry.py
backend/app/services/training_requests.py
backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/schema.py
```

## Mental model

Keep these MLflow concepts separate:

| Concept | Meaning in Mirai | Example |
|---|---|---|
| Experiment | Training workspace / messy laboratory notebook | `pem_fuel_cell_real_cathode_degradation` |
| Run | One model training attempt | `ridge_alpha_1`, `mlp_trial_03` |
| Logged model artifact | Deployable model payload inside a run, named by flavor/type rather than algorithm metadata | `onnx`, `sklearn_pipeline` |
| Registered Model | Stable deployable surrogate family | `doe_surrogate_pem_fuel_cell_real_cathode_degradation` |
| Model Version | One promoted artifact from a specific run | Version 8 = selected MLP run |
| Alias | Mutable role pointer | `baseline`, `challenger`, `champion` |

The registry should contain deployable candidates, not every training attempt.

## Naming convention

Use distinct names:

```text
Experiment name:        <project_id>
Registered model name:  doe_surrogate_<project_id>
```

For the current real fuel-cell project:

```text
Experiment:        pem_fuel_cell_real_cathode_degradation
Registered Model:  doe_surrogate_pem_fuel_cell_real_cathode_degradation
```

Do **not** include algorithm names, run names, `challenger`, or `champion` in the registered model name. Those belong in run params, model-version tags, and aliases.

Logged model artifact names should be short flavor/type names because each logged model already lives inside a candidate run with searchable model metadata. Use names such as:

```text
onnx
sklearn_pipeline
```

Avoid ambiguous generic names like `model`, and avoid duplicating algorithm metadata in the logged model artifact name, such as `ridge_alpha_10.0_sklearn_pipeline`. The algorithm identity belongs in `tags.model_name`, `params.model_name`, run name, and model-version tags.

Code references:

```text
backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/schema.py
  MLFLOW_REGISTERED_MODEL_NAME = f"doe_surrogate_{PROJECT_ID}"

backend/app/services/mlflow_registry.py
  registered_model_name_for_project(project_id) -> f"doe_surrogate_{project_id}"
```

## Intended training / registry flow

Automatic pipeline behavior:

1. Train all configured candidates: MVLR, Ridge variants, MLP trials, etc.
2. Log every candidate as an MLflow experiment run.
3. Compare validation metrics.
4. Select the best candidate using `validation_weighted_normalized_rmse`.
5. Register **only the selected best candidate** as a new Model Registry version.
6. Set `challenger` on that selected registered version.
7. Never set or overwrite `champion` automatically.
8. Optionally assign `baseline` manually to a stable accepted baseline model version.

Manual workflow:

1. Open MLflow UI.
2. Compare runs inside the experiment.
3. Inspect the registered `challenger` version.
4. If approved, manually move `champion` to that version in MLflow.

Code references:

```text
backend/app/services/training_requests.py
  start_training_request(...)
    mlflow_experiment_name=project_id
    registered_model_name=registered_model_name_for_project(project_id)
    set_alias="challenger"

backend/ml_lifecycle/training/fuel_cell_doe_demo/train.py
  for model_name in deployable_model_names:
    _log_run(...)
      # every model becomes an experiment run
      mlflow.onnx.log_model(name="onnx", registered_model_name=... if selected)
      register=register_mlflow and is_selected_candidate
      # only best model is registered

  if register_mlflow:
    set_model_alias(run_ids[best_model_name], "challenger", ...)

backend/ml_lifecycle/training/generic_tabular_doe/train.py
  for candidate in candidates:
    mlflow.start_run(run_name=f"generic_tabular_doe__{model_name}")
      # every generic model becomes an experiment run
      mlflow.sklearn.log_model(name="sklearn_pipeline", registered_model_name=... if selected)
      # only best model is registered

  client.set_registered_model_alias(registered_model_name, "challenger", selected_version)
```

## Concrete example

Training session:

```text
Experiment: pem_fuel_cell_real_cathode_degradation

Runs:
  run_A = mvlr
  run_B = ridge_alpha_0_1
  run_C = ridge_alpha_1_0
  run_D = mlp_trial_01
  run_E = mlp_trial_02
  run_F = mlp_trial_03
```

If `run_F` is selected as best:

```text
Registered Model:
  doe_surrogate_pem_fuel_cell_real_cathode_degradation

New Model Version:
  Version N = artifact from run_F

Aliases:
  challenger -> Version N
  champion   -> unchanged, manual only
  baseline   -> optional/manual reference pointer
```

Expected result for 8 trained candidates:

```text
8 MLflow experiment runs
1 new registered model version
1 challenger alias pointing to that selected version
0 automatic champion changes
optional baseline alias if manually assigned
```

The generic `generic_tabular_doe` flow follows the same governance pattern as the PEM fuel-cell flow. For the default generic candidate set:

```text
Experiment: fraunhofer_demo_39e89ec9
Runs:
  mean_baseline
  mvlr
  ridge_alpha_0.01
  ridge_alpha_0.1
  ridge_alpha_1.0
  ridge_alpha_10.0
  mlp

Registered Model:
  doe_surrogate_fraunhofer_demo_39e89ec9

Expected result:
  7 MLflow experiment runs
  1 new registered model version from the selected best run
  challenger -> selected best version
  champion   -> unchanged, manual only
```

## Version metadata and tags

The selected registered version should carry enough metadata to understand lineage, governance state, and model quality without guessing from the version number.

Selected model-version tags include:

```text
project_id
schema_project_id
source_run_id
source_experiment_name
model_type
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
dataset_id
ingestion_session_id
preprocessing_report_id
training_request_id
```

Candidate experiment runs carry run-level tags/params such as:

```text
project_id
phase_scope
quality_label
model_family
model_name
candidate_role
selected_candidate
seed
input_dim
output_dim
split_strategy
search_mode
```

Code references:

```text
backend/ml_lifecycle/training/fuel_cell_doe_demo/train.py
  _log_run(...)
    mlflow.set_tags(lifecycle_tags)
    mlflow.log_params(params)
    mlflow.log_metrics(metrics)
    mlflow.onnx.log_model(...)

  set_model_version_tags(...)
    source_run_id
    source_experiment_name
    model_type
    selection_metric
    selection_score
    input_schema_hash
    output_schema_hash

backend/ml_lifecycle/training/fuel_cell_doe_demo/mlflow.py
  set_model_version_tags(...)
    client.set_model_version_tag(...)
    client.set_registered_model_tag(...)
    client.update_model_version(... description=...)
```

## Loading / downloading the served model

The app does **not** upload a champion model at serving time. Training logs model artifacts to MLflow; the Model Registry stores metadata and pointers to those run artifacts. Serving/model-quality then resolves the appropriate aliased registered model and/or local activated runtime artifacts.

Production governance should route approved serving through `champion` by alias, not by hardcoded version:

```text
models:/doe_surrogate_<project_id>@champion
```

For local MVP continuity, backend resolution order is:

```text
champion -> challenger -> baseline -> legacy Production fallback
```

This means a freshly trained project can still be inspected/used through `challenger` before a human promotes it to `champion`, but the pipeline never sets `champion` automatically.

Where MLflow state comes from:

```text
MLFLOW_TRACKING_URI if set
otherwise backend/mlruns
```

Artifact flavor differs by flow:

```text
PEM/fuel-cell:         logged MLflow model artifact name = onnx
Generic tabular DoE:   logged MLflow model artifact name = sklearn_pipeline
```

Downloaded MLflow artifacts are cached locally under ignored runtime state:

```text
backend/.mlflow-cache/<project_id>/<alias>/
```

Serving resolves the MLflow alias first. If MLflow is unavailable, uploaded projects may fall back to their active session training artifacts under:

```text
backend/data-minio/intake/projects/<project_id>/.../training_artifacts/latest/
```

Code references:

```text
backend/app/services/project_registry.py
  get_project_model_path(project_id)
    may call download_production_onnx(project_id)

backend/app/services/mlflow_registry.py
  download_production_onnx(project_id)
    client.get_model_version_by_alias(registered_model_name, alias)
    mlflow.artifacts.download_artifacts(...)

  get_registered_model_metadata(project_id)
    reports champion/challenger/baseline aliases
```

Docker note: the container should include MLflow registry state and/or active session training artifacts. There is no separate packaged runtime-project fallback directory.

## Alias policy

```text
baseline   = stable reference version, usually manually assigned
challenger = latest selected candidate under review, set automatically
champion   = approved production model, manual only
```

The backend can load `challenger` when no `champion` exists for MVP continuity, but production governance should treat `champion` as the only approved serving pointer.

## Open the MLflow UI

```bash
cd backend
uv run mlflow ui --backend-store-uri ./mlruns --host 127.0.0.1 --port 5000
```

Open:

```text
http://127.0.0.1:5000
```

Useful run filters:

```text
tags.project_id = 'pem_fuel_cell_real_cathode_degradation'
tags.model_family = 'mlp'
tags.candidate_role = 'challenger'
params.model_name = 'mvlr'
metrics.validation_weighted_normalized_rmse < 0.12
```
