from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: str


@dataclass(frozen=True)
class ProjectContext:
    workspace_id: str
    project_id: str


@dataclass(frozen=True)
class DatasetContext:
    project_id: str
    dataset_id: str


@dataclass(frozen=True)
class SessionContext:
    project_id: str
    dataset_id: str | None
    session_id: str


@dataclass(frozen=True)
class UserContext:
    user_id: str | None = None
    display_name: str | None = None
