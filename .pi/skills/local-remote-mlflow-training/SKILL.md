---
name: local-remote-mlflow-training
description: Use when running Mirai training locally while logging to remote MLflow, especially with downloaded model_table_preprocessed.csv, exported training packages, project identity, MLflow experiment/model names, or preventing cross-project MLflow contamination.
---

# Local training with remote MLflow logging for Mirai

This skill prevents a dangerous failure mode: training locally with a downloaded CSV or stale manifest and logging runs/artifacts into the wrong remote MLflow experiment/registered model.

## Non-negotiable rule

Do **not** train from a loose `model_table_preprocessed.csv` alone.

A CSV has rows and columns, but it does not prove the owning Mirai workspace/project/dataset/session/training request. Local remote training must use an approved exported Mirai training package from the intended project.

Required package contents:

- `training_manifest.json`
- `schema.json`
- `model_table_preprocessed.csv` for ML preprocessing v1, or approved `model_table.csv` for legacy fallback
- `feature_map.json` and `target_map.json` when using ML preprocessing v1
- preprocessing/report/checksum artifacts when present

## Identity checks before every run

Inspect the package manifest before launching training:

```bash
unzip -p /path/to/mirai-training-package.zip training_manifest.json | jq '{workspace_id, project_id, dataset_id, session_id, training_request_id, preprocessing_contract_version}'
```

Confirm these match the current Mirai project selected in the deployed app.

MLflow names are derived from `project_id`:

- MLflow experiment: `<project_id>`
- Registered model: `doe_surrogate_<project_id>`

If the experiment is an older project, stop. Re-export the package from the correct project. Never reuse a schema or manifest from another project.

## Correct local command pattern

Run only the package runner, not a one-off CSV helper:

```bash
cd backend
set -a && source .env.training.local && set +a
MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true \
MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=true \
.venv/bin/python -m ml_lifecycle.training.run_exported_package \
  --package-dir /path/to/unzipped/exported-package \
  --workspace-id <workspace_id_from_manifest> \
  --project-id <project_id_from_manifest> \
  --dataset-id <dataset_id_from_manifest> \
  --session-id <session_id_from_manifest> \
  --training-request-id <training_request_id_from_manifest>
```

The runner must fail if supplied flags do not match `training_manifest.json`.

## Remote artifact verification

After training, verify the selected run is remote and has remote artifacts:

```python
from mlflow.tracking import MlflowClient
client = MlflowClient(tracking_uri="https://<remote-mlflow-host>", registry_uri="https://<remote-mlflow-host>")
run = client.get_run("<run_id>")
print(run.info.experiment_id, run.info.artifact_uri)
print(run.data.tags.get("project_id"), run.data.tags.get("workspace_id"))
print([a.path for a in client.list_artifacts("<run_id>")])
```

Expected:

- `artifact_uri` starts with `mlflow-artifacts:/` or `s3://`
- run tag `project_id` equals the intended Mirai project
- artifacts include `training_manifest.json`, `schema.json`, `preprocessing.json`, metrics, candidate comparison, predictions, ONNX/model artifacts, and for ML preprocessing v1: `model_table_preprocessed.csv` or its manifest/report artifacts as required by policy

## Red flags

Stop and correct the package/export if any of these happen:

- The only MLflow experiment receiving runs is an older project.
- `training_manifest.json.project_id` does not equal the intended project.
- The command uses a manually copied `schema.json` or `training_manifest.json` from a previous run.
- A helper script hardcodes project IDs or paths.
- The run lacks project/dataset/session/training-request tags.
- The run has local `file://` artifact URI while remote artifacts were required.

## Recovery

If a run was logged to the wrong project:

1. Do not promote it to `champion` for the intended project.
2. Do not manually copy artifacts between experiments as a substitute for retraining.
3. Re-export the approved package from the intended Mirai project.
4. Re-run the package runner with matching identity flags.
5. Promote only the correct registered model `doe_surrogate_<intended_project_id>`.
6. In Mirai, use **Load champion model** for that same project.
