from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
import zipfile

import numpy as np
import pandas as pd

from ..schemas import RecommendRequest
from .model_quality import _prediction_path, get_active_model_metadata
from .prediction import predict_rows
from .project_registry import get_project_schema
from .recommendation import _generate_candidates, _score_predictions

REAL_PROJECT_ID = "pem_fuel_cell_real_cathode_degradation"
FUEL_CELL_BOL_OUTPUT = "bol_current_density"
FUEL_CELL_EOL_OUTPUT = "eol_current_density"
FUEL_CELL_VOLTAGE_INPUT = "operating_voltage"
FUEL_CELL_RH_INPUT = "operating_rh"


def _default_inputs(schema: dict[str, Any]) -> dict[str, float]:
    return {item["name"]: float((float(item["min"]) + float(item["max"])) / 2.0) for item in schema.get("inputs", [])}


def _project_schema(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    return get_project_schema(project_id, workspace_id) if workspace_id else get_project_schema(project_id)


def _prediction_artifact_path(project_id: str, workspace_id: str | None = None) -> Path:
    return _prediction_path(project_id, workspace_id) if workspace_id else _prediction_path(project_id)


def _is_fuel_cell_project(project_id: str, schema: dict[str, Any] | None = None) -> bool:
    schema = schema or _project_schema(project_id)
    return project_id == REAL_PROJECT_ID or schema.get("source_project_id") == REAL_PROJECT_ID


def _default_objective_weights(schema: dict[str, Any], project_id: str) -> dict[str, float]:
    outputs = schema.get("outputs", [])
    if _is_fuel_cell_project(project_id, schema) and any(item.get("name") == FUEL_CELL_BOL_OUTPUT for item in outputs):
        return {FUEL_CELL_BOL_OUTPUT: 1.0}
    for output in outputs:
        if output.get("direction") == "maximize":
            return {output["name"]: 1.0}
    return {outputs[0]["name"]: 1.0} if outputs else {}


def _predictions_artifact(project_id: str, workspace_id: str | None = None) -> pd.DataFrame:
    path = _prediction_artifact_path(project_id, workspace_id)
    if not path.exists():
        raise FileNotFoundError("Design Studio real-cell comparisons require predictions.csv. Run real-data training first.")
    return pd.read_csv(path)


def _observed_voltage_grid(project_id: str, workspace_id: str | None = None) -> list[float]:
    schema = _project_schema(project_id, workspace_id)
    if not _is_fuel_cell_project(project_id, schema):
        return []
    frame = _predictions_artifact(project_id, workspace_id)
    schema = _project_schema(project_id, workspace_id)
    voltage_schema = next((item for item in schema.get("inputs", []) if item.get("name") == FUEL_CELL_VOLTAGE_INPUT), None)
    minimum = float(voltage_schema.get("min", -np.inf)) if voltage_schema else -np.inf
    maximum = float(voltage_schema.get("max", np.inf)) if voltage_schema else np.inf
    values = sorted(float(value) for value in frame[FUEL_CELL_VOLTAGE_INPUT].dropna().unique() if minimum <= float(value) <= maximum)
    # The raw observed table can contain thousands of nearly duplicate voltage
    # values from measured curves. Keep the sweep observed-data-derived, but
    # downsample it for an interactive playground response curve.
    if len(values) > 80:
        indices = np.linspace(0, len(values) - 1, 80).round().astype(int)
        values = [values[int(index)] for index in sorted(set(indices.tolist()))]
    return values


def _plot_recipes(project_id: str, schema: dict[str, Any], workspace_id: str | None = None) -> list[dict[str, Any]]:
    metadata = schema.get("domain_metadata") if isinstance(schema.get("domain_metadata"), dict) else {}
    ui_config = metadata.get("ui_config") if isinstance(metadata.get("ui_config"), dict) else {}
    recipes = ui_config.get("plot_recipes") if isinstance(ui_config.get("plot_recipes"), list) else []
    enriched: list[dict[str, Any]] = []
    for recipe in recipes:
        item = dict(recipe)
        if item.get("kind") == "fuel_cell_polarization":
            item["enabled"] = _is_fuel_cell_project(project_id, schema)
            item["observed_voltage_grid"] = _observed_voltage_grid(project_id, workspace_id) if item["enabled"] else []
            item["x_output_bol"] = FUEL_CELL_BOL_OUTPUT
            item["x_output_eol"] = FUEL_CELL_EOL_OUTPUT
            item["y_input"] = FUEL_CELL_VOLTAGE_INPUT
        else:
            item["enabled"] = True
        enriched.append(item)
    return enriched


def _fuel_cell_preset(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    schema = _project_schema(project_id, workspace_id)
    recipe = next((item for item in _plot_recipes(project_id, schema, workspace_id) if item.get("kind") == "fuel_cell_polarization"), None)
    if not recipe:
        return {"enabled": False}
    return recipe


def get_real_cell_options(project_id: str) -> dict[str, Any]:
    try:
        frame = _predictions_artifact(project_id)
    except FileNotFoundError:
        return {"project_id": project_id, "real_cell_options": []}
    required = {"cell_id", FUEL_CELL_RH_INPUT, "split"}
    if not required.issubset(frame.columns):
        return {"project_id": project_id, "real_cell_options": []}
    rows = []
    grouped = frame.drop_duplicates(["cell_id", FUEL_CELL_RH_INPUT, "split"])
    for _, row in grouped.sort_values(["cell_id", FUEL_CELL_RH_INPUT, "split"]).iterrows():
        subset = frame[(frame["cell_id"] == row["cell_id"]) & (frame[FUEL_CELL_RH_INPUT] == row[FUEL_CELL_RH_INPUT]) & (frame["split"] == row["split"])]
        rows.append(
            {
                "cell_id": str(row["cell_id"]),
                "operating_rh": float(row[FUEL_CELL_RH_INPUT]),
                "split": str(row["split"]),
                "row_count": int(len(subset.drop_duplicates(["cell_id", FUEL_CELL_RH_INPUT, FUEL_CELL_VOLTAGE_INPUT]) if FUEL_CELL_VOLTAGE_INPUT in subset.columns else subset)),
            }
        )
    return {"project_id": project_id, "real_cell_options": rows}


def _training_overlay(project_id: str, x_variable: str | None, output_variables: list[str] | None, group_by: str | None = None, workspace_id: str | None = None) -> dict[str, Any] | None:
    if not x_variable or not output_variables:
        return None
    try:
        frame = _predictions_artifact(project_id, workspace_id)
    except FileNotFoundError:
        return None
    true_columns = [f"{name}_true" for name in output_variables if f"{name}_true" in frame.columns]
    if x_variable not in frame.columns or not true_columns:
        return None
    columns = [x_variable, *true_columns]
    if group_by and group_by in frame.columns:
        columns.append(group_by)
    if "split" in frame.columns and "split" not in columns:
        columns.append("split")
    subset = frame[columns].dropna(subset=[x_variable, *true_columns]).drop_duplicates().sort_values(x_variable)
    if len(subset) > 1200:
        subset = subset.iloc[np.linspace(0, len(subset) - 1, 1200).round().astype(int)]
    rows = []
    for _, row in subset.iterrows():
        item: dict[str, Any] = {str(x_variable): float(row[x_variable])}
        for column in true_columns:
            item[column] = float(row[column])
        if group_by and group_by in row:
            item[group_by] = str(row[group_by])
        if "split" in row:
            item["split"] = str(row["split"])
        rows.append(item)
    return {"source": "predictions.csv", "x_variable": x_variable, "output_variables": output_variables, "group_by": group_by, "rows": rows}


def _real_cell_curve(project_id: str, selection: dict[str, Any] | None, x_variable: str | None = None, output_variables: list[str] | None = None) -> dict[str, Any] | None:
    if not selection:
        return None
    try:
        frame = _predictions_artifact(project_id)
    except FileNotFoundError:
        return None
    cell_id = selection.get("cell_id")
    rh = selection.get("operating_rh")
    if not cell_id or rh is None or "cell_id" not in frame.columns or FUEL_CELL_RH_INPUT not in frame.columns:
        return None
    x_variable = x_variable or FUEL_CELL_VOLTAGE_INPUT
    output_variables = output_variables or [FUEL_CELL_BOL_OUTPUT, FUEL_CELL_EOL_OUTPUT]
    true_columns = [f"{name}_true" for name in output_variables if f"{name}_true" in frame.columns]
    required_columns = {x_variable, *true_columns}
    if not true_columns or not required_columns.issubset(frame.columns):
        return None
    subset = frame[(frame["cell_id"].astype(str) == str(cell_id)) & (np.isclose(frame[FUEL_CELL_RH_INPUT].astype(float), float(rh)))]
    if "split" in selection and selection["split"] and "split" in subset.columns:
        subset = subset[subset["split"].astype(str) == str(selection["split"])]
    # Measured values are duplicated by model_name/candidate rows; keep one physical curve.
    dedupe_columns = ["cell_id", FUEL_CELL_RH_INPUT, x_variable, *true_columns]
    subset = subset.drop_duplicates(dedupe_columns).sort_values(x_variable)
    rows = []
    for _, row in subset.iterrows():
        item = {
            "cell_id": str(row["cell_id"]),
            "split": str(row["split"]) if "split" in row else "",
            "operating_rh": float(row[FUEL_CELL_RH_INPUT]),
            str(x_variable): float(row[x_variable]),
        }
        for column in true_columns:
            item[column] = float(row[column])
        rows.append(item)
    return {"selection": selection, "x_variable": x_variable, "output_variables": output_variables, "rows": rows}


def _curve_rows(project_id: str, inputs: dict[str, float], plot_recipe_id: str | None = None, plot_recipe: dict[str, Any] | None = None, workspace_id: str | None = None) -> tuple[dict[str, Any] | None, list[str], str]:
    schema = _project_schema(project_id, workspace_id)
    response_recipe_kinds = {"fuel_cell_polarization", "scatter_response"}
    recipes = [recipe for recipe in _plot_recipes(project_id, schema, workspace_id) if recipe.get("enabled", True) and recipe.get("kind") in response_recipe_kinds]
    preset = dict(plot_recipe) if isinstance(plot_recipe, dict) else None
    if preset is not None and preset.get("kind") not in response_recipe_kinds:
        preset = None
    if preset is None:
        preset = next((item for item in recipes if item.get("id") == plot_recipe_id), None) if plot_recipe_id else None
    preset = preset or next((item for item in recipes if item.get("recommended")), None)
    if not preset or not preset.get("enabled", True):
        return None, [], "unknown"
    if preset.get("kind") == "fuel_cell_polarization":
        voltage_grid = preset["observed_voltage_grid"]
        sweep_rows = [{**inputs, FUEL_CELL_VOLTAGE_INPUT: float(voltage)} for voltage in voltage_grid]
        predictions, warnings, model_version = predict_rows(project_id, sweep_rows, warn_near_bounds=False, workspace_id=workspace_id)
        rows = [
            {
                "operating_voltage": float(row[FUEL_CELL_VOLTAGE_INPUT]),
                FUEL_CELL_BOL_OUTPUT: float(pred[FUEL_CELL_BOL_OUTPUT]),
                FUEL_CELL_EOL_OUTPUT: float(pred[FUEL_CELL_EOL_OUTPUT]),
            }
            for row, pred in zip(sweep_rows, predictions, strict=True)
        ]
        return {"preset": preset.get("id", "fuel_cell_polarization"), "recipe": preset, "rows": rows}, warnings, model_version
    if preset.get("kind") == "scatter_response":
        x_variable = (preset.get("x") or {}).get("variable")
        y_variable = (preset.get("y") or {}).get("variable")
        series_variables = [item.get("variable") for item in preset.get("series", []) if isinstance(item, dict) and item.get("variable")]
        y_variables = []
        for variable in [y_variable, *series_variables]:
            if variable and variable not in y_variables:
                y_variables.append(str(variable))
        input_schema = next((item for item in schema.get("inputs", []) if item.get("name") == x_variable), None)
        output_names = {item.get("name") for item in schema.get("outputs", [])}
        invalid_outputs = [name for name in y_variables if name not in output_names]
        if not x_variable or not y_variables or not input_schema or invalid_outputs:
            return None, ["Selected response plot is missing a valid sweep input or output variable."], "unknown"
        points = int(preset.get("points") or 60)
        points = max(10, min(points, 200))
        min_value = float(preset.get("x_min") if preset.get("x_min") is not None else input_schema.get("min", 0))
        max_value = float(preset.get("x_max") if preset.get("x_max") is not None else input_schema.get("max", 1))
        if min_value > max_value:
            min_value, max_value = max_value, min_value
        grid = np.linspace(min_value, max_value, points)
        sweep_rows = [{**inputs, str(x_variable): float(value)} for value in grid]
        predictions, warnings, model_version = predict_rows(project_id, sweep_rows, warn_near_bounds=False, workspace_id=workspace_id)
        rows = []
        for row, pred in zip(sweep_rows, predictions, strict=True):
            next_row = {str(x_variable): float(row[str(x_variable)])}
            for variable in y_variables:
                next_row[variable] = float(pred[variable])
            rows.append(next_row)
        recipe = {**preset, "y_variables": y_variables, "points": points}
        return {"preset": preset.get("id", "scatter_response"), "recipe": recipe, "rows": rows}, warnings, model_version
    return None, [f"Plot recipe kind is not supported yet: {preset.get('kind')}"], "unknown"


def get_design_studio_state(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    schema = _project_schema(project_id, workspace_id)
    recipes = _plot_recipes(project_id, schema, workspace_id)
    response_recipe_kinds = {"fuel_cell_polarization", "scatter_response"}
    design_recipes = [recipe for recipe in recipes if recipe.get("enabled", True) and recipe.get("kind") in response_recipe_kinds]
    ui_config = schema.get("domain_metadata", {}).get("ui_config", {}) if isinstance(schema.get("domain_metadata"), dict) else {}
    design_config = ui_config.get("design_studio", {}) if isinstance(ui_config.get("design_studio"), dict) else {}
    configured_recipe_id = design_config.get("primary_plot_recipe_id") or ui_config.get("selected_plot_recipe_id")
    selected_recipe_id = next((recipe.get("id") for recipe in design_recipes if recipe.get("id") == configured_recipe_id), None)
    selected_recipe_id = selected_recipe_id or next((recipe.get("id") for recipe in design_recipes if recipe.get("recommended")), None)
    selected_recipe_id = selected_recipe_id or (design_recipes[0].get("id") if design_recipes else "")
    return {
        "project_id": project_id,
        "active_model": get_active_model_metadata(project_id),
        "inputs": schema.get("inputs", []),
        "outputs": schema.get("outputs", []),
        "default_inputs": _default_inputs(schema),
        "default_objective_weights": _default_objective_weights(schema, project_id),
        "plot_recipes": design_recipes,
        "selected_plot_recipe_id": selected_recipe_id,
        "presets": {"fuel_cell_polarization": _fuel_cell_preset(project_id)},
        "real_cell_options": get_real_cell_options(project_id).get("real_cell_options", []),
    }


def predict_design(project_id: str, payload: dict[str, Any], workspace_id: str | None = None) -> dict[str, Any]:
    inputs = {key: float(value) for key, value in payload.get("inputs", {}).items()}
    predictions, point_warnings, point_model_version = predict_rows(project_id, [inputs], warn_near_bounds=True, workspace_id=workspace_id)
    curve, curve_warnings, curve_model_version = _curve_rows(project_id, inputs, payload.get("plot_recipe_id"), payload.get("plot_recipe"), workspace_id=workspace_id)
    curve_recipe = curve.get("recipe", {}) if isinstance(curve, dict) else {}
    comparison_x = ((curve_recipe.get("x") or {}).get("variable") if isinstance(curve_recipe, dict) else None) or FUEL_CELL_VOLTAGE_INPUT
    comparison_outputs = curve_recipe.get("y_variables") if isinstance(curve_recipe, dict) else None
    if not comparison_outputs and isinstance(curve_recipe, dict):
        y_variable = (curve_recipe.get("y") or {}).get("variable")
        series_variables = [item.get("variable") for item in curve_recipe.get("series", []) if isinstance(item, dict) and item.get("variable")]
        comparison_outputs = [item for item in [y_variable, *series_variables] if item]
    comparison_output_names = [str(item) for item in comparison_outputs] if comparison_outputs else None
    comparison = _real_cell_curve(project_id, payload.get("comparison_real_cell"), str(comparison_x), comparison_output_names)
    training_overlay = _training_overlay(
        project_id,
        str(comparison_x),
        comparison_output_names,
        group_by=str(payload.get("training_overlay_group_by") or "") or None,
        workspace_id=workspace_id,
    )
    return {
        "project_id": project_id,
        "source": "served_model_prediction",
        "model_version": curve_model_version if curve_model_version != "unknown" else point_model_version,
        "inputs": inputs,
        "predictions_at_selected_point": predictions[0],
        "curve": curve,
        "warnings": [*point_warnings, *curve_warnings],
        "comparison_real_cell": comparison,
        "training_overlay": training_overlay,
    }


def _selected_objectives(schema: dict[str, Any], objective_weights: dict[str, float]) -> list[dict[str, Any]]:
    outputs = {item["name"]: item for item in schema.get("outputs", [])}
    objectives: list[dict[str, Any]] = []
    for name, weight in objective_weights.items():
        if abs(float(weight)) <= 1e-12 or name not in outputs:
            continue
        output = outputs[name]
        objectives.append(
            {
                "name": name,
                "label": output.get("label", name),
                "unit": output.get("unit", ""),
                "schema_direction": output.get("direction", "maximize"),
                "direction": "maximize" if float(weight) > 0 else "minimize",
                "weight": float(weight),
            }
        )
    return objectives


def _objective_matrix(predictions: list[dict[str, float]], objectives: list[dict[str, Any]]) -> np.ndarray:
    matrix = np.asarray([[row[obj["name"]] for obj in objectives] for row in predictions], dtype=np.float64)
    signs = np.asarray([1.0 if obj["direction"] == "maximize" else -1.0 for obj in objectives], dtype=np.float64)
    return matrix * signs


def _non_dominated_mask(matrix: np.ndarray) -> np.ndarray:
    n_rows = matrix.shape[0]
    keep = np.ones(n_rows, dtype=bool)
    for i in range(n_rows):
        if not keep[i]:
            continue
        dominates_i = np.all(matrix >= matrix[i], axis=1) & np.any(matrix > matrix[i], axis=1)
        if np.any(dominates_i):
            keep[i] = False
    return keep


def _normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    minimum = matrix.min(axis=0)
    maximum = matrix.max(axis=0)
    scale = np.where(maximum > minimum, maximum - minimum, 1.0)
    return (matrix - minimum) / scale


def _select_representative_indices(frontier_indices: np.ndarray, transformed_matrix: np.ndarray, max_results: int) -> list[int]:
    if len(frontier_indices) <= max_results:
        return [int(index) for index in frontier_indices]
    frontier_matrix = transformed_matrix[frontier_indices]
    normalized = _normalize_matrix(frontier_matrix)
    selected_local: list[int] = []
    for column in range(normalized.shape[1]):
        selected_local.append(int(np.argmax(normalized[:, column])))
    selected_local.append(int(np.argmax(normalized.mean(axis=1))))
    while len(set(selected_local)) < max_results:
        selected_points = normalized[list(set(selected_local))]
        distances = np.min(np.linalg.norm(normalized[:, None, :] - selected_points[None, :, :], axis=2), axis=1)
        for index in set(selected_local):
            distances[index] = -1
        selected_local.append(int(np.argmax(distances)))
    unique_local = []
    for index in selected_local:
        if index not in unique_local:
            unique_local.append(index)
        if len(unique_local) >= max_results:
            break
    return [int(frontier_indices[index]) for index in unique_local]


def _pareto_label(candidate_prediction: dict[str, float], pareto_predictions: list[dict[str, float]], objectives: list[dict[str, Any]]) -> str:
    for obj in objectives:
        values = [row[obj["name"]] for row in pareto_predictions]
        value = candidate_prediction[obj["name"]]
        if obj["direction"] == "maximize" and np.isclose(value, max(values)):
            return f"High {obj['label']}"
        if obj["direction"] == "minimize" and np.isclose(value, min(values)):
            return f"Low {obj['label']}"
    return "Balanced tradeoff"


def pareto_tradeoff_candidates(project_id: str, payload: dict[str, Any], workspace_id: str | None = None) -> dict[str, Any]:
    schema = _project_schema(project_id, workspace_id)
    raw_weights = payload.get("objective_weights") or _default_objective_weights(schema, project_id)
    objective_weights = {key: float(value) for key, value in raw_weights.items()}
    objectives = _selected_objectives(schema, objective_weights)
    if len(objectives) < 2:
        raise ValueError("Select at least two non-zero objectives for Pareto tradeoff search")
    request = RecommendRequest(
        objective_weights=objective_weights,
        fixed_inputs={key: float(value) for key, value in payload.get("fixed_inputs", {}).items()},
        constraints=payload.get("constraints", {}),
        n_candidates=int(payload.get("n_candidates", 3000)),
        top_k=1,
        random_seed=payload.get("random_seed", 13),
    )
    max_results = max(1, min(int(payload.get("max_results", 12)), 25))
    candidates = _generate_candidates(schema, request)
    predictions, warnings, model_version = predict_rows(project_id, candidates, warn_near_bounds=False, workspace_id=workspace_id)
    transformed = _objective_matrix(predictions, objectives)
    pareto_mask = _non_dominated_mask(transformed)
    frontier_indices = np.flatnonzero(pareto_mask)
    if len(frontier_indices) == 0:
        frontier_indices = np.arange(len(candidates))
    representative_indices = _select_representative_indices(frontier_indices, transformed, max_results)
    pareto_predictions = [predictions[int(index)] for index in frontier_indices]
    normalized_scores = _normalize_matrix(transformed).mean(axis=1)
    response_candidates = []
    for rank, index in enumerate(representative_indices, start=1):
        prediction = predictions[index]
        response_candidates.append(
            {
                "rank": rank,
                "label": _pareto_label(prediction, pareto_predictions, objectives),
                "inputs": candidates[index],
                "predictions": prediction,
                "score": float(normalized_scores[index]),
                "tradeoff_summary": "Pareto candidate: improving one selected objective may worsen another selected objective.",
            }
        )
    return {
        "project_id": project_id,
        "source": "pareto_tradeoff_search",
        "model_version": model_version,
        "objective_weights": objective_weights,
        "objectives": objectives,
        "n_candidates": request.n_candidates,
        "pareto_count": int(len(frontier_indices)),
        "returned_count": int(len(response_candidates)),
        "candidates": response_candidates,
        "warnings": warnings,
    }


def seed_batch_candidate(project_id: str, payload: dict[str, Any], workspace_id: str | None = None) -> dict[str, Any]:
    schema = _project_schema(project_id, workspace_id)
    objective_weights = payload.get("objective_weights") or _default_objective_weights(schema, project_id)
    request = RecommendRequest(
        objective_weights={key: float(value) for key, value in objective_weights.items()},
        fixed_inputs={key: float(value) for key, value in payload.get("fixed_inputs", {}).items()},
        constraints=payload.get("constraints", {}),
        n_candidates=int(payload.get("n_candidates", 2000)),
        top_k=1,
        random_seed=payload.get("random_seed", 13),
    )
    candidates = _generate_candidates(schema, request)
    predictions, warnings, model_version = predict_rows(project_id, candidates, warn_near_bounds=False, workspace_id=workspace_id)
    scores = _score_predictions(schema, predictions, request.objective_weights)
    index = int(np.argsort(-scores)[0])
    design = predict_design(project_id, {"inputs": candidates[index], "comparison_real_cell": payload.get("comparison_real_cell"), "plot_recipe_id": payload.get("plot_recipe_id"), "plot_recipe": payload.get("plot_recipe")}, workspace_id=workspace_id)
    design["seed"] = {
        "source": "batch_search",
        "score": float(scores[index]),
        "objective_weights": request.objective_weights,
        "n_candidates": request.n_candidates,
    }
    design["model_version"] = design.get("model_version") or model_version
    design["warnings"] = [*warnings, *design.get("warnings", [])]
    return design


def _csv_from_records(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "\n"
    return pd.DataFrame(rows).to_csv(index=False)


def export_design_zip(project_id: str, payload: dict[str, Any], workspace_id: str | None = None) -> bytes:
    prediction = predict_design(project_id, payload, workspace_id=workspace_id)
    inputs = prediction["inputs"]
    selected_point = prediction["predictions_at_selected_point"]
    curve_rows = (prediction.get("curve") or {}).get("rows", [])
    real_rows = ((prediction.get("comparison_real_cell") or {}).get("rows") or [])
    comparison_candidate = payload.get("comparison_candidate") or {}
    readme = f"""Mirai DoE Design Studio export\n\nProject: {project_id}\nSource: served-model prediction\nModel version: {prediction.get('model_version', 'unknown')}\n\nFiles:\n- candidate_inputs.csv: selected design variables.\n- predicted_outputs_at_selected_point.csv: model predictions at the selected operating point.\n- predicted_polarization_curve.csv: fuel-cell voltage sweep using observed voltage grid when available.\n- comparison_candidate.csv: saved comparison candidate, if provided.\n- selected_real_cell_curve.csv: measured real-cell comparison curve, if selected.\n- nearest_real_cells.csv: reserved for nearest-neighbor trust evidence.\n\nPredictions are model estimates, not experimental results. Measured real-cell comparison rows are observational data from training artifacts.\n"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("candidate_inputs.csv", _csv_from_records([inputs]))
        archive.writestr("predicted_outputs_at_selected_point.csv", _csv_from_records([{**selected_point, "model_version": prediction.get("model_version", "unknown")}]))
        archive.writestr("predicted_polarization_curve.csv", _csv_from_records(curve_rows))
        archive.writestr("comparison_candidate.csv", _csv_from_records([comparison_candidate] if comparison_candidate else []))
        archive.writestr("selected_real_cell_curve.csv", _csv_from_records(real_rows))
        archive.writestr("nearest_real_cells.csv", _csv_from_records([]))
        archive.writestr("README.txt", readme)
    return buffer.getvalue()
