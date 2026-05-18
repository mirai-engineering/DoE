# Design Studio Playground Tutorial

## Purpose

The **Design Studio** is the interactive playground for applying the active surrogate model to engineering design.

Use it to answer:

```text
If I change these design variables, what does the model predict?
What would the proposed fuel-cell polarization curve look like?
How does this candidate compare with another design or a measured real cell?
Can I export this candidate for lab review?
```

For the PEM fuel-cell project, the Design Studio shows a dynamic predicted polarization curve:

```text
x-axis: current density / A cm⁻²
y-axis: cell voltage / V
```

The page is intentionally schema-driven. Input controls and output cards are generated from the project schema, so future projects can reuse the same playground with different variables, outputs, and visualization presets.

---

## Where to find it

Start the app and open:

```text
Design Studio
```

Pitch-facing top-level areas:

```text
Tailored ML Model → ML-Guided Design → Business Impact
```

The `ML-Guided Design` area contains:

```text
Design Studio → Batch Search → Explore & Exploit Tests
```

Inside `Batch Search`, use the internal workflow tabs:

```text
Configure → Results → Visuals
```

---

## Recommended workflow

### 1. Check the active model banner

At the top, the page shows the model context:

```text
Served-model predictions
Champion: <version or not set>
Challenger: <version or not set>
Default objective: BoL current density
```

For the fuel-cell demo, the default objective is:

```text
maximize BoL current density
```

If no `champion` alias is set, the backend may still use the packaged or challenger model depending on local runtime configuration. Treat the banner as a reminder to review model lifecycle state before making lab decisions.

---

### 2. Choose what “best” means

Before asking the app to find a candidate, use the **Optimization goal** panel.

For the current fuel-cell project, examples include:

```text
Maximize BoL current density
Maximize EoL current density
Maximize BoL ECSA
Minimize ECSA loss
Balanced fuel-cell performance
Custom weights
```

In plain language, this tells the app what kind of candidate you want to find.

For example:

```text
Maximize BoL current density
```

means:

> Search for a design that the model predicts will have high beginning-of-life current density.

```text
Minimize ECSA loss
```

means:

> Search for a design that the model predicts will lose less electrochemical surface area after degradation.

Custom weights let you define tradeoffs:

```text
positive weight  = reward larger predicted values
negative weight  = reward smaller predicted values
zero weight      = ignore this output in the search score
```

For the detailed math and implementation mapping, see:

```text
docs/tutorials/DESIGN_STUDIO_OBJECTIVES_AND_PARETO_MATH.md
```

Example:

```text
BoL current density:  +0.4
EoL current density:  +0.4
ECSA loss:            -0.2
```

This means:

> Prefer candidates with high BoL and EoL current density, but penalize candidates with high ECSA loss.

---

### 3. Seed a candidate from batch search

Click:

```text
Find best starting design
```

This asks the backend Design Studio endpoint to run a dedicated candidate search using your selected optimization goal.

What happens internally:

1. The app creates many virtual candidate configurations inside the allowed input ranges.
2. The active served model predicts outputs for every candidate.
3. The app converts the selected objective weights into a score.
4. The candidate with the highest score is loaded into the sliders.
5. The predicted output cards and BoL/EoL polarization curve update.

Think of this as a strong model-guided starting point, not an automatic final answer or guaranteed global optimum.

---

### 4. Explore variables manually and generate one result

Move the input sliders or edit numeric values, then click:

```text
Generate result
```

This evaluates the currently selected composition/test condition and updates the predicted output cards plus the dynamic polarization curve.

Objective settings affect search actions only. Manual evaluation uses the current input values shown in the sliders.

For the PEM fuel-cell project, controls are generated from these schema inputs:

```text
Pt/C ratio
I/C ratio
Ionomer EW
Operating RH
Operating voltage
AST RH
AST UPL
```

After you click `Generate result`, the page updates predictions from the active served model.

The same mechanism is generic: for a future battery/materials project, the controls will be generated from that project’s own schema inputs.

---

### 5. Read the live prediction cards

The output cards are generated from schema outputs.

For the real fuel-cell project:

```text
BoL current density
EoL current density
BoL ECSA
ECSA loss
```

Each card shows:

```text
predicted value
unit
direction: maximize or minimize
change vs saved comparison, if available
```

Cards involved in the currently selected objective are visually emphasized. If you choose a multi-output or balanced objective, more than one card may be highlighted.

---

### 6. Find tradeoff candidates

Use:

```text
Find tradeoff candidates
```

when you care about multiple outputs at the same time.

Example:

```text
BoL current density:  +0.4
EoL current density:  +0.4
ECSA loss:            -0.2
```

A single weighted score can hide tradeoffs. Pareto search instead returns several candidate designs where no candidate is obviously better than another across all selected objectives.

Plain-language definition:

> A Pareto candidate is useful when improving one selected objective would likely make at least one other selected objective worse.

The app shows:

```text
Pareto tradeoff candidate cards
predicted objective values
candidate labels like High BoL current density or Low ECSA loss
a simple tradeoff scatter plot
```

Click:

```text
Load
```

on any Pareto candidate to move it into the playground sliders and update the predicted behavior curve.

Use `Find best starting design` when you want one simple winner. Use `Find tradeoff candidates` when you want optional Pareto-style starting points for a scientific discussion. Any loaded tradeoff candidate should be judged in the dynamic response curve.

---

### 7. Inspect the predicted polarization curve

The curve panel shows the predicted response of the current candidate.

For fuel cells:

```text
Current design BoL: dashed blue
Current design EoL: dashed red
```

The backend creates this curve by sweeping:

```text
operating_voltage
```

over the **observed in-domain voltage grid** from training artifacts, not over an arbitrary synthetic grid.

That means the predicted curve stays close to voltages actually represented in the real dataset.

---

### 8. Save a comparison candidate

Once you find an interesting design, click:

```text
Save current as comparison
```

Then move the sliders again.

The plot can overlay:

```text
Current design BoL/EoL
Saved comparison BoL/EoL
```

This is useful for asking:

```text
Did this variable change improve the curve?
Where did it improve — high voltage, low voltage, BoL, EoL?
What tradeoff did I introduce?
```

---

### 9. Compare with a measured real cell

Use:

```text
Compare with measured data
```

Select a real experiment option such as:

```text
Cell_17 · RH 100% · test · 114 rows
```

The plot overlays measured real-cell curves:

```text
Measured real BoL
Measured real EoL
```

These are not model predictions. They are measured data from training artifacts.

This comparison helps scientists decide whether the proposed design is plausible relative to real experiments.

---

### 10. Export a design package

Click:

```text
Export design package
```

The backend returns a ZIP file containing:

```text
candidate_inputs.csv
predicted_outputs_at_selected_point.csv
predicted_polarization_curve.csv
comparison_candidate.csv
selected_real_cell_curve.csv
nearest_real_cells.csv
README.txt
```

Use this export for:

```text
lab handoff
scientist review
external plotting
record keeping
candidate discussion
```

Important: predictions are model estimates, not experimental results.

---

## Backend endpoints

The Design Studio uses dedicated endpoints:

```text
GET  /projects/{project_id}/design-studio/state
POST /projects/{project_id}/design-studio/predict
POST /projects/{project_id}/design-studio/seed/batch
POST /projects/{project_id}/design-studio/export.zip
```

### State endpoint

Returns schema-driven setup information:

```text
inputs
outputs
default inputs
default objective weights
fuel-cell visualization preset
observed voltage grid
real-cell comparison options
active model metadata
```

### Predict endpoint

Given candidate inputs, returns:

```text
served-model predictions at the selected point
fuel-cell voltage-sweep curve rows, when the preset is available
selected measured real-cell comparison, when requested
warnings
model version
```

### Starting-design search endpoint

Runs a dedicated Design Studio candidate search and returns the best candidate plus its prediction curve.

### Export endpoint

Creates the lab/review ZIP package.

---

## Fuel-cell-specific behavior

The current project has a special preset:

```text
fuel_cell_polarization
```

It maps:

```text
x-axis BoL output: bol_current_density
x-axis EoL output: eol_current_density
y-axis input: operating_voltage
```

The curve is plotted as:

```text
x = predicted current density
y = operating voltage
```

This matches the conventional engineering reading of PEM fuel-cell polarization behavior.

---

## Generalization principle

The Design Studio should remain generic.

Do not hardcode future UI controls around fuel-cell variable names. Instead:

```text
inputs come from schema.inputs
outputs come from schema.outputs
button labels stay generic
project-specific curves are optional presets
```

Examples of future presets:

```text
Battery: capacity retention vs cycle number
Materials: composition vs strength
Catalyst: temperature vs yield
Membrane: humidity vs conductivity
```

Generic button language should remain broad:

```text
Find best starting design
Explore design variables
Save current as comparison
Compare with measured data
Export design package
```

Avoid narrow labels like:

```text
Optimize fuel cell
Export MEA recipe
```

unless they are part of an optional project-specific preset.

---

## Trust notes

The Design Studio is for exploration and decision support. Before using a candidate for physical testing, review:

```text
Model Quality → trust metrics
Prediction diagnostics → parity/residual/polarization plots
Design Studio → comparison with saved candidate and measured real cell
Business Impact → expected value/cost framing
```

Recommended review language:

```text
This candidate is model-proposed and should be reviewed by a scientist before lab execution.
```

---

## Troubleshooting

### The Design Studio does not load

Check backend health:

```bash
curl http://localhost:3000/api/health
```

or direct backend:

```bash
curl http://localhost:8000/health
```

### No real-cell comparisons appear

Regenerate training artifacts so `predictions.csv` exists:

```bash
cd backend
uv run python training/real_training_pipeline/train_real_fuel_cell_models.py \
  --project-id pem_fuel_cell_real_cathode_degradation \
  --register-mlflow \
  --set-alias challenger \
  --epochs 1000 \
  --learning-rate 0.003 \
  --seed 7
```

Expected artifact:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/training_artifacts/latest/predictions.csv
```

### Predicted curve looks sparse or unexpected

The fuel-cell curve uses observed voltage values from the training artifacts. If the observed grid changes, the curve grid changes too.

### Export ZIP fails

Check the backend logs and confirm that the Design Studio prediction endpoint works first:

```bash
curl http://localhost:8000/projects/pem_fuel_cell_real_cathode_degradation/design-studio/state
```

---

## Validation commands

Backend:

```bash
cd backend
uv run pytest tests/test_real_fuel_cell_data_pipeline.py tests/test_api.py
```

Frontend:

```bash
cd frontend
npm run build
```
