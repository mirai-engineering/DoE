# Mirai Training Lifecycle

Mirai has one generic preprocessing/training engine and two execution adapters.

## Core engine

```text
backend/ml_lifecycle/
  ingesting/generic_tabular_doe/preprocessing.py
  training/generic_tabular_doe/train.py::train_generic_project(...)
```

`generic_tabular_doe` is the live lifecycle path. Uploaded ZIP packages are expected to be Mirai contract packages with project-specific inputs, outputs, labels, ranges, and metadata.

## Canonical lifecycle

```text
approved preprocessing
  -> training request created
  -> execution pending
  -> train_generic_project(...)
       via Railway OR local exported package
  -> remote MLflow run/model version
  -> app dev promotes intended MLflow model version to alias: champion
  -> Mirai Load champion model
  -> Approved champion active
  -> Model Quality + Design Studio use the loaded champion
```

The single user-visible activation action is **Load champion model**. There is no separate user-facing sync step.

## Execution adapters

### A. Managed Railway execution

```text
Mirai UI
  -> approved training request
  -> Start training
  -> backend/app/services/training_requests.py::start_training_request(...)
  -> train_generic_project(...)
  -> canonical training_runs row
  -> MLflow model version awaiting champion approval
```

Railway execution invokes the same generic engine. It must not create an active serving champion until the selected MLflow model version has the `champion` alias and **Load champion model** succeeds.

### B. Local/on-prem execution

```text
Mirai UI
  -> approved training request
  -> export approved package
  -> local MacBook/on-prem runs run_exported_package.py
  -> train_generic_project(...)
  -> remote MLflow run/model version
  -> app dev promotes selected model version to champion in MLflow
  -> Load champion model in Mirai
```

Local training must not write directly to Railway Postgres. It logs to remote MLflow. Mirai only activates serving after backend verification during **Load champion model**.

## Load champion model contract

The activation path is:

```text
POST /projects/{project_id}/models/load-champion-model
backend/app/services/training_requests.py::load_champion_model(...)
backend/app/services/mlflow_registry.py::verify_champion_mlflow_model(...)
```

Load champion verifies:

- current MLflow registered model alias is `champion`
- optional selected run/version/model fields match that current champion
- `workspace_id` and `project_id` match the Mirai project
- source run status is `FINISHED`
- required artifacts exist:
  - `schema.json`
  - `preprocessing.json`
  - `metadata.json`
  - `metrics_summary.json`
  - `candidate_comparison.csv`
  - `predictions.csv`
  - `training_manifest.json`
- `training_manifest.json` contains matching project identity and source checksums
- the MLflow model artifact contains a required ONNX model for serving

On success, Mirai:

- downloads/caches the run artifacts and ONNX model
- backfills the runtime schema manifest when missing
- creates or updates the completed `training_runs` row
- creates or updates the active `models` champion row
- clears runtime schema/model caches

Mirai does not automatically promote challengers based on metrics. Manual MLflow alias promotion remains the MVP approval source.

## App behavior

| State | UI behavior | Serving behavior |
| --- | --- | --- |
| Training request pending | App-dev training/export controls visible | No model served |
| MLflow run exists but no champion loaded | **Load champion model** app-dev step is available | Prediction and batch recommendations fail closed |
| Champion loaded in Mirai | `Champion loaded` / `Approved champion active` | Prediction and Design Studio use the loaded ONNX champion only |

Model Quality uses static training artifacts such as `metrics_summary.json`, `candidate_comparison.csv`, and `predictions.csv`. Design Studio uses the served champion for live deterministic predictions and can overlay training points from `predictions.csv`.

## Operator how-to

1. In Mirai, upload a Mirai contract ZIP and approve metadata/preprocessing.
2. Create a training request.
3. Export the approved training package.
4. On the local/on-prem machine, use direnv and run exported-package training:

   ```bash
   cd backend
   direnv allow ..  # if needed for the repo envrc
   uv run python -m ml_lifecycle.training.run_exported_package --package-dir /path/to/package
   ```

5. Inspect the remote MLflow run and registered model.
6. In MLflow, manually promote the intended registered model version to alias `champion`.
7. In Mirai, click **Load champion model** or call:

   ```text
   POST /projects/{project_id}/models/load-champion-model
   ```

8. Confirm the UI shows `Champion loaded` / `Approved champion active`.
9. Confirm Model Quality plots populate from `predictions.csv`.
10. Confirm Design Studio predictions and batch recommendations use the loaded champion.

## Cleanup notes

Retained live paths:

```text
backend/ml_lifecycle/ingesting/generic_tabular_doe/
backend/ml_lifecycle/training/generic_tabular_doe/
backend/ml_lifecycle/training/run_exported_package.py
```

Fuel-cell-specific extractor/adapter paths are not part of the generic live path and should remain removed or quarantined once tests confirm uploaded pilot ZIPs are Mirai contract packages.
