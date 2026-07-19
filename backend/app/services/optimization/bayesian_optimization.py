from dataclasses import dataclass
from datetime import datetime, timezone
from math import erf, pi, sqrt
from typing import Any
from uuid import uuid4

import numpy as np

from ...schemas import (
    BOAcquisitionFunction,
    BOConfig,
    BOConfigUpdate,
    BOCurrentBest,
    BOExplorationLevel,
    BOInitializeReplayRequest,
    BOReviewRequest,
    BORevealReplayExperiment,
    BORevealReplayResponse,
    BOReviewResponse,
    BOStateResponse,
    BOSuggestResponse,
    ExperimentReview,
    ExperimentSource,
    ExperimentStatus,
    LoggedExperiment,
    ReviewDecision,
)
from .experiment_log import (
    append_experiment,
    clear_experiment_log,
    get_experiment,
    load_experiment_log,
    load_saved_bo_config,
    save_bo_config,
    update_experiment,
    write_experiment_log,
)
from .botorch_engine import suggest_next_candidate
from ..model_serving.prediction import predict_rows
from ..model_serving.preprocessing import input_names, output_names, validate_row
from ..platform.project_registry import get_project_schema
from .replay_mapping import find_nearest_hidden_experiment, get_used_replay_ids, select_initial_observed


EXPLORATION_PRESETS: dict[BOExplorationLevel, dict[str, float | str]] = {
    BOExplorationLevel.conservative: {
        "xi": 0.001,
        "kappa": 1.0,
        "description": "Prefer regions near known good experiments.",
    },
    BOExplorationLevel.balanced: {
        "xi": 0.01,
        "kappa": 2.0,
        "description": "Balance promising regions and uncertainty.",
    },
    BOExplorationLevel.exploratory: {
        "xi": 0.05,
        "kappa": 4.0,
        "description": "Search more uncertain regions.",
    },
}

DEFAULT_OBJECTIVE_WEIGHTS = {
    "bol_current_density": 0.35,
    "eol_current_density": 0.35,
    "durability_score": 0.2,
    "ecsa_loss": -0.1,
    "cost_score": -0.1,
}


@dataclass(frozen=True)
class FittedGaussianProcess:
    training_inputs: np.ndarray
    y_mean: float
    y_scale: float
    length_scale: float
    cholesky: np.ndarray
    alpha: np.ndarray


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_objective_weights(schema: dict) -> dict[str, float]:
    weights: dict[str, float] = {}
    for output in schema.get("outputs", []):
        fallback = -0.1 if output.get("direction") == "minimize" else 0.2
        weights[output["name"]] = DEFAULT_OBJECTIVE_WEIGHTS.get(output["name"], fallback)
    return weights


def resolve_bo_config(project_id: str, incoming: BOConfig | BOConfigUpdate | None = None) -> BOConfig:
    schema = get_project_schema(project_id)
    saved_config = load_saved_bo_config(project_id)
    base = saved_config or BOConfig(objective_weights=default_objective_weights(schema))

    if incoming is not None:
        update = incoming.model_dump(exclude_unset=True, mode="python")
        if isinstance(incoming, BOConfigUpdate):
            update = {key: value for key, value in update.items() if value is not None}
        payload = base.model_dump(mode="python")
        payload.update(update)
        base = BOConfig.model_validate(payload)

    if not base.objective_weights:
        base = base.model_copy(update={"objective_weights": default_objective_weights(schema)})

    _validate_bo_config(schema, base)
    return base


def _validate_bo_config(schema: dict, config: BOConfig) -> None:
    known_outputs = set(output_names(schema))
    unknown_outputs = [name for name in config.objective_weights if name not in known_outputs]
    if unknown_outputs:
        raise ValueError(f"Objective weights reference unknown outputs: {', '.join(sorted(unknown_outputs))}")

    known_inputs = {item["name"]: item for item in schema.get("inputs", [])}
    unknown_inputs = [name for name in config.input_constraints if name not in known_inputs]
    if unknown_inputs:
        raise ValueError(f"Input constraints reference unknown inputs: {', '.join(sorted(unknown_inputs))}")

    if config.n_suggestions != 1:
        raise ValueError("This MVP supports n_suggestions=1")

    for name, constraint in config.input_constraints.items():
        variable = known_inputs[name]
        schema_min = float(variable["min"])
        schema_max = float(variable["max"])
        active_min = schema_min if constraint.min is None else max(schema_min, float(constraint.min))
        active_max = schema_max if constraint.max is None else min(schema_max, float(constraint.max))
        if active_min > active_max:
            raise ValueError(f"Constraint for '{name}' leaves no feasible range")
        if constraint.fixed is not None and not active_min <= float(constraint.fixed) <= active_max:
            raise ValueError(f"Fixed value for '{name}' is outside the active BO range")


def _effective_bounds(schema: dict, config: BOConfig) -> dict[str, tuple[float, float, float | None]]:
    bounds: dict[str, tuple[float, float, float | None]] = {}
    for variable in schema.get("inputs", []):
        name = variable["name"]
        minimum = float(variable["min"])
        maximum = float(variable["max"])
        fixed: float | None = None
        constraint = config.input_constraints.get(name)
        if constraint is not None:
            if constraint.min is not None:
                minimum = max(minimum, float(constraint.min))
            if constraint.max is not None:
                maximum = min(maximum, float(constraint.max))
            if constraint.fixed is not None:
                fixed = float(constraint.fixed)
        bounds[name] = (minimum, maximum, fixed)
    return bounds


def _lhs_values(rng: np.random.Generator, minimum: float, maximum: float, n_candidates: int) -> np.ndarray:
    strata = (np.arange(n_candidates, dtype=np.float64) + rng.random(n_candidates)) / n_candidates
    rng.shuffle(strata)
    return minimum + strata * (maximum - minimum)


def _generate_candidate_pool(
    schema: dict,
    config: BOConfig,
    *,
    n_candidates: int,
    random_seed: int,
) -> list[dict[str, float]]:
    bounds = _effective_bounds(schema, config)
    rng = np.random.default_rng(random_seed)
    columns: dict[str, np.ndarray] = {}
    for variable in schema.get("inputs", []):
        name = variable["name"]
        minimum, maximum, fixed = bounds[name]
        if fixed is not None:
            columns[name] = np.full(n_candidates, fixed, dtype=np.float64)
        else:
            columns[name] = _lhs_values(rng, minimum, maximum, n_candidates)

    names = input_names(schema)
    return [{name: float(columns[name][index]) for name in names} for index in range(n_candidates)]


def _observed_experiments(history: list[LoggedExperiment]) -> list[LoggedExperiment]:
    return [
        experiment
        for experiment in history
        if experiment.observed_outputs is not None
        and experiment.status in {ExperimentStatus.observed, ExperimentStatus.tested}
    ]


def _output_normalization_stats(observed: list[LoggedExperiment], names: list[str]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for name in names:
        values = [
            float(experiment.observed_outputs[name])
            for experiment in observed
            if experiment.observed_outputs is not None and name in experiment.observed_outputs
        ]
        if not values:
            stats[name] = {"min": 0.0, "max": 1.0}
            continue
        minimum = min(values)
        maximum = max(values)
        if maximum <= minimum:
            maximum = minimum + 1.0
        stats[name] = {"min": float(minimum), "max": float(maximum)}
    return stats


def compute_weighted_objective(
    outputs: dict[str, float],
    objective_weights: dict[str, float],
    normalization_stats: dict[str, dict[str, float]],
) -> float:
    score = 0.0
    for name, weight in objective_weights.items():
        if name not in outputs:
            raise ValueError(f"Outputs are missing objective KPI '{name}'")
        bounds = normalization_stats[name]
        denominator = max(bounds["max"] - bounds["min"], 1e-12)
        normalized = (float(outputs[name]) - bounds["min"]) / denominator
        score += float(weight) * normalized
    return float(score)


def _normalized_input_array(schema: dict, experiments: list[LoggedExperiment]) -> np.ndarray:
    rows: list[list[float]] = []
    for experiment in experiments:
        rows.append(_normalized_input_vector(schema, experiment.inputs).tolist())
    return np.asarray(rows, dtype=np.float64)


def _normalized_input_vector(schema: dict, inputs: dict[str, float]) -> np.ndarray:
    validate_row(schema, inputs, warn_near_bounds=False)
    values: list[float] = []
    for variable in schema.get("inputs", []):
        name = variable["name"]
        minimum = float(variable["min"])
        maximum = float(variable["max"])
        values.append((float(inputs[name]) - minimum) / max(maximum - minimum, 1e-12))
    return np.asarray(values, dtype=np.float64)


def _normalized_bounds(schema: dict, config: BOConfig) -> np.ndarray:
    bounds = _effective_bounds(schema, config)
    lower: list[float] = []
    upper: list[float] = []
    for variable in schema.get("inputs", []):
        name = variable["name"]
        schema_minimum = float(variable["min"])
        schema_maximum = float(variable["max"])
        scale = max(schema_maximum - schema_minimum, 1e-12)
        minimum, maximum, fixed = bounds[name]
        if fixed is not None:
            normalized_fixed = (fixed - schema_minimum) / scale
            lower.append(float(np.clip(normalized_fixed, 0.0, 1.0)))
            upper.append(float(np.clip(normalized_fixed, 0.0, 1.0)))
        else:
            lower.append(float(np.clip((minimum - schema_minimum) / scale, 0.0, 1.0)))
            upper.append(float(np.clip((maximum - schema_minimum) / scale, 0.0, 1.0)))
    return np.asarray([lower, upper], dtype=np.float64)


def _raw_inputs_from_normalized(schema: dict, values: list[float] | np.ndarray) -> dict[str, float]:
    normalized_values = np.asarray(values, dtype=np.float64).reshape(-1)
    names = input_names(schema)
    if normalized_values.shape[0] != len(names):
        raise ValueError("Normalized candidate dimension does not match project schema")

    inputs: dict[str, float] = {}
    for value, variable in zip(normalized_values, schema.get("inputs", []), strict=True):
        minimum = float(variable["min"])
        maximum = float(variable["max"])
        clipped = float(np.clip(value, 0.0, 1.0))
        inputs[variable["name"]] = minimum + clipped * (maximum - minimum)
    return inputs


def _nearest_normalized_distance(x_candidate: np.ndarray, x_real: np.ndarray) -> float:
    distances = np.linalg.norm(x_real - np.asarray(x_candidate, dtype=np.float64).reshape(1, -1), axis=1)
    return float(np.min(distances))


def _rbf_kernel(left: np.ndarray, right: np.ndarray, length_scale: float) -> np.ndarray:
    left_sq = np.sum(left**2, axis=1)[:, None]
    right_sq = np.sum(right**2, axis=1)[None, :]
    distances = np.maximum(left_sq + right_sq - 2.0 * left @ right.T, 0.0)
    return np.exp(-0.5 * distances / max(length_scale**2, 1e-12))


def _fit_gp(training_inputs: np.ndarray, objective_values: np.ndarray, length_scale: float = 0.35) -> FittedGaussianProcess:
    y_mean = float(np.mean(objective_values))
    y_scale = float(np.std(objective_values))
    if y_scale < 1e-8:
        y_scale = 1.0
    y_scaled = (objective_values - y_mean) / y_scale

    kernel = _rbf_kernel(training_inputs, training_inputs, length_scale)
    identity = np.eye(training_inputs.shape[0], dtype=np.float64)
    last_error: Exception | None = None
    for jitter in (1e-6, 1e-5, 1e-4, 1e-3):
        try:
            cholesky = np.linalg.cholesky(kernel + jitter * identity)
            alpha = np.linalg.solve(cholesky.T, np.linalg.solve(cholesky, y_scaled))
            return FittedGaussianProcess(training_inputs, y_mean, y_scale, length_scale, cholesky, alpha)
        except np.linalg.LinAlgError as exc:
            last_error = exc
    raise ValueError("Could not fit BO Gaussian process") from last_error


def _predict_gp(gp: FittedGaussianProcess, candidate_inputs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    cross_kernel = _rbf_kernel(gp.training_inputs, candidate_inputs, gp.length_scale)
    mean_scaled = cross_kernel.T @ gp.alpha
    solved = np.linalg.solve(gp.cholesky, cross_kernel)
    variance_scaled = np.maximum(1.0 - np.sum(solved**2, axis=0), 1e-12)
    return mean_scaled * gp.y_scale + gp.y_mean, np.sqrt(variance_scaled) * gp.y_scale


def _normal_pdf(values: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * values**2) / sqrt(2.0 * pi)


def _normal_cdf(values: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(erf)(values / sqrt(2.0)))


def expected_improvement(mu: np.ndarray, sigma: np.ndarray, y_best: float, xi: float) -> np.ndarray:
    safe_sigma = np.maximum(sigma, 1e-12)
    improvement = mu - y_best - xi
    z = improvement / safe_sigma
    return np.maximum(improvement * _normal_cdf(z) + safe_sigma * _normal_pdf(z), 0.0)


def upper_confidence_bound(mu: np.ndarray, sigma: np.ndarray, kappa: float) -> np.ndarray:
    return mu + kappa * sigma


def _experiment_iteration(history: list[LoggedExperiment]) -> int:
    if not history:
        return 1
    return max(experiment.iteration for experiment in history) + 1


def _enrich_history_with_scores(
    history: list[LoggedExperiment],
    config: BOConfig,
) -> list[LoggedExperiment]:
    observed = _observed_experiments(history)
    stats = _output_normalization_stats(observed, list(config.objective_weights))
    enriched: list[LoggedExperiment] = []
    for experiment in history:
        objective = dict(experiment.objective or {})
        if experiment.predicted_outputs is not None:
            objective["predicted_score"] = compute_weighted_objective(
                experiment.predicted_outputs,
                config.objective_weights,
                stats,
            )
        if experiment.observed_outputs is not None:
            objective["observed_score"] = compute_weighted_objective(
                experiment.observed_outputs,
                config.objective_weights,
                stats,
            )
        enriched.append(experiment.model_copy(update={"objective": objective or None}))
    return enriched


def get_bo_state(project_id: str, config: BOConfig | None = None) -> BOStateResponse:
    resolved_config = config or resolve_bo_config(project_id)
    history = _enrich_history_with_scores(load_experiment_log(project_id), resolved_config)
    observed = _observed_experiments(history)
    suggested_count = sum(
        1 for experiment in history if experiment.status in {ExperimentStatus.suggested, ExperimentStatus.accepted}
    )
    rejected_count = sum(1 for experiment in history if experiment.status == ExperimentStatus.rejected)

    current_best: BOCurrentBest | None = None
    best_observed = [
        experiment
        for experiment in observed
        if experiment.observed_outputs is not None
        and experiment.objective is not None
        and experiment.objective.get("observed_score") is not None
    ]
    if best_observed:
        best = max(best_observed, key=lambda experiment: float(experiment.objective["observed_score"]))
        current_best = BOCurrentBest(
            experiment_id=best.experiment_id,
            inputs=best.inputs,
            observed_outputs=best.observed_outputs or {},
            observed_score=float(best.objective["observed_score"]),
        )

    latest_suggestion = next(
        (
            experiment
            for experiment in reversed(history)
            if experiment.status in {ExperimentStatus.suggested, ExperimentStatus.accepted}
        ),
        None,
    )

    return BOStateResponse(
        project_id=project_id,
        observed_count=len(observed),
        suggested_count=suggested_count,
        rejected_count=rejected_count,
        current_best=current_best,
        latest_suggestion=latest_suggestion,
        history=history,
        config=resolved_config,
    )


def save_bo_config_update(project_id: str, update: BOConfigUpdate) -> BOStateResponse:
    config = resolve_bo_config(project_id, update)
    save_bo_config(project_id, config)
    return get_bo_state(project_id, config)


def initialize_replay(project_id: str, request: BOInitializeReplayRequest) -> BOStateResponse:
    schema = get_project_schema(project_id)
    config = resolve_bo_config(project_id)
    save_bo_config(project_id, config)

    if request.reset:
        clear_experiment_log(project_id)

    existing_history = load_experiment_log(project_id)
    if existing_history and not request.reset:
        return get_bo_state(project_id, config)

    rows = select_initial_observed(project_id, request.n_initial, request.selection)
    inputs = [row["inputs"] for row in rows]
    predictions, _, model_version = predict_rows(project_id, inputs, warn_near_bounds=False)

    temporary_observed = [
        LoggedExperiment(
            experiment_id=str(uuid4()),
            project_id=project_id,
            iteration=index + 1,
            source=ExperimentSource.initial_observed,
            status=ExperimentStatus.observed,
            inputs=row["inputs"],
            predicted_outputs=predictions[index],
            observed_outputs=row["outputs"],
            review=ExperimentReview(),
            metadata={
                "replay_id": str(row["replay_id"]),
                "model_version": model_version,
                "created_at": _utc_now(),
                "replay_role": "initial_observed",
            },
        )
        for index, row in enumerate(rows)
    ]

    stats = _output_normalization_stats(temporary_observed, list(config.objective_weights))
    initialized: list[LoggedExperiment] = []
    for experiment in temporary_observed:
        objective = {
            "predicted_score": compute_weighted_objective(
                experiment.predicted_outputs or {},
                config.objective_weights,
                stats,
            ),
            "observed_score": compute_weighted_objective(
                experiment.observed_outputs or {},
                config.objective_weights,
                stats,
            ),
        }
        initialized.append(experiment.model_copy(update={"objective": objective}))

    write_experiment_log(project_id, initialized)
    return get_bo_state(project_id, config)


def suggest_next_experiment(project_id: str, incoming_config: BOConfig) -> BOSuggestResponse:
    schema = get_project_schema(project_id)
    config = resolve_bo_config(project_id, incoming_config)
    save_bo_config(project_id, config)

    history = load_experiment_log(project_id)
    observed = _observed_experiments(history)
    if len(observed) < 2:
        raise ValueError("Initialize replay with at least two observed experiments before suggesting")

    stats = _output_normalization_stats(observed, list(config.objective_weights))
    objective_values = np.asarray(
        [
            compute_weighted_objective(experiment.observed_outputs or {}, config.objective_weights, stats)
            for experiment in observed
        ],
        dtype=np.float64,
    )
    training_inputs = _normalized_input_array(schema, observed)
    preset = EXPLORATION_PRESETS[config.exploration_level]

    engine_name = "botorch"
    candidate_pool_size: int | None = None
    try:
        bo_result = suggest_next_candidate(
            training_inputs,
            objective_values,
            _normalized_bounds(schema, config),
            {
                "acquisition": config.acquisition_function.value,
                "xi": float(preset["xi"]),
                "beta": float(preset["kappa"]) ** 2,
                "num_restarts": 12,
                "raw_samples": 256,
            },
        )
        selected_normalized = np.asarray(bo_result["x_next"], dtype=np.float64)
        selected_inputs = _raw_inputs_from_normalized(schema, selected_normalized)
        objective_mean = float(bo_result["mean"])
        std_value = float(bo_result["std"])
        acquisition_score = float(bo_result["acquisition"])
        expected_improvement_score = float(bo_result["expected_improvement"])
    except Exception:  # noqa: BLE001 - keep the demo usable if BoTorch optimization fails numerically.
        engine_name = "numpy_gp_fallback"
        gp = _fit_gp(training_inputs, objective_values)

        candidate_pool_size = 5000
        seed = int(config.random_seed + len(history) * 17)
        candidates = _generate_candidate_pool(schema, config, n_candidates=candidate_pool_size, random_seed=seed)
        candidate_array = np.asarray(
            [_normalized_input_vector(schema, candidate) for candidate in candidates],
            dtype=np.float64,
        )

        mu, std = _predict_gp(gp, candidate_array)
        improvement = expected_improvement(mu, std, float(np.max(objective_values)), xi=float(preset["xi"]))
        if config.acquisition_function == BOAcquisitionFunction.ucb:
            acquisition = upper_confidence_bound(mu, std, kappa=float(preset["kappa"]))
        else:
            acquisition = improvement

        best_index = int(np.argmax(acquisition))
        selected_inputs = candidates[best_index]
        selected_normalized = candidate_array[best_index]
        objective_mean = float(mu[best_index])
        std_value = float(std[best_index])
        acquisition_score = float(acquisition[best_index])
        expected_improvement_score = float(improvement[best_index])

    predicted_outputs, _, model_version = predict_rows(project_id, [selected_inputs], warn_near_bounds=False)
    nearest_real_distance = _nearest_normalized_distance(selected_normalized, training_inputs)

    uncertainty_level = "low"
    observed_spread = max(float(np.std(objective_values)), 1e-12)
    if std_value > observed_spread * 0.75:
        uncertainty_level = "high"
    elif std_value > observed_spread * 0.35:
        uncertainty_level = "medium"

    experiment = LoggedExperiment(
        experiment_id=str(uuid4()),
        project_id=project_id,
        iteration=_experiment_iteration(history),
        source=ExperimentSource.bo_suggested,
        status=ExperimentStatus.suggested,
        inputs=selected_inputs,
        predicted_outputs=predicted_outputs[0],
        observed_outputs=None,
        uncertainty={
            "objective_mean": objective_mean,
            "objective_std": std_value,
            "objective_variance": std_value**2,
            "uncertainty_level": uncertainty_level,
            "distance_to_nearest_observed": nearest_real_distance,
            "low_confidence_region": nearest_real_distance > 0.2,
        },
        objective={
            "predicted_score": compute_weighted_objective(
                predicted_outputs[0],
                config.objective_weights,
                stats,
            ),
            "acquisition_score": acquisition_score,
            "expected_improvement": expected_improvement_score,
            "current_best_observed": float(np.max(objective_values)),
        },
        review=ExperimentReview(),
        metadata={
            "model_version": model_version,
            "bo_run_id": str(uuid4()),
            "created_at": _utc_now(),
            "candidate_pool_size": candidate_pool_size,
            "optimizer_engine": engine_name,
            "acquisition_function": config.acquisition_function.value,
            "exploration_level": config.exploration_level.value,
            "n_observed": len(observed),
            "reason": _suggestion_reason(expected_improvement_score, uncertainty_level, config.exploration_level),
        },
    )
    append_experiment(project_id, experiment)
    return BOSuggestResponse(suggestion=experiment, state=get_bo_state(project_id, config))


def _suggestion_reason(
    improvement: float,
    uncertainty_level: str,
    exploration_level: BOExplorationLevel,
) -> str:
    if exploration_level == BOExplorationLevel.exploratory:
        return f"High acquisition value with {uncertainty_level} uncertainty to test an underexplored region."
    if improvement > 0:
        return f"Positive expected improvement with {uncertainty_level} uncertainty near promising observed data."
    return f"Best acquisition tradeoff available with {uncertainty_level} uncertainty under current constraints."


def review_suggestion(project_id: str, experiment_id: str, request: BOReviewRequest) -> BOReviewResponse:
    status_by_decision = {
        ReviewDecision.accepted: ExperimentStatus.accepted,
        ReviewDecision.rejected: ExperimentStatus.rejected,
        ReviewDecision.skipped: ExperimentStatus.skipped,
    }
    if request.decision == ReviewDecision.none:
        raise ValueError("Review decision must be accepted, rejected, or skipped")

    review = ExperimentReview(decision=request.decision, reason=request.reason, notes=request.notes)
    current = get_experiment(project_id, experiment_id)
    metadata = dict(current.metadata)
    metadata["reviewed_at"] = _utc_now()

    updated = update_experiment(
        project_id,
        experiment_id,
        {
            "status": status_by_decision[request.decision],
            "review": review,
            "metadata": metadata,
        },
    )
    return BOReviewResponse(experiment=updated, state=get_bo_state(project_id))


def reveal_replay_result(project_id: str, experiment_id: str) -> BORevealReplayResponse:
    config = resolve_bo_config(project_id)
    experiment = get_experiment(project_id, experiment_id)
    if experiment.status in {ExperimentStatus.rejected, ExperimentStatus.skipped}:
        raise ValueError("Rejected or skipped suggestions cannot reveal replay results")
    if experiment.status == ExperimentStatus.suggested:
        raise ValueError("Accept the suggestion before revealing the replay result")

    if experiment.observed_outputs is not None:
        metadata = experiment.metadata
        replay_distance = float(metadata.get("replay_distance", 0.0))
        matched_inputs = metadata.get("matched_inputs")
        if not isinstance(matched_inputs, dict):
            matched_inputs = experiment.inputs
        return BORevealReplayResponse(
            experiment=BORevealReplayExperiment(
                suggested_inputs=experiment.inputs,
                matched_replay_inputs={name: float(value) for name, value in matched_inputs.items()},
                observed_outputs=experiment.observed_outputs,
                predicted_outputs=experiment.predicted_outputs,
                prediction_error=metadata.get("prediction_error") if isinstance(metadata.get("prediction_error"), dict) else None,
                replay_distance=replay_distance,
            ),
            logged_experiment=experiment,
            state=get_bo_state(project_id, config),
        )

    match = find_nearest_hidden_experiment(project_id, experiment.inputs, get_used_replay_ids(project_id))
    prediction_error: dict[str, float] | None = None
    if experiment.predicted_outputs is not None:
        prediction_error = {
            name: float(match.observed_outputs[name] - experiment.predicted_outputs[name])
            for name in output_names(get_project_schema(project_id))
            if name in experiment.predicted_outputs and name in match.observed_outputs
        }

    observed_history = _observed_experiments(load_experiment_log(project_id))
    temporary_experiment = experiment.model_copy(update={"observed_outputs": match.observed_outputs})
    stats = _output_normalization_stats([*observed_history, temporary_experiment], list(config.objective_weights))
    objective = dict(experiment.objective or {})
    objective["observed_score"] = compute_weighted_objective(match.observed_outputs, config.objective_weights, stats)
    if experiment.predicted_outputs is not None:
        objective["predicted_score"] = compute_weighted_objective(experiment.predicted_outputs, config.objective_weights, stats)

    metadata: dict[str, Any] = dict(experiment.metadata)
    metadata.update(
        {
            "matched_replay_id": match.replay_id,
            "matched_inputs": match.matched_inputs,
            "prediction_error": prediction_error,
            "replay_distance": match.distance,
            "revealed_at": _utc_now(),
            "measurement_source": "hidden_replay_pool",
        }
    )
    review = experiment.review or ExperimentReview(decision=ReviewDecision.accepted)
    if review.decision == ReviewDecision.none:
        review = review.model_copy(update={"decision": ReviewDecision.accepted})

    updated = update_experiment(
        project_id,
        experiment_id,
        {
            "source": ExperimentSource.replay_revealed,
            "status": ExperimentStatus.observed,
            "observed_outputs": match.observed_outputs,
            "objective": objective,
            "review": review,
            "metadata": metadata,
        },
    )

    return BORevealReplayResponse(
        experiment=BORevealReplayExperiment(
            suggested_inputs=experiment.inputs,
            matched_replay_inputs=match.matched_inputs,
            observed_outputs=match.observed_outputs,
            predicted_outputs=experiment.predicted_outputs,
            prediction_error=prediction_error,
            replay_distance=match.distance,
        ),
        logged_experiment=updated,
        state=get_bo_state(project_id, config),
    )
