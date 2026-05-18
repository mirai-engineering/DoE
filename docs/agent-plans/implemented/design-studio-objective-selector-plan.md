# Design Studio Objective Selector and Scientist Guidance Plan

## Context

The Design Studio now provides an interactive playground where scientists can move schema-driven inputs, seed a candidate from batch search, see served-model predictions, inspect predicted polarization curves, compare against measured cells, and export a design package.

However, the current `Seed from best batch search` behavior is not transparent enough for non-ML users. It currently uses the project default objective:

```text
maximize BoL current density
```

That means the app searches many candidate configurations, predicts each candidate with the active model, scores them by predicted BoL current density, and loads the highest-scoring candidate into the sliders. This is useful, but the user cannot yet change what “best” means from the UI.

Scientists need to choose objectives such as:

```text
maximize BoL current density
maximize EoL current density
minimize ECSA loss
balanced BoL/EoL/degradation tradeoff
custom weighted objective
```

The UI should explain this in plain language:

> “Seed from best batch search tries many virtual candidates and loads the one that scores best for your selected goal. It is a model-guided starting point, not a guaranteed lab optimum.”

## Approach

Add an objective selector/weight panel to Design Studio. Keep it schema-driven so future projects automatically adapt to their own output names, units, and optimization directions.

The first implementation should support:

1. Single-output objective presets generated from `schema.outputs`:
   - `Maximize {output label}` for maximize outputs
   - `Minimize {output label}` for minimize outputs

2. A fuel-cell balanced preset:
   - maximize BoL current density
   - maximize EoL current density
   - minimize ECSA loss

3. Custom weights:
   - one editable numeric weight per output
   - positive weights favor larger values
   - negative weights favor smaller values
   - zero excludes the output from the score

4. Plain-language explanation of batch search:
   - what it samples
   - what the model predicts
   - how the score is computed
   - why it is not a guaranteed global optimum
   - why scientist review is still required

## Files to modify

Frontend:

```text
frontend/src/components/DesignStudioPage.tsx
```

Optional API type refinements:

```text
frontend/src/lib/api.ts
```

Backend, if needed for richer response metadata:

```text
backend/app/services/design_studio.py
```

Docs:

```text
docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md
```

Tests:

```text
backend/tests/test_real_fuel_cell_data_pipeline.py
```

## Reuse

Reuse existing backend behavior:

```text
POST /projects/{project_id}/design-studio/seed/batch
```

It already accepts `objective_weights`, so most of this work is frontend and copy/UI.

Reuse schema metadata:

```text
schema.outputs[].name
schema.outputs[].label
schema.outputs[].unit
schema.outputs[].direction
```

Reuse current Design Studio state:

```text
state.default_objective_weights
```

## Step 1 — Add objective mode state

In `DesignStudioPage.tsx`, add state for:

```ts
objectiveMode: string
objectiveWeights: Record<string, string>
```

Initialize from:

```text
state.default_objective_weights
```

Default for fuel-cell project remains:

```text
bol_current_density: 1.0
```

## Step 2 — Generate schema-driven objective presets

Create objective presets from `schema.outputs`:

For each maximize output:

```text
Maximize {output.label}
weights: { [output.name]: 1.0 }
```

For each minimize output:

```text
Minimize {output.label}
weights: { [output.name]: -1.0 }
```

Add a fuel-cell-specific balanced preset only when the outputs exist:

```text
Balanced fuel-cell performance
weights:
  bol_current_density: 0.40
  eol_current_density: 0.40
  ecsa_loss: -0.20
```

Keep implementation generic by checking for output names rather than assuming the project always has them.

## Step 3 — Add objective panel UI

Add a new card near the top/left of Design Studio:

```text
Optimization goal
```

Plain-language copy:

```text
Choose what “best” means before seeding from batch search. The app will try many virtual candidates, predict each one with the active model, and load the highest-scoring candidate into the playground.
```

Controls:

```text
Objective preset dropdown
Custom weights toggle/details
```

Dropdown examples for current project:

```text
Maximize BoL current density
Maximize EoL current density
Maximize BoL ECSA
Minimize ECSA loss
Balanced fuel-cell performance
Custom weights
```

## Step 4 — Add custom weights editor

If `Custom weights` is selected, show one row per output:

```text
BoL current density    [ +1.0 ]   A/cm²   maximize
EoL current density    [ +0.0 ]   A/cm²   maximize
BoL ECSA               [ +0.0 ]   m²/gPt  maximize
ECSA loss              [ -0.0 ]   fraction minimize
```

Help text:

```text
Positive weights reward larger predictions. Negative weights reward smaller predictions. Zero means this output is ignored in the batch-search score.
```

## Step 5 — Pass selected objective to batch seed endpoint

Update `seedFromBatch()` to send current objective weights:

```ts
objective_weights: selectedObjectiveWeights
```

The button remains generic:

```text
Seed from best batch search
```

But add nearby text:

```text
Current goal: Maximize BoL current density
```

## Step 6 — Explain seed result

After a batch seed response, show a small explanation card:

```text
Why this candidate?
This candidate had the highest model score among 3,000 sampled virtual candidates for the selected goal: Maximize BoL current density.
```

Include:

```text
sample count
objective weights
score
model version
```

Plain-language warning:

```text
This is a model-guided starting point. It should be checked against Model Quality diagnostics and reviewed by a scientist before lab execution.
```

## Step 7 — Improve live prediction guidance

Add friendly explanatory copy near output cards:

```text
These cards are not measurements. They are predictions from the active served model for the current slider settings.
```

Add per-card labels:

```text
Higher is better
Lower is better
```

based on `schema.outputs[].direction`.

## Step 8 — Add tutorial updates

Update:

```text
docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md
```

Add sections:

```text
What does Seed from best batch search mean?
How to choose an optimization goal
How custom weights work
Why the result is a starting point, not a guaranteed optimum
```

## Step 9 — Verification

Frontend:

```bash
cd frontend
npm run build
```

Backend smoke check if backend response metadata changes:

```bash
cd backend
uv run pytest tests/test_real_fuel_cell_data_pipeline.py tests/test_api.py
```

Manual checks:

- Design Studio has an Optimization goal panel.
- Presets are generated from schema outputs.
- Fuel-cell balanced preset appears only when needed outputs exist.
- `Seed from best batch search` uses selected weights.
- Result explanation shows sample count, goal, score, and model version.
- Custom weights can target EoL current density or ECSA loss.
- Existing live sliders, curve, comparison, and ZIP export still work.

## Suggested meaningful playground additions after this

These are not all required in the objective-selector implementation, but they would make the playground more compelling.

### 1. 2D response surface heatmap

Let users choose:

```text
x variable
y variable
color target output
```

All other variables stay fixed by the sliders.

Example for fuel cells:

```text
x = Pt/C ratio
y = I/C ratio
color = predicted BoL current density
```

This would make the page feel even closer to TensorFlow Playground.

### 2. Local sensitivity chart

Show which knobs matter most near the current candidate using small finite-difference perturbations:

```text
Most influential variables near this design:
1. operating_voltage
2. i_c_ratio
3. ast_upl
```

This is very useful for scientists asking, “What should I tune?”

### 3. Candidate trail/history

Keep recent designs:

```text
Candidate A → Candidate B → Candidate C
```

Allow users to restore, compare, or export previous candidates.

### 4. In-domain / extrapolation meter

Show whether the current design is:

```text
Interpolating
Near training edge
Outside observed domain
```

This would build trust and prevent overconfident use of the model.

### 5. Pareto candidates panel

For multi-objective tradeoffs, show several candidates rather than one “best”:

```text
High BoL current density
High EoL retention
Low ECSA loss
Balanced tradeoff
```

### 6. “Lab readiness” checklist

Before export, show:

```text
Model Quality reviewed?
Inside training domain?
Compared with measured cell?
Objective weights documented?
Scientist approved?
```

This would make the software feel like a real R&D decision-support tool, not just a plotting app.
