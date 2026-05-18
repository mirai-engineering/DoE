# Design Studio Playground Plan

## Context

The app currently has credible model-quality evidence, batch search, BO, and prediction diagnostics. What is missing is the interactive “whoa” layer: a scientist-facing playground where users can apply the active/champion model to explore designs dynamically.

The goal is a new tab:

```text
Design Studio
```

It should feel closer to TensorFlow Playground than a static report: move input sliders, see predictions and curves update, seed the controls from batch search or BO, compare against a saved candidate or selected real cell, then export a professional ZIP.

Key user decisions:

- Tab name: `Design Studio`
- First interaction priority: batch-search seed first, manual exploration second, BO suggestion third
- Create a dedicated backend API for Design Studio rather than overloading `/recommend`
- Use the observed voltage grid for fuel-cell polarization sweeps
- Compare against a saved/selected candidate, with option to manually choose a real cell
- Default fuel-cell objective: maximize BoL current density
- Export format: ZIP
- UI controls/buttons must be generic/schema-driven and adapt to future projects beyond fuel cells

## Approach

Implement Design Studio as a schema-driven interactive surrogate-model playground with project-specific visualization presets.

Generic foundation:

```text
schema inputs → live controls → active model predictions → output cards → comparison/export
```

Fuel-cell preset:

```text
candidate inputs + observed operating_voltage grid
→ predicted BoL/EoL current-density curves
→ polarization plot: x=current density, y=voltage
```

Batch search and BO become seed sources for the playground, not replacements for manual scientist exploration.

## Files to modify

Backend:

```text
backend/app/main.py
backend/app/schemas.py
backend/app/services/design_studio.py
backend/app/services/prediction.py
backend/app/services/recommendation.py
backend/app/services/model_quality.py
```

Frontend:

```text
frontend/src/types/doe.ts
frontend/src/lib/api.ts
frontend/src/App.tsx
frontend/src/components/DesignStudioPage.tsx
frontend/src/components/Tabs.tsx
```

Tests:

```text
backend/tests/test_real_fuel_cell_data_pipeline.py
backend/tests/test_api.py
```

Docs:

```text
docs/reference/REAL_FUEL_CELL_DATASET.md
backend/training/README.md
```

## Reuse

Backend reuse:

- `predict_rows(...)` from `backend/app/services/prediction.py`
- `_generate_candidates(...)` and `_score_predictions(...)` concepts from `backend/app/services/recommendation.py`
- project schema from `get_project_schema(...)`
- `predictions.csv` / training artifact loading patterns from `model_quality.py`
- observed voltage values from real prediction artifacts/model table

Frontend reuse:

- `ProjectSchema`, `PredictionMap`, recommendation types from `frontend/src/lib/api.ts`
- `schema.inputs` and `schema.outputs` to generate generic controls/cards
- existing `formatNumber` helpers
- Plotly styling from Model Quality prediction diagnostics

## Step 1 — Add backend Design Studio service

Create:

```text
backend/app/services/design_studio.py
```

Responsibilities:

- load project schema
- generate schema-driven default input values
- compute live predictions for one candidate
- for fuel-cell project, generate voltage-sweep rows using observed `operating_voltage` grid
- seed a candidate from dedicated batch search
- expose selected-real-cell comparison curve from training artifacts
- package export ZIP

Keep service generic, with project-specific hooks/presets.

Suggested internal API:

```python
get_design_studio_state(project_id: str) -> dict
predict_design(project_id: str, inputs: dict[str, float]) -> dict
seed_batch_candidate(project_id: str, objective_weights: dict[str, float] | None, constraints: dict | None, n_candidates: int) -> dict
get_real_cell_options(project_id: str) -> dict
export_design_zip(project_id: str, payload: dict) -> bytes
```

## Step 2 — Add dedicated backend endpoints

Add endpoints:

```text
GET  /projects/{project_id}/design-studio/state
POST /projects/{project_id}/design-studio/predict
POST /projects/{project_id}/design-studio/seed/batch
POST /projects/{project_id}/design-studio/export.zip
```

Optional later:

```text
POST /projects/{project_id}/design-studio/seed/bo
```

Initial `state` response should include:

```json
{
  "project_id": "...",
  "active_model": {...},
  "inputs": [...],
  "outputs": [...],
  "default_inputs": {...},
  "default_objective_weights": {...},
  "presets": {
    "fuel_cell_polarization": {
      "enabled": true,
      "x_output_bol": "bol_current_density",
      "x_output_eol": "eol_current_density",
      "y_input": "operating_voltage",
      "observed_voltage_grid": [0.45, 0.5, ...]
    }
  },
  "real_cell_options": [...]
}
```

Design prediction response:

```json
{
  "project_id": "...",
  "source": "served_model_prediction",
  "model_version": "...",
  "inputs": {...},
  "predictions_at_selected_point": {...},
  "curve": {
    "preset": "fuel_cell_polarization",
    "rows": [
      {"operating_voltage": 0.45, "bol_current_density": 1.2, "eol_current_density": 0.9}
    ]
  },
  "warnings": [],
  "comparison_real_cell": {... optional ...}
}
```

## Step 3 — Use observed voltage grid

For the real fuel-cell project, derive the sweep grid from training artifacts rather than a made-up linspace.

Preferred source:

```text
training_artifacts/latest/predictions.csv
```

or fallback:

```text
model_table_preprocessed.csv
```

Use unique sorted `operating_voltage` values. For each voltage value:

- copy current candidate inputs
- replace `operating_voltage`
- call `predict_rows(...)`
- return predicted BoL/EoL current density for the curve

This avoids an artificial voltage grid and keeps the playground close to the measured domain.

## Step 4 — Add real-cell comparison support

State endpoint should expose real cell choices from training artifacts:

```text
cell_id
operating_rh values
split
row_count
```

Prediction endpoint accepts optional comparison selection:

```json
{
  "comparison_real_cell": {
    "cell_id": "Cell_17",
    "operating_rh": 100
  }
}
```

Response includes measured real-cell curve rows:

```text
operating_voltage
bol_current_density_true
eol_current_density_true
split
cell_id
operating_rh
```

UI should label these as measured real-cell data, not model predictions.

## Step 5 — Add batch-search seed endpoint

Create a richer endpoint than `/recommend` so the Design Studio can request a seed candidate and immediately receive its prediction curve.

Default fuel-cell objective:

```text
maximize BoL current density
```

Generic rule:

- choose first output with `direction=maximize` as the default positive objective if no project-specific objective is configured
- for fuel-cell project, explicitly default to `bol_current_density: 1.0`

Response should include:

```text
candidate inputs
predictions
score
curve
model_version
warnings
```

## Step 6 — Add ZIP export endpoint

Export a professional ZIP containing:

```text
candidate_inputs.csv
predicted_outputs_at_selected_point.csv
predicted_polarization_curve.csv
comparison_candidate.csv
selected_real_cell_curve.csv
nearest_real_cells.csv        # placeholder/empty in v1 if nearest-neighbor not implemented yet
README.txt
```

README should clearly state:

- source is served-model prediction
- active model version
- candidate inputs
- observed voltage grid was used for fuel-cell curve sweep
- measured real-cell comparison is observational data
- predictions are model estimates, not experimental results

## Step 7 — Add frontend Design Studio tab

Update:

```text
frontend/src/types/doe.ts
```

Add tab:

```text
{ id: 'design-studio', label: 'Design Studio' }
```

Update `App.tsx` to render:

```tsx
<DesignStudioPage schema={schema} />
```

Place the tab near the interactive workflows:

```text
Batch Explorer
Design Studio
Batch Results
Batch Visuals
Optimization Loop
Business Impact
Model Quality
```

## Step 8 — Build schema-driven live controls

Create:

```text
frontend/src/components/DesignStudioPage.tsx
```

Generate controls from `schema.inputs`, not hardcoded names.

Each input control:

```text
label from schema
slider min/max from schema
numeric input
unit label
reset/default affordance
```

Buttons should be generic:

```text
Seed from best batch search
Save current as comparison
Compare with real experiment
Export design ZIP
```

Avoid hardcoded fuel-cell-only button labels like `Optimize fuel cell`; use project display name or generic language:

```text
Explore design
Generate candidate
Compare design
Export design package
```

## Step 9 — Build live prediction cards

Generate output cards from `schema.outputs`.

Each card:

```text
output label
predicted value
unit
direction badge: maximize/minimize
change vs saved comparison if available
```

For fuel-cell project, visually emphasize default objective:

```text
BoL current density
```

But implement this as data-driven `default_objective_weights`, not a hardcoded UI-only rule.

## Step 10 — Build dynamic fuel-cell curve visual

If `presets.fuel_cell_polarization.enabled`, show hero curve:

```text
Predicted BoL curve
Predicted EoL curve
Saved candidate comparison curve, if present
Selected measured real-cell BoL/EoL curves, if present
```

Axis labels:

```text
x-axis: Current density / A cm⁻²
y-axis: Cell voltage / V
```

If a future project has no fuel-cell preset, show a generic output response panel instead of breaking the page.

## Step 11 — Add saved comparison candidate

Frontend state should support:

```text
current candidate
saved comparison candidate
selected real cell comparison
```

User flow:

1. Seed from batch search.
2. Save current as comparison.
3. Move sliders manually.
4. See output deltas and curve overlay vs saved comparison.
5. Optionally select a measured real cell.
6. Export ZIP.

## Step 12 — Add tests

Backend tests:

- `GET /design-studio/state` returns schema-driven inputs/outputs and voltage grid for real project
- `POST /design-studio/predict` returns selected-point predictions and curve rows
- curve uses observed voltage grid
- real-cell options are available
- `POST /design-studio/seed/batch` returns a candidate and curve
- `POST /design-studio/export.zip` returns a ZIP with required files

Frontend:

- run production build

```bash
cd frontend
npm run build
```

Backend:

```bash
cd backend
uv run pytest tests/test_real_fuel_cell_data_pipeline.py tests/test_api.py
```

## Verification

Manual checks:

- Design Studio tab appears.
- Controls are generated from schema input labels/units.
- Output cards are generated from schema outputs.
- Batch seed loads a proposed candidate.
- Moving sliders updates predictions and curve.
- Fuel-cell polarization curve uses observed voltage grid.
- User can save current candidate as comparison.
- User can select a measured real cell for comparison.
- Export ZIP downloads and contains expected CSV/README files.
- Existing Batch Explorer, BO, Model Quality, and Business Impact pages still work.

## Acceptance criteria

- Design Studio feels interactive and model-driven, not like a static report.
- The first CTA is schema-generic but supports batch-seeded fuel-cell design exploration.
- Fuel-cell project shows dynamic predicted BoL/EoL polarization curves.
- UI labels/buttons are generic and adapt to future project schemas.
- Observed voltage grid is used for curve sweeps.
- Comparison supports saved candidate and manually selected real cell.
- Default fuel-cell objective maximizes BoL current density.
- Export is a ZIP suitable for scientist/lab handoff.
