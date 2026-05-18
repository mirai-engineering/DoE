# Fuel-Cell Upload → Preprocessing → Training Automation Plan

## Context

The Data Intake MVP now creates local ingestion sessions, stores uploaded files, computes checksums, generates lightweight EDA/preprocessing reports, supports Mirai-admin approval, and creates reviewed training request specs. For the real PEM fuel-cell validation package, the next step is to make the UI path operational end-to-end enough to validate:

1. upload `data_overview.xlsx`, `Cell_*.zip`, `mirai_manifest_template.json`, and `data_dictionary_template.csv`,
2. unpack/copy the raw package into a preprocessing workspace,
3. run the existing real fuel-cell raw-data transformer to produce canonical CSV artifacts,
4. require Mirai-admin approval before training,
5. launch the existing real fuel-cell trainer from the approved request,
6. show progress/status in the UI and direct the user to Model Quality when complete.

This should remain explicitly **fuel-cell package automation**, not generalized arbitrary-data AutoML.

## Current Findings

- `backend/app/services/data_intake.py` stores uploads under `backend/data/intake/projects/.../raw` and records uploaded files in `session.json` plus `inventory/file_inventory.json`.
- `backend/app/services/preprocessing_review.py` currently profiles uploaded CSV/XLSX files but does not unpack zip archives or call the fuel-cell transformation pipeline.
- `backend/app/services/training_requests.py` creates request specs and blocks them until `approval.status == approved_for_training`, but it does not execute training.
- `frontend/src/components/DataIntakePage.tsx` creates an ingestion session and displays IDs, but does not pass/select the active session for the Preprocessing Review page.
- `frontend/src/components/PreprocessingReviewPage.tsx` is mostly static; it needs session selection, action buttons, status cards, and training execution feedback.
- `backend/training/real_data_pipeline/build_real_fuel_cell_dataset.py` already supports custom `BuildPaths` internally and CLI `--output`, but default raw input paths point to repo-local `data/Cathode Catalyst Degradation`.
- `backend/training/real_data_pipeline/preprocess_real_fuel_cell.py` accepts `data_dir` and `artifact_dir` parameters, but the training pipeline currently calls preprocessing with defaults.
- `backend/training/real_training_pipeline/train_real_fuel_cell_models.py` now accepts dataset/session/training request IDs for MLflow tags, but still supports only the existing real fuel-cell `PROJECT_ID`.

## Approach

Implement a constrained, auditable fuel-cell intake runner with synchronous MVP execution and clear status artifacts. The runner should unpack uploaded `Cell_*.zip` archives into a session workspace that mimics the existing expected raw layout, copy `data_overview.xlsx`, run the existing canonical CSV builder, generate preprocessing artifacts, wait for admin approval, then allow an explicit training-launch button to run MVLR/MLP training with MLflow tags.

Recommended MVP boundary:

- **Start preprocessing** can run after upload/mapping review and should unpack/canonicalize/profile the raw fuel-cell package.
- **Approve preprocessing** remains an explicit admin action after generated artifacts are visible.
- **Start training** should only be enabled after approval.
- Training may run synchronously for the MVP, with a long-running button/spinner and status JSON; if it proves too slow or blocks the API, move to a background task in the same implementation.
- The trained served model can still register under the existing MLflow registered model name initially, with uploaded `project_id`, `dataset_id`, `ingestion_session_id`, and `training_request_id` as tags. A later plan can generalize registered model names per uploaded project.

## Files to modify

Backend:

- `backend/app/services/data_intake.py` — add helper functions for session paths and safe zip extraction inventory.
- `backend/app/services/preprocessing_review.py` — add fuel-cell package preprocessing runner that unpacks zips, builds canonical CSV artifacts, writes status/progress/artifact paths, and merges results into preprocessing report.
- `backend/app/services/training_requests.py` — add training execution status and execution function that invokes the existing real fuel-cell trainer after approval.
- `backend/app/main.py` — add endpoints for preprocessing start/status, approval, training request creation, training execution, and training status as needed.
- `backend/app/schemas.py` — add request/response models for package type, preprocessing execution, and training execution.
- `backend/training/real_training_pipeline/train_real_fuel_cell_models.py` — if needed, accept precomputed `data_dir`/`artifact_dir` from a session so training uses uploaded-session artifacts instead of default global artifacts.
- `backend/training/real_data_pipeline/build_real_fuel_cell_dataset.py` — reuse `BuildPaths`; add/import helper if current API cannot cleanly accept session raw paths.

Frontend:

- `frontend/src/lib/api.ts` — add clients and types for session listing, preprocessing start/status/report, approval, training request creation, training execution/status.
- `frontend/src/components/DataIntakePage.tsx` — after upload, provide a clear `Go to Preprocessing Review` affordance and persist the latest session selection locally.
- `frontend/src/components/PreprocessingReviewPage.tsx` — replace static cards with session-driven workflow: select latest session, start preprocessing, show artifacts/counts/warnings, approve preprocessing, create/start training request, and link to Model Quality.

Tests/docs:

- `backend/tests/test_api.py` — add API tests for fuel-cell upload session lifecycle with tiny/mock zip/workbook fixtures where feasible.
- `backend/tests/test_real_fuel_cell_data_pipeline.py` — add or adapt integration coverage for session workspace preprocessing/training metadata tags, avoiding a full expensive retrain unless already covered.
- `docs/tutorials/TAILORED_ML_MODEL_DATA_INTAKE.md` — add upload package and click-path instructions.

## Reuse

- Existing ingestion session storage/checksum model: `backend/app/services/data_intake.py`.
- Existing preprocessing approval model: `backend/app/services/preprocessing_review.py`.
- Existing training request gate: `backend/app/services/training_requests.py`.
- Existing canonical fuel-cell CSV builder: `backend/training/real_data_pipeline/build_real_fuel_cell_dataset.py` (`BuildPaths`, `build_all_cells`).
- Existing fuel-cell preprocessing artifacts: `backend/training/real_data_pipeline/preprocess_real_fuel_cell.py` (`build_preprocessing_artifacts`).
- Existing trainer and MLflow lifecycle: `backend/training/real_training_pipeline/train_real_fuel_cell_models.py`.
- Existing frontend premium card styles in `DataIntakePage.tsx`, `PreprocessingReviewPage.tsx`, and `ModelQualityPage.tsx`.

## Steps

- [x] Add backend session workspace helpers for `raw/`, `extracted/`, `canonical/`, `training_artifacts/`, `runs/`, and status JSON files.
- [x] Add safe zip extraction for uploaded `Cell_*.zip` archives: prevent path traversal, skip macOS metadata, preserve `Cell_NN/...` layout, and record extracted file counts/checksums.
- [x] Add fuel-cell package detector/validator: require `data_overview.xlsx` and at least one `Cell_*.zip`; mark missing/ambiguous package contents with actionable errors.
- [x] Implement `start_fuel_cell_preprocessing(project_id, dataset_id, session_id)`:
  - [x] copy workbook into expected session layout,
  - [x] extract cell archives into `extracted/01-Data/Cell_NN/...`,
  - [x] call `build_all_cells` with session-specific `BuildPaths`,
  - [x] run `build_preprocessing_artifacts(data_dir=session/canonical, artifact_dir=session/training_artifacts/latest)`,
  - [x] write preprocessing status/report with canonical artifact paths, row counts, rejected rows, split summary, and EDA links.
- [x] Keep Mirai-admin approval separate: generated preprocessing report status should be `preprocessing_complete_needs_approval`; training remains locked until approval.
- [x] Add backend endpoints for preprocessing execution/status if current report endpoint is insufficient, e.g. `POST .../preprocessing/start` and `GET .../preprocessing/status`.
- [x] Add training execution after approval:
  - [x] create request spec as today,
  - [x] add `POST .../training-requests/{training_request_id}/start`,
  - [x] run the existing trainer with uploaded `dataset_id`, `ingestion_session_id`, `preprocessing_report_id`, and `training_request_id` MLflow tags,
  - [x] write training status/result JSON and return Model Quality route.
- [x] Decide whether training uses session-specific canonical/preprocessing artifacts directly or copies approved artifacts into the existing packaged `backend/data/real/.../latest` location before training.
- [x] Wire frontend API clients for session listing, preprocessing start/status/report, approval, training request creation, and training start/status.
- [x] Update Data Intake UI to persist/show the latest uploaded session and offer `Review preprocessing`.
- [x] Rebuild Preprocessing Review UI around a session-driven checklist:
  - [x] uploaded package inventory,
  - [x] `Start preprocessing`,
  - [x] preprocessing artifacts/row counts/warnings,
  - [x] `Approve preprocessing`,
  - [x] `Create training request`,
  - [x] `Start training`,
  - [x] `Open Model Quality`.
- [x] Add tests for zip extraction safety, package validation, status transitions, approval gate, and training-start gate.
- [x] Verify with the real uploaded fuel-cell package and document exact click path.

## Verification

Backend:

```bash
cd backend
uv run pytest tests/test_api.py tests/test_real_fuel_cell_data_pipeline.py
```

Frontend:

```bash
cd frontend
npm run build
```

Manual end-to-end validation:

1. Start Docker Compose or local backend/frontend.
2. Open **Tailored ML Model → Data Intake**.
3. Upload `data_overview.xlsx`, `Cell_*.zip`, `mirai_manifest_template.json`, and `data_dictionary_template.csv`.
4. Click **Review preprocessing**.
5. Click **Start preprocessing**.
6. Confirm extracted/canonical artifacts appear, including `model_table.csv`, `dataset_profile.json`, `preprocessing_report.json`, and split/EDA artifacts.
7. Click **Approve preprocessing**.
8. Click **Create training request**.
9. Click **Start training**.
10. Confirm MLflow run tags include uploaded dataset/session/training request IDs and selected model alias remains `challenger` only.
11. Open **Model Quality** and verify metrics/diagnostics load.

## Open questions

1. Should uploaded-session training **overwrite/update the packaged runtime artifacts** (`backend/data/real/.../training_artifacts/latest` and `backend/artifacts/...`) so Model Quality immediately shows the new run, or should it remain isolated under the uploaded session and require a project registry update before serving?
2. For this MVP, is synchronous training acceptable from the UI button, or do you want a background job/status polling implementation immediately?
3. Should we support uploading the whole `Cathode Catalyst Degradation` folder as one zip and unpacking nested `01-Data/Cell_*.zip`, or is selecting `data_overview.xlsx` plus individual `Cell_*.zip` files enough for now?
