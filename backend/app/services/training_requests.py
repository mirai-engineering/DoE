from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
import logging
import mimetypes
from pathlib import Path
import re
import shutil
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from .control_plane import activate_champion_model, complete_training_run, create_training_run, fail_training_run, get_project_storage_config, get_training_run_by_mlflow_run_id, record_candidate_model, upsert_schema_manifest
from .data_intake import BACKEND_ROOT, get_ingestion_session, read_status, session_workspace, write_status
from .domain_metadata import build_domain_metadata, infer_template_id
from .db import postgres_control_plane_required
from .mlflow_registry import download_production_onnx, download_run_artifacts, durable_artifact_pointer_for_project, registered_model_name_for_project, verify_champion_mlflow_model, verify_external_mlflow_model_version
from .workspace_storage import put_workspace_object, validate_workspace_object_key, workspace_s3_config_from_env
from .preprocessing_review import get_preprocessing_review_report
from .project_registry import get_project_schema
from ml_lifecycle.training.generic_tabular_doe.train import train_generic_project


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApprovedTrainingPackage:
    filename: str
    content: bytes
    sha256: str
    size_bytes: int
    manifest: dict[str, Any]


DEFAULT_TRAINING_PLAN: dict[str, Any] = {
    "preset": "balanced_training",
    "estimated_duration": "2-5 minutes on this local dataset; first run may be slower if MLflow/model export initializes caches",
    "dataset": {
        "source": "session canonical/model_table.csv",
        "split_strategy": "metadata-aware grouped split by cell_id",
        "bo_holdout_policy": "not_reserved; BO uses train+validation and keeps test untouched",
    },
    "models": [
        {
            "family": "mean_baseline",
            "label": "Train-cell mean baseline",
            "parameters": {"strategy": "predict train-set output mean per target"},
            "purpose": "sanity baseline for improvement checks",
        },
        {
            "family": "mvlr",
            "label": "Multivariate linear regression",
            "parameters": {"estimator": "sklearn.linear_model.LinearRegression", "regularization": "none"},
            "purpose": "interpretable linear challenger",
        },
        {
            "family": "mlp",
            "label": "Scientific tabular ANN",
            "parameters": {
                "hidden_layers": [128, 64, 32],
                "activation": "SiLU",
                "normalization": "LayerNorm per hidden layer",
                "dropout": 0.05,
                "optimizer": "AdamW",
                "learning_rate": 0.01,
                "weight_decay": 0.0001,
                "max_epochs": 500,
                "early_stopping": "after epoch 100 with validation patience",
                "seed": 7,
                "export": "ONNX export for deployment",
            },
            "purpose": "deployable nonlinear surrogate candidate",
        },
    ],
    "outputs": "contract-defined output variables",
    "selection": "validation weighted nRMSE chooses the challenger candidate; champion remains manual in MLflow",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_dir(project_id: str, dataset_id: str, session_id: str) -> Path:
    return session_workspace(project_id, dataset_id, session_id)["root"]


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _default_training_config() -> dict[str, Any]:
    return {
        "linear": {"include_mvlr": True, "fit_intercept": True, "include_ridge": True, "ridge_alphas": [0.01, 0.1, 1.0, 10.0]},
        "mlp": {
            "include": True,
            "architecture_family": "plain_mlp",
            "hidden_layers": [128, 64, 32],
            "trunk_layers": [128, 128],
            "head_layers": [64],
            "secondary_head_layers": [32],
            "activation": "SiLU",
            "normalization": "layer_norm",
            "dropout": 0.05,
            "optimizer": "AdamW",
            "learning_rate": 0.003,
            "weight_decay": 0.0001,
            "batch_size": "full_batch",
            "max_epochs": 500,
            "early_stopping_patience": 100,
            "loss": "smooth_l1",
            "output_weights": {},
            "seeds": [7],
        },
        "search": {"mode": "single_config", "wall_clock_budget_minutes": 60, "rerun_top_k": 0},
        "selection_metric": "validation_weighted_normalized_rmse",
    }


def create_training_request(
    project_id: str,
    dataset_id: str,
    session_id: str,
    *,
    requested_by: str,
    preset: str,
    model_families: list[str],
    training_config: dict[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    session = get_ingestion_session(project_id, dataset_id, session_id)
    report = get_preprocessing_review_report(project_id, dataset_id, session_id)
    if report.get("approval", {}).get("status") != "approved_for_training":
        raise ValueError("Preprocessing must be approved by a Mirai admin before creating a training request")
    allowed = {"mean_baseline", "mvlr", "ridge", "mlp"}
    invalid = sorted(set(model_families) - allowed)
    if invalid:
        raise ValueError(f"Unsupported MVP model families: {', '.join(invalid)}")
    if not model_families:
        raise ValueError("At least one model family is required")

    request_id = f"train_req_{uuid4().hex[:10]}"
    payload = {
        "training_request_id": request_id,
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "preprocessing_report_id": f"{session_id}:preprocessing_report",
        "status": "staged_for_mirai_execution",
        "requested_by": requested_by,
        "requested_at": _now(),
        "preset": preset,
        "model_families": model_families,
        "training_config": training_config or _default_training_config(),
        "notes": notes or "",
        "training_plan": {**DEFAULT_TRAINING_PLAN, "training_config": training_config or _default_training_config()},
        "execution": {
            "mode": "approved_synchronous_mvp_execution",
            "automatic_training_enabled": False,
            "manual_start_required": True,
            "message": "MVP stores a reviewed training request. After Mirai-admin approval, the user explicitly starts synchronous training from the UI.",
        },
        "mlflow": {
            "experiment_name": project_id,
            "registered_model_name": registered_model_name_for_project(project_id),
            "candidate_alias": "challenger",
            "champion_policy": "manual_promotion_only",
        },
        "mlflow_tags_to_apply_on_execution": {
            "project_id": project_id,
            "dataset_id": dataset_id,
            "ingestion_session_id": session_id,
            "preprocessing_report_id": f"{session_id}:preprocessing_report",
            "training_request_id": request_id,
            "lifecycle_role": "challenger",
        },
        "source_session_status": session.get("status"),
        "preprocessing_approval": report.get("approval"),
        "route_after_completion": f"/projects/{project_id}/model-quality",
    }
    _write_json(_session_dir(project_id, dataset_id, session_id) / "training_requests" / f"{request_id}.json", payload)
    return payload


def list_training_requests(project_id: str, dataset_id: str, session_id: str) -> list[dict[str, Any]]:
    request_dir = _session_dir(project_id, dataset_id, session_id) / "training_requests"
    if not request_dir.exists():
        return []
    requests = [_read_json(path, default={}) for path in sorted(request_dir.glob("*.json"))]
    return [request for request in requests if request]


def get_training_request(project_id: str, dataset_id: str, session_id: str, training_request_id: str) -> dict[str, Any]:
    request = _read_json(_session_dir(project_id, dataset_id, session_id) / "training_requests" / f"{training_request_id}.json")
    if not request:
        raise FileNotFoundError("Training request not found")
    return request


def _write_training_request(project_id: str, dataset_id: str, session_id: str, request: dict[str, Any]) -> dict[str, Any]:
    return _write_json(_session_dir(project_id, dataset_id, session_id) / "training_requests" / f"{request['training_request_id']}.json", request)


def _copy_tree_contents(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.name in {"raw_reference_extracted", "01-Data"}:
            # Raw/reference ZIPs and source workspaces must stay out of activated
            # project artifacts. They can contain many raw CSV files and are not needed
            # for serving/model-quality; only bounded inventories and canonical outputs
            # should be persisted.
            continue
        destination = target / path.name
        if path.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(path, destination)
        else:
            shutil.copy2(path, destination)


def activate_session_artifacts_for_model_quality(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    workspace = session_workspace(project_id, dataset_id, session_id)
    canonical = workspace["canonical"]
    training_latest = workspace["training_latest"]
    if not (canonical / "model_table.csv").exists():
        raise FileNotFoundError("Session canonical model_table.csv is missing")
    if not (training_latest / "metrics_summary.json").exists():
        raise FileNotFoundError("Session training metrics_summary.json is missing")
    schema = _read_json(training_latest / "schema.json", default={}) or {}
    template_id = schema.get("metadata", {}).get("template_id") if isinstance(schema.get("metadata"), dict) else None
    return {
        "mode": "session_artifacts_active_in_object_store",
        "canonical_source": str(canonical.relative_to(BACKEND_ROOT)),
        "artifact_target": str(training_latest.relative_to(BACKEND_ROOT)),
        "template_id": template_id or "generic_tabular_doe",
        "professional_follow_up": "Use immutable object-storage artifact URIs plus per-project activation records for multi-client deployments.",
    }


def _project_storage_config_for_training(workspace_id: str, project_id: str):
    runtime_config = get_project_storage_config(workspace_id, project_id)
    if runtime_config is not None:
        return runtime_config
    return workspace_s3_config_from_env(workspace_id, prefix=f"workspaces/{workspace_id}/projects/{project_id}")


def _upload_training_artifacts_to_s3(workspace_id: str, project_id: str, training_run_id: str, artifact_dir: Path) -> dict[str, Any]:
    try:
        config = _project_storage_config_for_training(workspace_id, project_id)
        uploaded: list[dict[str, Any]] = []
        prefix = validate_workspace_object_key(config, f"{config.normalized_prefix}/artifacts/{training_run_id}")
        for path in sorted(artifact_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(artifact_dir).as_posix()
            key = f"{prefix}/{relative}"
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            with path.open("rb") as handle:
                put_workspace_object(config, key, handle, content_type=content_type)
            uploaded.append({"key": key, "size_bytes": path.stat().st_size})
        return {"status": "uploaded", "count": len(uploaded), "objects": uploaded[:50], "prefix": prefix + "/"}
    except Exception as exc:  # noqa: BLE001 - local/dev can run without S3.
        logger.warning("Training artifact S3 upload skipped/failed for workspace_id=%s project_id=%s: %s", workspace_id, project_id, exc)
        if postgres_control_plane_required():
            raise
        return {"status": "skipped", "detail": str(exc)}


_SAFE_EXPORT_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_export_route_id(name: str, value: str) -> str:
    if not value or not _SAFE_EXPORT_ID.fullmatch(value):
        raise ValueError(f"{name} must be a safe identifier")
    return value


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


def _source_checksums(session: dict[str, Any], canonical_table: Path, schema_path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for item in session.get("files", []):
        if isinstance(item, dict) and item.get("sha256"):
            checksums[str(item.get("filename") or "uploaded_source")] = str(item["sha256"])
    checksums[canonical_table.name] = _sha256_file(canonical_table)
    checksums[schema_path.name] = _sha256_file(schema_path)
    return checksums


def _preprocessing_contract_version(schema: dict[str, Any], preprocessing: dict[str, Any]) -> str:
    if preprocessing.get("version"):
        return str(preprocessing["version"])
    metadata = schema.get("metadata") if isinstance(schema.get("metadata"), dict) else {}
    return str(metadata.get("contract_version") or metadata.get("template_id") or "unknown")


def build_approved_training_package(
    *,
    workspace_id: str | None,
    project_id: str,
    dataset_id: str,
    session_id: str,
    training_request_id: str,
) -> ApprovedTrainingPackage:
    project_id = _validate_export_route_id("project_id", project_id)
    dataset_id = _validate_export_route_id("dataset_id", dataset_id)
    session_id = _validate_export_route_id("session_id", session_id)
    training_request_id = _validate_export_route_id("training_request_id", training_request_id)
    session = get_ingestion_session(project_id, dataset_id, session_id)
    session_workspace_id = session.get("workspace_id")
    if workspace_id and session_workspace_id and str(session_workspace_id) != str(workspace_id):
        raise ValueError("Training package does not belong to the authorized workspace")
    if str(session.get("project_id")) != project_id or str(session.get("dataset_id")) != dataset_id or str(session.get("ingestion_session_id")) != session_id:
        raise ValueError("Session identity does not match requested training package")

    request = get_training_request(project_id, dataset_id, session_id, training_request_id)
    if (
        str(request.get("project_id")) != project_id
        or str(request.get("dataset_id")) != dataset_id
        or str(request.get("ingestion_session_id")) != session_id
        or str(request.get("training_request_id")) != training_request_id
    ):
        raise ValueError("Training request does not belong to the requested dataset/session/project")

    report = get_preprocessing_review_report(project_id, dataset_id, session_id)
    if report.get("approval", {}).get("status") != "approved_for_training":
        raise ValueError("Preprocessing must be approved before exporting a training package")

    workspace = session_workspace(project_id, dataset_id, session_id)
    canonical = workspace["canonical"]
    training_latest = workspace["training_latest"]
    table_path = canonical / "model_table.parquet"
    if not table_path.exists():
        table_path = canonical / "model_table.csv"
    if not table_path.exists():
        raise FileNotFoundError("Approved model table is missing")
    schema_path = training_latest / "schema.json"
    if not schema_path.exists():
        raise FileNotFoundError("Approved schema.json is missing")

    preprocessing = _read_json(training_latest / "preprocessing.json", default={}) or {}
    schema = _read_json(schema_path, default={}) or {}
    feature_columns = list(preprocessing.get("input_order") or _column_names(schema.get("inputs")))
    target_columns = list(preprocessing.get("output_order") or _column_names(schema.get("outputs")))
    manifest = {
        "package_format_version": "1",
        "workspace_id": str(session_workspace_id or workspace_id or ""),
        "project_id": project_id,
        "dataset_id": dataset_id,
        "session_id": session_id,
        "training_request_id": training_request_id,
        "feature_columns": feature_columns,
        "target_columns": target_columns,
        "preprocessing_contract_version": _preprocessing_contract_version(schema, preprocessing),
        "source_checksums": _source_checksums(session, table_path, schema_path),
        "exported_at": _now(),
    }

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.write(table_path, table_path.name)
        archive.write(schema_path, "schema.json")
        archive.writestr("training_manifest.json", json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
    content = buffer.getvalue()
    filename = f"mirai-training-package-{project_id}-{dataset_id}-{training_request_id}.zip"
    return ApprovedTrainingPackage(
        filename=filename,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        manifest=manifest,
    )


def start_training_request(project_id: str, dataset_id: str, session_id: str, training_request_id: str) -> dict[str, Any]:
    request = get_training_request(project_id, dataset_id, session_id, training_request_id)
    report = get_preprocessing_review_report(project_id, dataset_id, session_id)
    if report.get("approval", {}).get("status") != "approved_for_training":
        raise ValueError("Preprocessing must be approved by a Mirai admin before training starts")
    workspace = session_workspace(project_id, dataset_id, session_id)
    canonical = workspace["canonical"]
    training_latest = workspace["training_latest"]
    if not (canonical / "model_table.csv").exists():
        raise FileNotFoundError("Canonical model_table.csv not found; run preprocessing first")
    schema = _read_json(training_latest / "schema.json", default={}) or {}
    template_id = schema.get("metadata", {}).get("template_id") if isinstance(schema.get("metadata"), dict) else "generic_tabular_doe"

    status_payload = {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "training_request_id": training_request_id,
        "status": "running",
        "stage": "training_generic_tabular_models",
        "template_id": template_id or "generic_tabular_doe",
    }
    write_status(project_id, dataset_id, session_id, f"training_{training_request_id}", status_payload)
    session = get_ingestion_session(project_id, dataset_id, session_id)
    workspace_id = str(session.get("workspace_id") or "mirai-engineering")
    storage_config = _project_storage_config_for_training(workspace_id, project_id)
    artifact_prefix = validate_workspace_object_key(storage_config, f"{storage_config.normalized_prefix}/artifacts/{training_request_id}") + "/"
    create_training_run(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_request_id,
        dataset_id=dataset_id,
        artifact_s3_prefix=artifact_prefix,
        created_by=str(request.get("requested_by") or "unknown"),
    )
    request["status"] = "running"
    request["started_at"] = _now()
    _write_training_request(project_id, dataset_id, session_id, request)

    try:
        result = train_generic_project(project_id=project_id, data_dir=canonical, artifact_dir=training_latest, training_config=request.get("training_config"))
    except Exception as exc:  # noqa: BLE001 - persist failed runtime row before surfacing API error.
        fail_training_run(workspace_id=workspace_id, project_id=project_id, training_run_id=training_request_id, error_message=str(exc))
        raise
    metadata_status = read_status(project_id, dataset_id, session_id, "domain_metadata", default={})
    schema_path = training_latest / "schema.json"
    if schema_path.exists():
        schema = _read_json(schema_path)
        approved_metadata = metadata_status.get("domain_metadata") if isinstance(metadata_status, dict) and metadata_status.get("approval_status") == "approved" else None
        schema["domain_metadata"] = approved_metadata or build_domain_metadata(schema, template_id=infer_template_id(schema), approval_status="approved")
        _write_json(schema_path, schema)
    try:
        activation = activate_session_artifacts_for_model_quality(project_id, dataset_id, session_id)
        s3_upload = _upload_training_artifacts_to_s3(workspace_id, project_id, training_request_id, training_latest)
    except Exception as exc:  # noqa: BLE001 - durable artifact upload failure must be explicit/recoverable.
        fail_training_run(workspace_id=workspace_id, project_id=project_id, training_run_id=training_request_id, error_message=f"Training artifact upload failed: {exc}")
        failed = {
            **status_payload,
            "status": "failed_retryable_artifact_upload",
            "completed_at": _now(),
            "result": result,
            "error": "Training artifact upload failed",
            "detail": str(exc),
            "retryable": True,
        }
        write_status(project_id, dataset_id, session_id, f"training_{training_request_id}", failed)
        request["status"] = failed["status"]
        request["error"] = failed["error"]
        request["retryable"] = True
        _write_training_request(project_id, dataset_id, session_id, request)
        return failed
    completed = {
        **status_payload,
        "status": "completed",
        "completed_at": _now(),
        "result": result,
        "activation": activation,
        "s3_upload": s3_upload,
        "model_quality_project_id": project_id,
        "route_after_completion": f"/projects/{project_id}/model-quality",
    }
    write_status(project_id, dataset_id, session_id, f"training_{training_request_id}", completed)
    metrics = result.get("metrics_summary") if isinstance(result, dict) and isinstance(result.get("metrics_summary"), dict) else result if isinstance(result, dict) else {}
    mlflow_run_ids = result.get("mlflow_run_ids") if isinstance(result, dict) else None
    mlflow_run_id = mlflow_run_ids[0] if isinstance(mlflow_run_ids, list) and mlflow_run_ids else None
    best_model_type = str(result.get("best_model_name") or result.get("best_model") or "unknown") if isinstance(result, dict) else "unknown"
    run_metrics = metrics if isinstance(metrics, dict) else {}
    complete_training_run(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_request_id,
        mlflow_run_id=mlflow_run_id,
        best_model_type=best_model_type,
        metrics=run_metrics,
    )
    record_candidate_model(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_request_id,
        model_name=f"doe_surrogate_{project_id}",
        version=training_request_id,
        artifact_uri=f"{artifact_prefix}model.onnx",
        preprocessing_uri=f"{artifact_prefix}preprocessing.json",
        schema_uri=f"{artifact_prefix}schema.json",
        metrics=run_metrics,
    )
    request["status"] = "completed"
    request["completed_at"] = completed["completed_at"]
    request["result"] = result
    request["activation"] = activation
    request["route_after_completion"] = completed["route_after_completion"]
    _write_training_request(project_id, dataset_id, session_id, request)
    return completed


def import_external_mlflow_run(
    project_id: str,
    dataset_id: str,
    session_id: str,
    training_request_id: str,
    *,
    mlflow_run_id: str,
    registered_model_name: str | None = None,
    model_version: str | None = None,
    alias: str = "challenger",
    imported_by: str = "Mirai admin",
    notes: str | None = None,
) -> dict[str, Any]:
    request = get_training_request(project_id, dataset_id, session_id, training_request_id)
    report = get_preprocessing_review_report(project_id, dataset_id, session_id)
    if report.get("approval", {}).get("status") != "approved_for_training":
        raise ValueError("Preprocessing must be approved before importing external MLflow training")
    session = get_ingestion_session(project_id, dataset_id, session_id)
    workspace_id = str(session.get("workspace_id") or "mirai-engineering")
    verified = verify_external_mlflow_model_version(
        workspace_id=workspace_id,
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        training_request_id=training_request_id,
        mlflow_run_id=mlflow_run_id,
        registered_model_name=registered_model_name,
        model_version=model_version,
        alias=alias,
    )
    approved_package = build_approved_training_package(
        workspace_id=workspace_id,
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        training_request_id=training_request_id,
    )
    expected_checksums = approved_package.manifest.get("source_checksums") if isinstance(approved_package.manifest, dict) else None
    actual_manifest = verified.get("training_manifest") if isinstance(verified.get("training_manifest"), dict) else {}
    actual_checksums = actual_manifest.get("source_checksums") if isinstance(actual_manifest, dict) else None
    if actual_checksums != expected_checksums:
        raise ValueError("MLflow training_manifest source_checksums do not match the approved Mirai training package")
    # Populate the local MLflow artifact cache now so Model Quality/Design Studio
    # fail at import time if the remote run is incomplete or inaccessible.
    artifact_cache = download_run_artifacts(project_id, mlflow_run_id, include_quality=True, include_predictions=True)
    storage_config = _project_storage_config_for_training(workspace_id, project_id)
    artifact_prefix = validate_workspace_object_key(storage_config, f"{storage_config.normalized_prefix}/mlflow-imports/{training_request_id}") + "/"
    mlflow_pointer = durable_artifact_pointer_for_project(project_id, "mlflow_artifacts", workspace_id=workspace_id)
    create_training_run(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_request_id,
        dataset_id=dataset_id,
        artifact_s3_prefix=artifact_prefix,
        created_by=imported_by,
    )
    import_metrics = {
        **(verified.get("metrics") if isinstance(verified.get("metrics"), dict) else {}),
        "mlflow_import": {
            "run_id": mlflow_run_id,
            "registered_model_name": verified.get("registered_model_name"),
            "model_version": verified.get("model_version"),
            "alias": verified.get("alias"),
            "model_uri": verified.get("model_uri"),
        },
    }
    complete_training_run(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_request_id,
        mlflow_run_id=mlflow_run_id,
        best_model_type=str(verified.get("model_name") or "external_mlflow_model"),
        metrics=import_metrics,
    )
    record_candidate_model(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_request_id,
        model_name=str(verified.get("registered_model_name") or registered_model_name_for_project(project_id)),
        version=str(verified.get("model_version") or training_request_id),
        artifact_uri=str(mlflow_pointer["object_uri"]),
        preprocessing_uri=f"{artifact_prefix}preprocessing.json",
        schema_uri=f"{artifact_prefix}schema.json",
        metrics=import_metrics,
    )
    completed = {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "training_request_id": training_request_id,
        "status": "candidate_ready_for_review",
        "stage": "external_mlflow_run_imported",
        "completed_at": _now(),
        "imported_by": imported_by,
        "notes": notes or "",
        "mlflow": verified,
        "artifact_cache": str(artifact_cache),
        "model_quality_project_id": project_id,
        "route_after_completion": f"/projects/{project_id}/model-quality",
    }
    write_status(project_id, dataset_id, session_id, f"training_{training_request_id}", completed)
    request["status"] = "candidate_ready_for_review"
    request["completed_at"] = completed["completed_at"]
    request["execution"] = {
        **(request.get("execution") if isinstance(request.get("execution"), dict) else {}),
        "mode": "external_mlflow_import",
        "message": "Completed by importing a verified external MLflow training run.",
    }
    request["mlflow_import"] = verified
    request["route_after_completion"] = completed["route_after_completion"]
    _write_training_request(project_id, dataset_id, session_id, request)
    return completed


def _schema_for_champion_load(*, workspace_id: str, project_id: str, artifact_cache: Path) -> dict[str, Any]:
    artifact_schema = _read_json(artifact_cache / "schema.json", default={}) or {}
    try:
        mirai_schema = get_project_schema(project_id, workspace_id)
    except Exception:
        mirai_schema = {}
    if isinstance(mirai_schema, dict) and mirai_schema.get("inputs") and mirai_schema.get("outputs"):
        return mirai_schema
    if isinstance(artifact_schema, dict) and artifact_schema.get("inputs") and artifact_schema.get("outputs"):
        artifact_schema["project_id"] = artifact_schema.get("project_id") or project_id
        artifact_schema["workspace_id"] = artifact_schema.get("workspace_id") or workspace_id
        return artifact_schema
    raise FileNotFoundError("Champion load requires a schema with inputs and outputs from Mirai or MLflow schema.json")


def load_champion_model(
    *,
    workspace_id: str,
    project_id: str,
    mlflow_run_id: str | None = None,
    registered_model_name: str | None = None,
    model_version: str | None = None,
    loaded_by: str = "Mirai admin",
    notes: str | None = None,
) -> dict[str, Any]:
    """Load the approved MLflow champion into Mirai serving state.

    This is the single app-dev activation path: the selected MLflow model must
    already be the current `champion` alias, contain a serveable ONNX artifact,
    and match the requested workspace/project identity.
    """
    verified = verify_champion_mlflow_model(workspace_id=workspace_id, project_id=project_id)
    expected_name = registered_model_name_for_project(project_id)
    if registered_model_name and registered_model_name != expected_name:
        raise ValueError(f"Registered model name must be {expected_name!r} for this project")
    actual_run_id = str(verified["mlflow_run_id"])
    if mlflow_run_id and mlflow_run_id != actual_run_id:
        raise ValueError("Selected MLflow run is not the current champion alias for this project")
    if model_version and str(model_version) != str(verified.get("model_version")):
        raise ValueError("Selected MLflow model version is not the current champion alias for this project")

    artifact_cache = download_run_artifacts(project_id, actual_run_id, refresh=True, include_quality=True, include_predictions=True)
    onnx_model_path = download_production_onnx(project_id, refresh=True, workspace_id=None)
    # Verify the cached ONNX comes from the same registered champion by forcing
    # runtime resolution through Mirai state after activation below; before the
    # model row exists, this call verifies the MLflow champion model artifact is
    # ONNX-loadable via the alias path used by local/offline tests.
    if onnx_model_path.suffix.lower() != ".onnx":
        raise FileNotFoundError("MLflow champion did not resolve to an ONNX model artifact")

    training_run = get_training_run_by_mlflow_run_id(workspace_id, project_id, actual_run_id)
    training_manifest = verified.get("training_manifest") if isinstance(verified.get("training_manifest"), dict) else {}
    tags = verified.get("tags") if isinstance(verified.get("tags"), dict) else {}
    training_run_id = str(
        (training_run or {}).get("training_run_id")
        or training_manifest.get("training_request_id")
        or tags.get("training_request_id")
        or f"mlflow_{actual_run_id[:12]}"
    )
    dataset_id = str(training_manifest.get("dataset_id") or tags.get("dataset_id") or "") or None

    storage_config = _project_storage_config_for_training(workspace_id, project_id)
    artifact_prefix = validate_workspace_object_key(storage_config, f"{storage_config.normalized_prefix}/mlflow-imports/{training_run_id}") + "/"
    schema_uri = f"{artifact_prefix}schema.json"
    preprocessing_uri = f"{artifact_prefix}preprocessing.json"
    schema = _schema_for_champion_load(workspace_id=workspace_id, project_id=project_id, artifact_cache=artifact_cache)
    upsert_schema_manifest(
        workspace_id=workspace_id,
        project_id=project_id,
        schema=schema,
        manifest_object_uri=schema_uri,
        validation_status="approved",
    )

    mlflow_pointer = durable_artifact_pointer_for_project(project_id, "mlflow_artifacts", workspace_id=workspace_id)
    metrics = {
        **((training_run or {}).get("metrics_json") if isinstance((training_run or {}).get("metrics_json"), dict) else {}),
        **(verified.get("metrics") if isinstance(verified.get("metrics"), dict) else {}),
        "mlflow_import": {
            "run_id": actual_run_id,
            "registered_model_name": verified.get("registered_model_name"),
            "model_version": verified.get("model_version"),
            "alias": "champion",
            "model_uri": verified.get("model_uri"),
            "model_artifact_format": "onnx",
        },
        "champion_load": {
            "status": "approved_champion_active",
            "loaded_by": loaded_by,
            "loaded_at": _now(),
            "notes": notes or "",
        },
    }
    if not training_run:
        create_training_run(
            workspace_id=workspace_id,
            project_id=project_id,
            training_run_id=training_run_id,
            dataset_id=dataset_id,
            artifact_s3_prefix=artifact_prefix,
            created_by=loaded_by,
        )
    complete_training_run(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_run_id,
        mlflow_run_id=actual_run_id,
        best_model_type=str(verified.get("model_name") or "external_mlflow_model"),
        metrics=metrics,
    )
    activate_champion_model(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_run_id,
        model_name=str(verified.get("registered_model_name") or expected_name),
        version=str(verified.get("model_version") or training_run_id),
        artifact_uri=str(mlflow_pointer["object_uri"]),
        preprocessing_uri=preprocessing_uri,
        schema_uri=schema_uri,
        metrics=metrics,
    )
    return {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "training_run_id": training_run_id,
        "status": "approved_champion_active",
        "stage": "champion_model_loaded",
        "loaded_at": metrics["champion_load"]["loaded_at"],
        "loaded_by": loaded_by,
        "notes": notes or "",
        "mlflow": verified,
        "artifact_cache": str(artifact_cache),
        "onnx_model_cache": str(onnx_model_path),
        "schema_outputs": [item.get("name") for item in schema.get("outputs", []) if isinstance(item, dict)],
    }


def reconcile_champion_model(*, workspace_id: str, project_id: str, reconciled_by: str = "Mirai admin", notes: str | None = None) -> dict[str, Any]:
    """Legacy compatibility helper for older tests/clients.

    New app routes use `load_champion_model`, which is the stricter ONNX-serving
    contract. This helper preserves the previous imported-candidate prerequisite
    for callers that still use the old name directly.
    """
    verified = verify_champion_mlflow_model(workspace_id=workspace_id, project_id=project_id)
    mlflow_run_id = str(verified["mlflow_run_id"])
    training_run = get_training_run_by_mlflow_run_id(workspace_id, project_id, mlflow_run_id)
    if not training_run:
        raise ValueError("MLflow champion run must be imported into Mirai as a reviewable candidate before activation")

    artifact_cache = download_run_artifacts(project_id, mlflow_run_id, include_quality=True, include_predictions=True)
    training_run_id = str(training_run["training_run_id"])
    metrics = {
        **(training_run.get("metrics_json") if isinstance(training_run.get("metrics_json"), dict) else {}),
        **(verified.get("metrics") if isinstance(verified.get("metrics"), dict) else {}),
        "mlflow_import": {
            "run_id": mlflow_run_id,
            "registered_model_name": verified.get("registered_model_name"),
            "model_version": verified.get("model_version"),
            "alias": "champion",
            "model_uri": verified.get("model_uri"),
        },
        "champion_load": {
            "status": "approved_champion_active",
            "loaded_by": reconciled_by,
            "loaded_at": _now(),
            "notes": notes or "",
        },
    }
    storage_config = _project_storage_config_for_training(workspace_id, project_id)
    artifact_prefix = validate_workspace_object_key(storage_config, f"{storage_config.normalized_prefix}/mlflow-imports/{training_run_id}") + "/"
    mlflow_pointer = durable_artifact_pointer_for_project(project_id, "mlflow_artifacts", workspace_id=workspace_id)
    activate_champion_model(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_run_id,
        model_name=str(verified.get("registered_model_name") or registered_model_name_for_project(project_id)),
        version=str(verified.get("model_version") or training_run_id),
        artifact_uri=str(mlflow_pointer["object_uri"]),
        preprocessing_uri=f"{artifact_prefix}preprocessing.json",
        schema_uri=f"{artifact_prefix}schema.json",
        metrics=metrics,
    )
    return {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "training_run_id": training_run_id,
        "status": "approved_champion_active",
        "stage": "champion_model_loaded",
        "loaded_at": metrics["champion_load"]["loaded_at"],
        "loaded_by": reconciled_by,
        "notes": notes or "",
        "mlflow": verified,
        "artifact_cache": str(artifact_cache),
    }


def get_training_status(project_id: str, dataset_id: str, session_id: str, training_request_id: str) -> dict[str, Any]:
    return read_status(project_id, dataset_id, session_id, f"training_{training_request_id}", default={"status": "not_started"})
