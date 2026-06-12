"""Typed contracts for the safe, on-demand GitHub MCP wrapper.

The models in this module intentionally expose only a narrow set of GitHub
operations needed by Pi-assisted branch and draft-PR workflows. Anything outside
this allowlist should be rejected before the MCP server is contacted.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GitHubOperation(StrEnum):
    """Operations this wrapper may dispatch to GitHub MCP."""

    INSPECT_REPO = "inspect_repo"
    CREATE_BRANCH = "create_branch"
    COMPARE_BRANCH = "compare_branch"
    CREATE_DRAFT_PR = "create_draft_pr"
    LIST_OWN_PRS = "list_own_prs"


ALLOWED_OPERATIONS = frozenset(item.value for item in GitHubOperation)
PROTECTED_BASE_BRANCHES = frozenset({"main", "master", "develop", "dev", "production", "prod"})
_BRANCH_RE = re.compile(r"^pi/[a-z0-9][a-z0-9._/-]{1,78}$")
_SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^\s'\"]{12,}"),
)


class ContractError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RepoRef(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    default_branch: str = "main"

    @field_validator("owner", "repo", "default_branch")
    @classmethod
    def no_blank_or_pathy_values(cls, value: str) -> str:
        value = value.strip()
        if not value or any(part in value for part in ("..", "/", "\\")):
            raise ValueError("must be a non-empty name, not a path")
        return value

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


class OperationRequest(BaseModel):
    operation: GitHubOperation
    repo: RepoRef


class InspectRepoRequest(OperationRequest):
    operation: Literal[GitHubOperation.INSPECT_REPO] = GitHubOperation.INSPECT_REPO


class ListOwnPullRequestsRequest(OperationRequest):
    operation: Literal[GitHubOperation.LIST_OWN_PRS] = GitHubOperation.LIST_OWN_PRS
    state: Literal["open", "closed", "all"] = "open"


class BranchCreateRequest(OperationRequest):
    operation: Literal[GitHubOperation.CREATE_BRANCH] = GitHubOperation.CREATE_BRANCH
    base_branch: str = "main"
    new_branch: str

    @field_validator("base_branch")
    @classmethod
    def base_branch_must_be_named(cls, value: str) -> str:
        value = value.strip()
        if not value or value.startswith("-") or ".." in value:
            raise ValueError("base branch must be a safe branch name")
        return value

    @field_validator("new_branch")
    @classmethod
    def branch_must_use_pi_prefix(cls, value: str) -> str:
        value = value.strip()
        if not _BRANCH_RE.fullmatch(value):
            raise ValueError("branch must match safe prefix pattern pi/<slug>")
        return value

    @model_validator(mode="after")
    def branch_must_not_target_same_ref(self) -> "BranchCreateRequest":
        if self.base_branch == self.new_branch:
            raise ValueError("new branch must differ from base branch")
        return self


class BranchCompareRequest(OperationRequest):
    operation: Literal[GitHubOperation.COMPARE_BRANCH] = GitHubOperation.COMPARE_BRANCH
    base_branch: str = "main"
    head_branch: str

    @field_validator("base_branch", "head_branch")
    @classmethod
    def branches_must_be_safe(cls, value: str) -> str:
        value = value.strip()
        if not value or value.startswith("-") or ".." in value or " " in value:
            raise ValueError("branch name must be safe")
        return value


class PullRequestCreateRequest(OperationRequest):
    operation: Literal[GitHubOperation.CREATE_DRAFT_PR] = GitHubOperation.CREATE_DRAFT_PR
    base_branch: str = "main"
    head_branch: str
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=20_000)
    draft: Literal[True] = True

    @field_validator("base_branch")
    @classmethod
    def base_branch_is_not_head_or_missing(cls, value: str) -> str:
        value = value.strip()
        if not value or value.startswith("-") or ".." in value:
            raise ValueError("base branch must be safe")
        return value

    @field_validator("head_branch")
    @classmethod
    def head_branch_must_use_pi_prefix(cls, value: str) -> str:
        value = value.strip()
        if not _BRANCH_RE.fullmatch(value):
            raise ValueError("head branch must match safe prefix pattern pi/<slug>")
        return value

    @field_validator("title", "body")
    @classmethod
    def text_must_not_contain_obvious_secret(cls, value: str) -> str:
        for pattern in _SECRET_PATTERNS:
            if pattern.search(value):
                raise ValueError("text appears to contain a secret-like value")
        return value

    @model_validator(mode="after")
    def pr_refs_must_be_valid(self) -> "PullRequestCreateRequest":
        if self.base_branch == self.head_branch:
            raise ValueError("head branch must differ from base branch")
        if self.base_branch.startswith("pi/"):
            raise ValueError("base branch may not be a Pi working branch")
        return self


class PullRequestSummary(BaseModel):
    number: int | None = None
    title: str
    url: str | None = None
    state: Literal["open", "closed", "merged", "draft"] | str = "open"
    head_branch: str
    base_branch: str
    draft: bool = True


class SafetyCheckResult(BaseModel):
    ok: bool
    errors: list[ContractError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def pass_(cls, warnings: list[str] | None = None) -> "SafetyCheckResult":
        return cls(ok=True, warnings=warnings or [])

    @classmethod
    def fail(cls, code: str, message: str, **details: Any) -> "SafetyCheckResult":
        return cls(ok=False, errors=[ContractError(code=code, message=message, details=details)])


class ToolDispatchResult(BaseModel):
    operation: GitHubOperation
    dry_run: bool = True
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    safety: SafetyCheckResult | None = None


def assert_allowed_operation(operation: str) -> GitHubOperation:
    """Return a typed operation or raise for anything outside the allowlist."""
    try:
        return GitHubOperation(operation)
    except ValueError as exc:
        raise ValueError(f"unsupported GitHub MCP operation: {operation}") from exc
