from fastapi.testclient import TestClient

from app.main import app
from app.services.mlflow_registry import durable_artifact_pointer_for_project, get_registered_model_metadata
from app.services.model_quality import get_artifact_summary


FUEL_PROJECT = "pem_fuel_cell_real_cathode_degradation"
BATTERY_PROJECT = "battery_tabular_doe_demo"


def test_durable_onnx_pointers_are_workspace_project_scoped():
    fuel = durable_artifact_pointer_for_project(FUEL_PROJECT, "onnx_model")
    battery = durable_artifact_pointer_for_project(BATTERY_PROJECT, "onnx_model")

    assert fuel["workspace_id"] == "fraunhofer"
    assert fuel["bucket"] == "mirai-fuel-cells-demo"
    assert fuel["object_key"] == "workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/model.onnx"
    assert fuel["object_uri"].startswith("s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/")

    assert battery["workspace_id"] == "battery-demo"
    assert battery["bucket"] == "mirai-batteries-demo"
    assert battery["object_key"] == "workspaces/battery-demo/projects/battery_tabular_doe_demo/training_artifacts/latest/model.onnx"
    assert battery["object_uri"].startswith("s3://mirai-batteries-demo/workspaces/battery-demo/projects/")

    assert "backend/mlruns" not in fuel["object_uri"]
    assert "backend/mlruns" not in battery["object_uri"]


def test_registered_model_metadata_exposes_durable_pointers_without_requiring_local_image_paths(monkeypatch):
    monkeypatch.setenv("DOE_DISABLE_MLFLOW_MODEL_LOADING", "true")
    metadata = get_registered_model_metadata(FUEL_PROJECT)

    assert metadata["durable_artifact_pointer"]["artifact_kind"] == "mlflow_artifacts"
    assert metadata["durable_onnx_pointer"]["artifact_kind"] == "onnx_model"
    assert metadata["durable_onnx_pointer"]["workspace_id"] == "fraunhofer"
    assert "backend/mlruns" not in metadata["durable_onnx_pointer"]["object_uri"]


def test_model_quality_summary_exposes_durable_pointers_for_packaged_project():
    summary = get_artifact_summary(FUEL_PROJECT)

    pointers = summary["durable_artifact_pointers"]
    assert {"dataset", "preprocessing_output", "mlflow_artifacts", "onnx_model", "bo_state", "review_file"}.issubset(pointers)
    assert pointers["onnx_model"]["workspace_id"] == "fraunhofer"
    assert "backend/mlruns" not in pointers["onnx_model"]["object_uri"]


def test_artifact_status_endpoint_exposes_battery_metadata_without_quality_artifacts():
    with TestClient(app) as client:
        response = client.get(f"/projects/{BATTERY_PROJECT}/artifact-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "battery-demo"
    assert payload["artifact_pointers"]["onnx_model"]["bucket"] == "mirai-batteries-demo"
    assert payload["model_quality"]["available"] is False
    assert "training/bootstrap" in payload["model_quality"]["message"]


def test_artifact_status_endpoint_denies_cross_workspace_access(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")

    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "fraunhofer")
    with TestClient(app) as client:
        battery_response = client.get(
            f"/projects/{BATTERY_PROJECT}/artifact-status",
            headers={"Authorization": "Bearer valid-test-token"},
        )
    assert battery_response.status_code == 403

    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "battery-demo")
    with TestClient(app) as client:
        fuel_response = client.get(
            f"/projects/{FUEL_PROJECT}/artifact-status",
            headers={"Authorization": "Bearer valid-test-token"},
        )
    assert fuel_response.status_code == 403
