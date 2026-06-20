# Mirai Training Lifecycle

Mirai has one core preprocessing/training engine and two execution adapters.

## Core engine

```text
backend/ml_lifecycle/
  ingesting/generic_tabular_doe/preprocessing.py
  training/generic_tabular_doe/train.py::train_generic_project(...)
```

Do not delete `backend/ml_lifecycle/`. It is the shared lifecycle engine for both managed and local execution.

Historical fuel-cell modules remain as reference/offline migration code and are not removed in this cleanup.

## Canonical lifecycle

```text
approved preprocessing
  -> training request created
  -> execution pending
  -> train_generic_project(...)
       via Railway OR local exported package
  -> MLflow candidate run/model
  -> Mirai verifies/imports candidate
  -> Candidate ready for review
  -> operator manually promotes MLflow alias: champion
  -> Mirai refreshes/reconciles approved champion
  -> Approved champion active
  -> serving / Design Studio use champion only
```

## Execution adapters

### A. Managed Railway execution

```text
Mirai UI
  -> approved training request
  -> Start training
  -> backend/app/services/training_requests.py::start_training_request(...)
  -> train_generic_project(...)
  -> canonical training_runs row
  -> reviewable candidate model state
```

Railway execution invokes the same generic engine. It must not create an active serving champion unless the champion reconciliation step has happened.

### B. Local/on-prem execution

```text
Mirai UI
  -> approved training request
  -> export approved package
  -> local MacBook/on-prem runs run_exported_package.py
  -> train_generic_project(...)
  -> remote MLflow candidate run/model
  -> Import MLflow run in Mirai
  -> Candidate ready for review
```

Local training must not write directly to Railway Postgres. It logs to remote MLflow and then Mirai imports only after backend verification.

## Candidate import contract

The import path reuses:

```text
POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests/{training_request_id}/import-mlflow-run
backend/app/services/training_requests.py::import_external_mlflow_run(...)
backend/app/services/mlflow_registry.py::verify_external_mlflow_model_version(...)
```

Import verifies:

- `workspace_id`
- `project_id`
- `dataset_id`
- `session_id` / `ingestion_session_id`
- `training_request_id`
- MLflow run ID
- registered model name/version/alias
- run status is `FINISHED`
- required artifacts exist:
  - `schema.json`
  - `preprocessing.json`
  - `metrics_summary.json`
  - `candidate_comparison.csv`
  - `predictions.csv`
  - `training_manifest.json`
- manifest source checksums match the approved Mirai export package

A successful import records candidate state as reviewable. It does not make the model active for serving.

## Champion reconciliation

Manual MLflow promotion is the source of approval for now:

```text
MLflow registered model alias = champion
```

After promotion, an operator refreshes Mirai:

```text
POST /projects/{project_id}/models/refresh-approved-champion
```

The backend verifies the MLflow `champion` alias, workspace/project identity, source run status, required artifacts, and that the champion run was already imported into Mirai. Only then does Mirai update the canonical champion model row.

Mirai does not automatically promote challengers based on metrics.

## App behavior

| State | UI behavior | Serving behavior |
| --- | --- | --- |
| No imported local run | `Awaiting local-run import` / training request pending | No local challenger is served |
| Imported challenger | `Candidate ready for review` | Model Quality can review candidate artifacts if complete; Design Studio/serving still require champion |
| Champion promoted in MLflow but not refreshed in Mirai | Operator must click/call refresh | Not active in Mirai yet |
| Champion reconciled in Mirai | `Approved champion active` | Prediction and Design Studio use the reconciled champion only |

## Operator how-to

1. In Mirai, upload data and approve preprocessing.
2. Create a training request.
3. Export the approved training package.
4. On the local/on-prem machine, use direnv and run exported-package training:

   ```bash
   cd backend
   direnv allow ..  # if needed for the repo envrc
   uv run python -m ml_lifecycle.training.run_exported_package --package-dir /path/to/package
   ```

5. Inspect the remote MLflow run and registered model.
6. Confirm the selected candidate is registered as `challenger`.
7. In Mirai, import the MLflow run for the matching training request.
8. Review Model Quality candidate artifacts.
9. In MLflow, manually promote the intended registered model version to alias `champion`.
10. In Mirai, click **Refresh approved model** or call:

    ```text
    POST /projects/{project_id}/models/refresh-approved-champion
    ```

11. Confirm the UI shows `Approved champion active` and Design Studio/prediction endpoints use the reconciled champion.

## Cleanup notes

Retained:

```text
backend/ml_lifecycle/ingesting/generic_tabular_doe/
backend/ml_lifecycle/training/generic_tabular_doe/
backend/ml_lifecycle/training/run_exported_package.py
```

Deferred cleanup candidates only:

```text
backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/
backend/ml_lifecycle/training/fuel_cell_doe_demo/
backend/ml_lifecycle/entrypoints/*real_fuel_cell*
backend/ml_lifecycle/ingesting/extractors/pem_cell_zip_bundle.py
```
