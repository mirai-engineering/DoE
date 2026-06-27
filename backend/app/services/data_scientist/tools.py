from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.services.data_intake import get_file_inventory, get_ingestion_session, list_ingestion_sessions
from app.services.model_quality import get_active_model_metadata, get_artifact_summary, get_metrics
from app.services.ml_preprocessing import get_ml_preprocessed_table_path, get_ml_preprocessing_report, get_ml_preprocessing_status, load_ml_preprocessing_plan
from app.services.preprocessing_review import get_preprocessing_eda_summary, get_preprocessing_status
from app.services.project_registry import get_project_schema, list_projects

from .sanitization import sanitize_agent_payload
from .schemas import InventoryArgs, LatestSessionArgs, NoArgs, TableProfileArgs
from .scope import AgentScope


class AgentToolError(ValueError):
    pass


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[AgentScope, BaseModel], dict[str, Any]]

    def run(self, scope: AgentScope, raw_args: dict[str, Any] | None = None) -> dict[str, Any]:
        raw_args = raw_args or {}
        _reject_scope_or_storage_args(raw_args)
        try:
            args = self.args_model.model_validate(raw_args)
        except ValidationError as exc:
            raise AgentToolError(f"Invalid arguments for {self.name}: {exc.errors()[0].get('msg', 'validation failed')}") from exc
        _ensure_project_scope(scope)
        result = self.handler(scope, args)
        return sanitize_agent_payload(result, scope)


def _reject_scope_or_storage_args(value: Any) -> None:
    forbidden_keys = {"workspace_id", "workspace", "clerk_user_id", "user_id", "path", "root", "bucket", "prefix", "object_key", "object_uri", "sql", "query"}
    if isinstance(value, dict):
        for key, item in value.items():
            lower = str(key).lower()
            if lower in forbidden_keys or lower.endswith("_path") or lower.endswith("_key"):
                raise AgentToolError("Tool arguments cannot include scope, path, object-key, or SQL fields")
            _reject_scope_or_storage_args(item)
    elif isinstance(value, list):
        for item in value:
            _reject_scope_or_storage_args(item)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(token in lowered for token in ("s3://", "file://", "../", "/etc/", "/tmp/", "select ", " from ", "workspaces/")):
            raise AgentToolError("Tool arguments cannot include paths, object keys, or SQL")


def _ensure_project_scope(scope: AgentScope) -> None:
    if scope.workspace_id:
        if not any(project.get("id") == scope.project_id for project in list_projects(scope.workspace_id)):
            raise AgentToolError("Project is not available in the authenticated workspace")


def _accessible_sessions(scope: AgentScope) -> list[dict[str, Any]]:
    sessions = [session for session in list_ingestion_sessions() if session.get("project_id") == scope.project_id]
    if scope.workspace_id:
        sessions = [session for session in sessions if session.get("workspace_id") == scope.workspace_id]
    return sessions


def _select_session(scope: AgentScope, args: LatestSessionArgs) -> dict[str, Any] | None:
    sessions = _accessible_sessions(scope)
    if args.dataset_id:
        sessions = [session for session in sessions if session.get("dataset_id") == args.dataset_id]
    if args.session_id:
        sessions = [session for session in sessions if session.get("ingestion_session_id") == args.session_id]
    if not sessions:
        return None
    return sorted(sessions, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)[0]


def dataset_contract(scope: AgentScope, args: NoArgs) -> dict[str, Any]:
    schema = get_project_schema(scope.project_id, workspace_id=scope.workspace_id)
    return {
        "project": schema.get("display_name") or scope.project_id,
        "inputs": schema.get("inputs", []),
        "outputs": schema.get("outputs", []),
        "constraints": schema.get("constraints", []),
    }


def artifact_inventory(scope: AgentScope, args: InventoryArgs) -> dict[str, Any]:
    session = _select_session(scope, args)
    if not session:
        return {"status": "not_found", "files": []}
    inventory = get_file_inventory(str(session["project_id"]), str(session["dataset_id"]), str(session["ingestion_session_id"]))
    files = inventory.get("files", [])[: args.limit]
    return {
        "status": session.get("status"),
        "approval_status": session.get("approval_status"),
        "dataset_id": session.get("dataset_id"),
        "session_id": session.get("ingestion_session_id"),
        "file_count": len(inventory.get("files", [])),
        "files": [
            {
                "filename": file.get("original_filename") or file.get("filename"),
                "content_type": file.get("content_type"),
                "size_bytes": file.get("size_bytes"),
                "suffix": file.get("suffix"),
            }
            for file in files
        ],
    }


def table_profile(scope: AgentScope, args: TableProfileArgs) -> dict[str, Any]:
    session = _select_session(scope, args)
    if not session:
        return {"status": "not_found"}
    try:
        eda = get_preprocessing_eda_summary(str(session["project_id"]), str(session["dataset_id"]), str(session["ingestion_session_id"]))
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "detail": str(exc)}
    columns = eda.get("columns") or eda.get("variables") or []
    if isinstance(columns, dict):
        columns = [{"name": key, **(value if isinstance(value, dict) else {"summary": value})} for key, value in columns.items()]
    return {"status": eda.get("status", "available"), "summary": eda.get("summary") or eda.get("table"), "columns": columns[: args.max_columns] if isinstance(columns, list) else []}


def preprocessing_status(scope: AgentScope, args: LatestSessionArgs) -> dict[str, Any]:
    session = _select_session(scope, args)
    if not session:
        return {"status": "not_found"}
    try:
        status = get_preprocessing_status(str(session["project_id"]), str(session["dataset_id"]), str(session["ingestion_session_id"]))
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "detail": str(exc)}
    return status


def ml_preprocessing_summary(scope: AgentScope, args: LatestSessionArgs) -> dict[str, Any]:
    session = _select_session(scope, args)
    if not session:
        return {"status": "not_found"}
    project_id = str(session["project_id"])
    dataset_id = str(session["dataset_id"])
    session_id = str(session["ingestion_session_id"])
    status = get_ml_preprocessing_status(project_id, dataset_id, session_id)
    report = get_ml_preprocessing_report(project_id, dataset_id, session_id)
    plan_summary: dict[str, Any] = {"available": False, "actions": []}
    try:
        plan = load_ml_preprocessing_plan(project_id, dataset_id, session_id)
        plan_summary = {
            "available": True,
            "plan_id": plan.plan_id,
            "status": plan.status,
            "fit_scope": plan.fit_scope,
            "actions": [
                {
                    "variable_id": action.variable_id,
                    "role": action.role,
                    "tool": action.tool.value,
                    "method": action.method,
                    "reason": action.reason,
                    "risk_level": action.risk_level.value,
                }
                for action in plan.actions[:80]
            ],
            "action_count": len(plan.actions),
        }
    except Exception:  # noqa: BLE001 - plan may not exist yet.
        pass
    table_summary: dict[str, Any] = {"available": False}
    try:
        import pandas as pd  # type: ignore[import-not-found]

        table_path = get_ml_preprocessed_table_path(project_id, dataset_id, session_id)
        frame = pd.read_csv(table_path)
        columns = list(frame.columns)
        binary_columns = [column for column in columns if column not in {"split", "cell_id"} and set(frame[column].dropna().unique().tolist()).issubset({0, 1, 0.0, 1.0})]
        table_summary = {
            "available": True,
            "row_count": int(len(frame)),
            "column_count": int(len(columns)),
            "columns": columns[:80],
            "binary_columns": binary_columns[:40],
            "note": "Binary numeric indicators are normally kept as a single 0/1 feature; one-hot with both categories would add a redundant collinear column unless a user explicitly requests a different policy.",
        }
    except Exception:  # noqa: BLE001 - table may not exist yet.
        pass
    return {
        "status": status.get("status", "unknown"),
        "summary": status.get("summary") or report.get("summary"),
        "plan": plan_summary,
        "report": {
            "status": report.get("status"),
            "summary": report.get("summary"),
            "warnings": report.get("warnings", []),
            "risks": report.get("risks", []),
            "export_files": report.get("export_files", []),
        },
        "table": table_summary,
        "training_ready": status.get("status") == "ml_preprocessing_ready_for_training",
    }


def training_summary(scope: AgentScope, args: NoArgs) -> dict[str, Any]:
    # Deliberately avoid unscoped MLflow experiment scans here. Active-model metadata
    # is resolved through workspace-aware project artifacts/control-plane pointers.
    return {
        "active_model": get_active_model_metadata(scope.project_id, workspace_id=scope.workspace_id),
    }


def model_quality(scope: AgentScope, args: NoArgs) -> dict[str, Any]:
    # Compose only workspace-aware readers. Avoid get_model_quality_summary because it
    # currently includes unscoped MLflow latest_runs/scientist_review fields.
    return {
        "metrics": get_metrics(scope.project_id, workspace_id=scope.workspace_id),
        "artifacts": get_artifact_summary(scope.project_id, workspace_id=scope.workspace_id),
        "active_model": get_active_model_metadata(scope.project_id, workspace_id=scope.workspace_id),
    }


TOOLS: dict[str, AgentTool] = {
    "dataset_contract": AgentTool("dataset_contract", "Summarize active project inputs, outputs, and constraints.", NoArgs, dataset_contract),
    "artifact_inventory": AgentTool("artifact_inventory", "List safe uploaded file inventory metadata for the latest or selected session.", InventoryArgs, artifact_inventory),
    "table_profile": AgentTool("table_profile", "Summarize safe table/column profile metadata from preprocessing artifacts.", TableProfileArgs, table_profile),
    "preprocessing_status": AgentTool("preprocessing_status", "Report preprocessing status for latest or selected session.", LatestSessionArgs, preprocessing_status),
    "ml_preprocessing_summary": AgentTool("ml_preprocessing_summary", "Summarize deterministic ML preprocessing plan, fitted artifacts, ready report, and safe preprocessed table metadata for the latest or selected session.", LatestSessionArgs, ml_preprocessing_summary),
    "training_summary": AgentTool("training_summary", "Summarize latest training runs and active model metadata.", NoArgs, training_summary),
    "model_quality": AgentTool("model_quality", "Summarize model quality metrics and artifact status.", NoArgs, model_quality),
}
