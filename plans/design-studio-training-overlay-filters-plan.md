# Design Studio Training Overlay Filters Plan

## Context

The Design Studio already uses the loaded MLflow champion for robust ONNX serving and resolves static training evidence from `predictions.csv`. A generic training overlay path exists for `scatter_response` plots, but it only supports optional grouping and does not expose row filters. The fuel-cell polarization plot path still has special handling for measured real-cell curves and currently does not include the generic training-overlay markers.

For the fuel-cell case, users often want to compare a predicted polarization/response curve against measured training rows at fixed conditions such as relative humidity, cell, split, or AST protocol. The improvement should stay schema/metadata-driven so future projects with different input/output/metadata columns automatically get appropriate overlay controls.

## Approach

Add a generic, predictions.csv-backed overlay and optimization-constraint contract between backend and frontend:

- Backend will summarize available overlay/search columns and values from the loaded champion run's `predictions.csv` using the approved schema/domain metadata as labels.
- Frontend will render dynamic overlay filter controls from that summary instead of hardcoding fuel-cell fields.
- Prediction requests will send selected overlay filters to Design Studio endpoints.
- Backend overlay extraction will apply filters with AND semantics before returning measured `*_true` rows for the currently selected x variable and output variables.
- The response plot will be fully generic: users obtain a polarization curve by selecting the appropriate x/y variables and axis orientation, not by entering a fuel-cell-specific branch.
- The existing MLflow pointer-only artifact resolution and ONNX serving path will remain unchanged.

Recommended UI shape based on user answers:

- Keep existing generic sweep controls: x/sweep input, y output(s), axis orientation, point count, range.
- Add a collapsible **Training data overlay** panel with:
  - toggle: show/hide overlay,
  - exact-match searchable dropdown filters for categorical or low-cardinality columns,
  - numeric min/max range filters for continuous/high-cardinality numeric columns,
  - robust generic defaults: low-cardinality numeric fields use searchable exact-value dropdowns; high-cardinality numeric fields use min/max ranges,
  - grouping/color-by dropdown,
  - a small row-count/status message after filters are applied.
- Candidate filter columns should be generic and derived from schema + `predictions.csv`; fuel-cell examples would include `operating_rh`, `cell_id`, `split`, `ast_rh`, `ast_upl` only because those columns are present/declared.
- Replace the existing fuel-cell-only “Measured real-cell overlay” shortcut entirely with these generic overlay filters.
- Add a generic **Search space / fixed conditions** control for optimization so “Find best starting design” and “Find tradeoff candidates” explicitly show which variables are fixed at current values, constrained to ranges/sets, or free to vary. This should be user-selectable and initialized from the current Design Studio input values.
- Auto-suggest training overlay filters from current input values when a matching `predictions.csv` column exists and the match can be made safely/generically.

## Files to modify

- `backend/app/services/design_studio.py`
  - Extend `_training_overlay()` to accept exact-match and range filter selections.
  - Add a helper to build overlay/search filter options from `predictions.csv` + schema metadata.
  - Include overlay metadata/options in `get_design_studio_state()`.
  - Apply filters in `predict_design()` for generic response recipes.
  - Extend `seed_batch_candidate()` and `pareto_tradeoff_candidates()` so optimization can honor generic fixed inputs/constraints and return/display the sampled input values.
- `backend/app/services/recommendation.py`
  - Reuse existing `fixed_inputs` and min/max `constraints` support in `_generate_candidates()` / `_effective_bounds()` for generic search-space controls.
  - Defer categorical allowed-value constraints unless/until the schema supports categorical inputs in candidate generation.
- `frontend/src/components/DesignStudioPage.tsx`
  - Remove the fuel-cell-specific recipe/real-cell overlay UI branch from the normal path.
  - Add state for overlay visibility, exact filters, range filters, and group-by.
  - Render schema-driven overlay controls with searchable dropdowns.
  - Render a generic optimization **Search space / fixed conditions** panel where each input can be fixed to the current value, allowed to vary over a range, or left free.
  - Send selected filters/constraints in prediction/seed/pareto/export requests where relevant.
  - Show candidate input parameters in optimization result cards, not only objective output values.
- `frontend/src/lib/api.ts`
  - Add typed Design Studio overlay option/filter fields.
- Tests to add/update:
  - `backend/tests/test_design_studio_contract.py` if present, or an appropriate existing backend test file.
  - `backend/tests/test_real_fuel_cell_data_pipeline.py` for fuel-cell overlay behavior if the fixture supports it.
  - Frontend build/test coverage if available.

## Reuse

- `backend/app/services/design_studio.py`
  - `_predictions_artifact()` for loaded champion `predictions.csv` resolution.
  - `_training_overlay()` for measured `*_true` overlay rows.
  - `_real_cell_curve()` and `get_real_cell_options()` as a reference for condition-specific filtering, but avoid making the generic overlay dependent on `cell_id`/`operating_rh` names.
  - `_curve_rows()` and `predict_design()` for determining the active x variable and output variables.
- `backend/app/services/model_quality.py`
  - `_prediction_path()` already resolves MLflow-loaded champion prediction artifacts by run id.
- `frontend/src/components/DesignStudioPage.tsx`
  - Existing generic sweep controls, `trainingOverlayGroupBy`, plot trace construction, and axis-switch behavior.
  - Existing metadata variable lookup from `schema.metadata?.all_variables` / `schema.domain_metadata?.all_variables`.

## Steps

- [x] Confirm desired overlay UX and filter semantics with the user.
- [x] Define backend response shape for overlay controls, e.g. `training_overlay_options` with columns, labels, roles, dtypes, distinct values/ranges, and recommended defaults.
- [x] Extend `predict_design()` payload contract with `training_overlay_filters`, `training_overlay_ranges`, `training_overlay_group_by`, and optional `training_overlay_enabled`.
- [x] Implement backend filter application against `predictions.csv` before row dedupe/downsampling using AND semantics.
- [x] Ensure overlay rows are returned through the generic `scatter_response` path when matching `*_true` output columns exist; do not add a fuel-cell-only plotting branch.
- [x] Replace fuel-cell-only measured real-cell overlay controls with dynamic frontend filter controls from `training_overlay_options`.
- [x] Add a generic optimization **Search space / fixed conditions** section so users can decide which schema inputs are fixed/current, constrained, or free during `Find best starting design` / Pareto search.
- [x] Update optimization result cards to show important input parameters/conditions generically, with labels/units, in addition to objective outputs.
- [x] Add row-count and empty-state messaging when filters remove all training points.
- [x] Add regression tests for generic metadata/input filtering and fuel-cell RH/cell/split-style filtering without hardcoded UI assumptions.
- [x] Run backend tests and frontend build.

## Verification

- Backend:
  - `cd backend && uv run pytest <targeted design studio tests> -q`
  - Existing MLflow/champion tests should still pass where relevant.
- Frontend:
  - `cd frontend && npm run build`
- Manual:
  - Load `fraunhofer / ccm_degradation_029a2f61` with champion v2.
  - Open Design Studio.
  - Select voltage/current-style plot.
  - Filter overlay to a specific relative humidity and, if available, cell/split/AST condition.
  - Confirm measured overlay points/traces match selected filters and predicted model curve still comes from the loaded champion ONNX model.
