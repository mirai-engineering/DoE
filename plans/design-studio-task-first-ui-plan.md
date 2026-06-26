# Design Studio Task-First UI Plan

## Context

The latest Design Studio functionality is technically correct and generic: it can plot champion-model response curves, overlay measured rows from `predictions.csv`, filter overlays, and constrain optimization search space. The current interface exposes too much of that machinery at once. For an engineering user, the primary task is simpler: choose a proposed design/condition, plot the predicted response curve, and compare it against relevant measured training reality.

The next change should improve task fulfillment without reintroducing fuel-cell hardcoding. Design Studio must remain driven by Mirai's canonical schema, optional generic metadata hints, and post-training artifacts such as `predictions.csv`. Intake, preprocessing, exported training, MLflow logging, and champion loading behavior should remain structurally unchanged.

## Approach

Reorganize the frontend around task-oriented Design Studio workflows while preserving the existing generic backend contracts.

Recommended UI structure:

1. **Plot curve** — default, compact workflow for predicted curve + measured training overlay.
2. **Optimize** — search-space/fixed-condition controls and candidate discovery.
3. **Compare/export** — saved comparison, result summaries, and ZIP export.

The app should not hardcode domain names such as humidity, Pt/C, voltage, current density, BoL, or EoL. Instead it should use generic signals, in this priority order:

1. Existing `plot_recipes` / selected recipe from schema metadata.
2. Optional generic Design Studio metadata hints copied through the Mirai contract, such as default sweep/output/filter/grouping preferences.
3. Current schema roles (`input`, `output`, `metadata`, `context`, `group`, `id`) and `predictions.csv` column availability.
4. Conservative fallbacks: first numeric input as sweep, first output as response, recommended low-cardinality exact filters from current input values.

No required changes should be made to the intake/preprocessing/training artifact structure. Optional metadata hints may be passed through when already present, but old contracts must continue to work.

## Files to modify

- `frontend/src/components/DesignStudioPage.tsx`
  - Reorganize sections/tabs into Plot curve, Optimize, Compare/export.
  - Replace the always-expanded overlay-filter grid with a compact measured-training overlay summary.
  - Keep the existing full filter controls behind **Refine matching** / **Advanced filters**.
  - Move **Search space / fixed conditions** out of the Plot curve path into the Optimize path.
  - Improve generic labels and helper copy.
- `frontend/src/lib/api.ts`
  - Add/adjust optional types if needed for overlay UI metadata or modes.
- `backend/app/services/design_studio.py`
  - Keep existing prediction/filter behavior.
  - Optionally enrich `training_overlay_options` with generic UI classification fields, such as `recommended`, `advanced`, `internal`, `default_match`, and `groupable`, derived from schema roles and column statistics.
  - Optionally read generic `design_studio` hints from schema variable metadata if present.
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/contract.py`
  - Only if necessary: pass through optional generic UI hints from contract/data dictionary into `schema.metadata.all_variables`, `inputs`, and `outputs` without making them required.
  - Do **not** add domain-specific fields or break current manifest validation.
- Tests:
  - `backend/tests/test_design_studio_contract.py` for optional hint pass-through / overlay column classification if backend changes are made.
  - Frontend build as the main guard unless existing frontend test infrastructure is available.

## Reuse

- Existing generic backend overlay support:
  - `backend/app/services/design_studio.py::training_overlay_options()`
  - `backend/app/services/design_studio.py::_training_overlay()`
  - `backend/app/services/design_studio.py::predict_design()`
- Existing generic plot recipe handling:
  - `plot_recipes`, `selected_plot_recipe_id`, dynamic `scatter_response` payloads.
- Existing frontend helpers/state:
  - `trainingOverlayPayload()`
  - `suggestedOverlayFilters()`
  - `searchSpacePayload()`
  - generic sweep/output recipe helpers.
- Existing optimization behavior:
  - `fixed_inputs` and `constraints` support already wired into seed/Pareto calls.

## Proposed UX details

### Plot curve default view

Show a compact, task-first layout:

```text
Curve plot
Sweep: [schema-selected input]
Predicted response: [schema-selected output] [+ Add response]

Measured training overlay
[x] Show comparable training data
Matching by: <summary of recommended filters from current inputs>
14,287 / 17,808 rows shown
[Refine matching]

<chart>
```

The summary should display only recommended, user-meaningful conditions. It should hide noisy/internal fields such as row indexes, source/model bookkeeping, and opaque IDs unless the user opens advanced filters.

### Refine matching / Advanced filters

Keep the existing full generic filter functionality, but move it into a collapsed drawer/details panel. Organize columns into:

- **Suggested matching conditions**: schema inputs/context/group variables with low-cardinality exact values or useful numeric ranges.
- **Other available columns**: metadata/id/source columns.
- **Internal/debug columns**: row index, model/source bookkeeping, high-cardinality identifiers.

This preserves expert control without forcing every engineer to start from CSV internals.

### Overlay modes

Use generic modes only:

- `comparable`: use recommended filters initialized from current input values where robust.
- `same_current_conditions`: match current values for selected exact-match inputs where possible.
- `custom`: user-edited filters/ranges.
- `none`: hide overlay.

These modes should be implemented as UI state that maps to the existing `training_overlay_enabled`, `training_overlay_filters`, and `training_overlay_ranges` payload. Backend behavior can remain unchanged unless metadata classification is needed.

### Optimize tab/section

Move **Search space / fixed conditions** to the Optimize workflow. Default copy:

```text
Choose what the optimizer may change. Fixed variables use the current curve-plot values; ranged variables search inside your selected bounds; free variables use schema bounds.
```

Seed/Pareto buttons should live near this control, not inside the basic plot setup.

## Skills and agents mapping

Implementation should use these skills/agents explicitly:

- **source-driven-development**
  - Inspect existing Design Studio component structure, schema metadata shape, and overlay option generation before editing.
- **incremental-implementation**
  - Make UI reorganization in small commits/patches: first layout/tabs, then overlay summary, then advanced drawer, then optimize relocation.
- **test-driven-development**
  - Add or update backend tests for any new metadata classification/hint pass-through before relying on it in the UI.
- **browser-testing-with-devtools**
  - Manually inspect the redesigned Design Studio with the real project to ensure the chart is visible early and the default task can be completed quickly.
- **surrogate-model-debugging**
  - Verify the UI still uses the loaded champion model and `predictions.csv` artifacts, not pre-preprocessing/raw data assumptions.
- **reviewer agent**
  - Review final diff for accidental fuel-cell hardcoding, broken generic contract assumptions, or upstream lifecycle changes.
- **scout agent**
  - Optional first-pass read-only scan of current component sections and backend response shapes before implementation.
- **worker agent**
  - Optional focused implementation of either frontend layout or backend metadata classification, not both at once, to keep changes reviewable.

## Steps

- [x] Inspect current `DesignStudioPage.tsx` layout and identify exact component blocks to move/collapse.
- [x] Define the minimal UI state model for `plot | optimize | compare` workflows and overlay mode selection.
- [x] Add generic overlay-column classification on the frontend first using existing `training_overlay_options` fields; avoid backend changes unless needed.
- [x] If frontend-only classification is insufficient, enrich `training_overlay_options` in `design_studio.py` with optional generic `advanced/internal/groupable/default_match` flags derived from schema role and column statistics.
- [x] Keep all full overlay filter controls, but render them only inside **Refine matching / Advanced filters**.
- [x] Add compact overlay summary showing enabled state, row counts, and active recommended filters.
- [x] Move search-space/fixed-condition controls and seed/Pareto actions into the Optimize workflow.
- [x] Update labels/copy from implementation-centric language to task-centric generic language.
- [x] Verify payloads are unchanged or backward compatible: prediction still sends overlay filters/ranges; optimization still sends fixed inputs/constraints; export still works.
- [x] Add/update backend tests only for backend contract changes; otherwise rely on frontend build plus manual browser checks.
- [x] Run targeted backend tests and frontend build.
- [x] Use reviewer agent to check for accidental domain hardcoding and lifecycle regressions.

## Verification

Backend:

- `cd backend && uv run pytest tests/test_design_studio_contract.py tests/test_mlflow_durable_pointers.py -q`
- If contract pass-through changes are made, add the relevant contract-focused test and include it in the command.

Frontend:

- `cd frontend && npm run build`

Manual/browser checks:

- Open Design Studio for `fraunhofer / ccm_degradation_029a2f61` after loading the champion.
- Confirm the default view is **Plot curve**, not optimization or advanced filters.
- Confirm a user can complete the task “plot predicted curve with measured training overlay” without opening advanced filters.
- Confirm **Refine matching** exposes the full generic filters and still updates overlay row counts.
- Confirm Optimize still supports fixed/current, ranged, and free variables.
- Confirm no fuel-cell-specific names are hardcoded in UI logic; any domain-specific labels should come from schema metadata.
- Confirm intake, preprocessing, training, MLflow artifact resolution, and champion loading code paths are untouched except for optional metadata pass-through if explicitly needed.
