"""CLI for safe, on-demand GitHub MCP workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .client import GitHubMcpClientError, with_github_mcp
from .contracts import (
    BranchCompareRequest,
    BranchCreateRequest,
    GitHubOperation,
    InspectRepoRequest,
    ListOwnPullRequestsRequest,
    PullRequestCreateRequest,
    RepoRef,
    ToolDispatchResult,
)
from .safety import check_dirty_worktree, preflight_for_write
from .server_config import GitHubMcpConfigError, GitHubMcpServerConfig


def _json(data: Any) -> str:
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    return json.dumps(data, indent=2, sort_keys=True)


def _print(data: Any) -> None:
    print(_json(data))


def _repo_from_args(args: argparse.Namespace) -> RepoRef:
    owner = args.owner or os.environ.get("GITHUB_OWNER") or "unknown-owner"
    repo = args.repo or os.environ.get("GITHUB_REPO") or "unknown-repo"
    return RepoRef(owner=owner, repo=repo, default_branch=args.base)


def _env_status() -> dict[str, bool]:
    return {
        "GITHUB_TOKEN": bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")),
        "GITHUB_OWNER": bool(os.environ.get("GITHUB_OWNER")),
        "GITHUB_REPO": bool(os.environ.get("GITHUB_REPO")),
    }


def _require_apply(args: argparse.Namespace) -> None:
    if not args.apply:
        raise SystemExit("Write action refused: rerun with --apply after reviewing the dry-run output.")
    if not args.yes:
        raise SystemExit("Write action refused: --apply also requires --yes for explicit confirmation.")


async def _maybe_call_tool(tool: str, payload: Mapping[str, Any], *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"dry_run": True, "tool": tool, "payload": dict(payload)}
    config = GitHubMcpServerConfig.from_env()
    async with with_github_mcp(config) as client:
        response = await client.call_tool(tool, payload)
    return {"dry_run": False, "tool": tool, "response": repr(response)}


async def cmd_preflight(args: argparse.Namespace) -> int:
    status = check_dirty_worktree(args.repo_root, allow_dirty=args.allow_dirty)
    env = _env_status()
    result = {
        "ok": status.ok,
        "dry_run": True,
        "repo_root": str(Path(args.repo_root).resolve()),
        "env": env,
        "errors": [e.model_dump() for e in status.errors],
        "warnings": status.warnings,
        "note": "Missing GitHub env vars are acceptable for local dry-run preflight but required for --apply operations.",
    }
    _print(result)
    return 0 if status.ok else 2


async def cmd_inspect_repo(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)
    request = InspectRepoRequest(repo=repo)
    payload = {"owner": repo.owner, "repo": repo.repo}
    data = await _maybe_call_tool("get_file_contents", payload, dry_run=not args.apply)
    _print(ToolDispatchResult(
        operation=GitHubOperation.INSPECT_REPO,
        dry_run=not args.apply,
        success=True,
        message=f"Inspect repository {repo.full_name}",
        data={"request": request.model_dump(mode="json"), "mcp": data},
    ))
    return 0


async def cmd_create_branch(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)
    request = BranchCreateRequest(repo=repo, base_branch=args.base, new_branch=args.branch)
    safety = preflight_for_write(
        repo_root=args.repo_root,
        branch=request.new_branch,
        base_branch=request.base_branch,
        paths=args.path,
        allow_dirty=args.allow_dirty,
    )
    if not safety.ok:
        _print({"ok": False, "safety": safety.model_dump(mode="json")})
        return 2
    if args.apply:
        _require_apply(args)
    payload = {
        "owner": repo.owner,
        "repo": repo.repo,
        "branch": request.new_branch,
        "from_branch": request.base_branch,
    }
    data = await _maybe_call_tool("create_branch", payload, dry_run=not args.apply)
    _print(ToolDispatchResult(
        operation=GitHubOperation.CREATE_BRANCH,
        dry_run=not args.apply,
        success=True,
        message=f"Create branch {request.new_branch} from {request.base_branch}",
        data={"request": request.model_dump(mode="json"), "mcp": data},
        safety=safety,
    ))
    return 0


async def cmd_compare(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)
    request = BranchCompareRequest(repo=repo, base_branch=args.base, head_branch=args.head)
    payload = {"owner": repo.owner, "repo": repo.repo, "base": request.base_branch, "head": request.head_branch}
    data = await _maybe_call_tool("compare_branches", payload, dry_run=not args.apply)
    _print(ToolDispatchResult(
        operation=GitHubOperation.COMPARE_BRANCH,
        dry_run=not args.apply,
        success=True,
        message=f"Compare {request.base_branch}...{request.head_branch}",
        data={"request": request.model_dump(mode="json"), "mcp": data},
    ))
    return 0


async def cmd_create_draft_pr(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)
    body = args.body or "Created by Pi via the safe on-demand GitHub MCP wrapper."
    request = PullRequestCreateRequest(
        repo=repo,
        base_branch=args.base,
        head_branch=args.head,
        title=args.title,
        body=body,
    )
    safety = preflight_for_write(
        repo_root=args.repo_root,
        branch=request.head_branch,
        base_branch=request.base_branch,
        paths=args.path,
        texts=[request.title, request.body],
        allow_dirty=args.allow_dirty,
    )
    if not safety.ok:
        _print({"ok": False, "safety": safety.model_dump(mode="json")})
        return 2
    if args.apply:
        _require_apply(args)
    payload = {
        "owner": repo.owner,
        "repo": repo.repo,
        "title": request.title,
        "body": request.body,
        "head": request.head_branch,
        "base": request.base_branch,
        "draft": True,
    }
    data = await _maybe_call_tool("create_pull_request", payload, dry_run=not args.apply)
    _print(ToolDispatchResult(
        operation=GitHubOperation.CREATE_DRAFT_PR,
        dry_run=not args.apply,
        success=True,
        message=f"Create draft PR {request.head_branch} -> {request.base_branch}",
        data={"request": request.model_dump(mode="json"), "mcp": data},
        safety=safety,
    ))
    return 0


async def cmd_list_own_prs(args: argparse.Namespace) -> int:
    repo = _repo_from_args(args)
    request = ListOwnPullRequestsRequest(repo=repo, state=args.state)
    payload = {"owner": repo.owner, "repo": repo.repo, "state": request.state}
    data = await _maybe_call_tool("list_pull_requests", payload, dry_run=not args.apply)
    _print(ToolDispatchResult(
        operation=GitHubOperation.LIST_OWN_PRS,
        dry_run=not args.apply,
        success=True,
        message=f"List own PRs for {repo.full_name}",
        data={"request": request.model_dump(mode="json"), "mcp": data},
    ))
    return 0


def _add_common_args(parser: argparse.ArgumentParser, *, suppress_defaults: bool = False) -> None:
    default = argparse.SUPPRESS if suppress_defaults else None
    bool_default = argparse.SUPPRESS if suppress_defaults else False
    parser.add_argument("--repo-root", default=".." if default is None else default, help="Repository root when running from backend (default: ..)")
    parser.add_argument("--owner", default=default, help="GitHub owner; defaults to GITHUB_OWNER")
    parser.add_argument("--repo", default=default, help="GitHub repo; defaults to GITHUB_REPO")
    parser.add_argument("--base", default="main" if default is None else default, help="Base branch (default: main)")
    parser.add_argument("--apply", action="store_true", default=bool_default, help="Actually contact GitHub MCP for this operation")
    parser.add_argument("--yes", action="store_true", default=bool_default, help="Explicit confirmation required with --apply for write operations")
    parser.add_argument("--allow-dirty", action="store_true", default=bool_default, help="Allow dirty local worktree after reporting it")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mirai-github-mcp", description="Safe on-demand GitHub MCP wrapper for Pi")
    _add_common_args(parser)

    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight", help="Run local dry-run safety checks")
    _add_common_args(preflight, suppress_defaults=True)
    preflight.set_defaults(func=cmd_preflight)
    inspect_repo = sub.add_parser("inspect-repo", help="Inspect configured repository")
    _add_common_args(inspect_repo, suppress_defaults=True)
    inspect_repo.set_defaults(func=cmd_inspect_repo)

    create_branch = sub.add_parser("create-branch", help="Create a pi/<slug> branch")
    _add_common_args(create_branch, suppress_defaults=True)
    create_branch.add_argument("--branch", required=True, help="New branch name; must start with pi/")
    create_branch.add_argument("--path", action="append", default=[], help="Path intended for commit/PR; checked for protected prefixes")
    create_branch.set_defaults(func=cmd_create_branch)

    compare = sub.add_parser("compare", help="Compare base branch with head branch")
    _add_common_args(compare, suppress_defaults=True)
    compare.add_argument("--head", required=True, help="Head branch to compare")
    compare.set_defaults(func=cmd_compare)

    pr = sub.add_parser("create-draft-pr", help="Create a draft PR from a pi/<slug> branch")
    _add_common_args(pr, suppress_defaults=True)
    pr.add_argument("--head", required=True, help="Head branch; must start with pi/")
    pr.add_argument("--title", required=True, help="Draft PR title")
    pr.add_argument("--body", default="", help="Draft PR body")
    pr.add_argument("--path", action="append", default=[], help="Path intended for PR; checked for protected prefixes")
    pr.set_defaults(func=cmd_create_draft_pr)

    prs = sub.add_parser("list-own-prs", help="List PRs in the configured repository")
    _add_common_args(prs, suppress_defaults=True)
    prs.add_argument("--state", choices=("open", "closed", "all"), default="open")
    prs.set_defaults(func=cmd_list_own_prs)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(args.func(args))
    except (GitHubMcpConfigError, GitHubMcpClientError, ValueError) as exc:
        print(f"mirai-github-mcp: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
