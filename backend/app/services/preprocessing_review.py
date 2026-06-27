from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from .data_intake import (
    BACKEND_ROOT,
    DATA_INTAKE_ROOT,
    OBJECT_STORE_ROOT,
    ensure_session_workspace,
    get_ingestion_session,
    read_status,
    reset_workspace_dir,
    write_status,
)
from .domain_metadata import build_domain_metadata, infer_template_id
from .db import postgres_control_plane_required
from .lifecycle_artifacts import (
    persist_multiple_artifact_sets,
    persist_session_artifact_set,
    public_artifact_persistence_summary,
    read_workspace_artifact_bytes,
    session_artifact_prefix,
    _resolve_storage_config,
)
from .project_registry import clear_registry_cache
from .workspace_storage import WorkspaceStorageConfig, validate_workspace_object_key
from ml_lifecycle.ingesting.generic_tabular_doe.contract import ContractValidationError, load_and_validate_contract, schema_from_contract
from ml_lifecycle.ingesting.generic_tabular_doe.preprocessing import _prepare_package_root, build_generic_preprocessing_artifacts


logger = logging.getLogger(__name__)


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


def validate_fuel_cell_package(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    """Deprecated compatibility wrapper for older clients.

    Runtime intake no longer validates a separate fuel-cell package shape. This
    endpoint reports the generic Mirai contract validation result so legacy
    sessions/clients can read safely without reviving a second intake path.
    """
    validation = _validate_generic_contract(project_id, dataset_id, session_id)
    return {
        **validation,
        "package_type": "mirai_contract_package",
        "deprecated_endpoint": True,
        "message": validation.get("message") or ("Mirai contract is valid." if validation.get("valid") else "Mirai contract blocks preprocessing."),
    }


def _profile_frame(path: Path, relative_path: str, max_rows: int = 5000) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path, nrows=max_rows)
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, nrows=max_rows)
    else:
        return {"path": relative_path, "supported": False, "reason": "Unsupported file type for lightweight tabular profiling"}

    numeric = frame.select_dtypes(include="number")
    profile: dict[str, Any] = {
        "path": relative_path,
        "supported": True,
        "rows_profiled": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "columns": list(map(str, frame.columns)),
        "missing_by_column": {str(col): int(count) for col, count in frame.isna().sum().to_dict().items()},
        "duplicate_rows": int(frame.duplicated().sum()),
        "numeric_summary": {},
    }
    if not numeric.empty:
        summary = numeric.describe().where(pd.notnull(numeric.describe()), None)
        profile["numeric_summary"] = json.loads(summary.to_json())
    return profile


def _try_ydata_profile(primary_file: Path, report_dir: Path) -> dict[str, Any]:
    try:
        from ydata_profiling import ProfileReport  # type: ignore
    except Exception:
        return {"enabled": False, "reason": "ydata-profiling is not installed in this environment"}

    try:
        if primary_file.suffix.lower() == ".csv":
            frame = pd.read_csv(primary_file, nrows=10000)
        elif primary_file.suffix.lower() in {".xlsx", ".xls"}:
            frame = pd.read_excel(primary_file, nrows=10000)
        else:
            return {"enabled": False, "reason": "No supported primary CSV/XLSX file for ydata profile"}
        report_dir.mkdir(parents=True, exist_ok=True)
        html_path = report_dir / "ydata_profile.html"
        json_path = report_dir / "ydata_profile.json"
        profile = ProfileReport(frame, title="Mirai Data Intake EDA", minimal=True)
        profile.to_file(html_path)
        json_path.write_text(profile.to_json(), encoding="utf-8")
        return {
            "enabled": True,
            "html_report": str(html_path.relative_to(BACKEND_ROOT)),
            "json_report": str(json_path.relative_to(BACKEND_ROOT)),
        }
    except Exception as exc:  # noqa: BLE001 - profile generation should fall back, not fail ingestion.
        return {"enabled": False, "reason": f"ydata-profiling failed: {exc}"}


def _validate_generic_contract(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    try:
        package_root, package_inventory = _prepare_package_root(workspace["raw"], workspace["inventory"])
        _write_json(workspace["inventory"] / "package_inventory.json", package_inventory)
        contract = load_and_validate_contract(package_root)
        return {
            "valid": True,
            "errors": [],
            "template_id": contract.get("project", {}).get("template_id"),
            "table_count": len(contract.get("tables", [])),
            "column_count": len(contract.get("columns", [])),
            "input_count": len([c for c in contract.get("columns", []) if c.get("role") == "input"]),
            "output_count": len([c for c in contract.get("columns", []) if c.get("role") == "output"]),
            "message": "Mirai contract is complete enough for preprocessing.",
        }
    except ContractValidationError as exc:
        return {"valid": False, "errors": exc.errors, "template_id": None, "message": "Mirai contract blocks preprocessing."}


def _should_use_generic_contract(project_id: str, dataset_id: str, session_id: str) -> bool:
    validation = _validate_generic_contract(project_id, dataset_id, session_id)
    return bool(validation.get("valid")) and validation.get("template_id") in {"generic_tabular_doe"}


def _session_workspace_id(project_id: str, dataset_id: str, session_id: str) -> str | None:
    try:
        session = get_ingestion_session(project_id, dataset_id, session_id)
    except Exception:  # noqa: BLE001 - callers handle missing artifacts separately.
        return None
    workspace_id = session.get("workspace_id")
    return str(workspace_id) if workspace_id else None


def _storage_config_for_session(project_id: str, dataset_id: str, session_id: str) -> WorkspaceStorageConfig | None:
    workspace_id = _session_workspace_id(project_id, dataset_id, session_id)
    if not workspace_id:
        return None
    try:
        return _resolve_storage_config(workspace_id, project_id)
    except Exception as exc:  # noqa: BLE001 - local/dev may not have object storage configured.
        logger.debug("Object-storage config unavailable for project_id=%s session_id=%s: %s", project_id, session_id, exc)
        return None


def _hydrate_artifact_from_storage(project_id: str, dataset_id: str, session_id: str, artifact_set: str, name: str, destination: Path) -> bool:
    config = _storage_config_for_session(project_id, dataset_id, session_id)
    if config is None:
        return False
    try:
        object_key = validate_workspace_object_key(config, f"{session_artifact_prefix(config, artifact_set, dataset_id, session_id)}/{name}")
        body = read_workspace_artifact_bytes(config, object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        return True
    except Exception as exc:  # noqa: BLE001 - absence means caller may regenerate/fallback.
        logger.debug("Artifact hydration miss for %s/%s project_id=%s session_id=%s: %s", artifact_set, name, project_id, session_id, exc)
        return False


def _read_json_local_or_storage(project_id: str, dataset_id: str, session_id: str, artifact_set: str, name: str, local_path: Path, default: Any = None) -> Any:
    payload = _read_json(local_path, default=None)
    if payload is not None:
        return payload
    if _hydrate_artifact_from_storage(project_id, dataset_id, session_id, artifact_set, name, local_path):
        return _read_json(local_path, default=default)
    return default


def _public_preprocessing_status(status: dict[str, Any]) -> dict[str, Any]:
    hidden = {"report_path", "canonical_dir", "training_artifact_dir"}
    public = {key: value for key, value in status.items() if key not in hidden}
    if "object_storage" in public:
        public["object_storage"] = public_artifact_persistence_summary(public["object_storage"])
    return public


def _artifact_exists_in_storage(project_id: str, dataset_id: str, session_id: str, artifact_set: str, name: str) -> bool:
    config = _storage_config_for_session(project_id, dataset_id, session_id)
    if config is None:
        return False
    try:
        object_key = validate_workspace_object_key(config, f"{session_artifact_prefix(config, artifact_set, dataset_id, session_id)}/{name}")
        read_workspace_artifact_bytes(config, object_key)
        return True
    except Exception:  # noqa: BLE001 - absence/unconfigured both mean unavailable.
        return False


def _persist_current_preprocessing_artifacts(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    session = get_ingestion_session(project_id, dataset_id, session_id)
    workspace_id = str(session.get("workspace_id") or "")
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    result = persist_multiple_artifact_sets(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=workspace_id,
        artifact_sets={
            "canonical": workspace["canonical"],
            "preprocessing_artifacts": workspace["training_latest"],
            "eda": workspace["eda"],
            "status": workspace["status"],
        },
    )
    return result


def queue_fuel_cell_preprocessing(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    current = get_preprocessing_status(project_id, dataset_id, session_id)
    if current.get("status") in {"queued", "running"}:
        return current
    validation = _validate_generic_contract(project_id, dataset_id, session_id)
    status = {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "package_type": "mirai_contract_package",
        "status": "queued" if validation.get("valid") else "failed_validation",
        "stage": "waiting_to_start" if validation.get("valid") else "contract_validation_failed",
        "validation": validation,
    }
    return write_status(project_id, dataset_id, session_id, "preprocessing", status)


def start_generic_preprocessing(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    status_base = {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "package_type": "mirai_contract_package",
    }
    try:
        validation = _validate_generic_contract(project_id, dataset_id, session_id)
        workspace = ensure_session_workspace(project_id, dataset_id, session_id)
        if not validation.get("valid"):
            return write_status(project_id, dataset_id, session_id, "preprocessing", {**status_base, "status": "failed_validation", "stage": "contract_validation_failed", "validation": validation})
        if validation.get("template_id") not in {"generic_tabular_doe"}:
            raise ValueError(f"Generic preprocessing does not handle template_id={validation.get('template_id')}; use the matching template adapter")
        write_status(project_id, dataset_id, session_id, "preprocessing", {**status_base, "status": "running", "stage": "building_generic_canonical_artifacts", "validation": validation})
        canonical = reset_workspace_dir(workspace["canonical"])
        training_latest = reset_workspace_dir(workspace["training_latest"])
        preprocessing_result = build_generic_preprocessing_artifacts(raw_root=workspace["raw"], canonical_dir=canonical, artifact_dir=training_latest, project_id=project_id)
        schema = _read_json(training_latest / "schema.json", default={}) or {}
        existing_metadata_status = read_status(project_id, dataset_id, session_id, "domain_metadata", default={})
        existing_domain_metadata = existing_metadata_status.get("domain_metadata") if isinstance(existing_metadata_status, dict) else None
        if (
            isinstance(existing_domain_metadata, dict)
            and existing_metadata_status.get("approval_status") == "approved"
            and not _validate_domain_metadata_for_approval(schema, existing_domain_metadata)
        ):
            domain_metadata = existing_domain_metadata
            domain_metadata_status = {
                "status": "approved",
                "approval_status": "approved",
                "approved_at": existing_metadata_status.get("approved_at"),
                "approved_by": existing_metadata_status.get("approved_by"),
            }
        else:
            domain_metadata = build_domain_metadata(schema, template_id=validation.get("template_id") or "generic_tabular_doe", approval_status="needs_admin_approval")
            domain_metadata_status = {"status": "contract_loaded_needs_admin_approval", "approval_status": "needs_admin_approval"}
        schema["domain_metadata"] = domain_metadata
        _write_json(training_latest / "schema.json", schema)
        write_status(project_id, dataset_id, session_id, "domain_metadata", {
            **domain_metadata_status,
            "template_id": domain_metadata["template_id"],
            "domain_metadata": domain_metadata,
        })
        profile = _read_json(training_latest / "dataset_profile.json", default={}) or {}
        split = _read_json(training_latest / "split_report.json", default={}) or {}
        validation_report = _read_json(training_latest / "validation_report.json", default={}) or {}
        report = {
            "project_id": project_id,
            "dataset_id": dataset_id,
            "ingestion_session_id": session_id,
            "generated_at": _now(),
            "status": "preprocessing_complete_needs_approval",
            "package_type": status_base["package_type"],
            "package_validation": validation,
            "canonical_artifacts": {
                "canonical_dir": str(canonical.relative_to(BACKEND_ROOT)),
                "training_artifact_dir": str(training_latest.relative_to(BACKEND_ROOT)),
                "files": sorted(str(path.relative_to(BACKEND_ROOT)) for path in canonical.glob("*")),
                "row_counts": {"model_table.csv": preprocessing_result.get("row_count"), "rejected_rows.csv": preprocessing_result.get("rejected_row_count")},
            },
            "preprocessing_artifacts": {key: value for key, value in preprocessing_result.items() if key.endswith("_path") or key in {"artifact_dir", "row_count"}},
            "dataset_profile": profile,
            "split_report": split,
            "validation_report": validation_report,
            "approval": {"status": "not_approved", "approver_role": "mirai_admin", "approved_at": None},
            "domain_metadata_review": {"status": "needs_admin_approval", "template_id": domain_metadata["template_id"], "plot_recipe_count": len(domain_metadata.get("ui_config", {}).get("plot_recipes", []))},
        }
        _write_json(workspace["eda"] / "preprocessing_report.json", report)
        _write_json(training_latest / "upload_preprocessing_report.json", report)
        status = write_status(project_id, dataset_id, session_id, "preprocessing", {
            **status_base,
            "status": "preprocessing_complete_needs_approval",
            "stage": "complete_needs_approval",
            "row_counts": report["canonical_artifacts"]["row_counts"],
            "report_path": str((workspace["eda"] / "preprocessing_report.json").relative_to(BACKEND_ROOT)),
            "canonical_dir": str(canonical.relative_to(BACKEND_ROOT)),
            "training_artifact_dir": str(training_latest.relative_to(BACKEND_ROOT)),
        })
        persistence = _persist_current_preprocessing_artifacts(project_id, dataset_id, session_id)
        report["object_storage"] = public_artifact_persistence_summary(persistence)
        _write_json(workspace["eda"] / "preprocessing_report.json", report)
        _write_json(training_latest / "upload_preprocessing_report.json", report)
        status = write_status(project_id, dataset_id, session_id, "preprocessing", {**status, "object_storage": public_artifact_persistence_summary(persistence)})
        persist_session_artifact_set(
            project_id=project_id,
            dataset_id=dataset_id,
            session_id=session_id,
            workspace_id=_session_workspace_id(project_id, dataset_id, session_id),
            artifact_set="eda",
            local_dir_or_files=workspace["eda"],
        )
        persist_session_artifact_set(
            project_id=project_id,
            dataset_id=dataset_id,
            session_id=session_id,
            workspace_id=_session_workspace_id(project_id, dataset_id, session_id),
            artifact_set="status",
            local_dir_or_files=workspace["status"],
        )
        clear_registry_cache()
        return status
    except Exception as exc:
        write_status(project_id, dataset_id, session_id, "preprocessing", {**status_base, "status": "failed", "stage": "error", "error": str(exc)})
        raise


def start_fuel_cell_preprocessing(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    """Deprecated compatibility name; all runtime preprocessing is generic."""
    return start_generic_preprocessing(project_id, dataset_id, session_id)


def get_preprocessing_status(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    return read_status(project_id, dataset_id, session_id, "preprocessing", default={"status": "not_started"})


def get_public_preprocessing_status(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    return _public_preprocessing_status(get_preprocessing_status(project_id, dataset_id, session_id))


def _schema_model_columns(schema: dict[str, Any], frame: pd.DataFrame) -> list[str]:
    ordered: list[str] = []
    for section in ("inputs", "outputs"):
        for item in schema.get(section, []):
            if not isinstance(item, dict):
                continue
            for candidate in (item.get("name"), item.get("variable_id")):
                if isinstance(candidate, str) and candidate in frame.columns and candidate not in ordered:
                    ordered.append(candidate)
    if ordered:
        return ordered
    return [str(column) for column in frame.select_dtypes(include="number").columns]


def ensure_ydata_html_report(project_id: str, dataset_id: str, session_id: str) -> Path:
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    model_table = workspace["canonical"] / "model_table.csv"
    if not model_table.exists():
        _hydrate_artifact_from_storage(project_id, dataset_id, session_id, "canonical", "model_table.csv", model_table)
    report_path = workspace["eda"] / "ydata_profile.html"
    if report_path.exists():
        return report_path
    if _hydrate_artifact_from_storage(project_id, dataset_id, session_id, "eda", "ydata_profile.html", report_path):
        _hydrate_artifact_from_storage(project_id, dataset_id, session_id, "eda", "ydata_profile.json", workspace["eda"] / "ydata_profile.json")
        return report_path
    if not model_table.exists():
        raise FileNotFoundError("Canonical model_table.csv is not available yet; run preprocessing first")
    try:
        from ydata_profiling import ProfileReport  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency is optional in older envs.
        raise ValueError("ydata-profiling is not installed in this backend environment") from exc
    frame = pd.read_csv(model_table, nrows=10000)
    schema = _read_json(workspace["training_latest"] / "schema.json", default={}) or {}
    preferred_columns = _schema_model_columns(schema, frame)
    profile_frame = frame[preferred_columns].copy() if preferred_columns else frame.select_dtypes(include="number").copy()
    if profile_frame.empty or not len(profile_frame.columns):
        raise ValueError("Canonical model_table.csv has no profileable input/output columns")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = workspace["eda"] / "ydata_profile.json"
    title = "Mirai Canonical Model-Table EDA"
    try:
        profile = ProfileReport(profile_frame, title=title, minimal=True)
        profile.to_file(report_path)
    except Exception:
        # ydata/wordcloud can fail on text/provenance columns in some versions.
        # Fall back to numeric-only data from the same schema-selected model columns.
        numeric_frame = profile_frame.select_dtypes(include="number")
        if numeric_frame.empty or not len(numeric_frame.columns):
            raise
        profile = ProfileReport(numeric_frame, title=title, minimal=True, explorative=False)
        profile.to_file(report_path)
    try:
        json_path.write_text(profile.to_json(), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - HTML is the primary downloadable report.
        logger.debug("Skipping y-data JSON persistence for project_id=%s session_id=%s: %s", project_id, session_id, exc)
    persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=_session_workspace_id(project_id, dataset_id, session_id),
        artifact_set="eda",
        local_dir_or_files={
            "ydata_profile.html": report_path,
            "ydata_profile.json": json_path,
        },
    )
    return report_path


def get_ydata_html_report_file_or_bytes(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    report_path = workspace["eda"] / "ydata_profile.html"
    if report_path.exists():
        return {"kind": "file", "path": report_path}
    config = _storage_config_for_session(project_id, dataset_id, session_id)
    if config is not None:
        try:
            object_key = validate_workspace_object_key(config, f"{session_artifact_prefix(config, 'eda', dataset_id, session_id)}/ydata_profile.html")
            return {"kind": "bytes", "body": read_workspace_artifact_bytes(config, object_key)}
        except Exception as exc:  # noqa: BLE001 - generate/hydrate fallback below.
            logger.debug("Y-data object-storage byte read missed for project_id=%s session_id=%s: %s", project_id, session_id, exc)
    return {"kind": "file", "path": ensure_ydata_html_report(project_id, dataset_id, session_id)}


def get_preprocessing_eda_summary(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    status = get_preprocessing_status(project_id, dataset_id, session_id)
    report = _read_json_local_or_storage(project_id, dataset_id, session_id, "eda", "preprocessing_report.json", workspace["eda"] / "preprocessing_report.json", default={}) or {}
    eda = _read_json_local_or_storage(project_id, dataset_id, session_id, "preprocessing_artifacts", "eda_report.json", workspace["training_latest"] / "eda_report.json", default={}) or {}
    split = _read_json_local_or_storage(project_id, dataset_id, session_id, "preprocessing_artifacts", "split_report.json", workspace["training_latest"] / "split_report.json", default={}) or {}
    profile = _read_json_local_or_storage(project_id, dataset_id, session_id, "canonical", "dataset_profile.json", workspace["canonical"] / "dataset_profile.json", default={}) or {}
    if not report and status.get("status") not in {"preprocessing_complete_needs_approval", "approved_for_training"}:
        raise FileNotFoundError("EDA summary is not available until preprocessing completes")
    row_counts = status.get("row_counts") or report.get("canonical_artifacts", {}).get("row_counts") or profile.get("row_counts", {})
    public_status = _public_preprocessing_status(status)
    object_storage_status = public_status.get("object_storage") or report.get("object_storage") or {}
    layouts = object_storage_status.get("layouts") if isinstance(object_storage_status, dict) else []
    uploaded_sets = {item.get("artifact_set") for item in layouts if isinstance(item, dict) and item.get("status") == "uploaded"}
    canonical_files = [Path(str(path)).name for path in report.get("canonical_artifacts", {}).get("files", [])]
    ydata_available = (workspace["eda"] / "ydata_profile.html").exists() or _artifact_exists_in_storage(project_id, dataset_id, session_id, "eda", "ydata_profile.html")
    return {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "status": public_status,
        "summary": {
            "cell_archive_count": report.get("extraction_summary", {}).get("cell_archive_count"),
            "extracted_file_count": report.get("extraction_summary", {}).get("extracted_file_count"),
            "cells_succeeded": row_counts.get("cells_succeeded"),
            "cells_failed": row_counts.get("cells_failed"),
            "model_rows": row_counts.get("model_table.csv"),
            "canonical_tables": row_counts,
            "missingness": eda.get("missingness", {}),
            "duplicate_feature_target_rows": eda.get("duplicate_feature_target_rows"),
            "duplicate_input_rows": eda.get("duplicate_input_rows"),
            "rejected_rows": eda.get("rejected_rows", {}),
            "split_counts": split.get("split_counts") or eda.get("split_counts", {}),
            "split_strategy": split.get("strategy"),
            "bo_policy": split.get("bo_holdout_policy") or split.get("bo_replay", {}).get("test_policy"),
            "input_distributions": eda.get("input_distributions", {}),
            "output_distributions": eda.get("output_distributions", {}),
            "leakage_warnings": eda.get("leakage_warnings", []),
        },
        "artifacts": {
            "canonical": {"available": bool(canonical_files), "durable": "canonical" in uploaded_sets, "files": canonical_files},
            "preprocessing": {"available": bool(eda or split), "durable": "preprocessing_artifacts" in uploaded_sets},
            "eda": {"available": bool(report), "durable": "eda" in uploaded_sets},
            "status": {"available": bool(status), "durable": "status" in uploaded_sets},
            "downloads": {
                "ydata_html": f"/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing/ydata-report.html",
                "preprocessing_report": f"/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing-report",
            },
            "ydata_html_available": ydata_available,
            "plots": report.get("plots", []),
        },
        "approval": report.get("approval", {"status": "not_approved"}),
    }


def generate_preprocessing_report(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    session = get_ingestion_session(project_id, dataset_id, session_id)
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    report_dir = workspace["eda"]
    raw_root = OBJECT_STORE_ROOT
    file_profiles: list[dict[str, Any]] = []
    primary_file: Path | None = None

    for item in session.get("files", []):
        relative_path = item.get("relative_path", "")
        path = raw_root / relative_path
        profile = _profile_frame(path, relative_path) if path.exists() else {"path": relative_path, "supported": False, "reason": "File missing"}
        file_profiles.append(profile)
        if primary_file is None and profile.get("supported"):
            primary_file = path

    ydata = _try_ydata_profile(primary_file, report_dir) if primary_file else {"enabled": False, "reason": "No supported CSV/XLSX file available"}
    report = {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "generated_at": _now(),
        "status": "eda_complete_needs_mirai_admin_review",
        "eda_engine": {
            "preferred": "ydata-profiling",
            "ydata_profile": ydata,
            "fallback": "lightweight_pandas_summary",
        },
        "file_profiles": file_profiles,
        "preprocessing_plan": {
            "imputation": "pending_mirai_admin_decision",
            "scaling_encoding": "pending_mirai_admin_decision",
            "split_strategy": "pending_mirai_admin_decision",
            "feature_exclusion": "pending_mirai_admin_decision",
        },
        "pi_assistant_recommendations": {
            "status": "placeholder_not_active",
            "message": "Future Pi assistant will recommend imputation, scaling/encoding, feature exclusion, and split strategy from EDA artifacts. No automatic preprocessing changes are applied in the MVP.",
            "imputation": [],
            "scaling_encoding": [],
            "feature_exclusion": [],
            "split_strategy": [],
            "requires_mirai_admin_approval": True,
        },
        "approval": {
            "status": "not_approved",
            "approver_role": "mirai_admin",
            "approved_at": None,
        },
        "artifacts": {
            "report_json": str((report_dir / "preprocessing_report.json").relative_to(BACKEND_ROOT)),
            "ydata_html": ydata.get("html_report"),
            "ydata_json": ydata.get("json_report"),
        },
    }
    _write_json(report_dir / "preprocessing_report.json", report)
    persistence = persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=_session_workspace_id(project_id, dataset_id, session_id),
        artifact_set="eda",
        local_dir_or_files={"preprocessing_report.json": report_dir / "preprocessing_report.json"},
    )
    report.setdefault("object_storage", {})["preprocessing_report"] = public_artifact_persistence_summary(persistence)
    _write_json(report_dir / "preprocessing_report.json", report)
    return report


def get_preprocessing_review_report(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    report = _read_json_local_or_storage(
        project_id,
        dataset_id,
        session_id,
        "eda",
        "preprocessing_report.json",
        workspace["eda"] / "preprocessing_report.json",
        default=None,
    )
    if not report:
        raise FileNotFoundError("Preprocessing report not generated yet")
    return report


def get_public_preprocessing_review_report(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    report = dict(get_preprocessing_review_report(project_id, dataset_id, session_id))
    if "object_storage" in report:
        report["object_storage"] = public_artifact_persistence_summary(report["object_storage"])
    canonical_artifacts = dict(report.get("canonical_artifacts") or {})
    if canonical_artifacts:
        canonical_artifacts.pop("canonical_dir", None)
        canonical_artifacts.pop("training_artifact_dir", None)
        canonical_artifacts["files"] = [Path(str(path)).name for path in canonical_artifacts.get("files", [])]
        report["canonical_artifacts"] = canonical_artifacts
    preprocessing_artifacts = report.get("preprocessing_artifacts")
    if isinstance(preprocessing_artifacts, dict):
        report["preprocessing_artifacts"] = {
            key: value
            for key, value in preprocessing_artifacts.items()
            if not key.endswith("_path") and key != "artifact_dir"
        }
    report["downloads"] = {
        "ydata_html": f"/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing/ydata-report.html",
        "preprocessing_report": f"/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing-report",
    }
    artifacts = report.get("artifacts")
    if isinstance(artifacts, dict):
        report["artifacts"] = {
            "downloads": report["downloads"],
            "ydata_html_available": bool(artifacts.get("ydata_html")) or _artifact_exists_in_storage(project_id, dataset_id, session_id, "eda", "ydata_profile.html"),
        }
    return report


def _schema_for_metadata(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    schema_path = workspace["training_latest"] / "schema.json"
    schema = _read_json_local_or_storage(
        project_id,
        dataset_id,
        session_id,
        "preprocessing_artifacts",
        "schema.json",
        schema_path,
        default=None,
    )
    if schema:
        return schema
    try:
        package_root, package_inventory = _prepare_package_root(workspace["raw"], workspace["inventory"])
        _write_json(workspace["inventory"] / "package_inventory.json", package_inventory)
        contract = load_and_validate_contract(package_root)
        return schema_from_contract(contract, project_id=project_id)
    except ContractValidationError:
        from .project_registry import get_project_schema  # Local import avoids service import cycle at module load.
        return get_project_schema(project_id)


def get_domain_metadata_status(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    status = read_status(project_id, dataset_id, session_id, "domain_metadata", default={})
    if isinstance(status, dict) and status.get("domain_metadata"):
        return status
    schema = _schema_for_metadata(project_id, dataset_id, session_id)
    domain_metadata = build_domain_metadata(schema, template_id=infer_template_id(schema), approval_status="needs_admin_approval")
    return write_status(project_id, dataset_id, session_id, "domain_metadata", {
        "status": "inferred_needs_admin_approval",
        "approval_status": "needs_admin_approval",
        "template_id": domain_metadata["template_id"],
        "domain_metadata": domain_metadata,
    })


def update_domain_metadata(project_id: str, dataset_id: str, session_id: str, domain_metadata: dict[str, Any], updated_by: str, notes: str | None = None) -> dict[str, Any]:
    domain_metadata = dict(domain_metadata)
    domain_metadata["approval_status"] = "draft"
    status = write_status(project_id, dataset_id, session_id, "domain_metadata", {
        "status": "draft",
        "approval_status": "draft",
        "updated_by": updated_by,
        "updated_at": _now(),
        "notes": notes or "",
        "template_id": domain_metadata.get("template_id"),
        "domain_metadata": domain_metadata,
    })
    clear_registry_cache()
    return status


def _validate_domain_metadata_for_approval(schema: dict[str, Any], domain_metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    variables = domain_metadata.get("variables") if isinstance(domain_metadata.get("variables"), list) else []
    by_name = {item.get("name"): item for item in variables if isinstance(item, dict) and item.get("name")}
    for item in schema.get("inputs", []):
        name = item.get("name")
        variable = by_name.get(name)
        if not variable:
            errors.append(f"Input {name} is missing metadata approval row")
            continue
        if variable.get("variable_id", name) != name:
            errors.append(f"Input {name} cannot change immutable variable_id")
        if item.get("source_name") and variable.get("source_name") and variable.get("source_name") != item.get("source_name"):
            errors.append(f"Input {name} cannot change source_name provenance")
        if item.get("source_table") and variable.get("source_table") and variable.get("source_table") != item.get("source_table"):
            errors.append(f"Input {name} cannot change source_table provenance")
        if variable.get("role") not in {"input", "sweep", "group"}:
            errors.append(f"Input {name} must have input-compatible role")
        if not variable.get("unit"):
            errors.append(f"Input {name} must have a unit; use 'unitless' if dimensionless")
        if variable.get("min") is None and item.get("min") is None:
            errors.append(f"Input {name} must have lower bound")
        if variable.get("max") is None and item.get("max") is None:
            errors.append(f"Input {name} must have upper bound")
    for item in schema.get("outputs", []):
        name = item.get("name")
        variable = by_name.get(name)
        if not variable:
            errors.append(f"Output {name} is missing metadata approval row")
            continue
        if variable.get("variable_id", name) != name:
            errors.append(f"Output {name} cannot change immutable variable_id")
        if item.get("source_name") and variable.get("source_name") and variable.get("source_name") != item.get("source_name"):
            errors.append(f"Output {name} cannot change source_name provenance")
        if item.get("source_table") and variable.get("source_table") and variable.get("source_table") != item.get("source_table"):
            errors.append(f"Output {name} cannot change source_table provenance")
        if variable.get("role") != "output":
            errors.append(f"Output {name} must have role=output")
        if not variable.get("unit"):
            errors.append(f"Output {name} must have a unit; use 'unitless' if dimensionless")
        if variable.get("direction") not in {"maximize", "minimize", "target"} and item.get("direction") not in {"maximize", "minimize", "target"}:
            errors.append(f"Output {name} must have direction maximize|minimize|target")
    ui_config = domain_metadata.get("ui_config") if isinstance(domain_metadata.get("ui_config"), dict) else {}
    recipes = ui_config.get("plot_recipes") if isinstance(ui_config.get("plot_recipes"), list) else []
    if not recipes:
        errors.append("At least one approved/safe plot recipe is required")
    return errors


def approve_domain_metadata(project_id: str, dataset_id: str, session_id: str, approver: str, notes: str | None = None) -> dict[str, Any]:
    status = get_domain_metadata_status(project_id, dataset_id, session_id)
    domain_metadata = dict(status.get("domain_metadata") or {})
    if not domain_metadata:
        raise ValueError("No inferred domain metadata is available to approve")
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    schema = _read_json(workspace["training_latest"] / "schema.json", default={}) or _schema_for_metadata(project_id, dataset_id, session_id)
    approval_errors = _validate_domain_metadata_for_approval(schema, domain_metadata)
    if approval_errors:
        raise ValueError("Metadata cannot be approved until required Mirai schema fields are complete: " + "; ".join(approval_errors))
    domain_metadata["approval_status"] = "approved"
    domain_metadata["approved_by"] = approver
    approved_at = _now()
    schema_path = workspace["training_latest"] / "schema.json"
    if schema_path.exists():
        schema = _read_json(schema_path, default={}) or {}
        schema["domain_metadata"] = domain_metadata
        _write_json(schema_path, schema)
    approved = write_status(project_id, dataset_id, session_id, "domain_metadata", {
        "status": "approved",
        "approval_status": "approved",
        "approved_at": approved_at,
        "approved_by": approver,
        "notes": notes or "",
        "template_id": domain_metadata.get("template_id"),
        "domain_metadata": domain_metadata,
    })
    clear_registry_cache()
    return approved


def _persist_preprocessing_outputs(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    try:
        return _persist_current_preprocessing_artifacts(project_id, dataset_id, session_id)
    except Exception as exc:  # noqa: BLE001 - local/dev can approve without configured S3.
        workspace_id = _session_workspace_id(project_id, dataset_id, session_id) or ""
        logger.warning("Preprocessing artifact upload skipped/failed for workspace_id=%s project_id=%s: %s", workspace_id, project_id, exc)
        if postgres_control_plane_required():
            raise
        return {"status": "skipped", "workspace_id": workspace_id, "project_id": project_id, "detail": str(exc)}


def approve_preprocessing(project_id: str, dataset_id: str, session_id: str, approver: str, notes: str | None = None) -> dict[str, Any]:
    report = get_preprocessing_review_report(project_id, dataset_id, session_id)
    if report.get("status") not in {"preprocessing_complete_needs_approval", "eda_complete_needs_mirai_admin_review", "approved_for_training"}:
        raise ValueError("Preprocessing is not complete and cannot be approved yet")
    report["approval"] = {
        "status": "approved_for_training",
        "approver_role": "mirai_admin",
        "approver": approver,
        "approved_at": _now(),
        "notes": notes or "",
    }
    report["status"] = "approved_for_training"
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    metadata_status = read_status(project_id, dataset_id, session_id, "domain_metadata", default={})
    domain_metadata = metadata_status.get("domain_metadata") if isinstance(metadata_status, dict) else None
    if not isinstance(domain_metadata, dict) or metadata_status.get("approval_status") != "approved":
        raise ValueError("Metadata & Plot Setup must be approved by a Mirai admin before preprocessing approval")
    schema_path = workspace["training_latest"] / "schema.json"
    schema = _read_json(schema_path, default={}) or {}
    if schema:
        schema["domain_metadata"] = domain_metadata
        _write_json(schema_path, schema)
    _write_json(workspace["eda"] / "preprocessing_report.json", report)
    persistence = _persist_preprocessing_outputs(project_id, dataset_id, session_id)
    report["object_storage"] = public_artifact_persistence_summary(persistence)
    _write_json(workspace["eda"] / "preprocessing_report.json", report)
    persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=_session_workspace_id(project_id, dataset_id, session_id),
        artifact_set="eda",
        local_dir_or_files={"preprocessing_report.json": workspace["eda"] / "preprocessing_report.json"},
    )
    write_status(project_id, dataset_id, session_id, "preprocessing", {**get_preprocessing_status(project_id, dataset_id, session_id), "status": "approved_for_training", "approved_at": report["approval"]["approved_at"], "object_storage": public_artifact_persistence_summary(persistence)})
    persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=_session_workspace_id(project_id, dataset_id, session_id),
        artifact_set="status",
        local_dir_or_files=workspace["status"],
    )
    return report
