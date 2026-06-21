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
