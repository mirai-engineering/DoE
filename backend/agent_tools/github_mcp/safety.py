"""Safety checks for Pi's on-demand GitHub MCP workflow."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .contracts import ContractError, SafetyCheckResult


PROTECTED_PATH_PREFIXES = (
    "data/",
    "backend/mlruns/",
    "backend/data-minio/",
    "legacy/",
)

PROTECTED_PATH_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
}

DESTRUCTIVE_OPERATION_HINTS = (
    "delete",
    "remove",
    "force",
    "merge",
    "publish",
    "workflow",
    "admin",
    "secret",
    "deploy_key",
)

SAFE_BRANCH_RE = re.compile(r"^pi/[a-z0-9][a-z0-9._/-]{1,78}$")
PROTECTED_BASE_BRANCHES = {"main", "master", "develop", "dev", "production", "prod"}

SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^\s'\"]{12,}"),
)


@dataclass(frozen=True)
class GitStatus:
    clean: bool
    changed_paths: tuple[str, ...]


def _error(code: str, message: str, **details: object) -> ContractError:
    return ContractError(code=code, message=message, details=dict(details))


def combine_results(*results: SafetyCheckResult) -> SafetyCheckResult:
    errors: list[ContractError] = []
    warnings: list[str] = []
    for result in results:
        errors.extend(result.errors)
        warnings.extend(result.warnings)
    return SafetyCheckResult(ok=not errors, errors=errors, warnings=warnings)


def run_git_status(repo_root: Path | str = ".") -> GitStatus:
    root = Path(repo_root)
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git status failed: {proc.stderr.strip()}")
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        # Porcelain lines start with two status chars and a space. Renames use
        # `old -> new`; guard both sides by preserving the whole string split.
        raw = line[3:] if len(line) > 3 else line
        if " -> " in raw:
            paths.extend(part.strip() for part in raw.split(" -> "))
        else:
            paths.append(raw.strip())
    return GitStatus(clean=not paths, changed_paths=tuple(paths))


def check_dirty_worktree(repo_root: Path | str = ".", *, allow_dirty: bool = False) -> SafetyCheckResult:
    status = run_git_status(repo_root)
    if status.clean or allow_dirty:
        warnings = [] if status.clean else ["working tree is dirty but allow_dirty=True was set"]
        return SafetyCheckResult.pass_(warnings)
    return SafetyCheckResult.fail(
        "dirty_worktree",
        "Refusing GitHub write workflow while the working tree has unreviewed changes.",
        changed_paths=list(status.changed_paths),
    )


def is_protected_path(path: str | os.PathLike[str]) -> bool:
    normalized = Path(path).as_posix().lstrip("./")
    name = Path(normalized).name
    if name in PROTECTED_PATH_NAMES or name.startswith(".env"):
        return True
    if normalized.endswith(('.pem', '.key', '.p12', '.pfx')):
        return True
    return any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in PROTECTED_PATH_PREFIXES)


def check_paths(paths: Iterable[str]) -> SafetyCheckResult:
    protected = sorted({p for p in paths if is_protected_path(p)})
    if protected:
        return SafetyCheckResult.fail(
            "protected_paths",
            "Refusing operation involving protected data/artifact/secret paths.",
            paths=protected,
        )
    return SafetyCheckResult.pass_()


def check_secret_text(*texts: str) -> SafetyCheckResult:
    hits: list[str] = []
    for idx, text in enumerate(texts):
        for pattern in SECRET_PATTERNS:
            if pattern.search(text or ""):
                hits.append(f"text[{idx}]:{pattern.pattern}")
    if hits:
        return SafetyCheckResult.fail(
            "secret_like_content",
            "Refusing operation because text appears to contain a secret-like value.",
            patterns=hits,
        )
    return SafetyCheckResult.pass_()


def check_branch_name(branch: str, *, require_pi_prefix: bool = True) -> SafetyCheckResult:
    if not branch or branch.startswith("-") or ".." in branch or " " in branch or branch.endswith("/"):
        return SafetyCheckResult.fail("unsafe_branch", "Branch name contains unsafe syntax.", branch=branch)
    if require_pi_prefix and not SAFE_BRANCH_RE.fullmatch(branch):
        return SafetyCheckResult.fail(
            "branch_prefix",
            "Pi-created branches must use the safe pi/<slug> prefix.",
            branch=branch,
        )
    return SafetyCheckResult.pass_()


def check_base_branch(base_branch: str) -> SafetyCheckResult:
    if not base_branch or base_branch.startswith("-") or ".." in base_branch or " " in base_branch:
        return SafetyCheckResult.fail("unsafe_base_branch", "Base branch name is unsafe.", branch=base_branch)
    if base_branch.startswith("pi/"):
        return SafetyCheckResult.fail(
            "pi_base_branch",
            "Base branch may not be a Pi working branch.",
            branch=base_branch,
        )
    if base_branch not in PROTECTED_BASE_BRANCHES:
        return SafetyCheckResult.pass_([f"base branch '{base_branch}' is not a standard protected branch name"])
    return SafetyCheckResult.pass_()


def check_destructive_operation(operation_or_tool: str) -> SafetyCheckResult:
    lowered = operation_or_tool.lower()
    for hint in DESTRUCTIVE_OPERATION_HINTS:
        if hint in lowered:
            return SafetyCheckResult.fail(
                "destructive_operation",
                "Refusing destructive or out-of-scope GitHub MCP operation.",
                operation=operation_or_tool,
                matched_hint=hint,
            )
    return SafetyCheckResult.pass_()


def check_allowlisted_tool(tool_name: str, allowed_tools: Sequence[str]) -> SafetyCheckResult:
    if tool_name not in set(allowed_tools):
        return SafetyCheckResult.fail(
            "tool_not_allowlisted",
            "Refusing GitHub MCP tool outside the wrapper allowlist.",
            tool=tool_name,
            allowed=list(allowed_tools),
        )
    return check_destructive_operation(tool_name)


def preflight_for_write(
    *,
    repo_root: Path | str = ".",
    branch: str,
    base_branch: str = "main",
    paths: Iterable[str] = (),
    texts: Iterable[str] = (),
    allow_dirty: bool = False,
) -> SafetyCheckResult:
    """Run all local checks required before a branch/PR write operation."""
    return combine_results(
        check_dirty_worktree(repo_root, allow_dirty=allow_dirty),
        check_branch_name(branch, require_pi_prefix=True),
        check_base_branch(base_branch),
        check_paths(paths),
        check_secret_text(*texts),
    )
