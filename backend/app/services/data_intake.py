from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4
from fastapi import UploadFile

from .control_plane import ensure_project_record, get_project_storage_config, record_artifact_object, record_uploaded_dataset
from .db import postgres_control_plane_enabled
from .lifecycle_artifacts import latest_manifest_key, persist_session_artifact_set, public_artifact_persistence_summary, read_workspace_artifact_bytes
from .workspace_storage import WorkspaceStorageConfig, local_object_storage_root, object_storage_backend, object_storage_bucket, object_storage_uri, put_workspace_object, workspace_s3_config_from_env, workspace_scoped_path
from .workspaces import ensure_workspace, workspace_id_for_name


BACKEND_ROOT = Path(__file__).resolve().parents[2]
OBJECT_STORE_ROOT = local_object_storage_root()
DATA_INTAKE_ROOT = OBJECT_STORE_ROOT / "intake"
PROJECT_METADATA_FILENAME = "project.json"
_SAFE_PERSISTED_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "uploaded_project"


def _legacy_session_dir(project_id: str, dataset_id: str, session_id: str) -> Path:
    return DATA_INTAKE_ROOT / "projects" / project_id / "datasets" / dataset_id / "ingestion_sessions" / session_id


def _project_workspace_id(project_id: str) -> str:
    for metadata_path in OBJECT_STORE_ROOT.glob(f"workspaces/*/intake/projects/{project_id}/{PROJECT_METADATA_FILENAME}"):
        metadata = _read_json(metadata_path, default={}) or {}
        workspace_id = metadata.get("workspace_id")
        if workspace_id:
            return str(workspace_id)
    legacy_metadata = _read_json(DATA_INTAKE_ROOT / "projects" / project_id / PROJECT_METADATA_FILENAME, default={}) or {}
    if legacy_metadata.get("workspace_id"):
        return str(legacy_metadata["workspace_id"])
    lowered = project_id.lower()
    if "pem" in lowered or "fuel_cell" in lowered or "fuel-cell" in lowered:
        return "fraunhofer"
    return "mirai-engineering"


def _session_dir(project_id: str, dataset_id: str, session_id: str) -> Path:
    scoped = workspace_scoped_path(
        OBJECT_STORE_ROOT,
        _project_workspace_id(project_id),
        "intake",
        "projects",
        project_id,
        "datasets",
        dataset_id,
        "ingestion_sessions",
        session_id,
    )
    if scoped.exists() or not _legacy_session_dir(project_id, dataset_id, session_id).exists():
        return scoped
    return _legacy_session_dir(project_id, dataset_id, session_id)


def session_dir(project_id: str, dataset_id: str, session_id: str) -> Path:
    return _session_dir(project_id, dataset_id, session_id)


def session_workspace(project_id: str, dataset_id: str, session_id: str) -> dict[str, Path]:
    root = _session_dir(project_id, dataset_id, session_id)
    return {
        "root": root,
        "raw": root / "raw",
        "extracted": root / "extracted",
        "canonical": root / "canonical",
        "training_artifacts": root / "training_artifacts",
        "training_latest": root / "training_artifacts" / "latest",
        "runs": root / "runs",
        "inventory": root / "inventory",
        "eda": root / "eda",
        "status": root / "status",
        "training_requests": root / "training_requests",
    }


def ensure_session_workspace(project_id: str, dataset_id: str, session_id: str) -> dict[str, Path]:
    workspace = session_workspace(project_id, dataset_id, session_id)
    for path in workspace.values():
        path.mkdir(parents=True, exist_ok=True)
    return workspace


def session_status_path(project_id: str, dataset_id: str, session_id: str, name: str) -> Path:
    return session_workspace(project_id, dataset_id, session_id)["status"] / f"{name}.json"


def write_status(project_id: str, dataset_id: str, session_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload = {"updated_at": _now(), **payload}
    return _write_json(session_status_path(project_id, dataset_id, session_id, name), payload)


def read_status(project_id: str, dataset_id: str, session_id: str, name: str, default: Any = None) -> Any:
    return _read_json(session_status_path(project_id, dataset_id, session_id, name), default=default)


def reset_workspace_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file_sha256(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_filename(filename: str) -> str:
    name = Path(filename or "uploaded_file").name
    return re.sub(r"[^a-zA-Z0-9._ -]+", "_", name).strip() or "uploaded_file"


async def _store_upload(upload: UploadFile, raw_dir: Path, *, storage_config: WorkspaceStorageConfig | None = None, object_key_prefix: str | None = None) -> dict[str, Any]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(upload.filename or "uploaded_file")
    target = raw_dir / filename
    stem = target.stem
    suffix = target.suffix
    counter = 1
    while target.exists():
        target = raw_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    sha256 = hashlib.sha256()
    size_bytes = 0
    with target.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            size_bytes += len(chunk)
            sha256.update(chunk)
            handle.write(chunk)

    file_metadata: dict[str, Any] = {
        "filename": target.name,
        "original_filename": upload.filename,
        "relative_path": str(target.relative_to(OBJECT_STORE_ROOT)),
        "content_type": upload.content_type or "application/octet-stream",
        "size_bytes": size_bytes,
        "sha256": sha256.hexdigest(),
        "suffix": target.suffix.lower(),
    }
    if storage_config and object_key_prefix:
        object_key = f"{object_key_prefix.rstrip('/')}/{target.name}"
        with target.open("rb") as handle:
            stored_key = put_workspace_object(storage_config, object_key, handle, content_type=file_metadata["content_type"])
        file_metadata.update(
            {
                "bucket": storage_config.bucket,
                "object_key": stored_key,
                "object_uri": f"s3://{storage_config.bucket}/{stored_key}" if storage_config.mode == "s3" else object_storage_uri(storage_config.bucket or "", stored_key),
                "storage_provider": storage_config.mode,
            }
        )
    return file_metadata


def _manifest_dictionary_presence(files: list[dict[str, Any]]) -> dict[str, bool]:
    names = {str(file.get("filename", "")).lower() for file in files}
    has_manifest = "mirai_manifest.json" in names
    has_dictionary = "data_dictionary.csv" in names
    has_model_table = "model_table.csv" in names
    has_experiments = "experiments.csv" in names
    has_conditions = "conditions.csv" in names
    has_results = "results.csv" in names
    has_fixed_source_tables = has_experiments and has_conditions and has_results
    has_zip_package = any(name.endswith(".zip") for name in names)
    return {
        "has_manifest": has_manifest,
        "has_data_dictionary": has_dictionary,
        "has_model_table": has_model_table,
        "has_experiments": has_experiments,
        "has_conditions": has_conditions,
        "has_results": has_results,
        "has_fixed_source_tables": has_fixed_source_tables,
        "has_zip_package": has_zip_package,
    }


def _infer_session_status(files: list[dict[str, Any]]) -> str:
    presence = _manifest_dictionary_presence(files)
    if presence["has_zip_package"] or (presence["has_manifest"] and presence["has_data_dictionary"] and (presence["has_model_table"] or presence["has_fixed_source_tables"])):
        return "ready_for_contract_review"
    return "blocked_missing_mirai_contract"


def _project_dir(project_id: str) -> Path:
    return workspace_scoped_path(OBJECT_STORE_ROOT, _project_workspace_id(project_id), "intake", "projects", project_id)


def project_metadata_path(project_id: str) -> Path:
    return _project_dir(project_id) / PROJECT_METADATA_FILENAME


def read_project_metadata(project_id: str) -> dict[str, Any] | None:
    return _read_json(project_metadata_path(project_id), default=None)


def upsert_project_metadata(
    *,
    project_id: str,
    project_name: str,
    workspace_name: str | None,
    ingestion_path: str = "generic_tabular_doe",
    workspace_id: str | None = None,
) -> dict[str, Any]:
    workspace = ensure_workspace(workspace_name or workspace_id or "Default workspace")
    resolved_workspace_id = workspace_id or str(workspace.get("workspace_id") or workspace_id_for_name(workspace_name))
    existing = read_project_metadata(project_id) or {}
    payload = {
        **existing,
        "project_id": project_id,
        "display_name": project_name or existing.get("display_name") or project_id,
        "workspace_id": resolved_workspace_id,
        "workspace_name": str(workspace.get("display_name") or workspace_name or resolved_workspace_id or "Default workspace"),
        "template_id": existing.get("template_id") or "generic_tabular_doe",
        "lifecycle_contract": "generic_tabular_doe",
        "status": existing.get("status") or "active",
        "created_at": existing.get("created_at") or _now(),
        "updated_at": _now(),
    }
    return _write_json(project_metadata_path(project_id), payload)


def _build_session_payload(
    project_name: str,
    project_id: str,
    dataset_id: str,
    session_id: str,
    files: list[dict[str, Any]],
    notes: str | None = None,
    ingestion_path: str = "generic_tabular_doe",
    workspace_name: str | None = None,
    workspace_id: str | None = None,
    storage_config: WorkspaceStorageConfig | None = None,
) -> dict[str, Any]:
    status = _infer_session_status(files)
    session_path = _session_dir(project_id, dataset_id, session_id)
    project_metadata = upsert_project_metadata(project_id=project_id, project_name=project_name, workspace_name=workspace_name, ingestion_path=ingestion_path, workspace_id=workspace_id)
    return {
        "project_id": project_id,
        "project_name": project_name,
        "workspace_id": project_metadata.get("workspace_id"),
        "workspace_name": project_metadata.get("workspace_name") or workspace_name or "Default workspace",
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "status": status,
        "approval_status": "not_ready",
        "created_at": _now(),
        "updated_at": _now(),
        "storage": {
            "provider": storage_config.mode if storage_config else "local_filesystem",
            "bucket": storage_config.bucket if storage_config else None,
            "prefix": storage_config.normalized_prefix if storage_config else None,
            "root": str(session_path.relative_to(BACKEND_ROOT)),
            "raw_dir": str((session_path / "raw").relative_to(BACKEND_ROOT)),
        },
        "files": files,
        "notes": notes or "",
        "ingestion_path": "generic_tabular_doe",
        "lifecycle_contract": "generic_tabular_doe",
        "mapping": {
            "state": "ready_for_mirai_admin_review" if status == "ready_for_contract_review" else "blocked_missing_required_contract",
            "message": "A Mirai package requires mirai_manifest.json, data_dictionary.csv, and either model_table.csv or the fixed source tables experiments.csv, conditions.csv, and results.csv (or a ZIP containing that package). Mirai admins must approve roles, dtypes, units, bounds, joins, split hints, and output directions before preprocessing.",
            "contract": _manifest_dictionary_presence(files),
        },
        "manifest_assistant": {
            "status": "placeholder_not_active",
            "message": "Future Pi may draft suggestions later, but the Mirai contract is mandatory and no autonomous mapping is applied in the MVP.",
        },
    }


async def create_ingestion_session(
    project_name: str,
    uploads: list[UploadFile],
    notes: str | None = None,
    ingestion_path: str = "generic_tabular_doe",
    workspace_name: str | None = None,
    existing_project_id: str | None = None,
    workspace_id: str | None = None,
    uploaded_by: str | None = None,
) -> dict[str, Any]:
    if not uploads:
        raise ValueError("At least one file must be uploaded")
    ingestion_path = "generic_tabular_doe"
    if existing_project_id:
        if _slugify(existing_project_id) != existing_project_id:
            raise ValueError("existing_project_id must be a safe project identifier")
        project_id = existing_project_id
    else:
        project_id = f"{_slugify(project_name)}_{uuid4().hex[:8]}"
    upsert_project_metadata(project_id=project_id, project_name=project_name, workspace_name=workspace_name, ingestion_path=ingestion_path, workspace_id=workspace_id)
    storage_config = None
    if workspace_id and postgres_control_plane_enabled():
        storage_config = ensure_project_record(
            workspace_id=workspace_id,
            project_id=project_id,
            display_name=project_name,
            workspace_name=workspace_name or workspace_id,
            clerk_user_id=uploaded_by or workspace_id,
        )
    dataset_id = f"dataset_{uuid4().hex[:10]}"
    session_id = f"ing_{uuid4().hex[:10]}"
    session_path = _session_dir(project_id, dataset_id, session_id)
    raw_dir = session_path / "raw"
    object_key_prefix = f"{storage_config.normalized_prefix}/raw/{dataset_id}" if storage_config else None
    files = [await _store_upload(upload, raw_dir, storage_config=storage_config, object_key_prefix=object_key_prefix) for upload in uploads]
    payload = _build_session_payload(project_name, project_id, dataset_id, session_id, files, notes, ingestion_path, workspace_name, workspace_id=workspace_id, storage_config=storage_config)
    _write_json(session_path / "session.json", payload)
    _write_json(session_path / "inventory" / "file_inventory.json", {"files": files, "generated_at": _now()})
    session_metadata_persistence = persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=str(payload.get("workspace_id") or workspace_id or ""),
        artifact_set="session_metadata",
        local_dir_or_files={
            "session.json": session_path / "session.json",
            "inventory/file_inventory.json": session_path / "inventory" / "file_inventory.json",
        },
        storage_config=storage_config,
    )
    payload.setdefault("object_storage", {})["session_metadata"] = public_artifact_persistence_summary(session_metadata_persistence)
    _write_json(session_path / "session.json", payload)
    if workspace_id and files:
        primary_file = files[0]
        primary_uri = str(primary_file.get("object_uri") or primary_file.get("relative_path"))
        record_uploaded_dataset(
            workspace_id=workspace_id,
            project_id=project_id,
            dataset_id=dataset_id,
            filename=str(primary_file.get("filename") or "uploaded_file"),
            object_uri=primary_uri,
            sha256=primary_file.get("sha256"),
            size_bytes=primary_file.get("size_bytes"),
            uploaded_by=uploaded_by,
            metadata={"ingestion_session_id": session_id, "files": files},
        )
        for file_metadata in files:
            record_artifact_object(
                workspace_id=workspace_id,
                project_id=project_id,
                artifact_kind="raw_upload",
                object_uri=str(file_metadata.get("object_uri") or file_metadata.get("relative_path")),
                sha256=file_metadata.get("sha256"),
                size_bytes=file_metadata.get("size_bytes"),
                metadata={"dataset_id": dataset_id, "ingestion_session_id": session_id, "filename": file_metadata.get("filename")},
            )
    return payload


async def append_ingestion_files(project_id: str, dataset_id: str, session_id: str, uploads: list[UploadFile]) -> dict[str, Any]:
    if not uploads:
        raise ValueError("At least one file must be uploaded")
    session = get_ingestion_session(project_id, dataset_id, session_id)
    if session.get("status") in {"approved_for_training", "training_running", "training_complete"}:
        raise ValueError("Cannot append files after training approval/execution; create a new ingestion session instead")
    session_path = _session_dir(project_id, dataset_id, session_id)
    workspace_id = session.get("workspace_id")
    storage_config = get_project_storage_config(str(workspace_id), project_id) if workspace_id else None
    object_key_prefix = f"{storage_config.normalized_prefix}/raw/{dataset_id}" if storage_config else None
    new_files = [await _store_upload(upload, session_path / "raw", storage_config=storage_config, object_key_prefix=object_key_prefix) for upload in uploads]
    files = [*session.get("files", []), *new_files]
    session["files"] = files
    session["status"] = _infer_session_status(files)
    session["approval_status"] = "not_ready"
    session["updated_at"] = _now()
    session["mapping"] = {
        "state": "ready_for_mirai_admin_review" if session["status"] == "ready_for_contract_review" else "blocked_missing_required_contract",
        "message": "Files changed. A Mirai package requires mirai_manifest.json, data_dictionary.csv, and either model_table.csv or fixed source tables experiments.csv, conditions.csv, and results.csv (or a ZIP containing that package), and Mirai admins must reconfirm roles, units, dtypes, joins, split hints, and target outputs before preprocessing.",
        "contract": _manifest_dictionary_presence(files),
    }
    _write_json(session_path / "session.json", session)
    _write_json(session_path / "inventory" / "file_inventory.json", {"files": files, "generated_at": _now(), "appended_files": new_files})
    session_metadata_persistence = persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=str(workspace_id or ""),
        artifact_set="session_metadata",
        local_dir_or_files={
            "session.json": session_path / "session.json",
            "inventory/file_inventory.json": session_path / "inventory" / "file_inventory.json",
        },
        storage_config=storage_config,
    )
    session.setdefault("object_storage", {})["session_metadata"] = public_artifact_persistence_summary(session_metadata_persistence)
    _write_json(session_path / "session.json", session)
    if workspace_id:
        for file_metadata in new_files:
            record_artifact_object(
                workspace_id=str(workspace_id),
                project_id=project_id,
                artifact_kind="raw_upload",
                object_uri=str(file_metadata.get("object_uri") or file_metadata.get("relative_path")),
                sha256=file_metadata.get("sha256"),
                size_bytes=file_metadata.get("size_bytes"),
                metadata={"dataset_id": dataset_id, "ingestion_session_id": session_id, "filename": file_metadata.get("filename"), "appended": True},
            )
    # File additions invalidate previously generated preprocessing/training statuses.
    status_dir = session_path / "status"
    for status_file in status_dir.glob("*.json") if status_dir.exists() else []:
        status_file.unlink()
    return session


def get_ingestion_session(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    session = _read_json(_session_dir(project_id, dataset_id, session_id) / "session.json")
    if not session:
        raise FileNotFoundError("Ingestion session not found")
    return session


def _project_storage_config(workspace_id: str, project_id: str) -> WorkspaceStorageConfig:
    runtime_config = get_project_storage_config(workspace_id, project_id)
    if runtime_config is not None:
        return runtime_config
    if object_storage_backend() == "s3":
        return workspace_s3_config_from_env(workspace_id, prefix=f"workspaces/{workspace_id}/projects/{project_id}")
    bucket = object_storage_bucket(required=False) or f"mirai-{workspace_id}-local"
    return WorkspaceStorageConfig(
        workspace_id=workspace_id,
        mode="local",
        bucket=bucket,
        prefix=f"workspaces/{workspace_id}/projects/{project_id}",
    )


def _safe_persisted_identifier(value: Any) -> str | None:
    text = str(value or "")
    return text if _SAFE_PERSISTED_ID.fullmatch(text) else None


def restore_latest_persisted_ingestion_session(project_id: str, workspace_id: str | None) -> dict[str, Any] | None:
    """Restore the latest durable project session into local cache.

    This is intentionally project-scoped and server-side scoped: callers provide
    only the authenticated workspace and selected project id. Object keys are
    derived from the resolved workspace storage config plus the latest manifest;
    frontend-supplied keys/paths are never accepted.
    """

    if not workspace_id:
        return None
    project_id = _safe_persisted_identifier(project_id) or ""
    workspace_id = _safe_persisted_identifier(workspace_id) or ""
    if not project_id or not workspace_id:
        return None
    try:
        storage_config = _project_storage_config(workspace_id, project_id)
        latest = json.loads(read_workspace_artifact_bytes(storage_config, latest_manifest_key(storage_config)).decode("utf-8"))
        if str(latest.get("project_id") or "") != project_id:
            return None
        dataset_id = _safe_persisted_identifier(latest.get("dataset_id"))
        session_id = _safe_persisted_identifier(latest.get("session_id"))
        if not dataset_id or not session_id:
            return None
        session_key = f"{storage_config.normalized_prefix}/intake/{dataset_id}/{session_id}/session.json"
        session = json.loads(read_workspace_artifact_bytes(storage_config, session_key).decode("utf-8"))
        if str(session.get("project_id") or "") != project_id:
            return None
        if str(session.get("dataset_id") or "") != dataset_id or str(session.get("ingestion_session_id") or "") != session_id:
            return None
        if str(session.get("workspace_id") or workspace_id) != workspace_id:
            return None

        upsert_project_metadata(
            project_id=project_id,
            project_name=str(session.get("project_name") or project_id),
            workspace_name=str(session.get("workspace_name") or workspace_id),
            ingestion_path=str(session.get("ingestion_path") or "generic_tabular_doe"),
            workspace_id=workspace_id,
        )
        workspace = ensure_session_workspace(project_id, dataset_id, session_id)
        _write_json(workspace["root"] / "session.json", session)
        try:
            inventory_key = f"{storage_config.normalized_prefix}/intake/{dataset_id}/{session_id}/inventory/file_inventory.json"
            inventory = json.loads(read_workspace_artifact_bytes(storage_config, inventory_key).decode("utf-8"))
            _write_json(workspace["inventory"] / "file_inventory.json", inventory)
        except Exception:  # noqa: BLE001 - session restoration remains useful without inventory cache.
            pass
        return session
    except Exception:  # noqa: BLE001 - absence of persisted state should behave like no sessions.
        return None


def list_ingestion_sessions(project_id: str | None = None, workspace_id: str | None = None, *, restore_latest: bool = True) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    roots = [DATA_INTAKE_ROOT / "projects", *OBJECT_STORE_ROOT.glob("workspaces/*/intake/projects")]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*/datasets/*/ingestion_sessions/*/session.json"), reverse=True):
            session = _read_json(path, default=None)
            if session:
                sessions.append(session)
    if workspace_id:
        sessions = [session for session in sessions if session.get("workspace_id") == workspace_id]
    if project_id:
        sessions = [session for session in sessions if session.get("project_id") == project_id]
    if not sessions and project_id and restore_latest:
        restored = restore_latest_persisted_ingestion_session(project_id, workspace_id)
        if restored:
            sessions = [restored]
    return sessions


def _public_file_metadata(file_metadata: dict[str, Any]) -> dict[str, Any]:
    allowed = {"filename", "original_filename", "content_type", "size_bytes", "sha256", "suffix", "storage_provider"}
    return {key: value for key, value in file_metadata.items() if key in allowed and value is not None}


def public_ingestion_session(session: dict[str, Any]) -> dict[str, Any]:
    public = dict(session)
    storage = session.get("storage") if isinstance(session.get("storage"), dict) else {}
    public["storage"] = {"provider": storage.get("provider") or "object_storage", "durable": bool(session.get("object_storage"))}
    public["files"] = [_public_file_metadata(item) for item in session.get("files", []) if isinstance(item, dict)]
    if "object_storage" in public:
        public["object_storage"] = public_artifact_persistence_summary(public["object_storage"])
    return public


def public_file_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    public = dict(inventory)
    public["files"] = [_public_file_metadata(item) for item in inventory.get("files", []) if isinstance(item, dict)]
    return public


def get_file_inventory(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    session_path = _session_dir(project_id, dataset_id, session_id)
    inventory = _read_json(session_path / "inventory" / "file_inventory.json")
    if not inventory:
        session = get_ingestion_session(project_id, dataset_id, session_id)
        inventory = {"files": session.get("files", []), "generated_at": session.get("updated_at")}
    return inventory
