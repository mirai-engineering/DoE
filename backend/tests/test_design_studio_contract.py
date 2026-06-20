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

    def fake_predict_rows(project_id, rows, warn_near_bounds=True):
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
