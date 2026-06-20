# Training Lifecycle Canonicalization Plan

## Context

Mirai must keep `backend/ml_lifecycle/` as the single shared preprocessing/training engine. The architecture is not two training pipelines; it is one generic lifecycle engine invoked through two adapters:

```text
Core engine:
  backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py
  backend/ml_lifecycle/training/generic_tabular_doe/train.py::train_generic_project(...)

Adapters:
  A. Railway: UI/API approved training request -> start_training_request(...) -> train_generic_project(...) in Railway
  B. Local/on-prem: export approved package -> run_exported_package.py -> train_generic_project(...) locally -> remote MLflow -> explicit Mirai import/reconciliation
```

The current gap is lifecycle state canonicalization: local exported-package training can create a remote MLflow challenger, but a local MLflow run alone must not activate the app. Mirai must explicitly verify/import the candidate into canonical `training_runs` / `models`-like state, then separately reconcile an operator-promoted MLflow `champion` before serving.

Initial code scan found existing pieces to reuse and harden:

- Training request creation/start/import/export: `backend/app/services/training_requests.py`
- Import verification: `backend/app/services/mlflow_registry.py::verify_external_mlflow_model_version(...)`
- Runtime canonical state: `backend/app/services/control_plane.py::{create_training_run, complete_training_run, get_project_runtime_state}`
- Serving/schema/model-quality resolution: `backend/app/services/project_registry.py`, `model_loader.py`, `prediction.py`, `design_studio.py`, `model_quality.py`
- Frontend training/import UI: `frontend/src/components/PreprocessingReviewPage.tsx`
- Frontend app schema propagation and pages: `frontend/src/App.tsx`, `ModelQualityPage.tsx`, `DesignStudioPage.tsx`, `ProjectHeader.tsx`

A key suspected bug from inspection: `complete_training_run(...)` currently creates/updates a `models` row with `status='champion'` and `is_champion=true` whenever `model_artifact_uri` is provided. That is suitable for a managed Railway training path only if Railway produces approved champion artifacts, but it is not correct for imported local `challenger` candidates. The plan below makes diagnosis the required first deliverable before edits, then narrows implementation to explicit candidate import and explicit champion reconciliation.

## Agent / Skill Mapping

Use agents/subagents where meaningful, but keep implementation coordinated by one lead to avoid competing source-of-truth changes.

| Role | Skills | Scope |
| --- | --- | --- |
| Lead lifecycle architect | repo-postgres-migrations, security-and-hardening, api-and-interface-design | Own diagnosis, final design, source-of-truth decisions, acceptance criteria |
| Backend lifecycle subagent | debugging-and-error-recovery, incremental-implementation, test-driven-development | Trace and implement backend control-plane, MLflow verification, reconciliation endpoint/service |
| Frontend UX subagent | frontend-ui-engineering, scientific-ui-clarity | Implement status labels/actions: awaiting import, candidate ready, approved champion active |
| Test/audit subagent | code-review-and-quality, test-driven-development, browser-testing-with-devtools where available | Add regression tests, inspect API responses, verify no cross-project state retention |
| Docs/operator subagent | documentation-and-adrs, shipping-and-launch | Update `docs/training_lifecycle.md` and operator how-to |

No subagent should delete `backend/ml_lifecycle/`, `generic_tabular_doe/`, `run_exported_package.py`, or historical fuel-cell modules in this task.

## Required Diagnosis Before Editing

Produce a root-cause report as the first implementation artifact. It must be based on code and live/local API/DB evidence where credentials are available; no speculation.

### Trace map to produce

Document every route/service/frontend component/table involved in:

- training request creation;
- Railway start-training;
- local exported-package training;
- MLflow run/model registration;
- `import_external_mlflow_run(...)`;
- current approval UI;
- project listing;
- Model Quality;
- Design Studio;
- model serving selection.

Minimum files to trace:

```text
backend/app/main.py
backend/app/schemas.py
backend/app/services/training_requests.py
backend/app/services/mlflow_registry.py
backend/app/services/control_plane.py
backend/app/services/project_registry.py
backend/app/services/model_loader.py
backend/app/services/model_quality.py
backend/app/services/design_studio.py
backend/app/services/prediction.py
backend/app/services/data_intake.py
backend/app/services/preprocessing_review.py
backend/db/migrations/002_runtime_control_plane.sql
frontend/src/lib/api.ts
frontend/src/App.tsx
frontend/src/components/PreprocessingReviewPage.tsx
frontend/src/components/ModelQualityPage.tsx
frontend/src/components/DesignStudioPage.tsx
frontend/src/components/ProjectHeader.tsx
```

### Latest-run evidence to capture

For the latest local run, report:

```text
project_id
workspace_id
training_request_id
MLflow run ID
registered model name
version
alias
training_runs row
models row
UI training status
serving-selected model source
```

### Screenshot/API root cause to explain

Explain exactly why the app shows:

```text
inputs: 0
outputs: 0
model quality: Pending
```

Required evidence:

- exact `/projects` and `/projects/{project_id}/schema` API responses for the affected project/workspace;
- frontend state path that renders input/output counts and Model Quality status;
- backend source selected for schema/model-quality artifacts;
- DB/MLflow/source-state mismatch, if present.

### Serving-source verification

Verify whether current app serving resolves:

- MLflow `champion`;
- MLflow `challenger`;
- a DB-approved/champion model;
- stale local/session artifacts;
- or a mixture.

Pay special attention to these current fallback paths:

```text
backend/app/services/mlflow_registry.py::download_production_onnx(...)
  currently checks imported runtime state, then champion, challenger, baseline, Production

backend/app/services/project_registry.py::_latest_project_artifact_dir(...)
  currently can prefer latest ingestion artifacts before imported MLflow artifacts and alias artifacts

backend/app/services/model_quality.py
  currently has alias/session artifact source labels and fallbacks
```

## Approach

### Canonical lifecycle states

Introduce or clarify these effective states without adding a second training pipeline:

```text
approved preprocessing
  -> training request created
  -> execution pending
  -> execution completed in Railway OR external MLflow candidate imported
  -> candidate ready for review
  -> MLflow champion manually promoted by operator
  -> Mirai champion reconciled
  -> approved champion active
```

Use canonical Mirai state for app-serving decisions. MLflow is the remote experiment/model registry, but Mirai serving must use only a reconciled champion record.

### Backend design

1. Split candidate completion from champion activation.
   - Do not let imported `challenger` create `models.is_champion=true`.
   - Add or reuse control-plane functions so imported local runs create a completed `training_runs` row and a reviewable candidate model/state, but not active serving state.
   - If schema migration is needed, make it minimal and backwards compatible, e.g. `models.status in ('candidate','champion','archived')`, `is_champion=false` for candidates.

2. Harden `import_external_mlflow_run(...)` instead of adding a parallel mechanism.
   - Keep validation of workspace/project/dataset/session/training request identity.
   - Keep source checksum comparison against the approved exported package.
   - Keep required artifacts: `schema.json`, `preprocessing.json`, `metrics_summary.json`, `candidate_comparison.csv`, `predictions.csv`, `training_manifest.json`.
   - Record imported candidate status as `candidate_ready_for_review` or equivalent.

3. Add one explicit champion reconciliation action.
   - Candidate endpoint name:
     ```text
     POST /projects/{project_id}/models/refresh-approved-champion
     ```
     or a data-intake/operator route under the existing training request, whichever fits current auth patterns best.
   - It must resolve registered model for project, verify MLflow `champion` alias, verify workspace/project tags, verify artifact completeness, verify model version/run, and then update canonical Mirai model record as active champion.
   - It must not promote challenger based on metrics.
   - It must fail closed when alias/tags/artifacts are missing.

4. Remove competing serving fallbacks for active model selection.
   - Design Studio and prediction serving must use the reconciled champion record only.
   - Model Quality must use the selected imported/reconciled run, not arbitrary latest session artifacts or another project’s aliased run.
   - Project schema for active app views should come from the champion/candidate canonical source appropriate to the page state, not stale fallback artifacts.

5. Preserve review visibility for candidates.
   - Challenger imported but no champion: UI shows `Candidate ready for review`.
   - Model Quality may show candidate artifacts for review if complete, explicitly labeled as candidate/review, not active champion.
   - No imported local run: UI shows `Awaiting local-run import`.
   - Champion reconciled: UI shows `Approved champion active` and schema inputs/outputs come from champion authoritative schema.

### Frontend design

1. Update `PreprocessingReviewPage.tsx` to distinguish:
   - awaiting local-run import;
   - imported candidate ready;
   - champion refresh/reconcile available;
   - approved champion active.

2. Add a small operator-only/authorized action for `Refresh approved model` after MLflow alias promotion.

3. Ensure project switching clears or refetches schema/model-quality/design-studio state so prior project schema/model cannot leak into the next project view.

4. Ensure counts shown in `ProjectHeader`/schema cards derive from the current project’s authoritative API response only.

## Files to Modify

Expected minimal changed files:

```text
backend/app/main.py
backend/app/schemas.py
backend/app/services/control_plane.py
backend/app/services/training_requests.py
backend/app/services/mlflow_registry.py
backend/app/services/project_registry.py
backend/app/services/model_loader.py
backend/app/services/model_quality.py
backend/app/services/design_studio.py
backend/app/services/prediction.py
backend/db/migrations/00X_candidate_champion_lifecycle.sql   # only if needed
frontend/src/lib/api.ts
frontend/src/App.tsx
frontend/src/components/PreprocessingReviewPage.tsx
frontend/src/components/ModelQualityPage.tsx
frontend/src/components/DesignStudioPage.tsx
frontend/src/components/ProjectHeader.tsx
docs/training_lifecycle.md
backend/tests/test_*.py
frontend tests only if existing test setup supports them
```

Files/directories explicitly retained:

```text
backend/ml_lifecycle/
backend/ml_lifecycle/ingesting/generic_tabular_doe/
backend/ml_lifecycle/training/generic_tabular_doe/
backend/ml_lifecycle/training/run_exported_package.py
backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/
backend/ml_lifecycle/training/fuel_cell_doe_demo/
backend/ml_lifecycle/entrypoints/*real_fuel_cell*
```

## Reuse

Reuse existing code rather than creating new discovery paths:

```text
backend/app/services/training_requests.py::create_training_request
backend/app/services/training_requests.py::start_training_request
backend/app/services/training_requests.py::build_approved_training_package
backend/app/services/training_requests.py::import_external_mlflow_run
backend/app/services/mlflow_registry.py::verify_external_mlflow_model_version
backend/app/services/mlflow_registry.py::download_run_artifacts
backend/app/services/mlflow_registry.py::registered_model_name_for_project
backend/app/services/control_plane.py::get_project_runtime_state
backend/app/services/control_plane.py::create_training_run
backend/app/services/control_plane.py::complete_training_run, or refactor into candidate/champion-specific helpers
backend/ml_lifecycle/training/generic_tabular_doe/train.py::train_generic_project
backend/ml_lifecycle/training/run_exported_package.py
```

## Steps

- [ ] Phase 0: Diagnosis/report only.
  - [ ] Produce trace map for routes/services/frontend/tables listed above.
  - [ ] Query latest local MLflow run and canonical DB state where credentials are available.
  - [ ] Capture exact API responses explaining `inputs: 0`, `outputs: 0`, `model quality: Pending`.
  - [ ] Verify active serving source and all fallback paths.
  - [ ] Present root-cause report before broad edits.

- [ ] Phase 1: Define canonical lifecycle contract.
  - [ ] Document allowed states and transitions.
  - [ ] Decide whether existing `models` table can represent candidates or whether a minimal migration is needed.
  - [ ] Define API response shape for lifecycle status.

- [ ] Phase 2: Backend candidate import hardening.
  - [ ] Refactor `complete_training_run(...)` or add new control-plane helpers so candidate import does not mark `is_champion=true`.
  - [ ] Update `import_external_mlflow_run(...)` to create/update completed training run plus reviewable candidate state.
  - [ ] Preserve MLflow identity/artifact/checksum verification.

- [ ] Phase 3: Champion reconciliation.
  - [ ] Add service function to resolve and verify MLflow `champion` alias for the project/workspace.
  - [ ] Add operator-safe endpoint/action to reconcile champion into canonical Mirai state.
  - [ ] Update canonical `models` row only after alias/tag/artifact checks pass.

- [ ] Phase 4: Serving and artifact source canonicalization.
  - [ ] Make Design Studio and prediction serving require reconciled champion state.
  - [ ] Make Model Quality choose the imported candidate or reconciled champion explicitly, never arbitrary latest session/alias fallback.
  - [ ] Remove or demote broad alias fallback logic that can activate `challenger` as serving source.
  - [ ] Ensure schema/preprocessing/model binary/predictions all come from the same selected canonical run/model.

- [ ] Phase 5: Frontend lifecycle UX.
  - [ ] Show `Awaiting local-run import` when approved request has no imported/completed run.
  - [ ] Show `Candidate ready for review` after verified challenger import.
  - [ ] Add `Refresh approved model` / reconcile action after manual MLflow champion promotion.
  - [ ] Show `Approved champion active` after reconciliation.
  - [ ] Ensure project switch invalidates prior schema/model-quality/design-studio state.

- [ ] Phase 6: Documentation.
  - [ ] Add `docs/training_lifecycle.md` with canonical lifecycle diagram.
  - [ ] Include operator how-to: export package -> local train -> inspect MLflow -> promote champion -> refresh/reconcile in Mirai.
  - [ ] Mark historical fuel-cell entrypoints as later cleanup candidates only.

- [ ] Phase 7: Tests and validation.
  - [ ] Add focused backend tests for import/champion/source-selection behavior.
  - [ ] Add frontend/API contract tests where available for status labels and project switching.
  - [ ] Run focused backend tests and frontend build.

## Verification

Required tests/proofs:

- [ ] Local MLflow run alone does not become active automatically.
- [ ] Imported challenger appears as reviewable candidate.
- [ ] Champion promotion plus reconciliation activates the correct model.
- [ ] Wrong project/workspace MLflow model cannot be imported or reconciled.
- [ ] Missing required artifact prevents import/reconciliation.
- [ ] Model Quality receives the selected candidate/champion schema and predictions from the same run.
- [ ] Design Studio receives champion schema/defaults only after champion reconciliation.
- [ ] Switching project cannot retain prior schema/model state.
- [ ] Existing Railway managed training path still uses `train_generic_project(...)` and writes canonical records correctly.
- [ ] Existing local exported-package training still requires remote MLflow and does not require local S3 credentials.

Suggested commands after implementation:

```bash
cd backend && uv run pytest \
  tests/test_local_exported_package_training.py \
  tests/test_training_mlflow_contract.py \
  tests/test_mlflow_durable_pointers.py \
  tests/test_design_studio_contract.py \
  tests/test_api.py

cd frontend && npm run build
```

Manual/operator verification:

```text
1. Approve preprocessing and create training request.
2. Export package.
3. Run local training with remote MLflow.
4. Confirm MLflow selected model alias is challenger.
5. Import MLflow run in Mirai.
6. Confirm UI shows Candidate ready for review, not active champion.
7. Promote intended version to champion in MLflow.
8. Click Refresh approved model / call reconcile endpoint.
9. Confirm UI shows Approved champion active.
10. Confirm schema counts, Model Quality, Design Studio, and prediction serving all use the reconciled champion run/model.
```

## Out of Scope

- No deletion of `backend/ml_lifecycle/`.
- No deletion of historical fuel-cell modules in this task.
- No automatic champion selection or metric-based promotion.
- No direct local writes to Railway Postgres from local training.
- No new broad model-discovery fallback.
- No hardcoded Fraunhofer/fuel-cell variable names, project IDs, or artifact paths.
- No weakening of workspace/project authorization.
