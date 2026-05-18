# Design Studio Generate Result Workflow Plan

## Context

The Design Studio currently auto-runs predictions when the user changes input sliders/numeric values. Technically this already updates:

- predicted output cards
- dynamic fuel-cell polarization curve
- measured real-cell overlay, if selected

However, the UX is not clear enough for scientists. It can feel like the polarization curve only changes when using optimization actions such as:

```text
Find best starting design
Find tradeoff candidates → Load
```

The user proposed a clearer explicit workflow:

```text
Adjust experiment inputs → Generate result → show/update the existing Dynamic response curve panel
```

This is a good product decision because it separates three concepts:

1. `Generate result`
   - evaluate the currently selected input composition/design
2. `Find best starting design`
   - search for one high-scoring candidate using selected objective weights
3. `Find tradeoff candidates`
   - search for multiple Pareto-style alternatives using selected objective weights

## Recommendation

Implement an explicit **Generate result** button for the currently selected input composition.

Change the UX so manual slider/numeric edits mark the design as changed, but do not immediately overwrite the generated result. The result updates when the user clicks:

```text
Generate result
```

The existing `Dynamic response curve` panel remains the place where the generated result is shown.

## Files to modify

```text
frontend/src/components/DesignStudioPage.tsx
```

Optional tutorial update:

```text
docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md
docs/tutorials/DESIGN_STUDIO_OBJECTIVES_AND_PARETO_MATH.md
```

No backend changes required because the existing endpoint already supports evaluating the current inputs:

```text
POST /projects/{project_id}/design-studio/predict
backend/app/services/design_studio.py::predict_design
```

## Current implementation details

Current auto-update effect:

```tsx
useEffect(() => {
  if (!state) return
  const handle = window.setTimeout(() => runPrediction(), 350)
  return () => window.clearTimeout(handle)
}, [inputs, selectedRealCell, state?.project_id])
```

This should be changed so manual input edits do not automatically call `runPrediction()`.

Existing functions to reuse:

```tsx
runPrediction(nextInputs = numericInputs)
seedFromBatch()
loadParetoCandidate(candidate)
exportZip()
```

## Approach

### 1. Add dirty-state tracking

Add frontend state:

```tsx
const [hasPendingInputChanges, setHasPendingInputChanges] = useState(false)
```

When an input slider or numeric field changes:

```tsx
setInputs(...)
setHasPendingInputChanges(true)
```

This tells the user that the currently displayed curve/output cards may no longer match the latest slider values.

### 2. Replace auto-prediction on input edits

Remove or narrow the auto-prediction effect.

Recommended behavior:

- On initial page load: run one prediction after state/default inputs load, so the page is not empty.
- On input changes: do not auto-run prediction.
- On selected real-cell overlay change: either
  - update immediately using current generated inputs, or
  - require `Generate result` again.

Recommendation: when real-cell overlay changes, re-run prediction for the current inputs because it only changes overlay data and keeps the curve context fresh.

Implementation option:

```tsx
useEffect(() => {
  if (!state) return
  runPrediction()
}, [selectedRealCell])
```

but avoid depending directly on `inputs`.

### 3. Add `Generate result` button in Experiment inputs section

Place it in the `Experiment inputs` section header or footer.

Suggested copy:

```text
Generate result
```

Button behavior:

```tsx
onClick={() => runPrediction()}
```

After successful prediction:

```tsx
setHasPendingInputChanges(false)
```

Button state:

- primary green/black button
- disabled while `predicting`
- text changes to `Generating...` while loading

### 4. Add pending-change status text

In the `Experiment inputs` section, show a small status badge:

If changes are pending:

```text
Inputs changed — click Generate result to update predictions and curve.
```

If result is current:

```text
Result current for shown inputs.
```

If no prediction exists yet:

```text
No result generated yet.
```

### 5. Keep search actions behavior

`Find best starting design` should still:

1. search using selected objective weights
2. load the candidate into sliders
3. set prediction from backend response
4. clear pending changes

Update `seedFromBatch()`:

```tsx
setHasPendingInputChanges(false)
```

after setting prediction and inputs.

`Load` Pareto candidate should still:

1. load candidate inputs
2. call `runPrediction(candidate.inputs)`
3. clear pending changes

Update `loadParetoCandidate()` similarly.

### 6. Clarify copy around objective/search vs result generation

Add explanatory copy in the Design objective card:

```text
Objective settings affect search actions only. To evaluate the current slider values, use Generate result in Experiment inputs.
```

Add explanatory copy in Experiment inputs:

```text
Manual edits do not change the shown curve until you generate a result.
```

This prevents confusion between optimization variables and current composition evaluation.

### 7. Dynamic response curve empty/pending state

Update existing empty-state copy:

From:

```text
No response curve is available yet. Click Find best starting design or adjust a design variable to generate served-model predictions.
```

To:

```text
No response curve is available yet. Click Generate result to evaluate the current inputs, or Find best starting design to let the model choose a candidate.
```

If `hasPendingInputChanges` is true and a previous curve exists, show an amber notice above the curve:

```text
Inputs have changed since this curve was generated. Click Generate result to refresh the predicted KPIs and polarization curve.
```

### 8. Update tutorials

Update `DESIGN_STUDIO_PLAYGROUND.md`:

- Add `Generate result` as the manual evaluation path.
- Clarify that objective mix affects search, not manual prediction.

Update `DESIGN_STUDIO_OBJECTIVES_AND_PARETO_MATH.md`:

- Clarify the distinction between:
  - direct prediction `f(x)` from `Generate result`
  - weighted search over candidates from `Find best starting design`
  - Pareto frontier from `Find tradeoff candidates`

## Verification

Run:

```bash
cd frontend
npm run build
```

Manual browser checks:

1. Open Design Studio.
2. Initial/default result appears or can be generated.
3. Move a slider.
4. Confirm output cards/curve do **not** silently change immediately.
5. Confirm pending-change message appears.
6. Click `Generate result`.
7. Confirm predicted output cards and dynamic response curve update.
8. Click `Find best starting design`.
9. Confirm sliders, output cards, and curve update; pending state clears.
10. Run `Find tradeoff candidates`, load a candidate.
11. Confirm sliders, output cards, and curve update; pending state clears.
12. Change measured real-cell overlay and confirm behavior is clear.
13. Export still works.

## Acceptance criteria

- Scientists have a clear manual evaluation action: `Generate result`.
- The existing Dynamic response curve panel displays the generated result.
- Objective settings are clearly understood as search settings, not required for manual evaluation.
- Search and Pareto workflows remain intact.
- No backend changes are needed.
