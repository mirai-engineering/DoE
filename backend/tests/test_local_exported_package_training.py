from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from ml_lifecycle.training import run_exported_package as runner


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_package(root: Path, *, include_manifest: bool = True, include_schema: bool = True, include_data: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if include_data:
        pd.DataFrame(
            [
                {"split": "train", "x1": 1.0, "x2": 2.0, "y1": 3.0},
                {"split": "train", "x1": 2.0, "x2": 3.0, "y1": 5.0},
                {"split": "validation", "x1": 3.0, "x2": 4.0, "y1": 7.0},
            ]
        ).to_csv(root / "model_table.csv", index=False)
    if include_schema:
        (root / "schema.json").write_text(
            json.dumps(
                {
                    "project_id": "demo_project",
                    "inputs": [{"name": "x1"}, {"name": "x2"}],
                    "outputs": [{"name": "y1"}],
                    "metadata": {"workspace_id": "fraunhofer"},
                }
            ),
            encoding="utf-8",
        )
    if include_manifest:
        checksums = {}
        if include_data:
            checksums["model_table.csv"] = _sha256(root / "model_table.csv")
        if include_schema:
            checksums["schema.json"] = _sha256(root / "schema.json")
        (root / "training_manifest.json").write_text(
            json.dumps(
                {
                    "package_format_version": "1",
                    "workspace_id": "fraunhofer",
                    "project_id": "demo_project",
                    "dataset_id": "dataset_123",
                    "session_id": "ing_123",
                    "training_request_id": "train_req_123",
                    "exported_at": "2026-06-19T20:00:00+00:00",
                    "feature_columns": ["x1", "x2"],
                    "target_columns": ["y1"],
                    "source_checksums": checksums,
                }
            ),
            encoding="utf-8",
        )
    return root


def test_exported_package_parses_and_creates_working_layout_outside_package(tmp_path: Path) -> None:
    package_dir = _write_package(tmp_path / "package")

    package = runner.load_exported_package(package_dir)
    layout = runner.create_working_layout(package, output_root=tmp_path / "runs")

    assert package.project_id == "demo_project"
    assert package.feature_columns == ["x1", "x2"]
    assert package.target_columns == ["y1"]
    assert layout["run_root"].is_relative_to((tmp_path / "runs").resolve())
    assert not layout["run_root"].is_relative_to(package_dir.resolve())
    assert (layout["canonical"] / "model_table.csv").exists()
    preprocessing = json.loads((layout["artifacts"] / "preprocessing.json").read_text(encoding="utf-8"))
    assert preprocessing["input_order"] == ["x1", "x2"]
    assert preprocessing["output_order"] == ["y1"]
    assert preprocessing["source"] == "approved_export_package"
    assert not any(path.name == "preprocessing.json" for path in package_dir.iterdir())


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("training_manifest.json", "Missing required training_manifest.json"),
        ("schema.json", "Missing required schema.json"),
        ("model_table.csv", "Missing required model_table.csv"),
    ],
)
def test_exported_package_missing_required_files_fail_clearly(tmp_path: Path, filename: str, expected: str) -> None:
    package_dir = _write_package(tmp_path / "package")
    (package_dir / filename).unlink()

    with pytest.raises(runner.ExportedPackageError, match=expected):
        runner.load_exported_package(package_dir)


def test_exported_package_invalid_columns_and_checksum_fail_clearly(tmp_path: Path) -> None:
    package_dir = _write_package(tmp_path / "package")
    frame = pd.read_csv(package_dir / "model_table.csv")
    frame = frame.drop(columns=["x2"])
    frame.to_csv(package_dir / "model_table.csv", index=False)

    with pytest.raises(runner.ExportedPackageError, match="Checksum mismatch for model_table.csv"):
        runner.load_exported_package(package_dir)

    manifest = json.loads((package_dir / "training_manifest.json").read_text(encoding="utf-8"))
    manifest["source_checksums"]["model_table.csv"] = _sha256(package_dir / "model_table.csv")
    (package_dir / "training_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(runner.ExportedPackageError, match="missing required feature/target columns: x2"):
        runner.load_exported_package(package_dir)


def test_remote_mlflow_preflight_refuses_missing_or_local_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.setenv("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW", "true")
    monkeypatch.setenv("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS", "true")
    with pytest.raises(runner.ExportedPackageError, match="MLFLOW_TRACKING_URI is required"):
        runner.preflight_remote_mlflow()

    monkeypatch.setenv("MLFLOW_TRACKING_URI", "file:///tmp/mlruns")
    with pytest.raises(runner.ExportedPackageError, match="must be remote"):
        runner.preflight_remote_mlflow()

    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    with pytest.raises(runner.ExportedPackageError, match="must be remote"):
        runner.preflight_remote_mlflow()


def test_run_training_refuses_before_outputs_or_local_mlruns_without_remote_mlflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package_dir = _write_package(tmp_path / "package")
    output_root = tmp_path / "local-runs"
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW", raising=False)
    monkeypatch.delenv("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS", raising=False)

    with pytest.raises(runner.ExportedPackageError, match="MLFLOW_TRACKING_URI is required"):
        runner.run_training(package_dir, output_root=output_root)

    assert not output_root.exists()
    assert not (tmp_path / "mlruns").exists()


def test_run_training_uses_remote_preflight_and_keeps_outputs_outside_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package_dir = _write_package(tmp_path / "package")
    output_root = tmp_path / "local-runs"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example.test")
    monkeypatch.setenv("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW", "true")
    monkeypatch.setenv("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS", "true")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def search_experiments(self, max_results: int = 1):
            return []

    monkeypatch.setattr("mlflow.tracking.MlflowClient", FakeClient)

    captured: dict[str, Path | dict] = {}

    def fake_train_generic_project(*, project_id: str, data_dir: Path, artifact_dir: Path, training_config: dict):
        captured["data_dir"] = data_dir
        captured["artifact_dir"] = artifact_dir
        captured["training_config"] = training_config
        assert project_id == "demo_project"
        assert (data_dir / "model_table.csv").exists()
        assert (artifact_dir / "schema.json").exists()
        assert (artifact_dir / "training_manifest.json").exists()
        return {"best_model_name": "mean_baseline", "mlflow": {"run_ids": {"mean_baseline": "run_1"}}}

    monkeypatch.setattr(runner, "train_generic_project", fake_train_generic_project)

    result = runner.run_training(package_dir, output_root=output_root, max_epochs=3)

    assert result["status"] == "completed"
    assert Path(result["run_root"]).is_relative_to(output_root.resolve())
    assert not Path(result["run_root"]).is_relative_to(package_dir.resolve())
    config = captured["training_config"]
    assert isinstance(config, dict)
    assert config["mlflow"]["extra_tags"]["training_source"] == "approved_export_package"
    assert config["mlflow"]["extra_tags"]["training_request_id"] == "train_req_123"
    assert config["mlflow"]["extra_artifacts"] == ["training_manifest.json"]
    assert not any(path.name in {"metrics_summary.json", "preprocessing.json"} for path in package_dir.iterdir())
