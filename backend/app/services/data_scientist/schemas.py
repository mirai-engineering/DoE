from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DataScientistRole(str, Enum):
    user = "user"
    assistant = "assistant"


class DataScientistMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: DataScientistRole
    content: str = Field(min_length=1, max_length=8000)


class DataScientistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    history: list[DataScientistMessage] = Field(default_factory=list, max_length=12)


class DataScientistStopReason(str, Enum):
    completed = "completed"
    max_turns = "max_turns"
    max_tool_calls = "max_tool_calls"
    repeated_tool_call = "repeated_tool_call"
    provider_unconfigured = "provider_unconfigured"
    provider_error = "provider_error"
    tool_error = "tool_error"
    timeout = "timeout"


class DataScientistEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["message", "tool_call", "tool_result", "warning", "error", "stop"]
    label: str
    detail: str | None = None
    tool_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UsageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None


class DataScientistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    stop_reason: DataScientistStopReason
    events: list[DataScientistEvent] = Field(default_factory=list)
    usage: UsageMetadata | None = None


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LatestSessionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)

    @field_validator("dataset_id", "session_id")
    @classmethod
    def safe_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if any(token in value for token in ("/", "\\", "..", "s3://", "file://")):
            raise ValueError("unsafe identifier")
        return value


class InventoryArgs(LatestSessionArgs):
    limit: int = Field(default=10, ge=1, le=25)


class TableProfileArgs(LatestSessionArgs):
    max_columns: int = Field(default=20, ge=1, le=50)
