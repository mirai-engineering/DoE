from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from uuid import uuid4
import zipfile

from fastapi import UploadFile

from .cathode_contract_harness import build_cathode_demo_mirai_contract
from .control_plane import get_project_storage_config
from .db import execute, jsonb, postgres_control_plane_enabled
from .workspace_storage import WorkspaceStorageConfig, get_workspace_object, put_workspace_object

BACKEND_ROOT = Path(__file__).resolve().parents[2]
TARGET_CONTRACT_DIR = BACKEND_ROOT / "docs" / "examples" / "fuel-cell" / "fraunhofer2miraicontract-full"
LOCAL_BUCKET = "mirai-document-intake"

ALLOWED_SUFFIXES = {".pdf", ".docx", ".xlsx", ".csv", ".zip"}
PACKAGE_FILES = ["mirai_manifest.json", "data_dictionary.csv", "experiments.csv", "conditions.csv", "results.csv"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _local_config(workspace_id: str, project_id: str) -> WorkspaceStorageConfig:
    return WorkspaceStorageConfig(workspace_id=workspace_id, mode="local", bucket=LOCAL_BUCKET, prefix=f"workspaces/{workspace_id}/projects/{project_id}")


def _storage_config(workspace_id: str, project_id: str) -> WorkspaceStorageConfig:
    return get_project_storage_config(workspace_id, project_id) or _local_config(workspace_id, project_id)


def _session_prefix(config: WorkspaceStorageConfig, session_id: str) -> str:
    return f"{config.normalized_prefix}/document_intake/sessions/{session_id}"


def _json_key(config: WorkspaceStorageConfig, session_id: str, name: str) -> str:
    return f"{_session_prefix(config, session_id)}/state/{name}.json"


def _read_json(config: WorkspaceStorageConfig, key: str, default: Any) -> Any:
    try:
        return json.loads(get_workspace_object(config, key).decode("utf-8"))
    except Exception:  # noqa: BLE001 - absent local object, absent db project storage, or first-use state.
        return default


def _write_json(config: WorkspaceStorageConfig, key: str, payload: Any) -> None:
    put_workspace_object(config, key, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"), content_type="application/json")


def _session_index_key(config: WorkspaceStorageConfig, project_id: str) -> str:
    return f"{config.normalized_prefix}/document_intake/projects/{project_id}/sessions.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in session.items() if k not in {"workspace_id"}}


def list_document_intake_sessions(workspace_id: str, project_id: str) -> list[dict[str, Any]]:
    config = _storage_config(workspace_id, project_id)
    index = _read_json(config, _session_index_key(config, project_id), default=[])
    sessions = index if isinstance(index, list) else []
    return [_public_session(session) for session in sorted(sessions, key=lambda item: str(item.get("updated_at") or ""), reverse=True)]


def create_document_intake_session(workspace_id: str, project_id: str, *, title: str | None = None, target_contract_id: str | None = None, created_by: str | None = None) -> dict[str, Any]:
    config = _storage_config(workspace_id, project_id)
    session_id = f"dki_{uuid4().hex[:12]}"
    session = {
        "id": session_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "title": title or "Knowledge intake session",
        "target_contract_id": target_contract_id or "generic_tabular_doe",
        "loop_iterations": [],
        "status": "draft",
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
        "file_count": 0,
        "latest_draft_id": None,
        "latest_export_key": None,
    }
    _write_json(config, _json_key(config, session_id, "session"), session)
    index = _read_json(config, _session_index_key(config, project_id), default=[])
    index = [item for item in (index if isinstance(index, list) else []) if item.get("id") != session_id]
    index.append(session)
    _write_json(config, _session_index_key(config, project_id), index)
    _record_session_sql(session)
    return _public_session(session)


def _update_session(config: WorkspaceStorageConfig, project_id: str, session: dict[str, Any]) -> None:
    session["updated_at"] = _now()
    _write_json(config, _json_key(config, str(session["id"]), "session"), session)
    index = _read_json(config, _session_index_key(config, project_id), default=[])
    index = [item for item in (index if isinstance(index, list) else []) if item.get("id") != session.get("id")]
    index.append(session)
    _write_json(config, _session_index_key(config, project_id), index)
    _record_session_sql(session)


def get_document_intake_session(workspace_id: str, project_id: str, session_id: str) -> dict[str, Any]:
    config = _storage_config(workspace_id, project_id)
    session = _read_json(config, _json_key(config, session_id, "session"), default=None)
    if not isinstance(session, dict) or session.get("project_id") != project_id:
        raise FileNotFoundError("Document intake session not found")
    files = _read_json(config, _json_key(config, session_id, "files"), default=[])
    draft = _read_json(config, _json_key(config, session_id, "draft"), default=None)
    export = _read_json(config, _json_key(config, session_id, "export"), default=None)
    public = _public_session(session)
    public["files"] = files if isinstance(files, list) else []
    public["draft"] = draft if isinstance(draft, dict) else None
    public["export"] = export if isinstance(export, dict) else None
    return public


async def upload_document_intake_files(workspace_id: str, project_id: str, session_id: str, uploads: list[UploadFile]) -> dict[str, Any]:
    config = _storage_config(workspace_id, project_id)
    session = _read_json(config, _json_key(config, session_id, "session"), default=None)
    if not isinstance(session, dict):
        raise FileNotFoundError("Document intake session not found")
    files = _read_json(config, _json_key(config, session_id, "files"), default=[])
    files = files if isinstance(files, list) else []
    for upload in uploads:
        filename = Path(upload.filename or "upload.bin").name
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError(f"Unsupported document type: {suffix or filename}")
        data = await upload.read()
        file_id = f"file_{uuid4().hex[:12]}"
        object_key = f"{_session_prefix(config, session_id)}/raw/{file_id}_{filename}"
        put_workspace_object(config, object_key, data, content_type=upload.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream")
        parse_summary = _summarize_file(filename, suffix, data)
        file_record = {
            "id": file_id,
            "filename": filename,
            "content_type": upload.content_type,
            "file_type": suffix.removeprefix("."),
            "object_key": object_key,
            "sha256": _sha256(data),
            "size_bytes": len(data),
            "parse_status": parse_summary.get("status", "uploaded"),
            "parse_summary": parse_summary,
            "created_at": _now(),
        }
        files.append(file_record)
        _record_file_sql(workspace_id, project_id, session_id, file_record)
    session["status"] = "files_uploaded"
    session["file_count"] = len(files)
    _write_json(config, _json_key(config, session_id, "files"), files)
    _update_session(config, project_id, session)
    return {"status": session["status"], "files": files}


def _summarize_file(filename: str, suffix: str, data: bytes) -> dict[str, Any]:
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = [name for name in archive.namelist() if not name.endswith("/")]
                allowed_inner = [name for name in names if Path(name).suffix.lower() in {".csv", ".xlsx"}]
                return {"status": "container_indexed", "inner_file_count": len(names), "allowed_inner_file_count": len(allowed_inner), "sample_inner_files": allowed_inner[:20]}
        except zipfile.BadZipFile:
            return {"status": "parse_warning", "warning": "Invalid ZIP container"}
    if suffix == ".csv":
        text = data[:8192].decode("utf-8", errors="replace")
        return {"status": "parsed_preview", "line_count_sample": len(text.splitlines()), "preview": text.splitlines()[:5]}
    if suffix == ".xlsx":
        return {"status": "uploaded", "note": "XLSX parsing is planned behind the document parser boundary."}
    return {"status": "uploaded", "note": "Text/document parsing is planned behind the document parser boundary."}


def save_document_instruction(workspace_id: str, project_id: str, session_id: str, message: str, expected_columns: list[str] | None = None, expected_row_count: int | None = None) -> dict[str, Any]:
    config = _storage_config(workspace_id, project_id)
    session = _read_json(config, _json_key(config, session_id, "session"), default=None)
    if not isinstance(session, dict):
        raise FileNotFoundError("Document intake session not found")
    session["user_instruction"] = message
    session["expected_columns"] = expected_columns or []
    session["expected_row_count"] = expected_row_count
    session["status"] = "instruction_ready"
    _update_session(config, project_id, session)
    messages = _read_json(config, _json_key(config, session_id, "messages"), default=[])
    messages = messages if isinstance(messages, list) else []
    messages.append({"role": "user", "content": message, "created_at": _now()})
    _write_json(config, _json_key(config, session_id, "messages"), messages)
    return {"status": session["status"], "session": _public_session(session)}


def match_mirai_contract(workspace_id: str, project_id: str, session_id: str) -> dict[str, Any]:
    config = _storage_config(workspace_id, project_id)
    session = _read_json(config, _json_key(config, session_id, "session"), default=None)
    if not isinstance(session, dict):
        raise FileNotFoundError("Document intake session not found")
    files = _read_json(config, _json_key(config, session_id, "files"), default=[])
    if not files:
        raise ValueError("Upload source documents before matching the Mirai contract")
    draft_id = f"draft_{uuid4().hex[:12]}"
    run_id = f"run_{uuid4().hex[:12]}"
    target_contract_id = str(session.get("target_contract_id") or "generic_tabular_doe")
    iteration_number = len(session.get("loop_iterations") or []) + 1
    source_inventory = _source_inventory(files)
    if target_contract_id == "fraunhofer2miraicontract-full":
        draft, run, issue_lines, iteration = _run_fraunhofer_demo_adapter(config, session_id, draft_id, run_id, files, source_inventory, iteration_number)
    else:
        draft, run, issue_lines, iteration = _run_generic_contract_loop_stub(session, draft_id, run_id, files, source_inventory, iteration_number)
    issues_key = f"{_session_prefix(config, session_id)}/drafts/{draft_id}/issues.txt"
    put_workspace_object(config, issues_key, "\n".join(issue_lines).encode("utf-8"), content_type="text/plain")
    draft["issues_key"] = issues_key
    session.setdefault("loop_iterations", []).append(iteration)
    session["status"] = "draft_ready_for_review" if draft.get("validation_passed") else "needs_user_input"
    session["latest_draft_id"] = draft_id
    _write_json(config, _json_key(config, session_id, "draft"), draft)
    _record_draft_sql(workspace_id, project_id, session_id, draft)
    _write_json(config, _json_key(config, session_id, "latest_run"), run)
    _update_session(config, project_id, session)
    return {"status": session["status"], "draft": draft, "run": run, "iteration": iteration}


def _source_inventory(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.get("id"),
            "filename": item.get("filename"),
            "file_type": item.get("file_type"),
            "size_bytes": item.get("size_bytes"),
            "parse_status": item.get("parse_status"),
            "parse_summary": item.get("parse_summary"),
        }
        for item in files
    ]


def _run_fraunhofer_demo_adapter(config: WorkspaceStorageConfig, session_id: str, draft_id: str, run_id: str, files: list[dict[str, Any]], source_inventory: list[dict[str, Any]], iteration_number: int) -> tuple[dict[str, Any], dict[str, Any], list[str], dict[str, Any]]:
    harness = build_cathode_demo_mirai_contract(config, files)
    tables = {name: _csv_preview_text(text) for name, text in harness.files.items() if name.endswith(".csv")}
    manifest = json.loads(harness.files["mirai_manifest.json"])
    validation_passed = bool(harness.validation.get("passed"))
    mapping = {
        "adapter": "fraunhofer_cathode_catalyst_demo",
        "description": "Deterministic proof adapter for the Cathode Catalyst Degradation fixture only; not the generic intake harness.",
        "target_contract_id": "fraunhofer2miraicontract-full",
    }
    transform_plan = {
        "execution_mode": "approved_deterministic_adapter",
        "adapter": "fraunhofer_cathode_catalyst_demo",
        "steps": [
            "Parse data_overview.xlsx for experiment metadata.",
            "Parse Cell_XX.zip IV/ECSA CSVs.",
            "Align voltage grid to selected demo contract.",
            "Materialize Mirai fixed-source tables and model_table.csv.",
            "Validate row counts and required package files before approval/export.",
        ],
    }
    issue_lines = [
        "Knowledge Intake loop notes",
        "",
        "Target contract: fraunhofer2miraicontract-full (selected demo contract)",
        "Adapter: fraunhofer_cathode_catalyst_demo deterministic proof adapter",
        "Important: this adapter is not the generic arbitrary-data pathway.",
        "The generic pathway records a mapping/transform plan and requires approved deterministic tools before export.",
        "It does not call existing Data Intake, preprocessing, ML preprocessing, or training routes.",
        "",
        f"Loop iteration: {iteration_number}",
        f"Uploaded files: {len(files)}",
        f"Parsed overview rows: {harness.source_summary.get('overview_rows')}",
        f"Parsed cell archives: {harness.source_summary.get('cell_archives')}",
        f"Validation passed: {validation_passed}",
        "",
        "Issues / validation loop:",
        *[f"- {issue}" for issue in harness.issues],
    ]
    iteration = {
        "iteration_number": iteration_number,
        "created_at": _now(),
        "goal": {"target_contract_id": "fraunhofer2miraicontract-full", "export_requires_validation": True},
        "source_inventory": source_inventory,
        "proposed_mapping": mapping,
        "transform_plan": transform_plan,
        "transform_attempt": {"status": "completed", "executor": "backend_deterministic_adapter", "adapter": "fraunhofer_cathode_catalyst_demo"},
        "validation_result": harness.validation,
        "missing_fields": harness.validation.get("missing_fields", []),
        "questions": [] if validation_passed else ["Upload the missing overview workbook and all Cell_XX.zip archives, then run the loop again."],
        "user_answers": [],
    }
    draft = {
        "id": draft_id,
        "run_id": run_id,
        "status": "ready_for_review" if validation_passed else "needs_user_input",
        "table_kind": "mirai_fixed_source_tables",
        "adapter_id": "fraunhofer_cathode_catalyst_demo",
        "created_at": _now(),
        "schema": _contract_schema(manifest),
        "tables": tables,
        "contract_files": harness.files if validation_passed else None,
        "row_counts": harness.row_counts,
        "source_reference_mode": "filename+sheet/csv-row",
        "validation_passed": validation_passed,
        "validation_result": harness.validation,
        "loop_iteration": iteration,
        "approved_at": None,
    }
    run = {"id": run_id, "status": "completed" if validation_passed else "needs_user_input", "provider": "deterministic_demo_adapter", "model": None, "started_at": _now(), "finished_at": _now(), "draft_id": draft_id}
    return draft, run, issue_lines, iteration


def _run_generic_contract_loop_stub(session: dict[str, Any], draft_id: str, run_id: str, files: list[dict[str, Any]], source_inventory: list[dict[str, Any]], iteration_number: int) -> tuple[dict[str, Any], dict[str, Any], list[str], dict[str, Any]]:
    target_contract_id = str(session.get("target_contract_id") or "generic_tabular_doe")
    user_instruction = str(session.get("user_instruction") or "")
    agent_plan = _infer_mapping_plan_with_anthropic(target_contract_id, user_instruction, source_inventory)
    questions = agent_plan.get("questions") if isinstance(agent_plan.get("questions"), list) else []
    if not questions:
        questions = [
            "Confirm the exact target contract/table shape and required input/output columns.",
            "Identify which uploaded files contain experiment metadata, conditions/inputs, and measured results/outputs.",
            "Provide or approve an approved deterministic transform tool for this data shape before export.",
        ]
    mapping = {
        "status": "candidate_only",
        "target_contract_id": target_contract_id,
        "user_instruction": user_instruction,
        "agent_provider": agent_plan.get("provider"),
        "agent_model": agent_plan.get("model"),
        "agent_mapping": agent_plan.get("mapping"),
        "agent_confidence": agent_plan.get("confidence"),
        "note": "Generic arbitrary-data support is intentionally plan-first. The agent may propose a structured mapping, but backend export requires an approved deterministic transform executor.",
    }
    transform_plan = {
        "execution_mode": "not_executed",
        "requires_approved_tool": True,
        "agent_plan": agent_plan.get("transform_plan"),
        "steps": [
            "Inspect uploaded source inventory.",
            "Infer candidate source-to-contract mapping with an agent provider when configured.",
            "Ask user to resolve missing fields/ambiguous joins.",
            "Execute only approved deterministic backend transforms.",
            "Validate generated package against the selected contract before approval/export.",
        ],
    }
    validation = {"passed": False, "status": "blocked_no_approved_transform", "target_contract_id": target_contract_id, "missing_fields": questions}
    issue_lines = [
        "Knowledge Intake loop notes",
        "",
        f"Target contract: {target_contract_id}",
        f"Agent planner: {agent_plan.get('provider')} ({agent_plan.get('model')})",
        "Status: generic contract-driven loop planned only; no arbitrary transform was executed.",
        "The agent must not freely generate and execute transformation code. Export is blocked until an approved deterministic transform produces a valid contract package.",
        "",
        f"Loop iteration: {iteration_number}",
        f"Uploaded files: {len(files)}",
        "",
        "Questions / missing information:",
        *[f"- {question}" for question in questions],
    ]
    iteration = {
        "iteration_number": iteration_number,
        "created_at": _now(),
        "goal": {"target_contract_id": target_contract_id, "export_requires_validation": True},
        "source_inventory": source_inventory,
        "proposed_mapping": mapping,
        "transform_plan": transform_plan,
        "transform_attempt": {"status": "not_executed", "reason": "no_approved_deterministic_transform_for_target"},
        "validation_result": validation,
        "missing_fields": questions,
        "questions": questions,
        "user_answers": [user_instruction] if user_instruction else [],
    }
    draft = {
        "id": draft_id,
        "run_id": run_id,
        "status": "needs_user_input",
        "table_kind": "contract_mapping_plan",
        "adapter_id": None,
        "created_at": _now(),
        "schema": {"template_id": target_contract_id, "tables": [], "inputs": [], "outputs": []},
        "tables": {},
        "contract_files": None,
        "row_counts": {},
        "source_reference_mode": "filename+sheet/csv-row when available",
        "validation_passed": False,
        "validation_result": validation,
        "loop_iteration": iteration,
        "approved_at": None,
    }
    run = {"id": run_id, "status": "needs_user_input", "provider": agent_plan.get("provider") or "generic_loop_controller", "model": agent_plan.get("model"), "started_at": _now(), "finished_at": _now(), "draft_id": draft_id, "usage": agent_plan.get("usage")}
    return draft, run, issue_lines, iteration


def _infer_mapping_plan_with_anthropic(target_contract_id: str, user_instruction: str, source_inventory: list[dict[str, Any]]) -> dict[str, Any]:
    model = os.getenv("MIRAI_KNOWLEDGE_INTAKE_MODEL") or os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-5"
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"provider": "not_configured", "model": model, "questions": [], "mapping": None, "confidence": "none"}
    try:
        from anthropic import Anthropic

        client = Anthropic(timeout=float(os.getenv("MIRAI_KNOWLEDGE_INTAKE_TIMEOUT_SECONDS", "45")))
        prompt = {
            "target_contract_id": target_contract_id,
            "user_instruction": user_instruction,
            "source_inventory": source_inventory,
            "constraints": [
                "Do not generate executable code.",
                "Return only a structured JSON planning object.",
                "Backend may execute only approved deterministic transform tools.",
                "List missing fields/questions required before validation/export.",
            ],
        }
        response = client.messages.create(
            model=model,
            max_tokens=1800,
            system=(
                "You are Mirai's Knowledge Intake planner. Infer a source-to-contract mapping plan from uploaded source inventory. "
                "You never write executable code. You produce JSON only with keys: mapping, transform_plan, questions, confidence."
            ),
            messages=[{"role": "user", "content": json.dumps(prompt, indent=2)}],
        )
        text = "\n".join(getattr(block, "text", "") for block in getattr(response, "content", []) if getattr(block, "type", None) == "text").strip()
        parsed = _parse_json_object(text)
        usage = getattr(response, "usage", None)
        parsed.update({
            "provider": "anthropic",
            "model": model,
            "usage": {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            } if usage else None,
        })
        return parsed
    except Exception as exc:  # noqa: BLE001 - planning should degrade to explicit questions, not break intake.
        return {"provider": "anthropic_error", "model": model, "error": type(exc).__name__, "questions": [], "mapping": None, "confidence": "none"}


def _parse_json_object(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def _csv_preview(path: Path, *, limit: int = 25) -> dict[str, Any]:
    return _csv_preview_text(path.read_text(), limit=limit)


def _csv_preview_text(text: str, *, limit: int = 25) -> dict[str, Any]:
    lines = text.splitlines()
    header = lines[0].split(",") if lines else []
    return {"columns": header, "preview_rows": lines[1 : limit + 1], "total_rows": max(len(lines) - 1, 0)}


def _contract_schema(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_id": manifest.get("project", {}).get("template_id") or "generic_tabular_doe",
        "tables": manifest.get("tables", []),
        "inputs": [c for c in manifest.get("columns", []) if c.get("role") == "input"],
        "outputs": [c for c in manifest.get("columns", []) if c.get("role") == "output"],
    }


def get_draft_table(workspace_id: str, project_id: str, session_id: str) -> dict[str, Any]:
    config = _storage_config(workspace_id, project_id)
    draft = _read_json(config, _json_key(config, session_id, "draft"), default=None)
    if not isinstance(draft, dict):
        raise FileNotFoundError("Draft table not found")
    return draft


def get_issues_text(workspace_id: str, project_id: str, session_id: str) -> str:
    config = _storage_config(workspace_id, project_id)
    draft = get_draft_table(workspace_id, project_id, session_id)
    return get_workspace_object(config, draft["issues_key"]).decode("utf-8")


def approve_draft_table(workspace_id: str, project_id: str, session_id: str, approved_by: str | None = None) -> dict[str, Any]:
    config = _storage_config(workspace_id, project_id)
    session = _read_json(config, _json_key(config, session_id, "session"), default=None)
    draft = _read_json(config, _json_key(config, session_id, "draft"), default=None)
    if not isinstance(session, dict) or not isinstance(draft, dict):
        raise FileNotFoundError("Draft table not found")
    if not draft.get("validation_passed"):
        raise ValueError("Cannot approve/export until the selected contract validation passes")
    draft["status"] = "approved_persistent"
    draft["approved_at"] = _now()
    draft["approved_by"] = approved_by
    session["status"] = "approved"
    _write_json(config, _json_key(config, session_id, "draft"), draft)
    _record_draft_sql(workspace_id, project_id, session_id, draft)
    _update_session(config, project_id, session)
    return {"status": session["status"], "draft": draft}


def reject_draft_table(workspace_id: str, project_id: str, session_id: str) -> dict[str, Any]:
    config = _storage_config(workspace_id, project_id)
    session = _read_json(config, _json_key(config, session_id, "session"), default=None)
    if not isinstance(session, dict):
        raise FileNotFoundError("Document intake session not found")
    _write_json(config, _json_key(config, session_id, "draft"), {"status": "deleted", "deleted_at": _now()})
    session["status"] = "rejected_deleted"
    session["latest_draft_id"] = None
    _update_session(config, project_id, session)
    return {"status": session["status"]}


def export_mirai_package(workspace_id: str, project_id: str, session_id: str) -> dict[str, Any]:
    config = _storage_config(workspace_id, project_id)
    session = _read_json(config, _json_key(config, session_id, "session"), default=None)
    draft = _read_json(config, _json_key(config, session_id, "draft"), default=None)
    if not isinstance(session, dict) or not isinstance(draft, dict):
        raise FileNotFoundError("Approved draft not found")
    if draft.get("status") != "approved_persistent":
        raise ValueError("Approve the validated draft before exporting a Mirai package")
    if not draft.get("validation_passed"):
        raise ValueError("Export is blocked until the selected contract validation passes")
    contract_files = draft.get("contract_files") if isinstance(draft.get("contract_files"), dict) else None
    if not contract_files:
        raise ValueError("Export is blocked because no validated contract package files are available")
    zip_bytes = _build_package_zip(contract_files)
    export_key = f"{_session_prefix(config, session_id)}/exports/mirai_package.zip"
    put_workspace_object(config, export_key, zip_bytes, content_type="application/zip")
    export = {"status": "exported", "package_key": export_key, "size_bytes": len(zip_bytes), "created_at": _now()}
    session["status"] = "exported"
    session["latest_export_key"] = export_key
    _write_json(config, _json_key(config, session_id, "export"), export)
    _record_export_sql(workspace_id, project_id, session_id, draft.get("id"), export)
    _update_session(config, project_id, session)
    return export


def _build_package_zip(contract_files: dict[str, str] | None = None) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if contract_files:
            for name, text in contract_files.items():
                archive.writestr(name, text)
        else:
            raise ValueError("Cannot build a package ZIP without validated contract files")
    return buffer.getvalue()


def _materialize_model_table() -> str:
    # Prefer an existing materializer if the example package later gains model_table.csv.
    candidate = TARGET_CONTRACT_DIR / "model_table.csv"
    if candidate.exists():
        return candidate.read_text()
    import csv
    from io import StringIO

    experiments = {row["experiment_id"]: row for row in csv.DictReader((TARGET_CONTRACT_DIR / "experiments.csv").open())}
    conditions = {row["condition_id"]: row for row in csv.DictReader((TARGET_CONTRACT_DIR / "conditions.csv").open())}
    results = list(csv.DictReader((TARGET_CONTRACT_DIR / "results.csv").open()))
    columns = ["experiment_id", "condition_id", "result_id", "split", "x1", "x2", "x3", "x4", "x5", "x6", "x7", "y1", "y2", "y3", "y4"]
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    for result in results:
        condition = conditions[result["condition_id"]]
        experiment = experiments[condition["experiment_id"]]
        writer.writerow({
            "experiment_id": experiment["experiment_id"],
            "condition_id": condition["condition_id"],
            "result_id": result["result_id"],
            "split": condition.get("split", ""),
            "x1": experiment["pt_c_ratio"],
            "x2": experiment["i_c_ratio"],
            "x3": experiment["ionomer_ew"],
            "x4": condition["operating_rh"],
            "x5": condition["operating_voltage"],
            "x6": experiment["ast_rh"],
            "x7": experiment["ast_upl"],
            "y1": result["bol_current_density"],
            "y2": result["eol_current_density"],
            "y3": result["bol_ecsa"],
            "y4": result["ecsa_loss"],
        })
    return out.getvalue()


def get_export_zip(workspace_id: str, project_id: str, session_id: str) -> bytes:
    config = _storage_config(workspace_id, project_id)
    export = _read_json(config, _json_key(config, session_id, "export"), default=None)
    if not isinstance(export, dict) or not export.get("package_key"):
        raise FileNotFoundError("Export package not found")
    return get_workspace_object(config, export["package_key"])


def _record_session_sql(session: dict[str, Any]) -> None:
    if not postgres_control_plane_enabled():
        return
    try:
        execute(
            str(session["workspace_id"]),
            """
            INSERT INTO document_intake_sessions (id, workspace_id, project_id, status, title, user_instruction, target_contract_id, created_by, updated_by, metadata, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                title = EXCLUDED.title,
                user_instruction = EXCLUDED.user_instruction,
                target_contract_id = EXCLUDED.target_contract_id,
                updated_by = EXCLUDED.updated_by,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            """,
            (
                session["id"],
                session["workspace_id"],
                session["project_id"],
                session.get("status"),
                session.get("title"),
                session.get("user_instruction"),
                session.get("target_contract_id"),
                session.get("created_by"),
                session.get("updated_by") or session.get("created_by"),
                jsonb({k: v for k, v in session.items() if k not in {"id", "workspace_id", "project_id", "status", "title", "user_instruction", "target_contract_id", "created_by", "updated_by"}}),
            ),
        )
    except Exception:
        # Postgres migration may not be applied in local/dev. Object storage remains the fallback state store.
        return


def _record_file_sql(workspace_id: str, project_id: str, session_id: str, file_record: dict[str, Any]) -> None:
    if not postgres_control_plane_enabled():
        return
    try:
        execute(
            workspace_id,
            """
            INSERT INTO document_intake_files (id, workspace_id, project_id, session_id, filename, content_type, file_type, object_uri, sha256, size_bytes, parse_status, parse_summary, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET
                parse_status = EXCLUDED.parse_status,
                parse_summary = EXCLUDED.parse_summary
            """,
            (file_record["id"], workspace_id, project_id, session_id, file_record.get("filename"), file_record.get("content_type"), file_record.get("file_type"), file_record.get("object_key"), file_record.get("sha256"), file_record.get("size_bytes"), file_record.get("parse_status"), jsonb(file_record.get("parse_summary") or {})),
        )
    except Exception:
        return


def _record_draft_sql(workspace_id: str, project_id: str, session_id: str, draft: dict[str, Any]) -> None:
    if not postgres_control_plane_enabled():
        return
    try:
        execute(
            workspace_id,
            """
            INSERT INTO document_table_drafts (id, workspace_id, project_id, session_id, extraction_run_id, status, table_kind, schema_json, payload_json, issues_text_object_uri, source_refs_json, created_at, approved_at, approved_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), CASE WHEN %s IS NULL THEN NULL ELSE now() END, %s)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                schema_json = EXCLUDED.schema_json,
                payload_json = EXCLUDED.payload_json,
                issues_text_object_uri = EXCLUDED.issues_text_object_uri,
                source_refs_json = EXCLUDED.source_refs_json,
                approved_at = COALESCE(document_table_drafts.approved_at, EXCLUDED.approved_at),
                approved_by = COALESCE(EXCLUDED.approved_by, document_table_drafts.approved_by)
            """,
            (draft["id"], workspace_id, project_id, session_id, draft.get("run_id"), draft.get("status"), draft.get("table_kind") or "mirai_fixed_source_tables", jsonb(draft.get("schema") or {}), jsonb({"tables": draft.get("tables"), "row_counts": draft.get("row_counts"), "contract_files": draft.get("contract_files")}), draft.get("issues_key"), jsonb({"source_reference_mode": draft.get("source_reference_mode")}), draft.get("approved_at"), draft.get("approved_by")),
        )
    except Exception:
        return


def _record_export_sql(workspace_id: str, project_id: str, session_id: str, draft_id: str | None, export: dict[str, Any]) -> None:
    if not postgres_control_plane_enabled():
        return
    try:
        execute(
            workspace_id,
            """
            INSERT INTO document_intake_exports (id, workspace_id, project_id, session_id, draft_id, status, package_object_uri, fixed_source_tables_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, package_object_uri = EXCLUDED.package_object_uri
            """,
            (f"export_{session_id}", workspace_id, project_id, session_id, draft_id, export.get("status"), export.get("package_key"), jsonb(export)),
        )
    except Exception:
        return
