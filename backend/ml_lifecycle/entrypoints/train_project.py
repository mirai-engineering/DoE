from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

from app.services.workspace_storage import object_storage_bucket, object_storage_uri, read_object_storage_bytes
from ml_lifecycle.training.generic_tabular_doe.train import train_generic_project


def _materialize_model_table_from_object_key(*, bucket: str, object_key: str) -> tempfile.TemporaryDirectory[str]:
    tmp = tempfile.TemporaryDirectory(prefix="mirai-training-data-")
    data_dir = Path(tmp.name)
    (data_dir / "model_table.csv").write_bytes(read_object_storage_bytes(bucket, object_key))
    return tmp


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a Mirai-contract generic tabular project")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--data-dir", type=Path, help="Directory containing model_table.csv. Prefer --data-object-key for Railway/local-mirror demos.")
    parser.add_argument("--data-object-key", help="Logical object key for model_table.csv, e.g. workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv")
    parser.add_argument("--bucket", help="Object-storage bucket. Defaults to OBJECT_STORAGE_BUCKET.")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.data_dir) == bool(args.data_object_key):
        parser.error("Provide exactly one of --data-dir or --data-object-key")

    tmp: tempfile.TemporaryDirectory[str] | None = None
    data_dir = args.data_dir
    if args.data_object_key:
        bucket = args.bucket or object_storage_bucket(required=True)
        assert bucket is not None
        source = object_storage_uri(bucket, args.data_object_key)
        print(f"Loading training data from {source}")
        tmp = _materialize_model_table_from_object_key(bucket=bucket, object_key=args.data_object_key)
        data_dir = Path(tmp.name)
    assert data_dir is not None
    try:
        result = train_generic_project(project_id=args.project_id, data_dir=data_dir, artifact_dir=args.artifact_dir)
    finally:
        if tmp is not None:
            tmp.cleanup()
    print(result)


if __name__ == "__main__":
    main()
