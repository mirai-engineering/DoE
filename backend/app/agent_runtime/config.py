from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AgentRuntimeSettings:
    anthropic_api_key_present: bool
    model: str
    max_tokens: int
    provider_timeout_seconds: float
    loop_timeout_seconds: float
    max_turns: int
    max_tool_calls: int
    max_tool_output_chars: int


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def agent_runtime_settings() -> AgentRuntimeSettings:
    """Read server-side agent runtime settings from the process environment.

    Local development env vars are expected to be loaded by direnv from .envrc
    (including .env.local). Railway must provide the same variables as service
    variables. This module intentionally does not parse .env.local itself.
    """

    return AgentRuntimeSettings(
        anthropic_api_key_present=bool(os.getenv("ANTHROPIC_API_KEY")),
        model=os.getenv("MIRAI_AGENT_MODEL", "claude-opus-4-1-20250805"),
        max_tokens=_int_env("MIRAI_AGENT_MAX_TOKENS", 1000),
        provider_timeout_seconds=_float_env("MIRAI_AGENT_PROVIDER_TIMEOUT_SECONDS", 25.0),
        loop_timeout_seconds=_float_env("MIRAI_AGENT_TIMEOUT_SECONDS", 30.0),
        max_turns=_int_env("MIRAI_AGENT_MAX_TURNS", 4),
        max_tool_calls=_int_env("MIRAI_AGENT_MAX_TOOL_CALLS", 8),
        max_tool_output_chars=_int_env("MIRAI_AGENT_MAX_TOOL_OUTPUT_CHARS", 6000),
    )
