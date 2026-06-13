from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import mimetypes
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from .control_plane import complete_training_run, create_training_run, fail_training_run
from .data_intake import BACKEND_ROOT, DATA_INTAKE_ROOT, get_ingestion_session, read_status, session_workspace, write_status
from .domain_metadata import build_domain_metadata, infer_template_id
from .db import postgres_control_plane_required
from .mlflow_registry import registered_model_name_for_project
from .workspace_storage import put_workspace_object, workspace_s3_config_from_env
from .preprocessing_review import get_preprocessing_review_report
from ml_lifecycle.training.generic_tabular_doe.train import train_generic_project
from ml_lifecycle.ingesting.fuel_cell_doe_demo.schema import OUTPUT_DIR as REAL_CANONICAL_DIR, PROJECT_ID as REAL_FUEL_CELL_PROJECT_ID, TRAINING_ARTIFACT_DIR
from ml_lifecycle.training.fuel_cell_doe_demo.train import train_models


logger = logging.getLogger(__name__)


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
    "outputs": ["bol_current_density", "eol_current_density", "bol_ecsa", "ecsa_loss"],
    "selection": "validation weighted nRMSE chooses the challenger candidate; champion remains manual in MLflow",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_dir(project_id: str, dataset_id: str, session_id: str) -> Path:
    return DATA_INTAKE_ROOT / "projects" / project_id / "datasets" / dataset_id / "ingestion_sessions" / session_id


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
        if path.name in {"raw_reference_extracted", "raw_extractor_workspace", "01-Data"}:
            # Raw/reference ZIPs and PEM extractor workspaces must stay out of activated
            # project artifacts. They can contain 10k+ raw CSV files and are not needed
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
    if template_id in {"generic_tabular_doe"} or project_id != REAL_FUEL_CELL_PROJECT_ID:
        return {
            "mode": "session_artifacts_active_in_object_store",
            "canonical_source": str(canonical.relative_to(BACKEND_ROOT)),
            "artifact_target": str(training_latest.relative_to(BACKEND_ROOT)),
            "professional_follow_up": "Use immutable MinIO/object-storage artifact URIs plus per-project activation records for multi-client deployments.",
        }
    _copy_tree_contents(canonical, REAL_CANONICAL_DIR)
    _copy_tree_contents(training_latest, TRAINING_ARTIFACT_DIR / "latest")
    return {
        "mode": "copied_session_artifacts_to_active_runtime_latest",
        "canonical_target": str(REAL_CANONICAL_DIR.relative_to(BACKEND_ROOT)),
        "training_artifact_target": str((TRAINING_ARTIFACT_DIR / "latest").relative_to(BACKEND_ROOT)),
        "professional_follow_up": "Use immutable MinIO/object-storage artifact URIs plus per-project activation records for multi-client deployments.",
    }


def _upload_training_artifacts_to_s3(workspace_id: str, project_id: str, training_run_id: str, artifact_dir: Path) -> dict[str, Any]:
    try:
        config = workspace_s3_config_from_env(workspace_id)
        uploaded: list[dict[str, Any]] = []
        prefix = f"workspaces/{workspace_id}/projects/{project_id}/training_runs/{training_run_id}"
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
    template_id = schema.get("metadata", {}).get("template_id") if isinstance(schema.get("metadata"), dict) else None
    use_generic_training = template_id in {"generic_tabular_doe"}

    status_payload = {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "training_request_id": training_request_id,
        "status": "running",
        "stage": "training_generic_tabular_models" if use_generic_training else "training_real_fuel_cell_models",
    }
    write_status(project_id, dataset_id, session_id, f"training_{training_request_id}", status_payload)
    session = get_ingestion_session(project_id, dataset_id, session_id)
    workspace_id = str(session.get("workspace_id") or "fraunhofer" if project_id == REAL_FUEL_CELL_PROJECT_ID else session.get("workspace_id") or "mirai-engineering")
    artifact_prefix = f"workspaces/{workspace_id}/projects/{project_id}/training_runs/{training_request_id}/"
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
        if use_generic_training:
            result = train_generic_project(project_id=project_id, data_dir=canonical, artifact_dir=training_latest, training_config=request.get("training_config"))
        else:
            result = train_models(
                project_id=REAL_FUEL_CELL_PROJECT_ID,
                register_mlflow=True,
                set_alias="challenger",
                mlflow_experiment_name=project_id,
                registered_model_name=registered_model_name_for_project(project_id),
                dataset_id=dataset_id,
                ingestion_session_id=session_id,
                preprocessing_report_id=f"{session_id}:preprocessing_report",
                training_request_id=training_request_id,
                data_dir=canonical,
                artifact_dir=training_latest,
                training_config=request.get("training_config"),
            )
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
    activation = activate_session_artifacts_for_model_quality(project_id, dataset_id, session_id)
    s3_upload = _upload_training_artifacts_to_s3(workspace_id, project_id, training_request_id, training_latest)
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
    complete_training_run(
        workspace_id=workspace_id,
        project_id=project_id,
        training_run_id=training_request_id,
        mlflow_run_id=mlflow_run_id,
        best_model_type=str(result.get("best_model_name") or result.get("best_model") or "unknown") if isinstance(result, dict) else "unknown",
        metrics=metrics if isinstance(metrics, dict) else {},
        model_artifact_uri=f"{artifact_prefix}model.onnx",
        preprocessing_uri=f"{artifact_prefix}preprocessing.json",
        schema_uri=f"{artifact_prefix}schema.json",
    )
    request["status"] = "completed"
    request["completed_at"] = completed["completed_at"]
    request["result"] = result
    request["activation"] = activation
    request["route_after_completion"] = completed["route_after_completion"]
    _write_training_request(project_id, dataset_id, session_id, request)
    return completed


def get_training_status(project_id: str, dataset_id: str, session_id: str, training_request_id: str) -> dict[str, Any]:
    return read_status(project_id, dataset_id, session_id, f"training_{training_request_id}", default={"status": "not_started"})
