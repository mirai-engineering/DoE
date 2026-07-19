from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import csv
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from uuid import uuid4
import zipfile

from fastapi import UploadFile

from .demo_adapters import build_cathode_demo_mirai_contract
from ..platform.control_plane import get_project_storage_config
from ..platform.db import execute, jsonb, postgres_control_plane_enabled
from ..platform.workspace_storage import WorkspaceStorageConfig, get_workspace_object, put_workspace_object
from ml_lifecycle.ingesting.generic_tabular_doe.contract import ContractValidationError, load_and_validate_contract, schema_from_contract
from ml_lifecycle.ingesting.generic_tabular_doe.preprocessing import build_generic_preprocessing_artifacts

BACKEND_ROOT = Path(__file__).resolve().parents[3]
TARGET_CONTRACT_DIR = BACKEND_ROOT / "docs" / "examples" / "fuel-cell" / "fraunhofer2miraicontract-full"
LOCAL_BUCKET = "mirai-document-intake"

ALLOWED_SUFFIXES = {".pdf", ".docx", ".xlsx", ".csv", ".zip"}
TARGET_CONTRACT_SUFFIXES = {".csv", ".json", ".zip"}
PACKAGE_FILES = ["mirai_manifest.json", "data_dictionary.csv", "model_table.csv", "experiments.csv", "conditions.csv", "results.csv"]


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
    messages = _read_json(config, _json_key(config, session_id, "messages"), default=[])
    public = _public_session(session)
    public["files"] = files if isinstance(files, list) else []
    public["messages"] = messages if isinstance(messages, list) else []
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


async def upload_document_intake_target_contract(workspace_id: str, project_id: str, session_id: str, uploads: list[UploadFile]) -> dict[str, Any]:
    """Upload and validate the Mirai package shape Knowledge Intake must populate.

    This is intentionally scoped to Knowledge Intake. It reads the same generic contract
    rules downstream Data Intake uses, but does not create ingestion sessions or modify
    Data Intake/preprocessing state.
    """
    config = _storage_config(workspace_id, project_id)
    session = _read_json(config, _json_key(config, session_id, "session"), default=None)
    if not isinstance(session, dict):
        raise FileNotFoundError("Document intake session not found")
    target_files: dict[str, str] = {}
    stored_files: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mirai_target_contract_") as tmp:
        root = Path(tmp) / "package"
        root.mkdir(parents=True, exist_ok=True)
        for upload in uploads:
            filename = Path(upload.filename or "target.bin").name
            suffix = Path(filename).suffix.lower()
            if suffix not in TARGET_CONTRACT_SUFFIXES:
                raise ValueError(f"Unsupported target contract file type: {suffix or filename}")
            data = await upload.read()
            object_key = f"{_session_prefix(config, session_id)}/target_contract/{uuid4().hex[:8]}_{filename}"
            put_workspace_object(config, object_key, data, content_type=upload.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream")
            stored_files.append({"filename": filename, "object_key": object_key, "sha256": _sha256(data), "size_bytes": len(data), "created_at": _now()})
            if suffix == ".zip":
                with zipfile.ZipFile(BytesIO(data)) as archive:
                    for member in archive.namelist():
                        if member.endswith("/"):
                            continue
                        safe_name = _safe_package_member_name(member)
                        if safe_name and Path(safe_name).name in PACKAGE_FILES:
                            payload = archive.read(member)
                            (root / Path(safe_name).name).write_bytes(payload)
                            target_files[Path(safe_name).name] = payload.decode("utf-8-sig", errors="replace")
            else:
                if filename not in PACKAGE_FILES:
                    raise ValueError(f"Target contract file {filename!r} is not a supported Mirai package file")
                (root / filename).write_bytes(data)
                target_files[filename] = data.decode("utf-8-sig", errors="replace")
        contract = load_and_validate_contract(root)
        schema = schema_from_contract(contract, project_id=project_id)
    target_snapshot = _target_snapshot_from_contract(contract, schema, target_files, stored_files)
    session["target_contract_id"] = target_snapshot["contract_id"]
    session["target_contract"] = target_snapshot
    session["status"] = "target_contract_uploaded"
    _write_json(config, _json_key(config, session_id, "target_contract"), target_snapshot)
    _update_session(config, project_id, session)
    return {"status": session["status"], "target_contract": target_snapshot, "session": _public_session(session)}


def _safe_package_member_name(member: str) -> str | None:
    path = Path(member)
    if path.is_absolute() or ".." in path.parts:
        return None
    return path.name


def _target_snapshot_from_contract(contract: dict[str, Any], schema: dict[str, Any], target_files: dict[str, str], stored_files: list[dict[str, Any]]) -> dict[str, Any]:
    table_paths = [str(table.get("path")) for table in contract.get("tables", []) if isinstance(table, dict) and table.get("path")]
    package_style = "model_table" if "model_table.csv" in table_paths else "fixed_source_tables" if {"experiments.csv", "conditions.csv", "results.csv"}.issubset(set(table_paths)) else "unknown"
    fields = _fields_from_contract(contract)
    return {
        "id": f"target_{uuid4().hex[:12]}",
        "contract_id": contract.get("project", {}).get("template_id") or "generic_tabular_doe",
        "uploaded_at": _now(),
        "package_style": package_style,
        "required_files": ["mirai_manifest.json", "data_dictionary.csv", *[path for path in table_paths if path in PACKAGE_FILES and path not in {"mirai_manifest.json", "data_dictionary.csv"}]],
        "tables": contract.get("tables", []),
        "joins": contract.get("joins", []),
        "split_hints": contract.get("split_hints", {}),
        "columns": contract.get("columns", []),
        "fields": fields,
        "schema": schema,
        "files": {name: text for name, text in target_files.items() if name in {"mirai_manifest.json", "data_dictionary.csv"}},
        "file_names": sorted(target_files),
        "stored_files": stored_files,
    }


def _summarize_file(filename: str, suffix: str, data: bytes) -> dict[str, Any]:
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = [name for name in archive.namelist() if not name.endswith("/")]
                indexed_tables: list[dict[str, Any]] = []
                for name in names[:120]:
                    inner_suffix = Path(name).suffix.lower()
                    if inner_suffix == ".csv":
                        try:
                            indexed_tables.append(_summarize_csv_bytes(archive.read(name), table_name=name, max_bytes=120_000))
                        except Exception as exc:  # noqa: BLE001
                            indexed_tables.append({"table_name": name, "type": "csv", "status": "parse_warning", "warning": type(exc).__name__})
                    elif inner_suffix == ".xlsx":
                        try:
                            indexed_tables.extend(_summarize_xlsx_bytes(archive.read(name), workbook_name=name))
                        except Exception as exc:  # noqa: BLE001
                            indexed_tables.append({"table_name": name, "type": "xlsx", "status": "parse_warning", "warning": type(exc).__name__})
                allowed_inner = [name for name in names if Path(name).suffix.lower() in {".csv", ".xlsx"}]
                return {"status": "container_indexed", "inner_file_count": len(names), "allowed_inner_file_count": len(allowed_inner), "sample_inner_files": allowed_inner[:20], "tables": indexed_tables[:60]}
        except zipfile.BadZipFile:
            return {"status": "parse_warning", "warning": "Invalid ZIP container"}
    if suffix == ".csv":
        return {"status": "parsed_preview", "tables": [_summarize_csv_bytes(data, table_name=filename)]}
    if suffix == ".xlsx":
        tables = _summarize_xlsx_bytes(data, workbook_name=filename)
        return {"status": "parsed_preview" if tables else "uploaded", "tables": tables, "note": None if tables else "XLSX parser could not extract a tabular preview."}
    return {"status": "uploaded", "note": "Text/document parsing is planned behind the document parser boundary."}


def _summarize_csv_bytes(data: bytes, *, table_name: str, max_bytes: int = 250_000) -> dict[str, Any]:
    text = data[:max_bytes].decode("utf-8-sig", errors="replace")
    sample = text.splitlines()[:100]
    if not sample:
        return {"table_name": table_name, "type": "csv", "status": "empty", "columns": [], "row_count_sample": 0, "sample_rows": []}
    try:
        dialect = csv.Sniffer().sniff("\n".join(sample[:10])) if len(sample) > 1 else csv.excel
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(sample, dialect))
    columns = [str(value).strip() for value in (rows[0] if rows else [])]
    data_rows = rows[1:6]
    return {
        "table_name": table_name,
        "type": "csv",
        "status": "parsed_preview",
        "columns": columns,
        "row_count_sample": max(len(rows) - 1, 0),
        "sample_rows": [_row_dict(columns, row) for row in data_rows],
        "column_profiles": [_column_profile(column, [row[idx] if idx < len(row) else "" for row in rows[1:20]]) for idx, column in enumerate(columns)],
    }


def _summarize_xlsx_bytes(data: bytes, *, workbook_name: str) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except Exception:  # noqa: BLE001
        return []
    try:
        workbook = pd.ExcelFile(BytesIO(data))
    except Exception:  # noqa: BLE001
        return []
    tables: list[dict[str, Any]] = []
    for sheet_name in workbook.sheet_names[:20]:
        try:
            frame = workbook.parse(sheet_name=sheet_name, nrows=25)
            columns = [str(column).strip() for column in frame.columns.tolist()]
            sample_rows = frame.head(5).where(frame.notna(), None).to_dict(orient="records")
            tables.append({
                "table_name": f"{workbook_name}::{sheet_name}",
                "workbook": workbook_name,
                "sheet_name": sheet_name,
                "type": "xlsx_sheet",
                "status": "parsed_preview",
                "columns": columns,
                "row_count_sample": int(len(frame.index)),
                "sample_rows": sample_rows,
                "column_profiles": [_column_profile(column, [row.get(column) for row in sample_rows]) for column in columns],
            })
        except Exception as exc:  # noqa: BLE001
            tables.append({"table_name": f"{workbook_name}::{sheet_name}", "type": "xlsx_sheet", "status": "parse_warning", "warning": type(exc).__name__})
    return tables


def _row_dict(columns: list[str], row: list[str]) -> dict[str, Any]:
    return {column or f"column_{idx + 1}": row[idx] if idx < len(row) else None for idx, column in enumerate(columns[:40])}


def _column_profile(column: str, values: list[Any]) -> dict[str, Any]:
    non_empty = [value for value in values if value not in {None, ""}]
    numeric = 0
    for value in non_empty:
        try:
            float(str(value).replace(",", ""))
            numeric += 1
        except ValueError:
            pass
    return {
        "name": column,
        "sample_values": [str(value) for value in non_empty[:5]],
        "inferred_type": "numeric" if non_empty and numeric / len(non_empty) >= 0.8 else "text",
        "semantic_hints": _semantic_hints(column),
    }


def _semantic_hints(column: str) -> list[str]:
    text = column.lower().replace("_", " ").replace("-", " ")
    hints = []
    patterns = {
        "voltage": r"\b(voltage|volt|potential|ewe|u\b)",
        "current_density": r"current|j\b|ma\s*cm|a\s*cm",
        "relative_humidity": r"\brh\b|humidity",
        "ecsa": r"ecsa|surface area",
        "bol": r"\bbol\b|beginning",
        "eol": r"\beol\b|end of life",
        "upl": r"upl|upper potential",
        "catalyst_ratio": r"pt.?c|platinum|catalyst",
        "ionomer": r"ionomer|nafion|ew\b",
    }
    for hint, pattern in patterns.items():
        if re.search(pattern, text):
            hints.append(hint)
    return hints


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
    if not isinstance(session.get("target_contract"), dict):
        raise ValueError("Upload a target Mirai contract package before running the Knowledge Intake loop")
    iteration_number = len(session.get("loop_iterations") or []) + 1
    source_inventory = _source_inventory(files)
    if _fraunhofer_tool_requested(session, source_inventory):
        draft, run, issue_lines, iteration = _run_fraunhofer_demo_adapter(config, session_id, draft_id, run_id, files, source_inventory, iteration_number)
    else:
        draft, run, issue_lines, iteration = _run_generic_contract_loop_stub(config, session, draft_id, run_id, files, source_inventory, iteration_number)
    issues_key = f"{_session_prefix(config, session_id)}/drafts/{draft_id}/issues.txt"
    put_workspace_object(config, issues_key, "\n".join(issue_lines).encode("utf-8"), content_type="text/plain")
    draft["issues_key"] = issues_key
    session.setdefault("loop_iterations", []).append(iteration)
    session["status"] = "draft_ready_for_review" if draft.get("validation_passed") else "needs_user_input"
    session["latest_draft_id"] = draft_id
    _write_json(config, _json_key(config, session_id, "draft"), draft)
    _record_draft_sql(workspace_id, project_id, session_id, draft)
    _write_json(config, _json_key(config, session_id, "latest_run"), run)
    if isinstance(draft.get("agent_response"), str):
        messages = _read_json(config, _json_key(config, session_id, "messages"), default=[])
        messages = messages if isinstance(messages, list) else []
        messages.append({"role": "assistant", "content": draft["agent_response"], "created_at": _now(), "draft_id": draft_id})
        _write_json(config, _json_key(config, session_id, "messages"), messages[-50:])
    _update_session(config, project_id, session)
    return {"status": session["status"], "draft": draft, "run": run, "iteration": iteration}


def _source_inventory(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for item in files:
        parse_summary = item.get("parse_summary") if isinstance(item.get("parse_summary"), dict) else {}
        tables = parse_summary.get("tables") if isinstance(parse_summary.get("tables"), list) else []
        available_columns = []
        for table in tables:
            if not isinstance(table, dict):
                continue
            for column in table.get("columns") or []:
                available_columns.append({
                    "file_id": item.get("id"),
                    "filename": item.get("filename"),
                    "table_name": table.get("table_name"),
                    "column": column,
                    "semantic_hints": _semantic_hints(str(column)),
                })
        inventory.append({
            "id": item.get("id"),
            "filename": item.get("filename"),
            "file_type": item.get("file_type"),
            "size_bytes": item.get("size_bytes"),
            "parse_status": item.get("parse_status"),
            "tables": tables,
            "available_columns": available_columns,
            "parse_summary": {k: v for k, v in parse_summary.items() if k != "tables"},
        })
    return inventory


def _fields_from_contract(contract: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for column in contract.get("columns", []):
        if not isinstance(column, dict) or column.get("role") == "ignore":
            continue
        variable_id = str(column.get("variable_id") or column.get("name") or column.get("source_name") or "")
        fields.append({
            "field": variable_id,
            "variable_id": variable_id,
            "source_name": column.get("source_name") or column.get("name") or variable_id,
            "source_table": column.get("source_table") or column.get("table"),
            "role": column.get("role"),
            "dtype": column.get("dtype"),
            "unit": column.get("unit"),
            "required": bool(column.get("required")),
            "direction": column.get("direction"),
            "allowed_min": column.get("allowed_min"),
            "allowed_max": column.get("allowed_max"),
            "ui_label": column.get("ui_label") or column.get("source_name") or variable_id,
            "description": column.get("description") or "",
            "join_key": column.get("join_key"),
            "split_hint": column.get("split_hint"),
        })
    return fields


def _contract_fields(session: dict[str, Any]) -> list[dict[str, Any]]:
    target = session.get("target_contract") if isinstance(session.get("target_contract"), dict) else {}
    fields = target.get("fields") if isinstance(target.get("fields"), list) else []
    return [field for field in fields if isinstance(field, dict)]


def _fraunhofer_tool_requested(session: dict[str, Any], source_inventory: list[dict[str, Any]]) -> bool:
    instruction = str(session.get("user_instruction") or "").lower()
    if "fraunhofer" not in instruction and "cathode" not in instruction:
        return False
    filenames = " ".join(str(item.get("filename") or "") for item in source_inventory).lower()
    return "data_overview" in filenames or "cell_" in filenames


def _run_fraunhofer_demo_adapter(config: WorkspaceStorageConfig, session_id: str, draft_id: str, run_id: str, files: list[dict[str, Any]], source_inventory: list[dict[str, Any]], iteration_number: int) -> tuple[dict[str, Any], dict[str, Any], list[str], dict[str, Any]]:
    harness = build_cathode_demo_mirai_contract(config, files)
    tables = {name: _csv_preview_text(text) for name, text in harness.files.items() if name.endswith(".csv")}
    manifest = json.loads(harness.files["mirai_manifest.json"])
    validation_passed = bool(harness.validation.get("passed"))
    demo_fields = _fields_from_contract({"columns": manifest.get("columns", [])})
    mapping_board = [
        {"field": field["field"], "role": field.get("role"), "required": field.get("required", True), "description": field.get("description"), "source_name": field.get("source_name"), "variable_id": field.get("variable_id"), "source_column": "deterministic demo adapter", "source_table": "data_overview.xlsx + Cell_XX.zip IV/ECSA CSVs", "source_file": "uploaded Fraunhofer fixture", "confidence": "high", "status": "mapped", "rationale": "Mapped by approved Fraunhofer cathode catalyst deterministic adapter."}
        for field in demo_fields
    ]
    mapping = {
        "adapter": "fraunhofer_cathode_catalyst_demo",
        "description": "Deterministic proof adapter for the Cathode Catalyst Degradation fixture only; not the generic intake harness.",
        "target_contract_id": "fraunhofer2miraicontract-full",
        "mapping_board": mapping_board,
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
        "mapping_board": mapping_board,
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
        "available_columns": _flatten_available_columns(source_inventory),
        "mapping_board": mapping_board,
        "agent_response": "The Fraunhofer demo adapter mapped and validated the selected contract with a deterministic backend transform." if validation_passed else "The Fraunhofer demo adapter needs the missing fixture files listed in the issues panel.",
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


def _run_generic_contract_loop_stub(config: WorkspaceStorageConfig, session: dict[str, Any], draft_id: str, run_id: str, files: list[dict[str, Any]], source_inventory: list[dict[str, Any]], iteration_number: int) -> tuple[dict[str, Any], dict[str, Any], list[str], dict[str, Any]]:
    target_contract_id = str(session.get("target_contract_id") or "generic_tabular_doe")
    user_instruction = str(session.get("user_instruction") or "")
    contract_fields = _contract_fields(session)
    available_columns = _flatten_available_columns(source_inventory)
    user_intent = _classify_user_intent(user_instruction)
    agent_plan = _infer_mapping_plan_with_anthropic(target_contract_id, user_instruction, source_inventory, contract_fields)
    mapping_board = _build_mapping_board(contract_fields, available_columns, agent_plan, user_instruction)
    missing_fields = [row["field"] for row in mapping_board if row.get("required") and row.get("status") == "missing"]
    user_selected = _extract_user_selected_columns(user_instruction, available_columns)
    approved_mapping = user_intent == "approve_all" and not missing_fields
    blockers = []
    if missing_fields:
        blockers.extend([f"Map or mark constant/unknown: {field}" for field in missing_fields])
    blockers.append("No approved deterministic transform executor exists yet for this generic source shape; export remains blocked until one validates package files.")
    questions = _specific_questions(mapping_board, missing_fields, user_selected)
    if not questions:
        questions = agent_plan.get("questions") if isinstance(agent_plan.get("questions"), list) else []
    if not questions:
        questions = ["Confirm the proposed mapping, or say which available columns should be inputs and outputs."]
    agent_response = _agent_response_text(user_intent, approved_mapping, missing_fields, user_selected, mapping_board, available_columns)
    mapping = {
        "status": "user_approved_mapping" if approved_mapping else "candidate_only",
        "target_contract_id": target_contract_id,
        "user_instruction": user_instruction,
        "agent_provider": agent_plan.get("provider"),
        "agent_model": agent_plan.get("model"),
        "agent_mapping": agent_plan.get("mapping"),
        "agent_confidence": agent_plan.get("confidence"),
        "mapping_board": mapping_board,
        "available_columns": available_columns,
        "user_selected_columns": user_selected,
        "agent_response": agent_response,
        "note": "Generic arbitrary-data support is plan-first. The agent proposes a structured mapping, but backend export requires an approved deterministic transform executor and selected-contract validation.",
    }
    transform_plan = {
        "execution_mode": "not_executed",
        "requires_approved_tool": True,
        "agent_plan": agent_plan.get("transform_plan"),
        "steps": [
            "Inspect uploaded source inventory and list available columns.",
            "Infer candidate source-to-contract mapping with an agent provider when configured.",
            "Let the user approve/correct input and output assignments conversationally.",
            "Execute only approved deterministic backend transforms.",
            "Validate generated package against the selected contract before approval/export.",
        ],
    }
    materialized = _try_materialize_uploaded_package_tables(config, str(session["id"]), str(session.get("project_id") or "uploaded_project"), session.get("target_contract") if isinstance(session.get("target_contract"), dict) else {}, files)
    if materialized.get("validation", {}).get("passed"):
        validation = materialized["validation"]
        blockers = []
        transform_plan["execution_mode"] = "approved_ephemeral_table_copy"
        transform_plan["requires_approved_tool"] = False
        transform_plan["execution_summary"] = materialized.get("execution_summary")
    else:
        validation = {"passed": False, "status": "blocked_no_validated_transform", "target_contract_id": target_contract_id, "missing_fields": missing_fields, "blockers": blockers, "transform_attempt": materialized.get("validation")}
    issue_lines = [
        "Knowledge Intake loop notes",
        "",
        f"Target contract: {target_contract_id}",
        f"Agent planner: {agent_plan.get('provider')} ({agent_plan.get('model')})",
        "Status: generic contract-driven mapping conversation; no arbitrary transform was executed.",
        "The agent proposes columns and roles. Export is blocked until an approved Knowledge Intake transform produces a valid contract package.",
        "",
        f"Loop iteration: {iteration_number}",
        f"Uploaded files: {len(files)}",
        f"Available columns discovered: {len(available_columns)}",
        "",
        "Agent response:",
        agent_response,
        "",
        "Mapping blockers:",
        *[f"- {blocker}" for blocker in blockers],
        "",
        "Questions / next actions:",
        *[f"- {question}" for question in questions],
    ]
    iteration = {
        "iteration_number": iteration_number,
        "created_at": _now(),
        "goal": {"target_contract_id": target_contract_id, "export_requires_validation": True},
        "source_inventory": source_inventory,
        "contract_fields": contract_fields,
        "available_columns": available_columns,
        "proposed_mapping": mapping,
        "mapping_board": mapping_board,
        "transform_plan": transform_plan,
        "transform_attempt": materialized.get("execution_summary") or {"status": "not_executed", "reason": "no_validated_ephemeral_transform_for_target"},
        "validation_result": validation,
        "missing_fields": missing_fields,
        "blockers": blockers,
        "questions": questions,
        "user_answers": [user_instruction] if user_instruction else [],
        "conversation": _conversation_with_agent(session, agent_response),
    }
    draft = {
        "id": draft_id,
        "run_id": run_id,
        "status": "ready_for_review" if validation.get("passed") else "mapping_approved_blocked_executor" if approved_mapping else "needs_user_input",
        "table_kind": "contract_mapping_plan",
        "adapter_id": None,
        "created_at": _now(),
        "schema": (session.get("target_contract") or {}).get("schema") or {"template_id": target_contract_id, "fields": contract_fields, "inputs": [f for f in contract_fields if f.get("role") == "input"], "outputs": [f for f in contract_fields if f.get("role") == "output"]},
        "source_inventory": source_inventory,
        "available_columns": available_columns,
        "mapping_board": mapping_board,
        "agent_response": agent_response,
        "conversation": iteration["conversation"],
        "tables": materialized.get("tables") or {},
        "contract_files": materialized.get("contract_files") if validation.get("passed") else None,
        "row_counts": materialized.get("row_counts") or {},
        "source_reference_mode": "filename+sheet/csv-row when available",
        "validation_passed": bool(validation.get("passed")),
        "validation_result": validation,
        "loop_iteration": iteration,
        "approved_at": None,
    }
    session["mapping_state"] = mapping
    run = {"id": run_id, "status": "needs_user_input", "provider": agent_plan.get("provider") or "generic_loop_controller", "model": agent_plan.get("model"), "started_at": _now(), "finished_at": _now(), "draft_id": draft_id, "usage": agent_plan.get("usage")}
    return draft, run, issue_lines, iteration


def _try_materialize_uploaded_package_tables(config: WorkspaceStorageConfig, session_id: str, project_id: str, target_contract: dict[str, Any], files: list[dict[str, Any]]) -> dict[str, Any]:
    """Ephemeral MVP executor: assemble package files from uploaded source files only.

    This deliberately avoids persistent generated code. It supports the safest first case:
    source uploads already contain tables whose basenames match the target package style
    (`model_table.csv` or `experiments.csv`/`conditions.csv`/`results.csv`). The output is
    then validated through the unchanged generic contract/preprocessing pipeline in a temp dir.
    """
    target_static = target_contract.get("files") if isinstance(target_contract.get("files"), dict) else {}
    if not {"mirai_manifest.json", "data_dictionary.csv"}.issubset(set(target_static)):
        return {"validation": {"passed": False, "status": "missing_target_contract_files"}}
    required_files = [name for name in target_contract.get("required_files") or [] if name in PACKAGE_FILES]
    data_files = [name for name in required_files if name not in {"mirai_manifest.json", "data_dictionary.csv"}]
    if not data_files:
        return {"validation": {"passed": False, "status": "target_has_no_output_tables"}}
    source_texts = _source_package_texts(config, files, data_files)
    missing = [name for name in data_files if name not in source_texts]
    if missing:
        return {"validation": {"passed": False, "status": "source_package_tables_missing", "missing_files": missing}}
    contract_files = {"mirai_manifest.json": str(target_static["mirai_manifest.json"]), "data_dictionary.csv": str(target_static["data_dictionary.csv"]), **source_texts}
    validation = _validate_candidate_contract_files(contract_files, project_id)
    tables = {name: _csv_preview_text(text) for name, text in contract_files.items() if name.endswith(".csv")}
    row_counts = {name: table.get("total_rows", 0) for name, table in tables.items()}
    return {
        "contract_files": contract_files if validation.get("passed") else None,
        "tables": tables,
        "row_counts": row_counts,
        "validation": validation,
        "execution_summary": {
            "status": "completed" if validation.get("passed") else "failed_validation",
            "executor": "knowledge_intake_ephemeral_table_copy",
            "sandbox": "temporary_directory_no_persistent_code",
            "source_files": sorted(source_texts),
            "notes": "Copied package-shaped CSV tables from source uploads and validated with generic_tabular_doe preprocessing in a temp workspace.",
        },
    }


def _source_package_texts(config: WorkspaceStorageConfig, files: list[dict[str, Any]], wanted: list[str]) -> dict[str, str]:
    wanted_set = set(wanted)
    found: dict[str, str] = {}
    for item in files:
        filename = str(item.get("filename") or "")
        object_key = item.get("object_key")
        if not object_key:
            continue
        data = get_workspace_object(config, str(object_key))
        if Path(filename).name in wanted_set:
            found[Path(filename).name] = data.decode("utf-8-sig", errors="replace")
        elif Path(filename).suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(BytesIO(data)) as archive:
                    for member in archive.namelist():
                        base = Path(member).name
                        if base in wanted_set and base not in found:
                            found[base] = archive.read(member).decode("utf-8-sig", errors="replace")
            except zipfile.BadZipFile:
                continue
    return found


def _validate_candidate_contract_files(contract_files: dict[str, str], project_id: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="mirai_knowledge_validate_") as tmp:
        root = Path(tmp) / "package"
        canonical = Path(tmp) / "canonical"
        artifacts = Path(tmp) / "artifacts"
        root.mkdir(parents=True, exist_ok=True)
        for name, text in contract_files.items():
            (root / name).write_text(str(text), encoding="utf-8")
        try:
            contract = load_and_validate_contract(root)
            preprocessing = build_generic_preprocessing_artifacts(raw_root=root, canonical_dir=canonical, artifact_dir=artifacts, project_id=project_id)
            return {
                "passed": True,
                "status": "validated_with_generic_tabular_doe",
                "package_style": "model_table" if "model_table.csv" in contract_files else "fixed_source_tables",
                "row_count": preprocessing.get("row_count") or preprocessing.get("accepted_rows"),
                "inputs": [column.get("variable_id") for column in contract.get("columns", []) if column.get("role") == "input"],
                "outputs": [column.get("variable_id") for column in contract.get("columns", []) if column.get("role") == "output"],
            }
        except ContractValidationError as exc:
            return {"passed": False, "status": "contract_validation_failed", "errors": exc.errors}
        except Exception as exc:  # noqa: BLE001 - validation failures should be visible blockers.
            return {"passed": False, "status": "preprocessing_validation_failed", "error": type(exc).__name__, "detail": str(exc)}


def _flatten_available_columns(source_inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    for item in source_inventory:
        for column in item.get("available_columns") or []:
            if isinstance(column, dict):
                columns.append(column)
    return columns[:300]


def _classify_user_intent(message: str) -> str:
    text = message.strip().lower()
    if re.search(r"\b(approve|accept|ok|yes|confirm)\b.*\b(all|everything|suggested|mapping|proposal)\b", text) or text in {"approved", "approve", "yes", "ok"}:
        return "approve_all"
    if "input" in text or "output" in text:
        return "mapping_update"
    if "constant" in text or "unknown" in text or "exclude" in text:
        return "field_override"
    return "instruction"


def _extract_user_selected_columns(message: str, available_columns: list[dict[str, Any]]) -> dict[str, list[str]]:
    text = message.lower()
    names = [str(col.get("column") or "") for col in available_columns]
    selected = {"inputs": [], "outputs": [], "mentioned": []}
    for name in names:
        if name and name.lower() in text:
            selected["mentioned"].append(name)
            before = text[: text.find(name.lower())]
            if "output" in before[-80:]:
                selected["outputs"].append(name)
            elif "input" in before[-80:]:
                selected["inputs"].append(name)
    return selected


def _build_mapping_board(contract_fields: list[dict[str, Any]], available_columns: list[dict[str, Any]], agent_plan: dict[str, Any], user_instruction: str) -> list[dict[str, Any]]:
    agent_mapping = agent_plan.get("mapping") if isinstance(agent_plan.get("mapping"), dict) else {}
    rows = []
    for field in contract_fields:
        field_name = str(field.get("field"))
        candidate = _best_column_candidate(field, available_columns)
        agent_candidate = agent_mapping.get(field_name) if isinstance(agent_mapping, dict) else None
        if isinstance(agent_candidate, dict):
            source = agent_candidate.get("source") or agent_candidate.get("source_column") or candidate.get("column")
            confidence = agent_candidate.get("confidence") or candidate.get("confidence")
            rationale = agent_candidate.get("rationale") or candidate.get("rationale")
        else:
            source = candidate.get("column")
            confidence = candidate.get("confidence")
            rationale = candidate.get("rationale")
        status = "mapped" if source else "missing"
        if _user_marked_field_override(user_instruction, field_name):
            status = "constant_or_unknown"
            source = source or "user-marked constant/unknown"
            confidence = "user_confirmed"
            rationale = "User instructed Mirai to treat this field as constant/unknown/excluded for this dataset."
        rows.append({
            "field": field_name,
            "variable_id": field.get("variable_id") or field_name,
            "source_name": field.get("source_name"),
            "ui_label": field.get("ui_label"),
            "role": field.get("role"),
            "dtype": field.get("dtype"),
            "unit": field.get("unit"),
            "required": field.get("required", True),
            "direction": field.get("direction"),
            "allowed_min": field.get("allowed_min"),
            "allowed_max": field.get("allowed_max"),
            "description": field.get("description"),
            "source_column": source,
            "source_table": candidate.get("table_name") or field.get("source_table"),
            "source_file": candidate.get("filename"),
            "confidence": confidence or "none",
            "status": status,
            "rationale": rationale or ("No matching source column found yet." if status == "missing" else "Matched from target contract labels/source names."),
        })
    return rows


def _user_marked_field_override(message: str, field_name: str) -> bool:
    text = message.lower()
    return field_name.lower() in text and any(word in text for word in ["constant", "unknown", "exclude", "ignore"])


def _best_column_candidate(field: dict[str, Any], available_columns: list[dict[str, Any]]) -> dict[str, Any]:
    field_names = [str(value or "") for value in [field.get("field"), field.get("variable_id"), field.get("source_name"), field.get("ui_label")]]
    field_tokens = {token for name in field_names for token in re.split(r"[^a-z0-9]+", name.lower()) if len(token) > 2}
    best: tuple[int, dict[str, Any]] = (0, {})
    for column in available_columns:
        name = str(column.get("column") or "")
        normalized = name.lower().replace("_", " ").replace("-", " ")
        column_tokens = {token for token in re.split(r"[^a-z0-9]+", normalized) if len(token) > 2}
        score = 0
        if any(field_name and field_name.lower() == name.lower() for field_name in field_names):
            score += 12
        score += len(field_tokens & column_tokens) * 3
        if str(field.get("source_table") or "") and str(field.get("source_table")) == str(column.get("table_name")):
            score += 2
        if score > best[0]:
            confidence = "high" if score >= 10 else "medium" if score >= 5 else "low"
            best = (score, {**column, "confidence": confidence, "rationale": f"Contract label/source-name match score {score}."})
    return best[1] if best[0] >= 3 else {}


def _specific_questions(mapping_board: list[dict[str, Any]], missing_fields: list[str], user_selected: dict[str, list[str]]) -> list[str]:
    questions = []
    if user_selected.get("inputs") or user_selected.get("outputs"):
        questions.append("I recorded your mentioned input/output columns. Confirm which Mirai contract fields each should populate, or approve the proposed board if correct.")
    for field in missing_fields[:8]:
        questions.append(f"Which available column should populate `{field}`, or should it be marked constant/unknown for this dataset?")
    if any(row.get("confidence") == "low" for row in mapping_board):
        questions.append("Please confirm low-confidence mappings before validation.")
    return questions


def _agent_response_text(user_intent: str, approved_mapping: bool, missing_fields: list[str], user_selected: dict[str, list[str]], mapping_board: list[dict[str, Any]], available_columns: list[dict[str, Any]]) -> str:
    mapped = [row for row in mapping_board if row.get("status") == "mapped"]
    if user_intent == "approve_all" and missing_fields:
        return "I cannot approve everything yet. I found proposed columns for some fields, but these required Mirai fields are still unmapped: " + ", ".join(missing_fields) + ". Tell me which available columns to use, mark them constant/unknown, or upload metadata containing them."
    if approved_mapping:
        return "I recorded your approval of the proposed mapping. Export is still blocked because the generic path needs an approved deterministic transform executor and contract validation package files."
    if user_selected.get("mentioned"):
        return "I found your mentioned columns (" + ", ".join(user_selected["mentioned"]) + ") and updated the mapping conversation. Please confirm the specific Mirai fields or approve the board once blockers are resolved."
    if available_columns:
        return f"I found {len(available_columns)} available source columns and proposed {len(mapped)} Mirai field mappings. Review the mapping board; tell me which columns to use as inputs/outputs or say 'approve suggested mapping' if it is correct."
    return "I indexed the uploaded files, but did not find tabular columns yet. Upload CSV/XLSX files or ZIPs containing them, or describe where the contract variables are located."


def _conversation_with_agent(session: dict[str, Any], agent_response: str) -> list[dict[str, Any]]:
    conversation = []
    for message in session.get("loop_iterations") or []:
        for turn in message.get("conversation") or []:
            if isinstance(turn, dict):
                conversation.append(turn)
    if session.get("user_instruction"):
        conversation.append({"role": "user", "content": session.get("user_instruction"), "created_at": _now()})
    conversation.append({"role": "assistant", "content": agent_response, "created_at": _now()})
    return conversation[-20:]


def _knowledge_intake_model() -> str:
    configured = os.getenv("MIRAI_KNOWLEDGE_INTAKE_MODEL") or os.getenv("ANTHROPIC_MODEL")
    if configured:
        aliases = {
            "fable-5": "claude-fable-5",
            "claude-fable-5": "claude-fable-5",
        }
        return aliases.get(configured.strip().lower(), configured)
    return "claude-sonnet-4-5"


def _infer_mapping_plan_with_anthropic(target_contract_id: str, user_instruction: str, source_inventory: list[dict[str, Any]], contract_fields: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    model = _knowledge_intake_model()
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"provider": "not_configured", "model": model, "questions": [], "mapping": None, "confidence": "none"}
    try:
        from anthropic import Anthropic

        client = Anthropic(timeout=float(os.getenv("MIRAI_KNOWLEDGE_INTAKE_TIMEOUT_SECONDS", "45")))
        prompt = {
            "target_contract_id": target_contract_id,
            "contract_fields": contract_fields or [],
            "user_instruction": user_instruction,
            "source_inventory": source_inventory,
            "constraints": [
                "Do not generate executable code.",
                "Return only a structured JSON planning object.",
                "Backend may execute only approved deterministic transform tools.",
                "List missing fields/questions required before validation/export.",
                "Suggest source columns for each Mirai contract field when possible, with confidence and rationale.",
            ],
        }
        response = client.messages.create(
            model=model,
            max_tokens=1800,
            system=(
                "You are Mirai's Knowledge Intake planner. Infer a source-to-contract mapping plan from uploaded source inventory. "
                "You never write executable code. You produce JSON only with keys: source_summary, available_columns, mapping, transform_plan, questions, blockers, suggested_user_actions, confidence. "
                "The mapping object should be keyed by Mirai contract field and include source_column, source_table, confidence, and rationale."
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
