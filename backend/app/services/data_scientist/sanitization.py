from __future__ import annotations

import copy
import re
from typing import Any

from .scope import AgentScope

_ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:/[A-Za-z0-9._@%+=:,~-]+)+(?:/[A-Za-z0-9._@%+=:,~-]+)*")
_S3_RE = re.compile(r"s3://[^\s'\")<>]+")
_FILE_RE = re.compile(r"file://[^\s'\")<>]+")
_WORKSPACE_KEY_RE = re.compile(r"\bworkspaces/[A-Za-z0-9_.-]+/[^\s'\")<>]+")
_OBJECT_KEY_HINT_RE = re.compile(r"\b(?:raw|intake|projects|datasets|mlflow-artifacts|preprocessing)/[^\s'\")<>]+")


def _sensitive_values(scope: AgentScope, extra_values: list[str] | None = None) -> list[str]:
    values = [scope.workspace_id, scope.clerk_user_id]
    if scope.workspace_id:
        values.append(f"workspaces/{scope.workspace_id}")
    values.extend(extra_values or [])
    return sorted({str(value) for value in values if value}, key=len, reverse=True)


def redact_sensitive_text(text: str, scope: AgentScope, extra_values: list[str] | None = None) -> str:
    redacted = text
    for value in _sensitive_values(scope, extra_values):
        label = "[workspace]" if value == scope.workspace_id or value.endswith(str(scope.workspace_id)) else "[user]"
        redacted = redacted.replace(value, label)
    redacted = _S3_RE.sub("[storage-uri]", redacted)
    redacted = _FILE_RE.sub("[storage-uri]", redacted)
    redacted = _WORKSPACE_KEY_RE.sub("[object-key]", redacted)
    redacted = _OBJECT_KEY_HINT_RE.sub("[object-key]", redacted)
    redacted = _ABSOLUTE_PATH_RE.sub("[path]", redacted)
    return redacted


def sanitize_agent_payload(value: Any, scope: AgentScope, extra_values: list[str] | None = None) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value, scope, extra_values)
    if isinstance(value, list):
        return [sanitize_agent_payload(item, scope, extra_values) for item in value]
    if isinstance(value, tuple):
        return [sanitize_agent_payload(item, scope, extra_values) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = redact_sensitive_text(str(key), scope, extra_values)
            if key_text in {"object_key", "object_uri", "root", "path", "local_path", "bucket", "prefix"}:
                sanitized[key_text] = "[redacted]"
            else:
                sanitized[key_text] = sanitize_agent_payload(item, scope, extra_values)
        return sanitized
    try:
        return copy.deepcopy(value)
    except Exception:  # noqa: BLE001
        return str(value)
