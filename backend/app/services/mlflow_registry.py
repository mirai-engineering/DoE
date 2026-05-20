from __future__ import annotations

import os
from pathlib import Path
import shutil


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REAL_PROJECT_ID = "pem_fuel_cell_real_cathode_degradation"
MLFLOW_TRACKING_DIR = BACKEND_ROOT / "mlruns"
MODEL_CACHE_ROOT = BACKEND_ROOT / ".mlflow-cache"
MODEL_CACHE_DIR = MODEL_CACHE_ROOT / REAL_PROJECT_ID


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


def _download_model_uri(uri: str, dst: Path, mlflow, *, version: str | None = None) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    mlflow.artifacts.download_artifacts(artifact_uri=uri, dst_path=str(dst))
    if version is not None:
        (dst / ".model_version").write_text(str(version), encoding="utf-8")


def _cache_matches(dst: Path, version: str | None) -> bool:
    if not dst.exists() or not list(dst.rglob("*.onnx")):
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
    fallback_model_names = [registered_model_name, project_id]
    base = MODEL_CACHE_ROOT / project_id
    if refresh and base.exists():
        shutil.rmtree(base)
    selected: tuple[str, str, str] | None = None
    for candidate_model_name in fallback_model_names:
        for alias in ["champion", "challenger", "baseline"]:
            try:
                version = client.get_model_version_by_alias(candidate_model_name, alias)
                selected = (candidate_model_name, alias, str(version.version))
                break
            except Exception:
                continue
        if selected is not None:
            break
    if selected is None:
        for candidate_model_name in fallback_model_names:
            production_versions = [version for version in client.search_model_versions(f"name = '{candidate_model_name}'") if version.current_stage == "Production"]
            if production_versions:
                production_version = str(sorted(production_versions, key=lambda item: int(item.version))[-1].version)
                selected = (candidate_model_name, "production", production_version)
                break
    if selected is None:
        raise FileNotFoundError(f"No champion/challenger/baseline/Production MLflow model found for {registered_model_name}")
    selected_model_name, alias, version = selected
    dst = base / alias
    if not _cache_matches(dst, version):
        uri = f"models:/{selected_model_name}@{alias}" if alias in {"champion", "challenger", "baseline"} else f"models:/{selected_model_name}/Production"
        _download_model_uri(uri, dst, mlflow, version=version)
    candidates = sorted(dst.rglob("*.onnx"))
    if not candidates:
        raise FileNotFoundError(f"No ONNX model found in MLflow cache: {dst}")
    preferred = [path for path in candidates if path.name == "model.onnx"]
    return preferred[0] if preferred else candidates[0]


def get_registered_model_metadata(project_id: str) -> dict:
    if not is_mlflow_project(project_id):
        return {"project_id": project_id, "mlflow_enabled": False}
    configure_mlflow()
    from mlflow.tracking import MlflowClient

    client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
    expected_registered_model_name = registered_model_name_for_project(project_id)
    fallback_model_names = [expected_registered_model_name, project_id]
    selected_registered_model_name = expected_registered_model_name
    selected_versions = []
    selected_aliases: dict[str, dict | None] = {}

    for candidate_model_name in fallback_model_names:
        aliases: dict[str, dict | None] = {}
        has_alias = False
        for alias in ["champion", "challenger", "baseline"]:
            try:
                aliased = client.get_model_version_by_alias(candidate_model_name, alias)
                aliases[alias] = {"name": aliased.name, "version": aliased.version, "run_id": aliased.run_id, "source": aliased.source}
                has_alias = True
            except Exception:
                aliases[alias] = None
        versions = client.search_model_versions(f"name = '{candidate_model_name}'")
        if has_alias or versions:
            selected_registered_model_name = candidate_model_name
            selected_versions = versions
            selected_aliases = aliases
            break

    if not selected_aliases:
        selected_aliases = {"champion": None, "challenger": None, "baseline": None}
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
    return {
        "project_id": project_id,
        "mlflow_enabled": True,
        "tracking_uri": tracking_uri(),
        "registered_model_name": selected_registered_model_name,
        "expected_registered_model_name": expected_registered_model_name,
        "using_legacy_registered_model_name": selected_registered_model_name != expected_registered_model_name,
        "production_model": production,
        "aliases": selected_aliases,
        "versions": payload,
    }
