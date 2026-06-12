from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_tools.github_mcp.server_config import GitHubMcpConfigError, GitHubMcpServerConfig


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "agent_tools.github_mcp.cli", *args],
        cwd=BACKEND_DIR,
        text=True,
        capture_output=True,
        env=merged_env,
        check=False,
    )


def test_preflight_works_without_github_env_in_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_OWNER", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)

    proc = run_cli("preflight", "--repo-root", str(REPO_ROOT), "--allow-dirty")

    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data["dry_run"] is True
    assert data["env"]["GITHUB_TOKEN"] is False


def test_create_branch_defaults_to_dry_run_and_does_not_need_env() -> None:
    proc = run_cli(
        "create-branch",
        "--repo-root",
        str(REPO_ROOT),
        "--allow-dirty",
        "--owner",
        "example",
        "--repo",
        "mirai",
        "--branch",
        "pi/test-cli-dry-run",
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data["dry_run"] is True
    assert data["data"]["mcp"]["tool"] == "create_branch"


def test_write_action_fails_without_apply() -> None:
    # The command exits successfully in dry-run mode, proving no write is attempted.
    proc = run_cli(
        "create-draft-pr",
        "--repo-root",
        str(REPO_ROOT),
        "--allow-dirty",
        "--owner",
        "example",
        "--repo",
        "mirai",
        "--head",
        "pi/test-cli-dry-run",
        "--title",
        "Dry run PR",
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert json.loads(proc.stdout)["dry_run"] is True


def test_apply_write_action_requires_yes() -> None:
    proc = run_cli(
        "create-branch",
        "--repo-root",
        str(REPO_ROOT),
        "--allow-dirty",
        "--owner",
        "example",
        "--repo",
        "mirai",
        "--branch",
        "pi/test-cli-apply",
        "--apply",
    )
    assert proc.returncode != 0
    assert "requires --yes" in proc.stderr or "requires --yes" in proc.stdout


def test_apply_with_yes_requires_github_env_before_contacting_mcp() -> None:
    env = {
        "GITHUB_TOKEN": "",
        "GITHUB_PERSONAL_ACCESS_TOKEN": "",
        "GITHUB_OWNER": "",
        "GITHUB_REPO": "",
    }
    proc = run_cli(
        "create-branch",
        "--repo-root",
        str(REPO_ROOT),
        "--allow-dirty",
        "--owner",
        "example",
        "--repo",
        "mirai",
        "--branch",
        "pi/test-cli-apply",
        "--apply",
        "--yes",
        env=env,
    )
    assert proc.returncode != 0
    assert "Missing required environment variables" in proc.stderr


def test_server_config_rejects_missing_env() -> None:
    with pytest.raises(GitHubMcpConfigError):
        GitHubMcpServerConfig.from_env({})


def test_server_config_maps_github_token_to_server_env() -> None:
    config = GitHubMcpServerConfig.from_env(
        {"GITHUB_TOKEN": "token-value", "GITHUB_OWNER": "owner", "GITHUB_REPO": "repo"}
    )
    env = config.server_env()
    assert env["GITHUB_TOKEN"] == "token-value"
    assert env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "token-value"
    assert config.full_name == "owner/repo"
