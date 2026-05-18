# Model Quality UI Readability Redesign Plan

## Context

The current Model Quality page contains a `PER-OUTPUT ACCURACY` section implemented in:

```text
frontend/src/components/ModelQualityPage.tsx
```

The current section title is generated as:

```text
${bestModelName || 'Best model'} validation/test detail
```

It renders validation and test as two large split cards, then shows every per-output metric with equal weight:

- R²
- RMSE
- MAE
- nRMSE
- MAE/mean
- RMSE/range
- Baseline MAE
- baseline improvement
- scientist summary
- R² notes

The data is useful, but the presentation reads like a debug/model report. A scientist/user should first see whether the surrogate is trustworthy, then inspect detailed metrics only if needed.

Existing frontend helpers available in `ModelQualityPage.tsx`:

- `asRecord`
- `asNumber`
- `asString`
- `formatPercent`
- `formatNumber`

Existing UI primitives available in `frontend/src/components/ui.tsx`:

- `PanelHeader`
- `Alert`
- shared card styling conventions

Existing data source:

```text
getModelQualitySummary(schema.project_id)
```

The `ModelQualitySummary.metrics` object already contains the validation/test per-output metrics needed for this redesign, so no backend/model changes are required.

## Approach

Redesign only the `PER-OUTPUT ACCURACY` section of `ModelQualityPage.tsx` into a decision-support view:

1. Keep existing model-quality API contract and metric calculations unchanged.
2. Add frontend-only helpers to classify output trust from existing test metrics.
3. Replace the current dense validation/test split cards with:
   - top-level surrogate trust summary,
   - responsive grid of per-output KPI cards,
   - primary test metrics at high visual priority,
   - compact validation-vs-test comparison,
   - expandable secondary metrics.
4. Keep all existing metrics available in the UI, but move secondary metrics behind `<details>` controls.
5. Add a TODO-compatible objective-weight warning hook without fetching new backend state.

## Files to modify

Primary file:

```text
frontend/src/components/ModelQualityPage.tsx
```

Potential supporting file, only if the component becomes too large:

```text
frontend/src/lib/modelQualityTrust.ts
```

No backend files should be modified for this task.

## Reuse

Reuse existing functions/data:

- `getModelQualitySummary` from `frontend/src/lib/api.ts`
- `ProjectSchema.outputs` for output labels and units
- existing `metrics.models[bestModelName].splits.validation/outputName`
- existing `metrics.models[bestModelName].splits.test/outputName`
- `PanelHeader` and existing rounded card styles from `frontend/src/components/ui.tsx`
- `formatNumber` from `frontend/src/lib/doeUtils.ts`

## Recommended UI structure

### 1. Section heading

Change the section from:

```text
PER-OUTPUT ACCURACY
mlp validation/test detail
```

to:

```text
PER-OUTPUT ACCURACY
Surrogate model accuracy
Validation and test metrics for each predicted output. Use this page to judge how much to trust optimization recommendations.
```

Keep the eyebrow `PER-OUTPUT ACCURACY`.

### 2. Top-level trust summary

Add a summary card at the top of the section.

Inputs:

- best model validation/test split data
- schema outputs
- trust classifications derived from test metrics

Display:

- overall surrogate quality label: `Good`, `Medium`, `Weak`, or `Needs review`
- count of usable-or-strong outputs
- count of weak outputs
- best-predicted output
- weakest-predicted output
- deterministic one- or two-sentence summary

Example copy pattern:

```text
Surrogate trust summary
3 of 4 outputs show usable test performance. Current-density predictions are strong; BoL ECSA is weaker and should be treated with caution in optimization.
```

Use test metrics for the main summary. Validation metrics should not drive the top-line verdict.

### 3. Centralized trust helper

Add a helper function near the top of the component file, or in `frontend/src/lib/modelQualityTrust.ts` if the logic becomes large.

Suggested shape:

```ts
type TrustLevel = 'strong' | 'usable' | 'weak' | 'needs_review'

function classifyOutputTrust(metrics: Record<string, unknown>): {
  level: TrustLevel
  label: string
  reason: string
  sortScore: number
}
```

Suggested thresholds:

- `Strong`: test R² >= 0.75 and MAE/mean <= 20%
- `Usable`: test R² >= 0.50 or MAE/mean <= 30%
- `Weak`: test R² < 0.50 and MAE/mean > 30%
- `Needs review`: missing/non-finite metrics or undefined R² with insufficient substitute evidence

Use `mae_percent_of_split_mean` for MAE/mean because the backend already reports it as a percentage value.

Handle negative or near-zero R² explicitly:

- R² <= 0.05 should produce cautionary copy even if another metric looks passable.
- Missing R² should not crash; use MAE/mean and `r2_note` to form a `Needs review` or `Weak` state.

### 4. Per-output KPI cards

Render one card per output in a responsive grid.

Each card should show:

- output label
- trust badge: `Strong`, `Usable`, `Weak`, or `Needs review`
- 3–4 primary test metrics only:
  - Test R²
  - Test MAE with unit
  - Test MAE/mean
  - baseline improvement
- short deterministic interpretation

Example card copy:

```text
BoL current density
Strong
Test R² 0.860
Test MAE 0.331 A/cm²
Error vs mean 29.1%
Baseline improvement 69.1%

The model captures most of the variation for this KPI and substantially improves over a train-mean baseline.
```

For weak or near-zero/negative R² outputs, use cautionary copy:

```text
This output performs close to or worse than a simple baseline. Avoid using it as a dominant optimization objective until the model improves.
```

### 5. Validation vs test comparison

Inside each output card, add a compact side-by-side comparison table.

Columns:

```text
Split | R² | MAE | RMSE | MAE/mean | Baseline improvement
```

Rows:

```text
Validation
Test
```

The test row should be visually emphasized with a slightly darker background or stronger text weight because it is the most important trust signal.

### 6. Expandable secondary metrics

Move secondary metrics into a per-output expandable area using native `<details>` / `<summary>` or a simple React state toggle.

Hidden by default:

- nRMSE
- RMSE/range
- baseline MAE
- baseline RMSE, if present
- RMSE percent of train std, if present
- acceptance status, if present
- R² note, if present
- scientist summary, if still useful as raw backend copy

The main card should remain readable when details are closed.

### 7. Objective-weight warning hook

The Model Quality page currently does not appear to receive active objective weights. Do not add backend calls for this task.

Design the helper/component API so weights can be passed later:

```ts
const objectiveWeights: Record<string, number> | undefined = undefined
// TODO: Pass active BO/recommendation objective weights when Model Quality has access to them.
```

If weights are later available, show a warning when:

- output trust is `weak` or `needs_review`, and
- absolute objective weight is above a configurable threshold, for example `>= 0.25`.

Example warning:

```text
Warning: BoL ECSA has weak test performance but currently receives a high objective weight. The optimizer may over-rank candidates based on unreliable predictions.
```

For this implementation, include the TODO/hook but do not fetch new data.

## Formatting rules

Add focused formatting helpers rather than relying on generic `formatNumber` everywhere.

Recommended helpers:

```ts
formatR2(value)          // 0.860, -0.120, or '-'
formatMetric(value, unit) // 3 significant digits plus unit
formatPercent1(value)    // 29.1%
```

Rules:

- R²: 3 decimals
- MAE/RMSE: 3 significant digits or a sensible fixed fallback
- Percentages: 1 decimal place
- Units: display once next to metric value, not repeatedly in every sentence
- Missing/undefined metrics: show `-`, not `NaN`

## Visual direction

Use the existing premium visual language:

- outer rounded white/cream panel
- top summary card with clear hierarchy
- responsive card grid: `md:grid-cols-2`, maybe `xl:grid-cols-4` if cards remain readable
- trust badges with distinct but tasteful colors:
  - Strong: green
  - Usable: amber/olive
  - Weak: red/rose
  - Needs review: slate/amber
- muted secondary text
- generous spacing between title, primary metrics, comparison table, and details

Avoid dense paragraphs and avoid showing all numbers with the same visual weight.

## Steps

- [ ] Add trust-level and formatting helpers in `ModelQualityPage.tsx` or a small frontend utility module.
- [ ] Build derived per-output trust data from `bestSplits.validation`, `bestSplits.test`, and `schema.outputs`.
- [ ] Add the top-level surrogate trust summary card.
- [ ] Replace the current split-first validation/test cards with output-first KPI cards.
- [ ] Add primary test metrics and deterministic interpretation copy per output.
- [ ] Add compact validation-vs-test comparison table inside each card.
- [ ] Move secondary metrics into collapsed details per output.
- [ ] Add the objective-weight TODO/hook without changing backend contracts.
- [ ] Check responsive spacing on desktop and narrower widths.
- [ ] Run frontend build and relevant backend/frontend tests.

## Verification

Run:

```bash
cd frontend && npm run build
```

If backend is available, also run:

```bash
cd backend && uv run pytest tests/test_api.py tests/test_real_fuel_cell_data_pipeline.py
```

Manual checks:

- The section is understandable within 5 seconds.
- The top summary gives a clear model-trust verdict.
- Each predicted output has a visible trust badge.
- Test metrics are visually prioritized over validation metrics.
- Validation/test comparison remains available in each output card.
- Secondary metrics are still present but hidden by default.
- Weak or near-zero/negative R² outputs are clearly flagged.
- No training, backend metric calculation, recommendation scoring, BO/LHS, heatmap, or parallel-coordinates behavior changes.

## Acceptance criteria

- Page reads like a decision-support product screen, not a metric dump.
- No existing metric is removed from the data model.
- No backend API contract changes are introduced.
- UI remains consistent with the rest of the app.
- Existing build/tests pass.
