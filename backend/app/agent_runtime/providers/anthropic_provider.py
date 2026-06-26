from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.agent_runtime.config import agent_runtime_settings


class ProviderNotConfigured(RuntimeError):
    code = "provider_unconfigured"


class ProviderDependencyMissing(RuntimeError):
    code = "provider_dependency_missing"


class ProviderError(RuntimeError):
    code = "provider_error"

    def __init__(self, message: str, *, diagnostic: str | None = None):
        super().__init__(message)
        self.diagnostic = diagnostic or message


class ProviderAuthenticationError(ProviderError):
    code = "provider_authentication_error"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limit"


class ProviderUnsupportedModelError(ProviderError):
    code = "provider_unsupported_model"


class ProviderInternalError(ProviderError):
    code = "provider_internal_error"


@dataclass(frozen=True)
class ProviderResult:
    text: str
    tool_calls: list[dict[str, Any]]
    stop_reason: str | None = None
    usage: dict[str, Any] | None = None


def provider_configured() -> bool:
    return agent_runtime_settings().anthropic_api_key_present


def _get(block: Any, key: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _tool_definitions(tools: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.args_model.model_json_schema(),
        }
        for tool in tools.values()
    ]


def default_client_factory(timeout: float) -> Any:
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover - exercised by explicit monkeypatch tests if needed.
        raise ProviderDependencyMissing("Anthropic SDK is not installed") from exc
    return Anthropic(timeout=timeout)


def _map_provider_exception(exc: Exception) -> ProviderError:
    try:
        from anthropic import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, BadRequestError, InternalServerError, NotFoundError, RateLimitError
    except ImportError:
        return ProviderDependencyMissing("Anthropic SDK is not installed")

    if isinstance(exc, AuthenticationError):
        return ProviderAuthenticationError("Anthropic authentication failed", diagnostic="authentication_failed")
    if isinstance(exc, APITimeoutError | APIConnectionError):
        return ProviderTimeoutError("Anthropic request timed out or could not connect", diagnostic=type(exc).__name__)
    if isinstance(exc, RateLimitError):
        return ProviderRateLimitError("Anthropic rate limit reached", diagnostic="rate_limited")
    if isinstance(exc, NotFoundError):
        return ProviderUnsupportedModelError("Anthropic model was not found or is unsupported", diagnostic="model_not_found")
    if isinstance(exc, BadRequestError):
        return ProviderUnsupportedModelError("Anthropic rejected the request; check model and tool schema", diagnostic="bad_request")
    if isinstance(exc, InternalServerError):
        return ProviderInternalError("Anthropic provider returned an internal error", diagnostic="internal_server_error")
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        if status in {400, 404}:
            return ProviderUnsupportedModelError("Anthropic rejected the model or request", diagnostic=f"status_{status}")
        if status == 401:
            return ProviderAuthenticationError("Anthropic authentication failed", diagnostic="status_401")
        if status == 429:
            return ProviderRateLimitError("Anthropic rate limit reached", diagnostic="status_429")
        if status and status >= 500:
            return ProviderInternalError("Anthropic provider returned an internal error", diagnostic=f"status_{status}")
    return ProviderError("Anthropic provider request failed", diagnostic=type(exc).__name__)


def call_provider(
    messages: list[dict[str, Any]],
    system: str,
    *,
    tools: dict[str, Any],
    client_factory: Callable[[float], Any] = default_client_factory,
) -> ProviderResult:
    settings = agent_runtime_settings()
    if not settings.anthropic_api_key_present:
        raise ProviderNotConfigured("Anthropic provider is not configured")

    client = client_factory(settings.provider_timeout_seconds)
    try:
        response = client.messages.create(
            model=settings.model,
            max_tokens=settings.max_tokens,
            system=system,
            messages=messages,
            tools=_tool_definitions(tools),
        )
    except ProviderDependencyMissing:
        raise
    except Exception as exc:  # noqa: BLE001 - mapped to safe provider errors below.
        raise _map_provider_exception(exc) from exc

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in _get(response, "content", []) or []:
        block_type = _get(block, "type")
        if block_type == "text":
            text = _get(block, "text", "")
            if text:
                text_parts.append(str(text))
        elif block_type == "tool_use":
            tool_calls.append({
                "id": _get(block, "id"),
                "name": _get(block, "name"),
                "input": _get(block, "input", {}) or {},
            })

    raw_usage = _get(response, "usage", None)
    usage: dict[str, Any] = {}
    if raw_usage:
        usage = {
            "input_tokens": _get(raw_usage, "input_tokens"),
            "output_tokens": _get(raw_usage, "output_tokens"),
        }
    usage["model"] = settings.model
    return ProviderResult(
        text="\n".join(part for part in text_parts if part).strip(),
        tool_calls=tool_calls,
        stop_reason=_get(response, "stop_reason"),
        usage=usage,
    )
