from __future__ import annotations

import os
from pathlib import Path
import shutil

from .control_plane import get_project_storage_config
from .workspace_storage import WorkspaceStorageConfig, validate_workspace_object_uri


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REAL_PROJECT_ID = "pem_fuel_cell_real_cathode_degradation"
MLFLOW_TRACKING_DIR = BACKEND_ROOT / "mlruns"
MODEL_CACHE_ROOT = BACKEND_ROOT / ".mlflow-cache"
MODEL_CACHE_DIR = MODEL_CACHE_ROOT / REAL_PROJECT_ID


PROJECT_STORAGE_METADATA = {
    REAL_PROJECT_ID: {
        "workspace_id": "fraunhofer",
        "bucket": "mirai-fuel-cells-demo",
        "prefix": f"workspaces/fraunhofer/projects/{REAL_PROJECT_ID}",
    },
    "battery_tabular_doe_demo": {
        "workspace_id": "battery-demo",
        "bucket": "mirai-batteries-demo",
        "prefix": "workspaces/battery-demo/projects/battery_tabular_doe_demo",
    },
}


def registered_model_name_for_project(project_id: str) -> str:
    return f"doe_surrogate_{project_id}"


def tracking_uri() -> str:
    return os.getenv("MLFLOW_TRACKING_URI", MLFLOW_TRACKING_DIR.resolve().as_uri())


def configure_mlflow():
    import mlflow

    MLFLOW_TRACKING_DIR.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(tracking_uri())
    mlflow.set_registry_uri(tracking_uri())
    return mlflow


def is_mlflow_project(project_id: str) -> bool:
    return bool(project_id) and "/" not in project_id and "\\" not in project_id and ".." not in project_id


def _version_identity_tags(client, version) -> dict[str, str]:
    tags: dict[str, str] = {}
    raw_tags = getattr(version, "tags", None) or {}
    tags.update({str(key): str(value) for key, value in raw_tags.items() if value is not None})
    run_id = str(getattr(version, "run_id", "") or "")
    if run_id:
        try:
            run = client.get_run(run_id)
            tags.update({str(key): str(value) for key, value in run.data.tags.items() if value is not None})
            tags.update({str(key): str(value) for key, value in run.data.params.items() if value is not None and key not in tags})
        except Exception:
            pass
    return tags


def _assert_model_version_belongs_to_project(client, project_id: str, version) -> None:
    expected_name = registered_model_name_for_project(project_id)
    actual_name = str(getattr(version, "name", "") or "")
    if actual_name != expected_name:
        raise ValueError(f"MLflow model name {actual_name!r} does not match expected registered model {expected_name!r}")
    tags = _version_identity_tags(client, version)
    tagged_project_id = tags.get("project_id") or tags.get("schema_project_id")
    if tagged_project_id != project_id:
        raise ValueError(f"MLflow model {expected_name} is missing matching project_id tag for {project_id!r}")


def durable_artifact_pointer_for_project(project_id: str, artifact_kind: str = "onnx_model", workspace_id: str | None = None) -> dict:
    """Return the durable object-store pointer convention for a project artifact.

    This is metadata/validation only. Runtime download still happens through MLflow
    or local development artifacts until the object bootstrap/download path is
    implemented. The pointer avoids assuming `backend/mlruns/` is present in a
    Railway image and gives API/UI code a durable workspace/project-scoped target.
    """

    runtime_config = get_project_storage_config(workspace_id, project_id) if workspace_id else None
    metadata = PROJECT_STORAGE_METADATA.get(project_id)
    if runtime_config is None:
        if metadata is None:
            raise FileNotFoundError(f"No durable artifact pointer metadata configured for project_id={project_id}")
        workspace_id = metadata["workspace_id"]
        bucket = os.getenv(f"MIRAI_{workspace_id.upper().replace('-', '_')}_S3_BUCKET", metadata["bucket"])
        config = WorkspaceStorageConfig(
            workspace_id=workspace_id,
            mode="s3",
            bucket=bucket,
            prefix=metadata["prefix"],
        )
    else:
        config = runtime_config
        workspace_id = config.workspace_id
        bucket = config.bucket
        metadata = {"prefix": config.normalized_prefix}
    suffix_by_kind = {
        "dataset": "intake/dataset.csv" if project_id == "battery_tabular_doe_demo" else "intake/model_table.csv",
        "canonical_table": "canonical/model_table.parquet",
        "preprocessing_output": "training_artifacts/latest/preprocessing.json",
        "mlflow_artifacts": f"mlflow-artifacts/{registered_model_name_for_project(project_id)}",
        "onnx_model": "training_artifacts/latest/model.onnx",
        "bo_state": "bo/state.json",
        "review_file": "reviews/latest.json",
    }
    if artifact_kind not in suffix_by_kind:
        raise ValueError(f"Unsupported durable artifact kind: {artifact_kind}")
    object_key = f"{config.normalized_prefix}/{suffix_by_kind[artifact_kind]}"
    validate_workspace_object_uri(config, object_key)
    object_uri = f"s3://{bucket}/{object_key}" if config.mode == "s3" and bucket else object_key
    return {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "artifact_kind": artifact_kind,
        "bucket": bucket,
        "object_key": object_key,
        "object_uri": object_uri,
        "runtime_status": "pointer_only_until_bootstrapped",
    }


def _download_model_uri(uri: str, dst: Path, mlflow, *, version: str | None = None) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    mlflow.artifacts.download_artifacts(artifact_uri=uri, dst_path=str(dst))
    if version is not None:
        (dst / ".model_version").write_text(str(version), encoding="utf-8")


def _cache_matches(dst: Path, version: str | None) -> bool:
    if not dst.exists() or not (list(dst.rglob("*.onnx")) or list(dst.rglob("model.pkl")) or list(dst.rglob("*.joblib"))):
        return False
    if version is None:
        return True
    marker = dst / ".model_version"
    return marker.exists() and marker.read_text(encoding="utf-8").strip() == str(version)


def download_production_onnx(project_id: str, *, refresh: bool = False) -> Path:
    if not is_mlflow_project(project_id):
        raise ValueError(f"Project {project_id} is not configured for MLflow model loading")
    mlflow = configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    registered_model_name = registered_model_name_for_project(project_id)
    base = MODEL_CACHE_ROOT / project_id
    if refresh and base.exists():
        shutil.rmtree(base)
    selected: tuple[str, str, str] | None = None
    for alias in ["champion", "challenger", "baseline"]:
        try:
            version = client.get_model_version_by_alias(registered_model_name, alias)
            _assert_model_version_belongs_to_project(client, project_id, version)
            selected = (registered_model_name, alias, str(version.version))
            break
        except Exception:
            continue
    if selected is None:
        production_versions = [version for version in client.search_model_versions(f"name = '{registered_model_name}'") if version.current_stage == "Production"]
        valid_production_versions = []
        for version in production_versions:
            try:
                _assert_model_version_belongs_to_project(client, project_id, version)
                valid_production_versions.append(version)
            except Exception:
                continue
        if valid_production_versions:
            production_version = str(sorted(valid_production_versions, key=lambda item: int(item.version))[-1].version)
            selected = (registered_model_name, "production", production_version)
    if selected is None:
        raise FileNotFoundError(f"No champion/challenger/baseline/Production MLflow model found for {registered_model_name}")
    selected_model_name, alias, version = selected
    dst = base / alias
    if not _cache_matches(dst, version):
        uri = f"models:/{selected_model_name}@{alias}" if alias in {"champion", "challenger", "baseline"} else f"models:/{selected_model_name}/Production"
        _download_model_uri(uri, dst, mlflow, version=version)
    candidates = sorted(dst.rglob("*.onnx"))
    if candidates:
        preferred = [path for path in candidates if path.name == "model.onnx"]
        return preferred[0] if preferred else candidates[0]
    sklearn_candidates = sorted([*dst.rglob("model.pkl"), *dst.rglob("*.joblib")])
    if sklearn_candidates:
        preferred = [path for path in sklearn_candidates if path.name == "model.pkl"]
        return preferred[0] if preferred else sklearn_candidates[0]
    raise FileNotFoundError(f"No ONNX or sklearn model found in MLflow cache: {dst}")


def download_aliased_run_artifacts(project_id: str, *, alias: str = "challenger", refresh: bool = False, include_quality: bool = False, include_predictions: bool = False) -> Path:
    """Download schema/preprocessing/quality artifacts from the aliased MLflow run.

    Exported-package local training intentionally does not write into the Railway
    app container. The MLflow run is therefore the durable source for model
    quality and serving metadata when app-local/session artifacts are absent.
    """
    if not is_mlflow_project(project_id):
        raise ValueError(f"Project {project_id} is not configured for MLflow artifact loading")
    mlflow = configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    registered_model_name = registered_model_name_for_project(project_id)
    version = client.get_model_version_by_alias(registered_model_name, alias)
    _assert_model_version_belongs_to_project(client, project_id, version)
    run_id = str(version.run_id)
    if not run_id:
        raise FileNotFoundError(f"MLflow model {registered_model_name}@{alias} has no source run_id")
    dst = MODEL_CACHE_ROOT / project_id / "run-artifacts" / run_id
    marker = dst / ".run_id"
    required = ["schema.json", "preprocessing.json"]
    if refresh and dst.exists():
        shutil.rmtree(dst)
    needs_refresh = True
    if dst.exists() and marker.exists():
        needs_refresh = marker.read_text(encoding="utf-8").strip() != run_id
    if needs_refresh:
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)
        marker.write_text(run_id, encoding="utf-8")
    names = ["schema.json", "preprocessing.json", "metadata.json", "training_manifest.json"]
    if include_quality:
        names.extend(["metrics_summary.json", "candidate_comparison.csv", "preprocessing_report.json", "artifact_summary.json"])
    if include_predictions:
        names.append("predictions.csv")
    try:
        available = {artifact.path for artifact in client.list_artifacts(run_id)}
    except Exception:
        available = set(names)
    for name in names:
        if name not in available or (dst / name).exists():
            continue
        try:
            mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path=name, dst_path=str(dst))
        except Exception:
            continue
    missing = [name for name in required if not (dst / name).exists()]
    if missing:
        raise FileNotFoundError(f"MLflow run artifacts for {project_id}@{alias} are missing: {', '.join(missing)}")
    return dst


def get_registered_model_metadata(project_id: str) -> dict:
    if not is_mlflow_project(project_id):
        return {"project_id": project_id, "mlflow_enabled": False}
    configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    selected_registered_model_name = registered_model_name_for_project(project_id)
    selected_aliases: dict[str, dict | None] = {}
    for alias in ["champion", "challenger", "baseline"]:
        try:
            aliased = client.get_model_version_by_alias(selected_registered_model_name, alias)
            _assert_model_version_belongs_to_project(client, project_id, aliased)
            selected_aliases[alias] = {"name": aliased.name, "version": aliased.version, "run_id": aliased.run_id, "source": aliased.source}
        except Exception:
            selected_aliases[alias] = None
    selected_versions = []
    for version in client.search_model_versions(f"name = '{selected_registered_model_name}'"):
        try:
            _assert_model_version_belongs_to_project(client, project_id, version)
            selected_versions.append(version)
        except Exception:
            continue
    payload = []
    for version in sorted(selected_versions, key=lambda item: int(item.version), reverse=True):
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
    result = {
        "project_id": project_id,
        "mlflow_enabled": True,
        "tracking_uri": tracking_uri(),
        "registered_model_name": selected_registered_model_name,
        "expected_registered_model_name": selected_registered_model_name,
        "using_legacy_registered_model_name": False,
        "production_model": production,
        "aliases": selected_aliases,
        "versions": payload,
    }
    try:
        result["durable_artifact_pointer"] = durable_artifact_pointer_for_project(project_id, "mlflow_artifacts")
        result["durable_onnx_pointer"] = durable_artifact_pointer_for_project(project_id, "onnx_model")
    except Exception:
        pass
    return result
