from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

from app.services.platform.workspace_storage import (
    WorkspaceStorageError,
    local_object_storage_path,
    object_storage_backend,
    object_storage_bucket,
    object_storage_uri,
    read_object_storage_bytes,
    validate_object_key,
)


def _is_remote_tracking_uri(uri: str | None) -> bool:
    if not uri:
        return False
    parsed = urlparse(uri)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and host not in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check local-training data and Railway MLflow/S3 configuration without printing secrets.")
    parser.add_argument("--object-key", default=os.getenv("TRAINING_DATA_OBJECT_KEY"), help="Logical object key for model_table.csv")
    parser.add_argument("--bucket", default=None, help="Object-storage bucket. Defaults to OBJECT_STORAGE_BUCKET.")
    parser.add_argument("--read-check", action="store_true", help="Actually read the configured object and report byte count.")
    args = parser.parse_args()

    if not args.object_key:
        raise SystemExit("Missing --object-key or TRAINING_DATA_OBJECT_KEY")

    try:
        bucket = args.bucket or object_storage_bucket(required=True)
        assert bucket is not None
        key = validate_object_key(args.object_key)
        backend = object_storage_backend()
        source = object_storage_uri(bucket, key)
        tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
        require_remote_mlflow = _truthy("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW")
        require_remote_artifacts = _truthy("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS")
        workspace_id = os.getenv("MIRAI_MLFLOW_WORKSPACE_ID")
        artifact_bucket = os.getenv(f"MIRAI_{workspace_id.upper().replace('-', '_')}_S3_BUCKET") if workspace_id else None

        if require_remote_mlflow and not _is_remote_tracking_uri(tracking_uri):
            raise WorkspaceStorageError("Remote MLflow is required, but MLFLOW_TRACKING_URI is not a remote http(s) service URL")
        if require_remote_artifacts and not artifact_bucket:
            raise WorkspaceStorageError("Remote artifacts are required, but MIRAI_<WORKSPACE>_S3_BUCKET is missing")

        print("LOCAL_TRAINING_CONFIG_OK")
        print(f"backend={backend}")
        print(f"bucket={bucket}")
        print(f"object_key={key}")
        print(f"resolved_source={source}")
        print(f"mlflow_tracking_remote={_is_remote_tracking_uri(tracking_uri)}")
        print(f"mlflow_workspace={workspace_id or '<unset>'}")
        print(f"mlflow_artifact_bucket_configured={bool(artifact_bucket)}")
        if backend == "local":
            print(f"local_mirror_path={local_object_storage_path(bucket, key)}")
        if args.read_check:
            payload = read_object_storage_bytes(bucket, key)
            print(f"read_check_bytes={len(payload)}")
    except WorkspaceStorageError as exc:
        raise SystemExit(f"LOCAL_TRAINING_CONFIG_ERROR: {exc}") from exc


if __name__ == "__main__":
    main()
