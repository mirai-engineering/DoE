from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
from typing import Any
import zipfile

import pandas as pd

from .data_intake import list_ingestion_sessions, session_workspace
from .mlflow_registry import durable_artifact_pointer_for_project, download_aliased_run_artifacts, get_registered_model_metadata, tracking_uri
from .workspace_storage import local_object_storage_root


BACKEND_ROOT = Path(__file__).resolve().parents[2]
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


def _artifact_dir(project_id: str) -> Path:
    intake_dir = _latest_intake_training_artifact_dir(project_id)
    if intake_dir is not None:
        return intake_dir
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


def get_metrics(project_id: str) -> dict[str, Any]:
    return _read_json(_artifact_dir(project_id) / "metrics_summary.json", default={})


def get_preprocessing_report(project_id: str) -> dict[str, Any]:
    return _read_json(_artifact_dir(project_id) / "preprocessing_report.json", default={})


def _prediction_path(project_id: str) -> Path:
    artifact_dir = _artifact_dir(project_id)
    path = artifact_dir / "predictions.csv"
    if not path.exists():
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


def get_artifact_summary(project_id: str) -> dict[str, Any]:
    artifact_dir = _artifact_dir(project_id)
    summary = _read_json(artifact_dir / "artifact_summary.json", default={})
    if not summary:
        files = sorted(_display_path(path) for path in artifact_dir.rglob("*") if path.is_file()) if artifact_dir.exists() else []
        summary = {"project_id": project_id, "artifact_dir": str(artifact_dir), "files": files}
    durable_pointers = {}
    for artifact_kind in ["dataset", "canonical_table", "preprocessing_output", "mlflow_artifacts", "onnx_model", "bo_state", "review_file"]:
        try:
            durable_pointers[artifact_kind] = durable_artifact_pointer_for_project(project_id, artifact_kind)
        except Exception:
            continue
    if durable_pointers:
        summary["durable_artifact_pointers"] = durable_pointers
        summary["durable_state_note"] = "Railway mode should resolve durable state from Postgres artifact pointers and object storage, not from backend/mlruns copied into the image."
    predictions_path = _prediction_path(project_id)
    if predictions_path.exists():
        summary["predictions_artifact"] = str(predictions_path)
        summary["prediction_diagnostics_available"] = True
    else:
        summary["prediction_diagnostics_available"] = False
    return summary


def _load_predictions_frame(project_id: str) -> pd.DataFrame:
    path = _prediction_path(project_id)
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


def get_predictions(project_id: str, *, model_name: str | None = None, splits: str | None = None, limit: int = 5000) -> dict[str, Any]:
    frame = _load_predictions_frame(project_id)
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


def export_predictions_zip(project_id: str, *, model_name: str | None = None, splits: str | None = None) -> bytes:
    frame = _load_predictions_frame(project_id)
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


def get_active_model_metadata(project_id: str) -> dict[str, Any]:
    metadata = get_registered_model_metadata(project_id)
    artifact_dir = _artifact_dir(project_id)
    local_metadata = _read_json(artifact_dir / "metadata.json", default={})
    metrics = _read_json(artifact_dir / "metrics_summary.json", default={})
    aliases = metadata.get("aliases", {}) if isinstance(metadata.get("aliases"), dict) else {}
    if aliases.get("champion"):
        served_source = "champion"
    elif aliases.get("challenger"):
        served_source = "challenger"
    elif _latest_intake_training_artifact_dir(project_id) is not None:
        served_source = "session artifact"
        best_model_name = str(local_metadata.get("best_model") or metrics.get("best_model_name") or metrics.get("best_model") or "session_model")
        aliases = {
            **aliases,
            "challenger": {
                "name": best_model_name,
                "version": "session",
                "run_id": None,
                "source": "training_artifacts/latest",
            },
        }
        metadata["aliases"] = aliases
    else:
        served_source = "packaged artifact"
    metadata["local_metadata"] = local_metadata
    metadata["served_source"] = served_source
    return metadata


def get_candidate_comparison(project_id: str) -> list[dict[str, Any]]:
    path = _artifact_dir(project_id) / "candidate_comparison.csv"
    if not path.exists():
        return []
    return pd.read_csv(path).to_dict(orient="records")


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


def get_model_quality_summary(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "quality_label": "all-cells MVP",
        "metrics": get_metrics(project_id),
        "preprocessing_report": get_preprocessing_report(project_id),
        "artifact_summary": get_artifact_summary(project_id),
        "active_model": get_active_model_metadata(project_id),
        "scientist_review": get_scientist_review(project_id),
        "latest_runs": get_latest_runs(project_id),
        "candidate_comparison": get_candidate_comparison(project_id),
        "ai_preprocessing_assistant": {
            "status": "placeholder_not_active",
            "message": "AI preprocessing assistant is a future placeholder. No autonomous preprocessing is active yet.",
            "proposed_transformations": [],
            "rationale": "Future agent will propose transformations for scientist review before activation.",
            "review_affordance": "accept/reject placeholders only",
        },
    }
