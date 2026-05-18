# Design Studio Flow Layout Redesign Plan

## Context

The previous controls polish made the `Playground controls` card denser, but it did not solve the underlying layout problem:

- `Experiment variables` still feel trapped inside another card.
- The section is visually too form-like for a premium pitch.
- Inputs and outputs are not conceptually separated enough.
- Scientists need to understand the workflow quickly:

```text
Choose objective → tweak test inputs → model predicts outputs → inspect response curve → compare/export
```

The Design Studio should feel like a scientific design console, not a long form.

## Product goal

Make the Design Studio workspace look and behave like a premium ML-guided experiment design flow:

```text
Goal / objective
      ↓
Experiment inputs
      ↓
Served surrogate model
      ↓
Predicted outputs + dynamic response curve
```

The scientist should still be able to:

- select objective presets
- select multiple objectives/weights
- tweak input variables with sliders and number boxes
- see live predicted outputs
- compare measured real-cell curves
- save/export candidate packages
- find best starting design
- find tradeoff candidates

## Main design change

Break the first workspace into independent sections:

1. `Design objective` — compact top card with goal/preset/actions.
2. `Experiment inputs` — full-width dedicated container for sliders.
3. `Model flow` — visual flow diagram showing inputs → model → outputs.
4. `Predicted outputs` — separate output cards.
5. `Dynamic response curve` — remain the hero plot.

This uses the full page width better and makes inputs/outputs visually distinct.

## Files to modify

```text
frontend/src/components/DesignStudioPage.tsx
```

No backend changes.

## Layout target

### Top of Design Studio after intro

```text
[Design objective card]
  - Objective preset
  - Objective mix / weights
  - Find best starting design
  - Find tradeoff candidates
```

### New full-width experiment input section

```text
[Experiment inputs]
  [input card] [input card] [input card] [input card]
```

Use a responsive grid:

```text
sm: 1 column
lg: 2 columns
2xl: 4 columns if enough width
```

Each input card remains scientific and clear:

- label
- unit
- slider
- numeric value box
- min/max

### Flow diagram card

Add a premium visual diagram between inputs and outputs:

```text
┌──────────────┐      ┌────────────────────┐      ┌────────────────────┐
│ Inputs       │  →   │ Served ML model     │  →   │ Predicted outputs   │
│ 4 variables  │      │ challenger/champion │      │ 4 KPIs + curve      │
└──────────────┘      └────────────────────┘      └────────────────────┘
```

Style:

- dark/charcoal center model node
- ivory input/output nodes
- green/gold accent arrows
- compact enough not to dominate the page

Purpose copy:

```text
Every slider change is sent to the served surrogate model. Outputs and the response curve update as model predictions, not measurements.
```

### Outputs section

Move `Live predictions` out of the side column into its own full-width card after the flow diagram.

Use output cards in a responsive grid:

```text
md:grid-cols-2 xl:grid-cols-4
```

This creates a clean separation:

```text
Inputs are controls.
Outputs are predictions.
Curve is behavior.
```

### Compare/export section

Move real experiment comparison and save/export actions into a compact utility row/card after predicted outputs or near the curve.

Recommended:

```text
[Compare with measured data dropdown] [Save comparison] [Export design package]
```

This avoids hiding export inside input controls.

### Dynamic response curve

Keep the curve as the hero card after predicted outputs/compare row.

Do not move it lower than tradeoff candidates.

### Tradeoff candidates

Keep tradeoff candidates as optional secondary section below the curve.

## Implementation steps

### Step 1 — Replace current two-column workspace

In `DesignStudioPage.tsx`, replace the current `design-workspace` grid:

```tsx
<section id="design-workspace" className="... xl:grid-cols-[0.9fr_1.1fr]">
```

with a vertical flow:

```tsx
<section id="design-workspace" className="space-y-6 scroll-mt-8">
```

### Step 2 — Create objective card

Render a full-width/compact objective card containing:

- `PanelHeader` for `Design objective`
- action buttons
- objective preset selector
- objective mix checkboxes/weights
- caution copy

Use a grid inside it:

```text
left: explanation + preset
right: objective mix
```

### Step 3 — Create ExperimentInputs section

Create dedicated section:

```tsx
<section className="rounded-[2rem] ...">
  <PanelHeader eyebrow="Experiment inputs" title="Tune test conditions" ... />
  <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-4">
    {schema.inputs.map(...)}
  </div>
</section>
```

Keep slider functionality identical.

### Step 4 — Create flow diagram

Add section:

```tsx
<section className="rounded-[2rem] ...">
  flow nodes
</section>
```

Use simple JSX/CSS, no new dependencies.

Suggested nodes:

- `Experiment inputs`
- `Served surrogate model`
- `Predicted outputs`

Include current values:

- input count
- model version/challenger/champion
- output count
- prediction status

### Step 5 — Create predicted outputs section

Move the existing `Live predictions` card to its own full-width section after flow diagram.

Output cards grid:

```text
md:grid-cols-2 xl:grid-cols-4
```

Keep emphasized output highlighting.

### Step 6 — Create compare/export utility section

Move real-cell selector and save/export buttons into a section/card:

```text
Compare and package this candidate
```

Include:

- measured real-cell overlay dropdown
- save current as comparison
- export design package

This maps directly to the curve and lab handoff.

### Step 7 — Update `On this page` anchors

Keep existing anchor labels, but ensure they map to the new sections:

- `Workspace` → design objective / inputs
- `Response curve` → curve
- `Tradeoff candidates` → tradeoff section
- `Compare/export` → compare/export card

### Step 8 — Build and verify

Run:

```bash
cd frontend
npm run build
```

Manual checks:

- Experiment inputs are in their own container.
- Inputs spread horizontally across page width on desktop.
- Inputs/outputs are visually distinct.
- Flow diagram clearly explains input → model → output.
- Sliders and numeric input still update predictions.
- Objective selection still works.
- Find best starting design still loads values.
- Find tradeoff candidates still works.
- Compare real measured data still affects curve overlay.
- Save/export still work.
- Dynamic response curve remains the hero.

## Acceptance criteria

- The Design Studio looks like a premium scientific workflow, not a long control form.
- Inputs are full-width and easy to scan.
- Outputs are clearly separated from inputs.
- The model flow diagram communicates the ML-guided workflow during a pitch.
- UX functionality remains unchanged.
