import json

import pandas as pd
import pytest

from app.services import ml_preprocessing as mlp
from app.services.ml_preprocessing import (
    MLPreprocessingLineage,
    MLPreprocessingPlan,
    PreprocessingToolAction,
    ToolName,
    approve_ml_preprocessing_plan,
    execute_ml_preprocessing,
    fit_preprocessing_action,
    inverse_transform_series,
    start_ml_preprocessing,
)


def test_minmax_fit_uses_train_only_extrema():
    train = pd.DataFrame({"x": [0.0, 10.0]})
    action = PreprocessingToolAction(variable_id="x", tool=ToolName.minmax_scaler, method="minmax", reason="bounded", reversibility="reversible")

    fitted = fit_preprocessing_action(action, train)

    assert fitted.parameters["min"] == 0.0
    assert fitted.parameters["max"] == 10.0
    assert fitted.parameters["scale"] == 10.0


def test_standard_and_minmax_inverse_transform_outputs():
    lineage = MLPreprocessingLineage(workspace_id="w", project_id="p", dataset_id="d", ingestion_session_id="s")
    standard = mlp.FittedParameter(variable_id="y", tool=ToolName.target_transform, method="standard", parameters={"mean": 10.0, "std": 2.0}, output_columns=["y"])
    minmax = mlp.FittedParameter(variable_id="y", tool=ToolName.target_transform, method="minmax", parameters={"min": 5.0, "scale": 20.0}, output_columns=["y"])

    assert inverse_transform_series(pd.Series([0.0, 1.0]), standard).tolist() == [10.0, 12.0]
    assert inverse_transform_series(pd.Series([0.0, 1.0]), minmax).tolist() == [5.0, 25.0]
    assert lineage.workspace_id == "w"


def test_plan_rejects_unsafe_method_scope_content():
    with pytest.raises(Exception):
        PreprocessingToolAction(variable_id="x", tool=ToolName.minmax_scaler, method="standard", reason="bad")
    with pytest.raises(Exception):
        PreprocessingToolAction(variable_id="../x", tool=ToolName.passthrough, method="none", reason="bad")


def test_execute_ml_preprocessing_writes_preprocessed_table_without_test_leakage(monkeypatch, tmp_path):
    root = tmp_path / "session"
    workspace = {
        "root": root,
        "canonical": root / "canonical",
        "training_latest": root / "training_artifacts" / "latest",
        "eda": root / "eda",
        "status": root / "status",
    }
    for path in workspace.values():
        path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"cell_id": ["a", "b", "c"], "split": ["train", "train", "test"], "x": [0.0, 10.0, 1000.0], "y": [1.0, 2.0, 3.0]}).to_csv(workspace["canonical"] / "model_table.csv", index=False)
    (workspace["training_latest"] / "schema.json").write_text(json.dumps({"inputs": [{"name": "x", "variable_id": "x", "role": "input", "dtype": "float"}], "outputs": [{"name": "y", "variable_id": "y", "role": "output"}]}), encoding="utf-8")

    statuses = {}
    monkeypatch.setattr(mlp, "ensure_session_workspace", lambda *args, **kwargs: workspace)
    monkeypatch.setattr(mlp, "get_ingestion_session", lambda *args, **kwargs: {"workspace_id": "w"})
    monkeypatch.setattr(mlp, "read_status", lambda *args, **kwargs: statuses.get(args[3], {}))
    def fake_write_status(project_id, dataset_id, session_id, name, payload):
        statuses[name] = {"updated_at": "now", **payload}
        return statuses[name]

    monkeypatch.setattr(mlp, "write_status", fake_write_status)
    monkeypatch.setattr(mlp, "persist_ml_preprocessing_artifacts", lambda *args, **kwargs: {"status": "skipped"})

    start_ml_preprocessing("p", "d", "s")
    approve_ml_preprocessing_plan("p", "d", "s", approver="tester")
    status = execute_ml_preprocessing("p", "d", "s")

    output = pd.read_csv(root / "ml_preprocessing" / "runs" / "current" / "model_table_preprocessed.csv")
    assert status["status"] == "ml_preprocessing_ready_for_training"
    # If test leaked into min/max, 1000 would be 1.0. Train-only min/max makes it 100.0.
    assert output.loc[output["cell_id"] == "c", "x"].iloc[0] == 100.0
    assert (workspace["canonical"] / "model_table.csv").exists()
