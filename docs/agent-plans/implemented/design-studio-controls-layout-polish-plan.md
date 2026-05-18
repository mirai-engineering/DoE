# Design Studio Controls Layout Polish Plan

## Context

The Design Studio UX is working well, but the `Playground controls — Explore design variables` card is visually too long. The experiment variables appear as a single vertical list, which creates unused space beside them and makes the workspace feel less premium.

The goal is to keep the current UX and scientific clarity, but improve information density and visual balance.

## Approach

Restructure the first Design Studio workspace into a more balanced, professional control surface:

1. Split the controls card into two internal columns on wide screens:
   - left: objective/search controls
   - right: experiment variables + actions
2. Render experiment variables in a compact two-column grid on wide screens instead of a long single list.
3. Add a small “Current design summary” card to use empty space and reinforce the active design context.
4. Keep Dynamic Response Curve as the hero section below the workspace.
5. Avoid backend changes.

## Files to modify

```text
frontend/src/components/DesignStudioPage.tsx
```

## Reuse

Reuse existing Design Studio state and helpers:

```text
schema.inputs
inputs
setInputs
prediction
objectiveMode
objectiveWeights
seedFromBatch
findParetoTradeoffs
savedComparison
exportZip
formatNumber
```

## Steps

### 1. Change the controls card internal layout

Inside the existing left workspace card, replace the current vertical flow:

```text
Header/actions
Objective goal
Experiment variable list
Save/export buttons
```

with a more balanced layout:

```text
Header/actions
Two-column inner grid:
  Left column:
    Optimization goal
    Search explanation
  Right column:
    Experiment variables
    Current design summary
    Save/export buttons
```

On mobile, it should stack as before.

### 2. Make experiment variables compact

Change the variable list from:

```tsx
<div className="mt-5 space-y-4">
```

to a grid such as:

```tsx
<div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
```

Because the controls card itself sits in a page grid, use responsive classes that avoid squeezing labels too much.

Each variable card should be slightly more compact:

- reduce padding from `p-4` to `p-3`
- keep range + numeric input
- keep units visible
- use warm ivory background

### 3. Add Current design summary

Add a compact card next to/under the variables:

```text
Current design
- number of variables
- active objective label
- selected model version
- predicted outputs available / updating
```

This fills otherwise empty space and makes the page feel intentional.

Example copy:

```text
Current design
4 variables controlled from schema
Goal: maximize BoL current density
Predictions update from the active served model
```

### 4. Improve actions placement

Move actions into a dedicated action strip near the variable summary:

```text
Save current as comparison | Export design package
```

The primary action `Find best starting design` stays in the header. The tradeoff action remains secondary.

### 5. Keep output cards on the right

Do not overhaul the right-side `Live predictions` and `Compare with measured data` cards in this pass.

### 6. Verify

Run:

```bash
cd frontend
npm run build
```

Manual checks:

- Design Studio workspace no longer has a long awkward variable list.
- Experiment variables are easier to scan.
- No controls are hidden or too narrow on laptop width.
- Mobile layout still stacks cleanly.
- Sliders and numeric inputs still update predictions.
- Save/export actions still work.
- Find best starting design and tradeoff candidates still work.

## Acceptance criteria

- The controls section looks intentionally laid out, not like a long form.
- Empty space next to experiment variables is used productively.
- Existing Design Studio UX remains intact.
- The page feels more premium and pitch-ready.
