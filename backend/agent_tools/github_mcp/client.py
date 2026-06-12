"""Short-lived Python MCP client wrapper for GitHub MCP.

The MCP SDK is imported lazily so production backend imports are unaffected unless
this agent-only module is explicitly used with the `agent` dependency group.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

from .contracts import ToolDispatchResult, assert_allowed_operation
from .safety import check_allowlisted_tool
from .server_config import GitHubMcpServerConfig


# Conservative allowlist. Tool names in the official GitHub MCP server may vary
# by version, so the client also supports discovery and maps high-level wrapper
# operations in cli.py. Destructive tool names are rejected even if configured.
DEFAULT_ALLOWED_TOOL_NAMES = (
    "get_me",
    "search_repositories",
    "get_file_contents",
    "list_branches",
    "create_branch",
    "compare_branches",
    "list_pull_requests",
    "create_pull_request",
)


class GitHubMcpClientError(RuntimeError):
    """Raised when the on-demand MCP client cannot complete safely."""


class ShortLivedGitHubMcpClient:
    """Thin adapter around a single scoped MCP session."""

    def __init__(
        self,
        session: Any,
        *,
        allowed_tools: Sequence[str] = DEFAULT_ALLOWED_TOOL_NAMES,
    ) -> None:
        self._session = session
        self.allowed_tools = tuple(allowed_tools)

    async def list_tools(self) -> list[str]:
        response = await self._session.list_tools()
        tools = getattr(response, "tools", response)
        names: list[str] = []
        for tool in tools or []:
            name = getattr(tool, "name", None)
            if isinstance(name, str):
                names.append(name)
            elif isinstance(tool, Mapping) and isinstance(tool.get("name"), str):
                names.append(str(tool["name"]))
        return names

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        safety = check_allowlisted_tool(tool_name, self.allowed_tools)
        if not safety.ok:
            raise GitHubMcpClientError(safety.errors[0].message)
        return await self._session.call_tool(tool_name, dict(arguments or {}))

    async def dry_run_operation(self, operation: str, payload: Mapping[str, Any]) -> ToolDispatchResult:
        typed_operation = assert_allowed_operation(operation)
        return ToolDispatchResult(
            operation=typed_operation,
            dry_run=True,
            success=True,
            message="Dry run only; no GitHub MCP tool was called.",
            data={"payload": dict(payload)},
        )


@asynccontextmanager
async def with_github_mcp(
    config: GitHubMcpServerConfig | None = None,
    *,
    allowed_tools: Sequence[str] = DEFAULT_ALLOWED_TOOL_NAMES,
) -> AsyncIterator[ShortLivedGitHubMcpClient]:
    """Start/connect to GitHub MCP for one operation and close it afterwards."""

    config = config or GitHubMcpServerConfig.from_env()

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:  # pragma: no cover - exercised when group missing
        raise GitHubMcpClientError(
            "Python MCP SDK is not installed. Run: cd backend && uv sync --group agent"
        ) from exc

    server_params = StdioServerParameters(
        command=config.command,
        args=list(config.args),
        env=config.server_env(),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield ShortLivedGitHubMcpClient(session, allowed_tools=allowed_tools)
