from __future__ import annotations

from pathlib import Path

import pytest


def test_reconcile_champion_requires_prior_import(monkeypatch):
    from app.services import training_requests

    monkeypatch.setattr(
        training_requests,
        "verify_champion_mlflow_model",
        lambda **kwargs: {
            "workspace_id": kwargs["workspace_id"],
            "project_id": kwargs["project_id"],
            "mlflow_run_id": "run_champion",
            "registered_model_name": f"doe_surrogate_{kwargs['project_id']}",
            "model_version": "3",
            "model_uri": f"models:/doe_surrogate_{kwargs['project_id']}/3",
            "model_name": "mlp",
            "metrics": {},
        },
    )
    monkeypatch.setattr(training_requests, "get_training_run_by_mlflow_run_id", lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match="must be imported"):
        training_requests.reconcile_champion_model(workspace_id="fraunhofer", project_id="demo_project")


def test_champion_reconciliation_activates_verified_imported_run(tmp_path, monkeypatch):
    from app.services import training_requests
    from app.services.workspace_storage import WorkspaceStorageConfig

    artifact_cache = tmp_path / "run-artifacts"
    artifact_cache.mkdir()
    activated: list[dict] = []

    monkeypatch.setattr(
        training_requests,
        "verify_champion_mlflow_model",
        lambda **kwargs: {
            "workspace_id": kwargs["workspace_id"],
            "project_id": kwargs["project_id"],
            "mlflow_run_id": "run_champion",
            "registered_model_name": f"doe_surrogate_{kwargs['project_id']}",
            "model_version": "3",
            "model_uri": f"models:/doe_surrogate_{kwargs['project_id']}/3",
            "alias": "champion",
            "model_name": "mlp",
            "metrics": {"validation_weighted_normalized_rmse": 0.11},
        },
    )
    monkeypatch.setattr(
        training_requests,
        "get_training_run_by_mlflow_run_id",
        lambda workspace_id, project_id, run_id: {
            "training_run_id": "train_req_1",
            "metrics_json": {"mlflow_import": {"run_id": run_id, "alias": "challenger"}},
        },
    )
    monkeypatch.setattr(training_requests, "download_run_artifacts", lambda *args, **kwargs: artifact_cache)
    monkeypatch.setattr(
        training_requests,
        "_project_storage_config_for_training",
        lambda workspace_id, project_id: WorkspaceStorageConfig(workspace_id=workspace_id, mode="s3", bucket="mirai-demo", prefix=f"workspaces/{workspace_id}/projects/{project_id}"),
    )
    monkeypatch.setattr(
        training_requests,
        "durable_artifact_pointer_for_project",
        lambda project_id, artifact_kind, workspace_id=None: {"object_uri": f"s3://mirai-demo/workspaces/{workspace_id}/projects/{project_id}/mlflow-artifacts"},
    )
    monkeypatch.setattr(training_requests, "activate_champion_model", lambda **kwargs: activated.append(kwargs))

    result = training_requests.reconcile_champion_model(workspace_id="fraunhofer", project_id="demo_project", reconciled_by="operator")

    assert result["status"] == "approved_champion_active"
    assert result["mlflow"]["alias"] == "champion"
    assert activated[0]["training_run_id"] == "train_req_1"
    assert activated[0]["version"] == "3"
    assert activated[0]["metrics"]["mlflow_import"]["alias"] == "champion"


def test_champion_reconciliation_rejects_wrong_workspace(monkeypatch):
    from app.services import training_requests

    monkeypatch.setattr(
        training_requests,
        "verify_champion_mlflow_model",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("MLflow champion identity does not match this Mirai workspace/project")),
    )

    with pytest.raises(ValueError, match="identity does not match"):
        training_requests.reconcile_champion_model(workspace_id="fraunhofer", project_id="wrong_project")


def test_runtime_serving_does_not_fallback_to_session_candidate_without_champion(tmp_path, monkeypatch):
    from app.services import project_registry

    artifact_dir = tmp_path / "artifacts"
    models_dir = artifact_dir / "models"
    models_dir.mkdir(parents=True)
    (artifact_dir / "schema.json").write_text('{"metadata":{"template_id":"generic_tabular_doe"}}')
    (artifact_dir / "metrics_summary.json").write_text('{"best_model_name":"mlp"}')
    (models_dir / "mlp.joblib").write_text("not-a-real-model")

    monkeypatch.setattr(project_registry, "_latest_project_artifact_dir", lambda project_id, workspace_id=None: artifact_dir)
    monkeypatch.setattr(project_registry, "get_project_runtime_state", lambda workspace_id, project_id: {"project": {"project_id": project_id}, "champion_model": None})
    monkeypatch.setattr(project_registry, "download_production_onnx", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("No reconciled Mirai champion")))

    with pytest.raises(FileNotFoundError, match="No reconciled Mirai champion"):
        project_registry.get_project_model_path("demo_project", workspace_id="fraunhofer")


def test_model_quality_uses_loaded_champion_predictions_from_same_run(tmp_path, monkeypatch):
    from app.services import model_quality

    artifact_dir = tmp_path / "run-artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "metrics_summary.json").write_text('{"best_model_name":"mlp"}')
    (artifact_dir / "candidate_comparison.csv").write_text("model_name,selected_challenger\nmlp,true\n")
    (artifact_dir / "preprocessing_report.json").write_text("{}")
    (artifact_dir / "predictions.csv").write_text("model_name,split,y_true,y_pred\nmlp,test,1.0,0.9\n")

    monkeypatch.setattr(
        model_quality,
        "get_project_runtime_state",
        lambda workspace_id, project_id: {
            "training_run": {"status": "completed", "mlflow_run_id": "run_champion"},
            "candidate_model": {"metrics_json": {"mlflow_import": {"run_id": "run_candidate"}}},
            "champion_model": {"metrics_json": {"mlflow_import": {"run_id": "run_champion"}}},
        },
    )
    seen: list[tuple[str, str]] = []

    def fake_download(project_id: str, run_id: str, **kwargs):
        seen.append((project_id, run_id))
        return artifact_dir

    monkeypatch.setattr(model_quality, "download_run_artifacts", fake_download)
    monkeypatch.setattr(model_quality, "loaded_champion_mlflow_import", lambda project_id, workspace_id=None: {"run_id": "run_champion"})

    payload = model_quality.get_predictions("demo_project", workspace_id="fraunhofer")

    assert seen[-1] == ("demo_project", "run_champion")
    assert payload["rows"][0]["model_name"] == "mlp"
    assert payload["rows"][0]["y_pred"] == 0.9


def test_load_champion_model_upserts_runtime_state_and_schema(tmp_path, monkeypatch):
    from app.services import training_requests
    from app.services.workspace_storage import WorkspaceStorageConfig

    artifact_cache = tmp_path / "run-artifacts"
    artifact_cache.mkdir()
    (artifact_cache / "schema.json").write_text(
        '{"project_id":"demo_project","inputs":[{"name":"x1","label":"Temperature","min":0,"max":1,"unit":"C"}],"outputs":[{"name":"y1","label":"Yield","unit":"%","direction":"maximize"}]}',
        encoding="utf-8",
    )
    onnx_path = tmp_path / "model.onnx"
    onnx_path.write_bytes(b"onnx")
    calls: dict[str, list[dict]] = {"schema": [], "created": [], "completed": [], "activated": []}

    monkeypatch.setattr(
        training_requests,
        "verify_champion_mlflow_model",
        lambda **kwargs: {
            "workspace_id": kwargs["workspace_id"],
            "project_id": kwargs["project_id"],
            "mlflow_run_id": "run_champion",
            "registered_model_name": f"doe_surrogate_{kwargs['project_id']}",
            "model_version": "7",
            "model_uri": f"models:/doe_surrogate_{kwargs['project_id']}/7",
            "alias": "champion",
            "model_name": "ridge",
            "metrics": {"validation_weighted_normalized_rmse": 0.2},
            "training_manifest": {"workspace_id": kwargs["workspace_id"], "project_id": kwargs["project_id"], "training_request_id": "train_req_7", "dataset_id": "dataset_1", "source_checksums": {"model_table.csv": "abc"}},
            "tags": {"training_request_id": "train_req_7", "dataset_id": "dataset_1"},
        },
    )
    monkeypatch.setattr(training_requests, "download_run_artifacts", lambda *args, **kwargs: artifact_cache)
    monkeypatch.setattr(training_requests, "download_production_onnx", lambda *args, **kwargs: onnx_path)
    monkeypatch.setattr(training_requests, "get_training_run_by_mlflow_run_id", lambda *args, **kwargs: None)
    monkeypatch.setattr(training_requests, "get_project_schema", lambda *args, **kwargs: {"inputs": [], "outputs": []})
    monkeypatch.setattr(
        training_requests,
        "_project_storage_config_for_training",
        lambda workspace_id, project_id: WorkspaceStorageConfig(workspace_id=workspace_id, mode="s3", bucket="mirai-demo", prefix=f"workspaces/{workspace_id}/projects/{project_id}"),
    )
    monkeypatch.setattr(
        training_requests,
        "durable_artifact_pointer_for_project",
        lambda project_id, artifact_kind, workspace_id=None: {"object_uri": f"s3://mirai-demo/workspaces/{workspace_id}/projects/{project_id}/{artifact_kind}"},
    )
    monkeypatch.setattr(training_requests, "upsert_schema_manifest", lambda **kwargs: calls["schema"].append(kwargs))
    monkeypatch.setattr(training_requests, "create_training_run", lambda **kwargs: calls["created"].append(kwargs))
    monkeypatch.setattr(training_requests, "complete_training_run", lambda **kwargs: calls["completed"].append(kwargs))
    monkeypatch.setattr(training_requests, "activate_champion_model", lambda **kwargs: calls["activated"].append(kwargs))

    result = training_requests.load_champion_model(
        workspace_id="fraunhofer",
        project_id="demo_project",
        mlflow_run_id="run_champion",
        registered_model_name="doe_surrogate_demo_project",
        model_version="7",
        loaded_by="operator",
    )

    assert result["status"] == "approved_champion_active"
    assert result["stage"] == "champion_model_loaded"
    assert result["schema_outputs"] == ["y1"]
    assert calls["schema"][0]["schema"]["outputs"][0]["label"] == "Yield"
    assert calls["created"][0]["training_run_id"] == "train_req_7"
    assert calls["completed"][0]["mlflow_run_id"] == "run_champion"
    assert calls["activated"][0]["version"] == "7"
    assert calls["activated"][0]["metrics"]["mlflow_import"]["model_artifact_format"] == "onnx"


def test_model_quality_predictions_support_variable_schema_outputs(tmp_path, monkeypatch):
    from app.services import model_quality
    from app.services import project_registry

    artifact_dir = tmp_path / "run-artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "metrics_summary.json").write_text('{"best_model_name":"ridge"}', encoding="utf-8")
    (artifact_dir / "candidate_comparison.csv").write_text("model_name,selected_challenger\nridge,true\n", encoding="utf-8")
    (artifact_dir / "predictions.csv").write_text(
        "model_name,split,y1_true,y1_pred,y1_residual,y2_true,y2_pred,y2_residual\nridge,test,1.0,0.9,0.1,2.0,2.2,-0.2\n",
        encoding="utf-8",
    )
    schema = {
        "project_id": "demo_project",
        "inputs": [{"name": "x1", "label": "Temperature", "min": 0, "max": 1, "unit": "C"}],
        "outputs": [
            {"name": "y1", "label": "Yield", "unit": "%", "direction": "maximize"},
            {"name": "y2", "label": "Cost", "unit": "EUR", "direction": "minimize"},
        ],
    }
    monkeypatch.setattr(project_registry, "get_project_schema", lambda *args, **kwargs: schema)
    monkeypatch.setattr(model_quality, "_artifact_dir", lambda *args, **kwargs: artifact_dir)

    payload = model_quality.get_predictions("demo_project", workspace_id="fraunhofer")
    output_labels = {output["name"]: output["label"] for output in project_registry.get_project_schema("demo_project", "fraunhofer")["outputs"]}

    assert {"y1_true", "y1_pred", "y2_true", "y2_pred"}.issubset(payload["columns"])
    assert payload["rows"][0]["y2_pred"] == 2.2
    assert output_labels == {"y1": "Yield", "y2": "Cost"}
