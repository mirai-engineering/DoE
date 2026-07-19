from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, Path
import mimetypes
import os
import re
from typing import BinaryIO, Iterable
from urllib.parse import urlparse


BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOCAL_OBJECT_STORAGE_ROOT = BACKEND_ROOT / ".object-storage-local"


_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class WorkspaceStorageError(ValueError):
    pass


def _production_storage_required() -> bool:
    return (
        os.getenv("RAILWAY_ENVIRONMENT") is not None
        or os.getenv("RAILWAY_SERVICE_NAME") is not None
        or os.getenv("MIRAI_REQUIRE_S3_OBJECT_STORAGE", "").strip().lower() in {"1", "true", "yes", "on"}
    )


def object_storage_backend() -> str:
    """Return the configured object-storage backend.

    `local` is for developer mirrors/caches under `LOCAL_OBJECT_STORAGE_ROOT`.
    `s3` is mandatory in Railway/production. Legacy `DOE_OBJECT_STORE_ROOT`
    remains supported only as a local-root override during local development.
    """

    configured = os.getenv("OBJECT_STORAGE_BACKEND")
    if _production_storage_required() and (configured or "").strip().lower() != "s3":
        raise WorkspaceStorageError("OBJECT_STORAGE_BACKEND=s3 is required in Railway/production")
    backend = (configured or "local").strip().lower() or "local"
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


def object_storage_bucket(*, required: bool = True) -> str | None:
    """Return the bucket configured for local-training object-key resolution."""

    bucket = os.getenv("OBJECT_STORAGE_BUCKET") or os.getenv("MIRAI_OBJECT_STORAGE_BUCKET")
    if bucket:
        return bucket.strip()
    if required:
        raise WorkspaceStorageError("Missing OBJECT_STORAGE_BUCKET for object-key data loading")
    return None


def _validate_bucket_name(bucket: str) -> str:
    if not bucket or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", bucket):
        raise WorkspaceStorageError(f"Unsafe object-storage bucket: {bucket!r}")
    return bucket


def validate_object_key(object_key: str) -> str:
    """Validate a relative object-store key and return its normalized POSIX form.

    Unlike workspace-specific validation, this helper is bucket-level and only
    rejects absolute paths, traversal, and empty keys. Callers that need
    workspace confinement should use validate_workspace_object_key instead.
    """

    key_path = PurePosixPath(object_key)
    _reject_unsafe_posix_parts(key_path, original=object_key)
    key = key_path.as_posix().strip("/")
    if not key:
        raise WorkspaceStorageError("Object key cannot be empty")
    return key


def local_object_storage_path(bucket: str, object_key: str) -> Path:
    """Resolve a bucket/object key into the gitignored local mirror path.

    The logical key after the bucket is identical to the S3 key, e.g.:
      backend/.object-storage-local/<bucket>/workspaces/.../model_table.csv
      s3://<bucket>/workspaces/.../model_table.csv
    """

    bucket_name = _validate_bucket_name(bucket)
    key = validate_object_key(object_key)
    root = local_object_storage_root().resolve()
    path = (root / bucket_name / Path(*PurePosixPath(key).parts)).resolve()
    bucket_root = (root / bucket_name).resolve()
    if bucket_root not in [path, *path.parents]:
        raise WorkspaceStorageError("Resolved local object path escapes bucket mirror root")
    return path


def object_storage_uri(bucket: str, object_key: str) -> str:
    """Return the URI/path for the configured object-storage backend."""

    bucket_name = _validate_bucket_name(bucket)
    key = validate_object_key(object_key)
    if object_storage_backend() == "s3":
        return f"s3://{bucket_name}/{key}"
    return str(local_object_storage_path(bucket_name, key))


def _generic_s3_client():
    try:
        import boto3  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency/runtime guard
        raise WorkspaceStorageError("S3 operations require boto3") from exc
    endpoint = os.getenv("S3_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL") or os.getenv("MLFLOW_S3_ENDPOINT_URL")
    access_key = os.getenv("S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("S3_REGION") or os.getenv("AWS_DEFAULT_REGION") or os.getenv("MIRAI_S3_REGION") or "auto"
    if not endpoint or not access_key or not secret_key:
        raise WorkspaceStorageError("Missing S3_ENDPOINT_URL/S3_ACCESS_KEY_ID/S3_SECRET_ACCESS_KEY for S3 object loading")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def read_object_storage_bytes(bucket: str, object_key: str) -> bytes:
    """Read an object from the configured local mirror or S3 backend."""

    bucket_name = _validate_bucket_name(bucket)
    key = validate_object_key(object_key)
    if object_storage_backend() == "s3":
        response = _generic_s3_client().get_object(Bucket=bucket_name, Key=key)
        return response["Body"].read()
    path = local_object_storage_path(bucket_name, key)
    if not path.exists():
        raise WorkspaceStorageError(f"Local object mirror file does not exist: {path}")
    return path.read_bytes()


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
    raw_parts = [part for part in str(original).replace("\\", "/").split("/") if part]
    if not str(original).strip() or path.is_absolute() or ".." in path.parts or ".." in raw_parts:
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
    if endpoint and access_key and secret_key:
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
    # Railway demo buckets often share one S3 credential set. Fall back to the
    # generic S3 env vars after validating the workspace/project key prefix.
    return _generic_s3_client()


def put_workspace_object(config: WorkspaceStorageConfig, object_key: str, body: bytes | BinaryIO, *, content_type: str | None = None) -> str:
    key = validate_workspace_object_key(config, object_key)
    if config.mode == "local":
        if not config.bucket:
            raise WorkspaceStorageError("Local workspace object writes require a bucket/mirror name")
        path = local_object_storage_path(config.bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(body, "read"):
            with path.open("wb") as handle:
                while chunk := body.read(1024 * 1024):
                    handle.write(chunk)
        else:
            path.write_bytes(body)
        return key
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


def upload_workspace_directory_tree(
    config: WorkspaceStorageConfig,
    source_dir: Path | str,
    object_key_prefix: str,
    *,
    exclude_names: Iterable[str] = (),
    max_files: int = 500,
    max_bytes: int = 250 * 1024 * 1024,
) -> dict:
    """Upload a bounded local directory tree under a validated workspace prefix.

    The helper centralizes path validation for project-scoped artifact uploads.
    It refuses absolute/traversing object keys through validate_workspace_object_key,
    skips caller-supplied raw/reference directory names, and enforces simple file
    and byte limits so accidental raw data trees are not uploaded as model/EDA
    artifacts.
    """

    root = Path(source_dir).resolve()
    if not root.exists() or not root.is_dir():
        raise WorkspaceStorageError(f"Source directory does not exist: {source_dir}")
    prefix = validate_workspace_object_key(config, object_key_prefix).rstrip("/")
    excluded = {str(name) for name in exclude_names}
    candidates: list[Path] = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        relative_path = path.relative_to(root)
        if any(part in excluded for part in relative_path.parts):
            continue
        if path.is_symlink():
            raise WorkspaceStorageError(f"Directory upload rejects symlinks: {path}")
        if not path.is_file():
            continue
        resolved = path.resolve()
        if root not in [resolved, *resolved.parents]:
            raise WorkspaceStorageError(f"Directory upload file escapes source root: {path}")
        candidates.append(path)
        total_bytes += path.stat().st_size
        if len(candidates) > max_files:
            raise WorkspaceStorageError(f"Directory upload exceeds max_files={max_files}: {root}")
        if total_bytes > max_bytes:
            raise WorkspaceStorageError(f"Directory upload exceeds max_bytes={max_bytes}: {root}")

    uploaded: list[dict] = []
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        key = validate_workspace_object_key(config, f"{prefix}/{relative}")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as handle:
            put_workspace_object(config, key, handle, content_type=content_type)
        uploaded.append({"key": key, "size_bytes": path.stat().st_size})
    return {"status": "uploaded", "prefix": prefix + "/", "count": len(uploaded), "total_bytes": total_bytes, "objects": uploaded[:50]}


def get_workspace_object(config: WorkspaceStorageConfig, object_key: str) -> bytes:
    key = validate_workspace_object_key(config, object_key)
    if config.mode == "local":
        if not config.bucket:
            raise WorkspaceStorageError("Local workspace object reads require a bucket/mirror name")
        return read_object_storage_bytes(config.bucket, key)
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
