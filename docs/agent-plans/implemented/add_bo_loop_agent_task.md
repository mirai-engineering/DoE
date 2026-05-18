# Agent Task: Add Bayesian Optimization Loop + BO UI Tab to Mirai's DoE Engine

## Context

Mirai's DoE Engine currently has a working MVP based on:

- A trained MLP surrogate model exported to ONNX.
- A FastAPI backend serving predictions.
- A recommendation workflow based on Latin Hypercube Sampling (LHS) + weighted KPI scoring.
- A frontend UI that lets the user explore candidate configurations, choose objective weights, fix inputs, and inspect top-ranked candidates.
- A parallel coordinates visualization for top recommendations.

The current LHS workflow is valuable and should **not** be removed, hidden, or rewritten. It should remain part of the MVP as the **Batch Explorer** / **Design Space Explorer**.

The next step is to add a separate Bayesian Optimization workflow that demonstrates a sequential experimental optimization loop:

```text
observed experiments → BO surrogate / acquisition → next suggested experiment → scientist review → observed result → loop continues
```

Because there is not yet a real lab feedback loop, the first version should support an **offline replay mode** using held-out real experimental data from the paper dataset:

```text
BO suggests X*
↓
nearest hidden real experiment is selected
↓
measured Y* from the historical dataset is revealed
↓
Y* is appended to the observed experiment log
↓
BO updates and proposes the next candidate
```

This is intentionally different from simply doing:

```text
BO suggests X*
MLP predicts Y* = MLP(X*)
BO treats Y* as truth
```

That would only optimize the surrogate. The replay loop must use real held-out data as the stand-in for lab measurements.

The goal is to make the product more pitchable: show that the software can start with historical R&D data, train/use a surrogate, quantify uncertainty, recommend the next experiment, and incorporate scientist feedback/constraints.

---

## Product Goal

Add a new BO-focused page/tab without disrupting the existing LHS MVP.

The final software should communicate two complementary workflows:

1. **Batch Explorer / LHS Mode**
   - Explore a large candidate space quickly.
   - Rank many configurations using the MLP surrogate and weighted objectives.
   - Useful for initial design-space exploration.

2. **Optimization Loop / BO Mode**
   - Sequentially recommend the next experiment to run.
   - Show uncertainty and expected improvement.
   - Let a scientist accept/reject/skip suggestions.
   - Support simple constraint updates.
   - In demo mode, reveal measured results from held-out real data.

---

## Non-Negotiable Requirements

### Do Not Break Existing LHS Functionality

Do not remove or regress any of the current functionality:

- Existing recommendation endpoint.
- Existing LHS candidate generation.
- Existing weighted scoring.
- Existing fixed input behavior.
- Existing table of recommended candidates.
- Existing parallel coordinates visualization.
- Existing ONNX inference flow.

The new BO feature must be additive.

### Do Not Pretend MLP Predictions Are Lab Results

The BO loop must not use `MLP(X*)` as the observed result in replay mode.

Acceptable uses of the MLP:

- Predict expected KPI values for display.
- Score candidate configurations.
- Compare predicted vs observed values after a replay point is revealed.
- Provide context to the scientist.

Not acceptable:

- Treating `MLP(X*)` as the real experiment result and feeding it back as ground truth.

### Keep UI Scientifically Honest

The UI must clearly distinguish:

- `predicted` KPI values from the surrogate model.
- `observed` KPI values from the historical replay dataset or future real lab input.
- `uncertainty` from the BO surrogate/acquisition model.
- `suggested` candidates that have not yet been tested.

---

## Recommended UX Structure

Add navigation with at least two top-level modes:

```text
Batch Explorer | Optimization Loop
```

Alternative labels are acceptable if they fit the existing app style:

- Batch Explorer / Sequential Optimizer
- Design Space Explorer / BO Lab
- Explore / Optimize

The current LHS screen should live under **Batch Explorer**.

The new BO screen should live under **Optimization Loop**.

---

# Part 1 — Backend Data Model

## 1.1 Add Experiment Log Data Model

Create a persistent experiment log for each project.

For the MVP, a local CSV or JSONL file is acceptable. A database can come later.

Suggested path:

```text
backend/data/experiment_logs/{project_id}.jsonl
```

Each row should represent one experiment/candidate state.

Suggested schema:

```json
{
  "experiment_id": "uuid",
  "project_id": "pem_fuel_cell_demo",
  "iteration": 4,
  "source": "initial_observed | bo_suggested | replay_revealed | manual_observed",
  "status": "suggested | accepted | rejected | skipped | tested | observed",
  "inputs": {
    "pt_c_ratio": 0.42,
    "i_c_ratio": 0.8
  },
  "predicted_outputs": {
    "bol_current_density": 1.23,
    "eol_current_density": 0.98,
    "ecsa_loss": 0.12
  },
  "observed_outputs": {
    "bol_current_density": 1.18,
    "eol_current_density": 0.94,
    "ecsa_loss": 0.14
  },
  "uncertainty": {
    "objective_std": 0.08,
    "kpi_std": {
      "bol_current_density": 0.05,
      "eol_current_density": 0.04,
      "ecsa_loss": 0.02
    }
  },
  "objective": {
    "predicted_score": 0.74,
    "observed_score": 0.69,
    "acquisition_score": 0.13,
    "expected_improvement": 0.06
  },
  "review": {
    "decision": "accepted | rejected | skipped | none",
    "reason": "infeasible | unsafe | too_expensive | outside_protocol | chemically_implausible | duplicate | other",
    "notes": "Scientist comment here"
  },
  "metadata": {
    "model_version": "pem_fuel_cell_demo_mlp_v1",
    "bo_run_id": "uuid",
    "created_at": "2026-04-29T12:00:00Z"
  }
}
```

Implementation notes:

- Use Pydantic models in `backend/app/schemas.py`.
- Keep this schema extensible.
- `observed_outputs` can be `null` for suggestions that are not yet tested/revealed.
- `review` can be `null` or default to `none`.

Suggested Pydantic models:

```python
class ExperimentStatus(str, Enum):
    suggested = "suggested"
    accepted = "accepted"
    rejected = "rejected"
    skipped = "skipped"
    tested = "tested"
    observed = "observed"

class ExperimentSource(str, Enum):
    initial_observed = "initial_observed"
    bo_suggested = "bo_suggested"
    replay_revealed = "replay_revealed"
    manual_observed = "manual_observed"

class ReviewDecision(str, Enum):
    none = "none"
    accepted = "accepted"
    rejected = "rejected"
    skipped = "skipped"

class ReviewReason(str, Enum):
    infeasible = "infeasible"
    unsafe = "unsafe"
    too_expensive = "too_expensive"
    outside_protocol = "outside_protocol"
    chemically_implausible = "chemically_implausible"
    duplicate = "duplicate"
    other = "other"

class ExperimentReview(BaseModel):
    decision: ReviewDecision = ReviewDecision.none
    reason: ReviewReason | None = None
    notes: str | None = None

class LoggedExperiment(BaseModel):
    experiment_id: str
    project_id: str
    iteration: int
    source: ExperimentSource
    status: ExperimentStatus
    inputs: dict[str, float]
    predicted_outputs: dict[str, float] | None = None
    observed_outputs: dict[str, float] | None = None
    uncertainty: dict[str, Any] | None = None
    objective: dict[str, float] | None = None
    review: ExperimentReview | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

---

## 1.2 Add BO Configuration Model

Create a config object that controls the BO run.

Suggested schema:

```json
{
  "objective_weights": {
    "bol_current_density": 0.5,
    "eol_current_density": 0.4,
    "ecsa_loss": -0.1
  },
  "strategy": "balanced",
  "acquisition_function": "ei",
  "exploration_level": "balanced",
  "n_suggestions": 1,
  "input_constraints": {
    "pt_c_ratio": { "min": 0.2, "max": 0.6, "fixed": null },
    "i_c_ratio": { "min": 0.6, "max": 1.2, "fixed": null }
  },
  "forbidden_regions": [],
  "random_seed": 42,
  "replay_mode": true
}
```

Suggested Pydantic models:

```python
class BOExplorationLevel(str, Enum):
    conservative = "conservative"
    balanced = "balanced"
    exploratory = "exploratory"

class BOAcquisitionFunction(str, Enum):
    ei = "ei"
    ucb = "ucb"
    pi = "pi"

class InputConstraint(BaseModel):
    min: float | None = None
    max: float | None = None
    fixed: float | None = None

class BOConfig(BaseModel):
    objective_weights: dict[str, float]
    strategy: BOExplorationLevel = BOExplorationLevel.balanced
    acquisition_function: BOAcquisitionFunction = BOAcquisitionFunction.ei
    exploration_level: BOExplorationLevel = BOExplorationLevel.balanced
    n_suggestions: int = 1
    input_constraints: dict[str, InputConstraint] = Field(default_factory=dict)
    random_seed: int = 42
    replay_mode: bool = True
```

For the UI, expose presets first, not raw BO parameters.

Map presets internally:

```python
EXPLORATION_PRESETS = {
    "conservative": {
        "acq": "ei",
        "xi": 0.001,
        "kappa": 1.0,
        "description": "Prefer regions near known good experiments."
    },
    "balanced": {
        "acq": "ei",
        "xi": 0.01,
        "kappa": 2.0,
        "description": "Balance promising regions and uncertainty."
    },
    "exploratory": {
        "acq": "ucb",
        "xi": 0.05,
        "kappa": 4.0,
        "description": "Search more uncertain regions."
    }
}
```

---

# Part 2 — Historical Replay Data

## 2.1 Prepare Replay Dataset

Create a replay dataset from the real paper data.

Suggested path:

```text
backend/data/replay/{project_id}_hidden_pool.csv
```

This file should contain real experimental rows that were **not used in MLP training**.

Each row must include:

- All input variables used by the project schema.
- All output variables used by the project schema.
- Optional metadata from the paper.

Example:

```csv
replay_id,pt_c_ratio,i_c_ratio,...,bol_current_density,eol_current_density,ecsa_loss
paper_001,0.42,0.81,...,1.18,0.94,0.14
```

Important:

- Do not generate fake outputs for replay mode.
- Replay outputs must come from real held-out measurements.
- If the real dataset is small, it is okay. The point is to demonstrate the closed-loop architecture honestly.

---

## 2.2 Add Nearest Hidden Experiment Mapping

When BO suggests a continuous `X*`, map it to the nearest unused hidden experiment in normalized input space.

Algorithm:

```text
1. Load hidden replay pool.
2. Remove rows already revealed/used.
3. Normalize each input dimension using project schema min/max or replay pool min/max.
4. Normalize X* using the same scaling.
5. Compute Euclidean distance from X* to each hidden row.
6. Select nearest hidden row.
7. Return its real measured outputs as observed Y*.
8. Mark replay row as used.
```

Suggested implementation:

```python
def find_nearest_hidden_experiment(
    project_id: str,
    suggested_inputs: dict[str, float],
    used_replay_ids: set[str],
) -> ReplayMatch:
    schema = get_project_schema(project_id)
    input_names = [x["name"] for x in schema["inputs"]]
    replay_df = load_replay_pool(project_id)
    replay_df = replay_df[~replay_df["replay_id"].isin(used_replay_ids)]

    # normalize with schema bounds
    x_star = []
    X_pool = []
    for name in input_names:
        spec = next(i for i in schema["inputs"] if i["name"] == name)
        lo = spec["min"]
        hi = spec["max"]
        denom = max(hi - lo, 1e-12)
        x_star.append((suggested_inputs[name] - lo) / denom)
        X_pool.append((replay_df[name].to_numpy() - lo) / denom)

    X_pool = np.vstack(X_pool).T
    x_star = np.array(x_star)
    distances = np.linalg.norm(X_pool - x_star, axis=1)
    idx = int(np.argmin(distances))
    row = replay_df.iloc[idx]

    return ReplayMatch(
        replay_id=str(row["replay_id"]),
        matched_inputs={name: float(row[name]) for name in input_names},
        observed_outputs={name: float(row[name]) for name in output_names},
        distance=float(distances[idx]),
    )
```

Design note:

- The UI should display both the BO-suggested `X*` and the matched historical experiment if they differ.
- This keeps the demo honest.

Example UI copy:

```text
BO suggested a continuous candidate. In replay mode, it was mapped to the nearest hidden real experiment from the paper dataset.
```

---

# Part 3 — Bayesian Optimization Service

## 3.1 Add New Service Module

Create:

```text
backend/app/services/bayesian_optimization.py
```

Responsibilities:

- Load observed experiments.
- Fit/update BO model.
- Compute acquisition function.
- Suggest next candidate.
- Estimate uncertainty.
- Return structured recommendation object.

Use `scikit-optimize`, `scikit-learn GaussianProcessRegressor`, or BoTorch.

Recommended for MVP:

- Start with `scikit-learn` GaussianProcessRegressor directly for clarity and control.
- Use expected improvement or UCB manually.
- Avoid overengineering BoTorch unless already installed and familiar.

Dependency options:

```toml
scikit-learn
scipy
numpy
pandas
```

or:

```toml
scikit-optimize>=0.10
```

---

## 3.2 BO Objective Definition

Convert multi-output KPIs into a scalar objective using the same objective weights concept as LHS mode.

Important:

- Use observed outputs when fitting the BO GP.
- Use predicted outputs only for display or pre-scoring, not as ground truth.

Suggested scoring function:

```python
def compute_weighted_objective(
    outputs: dict[str, float],
    objective_weights: dict[str, float],
    normalization_stats: dict[str, dict[str, float]],
) -> float:
    score = 0.0
    for name, weight in objective_weights.items():
        value = outputs[name]
        lo = normalization_stats[name]["min"]
        hi = normalization_stats[name]["max"]
        denom = max(hi - lo, 1e-12)
        normalized = (value - lo) / denom
        score += weight * normalized
    return float(score)
```

Normalization options:

- Use observed experiment min/max for the current BO run.
- Or use schema-level output bounds if available.
- Be consistent and log the normalization method in BO run metadata.

---

## 3.3 BO Candidate Suggestion Algorithm

For MVP, implement candidate suggestion by sampling a candidate pool and evaluating acquisition values.

This is simpler than continuous numerical optimization and works well with constraints.

Algorithm:

```text
1. Load observed experiments with observed_outputs.
2. Convert each observed row to X and scalar y.
3. Fit GaussianProcessRegressor on X → y.
4. Generate candidate pool using LHS or random sampling within current constraints.
5. Filter invalid/forbidden/fixed candidates.
6. Predict mean and std for each candidate using GP.
7. Compute acquisition value: EI or UCB.
8. Pick candidate with max acquisition.
9. Also call the existing MLP ONNX model to get predicted KPI values for display.
10. Return the selected candidate with mean, std, acquisition score, predicted outputs, and reason.
```

This has an advantage: it reuses the existing LHS candidate generation idea while adding uncertainty and sequential acquisition.

Suggested core function:

```python
def suggest_next_experiment(
    project_id: str,
    config: BOConfig,
) -> BOSuggestion:
    observed = load_observed_experiments(project_id)
    X, y = build_bo_training_arrays(observed, config.objective_weights)

    gp = fit_gp(X, y)

    candidates = generate_candidate_pool(
        project_id=project_id,
        constraints=config.input_constraints,
        n_candidates=5000,
        random_seed=config.random_seed,
    )

    mu, std = gp.predict(candidate_array, return_std=True)
    acquisition = compute_acquisition(mu, std, y_best=np.max(y), config=config)
    best_idx = int(np.argmax(acquisition))

    selected_inputs = candidates[best_idx]
    predicted_outputs, model_version, _ = predict_rows(project_id, [selected_inputs])

    return BOSuggestion(
        inputs=selected_inputs,
        predicted_outputs=predicted_outputs[0],
        uncertainty={
            "objective_mean": float(mu[best_idx]),
            "objective_std": float(std[best_idx]),
        },
        objective={
            "acquisition_score": float(acquisition[best_idx]),
            "expected_improvement": float(acquisition[best_idx]) if config.acquisition_function == "ei" else None,
            "current_best_observed": float(np.max(y)),
        },
        metadata={
            "model_version": model_version,
            "n_observed": len(observed),
            "candidate_pool_size": len(candidates),
            "acquisition_function": config.acquisition_function,
            "exploration_level": config.exploration_level,
        }
    )
```

---

## 3.4 Acquisition Functions

Implement at least EI and UCB.

Expected Improvement:

```python
def expected_improvement(mu, sigma, y_best, xi=0.01):
    sigma = np.maximum(sigma, 1e-12)
    improvement = mu - y_best - xi
    z = improvement / sigma
    return improvement * norm.cdf(z) + sigma * norm.pdf(z)
```

Upper Confidence Bound:

```python
def upper_confidence_bound(mu, sigma, kappa=2.0):
    return mu + kappa * sigma
```

Preset behavior:

```text
Conservative:
  EI with low xi or UCB with low kappa
  More exploitation

Balanced:
  EI with default xi or UCB with medium kappa
  Mix of exploitation and exploration

Exploratory:
  UCB with high kappa
  More uncertainty-seeking
```

---

## 3.5 Initial Observed Experiments

BO needs initial observed experiments.

Create one of these approaches:

### Option A — Seed from visible training data

Use a subset of the real visible dataset as initial observations.

Suggested file:

```text
backend/data/replay/{project_id}_initial_observed.csv
```

Then add an endpoint/action to initialize the BO log:

```text
POST /projects/{project_id}/bo/initialize-replay
```

This should:

- Clear or archive existing replay log for the project.
- Load initial observed rows.
- Write them into experiment log with `source = initial_observed` and `status = observed`.
- Keep hidden replay pool unrevealed.

### Option B — Manually log observations

Support later, but not required for first demo.

---

# Part 4 — Backend API Endpoints

Add new endpoints while preserving existing ones.

## 4.1 Get BO State

```http
GET /projects/{project_id}/bo/state
```

Returns:

```json
{
  "project_id": "pem_fuel_cell_demo",
  "observed_count": 12,
  "suggested_count": 3,
  "rejected_count": 1,
  "current_best": {
    "experiment_id": "...",
    "inputs": {},
    "observed_outputs": {},
    "observed_score": 0.82
  },
  "latest_suggestion": {},
  "history": [],
  "config": {}
}
```

## 4.2 Initialize Replay

```http
POST /projects/{project_id}/bo/initialize-replay
```

Request:

```json
{
  "reset": true,
  "n_initial": 10,
  "selection": "diverse | random | first_n"
}
```

Behavior:

- Create initial observed experiment log from the initial replay dataset.
- Mark hidden pool rows as unrevealed.
- Return current BO state.

## 4.3 Suggest Next Experiment

```http
POST /projects/{project_id}/bo/suggest
```

Request:

```json
{
  "objective_weights": {},
  "exploration_level": "balanced",
  "acquisition_function": "ei",
  "input_constraints": {},
  "n_suggestions": 1,
  "replay_mode": true
}
```

Response:

```json
{
  "suggestion": {
    "experiment_id": "...",
    "status": "suggested",
    "inputs": {},
    "predicted_outputs": {},
    "uncertainty": {},
    "objective": {},
    "reason": "High expected improvement with medium uncertainty near known high-performing region."
  }
}
```

Important:

- This endpoint suggests but does not automatically reveal hidden outputs unless explicitly configured.
- The suggested candidate should be logged with `status = suggested`.

## 4.4 Review Suggestion

```http
POST /projects/{project_id}/bo/experiments/{experiment_id}/review
```

Request:

```json
{
  "decision": "accepted | rejected | skipped",
  "reason": "infeasible | unsafe | too_expensive | outside_protocol | chemically_implausible | duplicate | other",
  "notes": "Optional scientist note."
}
```

Behavior:

- Update experiment log.
- If rejected, do not reveal hidden result.
- If accepted, mark as accepted and allow reveal/test step.

## 4.5 Reveal Replay Result

```http
POST /projects/{project_id}/bo/experiments/{experiment_id}/reveal-replay-result
```

Behavior:

- Load the suggested candidate.
- Find nearest unused hidden real experiment.
- Attach matched observed outputs.
- Mark experiment as `observed` or `tested`.
- Store replay metadata:
  - `matched_replay_id`
  - `distance_to_suggestion`
  - `matched_inputs`
- Return updated experiment and BO state.

Response should include:

```json
{
  "experiment": {
    "suggested_inputs": {},
    "matched_replay_inputs": {},
    "observed_outputs": {},
    "predicted_outputs": {},
    "prediction_error": {},
    "replay_distance": 0.08
  }
}
```

## 4.6 Update BO Constraints

```http
POST /projects/{project_id}/bo/config
```

Request:

```json
{
  "input_constraints": {
    "pt_c_ratio": { "min": 0.2, "max": 0.5, "fixed": null }
  },
  "exploration_level": "conservative"
}
```

Behavior:

- Save config for this BO run/project.
- Next suggestion uses updated constraints.

---

# Part 5 — Frontend UI

## 5.1 Add Top-Level Tab Navigation

Add a navigation control:

```text
Batch Explorer | Optimization Loop
```

Existing LHS UI goes under **Batch Explorer**.

New BO UI goes under **Optimization Loop**.

Do not hide or remove the LHS UI.

---

## 5.2 Optimization Loop Page Layout

Suggested layout:

```text
┌──────────────────────────────────────────────────────────────┐
│ Optimization Loop                                             │
│ Sequential experiment recommendation with uncertainty.        │
├──────────────────────────────────────────────────────────────┤
│ Setup Panel                                                   │
│ - Objective weights                                           │
│ - Exploration mode: Conservative / Balanced / Exploratory     │
│ - Acquisition: EI / UCB                                       │
│ - Replay mode status                                          │
│ - Initialize replay button                                    │
├──────────────────────────────────────────────────────────────┤
│ Current Best + Next Suggested Experiment                      │
│ - Current best observed experiment                            │
│ - Next suggested experiment card                              │
│ - Predicted KPIs                                              │
│ - Uncertainty                                                 │
│ - Expected improvement                                        │
│ - Accept / Reject / Reveal result buttons                     │
├──────────────────────────────────────────────────────────────┤
│ Visualizations                                                │
│ - Objective over iterations                                   │
│ - Predicted vs observed KPIs                                  │
│ - Uncertainty / acquisition chart                             │
│ - Input-space/replay distance indicator                       │
├──────────────────────────────────────────────────────────────┤
│ Constraints Panel                                             │
│ - Fixed inputs                                                │
│ - Min/max range overrides                                     │
│ - Rejection reasons                                           │
├──────────────────────────────────────────────────────────────┤
│ Experiment History Table                                      │
│ - iteration                                                   │
│ - status                                                      │
│ - suggested inputs                                            │
│ - predicted score                                             │
│ - observed score                                              │
│ - uncertainty                                                 │
│ - decision                                                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 5.3 Setup Panel

Controls:

- Objective weights, reused from existing LHS flow if possible.
- Exploration preset:
  - Conservative
  - Balanced
  - Exploratory
- Acquisition function:
  - Expected Improvement
  - Upper Confidence Bound
- Replay mode badge:
  - `Historical replay enabled`
- Buttons:
  - `Initialize Replay`
  - `Suggest Next Experiment`
  - `Reset Loop`

Suggested helper copy:

```text
Replay mode uses held-out real experiments as stand-ins for future lab results. The optimizer does not see these measurements until a suggestion is accepted and revealed.
```

---

## 5.4 Next Suggested Experiment Card

This is the core pitch card.

Display:

```text
Next Suggested Experiment

Inputs:
- Pt/C ratio: 0.42
- I/C ratio: 0.81
- ...

Predicted KPIs:
- BoL current density: 1.23 A/cm²
- EoL current density: 0.98 A/cm²
- ECSA loss: 0.12

Optimization:
- Expected improvement: +0.06
- Uncertainty: medium
- Acquisition score: 0.13
- Exploration mode: Balanced

Why this experiment?
High expected improvement with moderate uncertainty near a known high-performing region.

Actions:
[Accept] [Reject] [Reveal replay result]
```

If replay result is revealed, update card:

```text
Replay Result Revealed

Suggested candidate was mapped to nearest hidden real experiment.
Replay distance: 0.08

Observed KPIs:
- BoL current density: 1.18 A/cm²
- EoL current density: 0.94 A/cm²
- ECSA loss: 0.14

Prediction error:
- BoL: -0.05
- EoL: -0.04
- ECSA loss: +0.02
```

---

## 5.5 Scientist Review / Rejection UX

When user clicks reject, open a small dialog:

```text
Why reject this suggestion?

[ ] Infeasible
[ ] Unsafe
[ ] Too expensive
[ ] Outside protocol
[ ] Chemically implausible
[ ] Duplicate / not useful
[ ] Other

Notes: __________________________

[Save rejection]
```

After rejection:

- Mark candidate as rejected in history.
- Do not reveal replay result.
- Next suggestion should be possible.
- Future version can learn from rejected regions; first version only logs this information.

---

## 5.6 Constraints Panel

Add simple constraint editing.

For each input variable:

```text
Input name | Schema min | Active min | Active max | Fixed value | Enabled
```

User can:

- Narrow min/max range.
- Fix a variable.
- Clear override.

Example:

```text
Pt loading:
Schema range: 0.1 - 0.6
Active range: 0.1 - 0.4
Fixed: none
```

When constraints change:

- Save config through BO config endpoint.
- Show a small message:

```text
Future suggestions will respect updated constraints.
```

Important:

- Constraints should only affect BO suggestions.
- Do not break existing LHS fixed input behavior.
- You may optionally later share constraint components between LHS and BO, but avoid a risky refactor now.

---

## 5.7 Visualizations

Implement at least three BO-specific visualizations.

### Visualization 1 — Objective Over Iterations

Line chart:

- x-axis: iteration
- y-axis: weighted objective score
- lines/points:
  - observed score
  - predicted score at suggestion time
  - current best observed score

Purpose:

Show whether the loop is finding better experiments over time.

### Visualization 2 — Uncertainty / Acquisition Over Iterations

Bar or line chart:

- x-axis: iteration
- y-axis:
  - objective uncertainty std
  - acquisition score
  - expected improvement

Purpose:

Show exploration vs exploitation behavior.

### Visualization 3 — Predicted vs Observed KPI Comparison

For revealed/tested experiments:

- x-axis: iteration or KPI
- y-axis: value
- compare predicted vs observed values

Purpose:

Show surrogate quality and expose when the model is wrong.

### Optional Visualization 4 — Input Space Distance / Replay Distance

Show how far the suggested continuous candidate was from the nearest hidden real experiment.

Purpose:

Make replay mode honest and transparent.

---

# Part 6 — UI Copy / Positioning

Use clear language that supports the pitch.

## Batch Explorer Copy

```text
Batch Explorer
Scan thousands of candidate configurations using the surrogate model and weighted objectives. Useful for understanding the design space and identifying promising regions before starting a sequential optimization loop.
```

## Optimization Loop Copy

```text
Optimization Loop
Recommend the next experiment to run using Bayesian optimization, uncertainty estimates, and expert constraints. In replay mode, held-out real experiments are used as stand-ins for lab results.
```

## Replay Mode Copy

```text
Historical replay mode
The optimizer only sees the initial observed experiments. When a suggested experiment is accepted, the system reveals the nearest hidden real measurement from the paper dataset and adds it to the experiment log.
```

## Scientist Review Copy

```text
AI suggestions are not executed blindly. Domain experts can accept, reject, or constrain the search space before the next recommendation.
```

---

# Part 7 — Implementation Order

Follow this order to reduce risk.

## Step 1 — Preserve Existing App

- Run existing app.
- Confirm current LHS recommendations still work.
- Add frontend tab shell only.
- Move existing LHS page into `Batch Explorer` tab without changing behavior.

Acceptance criteria:

- Existing LHS flow behaves exactly as before.
- Existing charts and tables still render.
- No backend regression.

## Step 2 — Add Experiment Log Utilities

Implement:

- `load_experiment_log(project_id)`
- `append_experiment(project_id, experiment)`
- `update_experiment(project_id, experiment_id, patch)`
- `get_bo_state(project_id)`

Acceptance criteria:

- Can initialize and read a project experiment log.
- JSONL or CSV persists across backend restarts.

## Step 3 — Add Replay Dataset Loader

Implement:

- `load_initial_observed(project_id)`
- `load_hidden_replay_pool(project_id)`
- `get_used_replay_ids(project_id)`
- `find_nearest_hidden_experiment(...)`

Acceptance criteria:

- Initial observed data can seed the experiment log.
- Hidden pool remains unrevealed.
- Suggested inputs can be mapped to nearest unused hidden row.

## Step 4 — Add BO Suggestion Service

Implement:

- Scalar objective from observed outputs.
- GP fitting.
- Candidate pool generation under constraints.
- EI/UCB acquisition.
- MLP prediction for display.
- Suggestion logging.

Acceptance criteria:

- Given initial observations, endpoint returns a next suggested experiment.
- Suggestion includes predicted outputs, uncertainty, acquisition score, and explanation.
- The BO loop does not use predicted outputs as observed ground truth.

## Step 5 — Add BO API Endpoints

Implement endpoints:

- `GET /projects/{project_id}/bo/state`
- `POST /projects/{project_id}/bo/initialize-replay`
- `POST /projects/{project_id}/bo/suggest`
- `POST /projects/{project_id}/bo/experiments/{experiment_id}/review`
- `POST /projects/{project_id}/bo/experiments/{experiment_id}/reveal-replay-result`
- `POST /projects/{project_id}/bo/config`

Acceptance criteria:

- Frontend can drive full replay loop through API.

## Step 6 — Build BO UI Page

Implement:

- Setup panel.
- Next suggestion card.
- Current best card.
- Scientist review controls.
- Replay reveal button.
- Experiment history table.

Acceptance criteria:

- User can initialize replay.
- User can request next suggestion.
- User can accept/reject suggestion.
- User can reveal replay result.
- History updates.

## Step 7 — Add Visualizations

Implement charts:

- Objective over iterations.
- Uncertainty/acquisition over iterations.
- Predicted vs observed KPIs.
- Optional replay distance.

Acceptance criteria:

- Charts update after each reveal.
- Charts distinguish predicted vs observed.

## Step 8 — Add Constraints Panel

Implement:

- Editable active min/max per input.
- Fixed values.
- Save config.
- Apply constraints to BO candidate generation.

Acceptance criteria:

- Future BO suggestions respect updated constraints.
- LHS UI remains unaffected.

---

# Part 8 — Suggested File/Module Structure

Backend:

```text
backend/app/services/
  bayesian_optimization.py
  experiment_log.py
  replay_mapping.py
  bo_config.py

backend/app/schemas.py
  BOConfig
  BOSuggestion
  LoggedExperiment
  ExperimentReview
  ReplayMatch

backend/data/replay/
  pem_fuel_cell_demo_initial_observed.csv
  pem_fuel_cell_demo_hidden_pool.csv

backend/data/experiment_logs/
  pem_fuel_cell_demo.jsonl
```

Frontend:

```text
frontend/src/components/bo/
  OptimizationLoopPage.tsx
  BOSetupPanel.tsx
  NextSuggestionCard.tsx
  CurrentBestCard.tsx
  BOHistoryTable.tsx
  BOConstraintsPanel.tsx
  BOObjectiveChart.tsx
  BOUncertaintyChart.tsx
  PredictedObservedChart.tsx
  ScientistReviewDialog.tsx

frontend/src/api/
  boApi.ts
```

If the current frontend structure is different, adapt to existing conventions instead of forcing this exact structure.

---

# Part 9 — Tests / Validation

## Backend Tests

Add tests for:

1. Experiment log append/read/update.
2. Replay initialization.
3. Nearest hidden experiment mapping.
4. BO suggestion returns valid schema.
5. BO suggestion respects constraints.
6. Rejected suggestions are not revealed.
7. Revealed replay result comes from hidden real data, not MLP prediction.
8. Used replay rows are not reused.

Critical test:

```text
Given a BO suggestion X*, when reveal-replay-result is called, observed_outputs must equal the matched hidden replay row outputs, not predicted_outputs.
```

## Frontend Smoke Tests

Manual validation:

1. Existing Batch Explorer still works.
2. Optimization Loop tab loads.
3. Replay can initialize.
4. Suggestion appears.
5. Accept/reject works.
6. Reveal result works.
7. Charts update.
8. Constraints affect future suggestions.

---

# Part 10 — Demo Flow to Support YC Pitch

The final implementation should support this demo script:

```text
1. Open Batch Explorer.
2. Show that the software can scan thousands of possible configurations with the MLP surrogate.
3. Explain this is useful for broad design-space exploration.
4. Switch to Optimization Loop.
5. Show initial observed experiments from historical paper data.
6. Click Suggest Next Experiment.
7. Show predicted KPIs, uncertainty, and expected improvement.
8. Accept suggestion.
9. Reveal replay result.
10. Show that the result came from held-out real paper data.
11. Show objective/history chart improving over iterations.
12. Reject one suggestion as infeasible.
13. Narrow a constraint.
14. Generate a new suggestion that respects scientist feedback.
```

Pitch message the software should make visually obvious:

```text
Mirai turns historical R&D data into a closed-loop experiment recommendation system.
It does not replace scientists; it helps them choose better experiments faster.
```

---

# Part 11 — Things Not To Build Yet

Do not prioritize these until the BO demo is working:

- Full MLflow model registry.
- Cloud multi-tenant deployment.
- Scientist chat agent.
- Automatic model selection across LR/XGBoost/MLP.
- Full LIMS integration.
- Complex feasibility classifier.
- Full MLOps retraining scheduler.

These are important next steps, but they dilute the immediate MVP/pitch focus.

Only add small hooks where cheap:

- Include `model_version` in BO logs.
- Keep experiment logs structured for future MLflow tracking.
- Keep config modular so optimizers/models can be swapped later.

---

# Final Acceptance Criteria

The task is complete when:

1. Existing LHS Batch Explorer works as before.
2. A new Optimization Loop / BO tab exists.
3. BO can initialize from initial observed real data.
4. BO can suggest a next experiment with uncertainty/acquisition metadata.
5. The user can accept/reject suggestions.
6. Replay mode reveals real held-out measurements, not MLP-generated labels.
7. Experiment history persists.
8. UI visualizes objective improvement, uncertainty, and predicted-vs-observed values.
9. Constraints can be edited and affect future BO suggestions.
10. The resulting demo clearly supports the pitch:

```text
From historical experimental data → to surrogate model → to uncertainty-aware next-experiment recommendations → to human-in-the-loop scientific feedback.
```
