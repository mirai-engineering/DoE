# Local MLflow workflow

This file summarizes the intended MLflow workflow for Mirai's DoE surrogate training. The source-of-truth implementation is split across:

```text
backend/training/real_training_pipeline/train_real_fuel_cell_models.py
backend/training/real_training_pipeline/mlflow_utils.py
backend/app/services/mlflow_registry.py
backend/app/services/training_requests.py
backend/training/real_data_pipeline/real_fuel_cell_schema.py
```

## Mental model

Keep these MLflow concepts separate:

| Concept | Meaning in Mirai | Example |
|---|---|---|
| Experiment | Training workspace / messy laboratory notebook | `pem_fuel_cell_real_cathode_degradation` |
| Run | One model training attempt | `ridge_alpha_1`, `mlp_trial_03` |
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

Code references:

```text
backend/training/real_data_pipeline/real_fuel_cell_schema.py
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

backend/training/real_training_pipeline/train_real_fuel_cell_models.py
  for model_name in deployable_model_names:
    _log_run(...)
      # every model becomes an experiment run
      register=register_mlflow and is_selected_candidate
      # only best model is registered

  if register_mlflow:
    set_model_alias(run_ids[best_model_name], "challenger", ...)
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
backend/training/real_training_pipeline/train_real_fuel_cell_models.py
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

backend/training/real_training_pipeline/mlflow_utils.py
  set_model_version_tags(...)
    client.set_model_version_tag(...)
    client.set_registered_model_tag(...)
    client.update_model_version(... description=...)
```

## Loading / downloading the served model

The app does **not** upload a champion model at serving time. Training logs model artifacts to MLflow; the Model Registry stores metadata and pointers to those run artifacts. Serving then **downloads** the aliased registered model artifact from MLflow.

Production serving should load by alias, not by hardcoded version:

```text
models:/doe_surrogate_<project_id>@champion
```

For this project:

```text
models:/doe_surrogate_pem_fuel_cell_real_cathode_degradation@champion
```

Where it comes from:

```text
MLFLOW_TRACKING_URI if set
otherwise backend/mlruns
```

Backend resolution order:

```text
champion -> challenger -> baseline -> legacy Production fallback
```

Downloaded ONNX artifacts are cached locally under:

```text
backend/.mlflow-cache/<project_id>/<alias>/
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

Docker note: when MLflow model loading is disabled, serving uses packaged artifacts from:

```text
backend/artifacts/<project_id>/
```

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
