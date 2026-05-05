import numpy as np

from ..schemas import BOConfig, BOFantasyRolloutRequest, BOFantasyRolloutResponse, BOFantasyStep
from .bayesian_optimization import (
    EXPLORATION_PRESETS,
    _nearest_normalized_distance,
    _normalized_bounds,
    _normalized_input_array,
    _observed_experiments,
    _output_normalization_stats,
    _raw_inputs_from_normalized,
    compute_weighted_objective,
    resolve_bo_config,
)
from .botorch_engine import suggest_next_candidate
from .experiment_log import load_experiment_log
from .prediction import predict_rows
from .project_registry import get_project_schema


LOW_CONFIDENCE_DISTANCE_THRESHOLD = 0.2


def run_fantasy_rollout(project_id: str, request: BOFantasyRolloutRequest) -> BOFantasyRolloutResponse:
    schema = get_project_schema(project_id)
    config = resolve_bo_config(project_id, request.config or BOConfig())
    history = load_experiment_log(project_id)
    observed = _observed_experiments(history)
    if len(observed) < 2:
        raise ValueError("Initialize replay with at least two observed experiments before running fantasy rollout")

    stats = _output_normalization_stats(observed, list(config.objective_weights))
    x_real = _normalized_input_array(schema, observed)
    y_real = np.asarray(
        [
            compute_weighted_objective(experiment.observed_outputs or {}, config.objective_weights, stats)
            for experiment in observed
        ],
        dtype=np.float64,
    )

    x_fantasy = x_real.copy()
    y_fantasy = y_real.copy()
    bounds = _normalized_bounds(schema, config)
    preset = EXPLORATION_PRESETS[config.exploration_level]

    trajectory: list[BOFantasyStep] = []
    model_version = "unknown"
    for step in range(1, request.steps + 1):
        result = suggest_next_candidate(
            x_fantasy,
            y_fantasy,
            bounds,
            {
                "acquisition": config.acquisition_function.value,
                "xi": float(preset["xi"]),
                "beta": float(preset["kappa"]) ** 2,
                "num_restarts": 8,
                "raw_samples": 128,
            },
        )
        normalized_candidate = np.asarray(result["x_next"], dtype=np.float64)
        inputs = _raw_inputs_from_normalized(schema, normalized_candidate)
        predicted_outputs, _, model_version = predict_rows(project_id, [inputs], warn_near_bounds=False)
        predicted_score = compute_weighted_objective(predicted_outputs[0], config.objective_weights, stats)

        distance_to_real = _nearest_normalized_distance(normalized_candidate, x_real)
        low_confidence = distance_to_real > LOW_CONFIDENCE_DISTANCE_THRESHOLD
        trajectory.append(
            BOFantasyStep(
                iteration=step,
                inputs=inputs,
                predicted_outputs=predicted_outputs[0],
                predicted_score=predicted_score,
                acquisition_score=float(result["acquisition"]),
                expected_improvement=max(float(result["expected_improvement"]), 0.0),
                uncertainty={
                    "objective_mean": float(result["mean"]),
                    "objective_std": float(result["std"]),
                    "objective_variance": float(result["variance"]),
                    "distance_threshold": LOW_CONFIDENCE_DISTANCE_THRESHOLD,
                },
                distance_to_nearest_real=distance_to_real,
                low_confidence_region=low_confidence,
            )
        )

        x_fantasy = np.vstack([x_fantasy, normalized_candidate])
        y_fantasy = np.append(y_fantasy, predicted_score)

    return BOFantasyRolloutResponse(
        project_id=project_id,
        fantasy_trajectory=trajectory,
        metadata={
            "source": "mlp_fantasy",
            "model_version": model_version,
            "n_real_observed": len(observed),
            "steps": request.steps,
            "not_logged": True,
            "scientific_note": "Fantasy rollout uses MLP predictions for simulation only; these points are not stored as observed experiments.",
        },
    )
