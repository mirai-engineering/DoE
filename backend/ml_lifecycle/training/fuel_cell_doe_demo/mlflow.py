from __future__ import annotations

import os
from pathlib import Path
import shutil

from ml_lifecycle.ingesting.fuel_cell_doe_demo.schema import MLFLOW_MODEL_CACHE_DIR, MLFLOW_REGISTERED_MODEL_NAME, MLFLOW_TRACKING_DIR, PROJECT_ID


def tracking_uri() -> str:
    return os.getenv("MLFLOW_TRACKING_URI", MLFLOW_TRACKING_DIR.resolve().as_uri())


def configure_mlflow(experiment_name: str | None = None):
    import mlflow

    MLFLOW_TRACKING_DIR.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(tracking_uri())
    mlflow.set_registry_uri(tracking_uri())
    mlflow.set_experiment(experiment_name or PROJECT_ID)
    return mlflow


def _latest_model_version_for_run(run_id: str, *, model_name: str = MLFLOW_REGISTERED_MODEL_NAME):
    configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    versions = client.search_model_versions(f"name = '{model_name}'")
    matching = sorted([version for version in versions if version.run_id == run_id], key=lambda item: int(item.version))
    if not matching:
        raise RuntimeError(f"No registered model version found for run_id={run_id} model={model_name}")
    return client, matching[-1]


def set_model_version_tags(run_id: str, tags: dict[str, str], *, model_name: str = MLFLOW_REGISTERED_MODEL_NAME) -> dict[str, str]:
    """Attach searchable lineage/governance metadata to the selected registered version."""
    client, model_version = _latest_model_version_for_run(run_id, model_name=model_name)
    for key, value in tags.items():
        client.set_model_version_tag(model_name, model_version.version, key, str(value))
    try:
        client.set_registered_model_tag(model_name, "model_family", "doe_surrogate")
        client.set_registered_model_tag(model_name, "project_id", str(tags.get("project_id", "")))
        client.update_model_version(
            name=model_name,
            version=model_version.version,
            description=(
                f"Selected DoE surrogate candidate from run {run_id}. "
                f"Model: {tags.get('model_name', 'unknown')}; "
                f"selection metric: {tags.get('selection_metric', 'unknown')}={tags.get('selection_score', 'unknown')}."
            ),
        )
    except Exception:
        pass
    return {"name": model_name, "version": str(model_version.version), "run_id": run_id}


def set_model_alias(run_id: str, alias: str = "champion", *, model_name: str = MLFLOW_REGISTERED_MODEL_NAME) -> dict[str, str]:
    """Assign an MLflow registered-model alias to the model version created by this run."""
    client, model_version = _latest_model_version_for_run(run_id, model_name=model_name)
    client.set_registered_model_alias(model_name, alias, model_version.version)
    client.set_model_version_tag(model_name, model_version.version, "lifecycle_alias", alias)
    return {"name": model_name, "version": str(model_version.version), "alias": alias, "run_id": run_id}


def transition_to_production(run_id: str, *, model_name: str = MLFLOW_REGISTERED_MODEL_NAME) -> dict[str, str]:
    """Legacy Production promotion kept as transition fallback."""
    configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    versions = client.search_model_versions(f"name = '{model_name}'")
    matching = sorted(
        [version for version in versions if version.run_id == run_id],
        key=lambda item: int(item.version),
    )
    if not matching:
        raise RuntimeError(f"No registered model version found for run_id={run_id} model={model_name}")
    model_version = matching[-1]
    client.transition_model_version_stage(
        name=model_name,
        version=model_version.version,
        stage="Production",
        archive_existing_versions=True,
    )
    try:
        client.set_registered_model_alias(model_name, "champion", model_version.version)
    except Exception:
        pass
    return {"name": model_name, "version": str(model_version.version), "stage": "Production", "run_id": run_id}


def download_production_model(*, model_name: str = MLFLOW_REGISTERED_MODEL_NAME, refresh: bool = False) -> Path:
    """Download the MLflow Production model and return the ONNX file path."""
    mlflow = configure_mlflow()
    dst = MLFLOW_MODEL_CACHE_DIR
    if refresh and dst.exists():
        shutil.rmtree(dst)
    if not list(dst.rglob("*.onnx")) if dst.exists() else True:
        dst.mkdir(parents=True, exist_ok=True)
        mlflow.artifacts.download_artifacts(
            artifact_uri=f"models:/{model_name}/Production",
            dst_path=str(dst),
        )
    candidates = sorted(dst.rglob("*.onnx"))
    if not candidates:
        raise FileNotFoundError(f"No ONNX file found in downloaded MLflow Production model at {dst}")
    # MLflow ONNX flavor usually stores the deployable model as model.onnx.
    preferred = [path for path in candidates if path.name == "model.onnx"]
    return preferred[0] if preferred else candidates[0]


def get_latest_registered_metadata(*, model_name: str = MLFLOW_REGISTERED_MODEL_NAME) -> dict:
    configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    versions = client.search_model_versions(f"name = '{model_name}'")
    payload = []
    for version in sorted(versions, key=lambda item: int(item.version), reverse=True):
        payload.append(
            {
                "name": version.name,
                "version": version.version,
                "stage": version.current_stage,
                "run_id": version.run_id,
                "source": version.source,
                "status": version.status,
            }
        )
    production = next((item for item in payload if item["stage"] == "Production"), None)
    return {
        "tracking_uri": tracking_uri(),
        "registered_model_name": model_name,
        "production_model": production,
        "versions": payload,
    }
