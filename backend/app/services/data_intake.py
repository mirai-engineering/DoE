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
from zipfile import BadZipFile, ZipFile

from fastapi import UploadFile

from .workspaces import ensure_workspace, workspace_id_for_name


BACKEND_ROOT = Path(__file__).resolve().parents[2]
OBJECT_STORE_ROOT = Path(os.getenv("DOE_OBJECT_STORE_ROOT", BACKEND_ROOT / "data-minio"))
DATA_INTAKE_ROOT = OBJECT_STORE_ROOT / "intake"
PROJECT_METADATA_FILENAME = "project.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "uploaded_project"


def _session_dir(project_id: str, dataset_id: str, session_id: str) -> Path:
    return DATA_INTAKE_ROOT / "projects" / project_id / "datasets" / dataset_id / "ingestion_sessions" / session_id


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


def _is_metadata_zip_member(name: str) -> bool:
    parts = Path(name).parts
    return not parts or parts[0] == "__MACOSX" or any(part == ".DS_Store" for part in parts) or Path(name).name.startswith("._")


def _safe_zip_target(root: Path, member_name: str) -> Path:
    normalized = Path(member_name)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"Unsafe zip member path: {member_name}")
    target = (root / normalized).resolve()
    root_resolved = root.resolve()
    if root_resolved not in [target, *target.parents]:
        raise ValueError(f"Zip member escapes extraction root: {member_name}")
    return target


def safe_extract_cell_zip(zip_path: Path, extract_root: Path) -> dict[str, Any]:
    match = re.fullmatch(r"Cell_(\d{2})\.zip", zip_path.name)
    if not match:
        raise ValueError(f"Expected Cell_NN.zip archive, got {zip_path.name}")
    cell_id = f"Cell_{match.group(1)}"
    data_root = extract_root / "01-Data"
    cell_root = data_root / cell_id
    extracted_files: list[dict[str, Any]] = []
    skipped_members: list[str] = []
    try:
        with ZipFile(zip_path) as archive:
            for member in archive.infolist():
                name = member.filename.replace("\\", "/")
                if member.is_dir() or _is_metadata_zip_member(name):
                    skipped_members.append(name)
                    continue
                parts = Path(name).parts
                relative = Path(*parts) if parts and parts[0] == cell_id else Path(cell_id) / Path(name)
                target = _safe_zip_target(data_root, str(relative))
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                extracted_files.append(
                    {
                        "path": str(target.relative_to(extract_root)),
                        "size_bytes": target.stat().st_size,
                        "sha256": _file_sha256(target),
                    }
                )
    except BadZipFile as exc:
        raise ValueError(f"Invalid zip archive: {zip_path.name}") from exc
    return {
        "archive": zip_path.name,
        "cell_id": cell_id,
        "target_dir": str(cell_root.relative_to(extract_root)),
        "file_count": len(extracted_files),
        "files": extracted_files,
        "skipped_member_count": len(skipped_members),
        "skipped_members_preview": skipped_members[:20],
    }


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


async def _store_upload(upload: UploadFile, raw_dir: Path) -> dict[str, Any]:
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

    return {
        "filename": target.name,
        "original_filename": upload.filename,
        "relative_path": str(target.relative_to(DATA_INTAKE_ROOT)),
        "content_type": upload.content_type or "application/octet-stream",
        "size_bytes": size_bytes,
        "sha256": sha256.hexdigest(),
        "suffix": target.suffix.lower(),
    }


def _manifest_dictionary_presence(files: list[dict[str, Any]]) -> dict[str, bool]:
    names = {str(file.get("filename", "")).lower() for file in files}
    has_manifest = any("manifest" in name and (name.endswith(".json") or name.endswith(".yml") or name.endswith(".yaml")) for name in names)
    has_dictionary = any("data_dictionary" in name and (name.endswith(".csv") or name.endswith(".xlsx") or name.endswith(".xls")) for name in names)
    return {"has_manifest": has_manifest, "has_data_dictionary": has_dictionary}


def _infer_session_status(files: list[dict[str, Any]]) -> str:
    presence = _manifest_dictionary_presence(files)
    if presence["has_manifest"] and presence["has_data_dictionary"]:
        return "ready_for_contract_review"
    return "blocked_missing_mirai_contract"


def _project_dir(project_id: str) -> Path:
    return DATA_INTAKE_ROOT / "projects" / project_id


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
) -> dict[str, Any]:
    workspace = ensure_workspace(workspace_name or "Default workspace")
    workspace_id = str(workspace.get("workspace_id") or workspace_id_for_name(workspace_name))
    existing = read_project_metadata(project_id) or {}
    payload = {
        **existing,
        "project_id": project_id,
        "display_name": project_name or existing.get("display_name") or project_id,
        "workspace_id": workspace_id,
        "workspace_name": str(workspace.get("display_name") or workspace_name or "Default workspace"),
        "template_id": existing.get("template_id") or "generic_tabular_doe",
        "raw_extractor": existing.get("raw_extractor") or ("pem_cell_zip_bundle" if ingestion_path == "pem_cell_zip_bundle" else None),
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
) -> dict[str, Any]:
    status = _infer_session_status(files)
    session_path = _session_dir(project_id, dataset_id, session_id)
    project_metadata = upsert_project_metadata(project_id=project_id, project_name=project_name, workspace_name=workspace_name, ingestion_path=ingestion_path)
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
            "provider": "local_filesystem",
            "root": str(session_path.relative_to(BACKEND_ROOT)),
            "raw_dir": str((session_path / "raw").relative_to(BACKEND_ROOT)),
        },
        "files": files,
        "notes": notes or "",
        "ingestion_path": ingestion_path,
        "mapping": {
            "state": "ready_for_mirai_admin_review" if status == "ready_for_contract_review" else "blocked_missing_required_contract",
            "message": "A Mirai manifest JSON and data_dictionary CSV/XLSX are required. Mirai admins must approve roles, dtypes, units, bounds, joins, split hints, and output directions before preprocessing.",
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
) -> dict[str, Any]:
    if not uploads:
        raise ValueError("At least one file must be uploaded")
    if existing_project_id:
        if _slugify(existing_project_id) != existing_project_id:
            raise ValueError("existing_project_id must be a safe project identifier")
        project_id = existing_project_id
    else:
        project_id = f"{_slugify(project_name)}_{uuid4().hex[:8]}"
    dataset_id = f"dataset_{uuid4().hex[:10]}"
    session_id = f"ing_{uuid4().hex[:10]}"
    session_path = _session_dir(project_id, dataset_id, session_id)
    raw_dir = session_path / "raw"
    files = [await _store_upload(upload, raw_dir) for upload in uploads]
    payload = _build_session_payload(project_name, project_id, dataset_id, session_id, files, notes, ingestion_path, workspace_name)
    _write_json(session_path / "session.json", payload)
    _write_json(session_path / "inventory" / "file_inventory.json", {"files": files, "generated_at": _now()})
    return payload


async def append_ingestion_files(project_id: str, dataset_id: str, session_id: str, uploads: list[UploadFile]) -> dict[str, Any]:
    if not uploads:
        raise ValueError("At least one file must be uploaded")
    session = get_ingestion_session(project_id, dataset_id, session_id)
    if session.get("status") in {"approved_for_training", "training_running", "training_complete"}:
        raise ValueError("Cannot append files after training approval/execution; create a new ingestion session instead")
    session_path = _session_dir(project_id, dataset_id, session_id)
    new_files = [await _store_upload(upload, session_path / "raw") for upload in uploads]
    files = [*session.get("files", []), *new_files]
    session["files"] = files
    session["status"] = _infer_session_status(files)
    session["approval_status"] = "not_ready"
    session["updated_at"] = _now()
    session["mapping"] = {
        "state": "ready_for_mirai_admin_review" if session["status"] == "ready_for_contract_review" else "blocked_missing_required_contract",
        "message": "Files changed. A Mirai manifest JSON and data_dictionary CSV/XLSX are required, and Mirai admins must reconfirm roles, units, dtypes, joins, split hints, and target outputs before preprocessing.",
        "contract": _manifest_dictionary_presence(files),
    }
    _write_json(session_path / "session.json", session)
    _write_json(session_path / "inventory" / "file_inventory.json", {"files": files, "generated_at": _now(), "appended_files": new_files})
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


def list_ingestion_sessions() -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    root = DATA_INTAKE_ROOT / "projects"
    if not root.exists():
        return []
    for path in sorted(root.glob("*/datasets/*/ingestion_sessions/*/session.json"), reverse=True):
        session = _read_json(path, default=None)
        if session:
            sessions.append(session)
    return sessions


def get_file_inventory(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    session_path = _session_dir(project_id, dataset_id, session_id)
    inventory = _read_json(session_path / "inventory" / "file_inventory.json")
    if not inventory:
        session = get_ingestion_session(project_id, dataset_id, session_id)
        inventory = {"files": session.get("files", []), "generated_at": session.get("updated_at")}
    return inventory
