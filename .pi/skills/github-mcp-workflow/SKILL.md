---
name: github-mcp-workflow
description: Use when the user asks to create, inspect, compare, or publish GitHub branches, pull requests, issues, releases, remote GitHub compares, or explicitly asks to use GitHub MCP in this repo.
---

# GitHub MCP Workflow

Use this skill only for explicit GitHub-side workflows in this repo. Do not use GitHub MCP for normal coding, local file reading, planning, refactoring, testing, debugging, documentation, or explanations.

## Mental model

The approved architecture is:

```text
Pi skill instructions
  -> repo-local CLI wrapper
  -> short-lived GitHub MCP connection
  -> GitHub API
```

Use the wrapper. Do not register or call raw GitHub MCP directly unless the user explicitly asks to bypass the wrapper and accepts the risks.

## Wrapper location

Run commands from `backend/`:

```bash
uv run --group agent mirai-github-mcp <command>
```

Implementation and docs:

- `backend/agent_tools/github_mcp/`
- `backend/agent_tools/github_mcp/README.md`
- `docs/agent-plans/to-implement/pi-github-mcp-safe-workflow.md`

## Environment

The wrapper expects these variables to be exported in the shell:

```bash
GITHUB_TOKEN
GITHUB_OWNER
GITHUB_REPO
```

For this repo, the GitHub remote is currently:

```text
mirai-engineering/DoE
```

If the user stores these in `.env.local`, remind them to load it before running commands:

```bash
set -a
source .env.local
set +a
```

Never print token values. Never commit credentials.

## Allowed commands

Use only these wrapper commands unless a future approved plan expands the allowlist:

```bash
uv run --group agent mirai-github-mcp preflight
uv run --group agent mirai-github-mcp list-own-prs
uv run --group agent mirai-github-mcp create-branch --branch pi/<task-slug>
uv run --group agent mirai-github-mcp compare --head pi/<task-slug>
uv run --group agent mirai-github-mcp create-draft-pr --head pi/<task-slug> --title "..."
```

## Dry-run first

Dry-run is the default. Start with dry-run for every branch or PR operation.

Examples:

```bash
cd backend
uv run --group agent mirai-github-mcp preflight --allow-dirty
uv run --group agent mirai-github-mcp create-branch --branch pi/<task-slug> --allow-dirty
uv run --group agent mirai-github-mcp create-draft-pr --head pi/<task-slug> --title "<title>" --allow-dirty
```

For read-only live GitHub checks, `--apply` is required to contact MCP:

```bash
cd backend
uv run --group agent mirai-github-mcp list-own-prs --apply
```

## Required approval for writes

Before any write action:

1. Run dry-run preflight.
2. Summarize the exact intended action.
3. Summarize branch name, base branch, PR title/body, and affected paths.
4. Ask the user for explicit approval.
5. Only then use `--apply --yes`.

Write examples after explicit approval:

```bash
cd backend
uv run --group agent mirai-github-mcp create-branch \
  --branch pi/<task-slug> \
  --apply --yes

uv run --group agent mirai-github-mcp create-draft-pr \
  --head pi/<task-slug> \
  --title "<title>" \
  --body "<summary, tests, risks>" \
  --apply --yes
```

## Branch and PR rules

- Pi-created branches must use `pi/<task-slug>`.
- Draft PRs are the default.
- PR bodies should include:
  - Summary
  - Changed files
  - Tests run
  - Safety checks
  - Known risks / follow-ups
- Do not include tokens, credentials, private URLs, or raw environment dumps.

## Protected paths and content

Refuse automated GitHub writes involving:

- `data/`
- `backend/mlruns/`
- `backend/data-minio/`
- `legacy/`
- `.env*`
- `*.pem`, `*.key`, `*.p12`, `*.pfx`
- secret-like values in titles, bodies, diffs, or command arguments

## Never do through this wrapper

Refuse or ask for a separate approved plan before:

- force-pushing;
- deleting branches;
- merging PRs;
- marking draft PRs as ready;
- modifying GitHub secrets;
- modifying GitHub Actions/workflows;
- changing branch protection;
- performing admin operations.

## If using Git CLI instead

Git CLI is acceptable for local Git operations when requested, but still follow the same safety policy:

- inspect `git status --short` first;
- avoid broad `git add .`;
- never force-push without explicit interactive approval;
- do not stage protected/generated/secret files;
- use `pi/<task-slug>` branches for Pi-created branches.

Prefer the wrapper for GitHub-side PR creation and remote comparison because it gives dry-run output and repo-specific guardrails.
