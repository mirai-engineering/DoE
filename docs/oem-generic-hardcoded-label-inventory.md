# OEM Generic Hardcoded Label Inventory

Classification: `generic` can remain; `project-configurable` should move to approved project metadata; `fuel-cell-only` should live only in the fuel-cell template/recipe or fuel-cell preprocessing pipeline.

## Frontend

### `frontend/src/components/DesignStudioPage.tsx`
- `fuel-cell`, `BoL/EoL`, `ECSA loss`, `voltage grid`, `polarization curve`, `real-cell`, `RH`, `cell_id`, `operating_voltage`, `bol_current_density`, `eol_current_density` — **fuel-cell-only** for current PEM recipe; should become `PlotRecipe` metadata.
- Objective presets from schema outputs — **generic**.
- Balanced fuel-cell objective — **fuel-cell-only**; should move to `TemplatePack.objective_presets`.
- Compare/export design package shell — **generic**, but measured overlay labels should be **project-configurable**.

### `frontend/src/components/ModelQualityPage.tsx`
- Defaults: `bol_current_density`, `cell_id`, `operating_rh`, `operating_voltage` — **fuel-cell-only** defaults; use approved metadata defaults.
- Cell-level partitions/all-cells MVP/BO holdout cells copy — **project-configurable**; generic split copy should be default.
- Fuel-cell polarization diagnostic — **fuel-cell-only add-on recipe**.
- Parity plot, residual plot, metric cards/table — **generic**.
- Residual x-axis currently operating voltage — **project-configurable**; default should be predicted value or selected x variable.

### `frontend/src/components/BusinessImpactPage.tsx`
- Fuel-cell builds, CCM samples, paper polarization curves, PEMFC references — **fuel-cell-only content**; move to fuel-cell template or remove from generic default.
- Hours/cost/campaign reduction calculator — **generic** if labels are configurable.

### `frontend/src/components/PreprocessingReviewPage.tsx`
- Fuel-cell package validation, Cell_NN.zip, data_overview.xlsx, fuel-cell preprocessing — **fuel-cell-only intake template**.
- Training request summary/approval concept — **generic**.

### `frontend/src/components/ModelMap.tsx`
- Mostly **generic**: schema inputs/outputs drive cards.
- Labels like controlled variables/predicted response/ML Model Map — **generic/project-configurable**.

### Other frontend components
- `PredictPanel`, `RecommendPanel`, `ParallelCoordinatesChart`, `RecommendationsTable` — mostly **generic**, driven by schema/recommendation rows.
- `ResponseSurfaceHeatmap`, `VisualizationsPage`, BO page should use schema labels/units; any fixed KPI wording should be **project-configurable**.

## Backend

### `backend/app/services/design_studio.py`
- Constants `FUEL_CELL_BOL_OUTPUT`, `FUEL_CELL_EOL_OUTPUT`, `FUEL_CELL_VOLTAGE_INPUT`, `FUEL_CELL_RH_INPUT` — **fuel-cell-only**, replace with `PlotRecipe`/template lookup.
- `_fuel_cell_preset`, `_observed_voltage_grid`, `_real_cell_curve` — **fuel-cell-only recipe helpers**; keep behind template pack or recipe handler.
- Default objective weights choosing BoL — **template-configurable**.
- Export filenames `predicted_polarization_curve.csv`, `selected_real_cell_curve.csv` — **project-configurable**.

### `backend/app/services/model_quality.py`
- Hardcoded output units and selected columns — **project-configurable**.
- Quality label `all-cells MVP`, cell split copy — **project-configurable/fuel-cell-only**.
- Metrics/predictions/residual artifact access — **generic**.

### `backend/app/services/preprocessing_review.py`
- Current validator/preprocessor for `data_overview.xlsx` and `Cell_NN.zip` — **fuel-cell-only**.
- EDA summary and preprocessing approval/status — **generic**.
- ydata report title and selected numeric columns — **project-configurable**.

### `backend/app/services/project_registry.py`
- Uploaded projects falling back to base fuel-cell schema — **migration fallback only**; future uploaded projects need approved metadata schema.

### `backend/app/services/business_impact.py`
- PEM/fuel-cell ROI data and external references — **fuel-cell-only template content**.
- Calculator shape — **generic**.

### `backend/app/services/bayesian_optimization.py`
- Default objective weights include PEM/synthetic outputs — **project-configurable**.

### Training pipeline
- `real_data_pipeline/*fuel_cell*` and `real_training_pipeline/train_real_fuel_cell_models.py` are intentionally **fuel-cell-only training/template implementation**.
- Generated `schema.json` / `metadata.json` should include approved template metadata and UI config for downstream generic rendering.

## Summary
The app can become OEM-generic by treating PEM as a template pack and moving plot/diagnostic/business copy into approved project metadata. The highest-risk refactors are Design Studio response curves and Model Quality diagnostics; the lowest-risk wins are metadata types, schema emission, and generic default Model Quality plots.
