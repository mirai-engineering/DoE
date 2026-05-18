# Training package layout

This package is split by project and pipeline responsibility.

## Synthetic demo project

Folder:

```text
backend/training/synthetic_demo/
```

Purpose: legacy/synthetic webapp demo for `pem_fuel_cell_demo`.

Files:

```text
synthetic_demo/generate_synthetic_data.py
synthetic_demo/train_mlp.py
```

It writes/uses:

```text
backend/data/synthetic/pem_fuel_cell_demo.csv
backend/artifacts/pem_fuel_cell_demo/
backend/data/replay/pem_fuel_cell_demo_*.csv
```

Keep this if you still want the synthetic project available in the webapp.

## Real fuel-cell data pipeline

Folder:

```text
backend/training/real_data_pipeline/
```

Purpose: raw real-data ingestion, audited CSV generation, grouped splits, BO holdout reservation, imputation/scaling, and preprocessing reports.

Files:

```text
real_data_pipeline/build_real_fuel_cell_dataset.py
real_data_pipeline/preprocess_real_fuel_cell.py
real_data_pipeline/real_fuel_cell_schema.py
```

## Real fuel-cell training pipeline

Folder:

```text
backend/training/real_training_pipeline/
```

Purpose: MVLR/MLP training, evaluation, ONNX export, MLflow logging/registry metadata, and packaged runtime artifacts.

Files:

```text
real_training_pipeline/train_real_fuel_cell_models.py
real_training_pipeline/mlflow_utils.py
real_training_pipeline/export_onnx.py
```

## Compatibility wrappers

The old top-level script paths still exist as thin wrappers, so existing commands/tests/docs continue to work:

```text
backend/training/train_mlp.py
backend/training/generate_synthetic_data.py
backend/training/build_real_fuel_cell_dataset.py
backend/training/preprocess_real_fuel_cell.py
backend/training/train_real_fuel_cell_models.py
```

Prefer the new folders for future code changes. The FastAPI inference pipeline lives under `backend/app/` and is intentionally untouched by this refactor.

## How to run real-data training

Recommended command from the backend folder:

```bash
cd backend
uv run python training/real_training_pipeline/train_real_fuel_cell_models.py \
  --project-id pem_fuel_cell_real_cathode_degradation \
  --register-mlflow \
  --set-alias challenger \
  --epochs 1000 \
  --learning-rate 0.003 \
  --seed 7
```

This trains:

```text
MVLR / multi-output linear regression
MLP / ScientificTabularANN
```

Both deployable models are logged and registered in local MLflow. The selected best candidate receives the `challenger` alias. The script does **not** automatically assign `champion`; promote a model manually in the MLflow UI after reviewing metrics.

The run also writes Model Quality diagnostics, including:

```text
training_artifacts/latest/residuals.csv      # error-centric long residual table
training_artifacts/latest/predictions.csv    # curve-friendly wide predictions table
```

`predictions.csv` preserves inputs, cell metadata, split labels, measured outputs, predicted outputs, residuals, and absolute errors for MVLR/MLP across train, validation, test, and `bo_holdout`. The Model Quality UI uses it for polarization-curve overlays, parity plots, residual plots, and ZIP exports. The Design Studio also uses these artifacts to provide observed voltage grids and measured real-cell comparison curves for interactive served-model exploration.

The old wrapper still works:

```bash
cd backend
uv run python training/train_real_fuel_cell_models.py \
  --project-id pem_fuel_cell_real_cathode_degradation \
  --register-mlflow \
  --set-alias challenger \
  --epochs 1000 \
  --learning-rate 0.003 \
  --seed 7
```

## How to rebuild the real-data pipeline first

If raw/source data changed or you want to regenerate audited CSV/preprocessing artifacts:

```bash
cd backend

uv run python training/real_data_pipeline/build_real_fuel_cell_dataset.py \
  --scope all_cells \
  --profile

uv run python training/real_data_pipeline/preprocess_real_fuel_cell.py \
  --project-id pem_fuel_cell_real_cathode_degradation
```

Then run the real-data training command above.

## How to run synthetic demo training

Recommended command:

```bash
cd backend
uv run python training/synthetic_demo/train_mlp.py
```

The old wrapper also still works:

```bash
cd backend
uv run python training/train_mlp.py
```

## How to view local MLflow runs

```bash
cd backend
uv run mlflow ui --backend-store-uri ./mlruns --host 127.0.0.1 --port 5000
```

Open:

```text
http://127.0.0.1:5000
```

Useful filters:

```text
tags.project_id = 'pem_fuel_cell_real_cathode_degradation'
tags.model_family = 'mlp'
tags.model_family = 'mvlr'
tags.candidate_role = 'challenger'
```
