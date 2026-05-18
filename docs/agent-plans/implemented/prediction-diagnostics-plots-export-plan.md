# Prediction Diagnostics Plots and Export Plan

> Implementation note: before starting implementation, compact the current conversation context so the prediction-diagnostics work begins with a clean, focused context window.

## Context

Scientists and engineers need visual evidence that a surrogate model reproduces real physical behavior. Scalar metrics in Model Quality are necessary but insufficient. For fuel cells, the familiar validation artifact is a polarization curve:

```text
x-axis: current density
y-axis: voltage
```

The desired fuel-cell-specific diagnostic is an overlay of measured vs predicted BoL/EoL curves, preferably at fixed RH and grouped by cell/condition:

```text
Measured BoL      solid blue
Predicted BoL     dashed blue
Measured EoL      solid orange/red
Predicted EoL     dashed orange/red
```

This should live under:

```text
Model Quality → Prediction diagnostics
```

The implementation should also be generalizable for future engineering domains such as batteries/materials, where the diagnostic may be generic `x-variable vs y-output` or predicted-vs-actual plots rather than fuel-cell polarization curves.

Current training writes `residuals.csv`, but that artifact is error-centric and not sufficient for professional curve reconstruction. It has rows like:

```text
model_name, split, row_index, output, y_true, y_pred, residual, abs_error
```

That is useful for residual plots, but it does not preserve all input/context columns in a curve-friendly wide format. We should keep `residuals.csv` and add a richer `predictions.csv` artifact.

## Approach

Implement prediction diagnostics in three layers:

1. Training artifact layer:
   - Add `predictions.csv` with one row per original preprocessed/model-table row per model.
   - Preserve input columns, metadata columns, split labels, true outputs, predicted outputs, residuals, and absolute errors.

2. Backend API/export layer:
   - Add endpoint to read prediction artifacts for Model Quality.
   - Add ZIP export containing:
     - `predictions_wide.csv`
     - `predictions_long.csv`
     - `README.txt`

3. Frontend Model Quality layer:
   - Add `Prediction diagnostics` section.
   - Add fuel-cell polarization curve preset.
   - Add generic plot builder controls.
   - Add parity plot and residual-vs-x plot.
   - Add ZIP export button.

Prioritize training-run predictions first. Later, support live served-model predictions under a separate label:

```text
Training-run predictions
DoE live predictions
```

## Files to modify

Training:

```text
backend/training/real_training_pipeline/train_real_fuel_cell_models.py
```

Backend:

```text
backend/app/main.py
backend/app/services/model_quality.py
```

Frontend:

```text
frontend/src/components/ModelQualityPage.tsx
frontend/src/lib/api.ts
```

Tests:

```text
backend/tests/test_real_fuel_cell_data_pipeline.py
backend/tests/test_api.py
```

Docs:

```text
backend/training/README.md
docs/reference/MLFLOW_MODEL_LIFECYCLE.md
```

## Reuse

Reuse existing training/evaluation functions:

- `_scaled_arrays(...)`
- `_inverse_minmax(...)`
- `_evaluate_predictions(...)`
- current model loop over `mean_baseline`, `mvlr`, `mlp`
- existing `model_table_preprocessed.csv`
- existing schema constants:
  - `PAPER_INPUT_COLUMNS`
  - `PAPER_OUTPUT_COLUMNS`
  - `PROJECT_ID`

Reuse frontend helpers:

- `asRecord`
- `asNumber`
- `asString`
- `formatR2`
- `formatMetric`
- `formatPercent1`
- existing Model Quality layout/cards

## Step 1 — Add `predictions.csv`

Generate a wide prediction artifact in `train_real_fuel_cell_models.py`.

Target path:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/training_artifacts/latest/predictions.csv
```

Suggested columns:

```text
project_id
model_name
model_type
split
cell_id
row_index
pt_c_ratio
i_c_ratio
ionomer_ew
operating_rh
operating_voltage
ast_rh
ast_upl
bol_current_density_true
bol_current_density_pred
bol_current_density_residual
bol_current_density_abs_error
eol_current_density_true
eol_current_density_pred
eol_current_density_residual
eol_current_density_abs_error
bol_ecsa_true
bol_ecsa_pred
bol_ecsa_residual
bol_ecsa_abs_error
ecsa_loss_true
ecsa_loss_pred
ecsa_loss_residual
ecsa_loss_abs_error
```

Include rows for:

```text
mvlr
mlp
```

Optionally include `mean_baseline` if useful, but first version should focus on deployable models.

Include splits:

```text
train
validation
test
bo_holdout
```

Important: BO holdout must remain labeled `bo_holdout`; do not merge it into `test` internally.

## Step 2 — Extend Model Quality artifact summary

Update `backend/app/services/model_quality.py` so `predictions.csv` appears in artifact summaries if present.

Add a helper that can load prediction rows safely, with reasonable row limits for UI payloads.

Suggested API shape:

```text
GET /projects/{project_id}/model-quality/predictions
```

Response:

```json
{
  "project_id": "...",
  "source": "training_run_predictions",
  "rows": [...],
  "columns": [...],
  "row_count": 1234,
  "truncated": false
}
```

Use a query parameter if needed:

```text
?model_name=mlp&split=validation,test&limit=5000
```

## Step 3 — Add ZIP export endpoint

Add:

```text
GET /projects/{project_id}/model-quality/predictions/export.zip
```

ZIP contents:

```text
predictions_wide.csv
predictions_long.csv
README.txt
```

### `predictions_wide.csv`

Same as training artifact, filtered or unfiltered depending on query params.

### `predictions_long.csv`

One row per prediction/output:

```text
project_id
model_name
model_type
split
cell_id
row_index
output_name
unit
y_true
y_pred
residual
abs_error
pt_c_ratio
i_c_ratio
ionomer_ew
operating_rh
operating_voltage
ast_rh
ast_upl
```

### `README.txt`

Explain:

- file generated from Model Quality prediction diagnostics
- training-run predictions vs future live predictions
- split definitions
- BO holdout caveat
- residual definition:

```text
residual = y_true - y_pred
```

## Step 4 — Add frontend API functions

In `frontend/src/lib/api.ts`, add:

```ts
getModelQualityPredictions(projectId, params?)
getModelQualityPredictionsExportUrl(projectId, params?)
```

For export, direct browser download can use a URL string.

## Step 5 — Add Model Quality → Prediction diagnostics section

In `ModelQualityPage.tsx`, add a new section after `Surrogate model accuracy` or directly below it.

Section title:

```text
Prediction diagnostics
```

Subtitle:

```text
Visual checks of measured vs predicted behavior. Use these plots to judge whether the surrogate learned physically meaningful trends, not just aggregate metrics.
```

Display source label:

```text
Training-run predictions
```

Reserve UI copy for future:

```text
DoE live predictions will appear here when generated from the served model.
```

## Step 6 — Fuel-cell polarization preset

Add a preset card/control:

```text
Fuel-cell polarization curve
```

Defaults:

```text
model_name = bestModelName or mlp
splits = validation + test
operating_rh = first available RH or all RH selectable
cell_id = first available test/validation cell or selectable
x = current density
y = operating_voltage
```

Plot data:

```text
Measured BoL: x=bol_current_density_true, y=operating_voltage
Predicted BoL: x=bol_current_density_pred, y=operating_voltage
Measured EoL: x=eol_current_density_true, y=operating_voltage
Predicted EoL: x=eol_current_density_pred, y=operating_voltage
```

Style:

```text
Measured BoL: solid blue
Predicted BoL: dashed blue
Measured EoL: solid orange/red
Predicted EoL: dashed orange/red
```

Sort points by voltage descending or current density ascending consistently so curves render cleanly.

## Step 7 — Generic plot builder

Add schema-driven controls:

```text
x variable: input or output true/pred
output: selected output
split: validation/test/bo_holdout/train
group by: split, cell_id, operating_rh, model_name
```

For first version, keep controls minimal:

- output selector
- split selector
- model selector
- group selector

Generic plot types:

1. Parity plot:

```text
x = measured y_true
y = predicted y_pred
reference line y=x
color = split
```

2. Residual vs x:

```text
x = selected x variable, default operating_voltage for fuel cells
y = residual
color = split
zero reference line
```

## Step 8 — Export button

Add a button:

```text
Download prediction diagnostics ZIP
```

It calls:

```text
/projects/{project_id}/model-quality/predictions/export.zip
```

Label export contents in UI:

```text
Includes wide predictions, long-format predictions, and README.
```

## Step 9 — Verification

Backend:

```bash
cd backend
uv run python training/real_training_pipeline/train_real_fuel_cell_models.py \
  --project-id pem_fuel_cell_real_cathode_degradation \
  --register-mlflow \
  --set-alias challenger \
  --epochs 1000 \
  --learning-rate 0.003 \
  --seed 7

uv run pytest tests/test_real_fuel_cell_data_pipeline.py tests/test_api.py
```

Frontend:

```bash
cd frontend
npm run build
```

Manual checks:

- `predictions.csv` exists in `training_artifacts/latest`.
- Model Quality loads prediction diagnostics.
- Fuel-cell polarization preset shows BoL/EoL measured vs predicted curves.
- Parity plot shows measured vs predicted with a y=x reference.
- Residual plot shows residuals around zero.
- Export ZIP downloads and contains:
  - `predictions_wide.csv`
  - `predictions_long.csv`
  - `README.txt`
- BO holdout appears only as `bo_holdout`, not merged into `test` internally.
- Existing Model Quality metrics and Business Impact tab remain unchanged.

## Acceptance criteria

- Engineers can visually inspect measured vs predicted polarization curves.
- UI is clean, white, scientific-paper style inside premium cards.
- Prediction source is clearly labeled as `Training-run predictions`.
- Fuel-cell preset is available but generic plotting foundation remains schema-driven.
- Predictions are exportable as a professional ZIP package.
- No change to model training logic beyond writing prediction artifacts.
- No inference-pipeline changes except optional API read/export endpoints.
- Existing tests/build pass.
