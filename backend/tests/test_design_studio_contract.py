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


def test_fuel_cell_recipe_is_adapted_to_generic_scatter_response(monkeypatch):
    schema = {
        "inputs": [{"name": "voltage", "min": 0.6, "max": 0.9}],
        "outputs": [{"name": "current", "direction": "maximize"}],
        "domain_metadata": {"ui_config": {"plot_recipes": [{"id": "legacy", "kind": "fuel_cell_polarization", "enabled": True, "x": {"variables": ["current"]}, "y": {"variable": "voltage"}}]}},
    }
    monkeypatch.setattr(design_studio, "get_project_schema", lambda project_id: schema)
    monkeypatch.setattr(design_studio, "_plot_recipes", lambda project_id, schema, workspace_id=None: schema["domain_metadata"]["ui_config"]["plot_recipes"])

    def fake_predict_rows(project_id, rows, warn_near_bounds=True, workspace_id=None):
        return [{"current": row["voltage"] * 10} for row in rows], [], "model_v1"

    monkeypatch.setattr(design_studio, "predict_rows", fake_predict_rows)

    curve, warnings, model_version = design_studio._curve_rows("p", {"voltage": 0.7}, plot_recipe_id="legacy")

    assert warnings == []
    assert model_version == "model_v1"
    assert curve["recipe"]["kind"] == "scatter_response"
    assert curve["recipe"]["x"]["variable"] == "voltage"
    assert curve["recipe"]["y"]["variable"] == "current"
    assert set(curve["rows"][0]) == {"voltage", "current"}
