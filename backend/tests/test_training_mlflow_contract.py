import pytest

from ml_lifecycle.training.generic_tabular_doe import train as generic_train


def test_demo_mlflow_contract_allows_remote_tracking_and_s3_artifacts(monkeypatch):
    monkeypatch.setenv("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW", "1")
    monkeypatch.setenv("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS", "1")

    generic_train._assert_demo_mlflow_contract(  # noqa: SLF001 - targeted contract guard test
        tracking_uri="https://mlflow.example.railway.app",
        artifact_location="s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/fuel-cell/mlflow-artifacts",
    )


def test_demo_mlflow_contract_rejects_local_tracking_when_required(monkeypatch):
    monkeypatch.setenv("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW", "1")
    monkeypatch.delenv("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS", raising=False)

    for tracking_uri in ["file:///tmp/mlruns", "sqlite:///tmp/mlflow.db", "postgresql://db.example.test/mlflow", "mysql://db.example.test/mlflow", "http://localhost:5000", "http://127.0.0.1:5000"]:
        with pytest.raises(RuntimeError, match="remote http"):
            generic_train._assert_demo_mlflow_contract(  # noqa: SLF001
                tracking_uri=tracking_uri,
                artifact_location="s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/fuel-cell/mlflow-artifacts",
            )


def test_demo_mlflow_contract_rejects_non_s3_artifacts_when_required(monkeypatch):
    monkeypatch.delenv("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW", raising=False)
    monkeypatch.setenv("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS", "1")

    with pytest.raises(RuntimeError, match="artifact location is not s3"):
        generic_train._assert_demo_mlflow_contract(  # noqa: SLF001
            tracking_uri="https://mlflow.example.railway.app",
            artifact_location="file:///tmp/mlruns/1",
        )
