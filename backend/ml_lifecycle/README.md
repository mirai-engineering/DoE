# Mirai ML lifecycle architecture

This directory is the source of truth for Mirai's current ML lifecycle. The live path is **generic_tabular_doe**; fuel-cell-specific code under `deprecated_fuel_cell_reference/` is historical reference only.

## Package boundaries

- `ingesting/generic_tabular_doe/`: validates Mirai tabular DoE packages and builds canonical preprocessing artifacts.
- `training/generic_tabular_doe/`: trains candidate surrogate models, logs MLflow runs, and registers the selected challenger.
- `training/run_exported_package.py`: local/operator entry point for a UI-exported approved training package.
- `app/services/*`: API-side orchestration, object-storage persistence, MLflow registry verification, and Mirai activation.

## Mirai package contract

A training package exported from the UI contains the approved fitting surface and identity metadata:

- `model_table.csv` — canonical model table with `split` plus feature/target columns.
- `schema.json` — Mirai schema/domain metadata used by Model Quality and Design Studio.
- `training_manifest.json` — `workspace_id`, `project_id`, `dataset_id`, `session_id`, `training_request_id`, feature/target columns, exported timestamp, and source checksums.

Remote/local training must validate explicit identity flags against this manifest before logging to MLflow.

## MLflow concept map

- Experiment name: `<project_id>`.
- Registered model name: `doe_surrogate_<project_id>`.
- Training registers the selected best model as alias `challenger`.
- Human review manually promotes one registered model version to alias `champion`.
- Mirai **Load champion model** resolves `doe_surrogate_<project_id>@champion`, verifies workspace/project tags and required artifacts, then activates the champion in Mirai.

Do not use S3/MLflow artifact folder names as the operator-facing model identity. MLflow artifact paths may be run-ID/hash-oriented. The durable identity is the experiment, registered model, alias, run tags, model-version tags, and training manifest.

## Naming conventions

- `workspace_id`: tenant/workspace boundary, e.g. `fraunhofer`.
- `project_id`: project/model namespace; also the MLflow experiment name.
- `training_request_id`: immutable run/request attribution.
- Candidate algorithm identity belongs in run names and `model_name` tags/params/version tags. Logged model artifact names such as `sklearn_pipeline` and `onnx_model` are flavor/artifact names and should remain stable.

## Object-storage contract

Project-scoped objects should live under:

```text
workspaces/<workspace_id>/projects/<project_id>/
  raw/<dataset_id>/...
  canonical/latest/...
  preprocessing/latest/...
  eda/latest/...
  training_packages/<training_request_id>/...
  training_runs/<training_request_id>/...
  training_artifacts/latest/...
  artifacts/<training_request_id>/...      # compatibility mirror
  mlflow-artifacts/...                     # MLflow implementation detail
```

Storage writes must use `WorkspaceStorageConfig`, `validate_workspace_object_key`, and `put_workspace_object`/shared helpers so keys cannot escape the workspace/project prefix.

## Activation model

Champion activation is intentionally manual:

1. Export approved package from Mirai UI.
2. Train locally/Railway against remote MLflow.
3. Review MLflow challenger metrics/artifacts.
4. Manually assign alias `champion` in MLflow.
5. In Mirai, click **Load champion model** for the same workspace/project.

Mirai loads models by `workspace_id + project_id -> doe_surrogate_<project_id>@champion`, not by guessing S3 folders.
