from typing import Any

import numpy as np
import torch
from botorch.acquisition import ExpectedImprovement, UpperConfidenceBound
from botorch.fit import fit_gpytorch_mll
from botorch.models import SingleTaskGP
from botorch.models.transforms import Standardize
from botorch.optim import optimize_acqf
from gpytorch.mlls import ExactMarginalLogLikelihood


def _fixed_features_from_bounds(bounds: np.ndarray) -> dict[int, float]:
    return {
        index: float(row[0])
        for index, row in enumerate(bounds.T)
        if abs(float(row[1]) - float(row[0])) <= 1e-12
    }


def _safe_bounds(bounds: np.ndarray) -> torch.Tensor:
    safe = np.asarray(bounds, dtype=np.float64).copy()
    if safe.shape[0] != 2:
        raise ValueError("BoTorch bounds must have shape [2, d]")

    for index in range(safe.shape[1]):
        if safe[1, index] < safe[0, index]:
            raise ValueError("BoTorch bounds lower values must be <= upper values")
        if safe[1, index] <= safe[0, index]:
            padding = 1e-6
            safe[0, index] = max(0.0, safe[0, index] - padding)
            safe[1, index] = min(1.0, safe[1, index] + padding)
    return torch.tensor(safe, dtype=torch.double)


def suggest_next_candidate(
    x_observed: np.ndarray,
    y_observed: np.ndarray,
    bounds: np.ndarray,
    config: dict[str, Any],
) -> dict[str, float | list[float]]:
    """Fit a BoTorch GP on observed data and optimize EI/UCB.

    X values are expected to be normalized to [0, 1]. y values must be real
    observed objective scores, not MLP fantasy labels.
    """

    x_array = np.asarray(x_observed, dtype=np.float64)
    y_array = np.asarray(y_observed, dtype=np.float64).reshape(-1, 1)
    bounds_array = np.asarray(bounds, dtype=np.float64)

    if x_array.ndim != 2:
        raise ValueError("x_observed must be a 2D array")
    if y_array.shape[0] != x_array.shape[0]:
        raise ValueError("y_observed length must match x_observed")
    if x_array.shape[0] < 2:
        raise ValueError("At least two observed points are required for BoTorch BO")

    train_x = torch.tensor(x_array, dtype=torch.double)
    train_y = torch.tensor(y_array, dtype=torch.double)

    model = SingleTaskGP(train_x, train_y, outcome_transform=Standardize(m=1))
    mll = ExactMarginalLogLikelihood(model.likelihood, model)
    fit_gpytorch_mll(mll)

    acquisition_name = str(config.get("acquisition", "ei")).lower()
    y_best = float(np.max(y_array))
    if acquisition_name == "ucb":
        beta = float(config.get("beta", 4.0))
        acquisition = UpperConfidenceBound(model, beta=beta)
    else:
        xi = float(config.get("xi", 0.0))
        acquisition = ExpectedImprovement(model, best_f=y_best + xi)

    fixed_features = _fixed_features_from_bounds(bounds_array)
    if len(fixed_features) == x_array.shape[1]:
        candidate = torch.tensor([[fixed_features[index] for index in range(x_array.shape[1])]], dtype=torch.double)
        acquisition_value = acquisition(candidate)
    else:
        candidate, acquisition_value = optimize_acqf(
            acquisition,
            bounds=_safe_bounds(bounds_array),
            q=1,
            num_restarts=int(config.get("num_restarts", 10)),
            raw_samples=int(config.get("raw_samples", 256)),
            fixed_features=fixed_features or None,
            options={"batch_limit": 5, "maxiter": int(config.get("maxiter", 200))},
        )
    candidate = torch.clamp(candidate.detach(), 0.0, 1.0)

    posterior = model.posterior(candidate)
    mean = float(posterior.mean.detach().reshape(-1)[0])
    variance = max(float(posterior.variance.detach().reshape(-1)[0]), 0.0)
    std = float(np.sqrt(variance))

    return {
        "x_next": candidate.cpu().numpy().reshape(-1).tolist(),
        "mean": mean,
        "variance": variance,
        "std": std,
        "acquisition": float(acquisition_value.detach().reshape(-1)[0]),
        "expected_improvement": max(mean - y_best, 0.0),
    }
