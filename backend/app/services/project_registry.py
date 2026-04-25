from functools import lru_cache
import json
import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = Path(os.getenv("DOE_ARTIFACTS_DIR", BACKEND_ROOT / "artifacts"))


class ProjectNotFoundError(LookupError):
    pass


def _safe_project_id(project_id: str) -> str:
    if not project_id or "/" in project_id or "\\" in project_id or ".." in project_id:
        raise ProjectNotFoundError(f"Unknown project_id: {project_id}")
    return project_id


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_project_dir(project_id: str) -> Path:
    safe_project_id = _safe_project_id(project_id)
    project_dir = ARTIFACTS_DIR / safe_project_id
    if not project_dir.exists():
        raise ProjectNotFoundError(f"Unknown project_id: {project_id}")
    return project_dir


def list_projects() -> list[dict[str, str]]:
    if not ARTIFACTS_DIR.exists():
        return []

    projects: list[dict[str, str]] = []
    for schema_path in sorted(ARTIFACTS_DIR.glob("*/schema.json")):
        try:
            schema = _read_json(schema_path)
            project_id = schema.get("project_id") or schema_path.parent.name
            projects.append(
                {
                    "id": project_id,
                    "display_name": schema.get("display_name", project_id),
                }
            )
        except Exception as exc:  # noqa: BLE001 - malformed projects should not break discovery.
            logger.warning("Skipping invalid project schema at %s: %s", schema_path, exc)
    return projects


@lru_cache(maxsize=32)
def get_project_schema(project_id: str) -> dict:
    project_dir = get_project_dir(project_id)
    schema_path = project_dir / "schema.json"
    if not schema_path.exists():
        raise ProjectNotFoundError(f"Project schema not found for project_id: {project_id}")
    return _read_json(schema_path)


@lru_cache(maxsize=32)
def get_project_metadata(project_id: str) -> dict:
    project_dir = get_project_dir(project_id)
    metadata_path = project_dir / "metadata.json"
    if not metadata_path.exists():
        return {}
    return _read_json(metadata_path)


@lru_cache(maxsize=32)
def get_project_preprocessing(project_id: str) -> dict:
    project_dir = get_project_dir(project_id)
    preprocessing_path = project_dir / "preprocessing.json"
    if not preprocessing_path.exists():
        raise FileNotFoundError(f"Preprocessing artifact not found for project_id: {project_id}")
    return _read_json(preprocessing_path)


def get_project_model_path(project_id: str) -> Path:
    project_dir = get_project_dir(project_id)
    model_path = project_dir / "model.onnx"
    if not model_path.exists():
        raise FileNotFoundError(f"ONNX model artifact not found for project_id: {project_id}")
    return model_path


def clear_registry_cache() -> None:
    get_project_schema.cache_clear()
    get_project_metadata.cache_clear()
    get_project_preprocessing.cache_clear()
