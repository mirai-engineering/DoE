# Plan: Simplify Design Studio to a Robust Generic X–Y Sweep

## Context

The current Design Studio implementation has reached the requested generic direction, but the UI still feels more complex than the core engineering task requires. In particular:

- The implemented **Curve grouping parameter** supports multiple predicted curves, but this is now considered premature for the current workflow.
- The user wants the basic workflow to be: select X, select predicted Y, choose X range and point count, fix all other inputs, then generate exactly `N` predictions.
- If the plot looks linear, that should be treated as a model/data issue, not solved with domain-specific UI tricks.
- Measured training overlay should be hidden by default because it is secondary and currently easy to misconfigure.
- The fixed-condition label inside the plot should be optional and user-controlled, defaulting to no annotation.
- The UI should become less repetitive: Experiment visualisation should focus on the multi-point sweep, while single-point inputs/results should not dominate the same workflow.

The goal is a simple, robust, generic engineering tool that lets users work with the surrogate model without hidden fuel-cell logic or overengineered scenario abstractions.

## Approach

Implement a focused simplification of Design Studio around a single generic X–Y sweep:

1. Keep the generic visualisation backend contract, but remove/deactivate grouped predicted curves from the primary UI and request path.
2. Generate exactly one row per sweep point: `N` prediction rows for `N` selected X values.
3. Treat every non-swept input as fixed by default and editable in the fixed-condition table.
4. Replace the cramped axis checkbox with a compact orientation selector that does not overflow.
5. Hide measured overlay by default while keeping it available in the advanced/overlay section.
6. Add optional plot annotation controls:
   - default: no annotation;
   - option: show selected fixed parameters;
   - option: show all fixed parameters.
7. Reduce repetition by moving single-point prediction controls into a dedicated **Single result** workflow tab, leaving **Experiment visualisation** focused on sweep setup and plotting.
8. Preserve public API route compatibility and avoid new upstream schema requirements.

This plan deliberately does **not** add curve scenarios, measured-grid sweep sampling, fuel-cell-specific plot types, derived objectives, or automatic domain presets.

## Files to modify

- `frontend/src/components/DesignStudioPage.tsx`
  - Main UI simplification, workflow tabs, fixed-condition annotation controls, overlay defaults, axis orientation cleanup.
- `frontend/src/lib/api.ts`
  - Only if a lightweight type extension is needed for annotation/orientation payload fields.
- `backend/app/services/design_studio.py`
  - Ensure grouped curve generation is not triggered unless explicitly present for compatibility; optionally accept annotation metadata without affecting predictions.
- `backend/tests/test_design_studio_contract.py`
  - Add/adjust tests proving a simple sweep creates exactly `N` prediction rows and uses fixed non-swept inputs.

## Reuse

Existing reusable pieces:

- `DesignStudioPage.tsx`
  - `sweepInputName`, `primaryOutputName`, `sweepRangeMin`, `sweepRangeMax`, `sweepPointCount` state.
  - `visualisationFixedInputs` and `numericVisualisationFixedInputs` for fixed non-swept values.
  - `runVisualisation(...)` and `experimentVisualisationPayload(...)` request flow.
  - Existing Plotly chart setup and PNG export.
  - Existing fixed-condition table can be simplified rather than replaced.
- `backend/app/services/design_studio.py`
  - `_experiment_visualisation_rows(...)` already supports generic schema-driven sweep rows.
  - Sweep bounds validation already exists.
  - `_curve_rows(...)` compatibility wrapper should remain.
- `backend/tests/test_design_studio_contract.py`
  - Existing generic sweep/fixed-input tests can be extended.
- `ModelMap` component
  - Already moved to its own tab; keep as-is unless minor tab-order cleanup is needed.

## Agent and skill mapping

Project instruction from `AGENTS.md`: use a scout/read-only discovery step before implementation whenever an agent runner is available, then focused implementation/review steps. If the configured agent runner is unavailable, perform the same steps manually with read-only inspection before editing.

### Agents

- **scout** — read-only reconnaissance before editing.
  - Confirm current `DesignStudioPage.tsx` state after recent commits.
  - Identify all remaining grouped-curve UI/request/backend paths.
  - Confirm where overlay default is initialized.
  - Confirm current single-result vs visualisation tab structure.
- **worker** — implementation handoff, if available.
  - Apply the frontend simplification and minimal backend/test adjustments in small topical commits.
- **reviewer** — focused review, if available.
  - Check for hidden fuel-cell/domain assumptions.
  - Check that simple sweep generates exactly `N` rows.
  - Check UI copy for engineering clarity and reduced complexity.
- **oracle** — optional high-stakes consistency review.
  - Use only if there is uncertainty about preserving API compatibility or if the UI diff becomes large.

### Skills

- `planning-and-task-breakdown`
  - Break implementation into small verifiable phases.
- `frontend-ui-engineering`
  - Simplify tab structure, fixed-condition table, orientation selector, and plot annotation controls without disrupting branding.
- `scientific-ui-clarity`
  - Ensure copy explains model sweep vs display zoom, fixed inputs, and annotation behavior in engineering terms.
- `api-and-interface-design`
  - Keep request payload generic and backward compatible; avoid public route renames.
- `code-simplification`
  - Remove/de-emphasize grouped-curve UI state and reduce redundant controls.
- `test-driven-development`
  - Add backend tests for exactly-`N` sweep behavior and fixed-condition preservation.
- `browser-testing-with-devtools`
  - Manually verify the production-like browser flow: one sweep, fixed values, axis orientation, annotation dropdown, overlay hidden by default.
- `code-review-and-quality`
  - Final diff review for legacy terminology leakage, domain hardcoding, and UI regressions.

## Steps

### Phase 0 — Reconnaissance

- [ ] Inspect current diffs/commits for `DesignStudioPage.tsx`, `design_studio.py`, and `test_design_studio_contract.py`.
- [ ] Locate all `curveGroupInputName`, `curveGroupValues`, grouped trace, and grouped backend payload paths.
- [ ] Confirm overlay default state is currently hidden or changeable from one state initializer.
- [ ] Confirm single-result controls can move to a new tab without changing prediction APIs.

### Phase 1 — Simplify the visualisation model

- [ ] Remove grouped-curve controls from the main Experiment visualisation UI.
- [ ] Stop sending `group_variable` / `group_values` from the standard `experiment_visualisation` payload.
- [ ] Keep backend compatibility for legacy/grouped payloads if already present, but do not expose grouped curves in the primary UI.
- [ ] Ensure `Generate visualisation` predicts exactly the requested point count.

### Phase 2 — Clean up the Experiment visualisation UI

- [ ] Replace the out-of-bounds axis checkbox with a compact orientation selector:
  - `X = sweep variable, Y = predicted response`;
  - `X = predicted response, Y = sweep variable`.
- [ ] Reorganize top controls into fewer, readable rows/cards.
- [ ] Keep sweep range validation and “Use schema range”.
- [ ] Keep the fixed-condition table, but make it visually compact and clearly tied to visualisation only.

### Phase 3 — Separate single-point prediction from sweep visualisation

- [ ] Add or finalize a **Single result** workflow tab.
- [ ] Move the single-result sliders and KPI cards into that tab.
- [ ] Keep a clear action to copy current single-result inputs into visualisation fixed conditions.
- [ ] Ensure optimization still loads candidates into single-result inputs, not directly into visualisation unless the user copies them.

### Phase 4 — Add optional plot annotation

- [ ] Add annotation mode state:
  - `None` by default;
  - `Selected fixed parameters`;
  - `All fixed parameters`.
- [ ] If selected mode is used, allow users to choose which fixed parameters appear in the plot label.
- [ ] Render a Plotly annotation box inside the chart using schema labels/units.
- [ ] Exclude the swept variable from the annotation.
- [ ] Keep annotation purely presentational; it must not change prediction rows.

### Phase 5 — Overlay default and robustness

- [ ] Set measured overlay default to hidden/off.
- [ ] Keep overlay controls available but visually secondary.
- [ ] Ensure no measured overlay request/filter is sent unless overlay is enabled.
- [ ] Keep overlay failure non-blocking for predicted sweep generation.

### Phase 6 — Backend and tests

- [ ] Add/adjust backend test proving simple visualisation predicts exactly `N` rows.
- [ ] Add/adjust backend test proving all non-swept fixed inputs are preserved exactly across sweep rows.
- [ ] Add/adjust backend test proving grouped compatibility does not affect the simple default path.
- [ ] Run focused backend test suite.

### Phase 7 — Verification and review

- [ ] Run `backend/.venv/bin/python -m pytest backend/tests/test_design_studio_contract.py -q`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Manually verify in browser:
  - select X and Y;
  - set valid range and points;
  - edit fixed values;
  - generate visualisation;
  - confirm one predicted curve/series per selected response, not grouped scenario curves;
  - switch axis orientation;
  - use annotation dropdown;
  - confirm overlay hidden by default;
  - export PNG.
- [ ] Final grep/review:
  - no new fuel-cell hardcoding;
  - no new public API route names;
  - no user-facing “recipe” terminology;
  - no accidental upstream pipeline changes.

## Verification commands

```bash
backend/.venv/bin/python -m pytest backend/tests/test_design_studio_contract.py -q
cd frontend && npm run build
```

## Acceptance criteria

- Experiment visualisation generates exactly `N` predictions for `N` sweep points.
- All non-swept inputs are fixed unless the user edits their fixed values.
- No default grouped curves or scenario abstractions are shown.
- Axis orientation control fits inside the layout and clearly states what will be plotted.
- Measured overlay is hidden by default.
- Optional plot annotation defaults to none and can show user-selected fixed parameters.
- Single-result prediction is separated from multi-point visualisation.
- Implementation remains generic and schema-driven with no fuel-cell-specific behavior.
