from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile

from .control_plane import get_project_runtime_state, get_project_storage_config
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


def _candidate_runtime_workspaces() -> list[str]:
    configured = os.getenv("MIRAI_TENANT_WORKSPACE_IDS") or os.getenv("MIRAI_ALLOWED_WORKSPACE_IDS")
    values = [item.strip() for item in configured.split(",") if item.strip()] if configured else ["fraunhofer", "test-client-isolated"]
    return list(dict.fromkeys(values))


def _model_file_from_cache(dst: Path) -> Path | None:
    candidates = sorted(dst.rglob("*.onnx"))
    if candidates:
        preferred = [path for path in candidates if path.name == "model.onnx"]
        return preferred[0] if preferred else candidates[0]
    sklearn_candidates = sorted([*dst.rglob("model.pkl"), *dst.rglob("*.joblib")])
    if sklearn_candidates:
        preferred = [path for path in sklearn_candidates if path.name == "model.pkl"]
        return preferred[0] if preferred else sklearn_candidates[0]
    return None


def _imported_model_uri_from_runtime(project_id: str, workspace_id: str | None = None) -> tuple[str, str] | None:
    workspaces = [workspace_id] if workspace_id else _candidate_runtime_workspaces()
    for candidate_workspace in [item for item in workspaces if item]:
        try:
            runtime_state = get_project_runtime_state(str(candidate_workspace), project_id)
        except Exception:
            continue
        model = runtime_state.get("champion_model") if isinstance(runtime_state, dict) else None
        metrics = model.get("metrics_json") if isinstance(model, dict) and isinstance(model.get("metrics_json"), dict) else {}
        mlflow_import = metrics.get("mlflow_import") if isinstance(metrics.get("mlflow_import"), dict) else None
        model_uri = mlflow_import.get("model_uri") if isinstance(mlflow_import, dict) else None
        run_id = mlflow_import.get("run_id") if isinstance(mlflow_import, dict) else None
        if model_uri and run_id:
            return str(model_uri), str(run_id)
    return None


def download_production_onnx(project_id: str, *, refresh: bool = False, workspace_id: str | None = None) -> Path:
    if not is_mlflow_project(project_id):
        raise ValueError(f"Project {project_id} is not configured for MLflow model loading")
    mlflow = configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    registered_model_name = registered_model_name_for_project(project_id)
    base = MODEL_CACHE_ROOT / project_id
    if refresh and base.exists():
        shutil.rmtree(base)
    imported = _imported_model_uri_from_runtime(project_id, workspace_id)
    if imported is not None:
        imported_uri, imported_run_id = imported
        dst = base / "imported" / imported_run_id
        if not _cache_matches(dst, imported_run_id):
            _download_model_uri(imported_uri, dst, mlflow, version=imported_run_id)
        imported_model = _model_file_from_cache(dst)
        if imported_model is not None:
            return imported_model
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
    cached_model = _model_file_from_cache(dst)
    if cached_model is not None:
        return cached_model
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


def verify_external_mlflow_model_version(
    *,
    workspace_id: str,
    project_id: str,
    dataset_id: str,
    session_id: str,
    training_request_id: str,
    mlflow_run_id: str,
    registered_model_name: str | None = None,
    model_version: str | None = None,
    alias: str = "challenger",
) -> dict:
    """Verify that an externally trained MLflow model belongs to one Mirai request.

    The caller supplies identifiers only; this function independently verifies
    registry/run metadata and required artifacts before the run can be imported
    into the Mirai control plane.
    """
    if not is_mlflow_project(project_id):
        raise ValueError(f"Project {project_id!r} is not a valid MLflow project id")
    if not mlflow_run_id or any(token in mlflow_run_id for token in ["/", "\\", ".."]):
        raise ValueError("A valid MLflow run id is required")
    expected_name = registered_model_name_for_project(project_id)
    if registered_model_name and registered_model_name != expected_name:
        raise ValueError(f"Registered model name must be {expected_name!r} for project {project_id!r}")
    if not alias:
        raise ValueError("An MLflow model alias is required so Mirai serving and quality paths resolve the imported model consistently")

    mlflow = configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    version = client.get_model_version(expected_name, str(model_version)) if model_version else client.get_model_version_by_alias(expected_name, alias)
    if model_version and alias:
        alias_version = client.get_model_version_by_alias(expected_name, alias)
        if str(alias_version.version) != str(model_version):
            raise ValueError("Supplied MLflow alias does not point to the supplied model version")
    _assert_model_version_belongs_to_project(client, project_id, version)
    if str(getattr(version, "run_id", "") or "") != mlflow_run_id:
        raise ValueError("MLflow model version does not point to the supplied run id")

    run = client.get_run(mlflow_run_id)
    if str(getattr(run.info, "status", "") or "") != "FINISHED":
        raise ValueError("MLflow run must be FINISHED before import")
    tags = {str(key): str(value) for key, value in run.data.tags.items() if value is not None}
    tags.update({str(key): str(value) for key, value in run.data.params.items() if value is not None and key not in tags})
    actual_identity = {
        "workspace_id": tags.get("workspace_id"),
        "project_id": tags.get("project_id"),
        "dataset_id": tags.get("dataset_id"),
        "ingestion_session_id": tags.get("ingestion_session_id") or tags.get("session_id"),
        "training_request_id": tags.get("training_request_id"),
    }
    expected_identity = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "training_request_id": training_request_id,
    }
    mismatches = [key for key, expected in expected_identity.items() if actual_identity.get(key) != expected]
    if mismatches:
        raise ValueError("MLflow run identity does not match this Mirai training request: " + ", ".join(mismatches))

    required_artifacts = {"schema.json", "preprocessing.json", "metrics_summary.json", "candidate_comparison.csv", "predictions.csv", "training_manifest.json"}
    available = {artifact.path for artifact in client.list_artifacts(mlflow_run_id)}
    missing = sorted(required_artifacts - available)
    if missing:
        raise FileNotFoundError("MLflow run is missing required import artifacts: " + ", ".join(missing))
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = mlflow.artifacts.download_artifacts(run_id=mlflow_run_id, artifact_path="training_manifest.json", dst_path=tmpdir)
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    manifest_identity = {
        "workspace_id": manifest.get("workspace_id"),
        "project_id": manifest.get("project_id"),
        "dataset_id": manifest.get("dataset_id"),
        "ingestion_session_id": manifest.get("session_id") or manifest.get("ingestion_session_id"),
        "training_request_id": manifest.get("training_request_id"),
    }
    manifest_mismatches = [key for key, expected in expected_identity.items() if manifest_identity.get(key) != expected]
    if manifest_mismatches:
        raise ValueError("MLflow training_manifest identity does not match this Mirai training request: " + ", ".join(manifest_mismatches))
    if not isinstance(manifest.get("source_checksums"), dict) or not manifest["source_checksums"]:
        raise ValueError("MLflow training_manifest.json is missing source_checksums")

    resolved_alias = alias
    return {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "dataset_id": dataset_id,
        "session_id": session_id,
        "training_request_id": training_request_id,
        "mlflow_run_id": mlflow_run_id,
        "registered_model_name": expected_name,
        "model_version": str(version.version),
        "alias": resolved_alias,
        "model_source": str(getattr(version, "source", "") or f"models:/{expected_name}/{version.version}"),
        "model_uri": f"models:/{expected_name}/{version.version}",
        "model_name": tags.get("model_name") or tags.get("model_family") or "external_mlflow_model",
        "metrics": dict(run.data.metrics),
        "tags": tags,
        "training_manifest": manifest,
    }


def download_run_artifacts(project_id: str, run_id: str, *, refresh: bool = False, include_quality: bool = False, include_predictions: bool = False) -> Path:
    """Download schema/preprocessing/quality artifacts from an immutable MLflow run id."""
    if not is_mlflow_project(project_id):
        raise ValueError(f"Project {project_id} is not configured for MLflow artifact loading")
    mlflow = configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    dst = MODEL_CACHE_ROOT / project_id / "run-artifacts" / run_id
    marker = dst / ".run_id"
    required = ["schema.json", "preprocessing.json"]
    if include_quality:
        required.extend(["metrics_summary.json", "candidate_comparison.csv"])
    if include_predictions:
        required.append("predictions.csv")
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
        raise FileNotFoundError(f"MLflow run artifacts for {project_id}/{run_id} are missing: {', '.join(missing)}")
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
