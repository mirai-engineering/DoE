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

def _default_inputs(schema: dict[str, Any]) -> dict[str, float]:
    return {item["name"]: float((float(item["min"]) + float(item["max"])) / 2.0) for item in schema.get("inputs", [])}


def _project_schema(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    return get_project_schema(project_id, workspace_id) if workspace_id else get_project_schema(project_id)


def _prediction_artifact_path(project_id: str, workspace_id: str | None = None) -> Path:
    return _prediction_path(project_id, workspace_id) if workspace_id else _prediction_path(project_id)


def _default_objective_weights(schema: dict[str, Any], project_id: str) -> dict[str, float]:
    outputs = schema.get("outputs", [])
    for output in outputs:
        if output.get("direction") == "maximize":
            return {output["name"]: 1.0}
    return {outputs[0]["name"]: 1.0} if outputs else {}


def _predictions_artifact(project_id: str, workspace_id: str | None = None) -> pd.DataFrame:
    path = _prediction_artifact_path(project_id, workspace_id)
    if not path.exists():
        raise FileNotFoundError("Design Studio training overlays require predictions.csv. Load a trained champion model first.")
    return pd.read_csv(path)


def _plot_recipes(project_id: str, schema: dict[str, Any], workspace_id: str | None = None) -> list[dict[str, Any]]:
    metadata = schema.get("domain_metadata") if isinstance(schema.get("domain_metadata"), dict) else {}
    ui_config = metadata.get("ui_config") if isinstance(metadata.get("ui_config"), dict) else {}
    configured = ui_config.get("plot_recipes") if isinstance(ui_config.get("plot_recipes"), list) else []
    recipes = [dict(recipe, enabled=recipe.get("enabled", True)) for recipe in configured if isinstance(recipe, dict)]
    if any(recipe.get("kind") == "scatter_response" for recipe in recipes):
        return recipes
    inputs = schema.get("inputs", []) or []
    outputs = schema.get("outputs", []) or []
    first_input = next((item for item in inputs if item.get("name")), None)
    first_output = next((item for item in outputs if item.get("name")), None)
    if not first_input or not first_output:
        return recipes
    recipes.append(
        {
            "id": f"experiment_visualisation_{first_input['name']}_{first_output['name']}",
            "label": "Generic experiment visualisation",
            "description": "Sweep one input, hold the remaining inputs fixed, and predict the selected response.",
            "kind": "scatter_response",
            "template_id": "generic_tabular_doe",
            "safe": True,
            "recommended": True,
            "x": {"source": "input", "variable": first_input["name"]},
            "y": {"source": "prediction", "variable": first_output["name"]},
            "series": [],
            "group_by": None,
            "filters": [],
            "enabled": True,
        }
    )
    return recipes


def _schema_variable_lookup(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for role in ("inputs", "outputs"):
        for item in schema.get(role, []) or []:
            if isinstance(item, dict) and item.get("name"):
                lookup[str(item["name"])] = {**item, "role": "input" if role == "inputs" else "output"}
    for container_name in ("metadata", "domain_metadata"):
        container = schema.get(container_name) if isinstance(schema.get(container_name), dict) else {}
        for key in ("all_variables", "variables"):
            values = container.get(key) if isinstance(container.get(key), list) else []
            for item in values:
                if isinstance(item, dict) and item.get("name"):
                    lookup.setdefault(str(item["name"]), item)
    return lookup


def _jsonable_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _is_numeric_series(series: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(series):
        return False
    return pd.api.types.is_numeric_dtype(series) or pd.to_numeric(series.dropna(), errors="coerce").notna().all()


def training_overlay_options(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    schema = _project_schema(project_id, workspace_id)
    lookup = _schema_variable_lookup(schema)
    try:
        frame = _predictions_artifact(project_id, workspace_id)
    except (FileNotFoundError, ValueError):
        return {"source": "predictions.csv", "available": False, "columns": [], "row_count": 0}
    output_names = {str(item.get("name")) for item in schema.get("outputs", []) if item.get("name")}
    excluded_suffixes = ("_true", "_pred", "_error", "_residual")
    excluded_names = {"model_name", "candidate", "project_id"}
    columns: list[dict[str, Any]] = []
    for column in frame.columns:
        if column in excluded_names or any(str(column).endswith(suffix) for suffix in excluded_suffixes) or column in output_names:
            continue
        series = frame[column].dropna()
        if series.empty:
            continue
        meta = lookup.get(str(column), {})
        is_numeric = _is_numeric_series(series)
        numeric = pd.to_numeric(series, errors="coerce") if is_numeric else None
        distinct_values = sorted(series.drop_duplicates().tolist(), key=lambda value: str(value))
        distinct_count = int(len(distinct_values))
        low_cardinality = distinct_count <= 50
        item: dict[str, Any] = {
            "name": str(column),
            "label": meta.get("label") or meta.get("ui_label") or str(column),
            "role": meta.get("role") or ("input" if column in {i.get("name") for i in schema.get("inputs", [])} else "metadata"),
            "dtype": meta.get("dtype") or ("number" if is_numeric else "string"),
            "unit": meta.get("unit") or "",
            "distinct_count": distinct_count,
            "filter_kind": "exact" if (not is_numeric or low_cardinality) else "range",
            "searchable": True,
            "recommended": (meta.get("role") in {"input", "metadata", "context", "group"}) or str(column) in {"split", "cell_id"},
        }
        if is_numeric and numeric is not None:
            item["min"] = float(numeric.min())
            item["max"] = float(numeric.max())
        if (not is_numeric) or low_cardinality:
            item["values"] = [_jsonable_value(value) for value in distinct_values[:500]]
        columns.append(item)
    return {"source": "predictions.csv", "available": True, "columns": columns, "row_count": int(len(frame))}


def _apply_overlay_filters(frame: pd.DataFrame, filters: dict[str, Any] | None, ranges: dict[str, Any] | None) -> pd.DataFrame:
    subset = frame
    for column, raw in (filters or {}).items():
        if column not in subset.columns or raw in (None, "", []):
            continue
        values = raw if isinstance(raw, list) else [raw]
        series = subset[column]
        if _is_numeric_series(series):
            numeric = pd.to_numeric(series, errors="coerce")
            wanted = []
            for value in values:
                if value in (None, ""):
                    continue
                try:
                    wanted.append(float(value))
                except (TypeError, ValueError):
                    continue
            if wanted:
                mask = np.zeros(len(subset), dtype=bool)
                for value in wanted:
                    mask |= np.isclose(numeric.astype(float), value, equal_nan=False)
                subset = subset[mask]
        else:
            wanted = {str(value) for value in values if value not in (None, "")}
            if wanted:
                subset = subset[subset[column].astype(str).isin(wanted)]
    for column, bounds in (ranges or {}).items():
        if column not in subset.columns or not isinstance(bounds, dict):
            continue
        numeric = pd.to_numeric(subset[column], errors="coerce")
        if bounds.get("min") not in (None, ""):
            try:
                subset = subset[numeric >= float(bounds["min"])]
                numeric = pd.to_numeric(subset[column], errors="coerce")
            except (TypeError, ValueError):
                pass
        if bounds.get("max") not in (None, ""):
            try:
                subset = subset[numeric <= float(bounds["max"])]
            except (TypeError, ValueError):
                pass
    return subset


def _training_overlay(project_id: str, x_variable: str | None, output_variables: list[str] | None, group_by: str | None = None, filters: dict[str, Any] | None = None, ranges: dict[str, Any] | None = None, enabled: bool = True, workspace_id: str | None = None) -> dict[str, Any] | None:
    if not enabled or not x_variable or not output_variables:
        return None
    try:
        frame = _predictions_artifact(project_id, workspace_id)
    except (FileNotFoundError, ValueError):
        return None
    true_columns = [f"{name}_true" for name in output_variables if f"{name}_true" in frame.columns]
    if x_variable not in frame.columns or not true_columns:
        return None
    filtered = _apply_overlay_filters(frame, filters, ranges)
    source_row_count = int(len(frame))
    filtered_row_count = int(len(filtered))
    columns = [x_variable, *true_columns]
    if group_by and group_by in filtered.columns:
        columns.append(group_by)
    filter_columns = [name for name in [*(filters or {}).keys(), *(ranges or {}).keys()] if name in filtered.columns and name not in columns]
    columns.extend(filter_columns)
    if "split" in filtered.columns and "split" not in columns:
        columns.append("split")
    if filtered.empty:
        return {"source": "predictions.csv", "x_variable": x_variable, "output_variables": output_variables, "group_by": group_by, "source_row_count": source_row_count, "filtered_row_count": 0, "rows": []}
    subset = filtered[columns].dropna(subset=[x_variable, *true_columns]).drop_duplicates().sort_values(x_variable)
    if len(subset) > 1200:
        subset = subset.iloc[np.linspace(0, len(subset) - 1, 1200).round().astype(int)]
    rows = []
    for _, row in subset.iterrows():
        item: dict[str, Any] = {str(x_variable): float(row[x_variable])}
        for column in true_columns:
            item[column] = float(row[column])
        for column in columns:
            if column in item or column in true_columns or column == x_variable:
                continue
            item[column] = _jsonable_value(row[column])
        rows.append(item)
    return {"source": "predictions.csv", "x_variable": x_variable, "output_variables": output_variables, "group_by": group_by, "source_row_count": source_row_count, "filtered_row_count": filtered_row_count, "rows": rows}


def _experiment_visualisation_rows(project_id: str, inputs: dict[str, float], visualisation_config_id: str | None = None, visualisation_config: dict[str, Any] | None = None, workspace_id: str | None = None) -> tuple[dict[str, Any] | None, list[str], str]:
    schema = _project_schema(project_id, workspace_id)
    response_config_kinds = {"scatter_response", "experiment_visualisation"}
    configured_visualisations = [item for item in _plot_recipes(project_id, schema, workspace_id) if item.get("enabled", True) and item.get("kind") in response_config_kinds]
    preset = dict(visualisation_config) if isinstance(visualisation_config, dict) else None
    if preset is not None and preset.get("kind") not in response_config_kinds:
        preset = None
    if preset is None:
        preset = next((item for item in configured_visualisations if item.get("id") == visualisation_config_id), None) if visualisation_config_id else None
    preset = preset or next((item for item in configured_visualisations if item.get("recommended")), None)
    if not preset or not preset.get("enabled", True):
        return None, [], "unknown"

    x_variable = (preset.get("x") or {}).get("variable") or preset.get("sweep_variable")
    y_variable = (preset.get("y") or {}).get("variable") or preset.get("response_variable")
    series_variables = [item.get("variable") for item in preset.get("series", []) if isinstance(item, dict) and item.get("variable")]
    y_variables: list[str] = []
    for variable in [y_variable, *series_variables]:
        if variable and str(variable) not in y_variables:
            y_variables.append(str(variable))
    input_schema = next((item for item in schema.get("inputs", []) if item.get("name") == x_variable), None)
    output_names = {item.get("name") for item in schema.get("outputs", [])}
    invalid_outputs = [name for name in y_variables if name not in output_names]
    if not x_variable or not y_variables or not input_schema or invalid_outputs:
        return None, ["Selected experiment visualisation is missing a valid sweep variable or predicted response."], "unknown"

    points = int(preset.get("points") or 60)
    points = max(10, min(points, 200))
    schema_min = float(input_schema.get("min", 0))
    schema_max = float(input_schema.get("max", 1))
    min_value = float(preset.get("x_min") if preset.get("x_min") is not None else schema_min)
    max_value = float(preset.get("x_max") if preset.get("x_max") is not None else schema_max)
    if min_value > max_value:
        min_value, max_value = max_value, min_value
    if min_value < schema_min or max_value > schema_max:
        return None, [f"Sweep range for '{x_variable}' must stay within allowed bounds [{schema_min:g}, {schema_max:g}]."], "unknown"
    grid = np.linspace(min_value, max_value, points)

    input_names = {item.get("name") for item in schema.get("inputs", [])}
    input_schema_by_name = {item.get("name"): item for item in schema.get("inputs", []) if item.get("name")}
    group_variable = preset.get("group_variable") or preset.get("group_by")
    group_values_raw = preset.get("group_values") if isinstance(preset.get("group_values"), list) else []
    group_values: list[float | None] = []
    if group_variable in input_names and group_variable != x_variable:
        group_schema = input_schema_by_name.get(group_variable, {})
        group_min = float(group_schema.get("min", -np.inf))
        group_max = float(group_schema.get("max", np.inf))
        for raw in group_values_raw:
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value < group_min or value > group_max:
                return None, [f"Group value for '{group_variable}' must stay within allowed bounds [{group_min:g}, {group_max:g}]."], "unknown"
            if value not in group_values:
                group_values.append(value)
    if not group_values:
        group_variable = None
        group_values = [None]

    sweep_rows: list[dict[str, float]] = []
    row_groups: list[float | None] = []
    for group_value in group_values:
        for value in grid:
            row = {**inputs, str(x_variable): float(value)}
            if group_variable and group_value is not None:
                row[str(group_variable)] = float(group_value)
            sweep_rows.append(row)
            row_groups.append(group_value)
    predictions, warnings, model_version = predict_rows(project_id, sweep_rows, warn_near_bounds=False, workspace_id=workspace_id)
    rows = []
    for row, pred, group_value in zip(sweep_rows, predictions, row_groups, strict=True):
        next_row: dict[str, Any] = {str(x_variable): float(row[str(x_variable)])}
        if group_variable and group_value is not None:
            next_row["__group_variable"] = str(group_variable)
            next_row["__group_value"] = float(group_value)
            next_row[str(group_variable)] = float(group_value)
        for variable in y_variables:
            next_row[variable] = float(pred[variable])
        rows.append(next_row)
    resolved_config = {**preset, "kind": "scatter_response", "y_variables": y_variables, "points": points, "group_variable": group_variable, "group_values": [value for value in group_values if value is not None]}
    return {"preset": preset.get("id", "experiment_visualisation"), "recipe": resolved_config, "rows": rows}, warnings, model_version


def _curve_rows(project_id: str, inputs: dict[str, float], plot_recipe_id: str | None = None, plot_recipe: dict[str, Any] | None = None, workspace_id: str | None = None) -> tuple[dict[str, Any] | None, list[str], str]:
    """Compatibility wrapper for older tests/callers using curve/plot_recipe names."""
    return _experiment_visualisation_rows(project_id, inputs, plot_recipe_id, plot_recipe, workspace_id)


def get_design_studio_state(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    schema = _project_schema(project_id, workspace_id)
    recipes = _plot_recipes(project_id, schema, workspace_id)
    response_recipe_kinds = {"scatter_response", "experiment_visualisation"}
    design_recipes = [recipe for recipe in recipes if recipe.get("enabled", True) and recipe.get("kind") in response_recipe_kinds]
    ui_config = schema.get("domain_metadata", {}).get("ui_config", {}) if isinstance(schema.get("domain_metadata"), dict) else {}
    design_config = ui_config.get("design_studio", {}) if isinstance(ui_config.get("design_studio"), dict) else {}
    configured_recipe_id = design_config.get("primary_plot_recipe_id") or ui_config.get("selected_plot_recipe_id")
    selected_recipe_id = next((recipe.get("id") for recipe in design_recipes if recipe.get("id") == configured_recipe_id), None)
    selected_recipe_id = selected_recipe_id or next((recipe.get("id") for recipe in design_recipes if recipe.get("recommended")), None)
    selected_recipe_id = selected_recipe_id or (design_recipes[0].get("id") if design_recipes else "")
    return {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "active_model": get_active_model_metadata(project_id, workspace_id),
        "inputs": schema.get("inputs", []),
        "outputs": schema.get("outputs", []),
        "default_inputs": _default_inputs(schema),
        "default_objective_weights": _default_objective_weights(schema, project_id),
        "plot_recipes": design_recipes,
        "selected_plot_recipe_id": selected_recipe_id,
        "presets": {},
        "real_cell_options": [],
        "training_overlay_options": training_overlay_options(project_id, workspace_id),
    }


def predict_design(project_id: str, payload: dict[str, Any], workspace_id: str | None = None) -> dict[str, Any]:
    inputs = {key: float(value) for key, value in payload.get("inputs", {}).items()}
    predictions, point_warnings, point_model_version = predict_rows(project_id, [inputs], warn_near_bounds=True, workspace_id=workspace_id)
    generate_visualisation = bool(payload.get("experiment_visualisation_enabled", True))
    curve, curve_warnings, curve_model_version = (None, [], "unknown")
    if generate_visualisation:
        visualisation_config = payload.get("experiment_visualisation") if isinstance(payload.get("experiment_visualisation"), dict) else payload.get("plot_recipe")
        curve, curve_warnings, curve_model_version = _experiment_visualisation_rows(project_id, inputs, payload.get("plot_recipe_id"), visualisation_config, workspace_id=workspace_id)
    curve_recipe = curve.get("recipe", {}) if isinstance(curve, dict) else {}
    comparison_x = ((curve_recipe.get("x") or {}).get("variable") if isinstance(curve_recipe, dict) else None)
    comparison_outputs = curve_recipe.get("y_variables") if isinstance(curve_recipe, dict) else None
    if not comparison_outputs and isinstance(curve_recipe, dict):
        y_variable = (curve_recipe.get("y") or {}).get("variable")
        series_variables = [item.get("variable") for item in curve_recipe.get("series", []) if isinstance(item, dict) and item.get("variable")]
        comparison_outputs = [item for item in [y_variable, *series_variables] if item]
    comparison_output_names = [str(item) for item in comparison_outputs] if comparison_outputs else None
    training_overlay = _training_overlay(
        project_id,
        str(comparison_x) if comparison_x else None,
        comparison_output_names,
        group_by=str(payload.get("training_overlay_group_by") or "") or None,
        filters=payload.get("training_overlay_filters") if isinstance(payload.get("training_overlay_filters"), dict) else None,
        ranges=payload.get("training_overlay_ranges") if isinstance(payload.get("training_overlay_ranges"), dict) else None,
        enabled=generate_visualisation and bool(payload.get("training_overlay_enabled", True)),
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
        "comparison_real_cell": None,
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
    design = predict_design(project_id, {"inputs": candidates[index], "plot_recipe_id": payload.get("plot_recipe_id"), "experiment_visualisation": payload.get("experiment_visualisation") or payload.get("plot_recipe"), "training_overlay_enabled": payload.get("training_overlay_enabled", True), "training_overlay_filters": payload.get("training_overlay_filters"), "training_overlay_ranges": payload.get("training_overlay_ranges"), "training_overlay_group_by": payload.get("training_overlay_group_by")}, workspace_id=workspace_id)
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
    overlay_rows = ((prediction.get("training_overlay") or {}).get("rows") or [])
    comparison_candidate = payload.get("comparison_candidate") or {}
    readme = f"""Mirai DoE Design Studio export\n\nProject: {project_id}\nSource: served-model prediction\nModel version: {prediction.get('model_version', 'unknown')}\n\nFiles:\n- candidate_inputs.csv: selected design variables.\n- predicted_outputs_at_selected_point.csv: model predictions at the selected operating point.\n- predicted_response_curve.csv: selected generic response sweep.\n- comparison_candidate.csv: saved comparison candidate, if provided.\n- training_overlay_rows.csv: filtered measured/training overlay rows from predictions.csv, if available.\n- nearest_real_cells.csv: reserved for nearest-neighbor trust evidence.\n\nPredictions are model estimates, not experimental results. Training overlay rows are observational data from training artifacts.\n"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("candidate_inputs.csv", _csv_from_records([inputs]))
        archive.writestr("predicted_outputs_at_selected_point.csv", _csv_from_records([{**selected_point, "model_version": prediction.get("model_version", "unknown")}]))
        archive.writestr("predicted_response_curve.csv", _csv_from_records(curve_rows))
        archive.writestr("comparison_candidate.csv", _csv_from_records([comparison_candidate] if comparison_candidate else []))
        archive.writestr("training_overlay_rows.csv", _csv_from_records(overlay_rows))
        archive.writestr("nearest_real_cells.csv", _csv_from_records([]))
        archive.writestr("README.txt", readme)
    return buffer.getvalue()
