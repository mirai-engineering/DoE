from functools import lru_cache
import json
import logging
import os
from pathlib import Path

from .control_plane import list_workspace_projects
from .data_intake import list_ingestion_sessions, read_project_metadata, read_status, session_workspace
from .domain_metadata import apply_variable_metadata_to_schema, attach_domain_metadata, infer_template_id
from .mlflow_registry import download_production_onnx, is_mlflow_project, registered_model_name_for_project, tracking_uri
from .workspace_storage import local_object_storage_root
from .workspaces import get_workspace


logger = logging.getLogger(__name__)
REAL_FUEL_CELL_PROJECT_ID = "pem_fuel_cell_real_cathode_degradation"
BATTERY_DEMO_PROJECT_ID = "battery_tabular_doe_demo"

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
OBJECT_STORE_ROOT = local_object_storage_root()
REFERENCE_DATA_ROOT = Path(os.getenv("DOE_REFERENCE_DATA_ROOT", REPO_ROOT / "data" / "reference"))
REAL_REFERENCE_ARTIFACT_DIR = REFERENCE_DATA_ROOT / "pem_fuel_cell_cathode_degradation" / "training_artifacts" / "latest"


class ProjectNotFoundError(LookupError):
    pass


def _safe_project_id(project_id: str) -> str:
    if not project_id or "/" in project_id or "\\" in project_id or ".." in project_id:
        raise ProjectNotFoundError(f"Unknown project_id: {project_id}")
    return project_id


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _reference_project_dir(project_id: str) -> Path:
    safe_project_id = _safe_project_id(project_id)
    if safe_project_id == REAL_FUEL_CELL_PROJECT_ID and (REAL_REFERENCE_ARTIFACT_DIR / "schema.json").exists():
        return REAL_REFERENCE_ARTIFACT_DIR
    raise ProjectNotFoundError(f"Unknown project_id: {project_id}")


def _workspace_from_payload(project_id: str, display_name: str, payload: dict | None = None) -> dict[str, str]:
    payload = payload or {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    explicit_id = payload.get("workspace_id") or metadata.get("workspace_id")
    explicit_name = payload.get("workspace_name") or metadata.get("workspace_name") or metadata.get("client_name")
    if explicit_id:
        workspace = get_workspace(str(explicit_id)) or {}
        return {"workspace_id": str(explicit_id), "workspace_name": str(workspace.get("display_name") or explicit_name or explicit_id)}
    if explicit_name:
        workspace_id = str(explicit_name).strip().lower().replace(" ", "-")
        workspace = get_workspace(workspace_id) or {}
        return {"workspace_id": str(workspace.get("workspace_id") or workspace_id), "workspace_name": str(workspace.get("display_name") or explicit_name)}
    lowered = f"{project_id} {display_name}".lower()
    if "fraunhofer" in lowered or "pem" in lowered or "fuel_cell" in lowered or "fuel cell" in lowered:
        return {"workspace_id": "fraunhofer", "workspace_name": "Fraunhofer"}
    return {"workspace_id": "mirai-engineering", "workspace_name": "Mirai Engineering"}


def _battery_placeholder_schema() -> dict:
    return {
        "project_id": BATTERY_DEMO_PROJECT_ID,
        "display_name": "Battery Tabular DoE Demo",
        "description": "Battery/generic tabular DoE demo metadata placeholder. Dataset/model bootstrap is pending an approved source dataset.",
        "schema_version": "placeholder-v1",
        "workspace_id": "battery-demo",
        "workspace_name": "Battery Demo",
        "inputs": [
            {"name": "formation_temperature", "label": "Formation temperature", "type": "continuous", "min": 20, "max": 60, "unit": "°C"},
            {"name": "charge_rate", "label": "Charge rate", "type": "continuous", "min": 0.1, "max": 2.0, "unit": "C"},
            {"name": "electrolyte_additive_pct", "label": "Electrolyte additive", "type": "continuous", "min": 0.0, "max": 5.0, "unit": "%"},
        ],
        "outputs": [
            {"name": "capacity_retention", "label": "Capacity retention", "direction": "maximize", "unit": "%"},
            {"name": "impedance_growth", "label": "Impedance growth", "direction": "minimize", "unit": "%"},
        ],
        "metadata": {"template_id": "generic_tabular_doe", "workspace_id": "battery-demo", "workspace_name": "Battery Demo"},
    }


def list_projects(workspace_id: str | None = None) -> list[dict[str, str]]:
    if workspace_id:
        db_projects = list_workspace_projects(workspace_id)
        if db_projects is not None:
            return db_projects

    projects: list[dict[str, str]] = []
    seen: set[str] = set()
    if (REAL_REFERENCE_ARTIFACT_DIR / "schema.json").exists():
        try:
            schema = _read_json(REAL_REFERENCE_ARTIFACT_DIR / "schema.json")
            project_id = str(schema.get("project_id") or REAL_FUEL_CELL_PROJECT_ID)
            seen.add(project_id)
            display_name = schema.get("display_name", project_id)
            projects.append({"id": project_id, "display_name": display_name, **_workspace_from_payload(project_id, display_name, schema)})
        except Exception as exc:  # noqa: BLE001 - malformed projects should not break discovery.
            logger.warning("Skipping invalid reference project schema at %s: %s", REAL_REFERENCE_ARTIFACT_DIR, exc)

    if BATTERY_DEMO_PROJECT_ID not in seen:
        battery_schema = _battery_placeholder_schema()
        projects.append(
            {
                "id": BATTERY_DEMO_PROJECT_ID,
                "display_name": battery_schema["display_name"],
                "workspace_id": "battery-demo",
                "workspace_name": "Battery Demo",
            }
        )
        seen.add(BATTERY_DEMO_PROJECT_ID)

    for session in list_ingestion_sessions():
        project_id = str(session.get("project_id") or "")
        if not project_id or project_id in seen:
            continue
        seen.add(project_id)
        project_metadata = read_project_metadata(project_id) or {}
        display_name = f"{project_metadata.get('display_name') or session.get('project_name') or project_id} · Uploaded"
        workspace = _workspace_from_payload(project_id, display_name, project_metadata or session)
        projects.append(
            {
                "id": project_id,
                "display_name": display_name,
                **workspace,
            }
        )
    if workspace_id:
        return [project for project in projects if project.get("workspace_id") == workspace_id]
    return projects


def is_packaged_project(project_id: str) -> bool:
    return project_id == REAL_FUEL_CELL_PROJECT_ID


def _latest_ingestion_project(project_id: str) -> dict | None:
    sessions = [session for session in list_ingestion_sessions() if session.get("project_id") == project_id]
    if not sessions:
        return None
    return sorted(sessions, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)[0]


def _latest_ingestion_artifact_dir(project_id: str) -> Path | None:
    session = _latest_ingestion_project(project_id)
    if not session:
        return None
    workspace = session_workspace(str(session["project_id"]), str(session["dataset_id"]), str(session["ingestion_session_id"]))
    artifact_dir = workspace["training_latest"]
    return artifact_dir if artifact_dir.exists() else None


def _best_model_name(artifact_dir: Path) -> str:
    metrics_path = artifact_dir / "metrics_summary.json"
    if metrics_path.exists():
        metrics = _read_json(metrics_path)
        best_model = metrics.get("best_model_name") or metrics.get("best_model")
        if best_model:
            return str(best_model)
    return "mlp"


def _mlflow_alias_model_name(project_id: str, alias: str = "challenger") -> str | None:
    if not is_mlflow_project(project_id):
        return None
    try:
        from mlflow.tracking import MlflowClient

        client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
        version = client.get_model_version_by_alias(registered_model_name_for_project(project_id), alias)
        if getattr(version, "tags", None) and version.tags.get("model_name"):
            return str(version.tags["model_name"])
        if version.run_id:
            run = client.get_run(version.run_id)
            model_name = run.data.tags.get("model_name") or run.data.params.get("model_name")
            if model_name:
                return str(model_name)
    except Exception as exc:  # noqa: BLE001 - local artifact fallback remains available.
        logger.info("Could not resolve MLflow %s model_name for %s: %s", alias, project_id, exc)
    return None


@lru_cache(maxsize=32)
def get_project_schema(project_id: str) -> dict:
    try:
        project_dir = _reference_project_dir(project_id)
        schema_path = project_dir / "schema.json"
        schema = _read_json(schema_path)
        workspace = _workspace_from_payload(project_id, schema.get("display_name", project_id), schema)
        schema["workspace_id"] = schema.get("workspace_id") or workspace["workspace_id"]
        schema["workspace_name"] = schema.get("workspace_name") or workspace["workspace_name"]
        return attach_domain_metadata(schema, template_id=infer_template_id(schema), approval_status="approved")
    except ProjectNotFoundError:
        if project_id == BATTERY_DEMO_PROJECT_ID:
            schema = _battery_placeholder_schema()
            return attach_domain_metadata(schema, template_id="generic_tabular_doe", approval_status="pending_bootstrap")
        session = _latest_ingestion_project(project_id)
        if not session:
            raise
        base_schema_path = REAL_REFERENCE_ARTIFACT_DIR / "schema.json"
        if not base_schema_path.exists():
            raise ProjectNotFoundError(f"Base fuel-cell schema not found for intake project_id: {project_id}")
        artifact_dir = _latest_ingestion_artifact_dir(project_id)
        schema_path = artifact_dir / "schema.json" if artifact_dir is not None else None
        schema = _read_json(schema_path) if schema_path and schema_path.exists() else _read_json(base_schema_path)
        schema["project_id"] = project_id
        schema["display_name"] = f"{session.get('project_name') or project_id} · Uploaded"
        project_metadata = read_project_metadata(project_id) or {}
        workspace = _workspace_from_payload(project_id, schema["display_name"], project_metadata or session)
        schema["workspace_id"] = workspace["workspace_id"]
        schema["workspace_name"] = workspace["workspace_name"]
        schema["source_project_id"] = schema.get("source_project_id") or REAL_FUEL_CELL_PROJECT_ID
        schema["ingestion_session"] = {
            "dataset_id": session.get("dataset_id"),
            "ingestion_session_id": session.get("ingestion_session_id"),
            "status": session.get("status"),
            "approval_status": session.get("approval_status"),
        }
        metadata_status = read_status(project_id, str(session["dataset_id"]), str(session["ingestion_session_id"]), "domain_metadata", default={})
        approved = metadata_status if isinstance(metadata_status, dict) and metadata_status.get("approval_status") == "approved" else None
        if approved and isinstance(approved.get("domain_metadata"), dict):
            schema["domain_metadata"] = approved["domain_metadata"]
            return apply_variable_metadata_to_schema(schema)
        return attach_domain_metadata(schema, template_id=infer_template_id(schema), approval_status="approved")


@lru_cache(maxsize=32)
def get_project_metadata(project_id: str) -> dict:
    artifact_dir = _latest_ingestion_artifact_dir(project_id)
    if artifact_dir is not None:
        metadata_path = artifact_dir / "metadata.json"
        best_model = _best_model_name(artifact_dir)
        if metadata_path.exists():
            metadata = _read_json(metadata_path)
            metadata["project_id"] = project_id
            metadata["model_version"] = f"{project_id}_{best_model}_challenger"
            return metadata
        return {"project_id": project_id, "model_version": f"{project_id}_{best_model}_challenger"}
    project_dir = _reference_project_dir(project_id)
    metadata_path = project_dir / "metadata.json"
    if not metadata_path.exists():
        return {"project_id": project_id, "model_version": f"{project_id}_mlflow_alias"}
    return _read_json(metadata_path)


@lru_cache(maxsize=32)
def get_project_preprocessing(project_id: str) -> dict:
    artifact_dir = _latest_ingestion_artifact_dir(project_id)
    if artifact_dir is not None:
        preprocessing_path = artifact_dir / "preprocessing.json"
        if not preprocessing_path.exists():
            raise FileNotFoundError(f"Preprocessing artifact not found for project_id: {project_id}")
        return _read_json(preprocessing_path)
    project_dir = _reference_project_dir(project_id)
    preprocessing_path = project_dir / "preprocessing.json"
    if not preprocessing_path.exists():
        raise FileNotFoundError(f"Preprocessing artifact not found for project_id: {project_id}")
    return _read_json(preprocessing_path)


def get_project_model_path(project_id: str) -> Path:
    artifact_dir = _latest_ingestion_artifact_dir(project_id)
    if is_mlflow_project(project_id) and os.getenv("DOE_DISABLE_MLFLOW_MODEL_LOADING", "").lower() not in {"1", "true", "yes"}:
        try:
            return download_production_onnx(project_id)
        except Exception as exc:  # noqa: BLE001 - fall back to object-store runtime state with explicit logging.
            logger.warning("Could not resolve MLflow aliased model for %s: %s", project_id, exc)

    if artifact_dir is not None:
        schema_path = artifact_dir / "schema.json"
        schema = _read_json(schema_path) if schema_path.exists() else {}
        template_id = schema.get("metadata", {}).get("template_id") if isinstance(schema.get("metadata"), dict) else None
        # Generic MVP models keep joblib for every candidate and additionally export
        # ONNX for the selected MLP. Prefer ONNX only when that selected model is the
        # generic MLP; linear/ridge candidates remain joblib artifacts.
        if template_id == "generic_tabular_doe":
            challenger_model = _mlflow_alias_model_name(project_id, "challenger")
            best_model = challenger_model or _best_model_name(artifact_dir)
            onnx_path = artifact_dir / "models" / f"{best_model}.onnx"
            if best_model == "mlp" and onnx_path.exists():
                return onnx_path
            joblib_path = artifact_dir / "models" / f"{best_model}.joblib"
            if joblib_path.exists():
                return joblib_path

    artifact_dir = artifact_dir or _latest_ingestion_artifact_dir(project_id)
    if artifact_dir is not None:
        best_model = _best_model_name(artifact_dir)
        model_path = artifact_dir / "models" / best_model / "model.onnx"
        if model_path.exists():
            return model_path
        joblib_path = artifact_dir / "models" / f"{best_model}.joblib"
        if joblib_path.exists():
            return joblib_path
        fallback_path = artifact_dir / "model.onnx"
        if fallback_path.exists():
            return fallback_path
        raise FileNotFoundError(f"Model artifact not found for project_id: {project_id}")

    raise FileNotFoundError(f"Model artifact not found for project_id: {project_id}; MLflow alias or local training artifact is required")


def clear_registry_cache() -> None:
    get_project_schema.cache_clear()
    get_project_metadata.cache_clear()
    get_project_preprocessing.cache_clear()
