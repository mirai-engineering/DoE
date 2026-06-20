# Training Lifecycle Canonicalization Diagnosis

## Scope and evidence availability

This is the required pre-edit diagnosis for `plans/training-lifecycle-canonicalization-plan.md`.

Local shell inspection found `DATABASE_URL`, `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME`, and `MLFLOW_TRACKING_PASSWORD` unset in the current command environment, so live Railway Postgres/MLflow API evidence could not be queried from this shell without secret injection. The latest production run facts used below are therefore the already captured non-secret run metadata from the prior audit summary, and source-code traces are from the checked-out repo.

## Trace map

### Training request creation

- Route: `POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests` in `backend/app/main.py`.
- Service: `backend/app/services/training_requests.py::create_training_request(...)`.
- Preconditions: ingestion session exists; preprocessing report approval status is `approved_for_training`; model families are in `{mean_baseline,mvlr,ridge,mlp}`.
- State written: session-local JSON under `<session>/training_requests/{training_request_id}.json` with status `staged_for_mirai_execution`, MLflow registered model name, candidate alias `challenger`, and `champion_policy=manual_promotion_only`.
- Frontend: `frontend/src/components/PreprocessingReviewPage.tsx` creates the request after preprocessing approval.

### Railway start-training

- Route: `POST /data-intake/.../training-requests/{training_request_id}/start` in `backend/app/main.py`.
- Service: `backend/app/services/training_requests.py::start_training_request(...)`.
- Engine call: `train_generic_project(project_id=..., data_dir=<session>/canonical, artifact_dir=<session>/training_artifacts/latest, training_config=...)`.
- Input: `<session>/canonical/model_table.csv`; `<session>/training_artifacts/latest/schema.json`; `<session>/training_artifacts/latest/preprocessing.json`.
- Output: session `training_artifacts/latest` plus MLflow artifacts when MLflow is enabled.
- Canonical DB: `create_training_run(...)` then `complete_training_run(...)`.
- Current gap: `complete_training_run(...)` inserts/updates a `models` row as `status='champion'` and `is_champion=true` whenever a model artifact URI is provided. This collapses candidate completion and champion approval.

### Local exported-package training

- CLI: `backend/ml_lifecycle/training/run_exported_package.py`.
- Required package: `training_manifest.json`, `schema.json`, `model_table.csv`.
- Local working layout: `backend/.local-training-runs/<timestamp>-<training_request_id>/canonical/model_table.csv` and `/artifacts/{schema,training_manifest,preprocessing}.json`.
- Engine call: same `train_generic_project(...)`.
- Remote requirement: `preflight_remote_mlflow()` fails closed unless `MLFLOW_TRACKING_URI` is remote http(s) and remote MLflow/artifact guard env vars are true.
- It intentionally does not write Railway Postgres. This is correct.

### MLflow run/model registration

- Engine code: `backend/ml_lifecycle/training/generic_tabular_doe/train.py::_log_generic_mlflow(...)`.
- Every candidate becomes an MLflow run with tags `candidate_role`/`lifecycle_role` set to `candidate` or `challenger`.
- Only selected best candidate is registered under `doe_surrogate_{project_id}` and assigned MLflow alias `challenger`.
- Registered model/version tags include `validation_status='pending_review'`, schema hashes, project/run identity tags.
- No code promotes `champion`; this must remain manual/operator-driven.

### External import

- Route: `POST /data-intake/.../training-requests/{training_request_id}/import-mlflow-run` in `backend/app/main.py`.
- Service: `backend/app/services/training_requests.py::import_external_mlflow_run(...)`.
- Verification: `backend/app/services/mlflow_registry.py::verify_external_mlflow_model_version(...)` checks registered model name, alias/version, MLflow run status, workspace/project/dataset/session/training_request tags, required artifacts, manifest identity, and non-empty source checksums.
- Additional check: `import_external_mlflow_run(...)` compares MLflow `training_manifest.source_checksums` to a freshly rebuilt approved training package manifest.
- Current gap: after verification it calls `complete_training_run(...)` with `model_artifact_uri`, which currently creates an active champion row. An imported `challenger` therefore becomes app-active without explicit champion reconciliation.

### Current approval UI

- Frontend: `frontend/src/components/PreprocessingReviewPage.tsx`.
- Shows export package and import MLflow run panels after preprocessing approval and training request creation.
- Current labels treat `trainingCompleted` as final completion and say “Model Quality is now available from the canonical Mirai training state.” There is no separate `Candidate ready for review` vs `Approved champion active` state and no explicit `Refresh approved model` action.

### Project listing

- Backend route: `/projects` in `backend/app/main.py` calls `project_registry.list_projects(...)`.
- Runtime projects come from Postgres through `control_plane.list_workspace_projects(...)` when enabled.
- Additional MLflow-only projects can be merged by `backend/app/services/project_registry.py` via registered model aliases, currently using `challenger` alias metadata.

### Model Quality

- Routes: `/projects/{project_id}/model-quality/*` in `backend/app/main.py`.
- Service: `backend/app/services/model_quality.py`.
- Current `_artifact_dir(...)` order: imported completed `training_runs.mlflow_run_id`, then latest intake session artifacts, then MLflow `challenger` alias, then packaged reference artifacts.
- Current active-model metadata labels source as `champion` if MLflow alias exists, otherwise `challenger`, otherwise `session artifact`, regardless of whether Mirai has reconciled the champion.
- This mixes canonical DB state, mutable aliases, and local/session artifacts.

### Design Studio

- Routes: `/projects/{project_id}/design-studio/*` in `backend/app/main.py`.
- Service: `backend/app/services/design_studio.py`.
- Prediction endpoints pass workspace to `predict_rows(...)`, but `get_design_studio_state(project_id)` currently calls `get_project_schema(project_id)` without workspace context.
- Design predictions call `prediction.predict_rows(...)`, which loads schema/preprocessing/model through `model_loader.py`.

### Serving selection

- Prediction route: `/projects/{project_id}/predict` -> `prediction.predict_rows(...)` -> `model_loader.get_model_bundle(...)` -> `project_registry.get_project_model_path(...)`.
- Current `mlflow_registry.download_production_onnx(...)` order: reconciled/imported runtime state if present, then mutable MLflow aliases `champion`, `challenger`, `baseline`, then Production stage.
- Current `project_registry._latest_project_artifact_dir(...)` order: latest ingestion artifacts, then imported MLflow artifacts, then `challenger` alias artifacts.
- Current serving can therefore resolve a mixture of DB champion/imported state, mutable MLflow aliases including `challenger`, and stale latest session artifacts.

## Latest local run evidence

Previously captured non-secret production audit facts:

```text
project_id: demo_ccm_degradation_cff1d4ae
workspace_id: fraunhofer
training_request_id: train_req_3363f05dc2
MLflow run ID: 85fa3553087141589115f987b8cfeaa4
registered model name: doe_surrogate_demo_ccm_degradation_cff1d4ae
version: 2
alias: challenger
model_name: mlp
run status: FINISHED
```

Prior DB audit before import showed:

```text
training_runs: newer incomplete Railway request train_req_52b2d80b0f, status=running, mlflow_run_id=null
models: 0 rows
schema_manifests: 0 rows
artifact_objects: raw_upload rows only
```

Expected serving source in that state was not canonical Mirai champion because no `models.is_champion=true` row existed. Current code could still fall back to mutable MLflow aliases or stale/session artifacts, which is exactly the ambiguity this plan removes.

## Root cause for `inputs: 0`, `outputs: 0`, `model quality: Pending`

Source-code trace:

- `ProjectHeader` renders input/output counts from `schema.inputs.length` and `schema.outputs.length` in `frontend/src/components/ProjectHeader.tsx`.
- It renders Model Quality `Pending` when `artifactStatus?.model_quality.available` is false.
- `artifact-status` builds `quality_status.available=false` when `model_quality.get_artifact_summary(project_id)` raises.
- `get_project_schema(project_id, workspace_id)` first uses Postgres runtime schema when `schema_manifests` exists, otherwise falls back to reference/session/artifact paths.
- In the prior production DB audit, `schema_manifests` had no rows and `models` had no rows. For the affected runtime project, this means there was no complete canonical schema/model-quality record for the app to render as active.
- Model Quality was pending because `model_quality._artifact_dir(...)` could not find complete canonical/imported quality artifacts for that project state; the previous backend error was `Model quality is not available yet for project_id=demo_ccm_degradation_cff1d4ae; train the uploaded project first`.

No exact live API payload can be captured from the current shell because auth/session secrets and production tokens are unavailable. The exact code path above explains the observed UI values: empty/missing authoritative schema -> zero count rendering; no complete quality artifact source -> `available=false` -> Pending.

## Current serving-source verification

Current code can resolve, in order depending on route:

1. DB runtime `champion_model` if `models.is_champion=true` and its metrics contain `mlflow_import.model_uri`/`run_id`.
2. Mutable MLflow aliases in `download_production_onnx(...)`: `champion`, then `challenger`, then `baseline`.
3. MLflow Production stage fallback.
4. Latest intake/session artifacts through `project_registry._latest_project_artifact_dir(...)`.
5. MLflow `challenger` alias artifacts for schema/preprocessing/model-quality.
6. Packaged reference artifacts for legacy/demo paths.

This violates the target behavior for runtime imported/local projects because a mutable `challenger` alias or stale session artifacts can influence serving/model-quality without explicit Mirai champion reconciliation.

## Required implementation conclusion

The focused fix is to split candidate import from champion activation:

- `import_external_mlflow_run(...)` should create/update a completed `training_runs` row and a reviewable candidate model/state, not `is_champion=true`.
- A new explicit reconciliation action should verify MLflow `champion` alias and required artifacts, require that the champion run was previously imported into canonical Mirai state, and only then write/update `models.is_champion=true`.
- Prediction/Design Studio serving should require reconciled champion state for runtime MLflow projects.
- Model Quality should explicitly choose candidate or champion canonical run artifacts, never arbitrary alias/session fallback.
