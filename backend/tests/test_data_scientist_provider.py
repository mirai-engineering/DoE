from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import copy

import pytest

from app.agent_runtime.providers.anthropic_provider import ProviderResult, call_provider
from app.services.data_scientist.agent_loop import run_data_scientist_agent
from app.services.data_scientist.scope import AgentScope


@dataclass
class FakeBlock:
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None


@dataclass
class FakeUsage:
    input_tokens: int = 12
    output_tokens: int = 7


@dataclass
class FakeResponse:
    content: list[FakeBlock]
    stop_reason: str = "end_turn"
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeMessages:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.responses.pop(0)


class FakeAnthropicClient:
    def __init__(self, responses: list[FakeResponse]):
        self.messages = FakeMessages(responses)


def test_mocked_anthropic_client_tool_use_then_final_answer(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret-key-never-return")
    monkeypatch.setenv("MIRAI_AGENT_MODEL", "claude-test-model")

    fake_client = FakeAnthropicClient(
        [
            FakeResponse([FakeBlock(type="tool_use", id="toolu_1", name="dataset_contract", input={})]),
            FakeResponse([FakeBlock(type="text", text="The active project has scoped metadata available.")]),
        ]
    )

    import app.services.data_scientist.agent_loop as loop_module
    import app.services.data_scientist.tools as tools_module

    def sdk_backed_call(messages, system, *, tools):
        return call_provider(messages, system, tools=tools, client_factory=lambda timeout: fake_client)

    monkeypatch.setattr(loop_module, "call_provider", sdk_backed_call)
    monkeypatch.setattr(tools_module, "list_projects", lambda workspace_id=None: [{"id": "project_a", "workspace_id": "workspace_a"}])
    monkeypatch.setattr(
        tools_module,
        "get_project_schema",
        lambda project_id, workspace_id=None: {"display_name": "Project A", "inputs": [{"name": "x"}], "outputs": [{"name": "y"}], "constraints": []},
    )

    response = run_data_scientist_agent(AgentScope(workspace_id="workspace_a", project_id="project_a", clerk_user_id="user_a"), "What is the schema?", [])

    assert response.stop_reason == "completed"
    assert "scoped metadata" in response.answer
    assert len(fake_client.messages.calls) == 2
    assert fake_client.messages.calls[0]["messages"][-1] == {"role": "user", "content": "What is the schema?"}
    assert any(tool["name"] == "dataset_contract" for tool in fake_client.messages.calls[0]["tools"])
    assert fake_client.messages.calls[1]["messages"][-1]["role"] == "user"
    assert fake_client.messages.calls[1]["messages"][-1]["content"][0]["type"] == "tool_result"


def test_missing_api_key_returns_provider_unconfigured_without_secret(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import app.services.data_scientist.tools as tools_module

    monkeypatch.setattr(tools_module, "list_projects", lambda workspace_id=None: [{"id": "project_a", "workspace_id": "workspace_a"}])
    monkeypatch.setattr(
        tools_module,
        "get_project_schema",
        lambda project_id, workspace_id=None: {"display_name": "Project A", "inputs": [], "outputs": [], "constraints": []},
    )

    response = run_data_scientist_agent(AgentScope(workspace_id="workspace_a", project_id="project_a", clerk_user_id="user_a"), "Summarize schema", [])

    assert response.stop_reason == "provider_unconfigured"
    assert "test-secret" not in response.model_dump_json()


def test_configured_provider_does_not_use_deterministic_fallback_and_redacts_secret(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret-key-never-return")
    import app.services.data_scientist.agent_loop as loop_module

    def final_answer(messages, system, *, tools):
        return ProviderResult(text="Final answer without secret.", tool_calls=[], usage={"model": "claude-test-model"})

    monkeypatch.setattr(loop_module, "call_provider", final_answer)

    response = run_data_scientist_agent(AgentScope(workspace_id="workspace_a", project_id="project_a", clerk_user_id="user_a"), "Hello", [])

    assert response.stop_reason == "completed"
    assert response.answer == "Final answer without secret."
    serialized = response.model_dump_json()
    assert "provider_unconfigured" not in serialized
    assert "test-secret-key-never-return" not in serialized
