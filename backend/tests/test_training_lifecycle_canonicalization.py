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


def test_model_quality_uses_imported_run_predictions_from_same_run(tmp_path, monkeypatch):
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
            "training_run": {"status": "completed", "mlflow_run_id": "run_candidate"},
            "candidate_model": {"metrics_json": {"mlflow_import": {"run_id": "run_candidate"}}},
            "champion_model": None,
        },
    )
    seen: list[tuple[str, str]] = []

    def fake_download(project_id: str, run_id: str, **kwargs):
        seen.append((project_id, run_id))
        return artifact_dir

    monkeypatch.setattr(model_quality, "download_run_artifacts", fake_download)

    payload = model_quality.get_predictions("demo_project", workspace_id="fraunhofer")

    assert seen[-1] == ("demo_project", "run_candidate")
    assert payload["rows"][0]["model_name"] == "mlp"
    assert payload["rows"][0]["y_pred"] == 0.9
