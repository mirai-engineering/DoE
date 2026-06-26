from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class AgentScope:
    workspace_id: str | None
    project_id: str
    clerk_user_id: str | None = None


def authorize_agent_scope(
    request: Request,
    project_id: str,
    *,
    require_workspace: Callable[[Request], str | None],
    can_access_project: Callable[[Request, str], bool],
    user_id_for_request: Callable[[Request], str | None],
) -> AgentScope:
    workspace_id = require_workspace(request)
    if not can_access_project(request, project_id):
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return AgentScope(workspace_id=workspace_id, project_id=project_id, clerk_user_id=user_id_for_request(request))
