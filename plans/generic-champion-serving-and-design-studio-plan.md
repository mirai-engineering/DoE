# Generic Champion Serving and Design Studio MVP Plan

## Context

The pilot should support a variable Mirai pipeline where each uploaded project defines its own inputs, outputs, labels, ranges, and metadata. The user-visible lifecycle should stay simple:

`upload Mirai contract -> approve metadata/preprocessing -> create training request -> train with remote MLflow -> load approved champion model -> Model Quality + Design Studio serve only the champion`

The current live state exposed two ambiguities:

- MLflow can show `champion` alias while Mirai serving state still has only a candidate model row, so Design Studio fails with “No reconciled Mirai champion model found.”
- Model Quality can load training-run prediction artifacts while the project schema state is incomplete, causing blank output selectors/plots.

User decisions captured in `docs/answers.md` and follow-up:

- The single user-visible activation action is **Load champion model**.
- The imported MLflow run must already be the approved `champion`; no separate reconciliation concept/button in the UI.
- Champion activation must verify identity/artifacts, ensure ONNX serving is available, persist Mirai canonical champion state, and unlock inference in the same action.
- Mirai approved schema is the UI/validation source of truth; MLflow `schema.json` is training evidence and may backfill missing runtime schema after compatibility checks.
- Model Quality uses static `predictions.csv` and split metrics; Design Studio uses the served champion for live deterministic predictions and overlays training points from `predictions.csv`.
- Remove scientist review UX and fuel-cell-specific UI/hardcoding. `generic_tabular_doe` is the only live path; uploaded ZIPs should already be Mirai contract packages.
- App-dev-only workflow steps may remain visible in the pilot with small “App dev step” hints.

## Approach

Implement a single generic champion-loading flow that replaces candidate import + hidden refresh/reconciliation with one explicit app-dev action: **Load champion model**.

Backend behavior:

1. Verify the requested MLflow run/model is the project’s `champion` alias.
2. Require complete training artifacts: `schema.json`, `preprocessing.json`, `metadata.json`, `metrics_summary.json`, `candidate_comparison.csv`, `predictions.csv`, and `training_manifest.json`.
3. Require an ONNX model in the MLflow model artifact for serving. If the training pipeline currently registers sklearn artifacts only, update training/export registration so the selected champion model is converted to/stored as ONNX before activation. Serving fails closed if no ONNX is available.
4. Backfill/repair Mirai runtime state in one transaction-like service operation:
   - completed `training_runs` row,
   - active `models` champion row (`is_champion=true`),
   - approved/runtime `schema_manifests` row when missing,
   - durable artifact pointers/cache metadata for MLflow artifacts and ONNX model.
5. Clear model/registry caches so the next prediction request resolves the new champion.

Frontend behavior:

1. Rename UI action/copy from “import candidate / refresh approved champion / reconciliation” to **Load champion model**.
2. Accept only approved champion runs for the app-dev import panel.
3. Show separate but simple states only when useful:
   - `Champion loaded` when Mirai serving is active.
   - Clear error/CTA when MLflow champion exists but Mirai activation failed.
4. Remove scientist review card/actions.
5. Add “App dev step” hint badges for preprocessing approval, training package/export/import, and champion loading.
6. Keep Model Quality as training evidence: candidate metrics table, champion-specific metrics, split diagnostics, static prediction diagnostics.
7. Make Design Studio generic: choose X, choose Y output(s), flip axes, choose/fix remaining variables, choose scan range/point count, run served champion predictions, overlay training points from `predictions.csv`, optionally color/group by metadata columns declared/present.
8. Hide fuel-cell/per-cell controls unless a project metadata plot recipe explicitly declares them; remove hardcoded fuel-cell presets from generic projects.

## Files to modify

Backend:

- `backend/app/services/training_requests.py`
  - Replace/extend external MLflow import + champion reconciliation into one `load_champion_model` style service.
  - Keep lower-level helpers if useful, but remove separate user-facing candidate/reconciliation state from the normal path.
- `backend/app/services/mlflow_registry.py`
  - Tighten champion verification.
  - Require ONNX model for production serving.
  - Ensure artifact download/cache includes model artifact and predictions.
- `backend/app/services/control_plane.py`
  - Add/update schema-manifest upsert helper if one does not already exist.
  - Ensure champion activation writes canonical runtime rows consistently.
- `backend/app/services/project_registry.py`
  - Make runtime schema resolution prefer approved/backfilled schema and avoid pending schema after champion load.
- `backend/app/services/model_loader.py`
  - Ensure serving only resolves Mirai champion ONNX artifacts for authenticated runtime projects.
- `backend/app/services/prediction.py`
  - Keep deterministic champion-only prediction path; no candidate fallback.
- `backend/app/services/model_quality.py`
  - Keep static `predictions.csv` diagnostics; ensure schema/output labels are resolved from Mirai schema and fallback safely to MLflow schema only during repaired/backfilled states.
- `backend/app/services/design_studio.py`
  - Remove fuel-cell-specific assumptions from generic state/prediction payloads.
  - Add generic training-overlay data from `predictions.csv` and metadata-column grouping options.
- `backend/app/main.py`
  - Replace/rename endpoint semantics from refresh/reconcile to load champion model, or keep old endpoint as backwards-compatible alias with new response/copy.
- `backend/ml_lifecycle/training/run_exported_package.py`
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py`
  - Ensure trained/selected champion-capable model artifacts include ONNX in MLflow model registration.
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/*`
  - Keep Mirai contract path as the only live ingestion path.
- Remove or quarantine fuel-cell-only ingestion/demo paths once tests prove Mirai contract ZIPs do not depend on them.

Frontend:

- `frontend/src/components/PreprocessingReviewPage.tsx`
  - Replace import/refresh flow with one **Load champion model** app-dev step.
  - Add app-dev badges/hints.
- `frontend/src/components/ModelQualityPage.tsx`
  - Remove scientist review card/actions.
  - Clarify champion loaded/serving status.
  - Fix output selector/plot behavior for variable outputs.
- `frontend/src/components/DesignStudioPage.tsx`
  - Remove/hide fuel-cell-specific controls for generic projects.
  - Add generic overlay controls and metadata grouping.
- `frontend/src/lib/api.ts`
  - Rename/add API client methods and response types for champion loading and generic Design Studio overlay data.

Tests/docs:

- `backend/tests/test_training_lifecycle_canonicalization.py`
- `backend/tests/test_training_mlflow_contract.py`
- `backend/tests/test_local_exported_package_training.py`
- `backend/tests/test_runtime_project_schema.py`
- `backend/tests/test_design_studio_contract.py`
- `backend/tests/test_generic_contract_pipeline.py`
- Add/adjust frontend/unit tests if available for lifecycle UI states.
- `docs/training_lifecycle.md`
- `docs/local_training_remote_mlflow_quickstart.md`
- `docs/tutorials/MIRAI_CONTRACT_INTAKE_TO_TRAINING_FLOW.md`

## Reuse

Existing code to reuse/refactor rather than rewrite:

- `backend/app/services/training_requests.py`
  - `import_external_mlflow_run()` for identity/artifact verification and training-run completion.
  - `reconcile_champion_model()` for champion row activation logic; rename/merge into load champion flow.
- `backend/app/services/mlflow_registry.py`
  - `verify_champion_mlflow_model()` for alias/identity checks.
  - `download_run_artifacts()` for schema/preprocessing/quality/predictions cache.
  - `download_production_onnx()` / `_model_file_from_cache()` for serving artifact resolution, with stricter ONNX requirement.
- `backend/app/services/control_plane.py`
  - `complete_training_run()`
  - `record_candidate_model()` if still needed internally for audit/history
  - `activate_champion_model()` for canonical champion row writing.
- `backend/app/services/model_quality.py`
  - `_prediction_path()` and `get_predictions()` for static diagnostics from `predictions.csv`.
- `frontend/src/components/DesignStudioPage.tsx`
  - Existing dynamic plot recipe builder, axis flip, multi-output series, sweep point count, objective weights, and optimization workflow.
- `frontend/src/components/ModelQualityPage.tsx`
  - Existing candidate comparison table and prediction diagnostics plots, but remove scientist review and hardcoded domain wording.

## Skills / agents / subagents to use

Use these as execution aids where they reduce ambiguity; do not let them replace the implementation checklist above.

- **Primary implementation owner**: main coding agent in repo context.
  - Best for cross-cutting edits across backend services, frontend lifecycle UI, tests, and docs.
  - Keep one owner for the final patch to avoid lifecycle/terminology drift.

- **`surrogate-model-debugging` skill**
  - Use for ONNX conversion/registration, model artifact layout, and serving-cache validation.
  - Relevant files: `backend/ml_lifecycle/training/generic_tabular_doe/train.py`, `backend/ml_lifecycle/training/run_exported_package.py`, `backend/app/services/model_loader.py`, `backend/app/services/prediction.py`.

- **`querying-mlflow-metrics` / `searching-mlflow-docs` / `mlflow-onboarding` skills**
  - Use for MLflow registry alias behavior, artifact download semantics, model URI handling, and ONNX artifact registration details.
  - Relevant files: `backend/app/services/mlflow_registry.py`, `backend/app/services/training_requests.py`, `docs/mlflow_remote_access.md`, `docs/training_lifecycle.md`.

- **`repo-postgres-migrations` skill**
  - Use if schema-manifest or model-row persistence requires a DB migration or seed update.
  - Confirm whether existing `schema_manifests`, `training_runs`, and `models` tables already support the champion-load contract before adding migrations.
  - Relevant files: `backend/db/migrations/*`, `backend/app/services/control_plane.py`, `backend/app/services/project_registry.py`.

- **`frontend-ui-engineering` skill**
  - Use for simplifying lifecycle UI copy, adding “App dev step” badges, removing scientist-review UI, and keeping Design Studio interactions clear.
  - Relevant files: `frontend/src/components/PreprocessingReviewPage.tsx`, `frontend/src/components/ModelQualityPage.tsx`, `frontend/src/components/DesignStudioPage.tsx`, `frontend/src/lib/api.ts`.

- **`scientific-ui-clarity` skill**
  - Use for variable labels, plot wording, split-vs-design-space separation, and avoiding domain-specific assumptions in generic plots.
  - Relevant files: `frontend/src/components/ModelQualityPage.tsx`, `frontend/src/components/DesignStudioPage.tsx`, `backend/app/services/model_quality.py`, `backend/app/services/design_studio.py`.

- **`test-driven-development` skill**
  - Use to define regression tests before broad refactors, especially for champion-load invariants and fail-closed serving.
  - Target tests: `backend/tests/test_training_lifecycle_canonicalization.py`, `backend/tests/test_training_mlflow_contract.py`, `backend/tests/test_runtime_project_schema.py`, `backend/tests/test_design_studio_contract.py`, `backend/tests/test_generic_contract_pipeline.py`.

- **`code-review-and-quality` skill or review subagent**
  - Use after implementation to review for leftover reconciliation/scientist-review/fuel-cell terminology, accidental candidate fallback, and overcomplicated branching.
  - Focus areas: service boundaries, naming, cache invalidation, auth/tenant scoping, and frontend copy consistency.

- **`security-and-hardening` skill**
  - Use for tenant isolation and fail-closed behavior: workspace/project checks, no cross-project MLflow model serving, no secret logging, no local MLflow fallback.
  - Relevant files: `backend/app/services/mlflow_registry.py`, `backend/app/services/model_loader.py`, `backend/app/services/training_requests.py`, `backend/app/auth.py`.

- **`browser-testing-with-devtools` skill**
  - Use only after code is deployed/running to manually verify the live pilot flow and UI states.
  - Confirm authenticated app behavior: upload -> preprocessing -> training request -> load champion -> Model Quality -> Design Studio.

- **`use-railway` skill / Railway subagent**
  - Use only for deployment/log inspection after local tests pass.
  - Avoid exposing secrets. Use direnv-compatible workflows and Railway service IDs already documented in session context.
  - Note: global executable `use-railway@1.3.0` currently wins over repo skill `1.2.6`; prefer the global executable if delegating.

- **Suggested subagent fanout during implementation**
  - Backend scout: inspect persistence, MLflow, ONNX, and schema-manifest paths before edits.
  - Frontend scout: inventory lifecycle, Model Quality, and Design Studio hardcoded domain UI before edits.
  - Test scout: map existing tests to required new assertions and identify minimal regression additions.
  - Final review subagent: check for deleted/renamed UX concepts (`reconciliation`, `scientist review`, `candidate review`) and fail-closed serving guarantees.

## Steps

- [ ] Define the new backend service contract: `load_champion_model(workspace_id, project_id, mlflow_run_id?, registered_model_name?, model_version?, notes?)`.
- [ ] Make `Load champion model` verify that the selected/entered MLflow run is the current `champion` alias for `doe_surrogate_<project_id>` and matches workspace/project/training request identity.
- [ ] Require ONNX in the MLflow model artifact for serving; update the generic training pipeline to export/register ONNX for the selected model if it does not already.
- [ ] Download/cache champion artifacts: schema, preprocessing, metadata, metrics, candidate comparison, predictions, manifest, and ONNX model.
- [ ] Upsert runtime `schema_manifests` from the approved Mirai schema or MLflow `schema.json` when the DB row is missing, preserving Mirai labels/roles/ranges as UI source of truth.
- [ ] Upsert `training_runs` and active `models` champion row in the same service path; ensure no candidate-only state remains blocking serving.
- [ ] Clear model/registry caches after champion activation.
- [ ] Replace frontend “Import MLflow run” + “Refresh approved model” copy and controls with a single **Load champion model** app-dev step.
- [ ] Remove “reconciliation” wording from UI and docs.
- [ ] Remove scientist review card/actions and related client calls from Model Quality.
- [ ] Fix Model Quality output dropdown and plots so they are driven by variable schema outputs and static `predictions.csv`; show actionable errors when outputs are missing.
- [ ] Refactor Design Studio generic plot controls: X variable, Y output(s), axis flip, fixed inputs, scan range, point count, metadata grouping, training-data overlay from `predictions.csv`.
- [ ] Hide/remove hardcoded fuel-cell/per-cell UI for generic projects; only render domain-specific recipes declared by metadata.
- [ ] Require active champion for single predictions and batch candidate recommendations.
- [ ] Remove or quarantine fuel-cell extractor/adapter code after confirming the Fraunhofer ZIP is already a Mirai contract package and tests pass without those paths.
- [ ] Update docs/tutorials to describe the simplified app-dev vs user flow.

## Verification

Automated backend checks:

- [ ] `cd backend && uv run pytest tests/test_training_lifecycle_canonicalization.py -q`
- [ ] `cd backend && uv run pytest tests/test_training_mlflow_contract.py tests/test_local_exported_package_training.py -q`
- [ ] `cd backend && uv run pytest tests/test_runtime_project_schema.py tests/test_design_studio_contract.py tests/test_generic_contract_pipeline.py -q`
- [ ] Add a regression test proving `Load champion model` creates/updates:
  - completed training run,
  - active champion model row,
  - schema manifest when missing,
  - ONNX-serving artifact/cache,
  - static prediction diagnostics availability.
- [ ] Add a regression test proving prediction and batch recommendation fail closed without active champion and pass after champion load.
- [ ] Add a regression test proving Model Quality can plot variable outputs from `predictions.csv` using schema labels.

Frontend/build checks:

- [ ] `cd frontend && npm run build`
- [ ] If test tooling exists, add/run component tests for:
  - no scientist review card,
  - **Load champion model** CTA states,
  - generic Design Studio plot controls,
  - no fuel-cell controls for generic projects.

Manual/live pilot checks:

- [ ] Fresh upload of Mirai contract ZIP.
- [ ] Approve metadata/preprocessing and create training request.
- [ ] Export package and train locally with remote MLflow.
- [ ] Promote selected model version to `champion` in MLflow.
- [ ] In Mirai, click **Load champion model** once.
- [ ] Confirm artifact/status shows active champion and schema outputs.
- [ ] Confirm Model Quality shows all-model metrics, champion metrics, split diagnostics, and populated prediction plots.
- [ ] Confirm Design Studio predicts with the served champion, overlays training points from `predictions.csv`, supports axis flip/range/fixed inputs/grouping, and batch recommendations require active champion.
- [ ] Confirm no separate reconciliation/scientist-review/fuel-cell-specific UI appears for generic projects.
