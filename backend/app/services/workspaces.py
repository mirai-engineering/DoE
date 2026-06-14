from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from .workspace_storage import local_object_storage_root, seed_object_storage_root


BACKEND_ROOT = Path(__file__).resolve().parents[2]
OBJECT_STORE_ROOT = local_object_storage_root()
WORKSPACES_ROOT = OBJECT_STORE_ROOT / "workspaces"
SEED_WORKSPACES_ROOT = seed_object_storage_root() / "workspaces"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def workspace_id_for_name(name: str | None) -> str:
    value = (name or "default-workspace").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return slug or "default-workspace"


def _workspace_path(workspace_id: str) -> Path:
    safe = workspace_id_for_name(workspace_id)
    return WORKSPACES_ROOT / safe / "workspace.json"


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def default_fraunhofer_workspace() -> dict[str, Any]:
    return {
        "workspace_id": "fraunhofer",
        "display_name": "Fraunhofer",
        "client_type": "demo_partner",
        "status": "active",
        "default_template_ids": ["generic_tabular_doe"],
        "allowed_extractors": [],
        "lifecycle_contract": "generic_tabular_doe",
        "notes": "Fraunhofer fuel-cell demo reshaped into the same generic Mirai tabular DoE lifecycle used for all projects.",
    }


def _seed_workspace_payload(workspace_id: str) -> dict[str, Any] | None:
    path = SEED_WORKSPACES_ROOT / workspace_id_for_name(workspace_id) / "workspace.json"
    return _read_json(path, default=None)


def ensure_seed_workspaces() -> None:
    """Create persistent seed clients that should survive project cleanup.

    Mirai Engineering is intentionally not seeded here; it is created when a user
    uploads a strict generic-contract project under that workspace. Tiny seed
    metadata is read from `backend/seeds/object_storage`, while generated local
    workspace state is written under the ignored local object-storage root.
    """
    ensure_workspace(_seed_workspace_payload("fraunhofer") or default_fraunhofer_workspace())


def ensure_workspace(payload: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(payload, str) or payload is None:
        display_name = payload or "Default workspace"
        workspace_payload: dict[str, Any] = {"display_name": display_name}
    else:
        workspace_payload = dict(payload)
        display_name = str(workspace_payload.get("display_name") or workspace_payload.get("workspace_name") or workspace_payload.get("workspace_id") or "Default workspace")
    workspace_id = workspace_id_for_name(str(workspace_payload.get("workspace_id") or display_name))
    path = _workspace_path(workspace_id)
    existing = _read_json(path, default={}) or {}
    created_at = existing.get("created_at") or _now()
    base = {
        "workspace_id": workspace_id,
        "display_name": display_name,
        "client_type": "customer_or_workspace",
        "status": "active",
        "default_template_ids": ["generic_tabular_doe"],
        "allowed_extractors": [],
        "lifecycle_contract": "generic_tabular_doe",
    }
    merged = {
        **base,
        **existing,
        **workspace_payload,
        "workspace_id": workspace_id,
        "display_name": display_name,
        "created_at": created_at,
        "updated_at": existing.get("updated_at") or _now(),
    }
    comparable_existing = {key: value for key, value in existing.items() if key != "updated_at"}
    comparable_merged = {key: value for key, value in merged.items() if key != "updated_at"}
    if existing and comparable_existing == comparable_merged:
        return existing
    merged["updated_at"] = _now()
    return _write_json(path, merged)


def get_workspace(workspace_id: str) -> dict[str, Any] | None:
    ensure_seed_workspaces()
    return _read_json(_workspace_path(workspace_id), default=None)


def list_workspaces() -> list[dict[str, Any]]:
    ensure_seed_workspaces()
    if not WORKSPACES_ROOT.exists():
        return []
    workspaces = [_read_json(path, default={}) for path in sorted(WORKSPACES_ROOT.glob("*/workspace.json"))]
    return [workspace for workspace in workspaces if workspace]
