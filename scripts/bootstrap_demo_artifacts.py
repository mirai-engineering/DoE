#!/usr/bin/env python3
"""Bootstrap approved Mirai demo artifacts into workspace/project object storage.

The default mode is dry-run. Real uploads require boto3 and credentials provided
only through environment variables. The script intentionally does not upload
`backend/data-minio/intake` wholesale.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import mimetypes
import os
from pathlib import Path
import sys
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
FUEL_PROJECT_ID = "pem_fuel_cell_real_cathode_degradation"
BATTERY_PROJECT_ID = "battery_tabular_doe_demo"


@dataclass(frozen=True)
class DemoProject:
    project_id: str
    workspace_id: str
    bucket_env: str
    endpoint_env: str
    access_key_env: str
    secret_key_env: str
    region_env: str
    default_bucket: str
    default_source: Path | None
    source_env: str

    @property
    def object_prefix(self) -> str:
        return f"workspaces/{self.workspace_id}/projects/{self.project_id}"


PROJECTS = {
    "fuel-cell": DemoProject(
        project_id=FUEL_PROJECT_ID,
        workspace_id="fraunhofer",
        bucket_env="MIRAI_FRAUNHOFER_S3_BUCKET",
        endpoint_env="MIRAI_FRAUNHOFER_S3_ENDPOINT",
        access_key_env="MIRAI_FRAUNHOFER_S3_ACCESS_KEY_ID",
        secret_key_env="MIRAI_FRAUNHOFER_S3_SECRET_ACCESS_KEY",
        region_env="MIRAI_FRAUNHOFER_S3_REGION",
        default_bucket="mirai-fuel-cells-demo",
        default_source=REPO_ROOT / "data" / "reference" / "pem_fuel_cell_cathode_degradation" / "training_artifacts" / "latest",
        source_env="MIRAI_FUEL_CELL_ARTIFACT_SOURCE",
    ),
    "battery": DemoProject(
        project_id=BATTERY_PROJECT_ID,
        workspace_id="battery-demo",
        bucket_env="MIRAI_BATTERY_DEMO_S3_BUCKET",
        endpoint_env="MIRAI_BATTERY_DEMO_S3_ENDPOINT",
        access_key_env="MIRAI_BATTERY_DEMO_S3_ACCESS_KEY_ID",
        secret_key_env="MIRAI_BATTERY_DEMO_S3_SECRET_ACCESS_KEY",
        region_env="MIRAI_BATTERY_DEMO_S3_REGION",
        default_bucket="mirai-batteries-demo",
        default_source=None,
        source_env="MIRAI_BATTERY_ARTIFACT_SOURCE",
    ),
}


ALLOWED_SUFFIXES = {
    ".csv",
    ".json",
    ".md",
    ".onnx",
    ".parquet",
    ".png",
    ".txt",
    ".yaml",
    ".yml",
}


def _env_path(name: str, fallback: Path | None) -> Path | None:
    value = os.getenv(name)
    if value:
        return Path(value).expanduser().resolve()
    return fallback


def _safe_relative(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"Unsafe relative path: {relative}")
    return relative.as_posix()


def _target_key(project: DemoProject, source_root: Path, source_file: Path, target_prefix: str = "training_artifacts/latest") -> str:
    relative = _safe_relative(source_file, source_root)
    return f"{project.object_prefix}/{target_prefix}/{relative}"


def _manifest_item(project: DemoProject, source_root: Path, source_file: Path, target_prefix: str) -> dict:
    return {
        "source": str(source_file.relative_to(REPO_ROOT)) if source_file.is_relative_to(REPO_ROOT) else str(source_file),
        "bucket": os.getenv(project.bucket_env, project.default_bucket),
        "key": _target_key(project, source_root, source_file, target_prefix),
        "size_bytes": source_file.stat().st_size,
    }


def _append_supported_objects(objects: list[dict], project: DemoProject, source_root: Path, target_prefix: str) -> None:
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        if "backend/data-minio/intake" in path.as_posix():
            raise ValueError("Refusing to upload backend/data-minio/intake content")
        objects.append(_manifest_item(project, source_root, path, target_prefix))


def _fuel_cell_intake_root(training_source_root: Path) -> Path | None:
    candidate = training_source_root
    if candidate.name == "latest" and candidate.parent.name == "training_artifacts":
        candidate = candidate.parent.parent
    for filename in ("model_table.csv", "cell_metadata.csv", "ast_trace_manifest.csv"):
        if not (candidate / filename).exists():
            return None
    return candidate


def _append_fuel_cell_intake_objects(objects: list[dict], project: DemoProject, training_source_root: Path) -> None:
    intake_root = _fuel_cell_intake_root(training_source_root)
    if intake_root is None:
        return
    for filename in ("model_table.csv", "cell_metadata.csv", "ast_trace_manifest.csv"):
        path = intake_root / filename
        if "backend/data-minio/intake" in path.as_posix():
            raise ValueError("Refusing to upload backend/data-minio/intake content")
        objects.append(_manifest_item(project, intake_root, path, "intake"))


def build_manifest(project: DemoProject) -> dict:
    source_root = _env_path(project.source_env, project.default_source)
    bucket = os.getenv(project.bucket_env, project.default_bucket)
    if source_root is None:
        return {
            "project_id": project.project_id,
            "workspace_id": project.workspace_id,
            "bucket": bucket,
            "prefix": project.object_prefix,
            "status": "deferred_no_source_configured",
            "source_env": project.source_env,
            "objects": [],
        }
    if not source_root.exists():
        return {
            "project_id": project.project_id,
            "workspace_id": project.workspace_id,
            "bucket": bucket,
            "prefix": project.object_prefix,
            "status": "source_missing",
            "source": str(source_root),
            "objects": [],
        }
    if "backend/data-minio/intake" in source_root.as_posix():
        raise ValueError("Refusing to upload backend/data-minio/intake wholesale")

    objects: list[dict] = []
    _append_supported_objects(objects, project, source_root, "training_artifacts/latest")
    if project.project_id == FUEL_PROJECT_ID:
        _append_fuel_cell_intake_objects(objects, project, source_root)
    return {
        "project_id": project.project_id,
        "workspace_id": project.workspace_id,
        "bucket": bucket,
        "prefix": project.object_prefix,
        "status": "ready" if objects else "no_supported_artifacts_found",
        "source": str(source_root),
        "objects": objects,
    }


def _credential_status(project: DemoProject) -> dict[str, bool]:
    return {
        project.bucket_env: bool(os.getenv(project.bucket_env)),
        project.endpoint_env: bool(os.getenv(project.endpoint_env)),
        project.access_key_env: bool(os.getenv(project.access_key_env)),
        project.secret_key_env: bool(os.getenv(project.secret_key_env)),
        project.region_env: bool(os.getenv(project.region_env)),
    }


def upload_manifest(manifest: dict, project: DemoProject) -> None:
    try:
        import boto3  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional real-upload path
        raise RuntimeError("Real uploads require boto3; dry-run does not.") from exc

    endpoint_url = os.environ[project.endpoint_env]
    access_key = os.environ[project.access_key_env]
    secret_key = os.environ[project.secret_key_env]
    region = os.getenv(project.region_env, "sjc")
    bucket = manifest["bucket"]
    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    for item in manifest["objects"]:
        source = REPO_ROOT / item["source"] if not Path(item["source"]).is_absolute() else Path(item["source"])
        content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        client.upload_file(str(source), bucket, item["key"], ExtraArgs={"ContentType": content_type})
        print(json.dumps({"uploaded": True, "bucket": bucket, "key": item["key"], "size_bytes": item["size_bytes"]}))


def selected_projects(selection: str) -> Iterable[tuple[str, DemoProject]]:
    if selection == "all":
        return PROJECTS.items()
    return [(selection, PROJECTS[selection])]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=["fuel-cell", "battery", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", default=True, help="List intended objects without uploading; default true.")
    parser.add_argument("--upload", action="store_true", help="Perform upload using env credentials. Never prints credential values.")
    args = parser.parse_args(argv)

    dry_run = not args.upload
    result = {"dry_run": dry_run, "projects": []}
    for name, project in selected_projects(args.project):
        manifest = build_manifest(project)
        manifest["credential_env_present"] = _credential_status(project)
        result["projects"].append(manifest)
        if args.upload:
            missing = [key for key, present in manifest["credential_env_present"].items() if not present]
            if missing:
                raise RuntimeError(f"Missing required env vars for upload: {', '.join(missing)}")
            upload_manifest(manifest, project)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
