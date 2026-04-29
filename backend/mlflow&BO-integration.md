# MLflow & Bayesian Optimization Integration

This document outlines where and how to add MLflow for model registry/tracking and a Bayesian Optimization (BO) loop, connecting them to the existing inference pipeline. It references actual code locations throughout.

---

## 0. What We Are Currently Doing — and Why

Before discussing the future, it's worth documenting the design rationale behind the current system. Understanding *why* things are built this way makes the migration path clearer.

### Why LHS + Weighted Scoring Instead of Bayesian Optimization

Bayesian Optimization is the gold standard for sequential experiment optimization — but it comes with prerequisites that the current system deliberately chose not to meet at this stage:

**Prerequisite 1: An experiment feedback loop.**
BO needs real observations. You run an experiment, measure the real output, feed it back into the model, and the model becomes more accurate. Without this loop, BO is just a fancy way of doing random search. The current system has no way to log real experimental results — there's no `ObservedExperiment` endpoint, no experiment database, no workflow for a lab technician to input measured values. Building that loop requires domain-specific infrastructure (a LIMS, a database, a data entry UI, error handling for bad measurements, outlier handling) that goes well beyond the DoE engine itself.

**Prerequisite 2: A slow, expensive evaluation process.**
BO's value is most obvious when each experiment costs time or money — a 24-hour lab test, a CFD simulation that takes 2 hours, a materials synthesis that takes a week. If evaluating a candidate is cheap and fast (as it is here: ONNX inference is ~1ms), then the overhead of fitting a Gaussian Process, computing an acquisition function, and managing a feedback loop is hard to justify. Running 10,000 LHS candidates through the surrogate in 10ms and sorting by weighted score achieves essentially the same result with far less complexity.

**Prerequisite 3: A well-characterized uncertainty model.**
BO with a Gaussian Process gives you uncertainty estimates — but only as good as the GP's noise assumption. If your surrogate model (the MLP) is wrong by ±10% on some KPIs, the uncertainty estimates from the GP are built on top of those errors and may be misleading. You need to validate calibration before trusting EI or UCB to make good exploration/exploitation trade-offs.

**Why Latin Hypercube Sampling (LHS) + weighted scoring was the right first step:**
- Ships with a working UI today
- The user can explore the design space visually with the parallel coordinates chart
- The table shows concrete parameter sets to try
- It's fast and cheap to run
- It surfaces the shape of the surrogate model's response surface without needing a GP
- It's easy to understand and explain

The current system is a **batch exploration tool** — good for when you want to see a wide slice of the design space, rank many candidates, and pick a batch to try in the lab. The BO loop would be the next step for **iterative sequential optimization** after the first batch of experiments returns real results.

### Why Weighted Scores Instead of a "Current Best" Reference Point

The system asks for objective weights rather than a reference point because:

**Explicit trade-off control.** Weights let you express *how much* you care about each KPI relative to the others, even if they have different units (A/cm² vs. fraction vs. no-unit). The weighted sum of normalized values is a proxy for a utility function. This is the standard approach in multi-objective optimization when you want a single scalar to rank candidates.

**Pareto frontier awareness.** By sampling many candidates (up to 100,000) and visualizing them all, you can see the Pareto frontier — the set of non-dominated candidates where improving one KPI necessarily worsens another. This is information you'd lose if you just provided a "current best" and asked for the single next point.

**No ground truth required.** The "current best" approach in classic BO requires that you have at least one real experiment with real measured outputs. Weights work purely on the surrogate model's predictions, which is sufficient for batch exploration.

**What the weight interface actually does** (`recommendation.py:72–93`):

```python
# Each KPI is min-max normalized to [0, 1] within the candidate batch
normalized = (value - min) / (max - min)
# Negative weights flip direction: minimize KPIs get a negative weight
scores += weight * normalized
```

The `direction` field on each output in `schema.json` (maximize/minimize) is what lets the system normalize correctly, but the sign of the weight is what the user controls. A weight of `-0.1` on `ecsa_loss` tells the system "lower ECSA loss is better, but it's only 10% as important as a weight of `0.1` on `bol_current_density`".

### Why Fixed Inputs Are Exposed in the UI

`recommendation.py:42–69`:

```python
if name in request.fixed_inputs:
    columns[name] = np.full(request.n_candidates, value)  # same for all candidates
else:
    columns[name] = _lhs_values(rng, minimum, maximum, n_candidates)
```

Some experimental parameters are not variables in a given study. For example:
- Operating voltage might be fixed by the test protocol
- Some parameters might be locked because changing them requires hardware modifications
- Cost-related parameters might be fixed because you're optimizing within an existing supplier contract

Fixed inputs reduce the dimensionality of the search space, which is especially valuable with LHS — fewer dimensions means better space-filling coverage for the same number of candidates.

In an iterative BO setting with a real feedback loop, fixed inputs become less important because the model learns the parameter space interactively. But for batch exploration, they're a practical constraint mechanism.

### Why Candidates, Table Rows, and Chart Rows Are Separate Controls

| Control | Location | Purpose |
|---|---|---|
| `n_candidates` | `recommendation.py:42` | **Exploration resolution.** How many LHS samples to draw. More = finer coverage of the design space, slower inference, more data to score and sort. |
| `tableTopK` | `doeUtils.ts:5` (default 5) | **Decision focus.** How many rows to show in the recommendations table. Purely a UX choice — the user only wants to see the top handful. |
| `visualizationTopK` | `doeUtils.ts:7` (default 75, cap 100) | **Plotly performance cap.** Parallel coordinates charts degrade with >100 traces. The cap is enforced at `maxVisualizationTopK = 100` (`doeUtils.ts:7`) and clamped in `App.tsx:141`. |

These are **exploration budget controls** for the batch approach. In a BO loop they would be replaced by the acquisition function's natural exploration driven by uncertainty — no need to manually tune the number of candidates.

---

## 1. MLflow Integration

### What MLflow Would Add

MLflow handles two concerns relevant here:

1. **Experiment tracking** — logging hyperparameters, metrics (MAE/RMSE), and artifacts during training
2. **Model registry** — versioning, staging (staging→production), and serving ONNX models from a central store

### Where We Are Today

`backend/training/train_mlp.py` already has a stub for MLflow logging (`_maybe_log_mlflow`, lines 68–79):

```python
def _maybe_log_mlflow(params: dict, metrics: dict[str, float], artifacts: list[Path]) -> None:
    try:
        import mlflow
    except ImportError:
        return

    with mlflow.start_run(run_name=f"{PROJECT_ID}_mlp"):
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        for artifact in artifacts:
            if artifact.exists():
                mlflow.log_artifact(str(artifact))
```

It silently does nothing if MLflow isn't installed — which is the current state. The call site is at line 263–273 of `train_mlp.py`.

### What's Missing to Enable It

**1. Install mlflow** — add to `[dependency-groups]` in `backend/pyproject.toml`:

```toml
[dependency-groups]
dev = [
    ...
    "mlflow>=2.0",
]
```

**2. Configure the tracking URI** — either:

```python
import mlflow
mlflow.set_tracking_uri("file:///tmp/mlruns")              # local
mlflow.set_tracking_uri("http://localhost:5000")           # mlflow server
mlflow.set_tracking_uri("mysql+pymysql://user:pass@host/mlflow")  # DB backend
```

This should live in a `training/config.py` or at the top of `train_mlp.py`.

**3. Register the ONNX model** — after training, push to the MLflow model registry:

```python
import mlflow.onnx

# Log the ONNX file as an MLflow artifact
mlflow.onnx.log_model(
    onnx_model=onnx_path,
    artifact_path="model",
    registered_model_name=f"{PROJECT_ID}_mlp",
)
```

This replaces the current `metadata.json` workflow with a versioned entry in MLflow's model registry. The `model_version` string returned at inference (`backend/app/services/prediction.py:34`) would come from MLflow instead of the JSON file.

### Champion / Challenger System

Today the system has **one active model** per project — loaded at startup via `project_registry.py:get_project_model_path()` (lines 84–89), which points to the single `model.onnx` in `artifacts/{project_id}/`. There's no concept of multiple models competing.

A champion/challenger setup would layer on top:

```
MLflow Model Registry
├── pem_fuel_cell_demo
│   ├── Version 1  → Staging  (challenger)
│   ├── Version 2  → Production (champion) ← served at runtime
│   └── Version 3  → Archived
```

**Where to implement the routing:**

`backend/app/services/project_registry.py` — modify `get_project_model_path()` (lines 84–89) to resolve a `DOE_MODEL_STAGE` env var:

```python
import os

def get_project_model_path(project_id: str) -> Path:
    ...
    if stage := os.getenv("DOE_MODEL_STAGE"):
        # Ask MLflow for the Stage model URI
        client = MlflowClient()
        mv = client.get_latest_version(model_name, stage=stage)
        uri = client.get_model_version_download_uri(mv)
        return _download_or_symlink(uri, project_dir / "model.onnx")
    return project_dir / "model.onnx"
```

Or, for a simpler version without a running MLflow server, encode the champion version in `artifacts/{project_id}/.active`:

```
artifacts/pem_fuel_cell_demo/
  .active          ← contains "model_v2.onnx"
  model_v1.onnx   ← archived
  model_v2.onnx   ← champion
  model_v3.onnx   ← challenger (staging)
```

A REST endpoint to switch stages:

```python
# backend/app/main.py — new endpoint
@app.post("/projects/{project_id}/models/stage")
def set_model_stage(project_id: str, target_stage: Literal["staging", "production"]):
    client = MlflowClient()
    versions = client.search_model_versions(model_name)
    target = next(v for v in versions if v.current_stage == target_stage)
    _set_active_model(project_id, target.version)
    return {"status": "ok", "model_version": f"{project_id}_mlp_v{target.version}"}
```

### What This Would Change

| Component | Change |
|---|---|
| `train_mlp.py` | Enable MLflow logging, register model on train |
| `project_registry.py` | Add stage-aware model path resolution |
| `model_loader.py` | Already flexible — only needs the file path |
| `main.py` | Optionally add `/projects/{id}/models/stage` endpoint |
| `docker-compose.yml` | Optionally add MLflow server container |

---

## 2. Bayesian Optimization Loop

### Where We Are Today

The current `recommend_experiments` in `backend/app/services/recommendation.py` (line 96–119) is **random sampling + weighted scoring**:

1. Generates `n_candidates` candidates using **Latin Hypercube Sampling (LHS)** (`_generate_candidates`, lines 42–69)
2. Runs all candidates through the surrogate model (`predict_rows`, calls `prediction.py:12`)
3. Scores them with a weighted sum of normalized KPIs (`_score_predictions`, lines 72–93)
4. Returns the top-`k`

This is a solid baseline but has no **acquisition function**, no **surrogate model uncertainty**, and no **feedback loop** from real experimental results.

### Where to Add BO

The BO loop belongs **outside the API request/response cycle**. It's a long-running process that feeds back into the model. Two places it could live:

**Option A — As a new FastAPI background task (inside backend)**

New endpoint `POST /projects/{project_id}/bo-run` kicks off a `BackgroundTask` that:
1. Loads observed experiments from a database (or CSV log)
2. Fits a BO surrogate (with uncertainty) on the observed data
3. Uses an acquisition function (EI, UCB) to pick the next batch
4. Logs the suggested experiments

**Option B — As a standalone CLI/scheduler (outside backend)**

A script in `backend/training/` that reads from a **experiment log** (new file or DB table) and writes new candidates to an **experiment queue**.

### Detailed Integration Points

**A. Experiment log — what the BO loop needs as input**

The BO loop requires observed (input → real_output) pairs. Currently there's no such log. You'd add:

```
backend/data/experiment_logs/{project_id}.csv
  timestamp, pt_c_ratio, i_c_ratio, ..., bol_current_density_observed, eol_current_density_observed, ...
```

A new schema Pydantic model in `backend/app/schemas.py`:

```python
class ObservedExperiment(BaseModel):
    inputs: dict[str, float]
    outputs: dict[str, float]   # real measured values, not predictions
```

And a new endpoint:

```python
# backend/app/main.py
@app.post("/projects/{project_id}/experiments")
def log_observed_experiment(project_id: str, experiment: ObservedExperiment):
    append_to_csv(f"data/experiment_logs/{project_id}.csv", experiment)
    return {"status": "logged"}
```

**B. The BO algorithm itself**

Install `scikit-optimize` or `botorch`:

```toml
# backend/pyproject.toml
dependencies = [
    ...existing...
    "scikit-optimize>=0.10",
]
```

New module `backend/app/services/bayesian_optimization.py`:

```python
import numpy as np
from skopt import gp_minimize
from skopt.acquisition import gaussian_ei

def bo_suggest_next(
    project_id: str,
    observed_rows: list[dict[str, float]],
    objective_weights: dict[str, float],
    n_suggestions: int = 5,
) -> list[dict[str, float]]:
    schema = get_project_schema(project_id)
    input_names = [i["name"] for i in schema["inputs"]]
    output_names = [i["name"] for i in schema["outputs"]]

    X = np.array([[row[n] for n in input_names] for row in observed_rows])

    # Weighted composite objective
    def composite_objective(X):
        preds, _, _ = predict_rows(project_id, [dict(zip(input_names, row)) for row in X])
        return weighted_score([dict(zip(output_names, p.values())) for p in preds], objective_weights)

    bounds = [(schema["inputs"][i]["min"], schema["inputs"][i]["max"]) for i in range(len(input_names))]

    result = gp_minimize(
        composite_objective,
        bounds,
        n_calls=20,
        n_initial_points=10,
        random_state=42,
        acq_func="EI",
        noise="gaussian",
    )

    return [dict(zip(input_names, x)) for x in result.x_iters[-n_suggestions:]]
```

**C. New endpoint to trigger BO**

```python
# backend/app/main.py
@app.post("/projects/{project_id}/bo-suggest")
def bo_suggest(
    project_id: str,
    request: RecommendRequest,   # reuse the same request shape
):
    observed = load_observed_experiments(project_id)
    suggestions = bo_suggest_next(project_id, observed, request.objective_weights, n_suggestions=request.top_k)
    return {"suggestions": suggestions}
```

**D. Closing the loop — retraining the surrogate**

When enough new observations accumulate (e.g., ≥ 500 new rows in the log), the system should retrain. This is where MLflow's champion/challenger model would be tested:

```python
def maybe_retrain_if_ready(project_id: str, threshold: int = 500) -> None:
    observed_count = count_logged_experiments(project_id)
    if observed_count >= threshold:
        run_id = trigger_retraining(project_id)  # calls train_mlp.py in a subprocess
        # Register as "challenger" in MLflow
        promote_if_better(run_id, project_id)
```

This could run on a schedule via APScheduler in `main.py`:

```python
# backend/app/main.py
from apscheduler.schedulers.background import BackgroundScheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all_models()
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: maybe_retrain_if_ready("pem_fuel_cell_demo"), "interval", hours=24)
    scheduler.start()
    yield
    scheduler.shutdown()
```

---

## 3. Connecting to Model Serving

The current serving model is **static file loading at startup**:

```
backend/app/main.py:36
  load_all_models()
    backend/app/services/model_loader.py:33
      ort.InferenceSession(str(model_path), ...)
```

MLflow model registry would change this to:

```
startup
  ├─ List registered model versions from MLflow
  ├─ Download champion model to /tmp/{project_id}/model.onnx
  └─ ort.InferenceSession("/tmp/.../model.onnx")
```

The `predict` function in `prediction.py` doesn't need changes — it calls `get_model_bundle()` which already abstracts the file path. Only `model_loader.py:get_project_model_path()` needs to support MLflow URI resolution.

For **A/B shadow mode** (shadow testing the challenger alongside the champion):

```python
def predict_with_shadow(project_id: str, row: dict):
    champion_pred = predict(project_id, row)
    shadow_pred = predict_with_shadow_model(project_id, row)  # loads challenger in a separate session
    log_comparison(project_id, champion_pred, shadow_pred)
    return champion_pred
```

---

## 4. Summary of Gaps

| Concern | Current State | Rationale | What Needs Building |
|---|---|---|---|
| Optimization method | LHS + weighted ranking | Right for batch exploration; no experiment feedback loop yet | BO with acquisition function |
| Objective input | Weights per KPI | Explicit trade-off control, works with surrogate-only (no real data) | Optionally: "current best" reference for EI |
| Fixed inputs | Exposed in UI | Practical constraints for batch studies | Less relevant in iterative BO |
| Candidate budget | Manual (n_candidates 1–100k) | Exploration resolution in LHS | Replaced by acquisition function in BO |
| MLflow tracking | Stub exists, never called | Optional — local metadata.json is sufficient for now | Enable, configure tracking URI |
| MLflow model registry | None | Single static model is fine for demo | Register model on train, add stage routing |
| Champion/challenger | None | No model versioning yet | Stage-aware model path, API to switch |
| Experiment log | None | No feedback loop infrastructure | DB/CSV for observed (input, real_output) |
| BO acq function | None | LHS covers design space well enough for batch | `gaussian_ei` or `UCB` on top of surrogate |
| BO loop | None | Sequential iteration not implemented yet | Background task or CLI, feed results back into log |
| Model retraining | Manual | Only one model, rarely retrained | Scheduler triggered by log size, challenger promotion |
| A/B shadow testing | None | No infrastructure for model comparison | Parallel ONNX session, diff logging |