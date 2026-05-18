# All-Cells Real Fuel-Cell MLflow + BO Holdout Plan

## Context

The current real-data MLOps workflow is a successful Cell_01 smoke path: audited CSVs, preprocessing, MVLR/MLP training, MLflow registration, runtime loading, and Model Quality UI. Its metrics validate plumbing only, not scientific generalization.

Next goal: expand from Cell_01 to all 42 available cell archives, move to grouped-by-cell scientific evaluation, use normalized/per-output model-quality criteria, and reserve exactly 3 never-trained cells for BO replay/evaluation.

Initial code findings:

- Raw data root contains 42 zip archives: `data/Cathode Catalyst Degradation/01-Data/Cell_01.zip` ... `Cell_42.zip`.
- Only `Cell_01/` is currently extracted as a folder.
- `backend/training/build_real_fuel_cell_dataset.py` intentionally blocks all non-Cell_01 processing via `_enforce_phase1_cell()`.
- Current build functions mostly accept `cell_id` and `cell_root`, so they are reusable once the Phase 1 guard and zip/folder input handling are generalized.
- Current BO replay code reads project replay CSVs from `backend/data/replay/{project_id}_initial_observed.csv` and `{project_id}_hidden_pool.csv` via `backend/app/services/replay_mapping.py`.
- Current model selection uses raw averaged validation RMSE over all four outputs; this is acceptable for smoke but weak for science because outputs have different units/scales.
- Current MLflow promotion uses the deprecated-ish `Production` stage. The next pass should use aliases/tags: `champion` and `challenger`.

## Approach

Recommended approach: create an all-cells real-data workflow with three distinct data partitions:

1. **Model-development cells**: used for train and validation grouped-by-cell ML fitting/model selection.
2. **Model test cells**: unseen during fitting and hyperparameter/model selection, used for final model quality reporting.
3. **BO holdout cells**: never used for MVLR/MLP training, validation, test, scaler fitting, model selection, or acceptance thresholds. These rows become BO replay data so the optimization loop can reveal real held-out outcomes.

Use deterministic, metadata-aware splitting rather than pure random splitting where possible. Stratify by key experimental design variables such as Pt/C ratio, I/C ratio, ionomer EW, AST RH, and AST UPL. If stratification is too sparse, fall back to a documented seeded random grouped-by-cell split with a warning.

Reserve exactly **3 BO holdout cells**. These cells must remain completely excluded from model development and final test metrics; they feed only BO replay initial/hidden pools.

For MLflow lifecycle, register every candidate model version, mark the deployable best model with alias/tag `champion`, and mark the best non-champion or latest experimental model as `challenger`. Runtime should prefer `champion` alias and use legacy `Production` only as a transition fallback.

## Files to modify

- `backend/training/real_fuel_cell_schema.py`
- `backend/training/build_real_fuel_cell_dataset.py`
- `backend/training/preprocess_real_fuel_cell.py`
- `backend/training/train_real_fuel_cell_models.py`
- `backend/training/mlflow_utils.py`
- `backend/app/services/mlflow_registry.py`
- `backend/app/services/project_registry.py`
- `backend/app/services/model_quality.py`
- `backend/app/services/replay_mapping.py` or a new replay-generation script under `backend/training/`
- `backend/tests/test_real_fuel_cell_data_pipeline.py`
- `backend/tests/test_api.py`
- `frontend/src/components/ModelQualityPage.tsx`
- `docs/reference/REAL_FUEL_CELL_DATASET.md`
- `docs/reference/MLFLOW_MODEL_LIFECYCLE.md`

## Reuse

- Reuse current per-cell parsing functions in `backend/training/build_real_fuel_cell_dataset.py`: metadata, inventory, polarization, ECSA, model-table, EIS, limiting-current, LSV, and AST artifact builders.
- Reuse schema constants from `backend/training/real_fuel_cell_schema.py`, updating phase labels from Cell_01 smoke to all-cells grouped evaluation.
- Reuse current fit-on-train preprocessing in `backend/training/preprocess_real_fuel_cell.py`, but fit only on grouped train cells.
- Reuse current MVLR and MLP training/evaluation flow from `backend/training/train_real_fuel_cell_models.py`.
- Reuse BO replay loading/reveal mechanics from `backend/app/services/replay_mapping.py` and `backend/app/services/bayesian_optimization.py`.
- Reuse Model Quality API/UI patterns from `backend/app/services/model_quality.py` and `frontend/src/components/ModelQualityPage.tsx`.

## Steps

- [x] Generalize raw cell input handling so the builder can read either extracted `Cell_NN/` folders or `Cell_NN.zip` archives without requiring manual extraction into tracked paths.
- [x] Remove/replace the Cell_01 Phase 1 guard with an explicit `--scope cell_01_smoke|all_cells` or equivalent safety switch.
- [x] Build audited all-cell CSV artifacts with appended rows across all cells, preserving `cell_id`, `test_no`, source file, source row, and rejection reasons.
- [x] Add all-cell QA summaries: per-cell row counts, parse failures, rejected rows, missing modalities, ECSA anomalies, negative ECSA loss flags, voltage-overlap rejection rates, and metadata coverage.
- [x] Define deterministic metadata-aware grouped-by-cell partitions: train, validation, final test, and exactly 3 BO holdout cells.
- [x] Ensure BO holdout cells are excluded from all preprocessing fit, model training, validation, test, model selection, and threshold calculation.
- [x] Generate BO replay CSVs from BO holdout rows: `{project_id}_initial_observed.csv` and `{project_id}_hidden_pool.csv`, with explicit metadata linking replay rows to held-out cell IDs.
- [x] Update preprocessing to fit imputers/scalers only on grouped train cells and transform validation/test/BO holdout separately.
- [x] Replace raw averaged RMSE model selection with normalized RMSE, plus per-output metrics.
- [x] Add MVP per-output acceptance/status reporting with provisional report-only thresholds: pass, warning, fail, or not_enough_variance. Do not block registration on these thresholds yet.
- [x] Add weighted model-selection objective using normalized per-output metrics and documented default weights, while keeping weights easy to revise later.
- [x] Preserve R² `null`/undefined semantics in JSON and stop logging undefined R² as normal `0.0` metrics. Log explicit `r2_defined` flags or skip undefined R² in MLflow metrics.
- [x] Update MLflow model lifecycle to use registered-model aliases/tags: `champion` for runtime production and `challenger` for comparison candidates.
- [x] Update runtime model loading to prefer MLflow alias `champion`, then fall back to legacy `Production`, then local artifact.
- [x] Expand Model Quality UI to show grouped split summary, BO holdout summary, normalized RMSE, per-output pass/warn/fail criteria, champion/challenger metadata, and residual/error plots.
- [x] Add tests proving BO holdout cells are absent from training/preprocessing/model-selection splits and present only in replay artifacts.
- [x] Add tests for alias-based MLflow loading and undefined R² logging behavior.
- [x] Run all-cell build, preprocessing, training, model-quality API tests, BO replay tests, and frontend build.

## Verification

Backend verification commands should include:

```bash
cd backend
uv run python training/build_real_fuel_cell_dataset.py --scope all_cells --profile
uv run python training/preprocess_real_fuel_cell.py --project-id pem_fuel_cell_real_cathode_degradation --scope all_cells
uv run python training/train_real_fuel_cell_models.py --project-id pem_fuel_cell_real_cathode_degradation --register-mlflow --set-alias champion
uv run pytest tests/test_real_fuel_cell_data_pipeline.py tests/test_api.py
```

Frontend verification:

```bash
cd frontend
npm run build
```

Manual checks:

- All 42 cell archives are represented in an inventory/profile, or missing/failed cells are explicitly listed with reasons.
- Train/validation/test/BO holdout are grouped by `cell_id` with no cell leakage.
- BO replay initial/hidden CSVs contain only the 3 BO holdout cells.
- Model Quality UI clearly shows champion/challenger, grouped split metrics, normalized RMSE, per-output acceptance status, and holdout warnings.
- MLflow registered model has a `champion` alias pointing to the runtime model version.

## Execution Evidence

Completed all-cells MVP run:

```text
all-cell model rows: 2544
cell metadata rows: 42
rejected rows: 207
BO holdout rows: 183
split rows: train 1617, validation 374, test 370, bo_holdout 183
BO holdout cells: exactly 3
```

Verification executed:

```bash
cd backend && uv run python training/build_real_fuel_cell_dataset.py --scope all_cells --profile
cd backend && uv run python training/preprocess_real_fuel_cell.py --project-id pem_fuel_cell_real_cathode_degradation --scope all_cells
cd backend && uv run python training/train_real_fuel_cell_models.py --project-id pem_fuel_cell_real_cathode_degradation --register-mlflow --promote-production --set-alias champion --epochs 50
cd backend && uv run pytest tests/test_real_fuel_cell_data_pipeline.py tests/test_api.py
cd frontend && npm run build
```

Results:

```text
backend tests: 19 passed, warnings only
frontend build: passed, Vite chunk-size warning only
MLflow alias: champion set on best model version
legacy Production: retained as fallback
```

## Resolved Decisions

1. Reserve exactly 3 cells exclusively for BO replay.
2. Keep final model test cells separate from BO holdout cells.
3. Use metadata-aware grouped splitting, with a documented seeded random fallback only if needed.
4. Acceptance criteria are MVP/report-only for now because no scientific thresholds are available yet.
5. Runtime should load MLflow alias `champion` first, then fall back to legacy `Production` during the transition.
