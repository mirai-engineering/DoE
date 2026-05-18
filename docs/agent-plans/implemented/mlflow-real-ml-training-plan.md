# MLflow Real ML Training Plan

## Context

The Phase 1 real-data pipeline now produces audited `Cell_01` CSV artifacts, including a paper-aligned `model_table.csv` with seven inputs and four outputs. The next step is to move from data assembly to professional ML engineering: preprocessing, EDA, train/validation/test splitting, model training, evaluation, MLflow tracking/registry, and scientist-facing model-quality visibility.

The user's intended product direction is:

- Scientists should see whether model training succeeded before trusting recommendations as replacements for costly experiments.
- Preprocessing should be inspectable: missingness, imputation, scaling, rejected rows, distribution shifts, train/val/test split summaries, and generated artifacts.
- MLflow should track training runs and register trained models.
- A future AI-agent preprocessing workflow should be anticipated but implemented only as placeholders for now.
- Human-in-the-loop scientist review should be part of the model lifecycle, especially around preprocessing outcomes and train/val/test accuracy.

## Current Codebase Findings

- `backend/training/train_mlp.py` trains the synthetic `pem_fuel_cell_demo` model and already has a small `_maybe_log_mlflow` stub, but MLflow is not a dependency yet.
- `backend/mlflow&BO-integration.md` already sketches MLflow tracking, registry, champion/challenger routing, and future model-stage handling.
- Runtime model loading currently expects local artifacts under `backend/artifacts/{project_id}/`: `schema.json`, `preprocessing.json`, `model.onnx`, and `metadata.json`.
- `backend/app/services/project_registry.py` discovers projects from local artifact directories and does not yet resolve MLflow model stages.
- Frontend currently has tabs for Batch Explorer, Batch Results, Batch Visuals, and Optimization Loop. There is no Model Training / Model Quality interface yet.
- `frontend/src/lib/api.ts` has typed API clients for projects, prediction, recommendations, and BO, but no training-run or model-registry client yet.
- Phase 1 generated real-data CSVs under `backend/data/real/pem_fuel_cell_cathode_degradation/`, but only from `Cell_01`; this is likely too small for meaningful train/val/test modeling by itself.

## Approach

Build this as an ML lifecycle layer rather than a one-off training script.

This next implementation is intentionally a **Cell_01 smoke MLOps workflow**. It validates the professional training, preprocessing, evaluation, MLflow, registry, and scientist-facing UI plumbing before scaling the dataset builder to all cells. Its model quality numbers must be labeled as smoke/demo quality, not final scientific evidence, because one cell cannot prove cross-cell generalization.

Resolved implementation choices:

1. Use `Cell_01` first; do not expand to all 42 cells in this step.
2. Use the easiest MLflow setup first: local file-based MLflow tracking/registry under an ignored backend path such as `backend/mlruns/`.
3. Register trained models in MLflow and update runtime loading so the API can load the MLflow `Production` model for the real project.
4. Evaluate regression quality with R², RMSE, and MAE, reported per output and per split.
5. Target grouped-by-`cell_id` splitting as the long-term standard. For the one-cell smoke workflow, use a lifecycle/cycle-aware validation strategy that holds out later cycle stages where available, and document that this must become true grouped-by-cell splitting once all cells are implemented.
6. Keep exactly the paper-aligned four outputs: `bol_current_density`, `eol_current_density`, `bol_ecsa`, and `ecsa_loss`.
7. Train and compare a focused first-pass model set: simple linear / MVLR baseline plus MLP. Defer XGBoost or other heavier models until the pipeline and UI are validated.
8. Add a new top-level scientist-facing Model Quality tab.
9. Store scientist review/feedback as local JSON for now.
10. Use a generic “AI preprocessing assistant” placeholder, not Pi-branded, for future agentic preprocessing.
11. Ignore generated model/preprocessing/MLflow artifacts in git for now.
12. Do not add Docker Compose MLflow in this first pass, but document it as an important near-term follow-up.

Recommended staged approach:

1. Keep the Phase 1 `Cell_01` CSV artifacts as the smoke dataset source.
2. Add a preprocessing pipeline that produces auditable preprocessing reports and deterministic transformed datasets.
3. Add a real-project training pipeline that creates a smoke train/validation/test split, logs EDA/preprocessing/model artifacts to MLflow, exports ONNX after evaluation, and registers a Production model in MLflow.
4. Update backend runtime loading so the real project can resolve the MLflow Production model while the synthetic demo still works from local artifacts.
5. Add backend API endpoints for listing training runs, model metrics, preprocessing reports, registered model versions, and local scientist feedback.
6. Add a scientist-facing frontend page for model quality and preprocessing review.
7. Add placeholders for future AI preprocessing proposals and real-time scientist feedback, but do not implement autonomous preprocessing yet.

## Files to modify

Likely backend files:

- `backend/pyproject.toml` — add MLflow, scikit-learn, pandas, and any minimal plotting/reporting dependency needed for artifacts. Do not add XGBoost in this first pass.
- `.gitignore` — ignore local MLflow/artifact/review state such as `backend/mlruns/`, model caches, and local scientist review JSON.
- `backend/training/build_real_fuel_cell_dataset.py` — reuse existing `Cell_01` model table; no all-cell expansion in this step.
- `backend/training/real_fuel_cell_schema.py` — real project schema, exact paper labels, and project ID.
- `backend/training/preprocess_real_fuel_cell.py` — new preprocessing/EDA/imputation/splitting pipeline.
- `backend/training/train_real_fuel_cell_models.py` — new real-data training/evaluation script for MVLR/simple linear regression and MLP.
- `backend/training/mlflow_utils.py` — local MLflow file-store tracking URI, experiment setup, artifact logging, registry helpers, and Production model resolution.
- `backend/app/schemas.py` — API models for training runs, metrics, preprocessing reports, model versions, and scientist review state.
- `backend/app/main.py` — endpoints for model-quality/registry visibility and local scientist review feedback.
- `backend/app/services/project_registry.py` — MLflow Production model resolution for the real project while preserving local artifact loading for the synthetic project.
- `backend/app/services/model_quality.py` — new service to read MLflow runs/reports and local review JSON for the UI.
- `backend/tests/` — tests for preprocessing artifacts, split integrity, MLflow logging/registry behavior, runtime loading, and API responses.

Likely frontend files:

- `frontend/src/types/doe.ts` — add a Model Quality / Training tab.
- `frontend/src/lib/api.ts` — client types/functions for training runs, metrics, preprocessing reports, model versions, and review feedback.
- `frontend/src/App.tsx` — route the new tab/page.
- `frontend/src/components/ModelQualityPage.tsx` — model accuracy dashboard.
- `frontend/src/components/PreprocessingReviewPage.tsx` or section inside `ModelQualityPage` — missingness/imputation/scaling/split report.
- `frontend/src/components/*` — charts/tables for metrics, residuals, per-output accuracy, preprocessing status, and model registry state.

Docs/config candidates:

- `docs/reference/REAL_FUEL_CELL_DATASET.md` — update with the smoke training/preprocessing workflow and its limitations.
- `docs/reference/MLFLOW_MODEL_LIFECYCLE.md` — document local MLflow tracking, registry, Production model loading, promotion, and scientist review flow.
- Do **not** modify `docker-compose.yml` in this step. Add a clear reminder that a Docker Compose MLflow server should be added soon.

## Reuse

- `backend/training/build_real_fuel_cell_dataset.py` for audited real-data CSV generation.
- `backend/training/train_mlp.py` for existing MLP architecture, scaling pattern, ONNX export flow, and MLflow stub.
- `backend/training/export_onnx.py` for verified ONNX export.
- `backend/scripts/model.py` for `TabularMLP`.
- `backend/app/services/preprocessing.py` for runtime min-max preprocessing conventions.
- `backend/app/services/project_registry.py` for local artifact discovery and future stage-aware routing.
- `backend/mlflow&BO-integration.md` for existing MLflow architecture notes.
- `.pi/skills/surrogate-model-debugging/SKILL.md` for feature order, scaling, target transform, and ONNX parity checks.
- `.pi/skills/scientific-ui-clarity/SKILL.md` for scientist-facing metric and uncertainty presentation.

## Steps

- [x] Add local-only MLflow/MLOps state handling: ignore `backend/mlruns/`, generated training artifacts, local model cache, and scientist review JSON.
- [x] Add minimal dependencies for this first pass: MLflow, pandas, scikit-learn, and any lightweight plotting/report dependency needed for static artifacts. Do not add XGBoost.
- [x] Define the Cell_01 smoke training contract: paper-aligned seven inputs, four outputs, exact labels, local artifact paths, and explicit “smoke only / not final scientific evidence” metadata.
- [x] Implement EDA/profiling over `Cell_01` model and diagnostic CSVs: missingness, ranges, duplicates, output distributions, rejected rows, source provenance, and leakage warnings.
- [x] Implement preprocessing: fit-only-on-train imputation, scaling, optional target scaling, saved preprocessing artifacts, and a readable preprocessing report.
- [x] Implement the smoke split: preserve grouped-by-`cell_id` as the future standard, but for one cell use a lifecycle/cycle-aware validation strategy with later-stage/cycle-derived rows emphasized in validation/test reporting. Clearly note this must change to true grouped-by-cell splitting when all cells are implemented.
- [x] Train MVLR/simple linear regression as the credibility baseline.
- [x] Train the MLP using the existing `TabularMLP`/ONNX export conventions.
- [x] Evaluate both models with R², RMSE, and MAE per output and per split; do not enforce hard scientific pass/fail thresholds in the one-cell smoke workflow.
- [x] Log all runs to local MLflow: params, metrics, source data hashes, preprocessing artifacts, plots/reports, model artifacts, ONNX, schema, and metadata.
- [x] Register the best smoke model as the MLflow `Production` model for the real project, while clearly labeling it as smoke/demo quality.
- [x] Update runtime loading so `pem_fuel_cell_real_cathode_degradation` resolves its MLflow `Production` model; preserve existing local artifact loading for `pem_fuel_cell_demo`.
- [x] Expose backend endpoints for model quality: latest runs, per-output metrics, preprocessing report, artifact summaries, active MLflow model metadata, and local scientist review JSON.
- [x] Add a new top-level Model Quality tab showing split metrics, model comparison, per-output accuracy, residual/error summaries, preprocessing summary, active model version, and scientist review status.
- [x] Add generic “AI preprocessing assistant” placeholders only: proposed transformations, rationale, pending review state, accept/reject affordance, and “not active yet” messaging.
- [x] Document the near-term Docker Compose MLflow server follow-up, but do not modify Docker Compose now.
- [x] Add tests covering preprocessing parity, split integrity notes, MLflow local logging/registry, runtime model resolution, API contracts, and frontend build.

## Verification

Backend commands should include:

```bash
cd backend
uv run python training/build_real_fuel_cell_dataset.py --cell-id Cell_01 --profile
uv run python training/preprocess_real_fuel_cell.py --project-id pem_fuel_cell_real_cathode_degradation --cell-id Cell_01
uv run python training/train_real_fuel_cell_models.py --project-id pem_fuel_cell_real_cathode_degradation --register-mlflow --promote-production
uv run pytest tests/test_real_fuel_cell_data_pipeline.py tests/test_api.py
```

Frontend commands should include:

```bash
cd frontend
npm run build
```

Manual checks:

- Local MLflow file store contains runs for MVLR/simple linear and MLP.
- MLflow shows params, R²/RMSE/MAE metrics, artifacts, and a registered Production model for the real project.
- API runtime can load the real project’s MLflow Production model while the synthetic demo still works.
- The app has a top-level Model Quality tab.
- The page clearly distinguishes train, validation, and test metrics and labels Cell_01 results as smoke/demo quality.
- Preprocessing report is visible and understandable.
- Scientist feedback is stored locally as JSON.
- Generic AI preprocessing assistant controls are visible as inactive placeholders only.
- No Docker Compose MLflow service is added in this pass; the follow-up is documented.

## Execution Evidence

Completed implementation artifacts:

```text
backend/training/preprocess_real_fuel_cell.py
backend/training/train_real_fuel_cell_models.py
backend/training/mlflow_utils.py
backend/app/services/mlflow_registry.py
backend/app/services/model_quality.py
frontend/src/components/ModelQualityPage.tsx
docs/reference/MLFLOW_MODEL_LIFECYCLE.md
```

Generated local-only ignored runtime artifacts include:

```text
backend/mlruns/
backend/.mlflow-cache/pem_fuel_cell_real_cathode_degradation/
backend/artifacts/pem_fuel_cell_real_cathode_degradation/
backend/data/real/pem_fuel_cell_cathode_degradation/training_artifacts/latest/
```

Verification commands executed:

```bash
cd backend && uv run python training/preprocess_real_fuel_cell.py --project-id pem_fuel_cell_real_cathode_degradation --cell-id Cell_01
cd backend && uv run python training/train_real_fuel_cell_models.py --project-id pem_fuel_cell_real_cathode_degradation --register-mlflow --promote-production --epochs 200
cd backend && uv run pytest tests/test_api.py tests/test_real_fuel_cell_data_pipeline.py
cd frontend && npm run build
```

Results:

```text
backend tests: 19 passed, warnings only
frontend build: passed, Vite chunk-size warning only
best smoke model in latest run: MLP
MLflow Production model: pem_fuel_cell_real_cathode_degradation
```

## Resolved Decisions

1. Training data scope: Cell_01 smoke workflow first.
2. MLflow deployment: local file store first, likely `backend/mlruns/`, ignored by git.
3. Registry behavior: register and load the MLflow `Production` model for the real project now.
4. Model metrics: regression R², RMSE, and MAE per output/split.
5. Split strategy: future grouped-by-`cell_id`; for one cell, use lifecycle/cycle-aware smoke validation and clearly document the limitation.
6. Outputs: keep exactly `bol_current_density`, `eol_current_density`, `bol_ecsa`, and `ecsa_loss`.
7. Baselines: MVLR/simple linear regression baseline plus MLP; defer XGBoost.
8. UI location: new top-level Model Quality tab.
9. Human review storage: local JSON for now.
10. Agentic placeholder: generic “AI preprocessing assistant”.
11. Generated model/preprocessing/MLflow artifacts: ignored by git for now.
12. Docker Compose MLflow: important near-term follow-up, not part of this pass.
