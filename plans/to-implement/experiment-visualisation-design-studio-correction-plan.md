# Corrected Plan: Experiment Visualisation Workflow in Design Studio

## Why this plan exists

The previous implemented direction was too shallow. It renamed parts of the current response-curve UI and added a few controls, but it did not fully implement the intent captured in the user answers:

- The UI still looks almost the same and still feels like the old response-curve panel.
- Internals still use `PlotRecipe`, `plot_recipe`, `selectedPlotRecipeId`, and related “recipe” language in many Design Studio code paths.
- The visualisation controls are crammed into one dense row rather than presenting a professional workflow for “generate multiple predicted points under fixed conditions.”
- Fixed inputs are shown mostly as badges from the current sliders, not as an explicit visualisation setup where non-swept inputs can be reviewed and edited for the multi-point run.
- Overlaying multiple curves by a fixed parameter exists only as a text field of comma-separated values, not an intuitive control with suggested initial values and clear curve-condition labels.
- The current implementation technically separates `Generate result` from `Generate visualisation`, but the user experience still does not clearly communicate the difference between single-point prediction, multi-point visualisation, and optimization.
- Placeholder field visualisation types were added, but they are not integrated into a clean professional concept.
- The code still leaks old response-curve/recipe vocabulary. User explicitly requested no “recipe” naming.

This corrected plan should guide a proper implementation, using the current Design Studio foundations but making the workflow genuinely usable and generic.

## User intent recap

The target is **not fuel-cell-specific plotting**. The target is a generic engineering workflow:

> Select a model, choose an input to sweep over a range, hold other inputs fixed, optionally generate multiple curves for different fixed-parameter values, and plot predicted responses using the project’s approved schema labels and units.

Fuel-cell polarization-style plots should emerge naturally from this workflow:

- sweep variable: voltage or current-related input, depending on the project schema;
- predicted response: current density or voltage-related output;
- fixed/grouped parameter: humidity, temperature, pressure, material, cell ID, etc.;
- multiple curves: different fixed values of that parameter.

The same workflow should support other engineering fields later:

- battery degradation vs cycle count at fixed temperature values;
- material performance vs process parameter at fixed composition;
- energy demand vs time/horizon at fixed weather/site scenario;
- any generic tabular DoE response sweep.

## Non-negotiable constraints

- Do not change intake, preprocessing, ML preprocessing, training, MLflow, champion loading, or upstream schema generation.
- Do not introduce new required schema fields or metadata contracts.
- Do not hardcode fuel-cell, battery, or forecasting domain knowledge.
- Do not implement derived objectives yet: no area under curve, slope, resistance, threshold crossing, degradation delta, etc.
- Keep optimization behavior simple: selected KPI / existing multi-KPI weights.
- Use the existing schema inputs/outputs, labels, units, min/max, and current model prediction APIs.
- Preserve current branding/layout structure, but make the Design Studio visualisation workflow materially clearer.
- Avoid the word “recipe” in UI and new internal naming.
- Public API routes should not be renamed.

## Current state comparison against user answers

| User answer / requirement | Current partial implementation | Gap |
| --- | --- | --- |
| Professional naming like “experiment visualisation,” not “recipe” | UI says “Experiment visualisation,” but code and types still use `PlotRecipe`, `plot_recipe`, `selectedPlotRecipeId`; UI still has “Starting setup” fed by recipe objects | Need introduce a Design-Studio-facing visualisation model and isolate legacy recipe compatibility behind adapters |
| Plot multiple points at fixed parameter(s) | Sweep exists; grouped curves via `curveGroupInputName` + comma text values | Needs explicit fixed-condition editor and a clearer multi-curve configuration UI |
| Avoid domain language; optionally name plot in UI | Plot title field exists | Needs plot title to become part of a coherent chart setup, not one field in a dense grid |
| Overlay multiple curves by fixed parameter | Text input for comma-separated values | Needs selectable suggested values, chips/table rows, and visible curve labels/condition cards |
| Default conventional axes but allow axis swapping | Axis swap checkbox exists | Needs clearer axis preview and labels so users understand “X = response, Y = swept variable” when swapped |
| Simple min/max range for MVP | Min/max exists | OK, but should be placed in a focused “Sweep” section with validation and range defaults |
| No hardcoded domain knowledge | Design Studio backend mostly generic now; domain metadata still contains fuel-cell plot definitions; frontend/API still use `PlotRecipe` | Do not change upstream domain metadata now, but Design Studio should consume only generic visualisation config/adapters and not depend on `fuel_cell_polarization` |
| Fixed params depend on functionality: one point doesn’t need it; multi-point does | Single-point and visualisation are separated technically | UI needs separate state: single-point input sliders vs visualisation fixed-condition setup, with an option to copy current slider values |
| Input count can vary: 4, 7, 10, etc. | Badges list all non-swept fixed inputs; dense with many inputs | Need scalable fixed-condition table/list, not badges only |
| Source of truth is intake/preprocessing labels/customization | Mostly uses schema labels/units | Preserve and make more visible; no new metadata required |
| Prediction/optimization should flow better but avoid hardcoding | Current workflows remain separate but feel bolted on | Need clearer framing: “single point,” “multi-point visualisation,” “optimization candidates” and handoffs between them |
| Keep optimization simple | Mostly unchanged | OK; ensure visualisation settings do not silently change optimization semantics |
| UI should not change drastically, but current changes are too minor | Current UI is visually similar with an added top control box | Need moderate restructuring inside Design Studio only: clearer sections, not app-wide redesign |
| Do not hide advanced controls yet | Current controls are visible | OK, but should be organized, not hidden |
| Placeholder future cases | Placeholder selector exists | Keep, but label as “visualisation mode” and show simple unavailable panel |
| No hardcoded domain knowledge | Some hardcoded domain terms still exist outside Design Studio and legacy naming remains | Scope removal to Design Studio consumption/new internals; do not mutate earlier pipeline unless strictly necessary |

## Target UX

Design Studio should keep the existing three-workflow structure but make each workflow purposeful:

1. **Experiment visualisation**
   - Main task: generate multiple predicted points.
   - Controls are organized around: title, sweep, response, fixed conditions, curve groups, measured overlay.
   - Button: **Generate visualisation**.
   - Output: plot + condition summary.

2. **Optimize candidates**
   - Main task: search candidate designs using selected KPI / weights.
   - Existing optimization controls remain mostly unchanged.
   - Candidate cards should offer: “Load into inputs” and optionally “Use as visualisation baseline.”

3. **Compare and package**
   - Main task: compare selected/generated candidate and export.
   - Existing behavior mostly preserved.

The single-point input sliders should remain visible in Design Studio, but the relationship should be explicit:

- **Generate result** = one prediction for current input sliders.
- **Generate visualisation** = many predictions from the visualisation setup.
- A visible action should copy current input slider values into the visualisation fixed-condition setup.

## Target experiment visualisation UI structure

### Section A: Visualisation mode

- Select:
  - `Generic experiment visualisation` — enabled.
  - `Electrochemical device visualisation` — feature not available yet.
  - `Battery degradation visualisation` — feature not available yet.
  - `Energy demand visualisation` — feature not available yet.
- If a placeholder is selected, show a plain unavailable state and disable generation.
- Do not implement domain behavior behind placeholders.

### Section B: Chart identity and axes

- Plot title input.
- Sweep variable dropdown from schema inputs.
- Predicted response dropdown from schema outputs.
- Optional second response dropdown.
- Axis orientation control with explicit preview:
  - Default: `X = sweep variable`, `Y = predicted response`.
  - Swapped: `X = predicted response`, `Y = sweep variable`.
- Axis labels must use approved labels and units.

### Section C: Sweep range

- Range min / range max / number of points.
- Defaults from selected input min/max and 60 points.
- Inline validation:
  - min/max must be numeric;
  - min and max can be swapped or normalized;
  - points clamped 10–200.
- Keep simple: no domain-region presets.

### Section D: Fixed conditions for multi-point visualisation

This is the biggest missing piece.

- Show every non-swept schema input in a compact table/list:
  - variable label/unit;
  - current visualisation value;
  - schema min/max;
  - action to copy from current experiment input slider.
- Values are editable in the visualisation setup, independent of the single-point sliders.
- Default visualisation fixed values initialize from current sliders or schema midpoints.
- This table must scale for 4, 7, 10+ inputs better than badges.
- This section is only for multi-point visualisation; single-point prediction continues to use the main input sliders.

### Section E: Multiple curves by fixed parameter

Generic implementation:

- Dropdown: choose one non-swept input as a curve grouping parameter.
- Value selection:
  - Suggested chips: schema min, current visualisation value, schema max.
  - If observed/training overlay values are available for that variable, optionally suggest those values too, but do not require this for MVP.
  - User can add/remove numeric values as chips/rows, not only comma text.
- Display resulting curve conditions clearly:
  - e.g. `Curve 1: Operating relative humidity = 40 %`
  - but labels/units come from schema, not hardcoded names.
- Generation logic: for each group value, sweep the sweep variable and keep all other fixed-condition values constant.

### Section F: Measured training overlay

Reuse existing overlay infrastructure, but improve clarity:

- Keep overlay controls visible.
- Label as `Measured training overlay`.
- Explicitly distinguish:
  - predicted curves = served model predictions;
  - markers = observed values from `predictions.csv` `*_true` columns.
- Overlay filters/ranges remain generic and sourced from available columns.
- Overlay grouping remains optional.

### Section G: Visualisation output

- Plot title from user setting.
- Condition summary above/below chart:
  - sweep variable/range;
  - predicted responses;
  - fixed conditions;
  - curve grouping values if any.
- Legend labels include response label + group value when grouped.
- Plot should still support exported PNG.

## Target internal architecture

### New Design Studio terminology layer

Do not rewrite public routes. Do introduce Design-Studio-internal naming:

- `ExperimentVisualisationConfig`
- `ExperimentVisualisationAxis`
- `ExperimentVisualisationState`
- `buildExperimentVisualisationPayload(...)`
- `generate_experiment_visualisation(...)` or `_experiment_visualisation_rows(...)`

Legacy compatibility may remain at the API boundary temporarily:

- Existing response keys like `curve` can remain if changing them is too risky.
- Existing request fields like `plot_recipe` can be accepted temporarily, but new frontend code should not be organized around them.
- Add comments marking legacy names as compatibility aliases.

### Backend behavior

Implement the backend as generic row generation:

Input:

- base input values / fixed condition values;
- sweep variable;
- min/max/points;
- response variables;
- optional group variable;
- group values.

Process:

1. Validate sweep variable is a schema input.
2. Validate response variables are schema outputs.
3. Validate fixed/group variables are schema inputs and not equal to sweep variable.
4. Build rows:
   - no group: `points` rows;
   - grouped: `points * group_values.length` rows.
5. Call `predict_rows` once for all rows.
6. Return rows with:
   - swept value;
   - predicted response values;
   - group variable/value if present.

No domain-specific variable names.

### Frontend behavior

Keep DesignStudioPage if necessary for MVP, but structure state clearly:

- `singlePointInputs` can remain as `inputs`.
- Add `visualisationFixedInputs` separate from `inputs`.
- Add helper to initialize/sync visualisation fixed inputs from current inputs.
- Rename new helpers away from `recipe*` naming.
- Keep legacy type imports contained or replace frontend-facing `PlotRecipe` usage with local `ExperimentVisualisationPreset` adapter.

## Implementation phases

### Phase 0: Freeze and assess current partial implementation

**Description:** Establish whether to build on the current uncommitted implementation or partially revert pieces that are misleading.

**Acceptance criteria:**
- [ ] Confirm current working-tree diff for `DesignStudioPage.tsx`, `design_studio.py`, `frontend/src/lib/api.ts`, and `backend/tests/test_design_studio_contract.py`.
- [ ] Identify which pieces are worth keeping: separate generate actions, basic sweep range, generic backend sweep, grouped prediction rows.
- [ ] Identify pieces to replace: dense top control grid, comma-only group values, recipe-centric state names, fixed inputs as badges only.

**Verification:**
- [ ] `git diff -- frontend/src/components/DesignStudioPage.tsx backend/app/services/design_studio.py frontend/src/lib/api.ts backend/tests/test_design_studio_contract.py` reviewed.

**Dependencies:** None.

**Files likely touched later:** None in this phase; read-only.

### Phase 1: Define the Design-Studio-facing visualisation contract

**Description:** Introduce a local/internal contract for experiment visualisation so the UI and backend are not mentally organized around plot recipes.

**Acceptance criteria:**
- [ ] New frontend-facing types use `ExperimentVisualisation...` naming.
- [ ] New backend helper names use `experiment_visualisation` naming.
- [ ] Legacy `plot_recipe` / `curve` names are either isolated at API boundaries or explicitly documented as compatibility aliases.
- [ ] No user-facing “recipe” wording remains in Design Studio.

**Verification:**
- [ ] Grep new/changed Design Studio code for user-facing `recipe` text returns none.
- [ ] Frontend build still passes.

**Dependencies:** Phase 0.

**Files likely touched:**
- `frontend/src/components/DesignStudioPage.tsx`
- `frontend/src/lib/api.ts`
- `backend/app/services/design_studio.py`

### Phase 2: Separate single-point state from visualisation fixed-condition state

**Description:** Make `Generate result` and `Generate visualisation` truly distinct. Single-point prediction uses current sliders; visualisation uses its own fixed-condition setup initialized from sliders.

**Acceptance criteria:**
- [ ] Single-point sliders remain the source for `Generate result`.
- [ ] Experiment visualisation has its own fixed values for all non-swept inputs.
- [ ] A visible action copies current slider values into visualisation fixed conditions.
- [ ] Changing a single-point slider marks both result/visualisation as stale appropriately but does not silently mutate already generated plot data.
- [ ] Sweep variable is excluded from fixed conditions.

**Verification:**
- [ ] Manual: change current inputs, generate result only, previous plot does not silently update.
- [ ] Manual: copy current inputs into visualisation setup, generate visualisation, plot reflects copied values.

**Dependencies:** Phase 1.

**Files likely touched:**
- `frontend/src/components/DesignStudioPage.tsx`

### Phase 3: Replace dense controls with a professional visualisation setup panel

**Description:** Rework only the Experiment visualisation section layout so it feels like a workflow, not a renamed response-curve row.

**Acceptance criteria:**
- [ ] Visualisation mode, chart/axes, sweep range, fixed conditions, curve groups, and measured overlay are separate labeled subsections.
- [ ] The setup remains visible; no advanced controls hidden.
- [ ] The layout handles 4–10+ inputs without unreadable badges.
- [ ] Labels/units use existing schema labels/units.
- [ ] Current branding and card style are preserved.

**Verification:**
- [ ] Frontend build passes.
- [ ] Browser/manual check on current fuel-cell demo and a generic schema if available.

**Dependencies:** Phase 2.

**Files likely touched:**
- `frontend/src/components/DesignStudioPage.tsx`

### Phase 4: Implement intuitive multi-curve fixed-parameter controls

**Description:** Replace comma-separated group values as the primary UX with chips/rows and suggested values.

**Acceptance criteria:**
- [ ] User can select a non-swept input as the curve grouping parameter.
- [ ] Suggested values appear from schema min/current/max.
- [ ] User can add/remove up to 5 numeric group values as visible chips/rows.
- [ ] Each generated curve is clearly labeled with schema label/unit and group value.
- [ ] No hardcoded assumptions about RH, temperature, voltage, current, battery cycle count, etc.

**Verification:**
- [ ] Manual: choose an input with min/current/max and generate 3 curves.
- [ ] Manual: remove one value and regenerate; legend/condition summary updates.
- [ ] Backend test covers grouped rows with arbitrary variable names.

**Dependencies:** Phase 3.

**Files likely touched:**
- `frontend/src/components/DesignStudioPage.tsx`
- `backend/app/services/design_studio.py`
- `backend/tests/test_design_studio_contract.py`

### Phase 5: Backend generic visualisation generation hardening

**Description:** Make the backend generic sweep/group implementation robust and independent of legacy plot-recipe assumptions.

**Acceptance criteria:**
- [ ] Backend accepts/constructs generic experiment visualisation config from payload.
- [ ] Validation is schema-based only: inputs/outputs/min/max/points/group values.
- [ ] Invalid config returns a clear API-safe warning/error without hardcoded domain terms.
- [ ] `predict_rows` is still the only prediction path.
- [ ] Existing optimization and export behaviors continue to work.

**Verification:**
- [ ] Backend tests for arbitrary variable names: `x1`, `condition`, `y1`.
- [ ] Backend tests for 4+ inputs where only one is swept and others are fixed.
- [ ] Backend tests for grouped visualisation row counts.

**Dependencies:** Phase 1; can run partly in parallel with Phase 3 after contract is defined.

**Files likely touched:**
- `backend/app/services/design_studio.py`
- `backend/tests/test_design_studio_contract.py`

### Phase 6: Clarify plot output and condition summary

**Description:** Make the generated chart communicate exactly what was generated.

**Acceptance criteria:**
- [ ] Chart title uses user-provided plot title.
- [ ] Axis labels are correct for default and swapped orientations.
- [ ] Condition summary lists sweep range, fixed inputs, and group values.
- [ ] Legend labels include group value when grouped.
- [ ] Predicted lines and measured overlay markers remain visually distinct.

**Verification:**
- [ ] Manual: default axes and swapped axes both make sense.
- [ ] Manual: grouped curves have unambiguous legend labels.
- [ ] Manual: PNG export still captures the intended plot.

**Dependencies:** Phases 3–5.

**Files likely touched:**
- `frontend/src/components/DesignStudioPage.tsx`

### Phase 7: Keep placeholder engineering cases but avoid domain implementation

**Description:** Retain future mode placeholders as proof of extensibility without building hidden domain logic.

**Acceptance criteria:**
- [ ] Placeholder modes are clearly unavailable.
- [ ] Selecting a placeholder disables generation and shows a plain message.
- [ ] No placeholder mode changes the backend payload or applies hardcoded field behavior.

**Verification:**
- [ ] Manual: select each placeholder; UI remains stable and no request is sent.

**Dependencies:** Phase 3.

**Files likely touched:**
- `frontend/src/components/DesignStudioPage.tsx`

### Phase 8: Preserve optimization and handoff flow

**Description:** Ensure optimization remains simple but fits the improved visualisation workflow.

**Acceptance criteria:**
- [ ] Existing selected-KPI/custom-weight optimization behavior remains unchanged.
- [ ] Loading an optimized candidate updates the single-point inputs.
- [ ] User can then copy those inputs into visualisation fixed conditions if desired.
- [ ] No area-under-curve or field-specific objectives are introduced.

**Verification:**
- [ ] Existing optimization manual flow works.
- [ ] Backend tests covering recommendation/design studio still pass.

**Dependencies:** Phase 2.

**Files likely touched:**
- `frontend/src/components/DesignStudioPage.tsx`
- `backend/app/services/design_studio.py` only if needed for compatibility.

### Phase 9: Cleanup legacy vocabulary within Design Studio scope

**Description:** Remove or isolate legacy “recipe” naming where it affects Design Studio readability, without touching upstream pipeline contracts unnecessarily.

**Acceptance criteria:**
- [ ] New frontend helpers/components do not use `recipe` naming.
- [ ] New backend helpers do not use `recipe` naming.
- [ ] Any remaining `plot_recipe` references are limited to compatibility adapters/API response parsing.
- [ ] No Design Studio code branches on `fuel_cell_polarization` or hardcoded fuel-cell variable names.
- [ ] Do not edit intake/preprocessing/training behavior.

**Verification:**
- [ ] `grep` confirms no `fuel_cell_polarization` references in `frontend/src/components/DesignStudioPage.tsx` or `backend/app/services/design_studio.py`.
- [ ] `grep` confirms `recipe` references are compatibility-only or removed from Design Studio code.

**Dependencies:** Phases 1–8.

**Files likely touched:**
- `frontend/src/components/DesignStudioPage.tsx`
- `frontend/src/lib/api.ts`
- `backend/app/services/design_studio.py`

## Testing and verification plan

### Automated checks

- [ ] Backend focused tests:
  - `backend/.venv/bin/python -m pytest backend/tests/test_design_studio_contract.py -q`
- [ ] Frontend build:
  - `cd frontend && npm run build`

### Manual checks

Use the current loaded champion/demo project:

- [ ] Generate a single result; KPI cards update without requiring visualisation generation.
- [ ] Generate a visualisation by sweeping one input with all other inputs fixed.
- [ ] Change fixed-condition values in the visualisation setup without changing single-point sliders.
- [ ] Overlay multiple predicted curves by one fixed input value list.
- [ ] Switch axes and confirm labels/legend remain clear.
- [ ] Enable measured training overlay and confirm markers remain distinct from predictions.
- [ ] Select unavailable placeholder modes and confirm generation is disabled.
- [ ] Run optimization and load a candidate; confirm visualisation can be regenerated from copied candidate values.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Over-refactoring DesignStudioPage | High | Keep route/API stable; extract only small local helpers if needed; avoid app-wide changes |
| Breaking current working fuel-cell demo | High | Use schema-driven controls; manually verify current demo after each phase |
| Keeping too much legacy recipe vocabulary | Medium | Isolate old names at compatibility boundary and document them |
| UI becomes too complex for MVP | Medium | Keep all controls visible but grouped into clear sections; no derived objectives or domain presets |
| Grouped curves produce too many prediction rows | Medium | Cap group values to 5 and points to 200 |
| Fixed-condition state diverges confusingly from single-point inputs | Medium | Add explicit “copy current inputs” action and stale-state messaging |

## Agent and skill mapping

This mapping follows `AGENTS.md`: use available configured agents and relevant skills for concrete tasks. The implementation should not blindly run all agents; use them where their role adds value.

### Phase-by-phase ownership

| Phase | Primary owner | Review / support agent | Skills to apply | Notes |
| --- | --- | --- | --- | --- |
| Phase 0: Freeze and assess current partial implementation | main agent | `scout` if available | `planning-and-task-breakdown`, `source-driven-development` | Read-only diff review. Recent `scout` attempts failed, so main agent may need to perform discovery directly. |
| Phase 1: Define visualisation contract | main agent | `reviewer` for contract sanity check | `api-and-interface-design`, `code-simplification`, `deprecation-and-migration` | Keep public routes stable while introducing `ExperimentVisualisation...` naming internally. |
| Phase 2: Separate single-point and visualisation state | main agent | optional `reviewer` | `frontend-ui-engineering`, `scientific-ui-clarity`, `incremental-implementation` | Critical UX change: `Generate result` and `Generate visualisation` must no longer share confusing state. |
| Phase 3: Restructure visualisation setup panel | main agent | `reviewer` after first UI diff | `frontend-ui-engineering`, `scientific-ui-clarity` | Make the UI materially clearer without app-wide redesign. |
| Phase 4: Multi-curve fixed-parameter controls | main agent | optional `reviewer` for usability | `frontend-ui-engineering`, `scientific-ui-clarity`, `api-and-interface-design` | Replace comma-only group values with chips/rows and suggested values. |
| Phase 5: Backend generic row generation | main agent | `reviewer` for domain-hardcoding check | `api-and-interface-design`, `test-driven-development`, `code-simplification` | Schema-driven only; no fuel-cell/battery/forecasting branches. |
| Phase 6: Plot output and condition summary | main agent | optional `reviewer` | `frontend-ui-engineering`, `scientific-ui-clarity`, `browser-testing-with-devtools` | Ensure chart labels, legends, overlays, and PNG export are understandable. |
| Phase 7: Placeholder engineering cases | main agent | none unless behavior expands | `frontend-ui-engineering`, `incremental-implementation` | Keep placeholders unavailable; do not add domain implementations. |
| Phase 8: Preserve optimization handoff | main agent | `reviewer` if optimization code changes | `api-and-interface-design`, `regression-testing`, `code-simplification` | Optimization should remain selected-KPI/current-weight behavior. |
| Phase 9: Cleanup legacy vocabulary | main agent | `reviewer` final pass | `deprecation-and-migration`, `code-simplification`, `code-review-and-quality` | Remaining `plot_recipe` names should be compatibility-only. |
| Final verification | main agent | `reviewer`; `oracle` only if scope drift or architecture concern remains | `debugging-and-error-recovery`, `browser-testing-with-devtools`, `code-review-and-quality` | Run focused backend tests, frontend build, and manual browser checks. |

### Agent roles

- `scout` — read-only reconnaissance: compare current code against the plan, locate existing helpers, and flag hardcoded domain assumptions. Use only if available; recent attempts returned connection errors.
- `reviewer` — focused review after meaningful diffs: check UX clarity, API compatibility, test coverage, and absence of domain hardcoding.
- `planner` — optional only if the approved plan needs to be split into a smaller execution checklist before coding.
- `worker` — optional implementation handoff after approval, but only with this plan as the source of truth.
- `oracle` — optional high-stakes review if there is a disagreement about architecture, scope, or whether to preserve/revert parts of the current uncommitted implementation.

### Skill roles

- `planning-and-task-breakdown` — keep implementation phased and acceptance-criteria driven.
- `frontend-ui-engineering` — restructure the panel into a production-quality UI while preserving Mirai styling.
- `scientific-ui-clarity` — ensure sweep/fixed-condition/grouped-curve concepts are understandable to engineering users without domain-specific explanations.
- `api-and-interface-design` — define stable frontend/backend payload boundaries and compatibility aliases.
- `code-simplification` — avoid overengineering while cleaning up legacy `recipe` mental model.
- `deprecation-and-migration` — isolate old `plot_recipe` / `curve` terms without risky public route renames.
- `test-driven-development` — add/adjust backend contract tests around generic arbitrary variable names, fixed inputs, and grouped row counts.
- `browser-testing-with-devtools` — manually verify the Design Studio UX, chart labels, overlay behavior, and PNG export.
- `code-review-and-quality` — final diff review before commit/deploy.

## Out of scope

- No upstream schema/metadata redesign.
- No domain-specific fuel-cell, battery, or forecasting logic.
- No field-specific engineering explanations or curve-region detection.
- No new optimization objectives beyond selected output / existing weighted outputs.
- No changes to training, MLflow, champion loading, package export, or preprocessing.
- No public route renaming.

## Approval gate

Before implementation, confirm explicitly:

- This plan should replace the previous shallow plan.
- Current uncommitted implementation may be revised rather than preserved exactly.
- The first implementation phase should focus on making the visualisation setup/fixed-condition workflow materially clearer, not only renaming internals.
