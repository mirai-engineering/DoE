from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Mapping

from .control_plane import get_project_storage_config, record_artifact_object
from .db import postgres_control_plane_required
from .workspace_storage import (
    WorkspaceStorageConfig,
    WorkspaceStorageError,
    get_workspace_object,
    object_storage_backend,
    object_storage_bucket,
    object_storage_uri,
    put_workspace_object,
    validate_workspace_object_key,
    workspace_s3_config_from_env,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


LIFECYCLE_ARTIFACT_SETS: dict[str, dict[str, Any]] = {
    "session_metadata": {
        "prefix": "intake",
        "artifact_kind": "intake_session_metadata",
        "files": ("session.json", "inventory/file_inventory.json"),
    },
    "canonical": {
        "prefix": "canonical",
        "artifact_kind": "canonical_artifact",
        "files": ("model_table.csv", "rejected_rows.csv", "dataset_profile.json"),
    },
    "preprocessing_artifacts": {
        "prefix": "preprocessing",
        "artifact_kind": "preprocessing_artifact",
        "files": ("schema.json", "preprocessing.json", "split_report.json", "validation_report.json", "eda_report.json", "dataset_profile.json", "upload_preprocessing_report.json"),
    },
    "eda": {
        "prefix": "eda",
        "artifact_kind": "eda_artifact",
        "files": ("preprocessing_report.json", "ydata_profile.html", "ydata_profile.json"),
    },
    "status": {
        "prefix": "status",
        "artifact_kind": "status_artifact",
        "files": ("preprocessing.json", "domain_metadata.json", "ml_preprocessing.json"),
    },
    "ml_preprocessing": {
        "prefix": "ml_preprocessing",
        "artifact_kind": "ml_preprocessing_artifact",
        "files": (
            "plans/current/ml_preprocessing_plan.schema.json",
            "plans/current/preprocessing_plan.json",
            "plans/current/preprocessing_plan_report.json",
            "plans/current/ml_preprocessing_report.md",
            "runs/current/ml_preprocessing_fitted.schema.json",
            "runs/current/ml_preprocessing_report.schema.json",
            "runs/current/preprocessing_fitted.json",
            "runs/current/feature_map.json",
            "runs/current/target_map.json",
            "runs/current/ml_preprocessing_report.json",
            "runs/current/ml_preprocessing_report.md",
            "runs/current/model_table_preprocessed.csv",
            "runs/current/model_table_preprocessed_manifest.json",
        ),
    },
}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_uri(config: WorkspaceStorageConfig, key: str) -> str:
    if config.mode == "s3" and config.bucket:
        return f"s3://{config.bucket}/{key}"
    if config.bucket:
        return object_storage_uri(config.bucket, key)
    return key


def _resolve_storage_config(workspace_id: str, project_id: str, storage_config: WorkspaceStorageConfig | None = None) -> WorkspaceStorageConfig:
    if storage_config is not None:
        return storage_config
    runtime_config = get_project_storage_config(workspace_id, project_id)
    if runtime_config is not None:
        return runtime_config
    backend = object_storage_backend()
    if backend == "s3":
        return workspace_s3_config_from_env(workspace_id, prefix=f"workspaces/{workspace_id}/projects/{project_id}")
    bucket = object_storage_bucket(required=False) or f"mirai-{workspace_id}-local"
    return WorkspaceStorageConfig(
        workspace_id=workspace_id,
        mode="local",
        bucket=bucket,
        prefix=f"workspaces/{workspace_id}/projects/{project_id}",
    )


def session_artifact_prefix(config: WorkspaceStorageConfig, artifact_set: str, dataset_id: str, session_id: str) -> str:
    definition = LIFECYCLE_ARTIFACT_SETS.get(artifact_set)
    if not definition:
        raise ValueError(f"Unknown lifecycle artifact set: {artifact_set}")
    return validate_workspace_object_key(config, f"{config.normalized_prefix}/{definition['prefix']}/{dataset_id}/{session_id}")


def manifest_prefix(config: WorkspaceStorageConfig, dataset_id: str, session_id: str) -> str:
    return validate_workspace_object_key(config, f"{config.normalized_prefix}/manifests/{dataset_id}/{session_id}")


def latest_manifest_key(config: WorkspaceStorageConfig) -> str:
    return validate_workspace_object_key(config, f"{config.normalized_prefix}/latest/artifact_manifest.json")


def _iter_named_files(local_dir_or_files: Path | Mapping[str, Path], *, artifact_set: str) -> list[tuple[str, Path]]:
    definition = LIFECYCLE_ARTIFACT_SETS[artifact_set]
    allowed_files = set(definition.get("files") or ())
    excluded_parts = {"raw", "raw_reference_extracted", "01-Data", "extracted", "__pycache__"}
    if isinstance(local_dir_or_files, Mapping):
        return [
            (name, path)
            for name, path in local_dir_or_files.items()
            if name in allowed_files and path.exists() and path.is_file()
        ]
    root = Path(local_dir_or_files)
    if not root.exists() or not root.is_dir():
        return []
    files: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        relative_name = path.relative_to(root).as_posix()
        if any(part in excluded_parts for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            raise WorkspaceStorageError(f"Artifact persistence rejects symlinks: {path}")
        if path.is_file() and relative_name in allowed_files:
            files.append((relative_name, path))
    return files


def public_artifact_persistence_summary(value: Any) -> Any:
    """Strip raw object keys/URIs/prefixes from API-facing persistence metadata."""

    if isinstance(value, list):
        return [public_artifact_persistence_summary(item) for item in value]
    if not isinstance(value, dict):
        return value
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"object_key", "object_uri", "prefix", "manifest_object_key", "manifest_object_uri"}:
            continue
        if key == "manifest" and isinstance(item, dict):
            sanitized[key] = {"available": bool(item.get("object_key") or item.get("object_uri")), "status": item.get("status", "available")}
            continue
        if key == "objects" and isinstance(item, list):
            sanitized[key] = [
                {
                    "name": str(obj.get("name")),
                    "content_type": obj.get("content_type"),
                    "size_bytes": obj.get("size_bytes"),
                    "sha256": obj.get("sha256"),
                    "available": True,
                }
                for obj in item
                if isinstance(obj, dict)
            ]
            continue
        sanitized[key] = public_artifact_persistence_summary(item)
    return sanitized


def persist_session_artifact_set(
    *,
    project_id: str,
    dataset_id: str,
    session_id: str,
    workspace_id: str | None,
    artifact_set: str,
    local_dir_or_files: Path | Mapping[str, Path],
    storage_config: WorkspaceStorageConfig | None = None,
    write_latest_pointer: bool = True,
) -> dict[str, Any]:
    """Persist one generated lifecycle artifact set to workspace object storage.

    Local filesystem remains a cache. The returned manifest is safe for service
    payloads: it exposes availability and friendly metadata while keeping object
    keys available for internal hydration.
    """

    if not workspace_id:
        return {"status": "skipped", "reason": "missing_workspace_id", "artifact_set": artifact_set}
    definition = LIFECYCLE_ARTIFACT_SETS.get(artifact_set)
    if not definition:
        raise ValueError(f"Unknown lifecycle artifact set: {artifact_set}")
    files = _iter_named_files(local_dir_or_files, artifact_set=artifact_set)
    if not files:
        return {"status": "skipped", "reason": "no_local_files", "artifact_set": artifact_set}
    try:
        config = _resolve_storage_config(str(workspace_id), project_id, storage_config)
        prefix = session_artifact_prefix(config, artifact_set, dataset_id, session_id)
        objects: list[dict[str, Any]] = []
        for relative_name, path in files:
            object_key = validate_workspace_object_key(config, f"{prefix}/{relative_name}")
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            with path.open("rb") as handle:
                put_workspace_object(config, object_key, handle, content_type=content_type)
            sha256 = _file_sha256(path)
            size_bytes = path.stat().st_size
            uri = _object_uri(config, object_key)
            object_record = {
                "name": relative_name,
                "object_key": object_key,
                "object_uri": uri,
                "content_type": content_type,
                "sha256": sha256,
                "size_bytes": size_bytes,
            }
            objects.append(object_record)
            record_artifact_object(
                workspace_id=str(workspace_id),
                project_id=project_id,
                artifact_kind=str(definition["artifact_kind"]),
                object_uri=uri,
                sha256=sha256,
                size_bytes=size_bytes,
                metadata={
                    "dataset_id": dataset_id,
                    "ingestion_session_id": session_id,
                    "artifact_set": artifact_set,
                    "name": relative_name,
                    "object_key": object_key,
                    "content_type": content_type,
                },
            )
        manifest = {
            "status": "uploaded",
            "workspace_id": str(workspace_id),
            "project_id": project_id,
            "dataset_id": dataset_id,
            "session_id": session_id,
            "artifact_set": artifact_set,
            "artifact_kind": definition["artifact_kind"],
            "prefix": prefix + "/",
            "generated_at": _now(),
            "count": len(objects),
            "total_bytes": sum(int(item["size_bytes"]) for item in objects),
            "objects": objects,
        }
        manifest_key = validate_workspace_object_key(config, f"{manifest_prefix(config, dataset_id, session_id)}/artifact_manifest.{artifact_set}.json")
        put_workspace_object(config, manifest_key, (json.dumps(manifest, indent=2, allow_nan=False) + "\n").encode("utf-8"), content_type="application/json")
        manifest["manifest"] = {"object_key": manifest_key, "object_uri": _object_uri(config, manifest_key)}
        if write_latest_pointer:
            pointer = {
                "status": "available",
                "project_id": project_id,
                "dataset_id": dataset_id,
                "session_id": session_id,
                "updated_at": _now(),
                "artifact_set": artifact_set,
                "manifest_object_key": manifest_key,
                "manifest_object_uri": manifest["manifest"]["object_uri"],
            }
            put_workspace_object(config, latest_manifest_key(config), (json.dumps(pointer, indent=2, allow_nan=False) + "\n").encode("utf-8"), content_type="application/json")
        return manifest
    except Exception as exc:  # noqa: BLE001 - local/dev can continue without durable storage.
        if postgres_control_plane_required():
            raise
        return {"status": "skipped", "reason": str(exc), "artifact_set": artifact_set, "workspace_id": workspace_id, "project_id": project_id}


def persist_multiple_artifact_sets(
    *,
    project_id: str,
    dataset_id: str,
    session_id: str,
    workspace_id: str | None,
    artifact_sets: Mapping[str, Path | Mapping[str, Path]],
    storage_config: WorkspaceStorageConfig | None = None,
) -> dict[str, Any]:
    layouts = []
    for artifact_set, local_files in artifact_sets.items():
        layouts.append(
            persist_session_artifact_set(
                project_id=project_id,
                dataset_id=dataset_id,
                session_id=session_id,
                workspace_id=workspace_id,
                artifact_set=artifact_set,
                local_dir_or_files=local_files,
                storage_config=storage_config,
                write_latest_pointer=False,
            )
        )
    combined = {
        "status": "uploaded" if any(item.get("status") == "uploaded" for item in layouts) else "skipped",
        "workspace_id": workspace_id,
        "project_id": project_id,
        "dataset_id": dataset_id,
        "session_id": session_id,
        "generated_at": _now(),
        "layouts": layouts,
        "count": sum(int(item.get("count", 0)) for item in layouts),
    }
    if workspace_id and combined["status"] == "uploaded":
        try:
            config = _resolve_storage_config(str(workspace_id), project_id, storage_config)
            combined_key = validate_workspace_object_key(config, f"{manifest_prefix(config, dataset_id, session_id)}/artifact_manifest.json")
            put_workspace_object(config, combined_key, (json.dumps(combined, indent=2, allow_nan=False) + "\n").encode("utf-8"), content_type="application/json")
            combined["manifest"] = {"object_key": combined_key, "object_uri": _object_uri(config, combined_key)}
            pointer = {
                "status": "available",
                "project_id": project_id,
                "dataset_id": dataset_id,
                "session_id": session_id,
                "updated_at": _now(),
                "manifest_object_key": combined_key,
                "manifest_object_uri": combined["manifest"]["object_uri"],
            }
            put_workspace_object(config, latest_manifest_key(config), (json.dumps(pointer, indent=2, allow_nan=False) + "\n").encode("utf-8"), content_type="application/json")
        except Exception as exc:  # noqa: BLE001 - preserve successful per-file uploads.
            if postgres_control_plane_required():
                raise
            combined["manifest"] = {"status": "skipped", "reason": str(exc)}
    return combined


def find_manifest_object(manifest: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    for item in (manifest or {}).get("objects", []):
        if item.get("name") == name:
            return item
    return None


def read_workspace_artifact_bytes(config: WorkspaceStorageConfig, object_key: str) -> bytes:
    return get_workspace_object(config, validate_workspace_object_key(config, object_key))
