from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
from typing import Any
import zipfile

import pandas as pd

from ..platform.control_plane import get_project_runtime_state
from ..data_preprocessing.ingestion_sessions import list_ingestion_sessions, session_workspace
from ..model_serving.registry import durable_artifact_pointer_for_project, download_aliased_run_artifacts, download_run_artifacts, get_registered_model_metadata, loaded_champion_mlflow_import, tracking_uri
from ..platform.workspace_storage import local_object_storage_root


BACKEND_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND_ROOT.parent
OBJECT_STORE_ROOT = local_object_storage_root()
REFERENCE_DATA_ROOT = Path(os.getenv("DOE_REFERENCE_DATA_ROOT", REPO_ROOT / "data" / "reference"))
REAL_PROJECT_ID = "pem_fuel_cell_real_cathode_degradation"
TRAINING_ARTIFACT_DIR = REFERENCE_DATA_ROOT / "pem_fuel_cell_cathode_degradation" / "training_artifacts" / "latest"
SCIENTIST_REVIEW_DIR = OBJECT_STORE_ROOT / "model_quality_reviews"


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is pd.NA:
        return None
    return value


MODEL_QUALITY_REQUIRED_ARTIFACTS = ["metrics_summary.json", "candidate_comparison.csv"]


def _is_complete_quality_artifact_dir(path: Path) -> bool:
    return path.exists() and all((path / name).exists() for name in MODEL_QUALITY_REQUIRED_ARTIFACTS)


def _latest_intake_training_artifact_dir(project_id: str) -> Path | None:
    sessions = [session for session in list_ingestion_sessions() if session.get("project_id") == project_id]
    for session in sorted(sessions, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True):
        workspace = session_workspace(str(session["project_id"]), str(session["dataset_id"]), str(session["ingestion_session_id"]))
        artifact_dir = workspace["training_latest"]
        if _is_complete_quality_artifact_dir(artifact_dir):
            return artifact_dir
    return None


def _latest_mlflow_training_artifact_dir(project_id: str, *, include_predictions: bool = False) -> Path | None:
    try:
        path = download_aliased_run_artifacts(project_id, alias="challenger", include_quality=True, include_predictions=include_predictions)
    except Exception:
        return None
    return path if _is_complete_quality_artifact_dir(path) else None


def _champion_not_loaded_message(project_id: str) -> str:
    return f"Champion model is not loaded yet for project_id={project_id}; promote a version to champion in MLflow, then use Load champion model."


def _imported_mlflow_training_artifact_dir(project_id: str, workspace_id: str | None, *, include_predictions: bool = False) -> Path | None:
    if not workspace_id:
        return None
    mlflow_import = loaded_champion_mlflow_import(project_id, workspace_id)
    if not isinstance(mlflow_import, dict) or not mlflow_import.get("run_id"):
        return None
    path = download_run_artifacts(project_id, str(mlflow_import["run_id"]), include_quality=True, include_predictions=include_predictions)
    return path if _is_complete_quality_artifact_dir(path) else None


def _artifact_dir(project_id: str, workspace_id: str | None = None) -> Path:
    if workspace_id:
        runtime_state = get_project_runtime_state(workspace_id, project_id)
        if runtime_state:
            imported_dir = _imported_mlflow_training_artifact_dir(project_id, workspace_id)
            if imported_dir is not None:
                return imported_dir
            raise ValueError(_champion_not_loaded_message(project_id))
    imported_dir = _imported_mlflow_training_artifact_dir(project_id, workspace_id)
    if imported_dir is not None:
        return imported_dir
    intake_dir = _latest_intake_training_artifact_dir(project_id)
    if intake_dir is not None:
        return intake_dir
    if not workspace_id:
        mlflow_dir = _latest_mlflow_training_artifact_dir(project_id)
        if mlflow_dir is not None:
            return mlflow_dir
    if project_id == REAL_PROJECT_ID and _is_complete_quality_artifact_dir(TRAINING_ARTIFACT_DIR):
        return TRAINING_ARTIFACT_DIR
    raise ValueError(f"Model quality is not available yet for project_id={project_id}; train the uploaded project first")


def get_latest_runs(project_id: str, max_results: int = 10) -> list[dict[str, Any]]:
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(tracking_uri())
        client = MlflowClient(tracking_uri=tracking_uri(), registry_uri=tracking_uri())
        experiment = client.get_experiment_by_name(project_id)
        if experiment is None:
            return []
        runs = client.search_runs(
            [experiment.experiment_id],
            order_by=["attributes.start_time DESC"],
            max_results=max_results,
        )
        return [
            {
                "run_id": run.info.run_id,
                "run_name": run.data.tags.get("mlflow.runName", ""),
                "status": run.info.status,
                "start_time": run.info.start_time,
                "end_time": run.info.end_time,
                "model_family": run.data.tags.get("model_family", ""),
                "quality_label": run.data.tags.get("quality_label", ""),
                "params": dict(run.data.params),
                "metrics": dict(run.data.metrics),
            }
            for run in runs
        ]
    except Exception:
        return []


def get_metrics(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    return _read_json(_artifact_dir(project_id, workspace_id) / "metrics_summary.json", default={})


def get_preprocessing_report(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    return _read_json(_artifact_dir(project_id, workspace_id) / "preprocessing_report.json", default={})


def _prediction_path(project_id: str, workspace_id: str | None = None) -> Path:
    if workspace_id and get_project_runtime_state(workspace_id, project_id):
        mlflow_dir = _imported_mlflow_training_artifact_dir(project_id, workspace_id, include_predictions=True)
        if mlflow_dir is None:
            raise ValueError(_champion_not_loaded_message(project_id))
        return mlflow_dir / "predictions.csv"
    artifact_dir = _artifact_dir(project_id, workspace_id)
    path = artifact_dir / "predictions.csv"
    if not path.exists() and not workspace_id:
        mlflow_dir = _latest_mlflow_training_artifact_dir(project_id, include_predictions=True)
        if mlflow_dir is not None:
            path = mlflow_dir / "predictions.csv"
    return path


def _display_path(path: Path) -> str:
    for root in (BACKEND_ROOT, REPO_ROOT):
        try:
            return str(path.relative_to(root))
        except ValueError:
            continue
    return str(path)


def get_artifact_summary(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    artifact_dir = _artifact_dir(project_id, workspace_id)
    summary = _read_json(artifact_dir / "artifact_summary.json", default={})
    if not summary:
        files = sorted(_display_path(path) for path in artifact_dir.rglob("*") if path.is_file()) if artifact_dir.exists() else []
        summary = {"project_id": project_id, "artifact_dir": str(artifact_dir), "files": files}
    durable_pointers = {}
    pointer_kinds = ["dataset", "canonical_table", "preprocessing_output", "bo_state", "review_file"] if workspace_id else ["dataset", "canonical_table", "preprocessing_output", "mlflow_artifacts", "onnx_model", "bo_state", "review_file"]
    for artifact_kind in pointer_kinds:
        try:
            durable_pointers[artifact_kind] = durable_artifact_pointer_for_project(project_id, artifact_kind, workspace_id=workspace_id)
        except Exception:
            continue
    if durable_pointers:
        summary["durable_artifact_pointers"] = durable_pointers
        summary["durable_state_note"] = "Railway mode should resolve durable state from Postgres artifact pointers and object storage. Loaded MLflow champion artifacts are resolved by MLflow run_id/model_uri; opaque S3 keys are an MLflow implementation detail."
    predictions_path = _prediction_path(project_id, workspace_id)
    if predictions_path.exists():
        summary["predictions_artifact"] = str(predictions_path)
        summary["prediction_diagnostics_available"] = True
    else:
        summary["prediction_diagnostics_available"] = False
    return summary


def _load_predictions_frame(project_id: str, workspace_id: str | None = None) -> pd.DataFrame:
    path = _prediction_path(project_id, workspace_id)
    if not path.exists():
        raise FileNotFoundError("Prediction diagnostics are not available yet. Run real-data training to generate predictions.csv.")
    return pd.read_csv(path)


def _normalize_filter(values: str | None) -> set[str] | None:
    if not values:
        return None
    normalized = {item.strip() for item in values.split(",") if item.strip()}
    return normalized or None


def _filter_predictions(frame: pd.DataFrame, *, model_name: str | None = None, splits: str | None = None, limit: int | None = None) -> tuple[pd.DataFrame, bool]:
    filtered = frame.copy()
    if model_name:
        filtered = filtered[filtered["model_name"] == model_name]
    split_values = _normalize_filter(splits)
    if split_values is not None:
        filtered = filtered[filtered["split"].isin(split_values)]
    truncated = False
    if limit is not None and limit > 0 and len(filtered) > limit:
        filtered = filtered.head(limit)
        truncated = True
    return filtered, truncated


def get_predictions(project_id: str, *, model_name: str | None = None, splits: str | None = None, limit: int = 5000, workspace_id: str | None = None) -> dict[str, Any]:
    frame = _load_predictions_frame(project_id, workspace_id)
    filtered, truncated = _filter_predictions(frame, model_name=model_name, splits=splits, limit=limit)
    return {
        "project_id": project_id,
        "source": "training_run_predictions",
        "columns": list(filtered.columns),
        "rows": json.loads(filtered.where(pd.notnull(filtered), None).to_json(orient="records")),
        "row_count": int(len(filtered)),
        "total_row_count": int(len(frame)),
        "truncated": truncated,
    }


def _predictions_long(frame: pd.DataFrame) -> pd.DataFrame:
    legacy_output_units = {
        "bol_current_density": "A/cm²",
        "eol_current_density": "A/cm²",
        "bol_ecsa": "m²/gPt",
        "ecsa_loss": "fraction",
    }
    output_names = sorted(column.removesuffix("_true") for column in frame.columns if column.endswith("_true") and f"{column.removesuffix('_true')}_pred" in frame.columns)
    output_units = {name: legacy_output_units.get(name, "") for name in output_names}
    context_columns = [
        column
        for column in [
            "project_id",
            "model_name",
            "model_type",
            "source",
            "split",
            "cell_id",
            "row_index",
            "experiment_id",
            "condition_id",
            "result_id",
            "x1",
            "x2",
            "x3",
            "x4",
            "x5",
            "x6",
            "x7",
            "pt_c_ratio",
            "i_c_ratio",
            "ionomer_ew",
            "operating_rh",
            "operating_voltage",
            "ast_rh",
            "ast_upl",
            "catalyst_type",
            "support_type",
        ]
        if column in frame.columns
    ]
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        context = {column: row[column] for column in context_columns}
        for output_name, unit in output_units.items():
            true_col = f"{output_name}_true"
            pred_col = f"{output_name}_pred"
            if true_col not in frame.columns or pred_col not in frame.columns:
                continue
            y_true = row[true_col]
            y_pred = row[pred_col]
            rows.append(
                {
                    **context,
                    "output_name": output_name,
                    "unit": unit,
                    "y_true": y_true,
                    "y_pred": y_pred,
                    "residual": row.get(f"{output_name}_residual", y_true - y_pred),
                    "abs_error": row.get(f"{output_name}_abs_error", abs(y_true - y_pred)),
                }
            )
    return pd.DataFrame(rows)


def export_predictions_zip(project_id: str, *, model_name: str | None = None, splits: str | None = None, workspace_id: str | None = None) -> bytes:
    frame = _load_predictions_frame(project_id, workspace_id)
    filtered, _ = _filter_predictions(frame, model_name=model_name, splits=splits, limit=None)
    long_frame = _predictions_long(filtered)
    readme = f"""Mirai DoE prediction diagnostics export

Project: {project_id}
Source: Training-run predictions

Files:
- predictions_wide.csv: one row per source experiment row and model, with inputs/context plus true/predicted output columns.
- predictions_long.csv: one row per output prediction, convenient for plotting/parity/residual analysis.
- README.txt: this file.

Residual definition:
residual = y_true - y_pred

Split definitions:
- train: rows used for fitting the surrogate model.
- validation: held-out cells used for model selection.
- test: held-out cells used for final quality reporting.
- BO replay uses train+validation rows; test remains untouched for model-quality evaluation.

Current source label:
Training-run predictions are generated during the training/evaluation run. Future DoE live predictions should be labeled separately because they come from the served model at prediction time.
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("predictions_wide.csv", filtered.to_csv(index=False))
        archive.writestr("predictions_long.csv", long_frame.to_csv(index=False))
        archive.writestr("README.txt", readme)
    return buffer.getvalue()


def get_active_model_metadata(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    metadata = get_registered_model_metadata(project_id)
    runtime_state = get_project_runtime_state(workspace_id, project_id) if workspace_id else None
    champion = runtime_state.get("champion_model") if isinstance(runtime_state, dict) else None
    candidate = runtime_state.get("candidate_model") if isinstance(runtime_state, dict) else None
    mlflow_import = loaded_champion_mlflow_import(project_id, workspace_id) if workspace_id else None
    local_metadata: dict[str, Any] = {}
    try:
        artifact_dir = _artifact_dir(project_id, workspace_id)
        local_metadata = _read_json(artifact_dir / "metadata.json", default={})
        cache_status = {
            "status": "available",
            "artifact_dir": str(artifact_dir),
            "metrics_summary": (artifact_dir / "metrics_summary.json").exists(),
            "candidate_comparison": (artifact_dir / "candidate_comparison.csv").exists(),
            "predictions": (artifact_dir / "predictions.csv").exists(),
        }
    except Exception as exc:  # noqa: BLE001 - returned as operator-facing state.
        cache_status = {"status": "unavailable", "message": str(exc)}
    if champion and mlflow_import:
        served_source = "loaded_champion"
        lifecycle_status = "approved_champion_active"
    elif candidate:
        served_source = "candidate_review"
        lifecycle_status = "candidate_ready_for_review"
    else:
        served_source = "packaged artifact" if not workspace_id else "champion_not_loaded"
        lifecycle_status = "champion_not_loaded" if workspace_id and runtime_state else "awaiting_local_run_import"
    traceability = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "registered_model_name": (mlflow_import or {}).get("registered_model_name") or metadata.get("registered_model_name"),
        "alias": (mlflow_import or {}).get("alias") or "champion",
        "model_version": (mlflow_import or {}).get("model_version"),
        "run_id": (mlflow_import or {}).get("run_id"),
        "model_uri": (mlflow_import or {}).get("model_uri"),
        "model_source": (mlflow_import or {}).get("model_source"),
        "tracking_uri": (mlflow_import or {}).get("tracking_uri") or metadata.get("tracking_uri"),
        "loaded_at": (mlflow_import or {}).get("loaded_at"),
        "loaded_by": (mlflow_import or {}).get("loaded_by"),
        "required_artifacts": (mlflow_import or {}).get("required_artifacts"),
        "cache_status": cache_status,
    }
    metadata["local_metadata"] = local_metadata
    metadata["served_source"] = served_source
    metadata["lifecycle_status"] = lifecycle_status
    metadata["mlflow_traceability"] = traceability
    if champion:
        metadata["mirai_champion_model"] = champion
    if candidate:
        metadata["mirai_candidate_model"] = candidate
    if workspace_id and runtime_state and not mlflow_import:
        metadata["operator_warning"] = _champion_not_loaded_message(project_id)
    return metadata


def get_candidate_comparison(project_id: str, workspace_id: str | None = None) -> list[dict[str, Any]]:
    path = _artifact_dir(project_id, workspace_id) / "candidate_comparison.csv"
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    return _json_safe(json.loads(frame.where(pd.notnull(frame), None).to_json(orient="records")))


def _default_review(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "status": "pending_review",
        "decision": "pending",
        "reviewer": None,
        "notes": "",
        "updated_at": None,
    }


def get_scientist_review(project_id: str) -> dict[str, Any]:
    path = SCIENTIST_REVIEW_DIR / f"{project_id}.json"
    return _read_json(path, default=_default_review(project_id))


def save_scientist_review(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_scientist_review(project_id)
    updated = {
        **existing,
        **payload,
        "project_id": project_id,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return _write_json(SCIENTIST_REVIEW_DIR / f"{project_id}.json", updated)


def get_model_quality_summary(project_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    warning: str | None = None
    try:
        metrics = get_metrics(project_id, workspace_id)
        preprocessing_report = get_preprocessing_report(project_id, workspace_id)
        artifact_summary = get_artifact_summary(project_id, workspace_id)
        candidate_comparison = get_candidate_comparison(project_id, workspace_id)
    except ValueError as exc:
        if "Champion model is not loaded yet" not in str(exc):
            raise
        warning = str(exc)
        metrics = {}
        preprocessing_report = {}
        artifact_summary = {"project_id": project_id, "prediction_diagnostics_available": False, "warning": warning}
        candidate_comparison = []
    return _json_safe(
        {
            "project_id": project_id,
            "quality_label": "all-cells MVP",
            "warning": warning,
            "metrics": metrics,
            "preprocessing_report": preprocessing_report,
            "artifact_summary": artifact_summary,
            "active_model": get_active_model_metadata(project_id, workspace_id),
            "scientist_review": get_scientist_review(project_id),
            "latest_runs": get_latest_runs(project_id),
            "candidate_comparison": candidate_comparison,
            "ai_preprocessing_assistant": {
                "status": "placeholder_not_active",
                "message": "AI preprocessing assistant is a future placeholder. No autonomous preprocessing is active yet.",
                "proposed_transformations": [],
                "rationale": "Future agent will propose transformations for scientist review before activation.",
                "review_affordance": "accept/reject placeholders only",
            },
        }
    )
