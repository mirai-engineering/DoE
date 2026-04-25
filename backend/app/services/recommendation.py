from typing import Any

import numpy as np

from ..schemas import RecommendRequest, RecommendResponse, RecommendedExperiment
from .prediction import predict_rows
from .preprocessing import output_names, validate_row
from .project_registry import get_project_schema


def _effective_bounds(schema: dict, constraints: dict[str, Any]) -> dict[str, tuple[float, float]]:
    bounds: dict[str, tuple[float, float]] = {}
    input_by_name = {item["name"]: item for item in schema.get("inputs", [])}

    unknown_constraints = [name for name in constraints if name not in input_by_name]
    if unknown_constraints:
        raise ValueError(f"Constraints reference unknown inputs: {', '.join(sorted(unknown_constraints))}")

    for name, variable in input_by_name.items():
        minimum = float(variable["min"])
        maximum = float(variable["max"])
        override = constraints.get(name)
        if override is not None:
            if not isinstance(override, dict):
                raise ValueError(f"Constraint for '{name}' must be an object with optional min/max")
            if "min" in override:
                minimum = max(minimum, float(override["min"]))
            if "max" in override:
                maximum = min(maximum, float(override["max"]))
        if minimum > maximum:
            raise ValueError(f"Constraint for '{name}' leaves no feasible range")
        bounds[name] = (minimum, maximum)
    return bounds


def _lhs_values(rng: np.random.Generator, minimum: float, maximum: float, n_candidates: int) -> np.ndarray:
    strata = (np.arange(n_candidates, dtype=np.float32) + rng.random(n_candidates)) / n_candidates
    rng.shuffle(strata)
    return minimum + strata * (maximum - minimum)


def _generate_candidates(
    schema: dict,
    request: RecommendRequest,
) -> list[dict[str, float]]:
    validate_row(schema, request.fixed_inputs, require_all=False, warn_near_bounds=False)
    bounds = _effective_bounds(schema, request.constraints)
    rng = np.random.default_rng(request.random_seed)

    columns: dict[str, np.ndarray] = {}
    for variable in schema.get("inputs", []):
        name = variable["name"]
        minimum, maximum = bounds[name]
        if name in request.fixed_inputs:
            value = float(request.fixed_inputs[name])
            if value < minimum or value > maximum:
                raise ValueError(
                    f"Fixed input '{name}'={value:g} is outside constrained bounds "
                    f"[{minimum:g}, {maximum:g}]"
                )
            columns[name] = np.full(request.n_candidates, value, dtype=np.float32)
        else:
            columns[name] = _lhs_values(rng, minimum, maximum, request.n_candidates).astype(np.float32)

    candidates: list[dict[str, float]] = []
    input_names = [item["name"] for item in schema.get("inputs", [])]
    for index in range(request.n_candidates):
        candidates.append({name: float(columns[name][index]) for name in input_names})
    return candidates


def _score_predictions(
    schema: dict,
    predictions: list[dict[str, float]],
    objective_weights: dict[str, float],
) -> np.ndarray:
    names = output_names(schema)
    unknown_weights = [name for name in objective_weights if name not in names]
    if unknown_weights:
        raise ValueError(f"Objective weights reference unknown outputs: {', '.join(sorted(unknown_weights))}")

    matrix = np.asarray([[row[name] for name in names] for row in predictions], dtype=np.float32)
    scores = np.zeros(matrix.shape[0], dtype=np.float32)
    for output_name, weight in objective_weights.items():
        index = names.index(output_name)
        values = matrix[:, index]
        minimum = float(values.min())
        maximum = float(values.max())
        if maximum <= minimum:
            continue
        normalized = (values - minimum) / (maximum - minimum)
        scores += float(weight) * normalized
    return scores


def recommend_experiments(project_id: str, request: RecommendRequest) -> RecommendResponse:
    schema = get_project_schema(project_id)
    top_k = min(request.top_k, request.n_candidates)

    candidates = _generate_candidates(schema, request)
    predictions, _, model_version = predict_rows(project_id, candidates, warn_near_bounds=False)
    scores = _score_predictions(schema, predictions, request.objective_weights)

    top_indices = np.argsort(-scores)[:top_k]
    recommendations = [
        RecommendedExperiment(
            inputs=candidates[int(index)],
            predictions=predictions[int(index)],
            score=float(scores[int(index)]),
        )
        for index in top_indices
    ]

    return RecommendResponse(
        project_id=project_id,
        recommendations=recommendations,
        model_version=model_version,
        warnings=[],
    )
