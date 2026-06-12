"""Environment-driven GitHub MCP server launch configuration."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from typing import Mapping


class GitHubMcpConfigError(RuntimeError):
    """Raised when required GitHub MCP configuration is missing or unsafe."""


@dataclass(frozen=True)
class GitHubMcpServerConfig:
    """Configuration for launching the official GitHub MCP server over stdio.

    Defaults to Docker because GitHub publishes an official container image for
    `github/github-mcp-server`. Override `GITHUB_MCP_COMMAND` and
    `GITHUB_MCP_ARGS` if using a locally installed server binary instead.
    """

    token: str
    owner: str
    repo: str
    command: str = "docker"
    args: tuple[str, ...] = (
        "run",
        "-i",
        "--rm",
        "-e",
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "-e",
        "GITHUB_TOKEN",
        "ghcr.io/github/github-mcp-server",
    )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "GitHubMcpServerConfig":
        env = os.environ if env is None else env
        token = (env.get("GITHUB_TOKEN") or env.get("GITHUB_PERSONAL_ACCESS_TOKEN") or "").strip()
        owner = (env.get("GITHUB_OWNER") or "").strip()
        repo = (env.get("GITHUB_REPO") or "").strip()
        missing = [name for name, value in (("GITHUB_TOKEN", token), ("GITHUB_OWNER", owner), ("GITHUB_REPO", repo)) if not value]
        if missing:
            raise GitHubMcpConfigError(f"Missing required environment variables: {', '.join(missing)}")
        if any(part in owner for part in ("/", "\\", "..")) or any(part in repo for part in ("/", "\\", "..")):
            raise GitHubMcpConfigError("GITHUB_OWNER and GITHUB_REPO must be names, not paths")

        command = (env.get("GITHUB_MCP_COMMAND") or cls.command).strip()
        raw_args = env.get("GITHUB_MCP_ARGS")
        args = tuple(shlex.split(raw_args)) if raw_args else cls.args
        if not command:
            raise GitHubMcpConfigError("GITHUB_MCP_COMMAND may not be empty")
        return cls(token=token, owner=owner, repo=repo, command=command, args=args)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    def server_env(self) -> dict[str, str]:
        env = dict(os.environ)
        # The plan uses GITHUB_TOKEN; the official server has historically used
        # GITHUB_PERSONAL_ACCESS_TOKEN. Provide both to avoid version drift.
        env["GITHUB_TOKEN"] = self.token
        env["GITHUB_PERSONAL_ACCESS_TOKEN"] = self.token
        env["GITHUB_OWNER"] = self.owner
        env["GITHUB_REPO"] = self.repo
        return env
