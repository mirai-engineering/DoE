# Prediction Diagnostics Plot Label Polish Plan

## Context

The new Model Quality → Prediction diagnostics plots are useful and visually strong, but they need more explicit scientist/engineer-facing labels so each plot is self-explanatory during a demo or technical review.

## Approach

Polish the existing plots without changing the data/model pipeline. Add clearer axis labels, units, subtitles, annotations, and lightweight visual aids that make the plots more publication/professional-review ready.

## Files to modify

```text
frontend/src/components/ModelQualityPage.tsx
```

Optional docs update:

```text
backend/training/README.md
```

## Reuse

Reuse existing schema output metadata:

```text
schema.outputs[].label
schema.outputs[].unit
```

Reuse existing prediction columns:

```text
operating_voltage
bol_current_density_true
bol_current_density_pred
eol_current_density_true
eol_current_density_pred
{output}_true
{output}_pred
{output}_residual
split
cell_id
operating_rh
```

## Steps

- [ ] Add richer axis titles to the polarization plot:
  - x-axis: `Current density / A cm⁻²`
  - y-axis: `Cell voltage / V`
  - plot subtitle/context: `Cell {cell_id}, RH {operating_rh}% — {split selection}`

- [ ] Add hover labels for polarization curves:
  - cell ID
  - split
  - RH
  - voltage
  - measured/predicted current density
  - BoL/EoL label

- [ ] Add an optional annotation/caption under the polarization plot:
  - `Dashed lines are model predictions; solid lines are measured data.`
  - `BoL = beginning of life; EoL = end of life.`

- [ ] Improve parity plot axis labels:
  - x-axis: `Measured {output label} ({unit})`
  - y-axis: `Predicted {output label} ({unit})`
  - title/caption: `Points close to the diagonal indicate better predictions.`

- [ ] Improve residual plot axis labels:
  - x-axis: `Operating voltage / V`
  - y-axis: `Residual: measured − predicted ({unit})`
  - add caption explaining sign:
    - positive residual = model underpredicted
    - negative residual = model overpredicted

- [ ] Add visual reference aids:
  - parity plot: keep y=x reference line and label it `Ideal prediction`
  - residual plot: keep zero-residual line and label it `No error`
  - optionally add subtle shaded bands around zero residual if useful later

- [ ] Add split/source labeling near controls:
  - `Training-run predictions`
  - selected model
  - selected splits
  - `BO holdout is diagnostic-only and not merged into test metrics.`

- [ ] Consider a small “How to read this” expandable note:
  - polarization curve: compares physical curve shape
  - parity plot: compares measured vs predicted values
  - residual plot: reveals systematic bias along operating voltage

## Verification

- [ ] Run frontend build:

```bash
cd frontend
npm run build
```

- [ ] Manually inspect Model Quality → Prediction diagnostics:
  - axis labels include units
  - hover labels are meaningful
  - captions explain dashed/solid lines and residual sign
  - plots still resize correctly
  - no changes to backend/training behavior
