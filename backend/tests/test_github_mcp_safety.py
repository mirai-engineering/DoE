from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_tools.github_mcp.contracts import (
    BranchCreateRequest,
    PullRequestCreateRequest,
    RepoRef,
    assert_allowed_operation,
)
from agent_tools.github_mcp.safety import (
    check_allowlisted_tool,
    check_branch_name,
    check_destructive_operation,
    check_paths,
    check_secret_text,
    preflight_for_write,
)


def repo() -> RepoRef:
    return RepoRef(owner="example", repo="mirai")


def test_contract_rejects_unsupported_operation() -> None:
    with pytest.raises(ValueError):
        assert_allowed_operation("delete_repository")


def test_branch_contract_requires_pi_prefix() -> None:
    with pytest.raises(ValidationError):
        BranchCreateRequest(repo=repo(), base_branch="main", new_branch="feature/raw")

    request = BranchCreateRequest(repo=repo(), base_branch="main", new_branch="pi/safe-branch")
    assert request.new_branch == "pi/safe-branch"


def test_pr_contract_rejects_secret_like_body() -> None:
    with pytest.raises(ValidationError):
        PullRequestCreateRequest(
            repo=repo(),
            base_branch="main",
            head_branch="pi/safe-branch",
            title="safe",
            body="api_key = '12345678901234567890'",
        )


def test_safety_rejects_protected_paths() -> None:
    result = check_paths(["backend/app/main.py", "backend/mlruns/123/meta.yaml", ".env.local"])
    assert not result.ok
    assert result.errors[0].code == "protected_paths"


def test_safety_rejects_unsafe_branch_name() -> None:
    assert not check_branch_name("main").ok
    assert not check_branch_name("pi/../bad").ok
    assert check_branch_name("pi/add-safe-wrapper").ok


def test_safety_rejects_secret_text() -> None:
    result = check_secret_text("GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz")
    assert not result.ok
    assert result.errors[0].code == "secret_like_content"


def test_safety_rejects_destructive_operations_and_unlisted_tools() -> None:
    assert not check_destructive_operation("delete_branch").ok
    assert not check_allowlisted_tool("delete_branch", ["create_branch"]).ok
    assert not check_allowlisted_tool("create_issue", ["create_branch"]).ok
    assert check_allowlisted_tool("create_branch", ["create_branch"]).ok


def test_preflight_for_write_combines_failures(tmp_path: Path) -> None:
    # A non-git temp dir makes git status fail; use the current repo root for git
    # status and force other deterministic failures through args.
    result = preflight_for_write(
        repo_root=Path(__file__).resolve().parents[2],
        branch="unsafe",
        base_branch="pi/not-a-base",
        paths=["data/reference/file.csv"],
        texts=["password=12345678901234567890"],
        allow_dirty=True,
    )
    assert not result.ok
    codes = {error.code for error in result.errors}
    assert {"branch_prefix", "pi_base_branch", "protected_paths", "secret_like_content"}.issubset(codes)
