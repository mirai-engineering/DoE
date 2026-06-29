from pathlib import Path

import pandas as pd

from app.services import design_studio


def test_design_curve_rows_ignores_non_response_recommended_recipes(monkeypatch):
    schema = {
        "project_id": "generic_project",
        "inputs": [{"name": "x1", "type": "continuous", "min": 0, "max": 1, "unit": ""}],
        "outputs": [{"name": "y1", "direction": "maximize", "unit": ""}],
        "domain_metadata": {
            "ui_config": {
                "plot_recipes": [
                    {"id": "parity_y1", "kind": "parity", "recommended": True, "enabled": True, "x": {"variable": "y1_true"}, "y": {"variable": "y1_pred"}},
                    {"id": "response_x1_y1", "kind": "scatter_response", "recommended": True, "enabled": True, "x": {"variable": "x1"}, "y": {"variable": "y1"}, "series": []},
                ]
            }
        },
    }
    monkeypatch.setattr(design_studio, "get_project_schema", lambda project_id: schema)

    def fake_predict_rows(project_id, rows, warn_near_bounds=True, workspace_id=None):
        return [{"y1": row["x1"] * 2} for row in rows], [], "model_v1"

    monkeypatch.setattr(design_studio, "predict_rows", fake_predict_rows)

    curve, warnings, model_version = design_studio._curve_rows("generic_project", {"x1": 0.5})

    assert warnings == []
    assert model_version == "model_v1"
    assert curve["preset"] == "response_x1_y1"
    assert len(curve["rows"]) == 60
    assert set(curve["rows"][0]) == {"x1", "y1"}


def test_predict_design_can_skip_experiment_visualisation(monkeypatch):
    schema = {
        "inputs": [{"name": "x1", "type": "continuous", "min": 0, "max": 1, "unit": ""}],
        "outputs": [{"name": "y1", "direction": "maximize", "unit": ""}],
        "domain_metadata": {"ui_config": {"plot_recipes": [{"id": "response_x1_y1", "kind": "scatter_response", "recommended": True, "enabled": True, "x": {"variable": "x1"}, "y": {"variable": "y1"}}]}},
    }
    monkeypatch.setattr(design_studio, "get_project_schema", lambda project_id: schema)

    def fake_predict_rows(project_id, rows, warn_near_bounds=True, workspace_id=None):
        return [{"y1": row["x1"] * 2} for row in rows], [], "model_v1"

    monkeypatch.setattr(design_studio, "predict_rows", fake_predict_rows)

    result = design_studio.predict_design("generic_project", {"inputs": {"x1": 0.25}, "experiment_visualisation_enabled": False})

    assert result["predictions_at_selected_point"] == {"y1": 0.5}
    assert result["curve"] is None
    assert result["training_overlay"] is None


def test_design_predictions_artifact_uses_lazy_prediction_path(monkeypatch, tmp_path: Path):
    prediction_path = tmp_path / "predictions.csv"
    pd.DataFrame([{"project_id": "p", "model_name": "m", "y1_true": 1.0, "y1_pred": 1.1}]).to_csv(prediction_path, index=False)
    monkeypatch.setattr(design_studio, "_prediction_path", lambda project_id: prediction_path)

    frame = design_studio._predictions_artifact("p")

    assert list(frame.columns) == ["project_id", "model_name", "y1_true", "y1_pred"]
    assert len(frame) == 1


def test_recommendations_fail_without_loaded_champion_and_pass_with_workspace(monkeypatch):
    from app.services import recommendation
    from app.schemas import RecommendRequest

    schema = {
        "inputs": [{"name": "x1", "min": 0, "max": 1}],
        "outputs": [{"name": "y1", "direction": "maximize"}],
    }
    monkeypatch.setattr(recommendation, "get_project_schema", lambda project_id, workspace_id=None: schema)

    def fake_predict_rows(project_id, rows, *, warn_near_bounds=True, workspace_id=None):
        if workspace_id is None:
            raise FileNotFoundError("load champion model before serving")
        return [{"y1": row["x1"]} for row in rows], [], "champion-v1"

    monkeypatch.setattr(recommendation, "predict_rows", fake_predict_rows)
    request = RecommendRequest(objective_weights={"y1": 1.0}, n_candidates=16, top_k=3, random_seed=1)

    import pytest
    with pytest.raises(FileNotFoundError, match="load champion"):
        recommendation.recommend_experiments("demo_project", request)

    result = recommendation.recommend_experiments("demo_project", request, workspace_id="fraunhofer")
    assert result.model_version == "champion-v1"
    assert len(result.recommendations) == 3


def test_training_overlay_options_and_filters_are_generic(monkeypatch, tmp_path: Path):
    schema = {
        "inputs": [
            {"name": "x1", "label": "Sweep X", "min": 0, "max": 1, "unit": "V"},
            {"name": "rh", "label": "Relative humidity", "min": 40, "max": 100, "unit": "%"},
        ],
        "outputs": [{"name": "y1", "label": "Output", "direction": "maximize"}],
        "metadata": {"all_variables": [{"name": "cell_id", "label": "Cell", "role": "metadata", "dtype": "string"}]},
    }
    prediction_path = tmp_path / "predictions.csv"
    pd.DataFrame([
        {"x1": 0.1, "rh": 70, "cell_id": "Cell_01", "split": "train", "y1_true": 1.0, "y1_pred": 0.9},
        {"x1": 0.2, "rh": 70, "cell_id": "Cell_02", "split": "test", "y1_true": 2.0, "y1_pred": 1.9},
        {"x1": 0.3, "rh": 90, "cell_id": "Cell_01", "split": "test", "y1_true": 3.0, "y1_pred": 2.9},
    ]).to_csv(prediction_path, index=False)
    monkeypatch.setattr(design_studio, "_project_schema", lambda project_id, workspace_id=None: schema)
    monkeypatch.setattr(design_studio, "_prediction_artifact_path", lambda project_id, workspace_id=None: prediction_path)

    options = design_studio.training_overlay_options("p")
    by_name = {item["name"]: item for item in options["columns"]}
    assert by_name["rh"]["filter_kind"] == "exact"
    assert by_name["cell_id"]["label"] == "Cell"

    overlay = design_studio._training_overlay(
        "p",
        "x1",
        ["y1"],
        group_by="split",
        filters={"rh": 70, "cell_id": "Cell_02"},
        ranges=None,
    )
    assert overlay["source_row_count"] == 3
    assert overlay["filtered_row_count"] == 1
    assert overlay["rows"] == [{"x1": 0.2, "y1_true": 2.0, "split": "test", "rh": 70, "cell_id": "Cell_02"}]


def test_training_overlay_range_filter_empty_state(monkeypatch, tmp_path: Path):
    schema = {"inputs": [{"name": "x1", "min": 0, "max": 1}], "outputs": [{"name": "y1"}]}
    prediction_path = tmp_path / "predictions.csv"
    pd.DataFrame([{"x1": 0.1, "temperature": 25.0, "y1_true": 1.0}, {"x1": 0.9, "temperature": 80.0, "y1_true": 2.0}]).to_csv(prediction_path, index=False)
    monkeypatch.setattr(design_studio, "_project_schema", lambda project_id, workspace_id=None: schema)
    monkeypatch.setattr(design_studio, "_prediction_artifact_path", lambda project_id, workspace_id=None: prediction_path)

    overlay = design_studio._training_overlay("p", "x1", ["y1"], ranges={"temperature": {"min": 30, "max": 40}})

    assert overlay["filtered_row_count"] == 0
    assert overlay["rows"] == []


def test_experiment_visualisation_grouped_sweep_is_generic(monkeypatch):
    schema = {
        "inputs": [
            {"name": "x1", "min": 0, "max": 1},
            {"name": "condition", "min": 10, "max": 30},
        ],
        "outputs": [{"name": "y1", "direction": "maximize"}],
        "domain_metadata": {"ui_config": {"plot_recipes": [{"id": "generic", "kind": "scatter_response", "enabled": True, "x": {"variable": "x1"}, "y": {"variable": "y1"}}]}},
    }
    monkeypatch.setattr(design_studio, "get_project_schema", lambda project_id: schema)

    def fake_predict_rows(project_id, rows, warn_near_bounds=True, workspace_id=None):
        return [{"y1": row["x1"] + row["condition"]} for row in rows], [], "model_v1"

    monkeypatch.setattr(design_studio, "predict_rows", fake_predict_rows)
    plot = {
        "id": "dynamic",
        "kind": "scatter_response",
        "x": {"variable": "x1"},
        "y": {"variable": "y1"},
        "group_variable": "condition",
        "group_values": [10, 20],
        "points": 10,
    }

    curve, warnings, model_version = design_studio._curve_rows("p", {"x1": 0.5, "condition": 15}, plot_recipe=plot)

    assert warnings == []
    assert model_version == "model_v1"
    assert curve["recipe"]["group_variable"] == "condition"
    assert curve["recipe"]["group_values"] == [10.0, 20.0]
    assert len(curve["rows"]) == 20
    assert {row["__group_value"] for row in curve["rows"]} == {10.0, 20.0}
    assert set(curve["rows"][0]) == {"x1", "condition", "__group_variable", "__group_value", "y1"}


def test_experiment_visualisation_sweeps_one_input_and_keeps_four_input_conditions(monkeypatch):
    schema = {
        "inputs": [
            {"name": "x1", "min": 0, "max": 1},
            {"name": "a", "min": 10, "max": 20},
            {"name": "b", "min": 100, "max": 200},
            {"name": "c", "min": -1, "max": 1},
        ],
        "outputs": [{"name": "y1", "direction": "maximize"}],
        "domain_metadata": {"ui_config": {"plot_recipes": []}},
    }
    captured_rows = []
    monkeypatch.setattr(design_studio, "get_project_schema", lambda project_id: schema)

    def fake_predict_rows(project_id, rows, warn_near_bounds=True, workspace_id=None):
        captured_rows.extend(rows)
        return [{"y1": row["x1"] + row["a"] + row["b"] + row["c"]} for row in rows], [], "model_v1"

    monkeypatch.setattr(design_studio, "predict_rows", fake_predict_rows)

    config = {
        "id": "experiment_visualisation",
        "kind": "experiment_visualisation",
        "x": {"variable": "x1"},
        "y": {"variable": "y1"},
        "points": 12,
        "x_min": 0.2,
        "x_max": 0.8,
    }
    curve, warnings, model_version = design_studio._experiment_visualisation_rows("p", {"x1": 0.5, "a": 11, "b": 123, "c": -0.25}, visualisation_config=config)

    assert warnings == []
    assert model_version == "model_v1"
    assert len(curve["rows"]) == 12
    assert {row["a"] for row in captured_rows} == {11}
    assert {row["b"] for row in captured_rows} == {123}
    assert {row["c"] for row in captured_rows} == {-0.25}
    assert min(row["x1"] for row in captured_rows) == 0.2
    assert max(row["x1"] for row in captured_rows) == 0.8


def test_experiment_visualisation_invalid_config_returns_schema_safe_warning(monkeypatch):
    schema = {
        "inputs": [{"name": "x1", "min": 0, "max": 1}],
        "outputs": [{"name": "y1", "direction": "maximize"}],
        "domain_metadata": {"ui_config": {"plot_recipes": []}},
    }
    monkeypatch.setattr(design_studio, "get_project_schema", lambda project_id: schema)

    curve, warnings, model_version = design_studio._experiment_visualisation_rows(
        "p",
        {"x1": 0.5},
        visualisation_config={"id": "bad", "kind": "experiment_visualisation", "x": {"variable": "missing_input"}, "y": {"variable": "missing_output"}},
    )

    assert curve is None
    assert model_version == "unknown"
    assert warnings == ["Selected experiment visualisation is missing a valid sweep variable or predicted response."]
