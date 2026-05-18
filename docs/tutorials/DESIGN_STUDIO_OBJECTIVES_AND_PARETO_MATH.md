# Design Studio Objectives and Pareto Math

## Purpose

This tutorial explains what happens mathematically when a scientist uses the Design Studio controls:

```text
Optimization goal
Objective mix
Find best starting design
Find tradeoff candidates
```

It is coupled to the current implementation in:

```text
frontend/src/components/DesignStudioPage.tsx
backend/app/services/design_studio.py
backend/app/services/recommendation.py
```

The short version:

- **Generate result** evaluates the current slider/input values directly with the served model.
- **Find best starting design** uses a single weighted score to search many virtual candidates.
- **Find tradeoff candidates** uses Pareto non-dominance across multiple selected objectives.
- Sliders define the current design, but the displayed result updates when the user clicks **Generate result** or loads a searched candidate.

---

## 1. Schema-driven inputs and outputs

The Design Studio does not hard-code scientific variables in the UI. It reads the project schema.

For the current fuel-cell project, inputs include test/design variables such as:

```text
Pt/C ratio
I/C ratio
Ionomer EW
Operating RH
Operating voltage
AST RH
AST UPL
```

Outputs include model-predicted KPIs:

```text
BoL current density
EoL current density
BoL ECSA
ECSA loss
```

Conceptually, the served surrogate model is a function:

```text
f(x) = y_hat
```

where:

```text
x     = selected experiment input vector
y_hat = predicted output vector
```

Example:

```text
x = [Pt/C, I/C, ionomer EW, operating RH, operating voltage, AST RH, AST UPL]

y_hat = [BoL current density, EoL current density, BoL ECSA, ECSA loss]
```

Implementation:

```text
DesignStudioPage.tsx
  slider / numeric input changes
    ↓
  Generate result
    ↓
POST /projects/{project_id}/design-studio/predict
    ↓
backend/app/services/design_studio.py::predict_design
    ↓
backend/app/services/prediction.py::predict_rows
```

Mathematically, `Generate result` is the direct prediction path:

```text
y_hat = f(x_current)
```

No objective weights are needed for direct prediction. Objective weights are used only when searching for candidates.

---

## 2. Objective weights: what the checkboxes and numbers mean

The `Objective mix` UI creates a dictionary:

```json
{
  "bol_current_density": 0.4,
  "eol_current_density": 0.4,
  "ecsa_loss": -0.2
}
```

Interpretation:

```text
positive weight  -> reward larger predicted values
negative weight  -> reward smaller predicted values
zero/unchecked   -> ignore that output
```

So:

```text
bol_current_density: +0.4
```

means high BoL current density is good.

```text
ecsa_loss: -0.2
```

means high ECSA loss is bad, so lower ECSA loss is preferred.

The frontend stores these weights in `selectedObjectiveWeights` / `objectiveWeights` and sends them to the backend as `objective_weights`.

Implementation:

```text
frontend/src/components/DesignStudioPage.tsx
  objective checkbox/weight inputs
    ↓
findDesignStudioSeed(... objective_weights ...)
findDesignStudioPareto(... objective_weights ...)
```

---

## 3. Find best starting design: single weighted score

When the user clicks:

```text
Find best starting design
```

the backend does a virtual batch search.

Implementation path:

```text
POST /projects/{project_id}/design-studio/seed/batch
  ↓
backend/app/services/design_studio.py::seed_batch_candidate
  ↓
backend/app/services/recommendation.py::_generate_candidates
  ↓
backend/app/services/prediction.py::predict_rows
  ↓
backend/app/services/recommendation.py::_score_predictions
```

### Step 1 — Generate virtual candidates

The app samples many candidate input vectors inside the schema bounds.

Current implementation uses Latin-hypercube-like stratified sampling:

```text
backend/app/services/recommendation.py::_lhs_values
backend/app/services/recommendation.py::_generate_candidates
```

For each input variable, the allowed range is divided into strata and sampled across the range.

Conceptually:

```text
X = {x_1, x_2, ..., x_N}
```

where `N` is usually 2000 for `Find best starting design`.

### Step 2 — Predict every candidate

For each candidate:

```text
y_hat_i = f(x_i)
```

This produces one predicted output vector per candidate.

### Step 3 — Normalize each output across the sampled candidate set

For each output `j`, the backend computes candidate-set min and max:

```text
min_j = min(y_hat_1j, ..., y_hat_Nj)
max_j = max(y_hat_1j, ..., y_hat_Nj)
```

Then it rescales candidate predictions to `[0, 1]`:

```text
normalized_ij = (y_hat_ij - min_j) / (max_j - min_j)
```

Implementation:

```text
backend/app/services/recommendation.py::_score_predictions
```

Important implication:

> The score is relative to the candidates sampled in this search, not an absolute physical score.

### Step 4 — Compute weighted score

The backend computes:

```text
score_i = Σ_j weight_j × normalized_ij
```

For example:

```text
score_i = 0.4 × norm(BoL current density)
        + 0.4 × norm(EoL current density)
        - 0.2 × norm(ECSA loss)
```

Because `ECSA loss` has a negative weight, larger ECSA loss lowers the score.

### Step 5 — Load the best-scoring candidate

The backend selects:

```text
x_best = argmax_i(score_i)
```

Then the Design Studio loads `x_best` into the sliders and recomputes:

- predicted outputs at the selected point
- dynamic fuel-cell response curve
- optional measured-cell overlay

Implementation:

```text
backend/app/services/design_studio.py::seed_batch_candidate
```

---

## 4. Why normalization matters

Outputs have different units and scales:

```text
current density: A cm⁻²
ECSA: m² gPt⁻¹ or equivalent scale
ECSA loss: fraction or percentage-like quantity
```

Without normalization, the output with the largest numerical scale would dominate the score.

Normalization makes weights easier to interpret:

```text
0.4 on BoL current density
0.4 on EoL current density
-0.2 on ECSA loss
```

means roughly:

```text
40% emphasis on BoL ranking within this candidate set
40% emphasis on EoL ranking within this candidate set
20% penalty on high ECSA loss within this candidate set
```

Caveat:

> These are ranking weights, not physical unit conversion factors.

---

## 5. Find tradeoff candidates: Pareto frontier

When the user clicks:

```text
Find tradeoff candidates
```

the backend does not return only the highest weighted-score candidate.

Instead, it finds candidates that are **not dominated** across the selected objectives.

Implementation path:

```text
POST /projects/{project_id}/design-studio/pareto
  ↓
backend/app/services/design_studio.py::pareto_tradeoff_candidates
  ↓
_selected_objectives
_objective_matrix
_non_dominated_mask
_select_representative_indices
```

### Step 1 — Select active objectives

Only non-zero weights are used.

Implementation:

```text
backend/app/services/design_studio.py::_selected_objectives
```

The sign of each weight determines optimization direction:

```text
weight > 0 -> maximize this output
weight < 0 -> minimize this output
```

Example:

```text
BoL current density: +0.4 -> maximize
EoL current density: +0.4 -> maximize
ECSA loss:           -0.2 -> minimize
```

### Step 2 — Convert minimization into maximization

For Pareto comparison, the backend transforms minimized objectives by multiplying by `-1`.

Implementation:

```text
backend/app/services/design_studio.py::_objective_matrix
```

Mathematically:

```text
z_ij = y_hat_ij                 if objective j is maximize
z_ij = -1 × y_hat_ij            if objective j is minimize
```

After this transformation, “larger is better” for every selected objective.

### Step 3 — Pareto dominance

Candidate `a` dominates candidate `b` if:

```text
a is at least as good as b on every selected objective
and
a is strictly better than b on at least one selected objective
```

Using the transformed matrix `z` where larger is better:

```text
z_a_j >= z_b_j for all j
and
z_a_j > z_b_j for at least one j
```

If another candidate dominates candidate `b`, then `b` is not on the Pareto frontier.

Implementation:

```text
backend/app/services/design_studio.py::_non_dominated_mask
```

Plain-language meaning:

> A Pareto candidate is interesting because you cannot improve one selected objective without giving up performance on at least one other selected objective, among the sampled candidates.

---

## 6. Why Pareto is different from weighted scoring

Weighted scoring asks:

```text
Which candidate has the highest single combined score?
```

Pareto search asks:

```text
Which candidates represent different scientifically meaningful tradeoffs?
```

Weighted scoring is good when you want:

```text
one recommended starting point
```

Pareto is good when you want:

```text
a short menu of alternatives for scientific discussion
```

Example:

Candidate A:

```text
very high BoL current density
moderate EoL current density
higher ECSA loss
```

Candidate B:

```text
slightly lower BoL current density
higher EoL current density
lower ECSA loss
```

A weighted score may choose only one. Pareto search can return both if neither is clearly better across all selected objectives.

---

## 7. Representative Pareto candidates

The Pareto frontier can contain many candidates. The UI should not show hundreds of cards.

The backend therefore selects representative points from the frontier.

Implementation:

```text
backend/app/services/design_studio.py::_select_representative_indices
```

Current strategy:

1. Include candidates that are best on individual selected objectives.
2. Include a candidate with high average normalized objective value.
3. Add diverse candidates that are far away from already selected representatives.

This creates a compact set of tradeoff candidates for the UI.

The returned cards are labels such as:

```text
High BoL current density
Low ECSA loss
Balanced tradeoff
```

Implementation:

```text
backend/app/services/design_studio.py::_pareto_label
```

---

## 8. How this connects to the dynamic response curve

The Pareto and weighted-score searches choose an input vector:

```text
x_candidate
```

When the user loads a candidate, the Design Studio uses that candidate as the current slider state.

Then the fuel-cell response curve is recomputed by sweeping operating voltage across the observed voltage grid:

```text
x_candidate with operating_voltage = v_1
x_candidate with operating_voltage = v_2
...
x_candidate with operating_voltage = v_K
```

For each voltage point:

```text
y_hat_k = f(x_candidate, operating_voltage = v_k)
```

The page plots:

```text
x-axis: predicted current density
 y-axis: operating voltage
```

Implementation:

```text
backend/app/services/design_studio.py::_observed_voltage_grid
backend/app/services/design_studio.py::_curve_rows
```

Important:

> The search score chooses a candidate. The dynamic response curve helps the scientist judge whether that candidate behaves plausibly across operating conditions.

---

## 9. Practical guidance for scientists

Use **Find best starting design** when:

- you want one strong model-ranked candidate
- you have a clear primary objective
- you are preparing a first lab-review candidate

Use **Find tradeoff candidates** when:

- at least two outputs matter
- improving one KPI may degrade another
- you want alternatives for a technical discussion
- you want to compare candidates in the dynamic response curve

Suggested fuel-cell examples:

### High beginning-of-life performance

```text
BoL current density: +1.0
all others:          0.0
```

### Durability-aware performance

```text
BoL current density: +0.4
EoL current density: +0.4
ECSA loss:           -0.2
```

### Minimize degradation signal

```text
ECSA loss: -1.0
all others: 0.0
```

### Compare multiple scientific priorities

```text
BoL current density: +0.35
EoL current density: +0.35
BoL ECSA:            +0.10
ECSA loss:           -0.20
```

Then run:

```text
Find tradeoff candidates
```

Load candidates one at a time and inspect the dynamic response curve.

---

## 10. Current limitations

The current MVP intentionally keeps the math simple and auditable.

Limitations:

- Candidate search is sampled, not guaranteed global optimization.
- Weighted score normalization is relative to the sampled candidate set.
- Pareto frontier is computed over sampled virtual candidates, not the continuous design space.
- The Design Studio currently uses point predictions; uncertainty is not yet shown in the objective score.
- Model quality still needs scientist review before lab decisions.

These limitations are acceptable for the MVP because the page is intended as decision support, not autonomous experiment execution.

---

## 11. Code reference map

| Concept | Implementation |
|---|---|
| Slider/manual prediction | `DesignStudioPage.tsx`, `predict_design` |
| Dynamic response curve | `_curve_rows` |
| Default objective | `_default_objective_weights` |
| Candidate generation | `_generate_candidates` |
| Weighted objective score | `_score_predictions` |
| Best starting design | `seed_batch_candidate` |
| Active Pareto objectives | `_selected_objectives` |
| Max/min transformation | `_objective_matrix` |
| Pareto frontier | `_non_dominated_mask` |
| Representative tradeoffs | `_select_representative_indices` |
| Tradeoff labels | `_pareto_label` |
| Design package export | `export_design_zip` |

---

## 12. Pitch explanation

A concise explanation for demos:

> The scientist defines what “best” means using objective weights. For a single recommended design, Mirai samples thousands of feasible virtual experiments, predicts each one with the active surrogate model, normalizes the outputs, and ranks candidates by a weighted score. For multi-objective decisions, Mirai computes a Pareto frontier so scientists can inspect alternatives where improving one KPI may compromise another. Any selected candidate is then loaded into the Design Studio, where the response curve updates immediately for scientific review.
