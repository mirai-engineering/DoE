from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from ml_lifecycle.training.generic_tabular_doe.train import train_generic_project


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = BACKEND_ROOT / ".local-training-runs"
REQUIRED_MANIFEST_FIELDS = ("project_id", "workspace_id", "dataset_id", "session_id", "training_request_id", "exported_at")


class ExportedPackageError(RuntimeError):
    """Raised when an exported training package cannot be used safely."""


@dataclass(frozen=True)
class ExportedPackage:
    package_dir: Path
    manifest_path: Path
    schema_path: Path
    table_path: Path
    manifest: dict[str, Any]
    schema: dict[str, Any]
    model_table: pd.DataFrame
    feature_columns: list[str]
    target_columns: list[str]

    @property
    def workspace_id(self) -> str:
        return str(self.manifest["workspace_id"])

    @property
    def project_id(self) -> str:
        return str(self.manifest["project_id"])

    @property
    def dataset_id(self) -> str:
        return str(self.manifest["dataset_id"])

    @property
    def session_id(self) -> str:
        return str(self.manifest["session_id"])

    @property
    def training_request_id(self) -> str:
        return str(self.manifest["training_request_id"])


def _now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _load_local_env() -> None:
    if os.getenv("PYTEST_CURRENT_TEST") and not _truthy_env("MIRAI_LOAD_LOCAL_TRAINING_ENV_IN_TESTS"):
        return
    env_path = BACKEND_ROOT / ".env.training.local"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(env_path, override=False)


def _read_json_file(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise ExportedPackageError(f"Missing required {label}: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExportedPackageError(f"Invalid JSON in {label} ({path}): {exc}") from exc
    if not isinstance(payload, dict):
        raise ExportedPackageError(f"{label} must contain a JSON object: {path}")
    return payload


def _column_names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("variable_id") or item.get("source_name")
            if name:
                names.append(str(name))
        elif isinstance(item, str):
            names.append(item)
    return names


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_checksum(manifest: dict[str, Any], path: Path) -> None:
    checksums = manifest.get("source_checksums")
    if not isinstance(checksums, dict):
        return
    expected = checksums.get(path.name)
    if not expected:
        return
    actual = _sha256_file(path)
    if str(expected).lower() != actual.lower():
        raise ExportedPackageError(f"Checksum mismatch for {path.name}: expected {expected}, got {actual}")


def _validate_manifest_schema_consistency(manifest: dict[str, Any], schema: dict[str, Any]) -> None:
    schema_project_id = schema.get("project_id")
    metadata = schema.get("metadata") if isinstance(schema.get("metadata"), dict) else {}
    project_meta = schema.get("project") if isinstance(schema.get("project"), dict) else {}
    candidates = [schema_project_id, metadata.get("project_id"), project_meta.get("project_id")]
    project_ids = {str(value) for value in candidates if value}
    manifest_project_id = str(manifest.get("project_id", ""))
    if project_ids and manifest_project_id not in project_ids:
        raise ExportedPackageError(
            f"Manifest project_id {manifest_project_id!r} does not match schema project identifiers {sorted(project_ids)!r}"
        )
    for key in ("workspace_id", "dataset_id", "session_id", "training_request_id"):
        schema_value = metadata.get(key) or project_meta.get(key)
        if schema_value and str(schema_value) != str(manifest.get(key, "")):
            raise ExportedPackageError(f"Manifest {key} {manifest.get(key)!r} does not match schema metadata {schema_value!r}")


def load_exported_package(package_dir: Path | str) -> ExportedPackage:
    root = Path(package_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ExportedPackageError(f"Package directory does not exist or is not a directory: {root}")
    manifest_path = root / "training_manifest.json"
    schema_path = root / "schema.json"
    preprocessed_table_path = root / "model_table_preprocessed.csv"
    table_path = preprocessed_table_path if preprocessed_table_path.exists() else root / "model_table.csv"
    manifest = _read_json_file(manifest_path, "training_manifest.json")
    schema = _read_json_file(schema_path, "schema.json")
    if not table_path.exists():
        raise ExportedPackageError(f"Missing required model_table.csv or model_table_preprocessed.csv in package: {root}")
    for field in REQUIRED_MANIFEST_FIELDS:
        if not manifest.get(field):
            raise ExportedPackageError(f"training_manifest.json is missing required field: {field}")
    _validate_manifest_schema_consistency(manifest, schema)
    _validate_checksum(manifest, table_path)
    _validate_checksum(manifest, schema_path)
    try:
        frame = pd.read_csv(table_path)
    except Exception as exc:
        raise ExportedPackageError(f"Unable to read {table_path.name}: {exc}") from exc
    if frame.empty:
        raise ExportedPackageError(f"{table_path.name} is empty; local training requires at least one row")
    feature_columns = [str(item) for item in manifest.get("feature_columns") or _column_names(schema.get("inputs"))]
    target_columns = [str(item) for item in manifest.get("target_columns") or _column_names(schema.get("outputs"))]
    if not feature_columns:
        raise ExportedPackageError("No feature columns found in manifest feature_columns or schema inputs")
    if not target_columns:
        raise ExportedPackageError("No target columns found in manifest target_columns or schema outputs")
    missing = [column for column in [*feature_columns, *target_columns] if column not in frame.columns]
    if missing:
        raise ExportedPackageError(f"{table_path.name} is missing required feature/target columns: {', '.join(missing)}")
    if "split" not in frame.columns:
        raise ExportedPackageError(f"{table_path.name} is missing required split column from approved preprocessing")
    if frame[frame["split"] == "train"].empty:
        raise ExportedPackageError(f"{table_path.name} has no train rows; approved package must include split=train rows")
    return ExportedPackage(
        package_dir=root,
        manifest_path=manifest_path,
        schema_path=schema_path,
        table_path=table_path,
        manifest=manifest,
        schema=schema,
        model_table=frame,
        feature_columns=feature_columns,
        target_columns=target_columns,
    )


def _is_remote_tracking_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and host not in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def preflight_remote_mlflow() -> str:
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if not tracking_uri:
        raise ExportedPackageError("MLFLOW_TRACKING_URI is required for exported-package local training")
    if not _truthy_env("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW"):
        raise ExportedPackageError("Set MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true so training cannot fall back to local mlruns")
    if not _truthy_env("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS"):
        raise ExportedPackageError("Set MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=true so artifacts must be remote")
    if not _is_remote_tracking_uri(tracking_uri):
        raise ExportedPackageError(f"MLFLOW_TRACKING_URI must be a remote http(s) MLflow service URL: {tracking_uri}")
    try:
        from mlflow.tracking import MlflowClient

        client = MlflowClient(tracking_uri=tracking_uri, registry_uri=tracking_uri)
        client.search_experiments(max_results=1)
    except Exception as exc:
        raise ExportedPackageError(f"Remote MLflow preflight failed for {tracking_uri}: {exc}") from exc
    return tracking_uri


def create_working_layout(package: ExportedPackage, output_root: Path | str = DEFAULT_OUTPUT_ROOT) -> dict[str, Path]:
    output_base = Path(output_root).expanduser().resolve()
    run_id = f"{_now_compact()}-{package.training_request_id}"
    run_root = output_base / run_id
    canonical = run_root / "canonical"
    artifacts = run_root / "artifacts"
    canonical.mkdir(parents=True, exist_ok=False)
    artifacts.mkdir(parents=True, exist_ok=False)
    shutil.copy2(package.table_path, canonical / package.table_path.name)
    if package.table_path.name != "model_table.csv":
        shutil.copy2(package.table_path, canonical / "model_table.csv")
    shutil.copy2(package.schema_path, artifacts / "schema.json")
    shutil.copy2(package.manifest_path, artifacts / "training_manifest.json")
    for name in ("feature_map.json", "target_map.json"):
        source = package.package_dir / name
        if source.exists():
            shutil.copy2(source, canonical / name)
    if package.table_path.name == "model_table_preprocessed.csv" and not (canonical / "feature_map.json").exists():
        (canonical / "feature_map.json").write_text(json.dumps({"feature_columns": package.feature_columns}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if package.table_path.name == "model_table_preprocessed.csv" and not (canonical / "target_map.json").exists():
        (canonical / "target_map.json").write_text(json.dumps({"target_columns": package.target_columns}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name in ("preprocessing_fitted.json", "ml_preprocessing_report.json", "ml_preprocessing_report.md", "model_table_preprocessed_manifest.json"):
        source = package.package_dir / name
        if source.exists():
            shutil.copy2(source, artifacts / name)
    preprocessing = {
        "version": package.manifest.get("preprocessing_contract_version") or "approved_export_package",
        "input_order": package.feature_columns,
        "output_order": package.target_columns,
        "split_strategy": "approved_export_package",
        "source": "approved_export_package",
        "package_dir": str(package.package_dir),
        "workspace_id": package.manifest.get("workspace_id"),
        "project_id": package.manifest.get("project_id"),
        "dataset_id": package.manifest.get("dataset_id"),
        "session_id": package.manifest.get("session_id"),
        "training_request_id": package.manifest.get("training_request_id"),
        "exported_at": package.manifest.get("exported_at"),
        "source_checksums": package.manifest.get("source_checksums", {}),
    }
    (artifacts / "preprocessing.json").write_text(json.dumps(preprocessing, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"run_root": run_root, "canonical": canonical, "artifacts": artifacts}


def validate_identity_flags(
    package: ExportedPackage,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    dataset_id: str | None = None,
    session_id: str | None = None,
    training_request_id: str | None = None,
) -> dict[str, str]:
    supplied = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "dataset_id": dataset_id,
        "session_id": session_id,
        "training_request_id": training_request_id,
    }
    manifest_values = {key: str(package.manifest.get(key) or "") for key in supplied}
    missing_required = [key for key in ("workspace_id", "project_id") if not supplied.get(key)]
    if missing_required:
        raise ExportedPackageError(
            "Explicit identity flags are required for remote training: " + ", ".join(f"--{key.replace('_', '-')}" for key in missing_required)
        )
    mismatches = [key for key, value in supplied.items() if value is not None and str(value) != manifest_values.get(key)]
    if mismatches:
        details = ", ".join(f"{key}: flag={supplied[key]!r} manifest={manifest_values.get(key)!r}" for key in mismatches)
        raise ExportedPackageError(f"Identity flags do not match training_manifest.json ({details})")
    return manifest_values


def registered_model_name(project_id: str) -> str:
    return f"doe_surrogate_{project_id}"


def build_training_config(package: ExportedPackage, *, max_epochs: int | None = None) -> dict[str, Any]:
    source_checksums = package.manifest.get("source_checksums") if isinstance(package.manifest.get("source_checksums"), dict) else {}
    source_checksum = source_checksums.get("model_table.csv") or source_checksums.get("schema.json") or ""
    config: dict[str, Any] = {
        "mlflow": {
            "enabled": True,
            "extra_tags": {
                "workspace_id": str(package.manifest.get("workspace_id", "")),
                "project_id": str(package.manifest.get("project_id", "")),
                "dataset_id": str(package.manifest.get("dataset_id", "")),
                "session_id": str(package.manifest.get("session_id", "")),
                "training_request_id": str(package.manifest.get("training_request_id", "")),
                "exported_at": str(package.manifest.get("exported_at", "")),
                "source_checksum": str(source_checksum),
                "training_source": "approved_export_package",
            },
            "extra_artifacts": ["training_manifest.json"],
        }
    }
    if max_epochs is not None:
        config["mlp"] = {"include": True, "max_epochs": max_epochs, "patience": min(max_epochs, 20), "seed": 7}
    return config


def run_training(
    package_dir: Path | str,
    *,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    max_epochs: int | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
    dataset_id: str | None = None,
    session_id: str | None = None,
    training_request_id: str | None = None,
) -> dict[str, Any]:
    _load_local_env()
    package = load_exported_package(package_dir)
    identity = validate_identity_flags(
        package,
        workspace_id=workspace_id,
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        training_request_id=training_request_id,
    )
    tracking_uri = preflight_remote_mlflow()
    layout = create_working_layout(package, output_root=output_root)
    config = build_training_config(package, max_epochs=max_epochs)
    metrics = train_generic_project(
        project_id=package.project_id,
        data_dir=layout["canonical"],
        artifact_dir=layout["artifacts"],
        training_config=config,
    )
    return {
        "status": "completed",
        "tracking_uri": tracking_uri,
        "run_root": str(layout["run_root"]),
        "artifact_dir": str(layout["artifacts"]),
        "identity": identity,
        "workspace_id": package.workspace_id,
        "project_id": package.project_id,
        "dataset_id": package.dataset_id,
        "session_id": package.session_id,
        "training_request_id": package.training_request_id,
        "mlflow_experiment_name": package.project_id,
        "registered_model_name": registered_model_name(package.project_id),
        "expected_output_alias": "challenger",
        "best_model": metrics.get("best_model_name") or metrics.get("best_model"),
        "mlflow": metrics.get("mlflow"),
        "next_steps": [
            f"Open MLflow experiment {package.project_id!r} at the remote tracking URI and review the selected challenger run.",
            f"Confirm registered model {registered_model_name(package.project_id)!r} has alias 'challenger' on the selected version.",
            "Manually promote the approved version to alias 'champion' in MLflow.",
            "Return to Mirai and use Load champion model for this workspace/project.",
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train locally from an approved Mirai exported package and log to remote MLflow.")
    parser.add_argument("--package-dir", required=True, type=Path, help="Directory containing model_table.csv, schema.json, and training_manifest.json")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, type=Path, help="Gitignored local output root; defaults to backend/.local-training-runs")
    parser.add_argument("--max-epochs", type=int, default=None, help="Optional modest MLP epoch override for smoke runs")
    parser.add_argument("--workspace-id", required=True, help="Workspace id; must match training_manifest.json")
    parser.add_argument("--project-id", required=True, help="Project id; must match training_manifest.json and becomes the MLflow experiment name")
    parser.add_argument("--dataset-id", default=None, help="Optional dataset id; if supplied, must match training_manifest.json")
    parser.add_argument("--session-id", default=None, help="Optional ingestion session id; if supplied, must match training_manifest.json")
    parser.add_argument("--training-request-id", default=None, help="Optional training request id; if supplied, must match training_manifest.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = run_training(
            args.package_dir,
            output_root=args.output_root,
            max_epochs=args.max_epochs,
            workspace_id=args.workspace_id,
            project_id=args.project_id,
            dataset_id=args.dataset_id,
            session_id=args.session_id,
            training_request_id=args.training_request_id,
        )
    except ExportedPackageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
