import json

from fastapi.testclient import TestClient

from app.main import app
from app.services.mlflow_registry import durable_artifact_pointer_for_project, get_registered_model_metadata
from app.services.workspace_storage import WorkspaceStorageConfig
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


def test_runtime_project_storage_metadata_routes_two_projects_to_distinct_buckets(monkeypatch):
    from app.services import mlflow_registry

    def fake_project_storage_config(workspace_id: str, project_id: str):
        return WorkspaceStorageConfig(
            workspace_id=workspace_id,
            mode="s3",
            bucket=f"bucket-for-{project_id}",
            prefix=f"workspaces/{workspace_id}/projects/{project_id}",
        )

    monkeypatch.setattr(mlflow_registry, "get_project_storage_config", fake_project_storage_config)

    project_a = durable_artifact_pointer_for_project("project_a", "onnx_model", "client_user_123")
    project_b = durable_artifact_pointer_for_project("project_b", "onnx_model", "client_user_123")

    assert project_a["workspace_id"] == "client_user_123"
    assert project_b["workspace_id"] == "client_user_123"
    assert project_a["bucket"] == "bucket-for-project_a"
    assert project_b["bucket"] == "bucket-for-project_b"
    assert project_a["object_key"] == "workspaces/client_user_123/projects/project_a/training_artifacts/latest/model.onnx"
    assert project_b["object_key"] == "workspaces/client_user_123/projects/project_b/training_artifacts/latest/model.onnx"


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


def test_workspace_model_quality_requires_loaded_champion(monkeypatch):
    from app.services import model_quality

    project_id = "runtime_project_unloaded"
    workspace_id = "fraunhofer"
    monkeypatch.setattr(model_quality, "get_project_runtime_state", lambda ws, pid: {"project": {"project_id": pid}})
    monkeypatch.setattr(model_quality, "loaded_champion_mlflow_import", lambda pid, ws=None: None)

    expected = f"Champion model is not loaded yet for project_id={project_id}; promote a version to champion in MLflow, then use Load champion model."
    try:
        model_quality.get_metrics(project_id, workspace_id)
    except ValueError as exc:
        assert str(exc) == expected
    else:
        raise AssertionError("Expected unloaded runtime project to refuse model quality")
    summary = model_quality.get_model_quality_summary(project_id, workspace_id)
    assert summary["warning"] == expected
    assert summary["active_model"]["lifecycle_status"] == "champion_not_loaded"


def test_loaded_champion_quality_artifacts_resolve_by_run_id(monkeypatch, tmp_path):
    from app.services import model_quality

    project_id = "runtime_project_loaded"
    workspace_id = "fraunhofer"
    run_id = "run_immutable_123"
    artifact_dir = tmp_path / "artifacts" / run_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "metrics_summary.json").write_text('{"best_model_name":"mlp"}\n', encoding="utf-8")
    (artifact_dir / "candidate_comparison.csv").write_text("model_name,score,validation_mean_r2\nmlp,0.1,\n", encoding="utf-8")
    (artifact_dir / "schema.json").write_text('{"outputs":[{"name":"y1"}]}\n', encoding="utf-8")
    (artifact_dir / "preprocessing.json").write_text("{}\n", encoding="utf-8")
    (artifact_dir / "predictions.csv").write_text("model_name,split,y1_true,y1_pred\nmlp,test,1.0,0.9\n", encoding="utf-8")
    calls = []

    def fake_download(pid, rid, *, refresh=False, include_quality=False, include_predictions=False):
        calls.append({"project_id": pid, "run_id": rid, "include_quality": include_quality, "include_predictions": include_predictions})
        return artifact_dir

    monkeypatch.setattr(model_quality, "get_project_runtime_state", lambda ws, pid: {"project": {"project_id": pid}, "champion_model": {"metrics_json": {"mlflow_import": {"run_id": run_id}}}})
    monkeypatch.setattr(model_quality, "loaded_champion_mlflow_import", lambda pid, ws=None: {"run_id": run_id, "registered_model_name": f"doe_surrogate_{pid}", "alias": "champion"})
    monkeypatch.setattr(model_quality, "download_run_artifacts", fake_download)

    assert model_quality.get_metrics(project_id, workspace_id)["best_model_name"] == "mlp"
    comparison = model_quality.get_candidate_comparison(project_id, workspace_id)
    assert comparison[0]["model_name"] == "mlp"
    assert comparison[0]["validation_mean_r2"] is None
    json.dumps(model_quality.get_model_quality_summary(project_id, workspace_id), allow_nan=False)
    predictions = model_quality.get_predictions(project_id, workspace_id=workspace_id)
    assert predictions["rows"][0]["y1_pred"] == 0.9
    assert {call["run_id"] for call in calls} == {run_id}
    assert any(call["include_predictions"] for call in calls)


def test_workspace_model_quality_does_not_use_challenger_fallback(monkeypatch):
    from app.services import model_quality

    project_id = "runtime_project_no_challenger"
    workspace_id = "fraunhofer"
    monkeypatch.setattr(model_quality, "get_project_runtime_state", lambda ws, pid: {"project": {"project_id": pid}})
    monkeypatch.setattr(model_quality, "loaded_champion_mlflow_import", lambda pid, ws=None: None)

    def fail_challenger(*args, **kwargs):
        raise AssertionError("workspace model quality must not resolve challenger alias")

    monkeypatch.setattr(model_quality, "download_aliased_run_artifacts", fail_challenger)

    try:
        model_quality.get_metrics(project_id, workspace_id)
    except ValueError as exc:
        assert "Champion model is not loaded yet" in str(exc)
    else:
        raise AssertionError("Expected unloaded runtime project to fail before challenger fallback")


def test_runtime_schema_prefers_loaded_champion_schema_outputs(monkeypatch, tmp_path):
    from app.services import project_registry

    project_id = "runtime_project_schema"
    workspace_id = "fraunhofer"
    artifact_dir = tmp_path / "run"
    artifact_dir.mkdir()
    (artifact_dir / "schema.json").write_text(
        '{"display_name":"Loaded","inputs":[{"name":"x1","min":0,"max":1}],"outputs":[{"name":"y1","label":"Actual output"}],"metadata":{"template_id":"generic_tabular_doe"}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(project_registry, "_imported_mlflow_artifact_dir", lambda pid, ws, champion_only=False, include_predictions=False: artifact_dir)
    project_registry.clear_registry_cache()

    schema = project_registry.get_project_schema(project_id, workspace_id)

    assert [item["name"] for item in schema["outputs"]] == ["y1"]
    assert schema["workspace_id"] == workspace_id


def test_workspace_project_model_path_does_not_resolve_challenger_alias(monkeypatch, tmp_path):
    from app.services import project_registry

    artifact_dir = tmp_path / "run"
    models_dir = artifact_dir / "models"
    models_dir.mkdir(parents=True)
    (artifact_dir / "schema.json").write_text('{"metadata":{"template_id":"generic_tabular_doe"}}\n', encoding="utf-8")
    (artifact_dir / "metrics_summary.json").write_text('{"best_model_name":"mlp"}\n', encoding="utf-8")
    (models_dir / "mlp.joblib").write_text("model", encoding="utf-8")
    monkeypatch.setenv("DOE_DISABLE_MLFLOW_MODEL_LOADING", "true")
    monkeypatch.setattr(project_registry, "_latest_project_artifact_dir", lambda project_id, workspace_id=None: artifact_dir)

    def fail_alias(*args, **kwargs):
        raise AssertionError("workspace model path must not resolve challenger alias")

    monkeypatch.setattr(project_registry, "_mlflow_alias_model_name", fail_alias)

    assert project_registry.get_project_model_path("runtime_project_loaded", workspace_id="fraunhofer") == models_dir / "mlp.joblib"


def test_design_studio_state_passes_workspace_to_active_model(monkeypatch):
    from app.services import design_studio

    captured = {}
    project_id = "runtime_project_design"
    workspace_id = "fraunhofer"
    schema = {
        "inputs": [{"name": "x1", "min": 0, "max": 1}],
        "outputs": [{"name": "y1", "direction": "maximize"}],
        "domain_metadata": {"ui_config": {}},
    }

    monkeypatch.setattr(design_studio, "_project_schema", lambda pid, ws=None: schema)
    monkeypatch.setattr(design_studio, "_plot_recipes", lambda pid, schema, ws=None: [])
    monkeypatch.setattr(design_studio, "_fuel_cell_preset", lambda pid, ws=None: {"enabled": False})
    monkeypatch.setattr(design_studio, "get_real_cell_options", lambda pid, ws=None: {"project_id": pid, "real_cell_options": []})

    def fake_active(pid, ws=None):
        captured["workspace_id"] = ws
        return {"served_source": "loaded_champion", "mlflow_traceability": {"run_id": "run_123"}}

    monkeypatch.setattr(design_studio, "get_active_model_metadata", fake_active)

    state = design_studio.get_design_studio_state(project_id, workspace_id)

    assert captured["workspace_id"] == workspace_id
    assert state["workspace_id"] == workspace_id
    assert state["active_model"]["mlflow_traceability"]["run_id"] == "run_123"
