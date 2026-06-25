from functools import lru_cache
import json
import logging
import os
from pathlib import Path

from .control_plane import get_project_runtime_state, list_workspace_projects
from .data_intake import list_ingestion_sessions, read_project_metadata, read_status, session_workspace
from .domain_metadata import apply_variable_metadata_to_schema, attach_domain_metadata, infer_template_id
from .mlflow_registry import download_aliased_run_artifacts, download_production_onnx, download_run_artifacts, is_mlflow_project, loaded_champion_mlflow_import, registered_model_name_for_project, tracking_uri
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


def _list_mlflow_registered_projects(workspace_id: str | None = None) -> list[dict[str, str]]:
    try:
        from mlflow.tracking import MlflowClient

        client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
        projects: list[dict[str, str]] = []
        for registered_model in client.search_registered_models():
            name = str(registered_model.name)
            if not name.startswith("doe_surrogate_"):
                continue
            project_id = name.removeprefix("doe_surrogate_")
            run_workspace_id = None
            display_name = project_id
            try:
                version = client.get_model_version_by_alias(name, "challenger")
                if version.run_id:
                    run = client.get_run(version.run_id)
                    run_workspace_id = run.data.tags.get("workspace_id") or run.data.params.get("workspace_id")
                    training_request_id = run.data.tags.get("training_request_id") or run.data.params.get("training_request_id")
                    if training_request_id == "train_req_smoke" or "smoke" in project_id.lower():
                        continue
                    display_name = run.data.tags.get("project_display_name") or run.data.params.get("project_display_name") or display_name
            except Exception:
                pass
            if workspace_id and run_workspace_id and run_workspace_id != workspace_id:
                continue
            if workspace_id and not run_workspace_id:
                continue
            workspace = _workspace_from_payload(project_id, display_name, {"workspace_id": run_workspace_id or workspace_id or "fraunhofer"})
            projects.append({"id": project_id, "display_name": f"{display_name} · MLflow", **workspace})
        return projects
    except Exception as exc:  # noqa: BLE001 - project listing must not fail if MLflow is unavailable.
        logger.info("Could not list MLflow registered projects: %s", exc)
        return []


def list_projects(workspace_id: str | None = None) -> list[dict[str, str]]:
    projects: list[dict[str, str]] = []
    seen: set[str] = set()
    if workspace_id:
        db_projects = list_workspace_projects(workspace_id)
        if db_projects is not None:
            projects.extend(db_projects)
            seen.update(str(project.get("id")) for project in db_projects if project.get("id"))
    if (REAL_REFERENCE_ARTIFACT_DIR / "schema.json").exists():
        try:
            schema = _read_json(REAL_REFERENCE_ARTIFACT_DIR / "schema.json")
            project_id = str(schema.get("project_id") or REAL_FUEL_CELL_PROJECT_ID)
            display_name = schema.get("display_name", project_id)
            if project_id not in seen:
                seen.add(project_id)
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
    for mlflow_project in _list_mlflow_registered_projects(workspace_id):
        project_id = str(mlflow_project.get("id") or "")
        if project_id and project_id not in seen:
            seen.add(project_id)
            projects.append(mlflow_project)
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


def _imported_mlflow_artifact_dir(project_id: str, workspace_id: str | None, *, champion_only: bool = False, include_predictions: bool = False) -> Path | None:
    if not workspace_id or not is_mlflow_project(project_id):
        return None
    try:
        mlflow_import = loaded_champion_mlflow_import(project_id, workspace_id)
        run_id = mlflow_import.get("run_id") if isinstance(mlflow_import, dict) else None
        if run_id:
            return download_run_artifacts(project_id, str(run_id), include_quality=True, include_predictions=include_predictions)
    except Exception as exc:  # noqa: BLE001 - local/reference fallbacks remain available only outside canonical runtime state.
        logger.info("Could not resolve loaded MLflow champion artifacts for %s: %s", project_id, exc)
    return None


def _latest_mlflow_artifact_dir(project_id: str) -> Path | None:
    if not is_mlflow_project(project_id):
        return None
    try:
        return download_aliased_run_artifacts(project_id, alias="challenger")
    except Exception as exc:  # noqa: BLE001 - local/reference fallbacks remain available.
        logger.info("Could not resolve MLflow run artifacts for %s: %s", project_id, exc)
        return None


def _latest_project_artifact_dir(project_id: str, workspace_id: str | None = None) -> Path | None:
    return _imported_mlflow_artifact_dir(project_id, workspace_id) or _latest_ingestion_artifact_dir(project_id) or (None if workspace_id else _latest_mlflow_artifact_dir(project_id))


def _has_runtime_project(workspace_id: str | None, project_id: str) -> bool:
    if not workspace_id:
        return False
    try:
        return bool(get_project_runtime_state(workspace_id, project_id))
    except Exception:
        return False


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


def _humanize_column_name(name: str) -> str:
    return name.replace("_", " ").strip().title() or name


def _runtime_variable(name: str, *, role: str, unit_map: dict) -> dict:
    payload = {
        "name": name,
        "label": _humanize_column_name(name),
        "ui_label": _humanize_column_name(name),
        "unit": str(unit_map.get(name) or ""),
        "role": role,
    }
    if role == "input":
        payload.update({"type": "continuous", "min": 0, "max": 1})
    if role == "output":
        payload.update({"direction": "maximize"})
    return payload


def _pending_runtime_schema(workspace_id: str, project_id: str, project: dict | None = None) -> dict:
    project = project or {}
    schema = {
        "project_id": project_id,
        "display_name": project.get("display_name") or project_id,
        "description": "Runtime project is waiting for preprocessing to produce an approved schema.",
        "schema_version": project.get("schema_version") or "pending-preprocessing",
        "allow_unknown_inputs": False,
        "inputs": [],
        "outputs": [],
        "workspace_id": workspace_id,
        "workspace_name": project.get("workspace_name") or workspace_id,
        "metadata": {
            "template_id": project.get("lifecycle_contract") or "generic_tabular_doe",
            "runtime_source": "postgres_control_plane",
            "schema_status": "pending_preprocessing",
        },
    }
    return attach_domain_metadata(schema, template_id="generic_tabular_doe", approval_status="pending_preprocessing")


def _schema_from_runtime_state(workspace_id: str, project_id: str) -> dict | None:
    runtime_state = get_project_runtime_state(workspace_id, project_id)
    if not runtime_state:
        return None
    project = runtime_state.get("project") or {}
    schema_manifest = runtime_state.get("schema_manifest") or {}
    schema_json = schema_manifest.get("schema_json") if isinstance(schema_manifest.get("schema_json"), dict) else {}
    if schema_json.get("inputs") and schema_json.get("outputs"):
        schema = dict(schema_json)
    else:
        input_columns = schema_manifest.get("input_columns") or []
        output_columns = schema_manifest.get("output_columns") or []
        if not input_columns and not output_columns:
            return _pending_runtime_schema(workspace_id, project_id, project)
        unit_map = schema_manifest.get("unit_map") or {}
        schema = {
            "project_id": project_id,
            "display_name": project.get("display_name") or project_id,
            "description": "Runtime project loaded from Railway/Postgres control-plane metadata.",
            "schema_version": project.get("schema_version") or schema_manifest.get("schema_id") or "runtime-control-plane",
            "allow_unknown_inputs": False,
            "inputs": [_runtime_variable(str(name), role="input", unit_map=unit_map) for name in input_columns],
            "outputs": [_runtime_variable(str(name), role="output", unit_map=unit_map) for name in output_columns],
            "metadata": {
                "template_id": project.get("lifecycle_contract") or "generic_tabular_doe",
                "runtime_source": "postgres_control_plane",
                "schema_manifest_id": schema_manifest.get("schema_id"),
            },
        }
    schema["project_id"] = project_id
    schema["display_name"] = schema.get("display_name") or project.get("display_name") or project_id
    schema["workspace_id"] = workspace_id
    schema["workspace_name"] = project.get("workspace_name") or workspace_id
    schema["schema_version"] = schema.get("schema_version") or project.get("schema_version") or "runtime-control-plane"
    schema.setdefault("metadata", {})
    if isinstance(schema["metadata"], dict):
        schema["metadata"].setdefault("template_id", project.get("lifecycle_contract") or "generic_tabular_doe")
        schema["metadata"].setdefault("runtime_source", "postgres_control_plane")
    return attach_domain_metadata(schema, template_id=infer_template_id(schema), approval_status="approved")


def _loaded_champion_schema(project_id: str, workspace_id: str | None) -> dict | None:
    artifact_dir = _imported_mlflow_artifact_dir(project_id, workspace_id, champion_only=True)
    schema_path = artifact_dir / "schema.json" if artifact_dir is not None else None
    if not schema_path or not schema_path.exists():
        return None
    schema = _read_json(schema_path)
    schema["project_id"] = project_id
    schema["workspace_id"] = workspace_id
    schema.setdefault("metadata", {})
    if isinstance(schema["metadata"], dict):
        schema["metadata"].setdefault("runtime_source", "loaded_mlflow_champion")
    return attach_domain_metadata(schema, template_id=infer_template_id(schema), approval_status="approved")


@lru_cache(maxsize=64)
def get_project_schema(project_id: str, workspace_id: str | None = None) -> dict:
    if workspace_id:
        champion_schema = _loaded_champion_schema(project_id, workspace_id)
        if champion_schema is not None:
            return champion_schema
        runtime_schema = _schema_from_runtime_state(workspace_id, project_id)
        if runtime_schema is not None:
            return runtime_schema
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
        artifact_dir = _latest_project_artifact_dir(project_id, workspace_id)
        if not session and artifact_dir is None:
            raise
        if workspace_id and _has_runtime_project(workspace_id, project_id):
            return _pending_runtime_schema(workspace_id, project_id, (get_project_runtime_state(workspace_id, project_id) or {}).get("project") or {})
        base_schema_path = REAL_REFERENCE_ARTIFACT_DIR / "schema.json"
        if not base_schema_path.exists() and artifact_dir is None:
            raise ProjectNotFoundError(f"Preprocessing schema is not available yet for intake project_id: {project_id}")
        schema_path = artifact_dir / "schema.json" if artifact_dir is not None else None
        schema = _read_json(schema_path) if schema_path and schema_path.exists() else _read_json(base_schema_path)
        schema["project_id"] = project_id
        schema["display_name"] = schema.get("display_name") or f"{session.get('project_name') if session else project_id} · Uploaded"
        project_metadata = read_project_metadata(project_id) or {}
        workspace = _workspace_from_payload(project_id, schema["display_name"], project_metadata or session or schema)
        schema["workspace_id"] = workspace["workspace_id"]
        schema["workspace_name"] = workspace["workspace_name"]
        schema["source_project_id"] = schema.get("source_project_id") or REAL_FUEL_CELL_PROJECT_ID
        if session:
            schema["ingestion_session"] = {
                "dataset_id": session.get("dataset_id"),
                "ingestion_session_id": session.get("ingestion_session_id"),
                "status": session.get("status"),
                "approval_status": session.get("approval_status"),
            }
        elif artifact_dir is not None:
            schema["ingestion_session"] = {"status": "external_training_package", "approval_status": "approved"}
        if session:
            metadata_status = read_status(project_id, str(session["dataset_id"]), str(session["ingestion_session_id"]), "domain_metadata", default={})
            approved = metadata_status if isinstance(metadata_status, dict) and metadata_status.get("approval_status") == "approved" else None
            if approved and isinstance(approved.get("domain_metadata"), dict):
                schema["domain_metadata"] = approved["domain_metadata"]
                return apply_variable_metadata_to_schema(schema)
        return attach_domain_metadata(schema, template_id=infer_template_id(schema), approval_status="approved")


@lru_cache(maxsize=32)
def get_project_metadata(project_id: str, workspace_id: str | None = None) -> dict:
    artifact_dir = _latest_project_artifact_dir(project_id, workspace_id)
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
def get_project_preprocessing(project_id: str, workspace_id: str | None = None) -> dict:
    artifact_dir = _latest_project_artifact_dir(project_id, workspace_id)
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


def get_project_model_path(project_id: str, workspace_id: str | None = None) -> Path:
    artifact_dir = _latest_project_artifact_dir(project_id, workspace_id)
    if is_mlflow_project(project_id) and os.getenv("DOE_DISABLE_MLFLOW_MODEL_LOADING", "").lower() not in {"1", "true", "yes"}:
        try:
            return download_production_onnx(project_id, workspace_id=workspace_id)
        except Exception as exc:  # noqa: BLE001 - runtime projects must not silently serve challenger/session artifacts.
            if _has_runtime_project(workspace_id, project_id):
                raise
            logger.warning("Could not resolve loaded MLflow champion for %s: %s", project_id, exc)

    if artifact_dir is not None:
        schema_path = artifact_dir / "schema.json"
        schema = _read_json(schema_path) if schema_path.exists() else {}
        template_id = schema.get("metadata", {}).get("template_id") if isinstance(schema.get("metadata"), dict) else None
        # Generic MVP models keep joblib for every candidate and additionally export
        # ONNX for the selected MLP. Prefer ONNX only when that selected model is the
        # generic MLP; linear/ridge candidates remain joblib artifacts.
        if template_id == "generic_tabular_doe":
            challenger_model = None if workspace_id else _mlflow_alias_model_name(project_id, "challenger")
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
