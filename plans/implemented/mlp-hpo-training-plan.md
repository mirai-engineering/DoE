# Plan: Add MLP Hyperparameter Optimization to Mirai Training

## Context
- Goal: improve the Fraunhofer / Fuel Cell Demo MLP results by adding a small hyperparameter-optimization layer to the existing MLflow training path.
- Non-goal: do not change ingestion, preprocessing, exported package structure, feature/target mappings, or Mirai data contract behavior.
- Training must continue from the approved UI-created training request package under `training-requests/`, with `training_manifest.json` identity validation and remote MLflow logging unchanged.

## Current findings
- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md` confirms Fuel Cell Demo uses the generic `generic_tabular_doe` lifecycle, not a fuel-cell-specific path.
- `backend/ml_lifecycle/REMOTE_TRAINING.md` confirms local/remote training must use `ml_lifecycle.training.run_exported_package` and an exported training package, not loose CSV files.
- `backend/ml_lifecycle/README.md` confirms MLflow experiment/model naming and manual challenger-to-champion promotion remain the model activation flow.
- Initial code scan shows the active generic training code is in `backend/ml_lifecycle/training/generic_tabular_doe/train.py`, with a PyTorch `GenericTorchMLPRegressor`, ONNX export helper, candidate logging, and per-candidate MLflow runs.

## Approach
- Add Optuna as a lightweight tuning layer around only the existing PyTorch `GenericTorchMLPRegressor` candidate.
- Reuse the exact approved package inputs and fixed train/validation/test split currently loaded from `model_table_preprocessed.csv`; do not alter preprocessing, feature maps, target maps, schema, or split assignment.
- Optimize MLP hyperparameters against the existing unified selection metric, `validation_weighted_normalized_rmse`, which averages normalized RMSE across the four targets (`y1`..`y4`). Continue logging the four per-output metrics plus the unified metric.
- After Optuna selects the best MLP config, retrain/keep the best fitted MLP as the normal `mlp` candidate and pass it through the unchanged candidate comparison, prediction CSV, ONNX export, MLflow model logging, and challenger registration flow.
- Log HPO details to MLflow under the MLP candidate run as nested trial runs, and also persist `mlp_hpo_trials.csv` / `mlp_hpo_summary.json` as artifacts so the optimization is auditable even outside MLflow.
- Preserve the existing manual MLflow review and challenger-to-champion promotion process.

## Files to modify
- `backend/pyproject.toml` and `backend/uv.lock`: add Optuna as a backend dependency.
- `backend/ml_lifecycle/training/run_exported_package.py`: expose conservative CLI/config knobs for MLP HPO (`--mlp-hpo-trials`, optional timeout/seed) while keeping `--max-epochs` useful for smoke runs.
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py`: implement the MLP-only Optuna study, trial artifact capture, best-param propagation, and nested MLflow trial logging.
- `backend/tests/test_generic_contract_pipeline.py`: add/adjust tests for HPO artifacts and MLflow trial logging without making tests slow.
- `backend/tests/test_local_exported_package_training.py`: assert exported-package training config carries HPO options/tags correctly.

## Reuse
- `GenericTorchMLPRegressor` in `backend/ml_lifecycle/training/generic_tabular_doe/train.py`; current tunable params already include `hidden_layers`, `activation`, `dropout`, `learning_rate`, `weight_decay`, `max_epochs`, `patience`, `seed`, and `loss`.
- `_metrics()` / `_ui_split_metrics()` in `backend/ml_lifecycle/training/generic_tabular_doe/train.py` for the existing per-target and unified metrics.
- `_export_generic_mlp_onnx()` in `backend/ml_lifecycle/training/generic_tabular_doe/train.py` so ONNX parity remains the same after tuning.
- Existing `_candidate_models()` / `train_generic_project()` candidate loop: keep mean baseline, MVLR, Ridge variants, and MLP as independent candidates; only the MLP candidate gets an internal HPO loop.
- Existing `_log_generic_mlflow()` candidate logging/registration flow; add nested trial logging for MLP HPO without registering trials as models.
- Existing exported-package identity validation and remote preflight in `backend/ml_lifecycle/training/run_exported_package.py`.

## Steps
- [x] Add Optuna to backend dependencies and lockfile.
- [x] Extend `build_training_config()` / CLI in `run_exported_package.py` with MLP HPO settings. Recommended defaults: HPO enabled for normal exported-package training, disabled or tiny-budget when `--max-epochs` is used for smoke tests; default seed `7`; default Fuel Cell Demo trial budget around 40–60 trials.
- [x] Implement a helper such as `_optimize_mlp_hyperparameters(...)` inside `train.py` that receives `x_train`, `y_train`, `x_val`, `y_val`, `outputs`, and `mlp_cfg`, then runs a sequential Optuna `TPESampler(seed=seed)` study.
- [x] Use a conservative search space: layer template/width, activation (`silu`, `gelu`, `relu`), dropout, learning rate, weight decay, loss (`smooth_l1`, `mse`), patience, and max epochs bounded by existing `max_epochs` caps.
- [x] For each trial, fit `GenericTorchMLPRegressor` on the existing train split with the existing validation split and score with `_metrics(...)["weighted_normalized_rmse"]`.
- [x] Store trial params, unified metric, per-output validation metrics, epochs trained, and best-trial metadata on the MLP candidate payload and in `mlp_hpo_trials.csv` / `mlp_hpo_summary.json`.
- [x] Keep the candidate name `mlp` stable; add params/tags like `mlp_hpo_enabled`, `mlp_hpo_best_trial`, and best hyperparameters to the existing MLflow MLP candidate run.
- [x] Inside `_log_generic_mlflow()`, when the MLP candidate has HPO trials, create nested MLflow trial runs under the MLP run with trial params/metrics and tags (`model_name=mlp`, `candidate_role=hpo_trial`, `selected_trial=true/false`).
- [x] Ensure the final best MLP still exports `models/mlp.onnx`, copies selected `model.onnx`, appears in `candidate_comparison.csv`, and can be registered as `doe_surrogate_<project_id>@challenger` if it wins.
- [x] Add fast tests with a tiny HPO budget (e.g. 2 trials, 2–5 epochs) and update exported-package config tests.
- [x] Verify on the Fuel Cell Demo package: `training-requests/mirai-training-package-fuel_cell_demo_65248559-dataset_aacae87f5a-train_req_1d50f16644/` (`fraunhofer`, `project_id=fuel_cell_demo_65248559`, 2544 rows, splits 1802/368/374, inputs `x1`..`x7`, targets `y1`..`y4`).

## Verification
- Run targeted tests from `backend/`, for example:
  - `uv run pytest tests/test_generic_contract_pipeline.py tests/test_local_exported_package_training.py`
- Run a short local smoke HPO training against the existing Fuel Cell Demo exported package with a tiny trial count and `--max-epochs`.
- Run the real Fuel Cell Demo training package with the agreed trial budget and remote MLflow/S3 env vars from `backend/.env.training.local`.
- Confirm MLflow experiment `fuel_cell_demo_65248559` receives the existing model candidate runs plus nested MLP HPO trial runs/tags/artifacts.
- Confirm selected challenger still has required artifacts: `training_manifest.json`, `schema.json`, `metrics_summary.json`, `candidate_comparison.csv`, `predictions.csv`, `model.onnx`, and registered `onnx_model`.
- Confirm Mirai activation remains unchanged: manually promote `doe_surrogate_fuel_cell_demo_65248559@challenger` to `champion`, then use **Load champion model**.

## Recommended decisions
- Enable MLP HPO by default for real exported-package training because the goal is to avoid manual MLP retraining.
- Keep HPO configurable from CLI for budget control: `--mlp-hpo-trials` default around `50`, `--mlp-hpo-timeout-seconds` optional, `--mlp-hpo-seed` default `7`, and `--no-mlp-hpo` escape hatch.
- Use sequential optimization, not parallel, to keep reproducibility simple and avoid stressing local/remote MLflow logging.
