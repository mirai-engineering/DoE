from pathlib import Path

import numpy as np
import pytest

from app.services import mlflow_registry, prediction, project_registry
from app.services.model_loader import ProjectModel
from app.services.preprocessing import transform_inputs


def test_transform_inputs_v1_composes_chained_actions_once_per_feature():
    preprocessing = {
        "preprocessing_contract_version": "mirai-ml-preprocessing-v1",
        "input_order": ["x1", "x2"],
        "feature_columns": ["x1", "x2"],
        "output_order": ["y1"],
        "fitted_parameters": [
            {"variable_id": "x1", "tool": "log1p_feature", "method": "log1p", "parameters": {}, "output_columns": ["x1"]},
            {"variable_id": "x1", "tool": "minmax_scaler", "method": "minmax", "parameters": {"min": 0.0, "scale": 2.0}, "output_columns": ["x1"]},
            {"variable_id": "x2", "tool": "passthrough", "method": "none", "parameters": {}, "output_columns": ["x2"]},
        ],
    }

    transformed = transform_inputs(np.asarray([[np.e**2 - 1.0, 7.0]], dtype=np.float32), preprocessing)

    assert transformed.shape == (1, 2)
    assert transformed[0, 0] == pytest.approx(1.0)
    assert transformed[0, 1] == pytest.approx(7.0)


def test_download_run_artifacts_accepts_v1_fitted_without_optional_maps(monkeypatch, tmp_path: Path):
    class Artifact:
        def __init__(self, path: str):
            self.path = path

    available = [
        "schema.json",
        "preprocessing.json",
        "preprocessing_fitted.json",
        "training_manifest.json",
        "model_table_preprocessed_manifest.json",
    ]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_artifacts(self, run_id):
            return [Artifact(path) for path in available]

    class FakeArtifacts:
        @staticmethod
        def download_artifacts(*, run_id, artifact_path, dst_path):
            Path(dst_path, artifact_path).write_text("{}", encoding="utf-8")
            return str(Path(dst_path, artifact_path))

    class FakeMlflow:
        artifacts = FakeArtifacts()

    monkeypatch.setattr(mlflow_registry, "MODEL_CACHE_ROOT", tmp_path)
    monkeypatch.setattr(mlflow_registry, "configure_mlflow", lambda: FakeMlflow())
    monkeypatch.setattr("mlflow.tracking.MlflowClient", FakeClient)

    artifact_dir = mlflow_registry.download_run_artifacts("p", "run123")

    assert (artifact_dir / "preprocessing_fitted.json").exists()
    assert not (artifact_dir / "feature_map.json").exists()
    assert not (artifact_dir / "target_map.json").exists()


def test_get_project_preprocessing_fails_for_v1_model_table_without_fitted(monkeypatch, tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "preprocessing.json").write_text('{"version":"mirai-ml-preprocessing-v1"}', encoding="utf-8")
    (artifact_dir / "model_table_preprocessed_manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(project_registry, "_latest_project_artifact_dir", lambda project_id, workspace_id=None: artifact_dir)
    project_registry.get_project_preprocessing.cache_clear()

    with pytest.raises(FileNotFoundError, match="preprocessing_fitted.json"):
        project_registry.get_project_preprocessing("p", "w")

    project_registry.get_project_preprocessing.cache_clear()


def test_predict_rows_transforms_schema_raw_inputs_for_ml_preprocessing_v1_when_forced(monkeypatch):
    schema = {
        "inputs": [
            {"name": "x1", "min": 0.0, "max": 10.0},
            {"name": "x2", "min": 0.0, "max": 10.0},
        ],
        "outputs": [{"name": "y1"}],
    }
    preprocessing = {
        "preprocessing_contract_version": "mirai-ml-preprocessing-v1",
        "input_order": ["x1", "x2"],
        "feature_columns": ["x1", "x2"],
        "output_order": ["y1"],
        "fitted_parameters": [
            {"variable_id": "x1", "tool": "minmax_scaler", "method": "minmax", "parameters": {"min": 0.0, "scale": 10.0}, "output_columns": ["x1"]},
            {"variable_id": "x2", "tool": "standard_scaler", "method": "standard", "parameters": {"mean": 5.0, "std": 5.0}, "output_columns": ["x2"]},
            {"variable_id": "y1", "tool": "target_transform", "method": "none", "parameters": {}, "output_columns": ["y1"]},
        ],
    }
    model = ProjectModel(
        project_id="p",
        session=None,
        input_name="raw_features",
        output_name="raw_outputs",
        schema=schema,
        metadata={"model_version": "test-v1"},
        preprocessing=preprocessing,
        model_kind="onnx_raw",
    )
    captured = {}
    monkeypatch.setattr(prediction, "get_model_bundle", lambda project_id, workspace_id=None: model)

    def fake_predict(project_id, input_matrix, workspace_id=None):
        captured["features"] = np.asarray(input_matrix, dtype=np.float32)
        return np.asarray([[42.0]], dtype=np.float32)

    monkeypatch.setattr(prediction, "predict", fake_predict)

    result, warnings, model_version = prediction.predict_rows("p", [{"x1": 5.0, "x2": 10.0}], warn_near_bounds=False, workspace_id="w", force_ml_preprocessing_v1=True)

    assert warnings == []
    assert model_version == "test-v1"
    assert result == [{"y1": 42.0}]
    assert captured["features"].shape == (1, 2)
    assert captured["features"][0, 0] == pytest.approx(0.5)
    assert captured["features"][0, 1] == pytest.approx(1.0)


def test_predict_rows_preserves_onnx_raw_without_transform_by_default(monkeypatch):
    schema = {"inputs": [{"name": "x1", "min": 0.0, "max": 10.0}], "outputs": [{"name": "y1"}]}
    model = ProjectModel(
        project_id="legacy",
        session=None,
        input_name="raw_features",
        output_name="raw_outputs",
        schema=schema,
        metadata={"model_version": "legacy-v1"},
        preprocessing={"input_scaler": {"method": "minmax", "min": [0], "max": [10]}, "output_scaler": {"method": "minmax", "min": [0], "max": [1]}},
        model_kind="onnx_raw",
    )
    captured = {}
    monkeypatch.setattr(prediction, "get_model_bundle", lambda project_id, workspace_id=None: model)
    monkeypatch.setattr(prediction, "transform_inputs", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy raw should not transform")))

    def fake_predict(project_id, input_matrix, workspace_id=None):
        captured["features"] = np.asarray(input_matrix, dtype=np.float32)
        return np.asarray([[3.0]], dtype=np.float32)

    monkeypatch.setattr(prediction, "predict", fake_predict)

    result, warnings, model_version = prediction.predict_rows("legacy", [{"x1": 5.0}], workspace_id=None)

    assert warnings == []
    assert model_version == "legacy-v1"
    assert result == [{"y1": 3.0}]
    assert captured["features"][0, 0] == pytest.approx(5.0)
