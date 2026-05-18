# UI Workflow Simplification Plan

## Context

The app now has powerful features, but the navigation and Design Studio page are becoming visually overloaded.

Current issues:

1. Batch workflow is split across three top-level tabs:
   - `Batch Explorer`
   - `Batch Results`
   - `Batch Visuals`

   These should feel like one workflow with internal sub-tabs.

2. Design Studio has too much visible at once. The strongest feature is the `Dynamic response curve`, but the Pareto section currently appears as a large separate panel and competes with the curve.

3. Pareto tradeoffs are useful, but their purpose should be reframed:
   - not a second main visualization
   - rather a candidate picker that helps users choose a design to load into the dynamic response curve

## Approach

Make two UI organization changes:

1. Collapse Batch Explorer / Batch Results / Batch Visuals into a single top-level tab:

```text
Batch Search
```

Inside that tab, add internal sub-tabs:

```text
Configure
Results
Visuals
```

2. Simplify Design Studio layout so the dynamic response curve is the hero. Pareto becomes a compact “candidate drawer/list” near the controls, not a full competing visualization section.

## Files to modify

Frontend:

```text
frontend/src/types/doe.ts
frontend/src/App.tsx
frontend/src/components/DesignStudioPage.tsx
```

Optional new component:

```text
frontend/src/components/BatchSearchPage.tsx
```

Docs:

```text
docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md
```

## Reuse

Reuse existing batch components:

```text
PredictPanel
RecommendPanel
RecommendationsPage
VisualizationsPage
```

Reuse existing Design Studio state/functions:

```text
paretoResults
findParetoTradeoffs
loadParetoCandidate
curveRows
prediction
savedComparison
selectedRealCell
```

## Part A — Batch workflow consolidation

### Step 1 — Update top-level tabs

Change top-level tabs from:

```text
Batch Explorer
Design Studio
Batch Results
Batch Visuals
Optimization Loop
Business Impact
Model Quality
```

to:

```text
Batch Search
Design Studio
Optimization Loop
Business Impact
Model Quality
```

This reduces top-level navigation noise.

### Step 2 — Add internal batch sub-tab state

In `App.tsx`, add:

```ts
const [batchView, setBatchView] = useState<'configure' | 'results' | 'visuals'>('configure')
```

When recommendation search succeeds, instead of navigating to top-level `recommendations`, set:

```ts
setActiveTab('batch')
setBatchView('results')
```

### Step 3 — Render batch sub-tabs inside Batch Search

At the top of the Batch Search tab, render internal pills:

```text
Configure
Results
Visuals
```

- `Configure`: current PredictPanel + RecommendPanel
- `Results`: current RecommendationsPage content
- `Visuals`: current VisualizationsPage content

If there is no recommendation run, Results/Visuals should show the existing empty state or prompt the user to run a batch search first.

### Step 4 — Update callbacks

Change callbacks so:

```text
View recommendations → batchView = results
Back to search → batchView = configure
View visuals → batchView = visuals
```

Keep all existing data flow intact.

## Part B — Design Studio simplification

### Step 5 — Make Dynamic response curve the hero

Move `Dynamic response curve` higher in the page, ideally directly after the top banner or in the right column of the first viewport.

Recommended layout:

```text
Design Studio
├── top banner / model context
├── main workspace grid
│   ├── left: compact controls
│   │   ├── optimization goal
│   │   ├── design variables
│   │   └── actions
│   └── right: dynamic response curve hero
├── prediction cards / measured comparison controls
└── advanced candidate exploration
    └── Pareto tradeoffs collapsed/compact
```

### Step 6 — Reframe Pareto as a candidate picker

Rename the section from:

```text
Pareto tradeoffs — Candidate designs with different strengths
```

to something more action-oriented:

```text
Tradeoff candidates
```

Description:

```text
Use these candidates as starting points. Loading one updates the sliders and the response curve above.
```

### Step 7 — Remove or collapse the Pareto scatter plot for now

The Pareto scatter plot is not as meaningful as the dynamic response curve yet and adds clutter.

For this iteration:

- hide it behind `<details>` with label:

```text
Show Pareto scatter plot
```

or remove it entirely.

Recommendation: collapse behind details to preserve functionality without visual overload.

### Step 8 — Compact Pareto candidate cards

Change Pareto cards from large cards to a compact horizontal/vertical list:

```text
[Load] High BoL current density | BoL 1.23 | EoL 0.91 | ECSA loss 0.18
[Load] Low ECSA loss            | BoL 1.05 | EoL 0.88 | ECSA loss 0.08
```

Keep the emphasis on the `Load` action.

### Step 9 — Add “advanced” affordance

Put Pareto under an advanced/secondary area:

```text
Advanced: tradeoff candidates
```

or:

```text
Find alternatives
```

The main action remains:

```text
Find best starting design
```

The secondary action is:

```text
Find tradeoff candidates
```

Consider renaming button from:

```text
Find Pareto tradeoffs
```

to:

```text
Find tradeoff candidates
```

with tooltip/help text explaining Pareto.

## Step 10 — Update tutorial

Update `docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md` to explain:

- Batch Search now contains Configure / Results / Visuals
- Tradeoff candidates are optional starting points
- The dynamic response curve is the main place to evaluate any loaded candidate

## Verification

Frontend:

```bash
cd frontend
npm run build
```

Backend should not need changes for this plan, but if touched:

```bash
cd backend
uv run pytest tests/test_real_fuel_cell_data_pipeline.py tests/test_api.py
```

Manual checks:

- Top nav has fewer tabs.
- Batch Search internal sub-tabs work.
- Running batch search lands on Results inside Batch Search.
- Batch Visuals are reachable inside Batch Search.
- Design Studio shows dynamic response curve prominently.
- Pareto/tradeoff candidates no longer dominate the page.
- Loading a tradeoff candidate updates sliders and the dynamic response curve.
- Existing export and real-cell comparison still work.

## Acceptance criteria

- The app feels less cluttered at top navigation level.
- Batch workflow is grouped as one coherent workflow.
- Design Studio’s primary visual is the dynamic response curve.
- Pareto results support the curve workflow instead of competing with it.
- No backend/model behavior changes required.
