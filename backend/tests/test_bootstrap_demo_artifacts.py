import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_demo_artifacts.py"
spec = importlib.util.spec_from_file_location("bootstrap_demo_artifacts", SCRIPT_PATH)
bootstrap = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = bootstrap
spec.loader.exec_module(bootstrap)


def test_fuel_cell_dry_run_manifest_lists_scoped_objects_without_secrets(monkeypatch):
    monkeypatch.delenv("MIRAI_FRAUNHOFER_S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("MIRAI_FRAUNHOFER_S3_SECRET_ACCESS_KEY", raising=False)

    manifest = bootstrap.build_manifest(bootstrap.PROJECTS["fuel-cell"])

    assert manifest["workspace_id"] == "fraunhofer"
    assert manifest["bucket"] == "mirai-fuel-cells-demo"
    assert manifest["status"] in {"ready", "source_missing"}
    if manifest["objects"]:
        assert all(item["key"].startswith("workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/") for item in manifest["objects"])
        assert any("/training_artifacts/latest/" in item["key"] for item in manifest["objects"])
        assert any("/intake/model_table.csv" in item["key"] for item in manifest["objects"])
        assert not any("backend/data-minio/intake" in item["source"] for item in manifest["objects"])


def test_fuel_cell_manifest_uses_training_and_intake_prefixes(monkeypatch, tmp_path):
    source_root = tmp_path / "data" / "reference" / "pem_fuel_cell_cathode_degradation"
    latest = source_root / "training_artifacts" / "latest"
    latest.mkdir(parents=True)
    for filename in ("model.onnx", "preprocessing.json", "schema.json", "metadata.json", "metrics.json"):
        (latest / filename).write_text("{}", encoding="utf-8")
    for filename in ("model_table.csv", "cell_metadata.csv", "ast_trace_manifest.csv"):
        (source_root / filename).write_text("id,value\n", encoding="utf-8")
    monkeypatch.setenv("MIRAI_FUEL_CELL_ARTIFACT_SOURCE", str(latest))

    manifest = bootstrap.build_manifest(bootstrap.PROJECTS["fuel-cell"])
    keys = {item["key"] for item in manifest["objects"]}

    base = "workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation"
    assert f"{base}/training_artifacts/latest/model.onnx" in keys
    assert f"{base}/training_artifacts/latest/preprocessing.json" in keys
    assert f"{base}/training_artifacts/latest/schema.json" in keys
    assert f"{base}/training_artifacts/latest/metadata.json" in keys
    assert f"{base}/training_artifacts/latest/metrics.json" in keys
    assert f"{base}/intake/model_table.csv" in keys
    assert f"{base}/intake/cell_metadata.csv" in keys
    assert f"{base}/intake/ast_trace_manifest.csv" in keys


def test_battery_manifest_is_deferred_without_dataset_source(monkeypatch):
    monkeypatch.delenv("MIRAI_BATTERY_ARTIFACT_SOURCE", raising=False)

    manifest = bootstrap.build_manifest(bootstrap.PROJECTS["battery"])

    assert manifest["workspace_id"] == "battery-demo"
    assert manifest["bucket"] == "mirai-batteries-demo"
    assert manifest["status"] == "deferred_no_source_configured"
    assert manifest["objects"] == []


def test_script_refuses_to_upload_wholesale_intake(monkeypatch, tmp_path):
    intake = tmp_path / "backend" / "data-minio" / "intake"
    intake.mkdir(parents=True)
    (intake / "raw.csv").write_text("x\n", encoding="utf-8")
    monkeypatch.setenv("MIRAI_FUEL_CELL_ARTIFACT_SOURCE", str(intake))

    with pytest.raises(ValueError, match="Refusing to upload backend/data-minio/intake"):
        bootstrap.build_manifest(bootstrap.PROJECTS["fuel-cell"])
