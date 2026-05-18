# MLflow Model Lifecycle

## Current MVP

The real fuel-cell project uses a local MLflow file store for the current all-cells MVP:

```text
backend/mlruns/
```

This path is local-only and git-ignored. It is intentionally simple for the Cell_01 smoke workflow.

## Project

```text
pem_fuel_cell_real_cathode_degradation
```

The current registered model workflow is an all-cells MVP. It uses grouped-by-cell train/validation/final-test partitions and reserves exactly 3 cells for BO replay only. Acceptance thresholds are provisional/report-only until scientific criteria are finalized.

Training now logs project/model identity as MLflow tags and parameters while allowing MLflow to generate distinctive run names in the UI. New registered candidates default to the `challenger` alias. Promotion to `champion` is intentionally manual in the MLflow UI after review.

## Models

The first pass trains:

- MVLR / simple multi-output linear regression baseline
- MLP using the existing `TabularMLP` and ONNX export conventions

XGBoost is intentionally deferred.

## Metrics

Regression metrics are logged per split and per output:

- R², with explicit `r2_defined` flags instead of fake `0.0` values for undefined R²
- RMSE and MAE in each output's physical unit
- normalized RMSE using the train-cell target range
- MAE as percent of the split mean
- RMSE as percent of the train-cell range/std
- train-mean baseline MAE/RMSE
- improvement versus the train-mean baseline

This is intended for scientist interpretation: e.g. “BoL current density MAE is 0.33 A/cm², ~29% of the split mean, and improves over the train-mean baseline by ~69%.”

## Runtime loading

The synthetic demo remains local-artifact based.

The real project resolves its MLflow `champion` alias first, then falls back to legacy `Production`, and downloads it into a local ignored cache. If neither exists, backend serving falls back to packaged local ONNX artifacts:

```text
backend/.mlflow-cache/pem_fuel_cell_real_cathode_degradation/
```

Companion schema/preprocessing/metadata files are generated under:

```text
backend/artifacts/pem_fuel_cell_real_cathode_degradation/
```

That directory is also local-only and git-ignored for now.

## Scientist review

Scientist review state is stored locally as JSON:

```text
backend/data/model_quality_reviews/{project_id}.json
```

The Model Quality UI surfaces review status, grouped split metrics, normalized RMSE, per-output units/reference values, baseline comparisons, provisional pass/warn/fail status, champion/challenger metadata, preprocessing summaries, prediction diagnostics, and inactive AI preprocessing assistant placeholders.

Prediction diagnostics are generated from local training artifacts:

```text
training_artifacts/latest/predictions.csv
```

This table stores training-run predictions for MVLR/MLP across train, validation, test, and `bo_holdout`. The UI uses it for fuel-cell polarization overlays, generic parity plots, residual-vs-axis plots, and a professional ZIP export containing wide predictions, long predictions, and a README. `bo_holdout` remains labeled separately and is not merged into final test metrics.

## Near-term Docker Compose follow-up

A Docker Compose MLflow server should be added soon, but not in this first pass. The follow-up should add:

- MLflow tracking server service
- persistent volume for MLflow backend/artifact store
- `MLFLOW_TRACKING_URI=http://mlflow:5000` wiring for backend/training
- optional UI exposure on localhost

Do not treat the local file store as the long-term deployment architecture.

## Future next steps: proper MLflow server

Do **not** copy `backend/mlruns/` into the backend Docker image as the long-term solution. Baking MLflow runs into the runtime image makes model history stale, bloats images, and mixes training/registry state with API serving.

Preferred local architecture:

```text
backend container
  ├─ serves FastAPI
  ├─ loads packaged ONNX for demo fallback
  └─ eventually resolves champion models from MLflow

mlflow container
  ├─ tracking server on :5000
  ├─ SQLite/Postgres backend store
  └─ persistent artifact volume or object store
```

Recommended Docker Compose follow-up:

- Add an `mlflow` service running `mlflow server`.
- Add a persistent Docker volume for MLflow metadata/artifacts.
- Set backend/training env vars:

```text
MLFLOW_TRACKING_URI=http://mlflow:5000
DOE_DISABLE_MLFLOW_MODEL_LOADING=0
```

- Train/register models against the MLflow service, not a local `backend/mlruns/` folder.
- Let the Model Quality API fetch latest runs, aliases, versions, and artifacts from the MLflow server.
- Keep packaged JSON reports/ONNX artifacts only as a demo/offline fallback.

Production target:

```text
MLflow tracking URI: https://mlflow.<company-domain>
Backend store: Postgres / Cloud SQL / RDS
Artifact store: S3 / GCS / Azure Blob
Model routing: train to `challenger`; manually promote reviewed versions to `champion`
```

This will make the Docker stack closer to a professional MLOps workflow: training writes to a shared registry, backend reads approved model versions, and the UI displays live model-quality metadata without rebuilding images for every training run.
