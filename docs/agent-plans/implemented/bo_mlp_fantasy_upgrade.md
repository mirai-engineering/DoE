# BO Upgrade + Fantasy Rollout Integration Guide

## Overview

This guide upgrades the Optimization Loop to:

1. Use BoTorch for Bayesian Optimization
2. Add Fantasy Rollout using the MLP surrogate
3. Preserve scientific integrity:
   - BO trains only on real observed data
   - MLP is used only for prediction and simulation

---

## Installation (uv-compatible)

Add dependencies:

```bash
uv add botorch gpytorch
```

Or update your pyproject.toml:

```toml
[project]
dependencies = [
    "botorch",
    "gpytorch"
]
```

---

## Part 1 — BoTorch Integration

### Create module

```
backend/bo/botorch_engine.py
```

### Core function

```python
import numpy as np
import torch
from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_model
from gpytorch.mlls import ExactMarginalLogLikelihood
from botorch.acquisition import ExpectedImprovement, UpperConfidenceBound
from botorch.optim import optimize_acqf


def suggest_next_candidate(X_obs, y_obs, bounds, config):
    X = torch.tensor(X_obs, dtype=torch.float32)
    y = torch.tensor(y_obs, dtype=torch.float32).unsqueeze(-1)

    model = SingleTaskGP(X, y)
    mll = ExactMarginalLogLikelihood(model.likelihood, model)
    fit_gpytorch_model(mll)

    if config.get("acquisition") == "ucb":
        beta = config.get("beta", 2.0)
        acq = UpperConfidenceBound(model, beta=beta)
    else:
        acq = ExpectedImprovement(model, best_f=y.max())

    candidate, acq_value = optimize_acqf(
        acq,
        bounds=torch.tensor(bounds, dtype=torch.float32),
        q=1,
        num_restarts=10,
        raw_samples=256,
    )

    posterior = model.posterior(candidate)
    mean = posterior.mean.item()
    var = posterior.variance.item()

    return {
        "x_next": candidate.numpy().flatten(),
        "acquisition": acq_value.item(),
        "uncertainty": var,
        "expected_improvement": mean - y.max().item()
    }
```

---

## Part 2 — Fantasy Rollout

### Create module

```
backend/bo/fantasy_rollout.py
```

### Core function

```python
import numpy as np
from .botorch_engine import suggest_next_candidate


def run_fantasy_rollout(X_real, y_real, bounds, mlp_model, steps=5, config={}):
    X_fant = X_real.copy()
    y_fant = y_real.copy()

    trajectory = []

    for t in range(steps):
        result = suggest_next_candidate(X_fant, y_fant, bounds, config)
        x_next = result["x_next"]

        y_mlp = mlp_model.predict(x_next.reshape(1, -1)).item()

        X_fant = np.vstack([X_fant, x_next])
        y_fant = np.append(y_fant, y_mlp)

        trajectory.append({
            "iteration": t,
            "x": x_next.tolist(),
            "predicted_score": y_mlp,
            "uncertainty": result["uncertainty"],
            "acquisition": result["acquisition"]
        })

    return trajectory
```

---

## Critical Rule

Fantasy data must NEVER be:

- stored in experiment logs
- treated as observed
- used to retrain the real BO loop

---

## API Endpoint

```
POST /bo/fantasy-rollout
```

Request:

```json
{
  "steps": 5,
  "config": {}
}
```

Response:

```json
{
  "fantasy_trajectory": [...]
}
```

---

## UI Integration

Add button:

```
Run 5-Step Lookahead
```

Visualization:

- Real: solid line
- Predicted: light line
- Fantasy: dashed line

Tooltip:

```
Simulated using MLP (not observed)
```

---

## Safety (Basic)

Add distance-based gating:

```python
def is_low_confidence(x, X_real, threshold=0.2):
    distances = np.linalg.norm(X_real - x, axis=1)
    return distances.min() > threshold
```

---

## Acceptance Criteria

- BO suggestions improve stability
- Fantasy rollout works independently
- No leakage between MLP and real data
- UI clearly distinguishes simulation vs reality

---

## Summary

- BoTorch improves statistical robustness
- Fantasy rollout adds foresight
- MLP accelerates exploration (without replacing experiments)
