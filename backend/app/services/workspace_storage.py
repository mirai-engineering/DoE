from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, Path
import os
import re
from typing import BinaryIO
from urllib.parse import urlparse


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCAL_OBJECT_STORAGE_ROOT = BACKEND_ROOT / ".object-storage-local"


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class WorkspaceStorageError(ValueError):
    pass


def object_storage_backend() -> str:
    """Return the configured object-storage backend.

    `local` is for developer mirrors/caches under `LOCAL_OBJECT_STORAGE_ROOT`.
    `s3` is for Railway/production object storage. Legacy `DOE_OBJECT_STORE_ROOT`
    remains supported only as a local-root override during migration.
    """

    backend = os.getenv("OBJECT_STORAGE_BACKEND", "local").strip().lower() or "local"
    if backend not in {"local", "s3"}:
        raise WorkspaceStorageError(f"Unsupported OBJECT_STORAGE_BACKEND: {backend!r}")
    return backend


def local_object_storage_root() -> Path:
    """Filesystem root for local object-storage mirrors/caches.

    Prefer the explicit `LOCAL_OBJECT_STORAGE_ROOT`. `DOE_OBJECT_STORE_ROOT` is
    accepted as a deprecated backward-compatible alias so existing local scripts
    can migrate gradually.
    """

    configured = os.getenv("LOCAL_OBJECT_STORAGE_ROOT") or os.getenv("DOE_OBJECT_STORE_ROOT")
    return Path(configured).expanduser() if configured else DEFAULT_LOCAL_OBJECT_STORAGE_ROOT


def seed_object_storage_root() -> Path:
    """Tracked tiny seed object metadata, not runtime object-store state."""

    return BACKEND_ROOT / "seeds" / "object_storage"


@dataclass(frozen=True)
class WorkspaceStorageConfig:
    """Storage contract for one workspace.

    `mode="local"` keeps the existing filesystem resolver behavior.
    `mode="s3"` validates object pointers against a configured bucket and
    workspace-scoped prefix such as `workspaces/fraunhofer`.
    """

    workspace_id: str
    mode: str = "local"
    bucket: str | None = None
    prefix: str | None = None

    def __post_init__(self) -> None:
        validate_workspace_id(self.workspace_id)
        if self.mode not in {"local", "s3"}:
            raise WorkspaceStorageError(f"Unsupported workspace storage mode: {self.mode!r}")
        if self.mode == "s3" and not self.bucket:
            raise WorkspaceStorageError("S3 workspace storage requires a bucket")

    @property
    def normalized_prefix(self) -> str:
        prefix = self.prefix or f"workspaces/{self.workspace_id}"
        return validate_object_key_prefix(prefix, self.workspace_id)


def validate_workspace_id(workspace_id: str) -> str:
    if not workspace_id or not _SAFE_SEGMENT.fullmatch(workspace_id):
        raise WorkspaceStorageError(f"Unsafe workspace_id: {workspace_id!r}")
    return workspace_id


def _reject_unsafe_posix_parts(path: PurePosixPath | Path, *, original: str) -> None:
    if path.is_absolute() or ".." in path.parts:
        raise WorkspaceStorageError(f"Unsafe storage path segment: {original}")


def validate_object_key_prefix(prefix: str, workspace_id: str) -> str:
    workspace = validate_workspace_id(workspace_id)
    path = PurePosixPath(prefix)
    _reject_unsafe_posix_parts(path, original=prefix)
    normalized = path.as_posix().strip("/")
    allowed = f"workspaces/{workspace}"
    if normalized != allowed and not normalized.startswith(f"{allowed}/"):
        raise WorkspaceStorageError(
            f"Storage prefix for workspace {workspace!r} must be under {allowed!r}: {prefix!r}"
        )
    return normalized


def workspace_root(object_store_root: Path, workspace_id: str) -> Path:
    workspace = validate_workspace_id(workspace_id)
    return (object_store_root / "workspaces" / workspace).resolve()


def workspace_scoped_path(object_store_root: Path, workspace_id: str, *parts: str | Path) -> Path:
    root = workspace_root(object_store_root, workspace_id)
    if not parts:
        raise WorkspaceStorageError("Workspace-scoped paths require at least one relative part")

    candidate = root
    for part in parts:
        path_part = Path(part)
        if path_part.is_absolute() or ".." in path_part.parts:
            raise WorkspaceStorageError(f"Unsafe storage path segment: {part!s}")
        candidate = candidate / path_part

    resolved = candidate.resolve()
    if root not in [resolved, *resolved.parents]:
        raise WorkspaceStorageError("Storage path escapes workspace root")
    return resolved


def assert_same_workspace_path(object_store_root: Path, workspace_id: str, path: Path) -> Path:
    root = workspace_root(object_store_root, workspace_id)
    resolved = path.resolve()
    if root not in [resolved, *resolved.parents]:
        raise WorkspaceStorageError(f"Path is not under workspace root {workspace_id!r}: {path}")
    return resolved


def validate_workspace_object_key(config: WorkspaceStorageConfig, object_key: str) -> str:
    """Validate a relative object-store key and return its normalized form."""

    key_path = PurePosixPath(object_key)
    _reject_unsafe_posix_parts(key_path, original=object_key)
    key = key_path.as_posix().strip("/")
    if not key:
        raise WorkspaceStorageError("Object key cannot be empty")

    prefix = config.normalized_prefix
    if key != prefix and not key.startswith(f"{prefix}/"):
        raise WorkspaceStorageError(
            f"Object key is not under workspace prefix {prefix!r}: {object_key!r}"
        )
    return key


def workspace_env_prefix(workspace_id: str) -> str:
    normalized = validate_workspace_id(workspace_id).upper().replace("-", "_")
    return f"MIRAI_{normalized}_S3"


def workspace_s3_config_from_env(workspace_id: str, *, prefix: str | None = None) -> WorkspaceStorageConfig:
    env_prefix = workspace_env_prefix(workspace_id)
    bucket = os.getenv(f"{env_prefix}_BUCKET")
    if not bucket:
        raise WorkspaceStorageError(f"Missing S3 bucket env var for workspace {workspace_id!r}: {env_prefix}_BUCKET")
    return WorkspaceStorageConfig(
        workspace_id=workspace_id,
        mode="s3",
        bucket=bucket,
        prefix=prefix or f"workspaces/{workspace_id}",
    )


def _workspace_s3_client(config: WorkspaceStorageConfig):
    if config.mode != "s3":
        raise WorkspaceStorageError("S3 client requires mode='s3'")
    try:
        import boto3  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency/runtime guard
        raise WorkspaceStorageError("S3 operations require boto3") from exc
    env_prefix = workspace_env_prefix(config.workspace_id)
    endpoint = os.getenv(f"{env_prefix}_ENDPOINT")
    access_key = os.getenv(f"{env_prefix}_ACCESS_KEY_ID")
    secret_key = os.getenv(f"{env_prefix}_SECRET_ACCESS_KEY")
    region = os.getenv(f"{env_prefix}_REGION", os.getenv("MIRAI_S3_REGION", "sjc"))
    if not endpoint or not access_key or not secret_key:
        raise WorkspaceStorageError(f"Missing S3 endpoint/access env vars for workspace {config.workspace_id!r}")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def put_workspace_object(config: WorkspaceStorageConfig, object_key: str, body: bytes | BinaryIO, *, content_type: str | None = None) -> str:
    key = validate_workspace_object_key(config, object_key)
    client = _workspace_s3_client(config)
    extra_args = {"ContentType": content_type} if content_type else None
    if hasattr(body, "read"):
        client.upload_fileobj(body, config.bucket, key, ExtraArgs=extra_args or {})
    else:
        kwargs = {"Bucket": config.bucket, "Key": key, "Body": body}
        if extra_args:
            kwargs.update(extra_args)
        client.put_object(**kwargs)
    return key


def get_workspace_object(config: WorkspaceStorageConfig, object_key: str) -> bytes:
    key = validate_workspace_object_key(config, object_key)
    client = _workspace_s3_client(config)
    response = client.get_object(Bucket=config.bucket, Key=key)
    return response["Body"].read()


def list_workspace_objects(config: WorkspaceStorageConfig, prefix: str | None = None) -> list[dict]:
    key_prefix = validate_workspace_object_key(config, prefix or config.normalized_prefix)
    client = _workspace_s3_client(config)
    paginator = client.get_paginator("list_objects_v2")
    objects: list[dict] = []
    for page in paginator.paginate(Bucket=config.bucket, Prefix=key_prefix):
        for item in page.get("Contents", []):
            objects.append({"key": item["Key"], "size_bytes": item.get("Size"), "last_modified": item.get("LastModified")})
    return objects


def validate_workspace_object_uri(config: WorkspaceStorageConfig, object_uri: str) -> str:
    """Validate a workspace-scoped object pointer.

    In S3 mode this accepts either a relative object key under the configured
    workspace prefix or an `s3://bucket/key` URI for the configured bucket.
    It returns the normalized object key. Local filesystem absolute paths are
    deliberately rejected here; use `workspace_scoped_path` for local paths.
    """

    if not object_uri:
        raise WorkspaceStorageError("Object URI cannot be empty")

    parsed = urlparse(object_uri)
    if parsed.scheme and parsed.scheme != "s3":
        raise WorkspaceStorageError(f"Unsupported object URI scheme: {parsed.scheme!r}")
    if parsed.scheme == "s3":
        if config.mode != "s3":
            raise WorkspaceStorageError("S3 object URI cannot be used with local workspace storage")
        if parsed.netloc != config.bucket:
            raise WorkspaceStorageError(
                f"Object URI bucket {parsed.netloc!r} does not match workspace bucket {config.bucket!r}"
            )
        return validate_workspace_object_key(config, parsed.path.lstrip("/"))

    # Treat schemeless values as object keys, not filesystem paths.
    if Path(object_uri).is_absolute():
        raise WorkspaceStorageError("Absolute filesystem paths are not valid object pointers")
    return validate_workspace_object_key(config, object_uri)
