# ML lifecycle docs and storage plan

## Context

The repo currently has overlapping ML lifecycle docs in `docs/mlflow_remote_access.md`, `docs/training_lifecycle.md`, `backend/ml_lifecycle/README.md`, and `backend/ml_lifecycle/MLFLOW_README.md`. The user wants these consolidated under `backend/ml_lifecycle/` into one or at most two source-of-truth markdown files.

The immediate operational issue is that Railway/S3/MLflow storage is hard to reason about: `mlflow_artifacts/` object names do not obviously map to the champion model selected in MLflow, while `projects/` is better named but appears to retain only uploaded ZIPs and not the canonical training/EDA artifacts needed for local training and audit. The local command currently only says to log into a remote MLflow URL and run `uv run python -m ml_lifecycle.training.run_exported_package --package-dir /path/to/package`, without clearly naming the target bucket/prefix or artifact contract.

## Initial findings

- Live lifecycle path is `generic_tabular_doe`; deprecated fuel-cell-specific paths should not be part of the new source of truth.
- Existing app code expects MLflow registered model names to be `doe_surrogate_<project_id>` via `backend/app/services/mlflow_registry.py::registered_model_name_for_project`.
- Existing app code treats `champion` as an MLflow registered-model alias, not as an S3 folder name. The champion is resolved via MLflow Registry (`models:/doe_surrogate_<project_id>/<version>`) and then Mirai downloads/verifies the source run artifacts.
- The S3/MLflow artifact layout is expected to be implementation detail. MLflow artifact folders may be run-ID/hash oriented and are not the intended operator navigation surface. The intended human-readable pointers are the MLflow experiment (`<project_id>`), registered model (`doe_surrogate_<project_id>`), aliases (`challenger`, `champion`), run tags (`model_name`, `workspace_id`, `project_id`, `training_request_id`), and project-scoped object keys.
- Existing tests and services use durable project storage keys like `workspaces/<workspace_id>/projects/<project_id>/training_artifacts/latest/...`, `workspaces/<workspace_id>/projects/<project_id>/artifacts/<training_request_id>/...`, and `workspaces/<workspace_id>/projects/<project_id>/mlflow-artifacts/...`.
- Upload intake writes raw ZIP/files to object storage under `.../raw/<dataset_id>/...`. Preprocessing generates canonical/training/EDA artifacts in the app-local session workspace, but I have not yet found a matching S3 upload step for those preprocessing outputs before training.
- Managed Railway training uploads `training_latest` artifacts to S3 under `.../artifacts/<training_request_id>/...` after training. That appears to cover model-quality artifacts for Railway-managed training, but not necessarily the pre-training canonical/EDA persistence the user wants for local training.
- Local exported-package training validates `MLFLOW_TRACKING_URI`, requires remote MLflow/artifacts guard env vars, creates a local working layout, trains, logs artifacts to remote MLflow, and registers only the selected best ONNX model as `challenger`.
- Generic training already sets `tags.model_name`, `params.model_name`, `model_family`, `workspace_id`, `project_id`, `training_request_id`, and version tags; the `sklearn_pipeline` logged-model name is a flavor/artifact name, while true candidate identity lives in run/version metadata.
- `verify_champion_mlflow_model` requires the champion source run to have `schema.json`, `preprocessing.json`, `metadata.json`, `metrics_summary.json`, `candidate_comparison.csv`, `predictions.csv`, `training_manifest.json`, matching workspace/project tags, non-empty manifest checksums, and a registered ONNX model.
- Current docs already say the intended flow is: train candidates -> register selected best as `challenger` -> manually promote to `champion` -> Mirai `Load champion model` verifies and caches artifacts.

## Approach

Use two source-of-truth docs under `backend/ml_lifecycle/`:

1. `backend/ml_lifecycle/README.md` — lifecycle architecture, repo intent, data/MLflow mental model, naming conventions, and what belongs in app storage vs MLflow.
2. `backend/ml_lifecycle/REMOTE_TRAINING.md` — Railway/MLflow setup, local operator workflow, UI export-package workflow, required env vars, promotion/load-champion steps, and troubleshooting.

Delete the old overlapping docs after their still-current information is migrated:

- `docs/mlflow_remote_access.md`
- `docs/training_lifecycle.md`
- `backend/ml_lifecycle/MLFLOW_README.md`

Prioritize robustness, maintainability, and traceability over a disruptive storage rewrite. Implement a clear project-scoped object-store contract for new artifacts, while preserving compatibility with existing current paths where reasonable. Do not make MLflow S3 folder names the human-facing source of truth; use MLflow registry metadata and deterministic Mirai object keys instead.

Recommended object-store contract for new/persisted artifacts:

```text
workspaces/<workspace_id>/projects/<project_id>/
  raw/<dataset_id>/...                         # uploaded source package/files, already mostly present
  canonical/latest/model_table.csv|parquet     # approved canonical fitting surface
  preprocessing/latest/...                     # schema, preprocessing, split/profile/reports
  eda/latest/...                               # EDA/profile artifacts when generated
  training_packages/<training_request_id>/...  # exported package zip + manifest/checksum metadata
  training_artifacts/latest/...                # active/latest quality and serving-adjacent artifacts
  training_runs/<training_request_id>/...      # immutable per-run copy of training artifacts
  mlflow-artifacts/...                         # MLflow implementation detail; not operator navigation source
```

Keep the local training source as the existing UI-exported package flow, assuming the UI route is already implemented. Strengthen the local command so attribution is explicit and validated instead of implicit. The exported package manifest remains the source of truth, but the operator must pass workspace/project identity flags for remote training; the CLI should fail if the flags disagree with `training_manifest.json`. Recommended command shape:

```bash
cd backend
uv run python -m ml_lifecycle.training.run_exported_package \
  --package-dir /path/to/exported/package \
  --workspace-id fraunhofer \
  --project-id ccm_degradation_029a2f61 \
  --dataset-id <dataset_id> \
  --training-request-id <training_request_id>
```

`--dataset-id` and `--training-request-id` may be optional if present in the manifest, but if provided they must also be validated. The CLI should derive the MLflow experiment and registered model from these IDs (`experiment=<project_id>`, `registered_model=doe_surrogate_<project_id>`) and log all identity fields as run tags, params where appropriate, model-version tags, and `training_manifest.json`. This gives the app a single deterministic load path: `workspace_id + project_id -> registered model doe_surrogate_<project_id> -> champion alias -> source run artifacts`.

Keep manual promotion: training registers only the selected best model as `challenger`; the operator/app dev manually promotes the approved version to `champion` in MLflow; then Mirai's existing **Load champion model** action verifies and activates it. Do not add automatic champion promotion.

## Files to modify

Documentation:

- `backend/ml_lifecycle/README.md` — rewrite as canonical architecture/source-of-truth doc.
- `backend/ml_lifecycle/REMOTE_TRAINING.md` — new operator/Railway/local-training runbook.
- Delete `docs/mlflow_remote_access.md` after migration.
- Delete `docs/training_lifecycle.md` after migration.
- Delete `backend/ml_lifecycle/MLFLOW_README.md` after migration.

Code/tests:

- `backend/app/services/preprocessing_review.py` and/or shared storage helper — persist approved preprocessing/canonical/EDA artifacts to deterministic project-scoped object keys after preprocessing completion/approval.
- `backend/app/services/training_requests.py` — persist exported package zip/manifest metadata under `training_packages/<training_request_id>/...`; adjust training artifact upload to also write/read clear `training_runs/<training_request_id>/...` and/or `training_artifacts/latest/...` pointers while keeping current compatibility.
- `backend/app/services/mlflow_registry.py` — improve error/status messages for missing champion alias, missing MLflow artifacts, and model-name/alias guidance; keep registered model naming `doe_surrogate_<project_id>`.
- `backend/ml_lifecycle/training/run_exported_package.py` — add explicit identity flags (`--workspace-id`, `--project-id`, optional `--dataset-id`, `--session-id`, `--training-request-id`), validate them against `training_manifest.json`, and improve preflight/final JSON output with workspace/project/dataset/session/training request, registered model name, experiment name, alias instructions, and remote URI.
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py` — leave `sklearn_pipeline`/`onnx_model` artifact names unless tests reveal missing metadata; true candidate identity is already logged in tags/params/version tags.
- Tests under `backend/tests/` for storage keys, export package persistence, CLI output/preflight, MLflow durable pointers, and lifecycle canonicalization.

## Reuse

- `backend/app/services/mlflow_registry.py::registered_model_name_for_project`
- `backend/app/services/mlflow_registry.py::verify_champion_mlflow_model`
- `backend/app/services/training_requests.py::load_champion_model`
- `backend/ml_lifecycle/training/run_exported_package.py`
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py`

## Open questions

None remaining from the user. Implementation should avoid guessing new architecture beyond the decisions above: two docs, delete old docs, keep UI export-package workflow, keep manual champion promotion, prioritize maintainable/traceable storage.

## Agent / skill mapping

| Task | Recommended agent/skill usage |
| --- | --- |
| Documentation consolidation | Use a docs-focused agent/skill if available. It should migrate current content, remove contradictions, and keep commands exact. No broad code changes in this task. |
| Object-storage persistence | Use a backend/storage-focused agent/skill if available. It should inspect `workspace_storage.py`, `data_intake.py`, `preprocessing_review.py`, and `training_requests.py`; avoid duplicating storage validation logic. |
| MLflow lifecycle fixes | Use an MLflow/backend agent/skill if available. It should focus on registry aliases, run/version tags, required artifact checks, and error messages; avoid changing champion policy. |
| Tests | Use a test-focused agent/skill or reviewer if available. It should add/adjust pytest coverage for storage keys, exported package persistence, CLI preflight/output, and load-champion failure messages. |
| Final review | Use a code-review agent/skill if available after implementation to check traceability, old-doc deletion, no secret leakage, no hardcoded Fraunhofer-only assumptions, and backward compatibility. |

## Steps

- [ ] Rewrite `backend/ml_lifecycle/README.md` as the canonical architecture doc: package boundaries, `generic_tabular_doe`, Mirai package contract, MLflow concept map, naming conventions, object-storage contract, and manual champion activation model.
- [ ] Create `backend/ml_lifecycle/REMOTE_TRAINING.md` with Railway variables by name only, local `backend/.env.training.local` shape, UI export-package workflow, exact local training command with explicit `--workspace-id`/`--project-id` attribution flags, MLflow challenger/champion promotion steps, **Load champion model**, and troubleshooting for the Design Studio “Model quality is not available yet” symptom.
- [ ] Delete `docs/mlflow_remote_access.md`, `docs/training_lifecycle.md`, and `backend/ml_lifecycle/MLFLOW_README.md` after migrating still-current content.
- [ ] Add/reuse a storage helper that uploads a bounded directory tree to a validated project-scoped prefix using `WorkspaceStorageConfig`, `validate_workspace_object_key`, and `put_workspace_object`; keep raw/reference exclusions where needed.
- [ ] Persist preprocessing outputs after preprocessing completion/approval: canonical model table, schema/preprocessing/split/profile/report artifacts, and EDA/profile artifacts under deterministic `canonical/latest/`, `preprocessing/latest/`, and `eda/latest/` keys.
- [ ] Persist exported UI training packages under `training_packages/<training_request_id>/`, including the ZIP, `training_manifest.json`, checksum, created-at/exported-at metadata, and enough workspace/project/dataset/session identity for audit.
- [ ] Adjust managed training artifact upload to provide deterministic per-run and latest project keys (`training_runs/<training_request_id>/...` plus `training_artifacts/latest/...`) while preserving or gracefully migrating the existing `artifacts/<training_request_id>/...` behavior used by tests/UI.
- [ ] Improve `run_exported_package.py` preflight/final JSON: require or accept explicit identity flags, validate them against the package manifest, print experiment name `<project_id>`, registered model `doe_surrogate_<project_id>`, run identity, remote tracking URI, expected output alias `challenger`, and next manual steps. The run must be unambiguously attributable to a specific `workspace_id/project_id`, and Mirai must be able to resolve the model later from the registered model alias rather than from ambiguous S3 folder names.
- [ ] Improve MLflow registry/load-champion errors so missing champion alias, wrong registered model name, missing required artifacts, or workspace/project mismatch clearly tell the operator what to check in MLflow UI.
- [ ] Keep logged model artifact names (`sklearn_pipeline`, `onnx_model`) unless a test proves metadata is missing; document that true algorithm identity belongs in `model_name` tags/params/version tags and run name.
- [ ] Add/adjust tests for the new object key layout, preprocessing persistence, export package persistence, local training identity flag validation/output/preflight, MLflow durable pointers, and load-champion diagnostics.

## Verification

- Run targeted backend tests, likely including:
  - `uv run pytest tests/test_api.py -k "preprocessing or export_package or import_mlflow"`
  - `uv run pytest tests/test_mlflow_durable_pointers.py`
  - `uv run pytest tests/test_training_lifecycle_canonicalization.py`
- Run any new storage/export tests added for this work.
- Manually inspect the two new docs for no secrets, no stale fuel-cell-only runtime guidance, exact commands, and clear explanation of MLflow vs S3 naming.
- End-to-end Railway-like check: upload package -> preprocess/approve -> confirm project-scoped canonical/preprocessing/EDA objects exist -> export package from UI -> train locally against remote MLflow -> confirm selected model is `challenger` with tags -> manually promote to `champion` -> run **Load champion model** -> verify Model Quality and Design Studio work.
