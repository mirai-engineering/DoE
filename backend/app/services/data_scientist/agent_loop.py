from __future__ import annotations

import json
import time
from typing import Any

from app.agent_runtime.config import agent_runtime_settings

from .provider import ProviderDependencyMissing, ProviderError, ProviderNotConfigured, call_provider, provider_configured
from .sanitization import redact_sensitive_text, sanitize_agent_payload
from .schemas import DataScientistEvent, DataScientistMessage, DataScientistResponse, DataScientistStopReason, UsageMetadata
from .scope import AgentScope
from .tools import TOOLS, AgentToolError

_SYSTEM_PROMPT = """You are Mirai's Data Scientist assistant. Answer only about the authenticated active project. Use provided read-only tools when you need project data, preprocessing, ML preprocessing plans/artifacts, or model quality facts. Do not reveal hidden reasoning, raw workspace IDs, Clerk user IDs, filesystem paths, object-store URIs, object keys, or storage prefixes. If data is unavailable, say so briefly. For ML preprocessing, explain deterministic tool choices, train-only fitting, binary-indicator handling, exported files, and what remains configurable before approval."""


def _event(type_: str, label: str, scope: AgentScope, *, detail: str | None = None, tool_name: str | None = None, metadata: dict[str, Any] | None = None) -> DataScientistEvent:
    return DataScientistEvent(type=type_, label=label, detail=redact_sensitive_text(detail, scope) if detail else None, tool_name=tool_name, metadata=sanitize_agent_payload(metadata or {}, scope))


def _truncate_json(value: Any, scope: AgentScope) -> str:
    text = json.dumps(sanitize_agent_payload(value, scope), ensure_ascii=False, default=str)
    max_chars = agent_runtime_settings().max_tool_output_chars
    if len(text) > max_chars:
        return text[:max_chars] + "… [truncated]"
    return text


def _initial_tool_names(question: str) -> list[str]:
    lowered = question.lower()
    names = ["dataset_contract"]
    if any(word in lowered for word in ("upload", "file", "artifact", "inventory", "dataset")):
        names.append("artifact_inventory")
    if any(word in lowered for word in ("column", "schema", "table", "profile", "sample", "distribution")):
        names.append("table_profile")
    if any(word in lowered for word in ("preprocess", "eda", "clean", "status")):
        names.append("preprocessing_status")
    if any(word in lowered for word in ("ml preprocessing", "ml-preprocessing", "model_table_preprocessed", "preprocessed", "one-hot", "one hot", "binary", "x7", "tool plan", "fitted")):
        names.append("ml_preprocessing_summary")
    if any(word in lowered for word in ("model", "metric", "quality", "train", "run", "rmse", "prediction")):
        names.extend(["training_summary", "model_quality"])
    return list(dict.fromkeys(names))[: agent_runtime_settings().max_tool_calls]


def _local_summary(question: str, tool_results: dict[str, Any]) -> str:
    parts = ["I reviewed the active project's available metadata."]
    if "dataset_contract" in tool_results:
        contract = tool_results["dataset_contract"]
        parts.append(f"The project has {len(contract.get('inputs', []))} input field(s) and {len(contract.get('outputs', []))} output field(s).")
    if "artifact_inventory" in tool_results:
        inv = tool_results["artifact_inventory"]
        parts.append(f"Uploaded data inventory status is {inv.get('status', 'unknown')} with {inv.get('file_count', 0)} file(s).")
    if "preprocessing_status" in tool_results:
        status = tool_results["preprocessing_status"].get("status", "unknown")
        parts.append(f"Preprocessing status is {status}.")
    if "ml_preprocessing_summary" in tool_results:
        ml_status = tool_results["ml_preprocessing_summary"].get("status", "unknown")
        table = tool_results["ml_preprocessing_summary"].get("table", {})
        binary = table.get("binary_columns", []) if isinstance(table, dict) else []
        parts.append(f"ML preprocessing status is {ml_status}.")
        if binary:
            parts.append(f"Binary indicator columns detected: {', '.join(map(str, binary[:8]))}. They are normally kept as one 0/1 feature rather than one-hot encoded into redundant paired columns.")
    if "model_quality" in tool_results or "training_summary" in tool_results:
        parts.append("Model/training metadata is available in the activity details when present; use the Model Quality tab for full charts.")
    parts.append("I only used read-only, workspace-scoped project tools.")
    return " ".join(parts)


def run_data_scientist_agent(scope: AgentScope, message: str, history: list[DataScientistMessage]) -> DataScientistResponse:
    started = time.monotonic()
    events: list[DataScientistEvent] = [_event("message", "Received question", scope)]
    safe_message = redact_sensitive_text(message, scope)
    safe_history = [
        {"role": item.role.value, "content": redact_sensitive_text(item.content, scope)}
        for item in history[-12:]
    ]

    settings = agent_runtime_settings()

    if not provider_configured():
        tool_results: dict[str, Any] = {}
        for name in _initial_tool_names(safe_message)[: settings.max_tool_calls]:
            if time.monotonic() - started > settings.loop_timeout_seconds:
                return DataScientistResponse(answer="The request timed out before I could finish checking the project metadata.", stop_reason=DataScientistStopReason.timeout, events=events)
            events.append(_event("tool_call", f"Checking {name.replace('_', ' ')}", scope, tool_name=name))
            try:
                tool_results[name] = TOOLS[name].run(scope, {})
                events.append(_event("tool_result", f"Checked {name.replace('_', ' ')}", scope, tool_name=name, metadata={"result": tool_results[name]}))
            except Exception as exc:  # noqa: BLE001
                events.append(_event("error", "Tool unavailable", scope, detail=str(exc), tool_name=name))
        answer = redact_sensitive_text(_local_summary(safe_message, tool_results), scope)
        events.append(_event("stop", "Provider not configured; returned scoped metadata summary", scope))
        return DataScientistResponse(answer=answer, stop_reason=DataScientistStopReason.provider_unconfigured, events=events)

    provider_messages: list[dict[str, Any]] = [*safe_history, {"role": "user", "content": safe_message}]
    seen_calls: set[tuple[str, str]] = set()
    usage: UsageMetadata | None = None
    tool_call_count = 0

    for _turn in range(settings.max_turns):
        if time.monotonic() - started > settings.loop_timeout_seconds:
            return DataScientistResponse(answer="The request timed out before I could finish.", stop_reason=DataScientistStopReason.timeout, events=events, usage=usage)
        try:
            result = call_provider(provider_messages, _SYSTEM_PROMPT, tools=TOOLS)
        except ProviderNotConfigured:
            return DataScientistResponse(answer="The data scientist provider is not configured.", stop_reason=DataScientistStopReason.provider_unconfigured, events=events, usage=usage)
        except ProviderDependencyMissing as exc:
            events.append(_event("error", "Provider SDK missing", scope, detail=str(exc)))
            return DataScientistResponse(answer="The data scientist provider dependency is not installed on the backend.", stop_reason=DataScientistStopReason.provider_error, events=events, usage=usage)
        except ProviderError as exc:
            events.append(_event("error", "Provider error", scope, detail=str(exc), metadata={"diagnostic": getattr(exc, "diagnostic", type(exc).__name__)}))
            return DataScientistResponse(answer="I could not reach the data scientist provider. Please try again later.", stop_reason=DataScientistStopReason.provider_error, events=events, usage=usage)
        if result.usage:
            usage = UsageMetadata(input_tokens=result.usage.get("input_tokens"), output_tokens=result.usage.get("output_tokens"), model=result.usage.get("model"))
        if not result.tool_calls:
            answer = redact_sensitive_text(result.text or "I could not produce an answer from the available project metadata.", scope)
            return DataScientistResponse(answer=answer, stop_reason=DataScientistStopReason.completed, events=events, usage=usage)
        assistant_blocks: list[dict[str, Any]] = []
        if result.text:
            assistant_blocks.append({"type": "text", "text": redact_sensitive_text(result.text, scope)})
        tool_result_blocks: list[dict[str, Any]] = []
        for call in result.tool_calls:
            tool_call_count += 1
            if tool_call_count > settings.max_tool_calls:
                return DataScientistResponse(answer="I stopped because the tool-call limit was reached.", stop_reason=DataScientistStopReason.max_tool_calls, events=events, usage=usage)
            name = str(call.get("name") or "")
            args = call.get("input") or {}
            fingerprint = (name, json.dumps(args, sort_keys=True, default=str))
            if fingerprint in seen_calls:
                return DataScientistResponse(answer="I stopped because the same tool request repeated.", stop_reason=DataScientistStopReason.repeated_tool_call, events=events, usage=usage)
            seen_calls.add(fingerprint)
            assistant_blocks.append({"type": "tool_use", "id": call.get("id"), "name": name, "input": sanitize_agent_payload(args, scope)})
            if name not in TOOLS:
                content = {"error": "Unknown tool"}
            else:
                events.append(_event("tool_call", f"Checking {name.replace('_', ' ')}", scope, tool_name=name))
                try:
                    content = TOOLS[name].run(scope, args if isinstance(args, dict) else {})
                    events.append(_event("tool_result", f"Checked {name.replace('_', ' ')}", scope, tool_name=name, metadata={"result": content}))
                except AgentToolError as exc:
                    content = {"error": str(exc)}
                    events.append(_event("error", "Tool rejected unsafe request", scope, detail=str(exc), tool_name=name))
                except Exception as exc:  # noqa: BLE001
                    content = {"error": "Tool failed"}
                    events.append(_event("error", "Tool failed", scope, detail=str(exc), tool_name=name))
            tool_result_blocks.append({"type": "tool_result", "tool_use_id": call.get("id"), "content": _truncate_json(content, scope)})
        provider_messages.append({"role": "assistant", "content": assistant_blocks})
        provider_messages.append({"role": "user", "content": tool_result_blocks})

    return DataScientistResponse(answer="I stopped because the turn limit was reached.", stop_reason=DataScientistStopReason.max_turns, events=events, usage=usage)
