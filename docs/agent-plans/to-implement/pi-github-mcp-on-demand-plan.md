# On-Demand GitHub MCP Integration for Pi

## Context

The goal is to optimize Pi usage for this repo without breaking existing work: reduce unnecessary context/token load, manage skills and packages more deliberately, and allow Pi to perform safe GitHub workflows such as creating branches and draft PRs.

The proposed integration should use the official Python MCP SDK (`modelcontextprotocol/python-sdk`) to connect to GitHub's MCP server (`github/github-mcp-server`). The GitHub MCP capability must **not** be loaded into Pi context all the time. It should activate only when a user explicitly asks for GitHub/PR/branch work.

Scout findings:

- Current Pi global config is in `/Users/brunocopa/.pi/agent/settings.json`.
- Current always-loaded packages are Plannotator, web access, subagents, and powerline footer.
- This repo has a backend/frontend split and existing backend Python tooling managed with `uv`.
- Heavy or sensitive local artifacts such as data directories, ML run artifacts, `.env*`, and secrets must be protected from automated GitHub operations.
- Pi’s exact MCP loading mechanism should be confirmed before registering any always-on server.

## Approach

Implement GitHub MCP as a **project-scoped, on-demand Python tooling wrapper**, not as an always-loaded global Pi package.

The wrapper should:

1. Use the Python MCP SDK from an isolated agent/tooling dependency group.
2. Start or connect to GitHub MCP only inside a short-lived operation.
3. Allowlist safe GitHub actions only: inspect repository, create branch, compare branch, create draft PR, and list own PRs.
4. Default to dry-run mode.
5. Require explicit `--apply` plus user confirmation for write actions.
6. Reject destructive operations, protected paths, unsafe branch names, dirty worktrees unless explicitly approved, and PR bodies that appear to contain secrets.

`context-mode` should be evaluated, but not blindly enabled. If it can reduce irrelevant context without hiding critical repo instructions, add it after a short validation pass. If it cannot be scoped safely, leave it out.

For selective loading, do **not** register GitHub MCP in `/Users/brunocopa/.pi/agent/settings.json` as an always-loaded package/server. Instead, document activation rules for Pi: only invoke the on-demand CLI when the user asks for PRs, branches, GitHub issues, releases, or an explicit GitHub workflow trigger.

## Files to modify

- `backend/pyproject.toml` — add an agent/dev dependency group for the Python MCP SDK and a CLI entrypoint.
- `/Users/brunocopa/.pi/agent/settings.json` — optionally add `npm:context-mode` only after evaluation; do **not** add GitHub MCP as always-loaded global context.
- `.pi/AGENTS.md` or `.pi/github-mcp-usage.md` — project-scoped activation and safety rules for Pi.
- `docs/agent-plans/to-implement/pi-github-mcp-safe-workflow.md` — safe human-readable GitHub workflow recipe.

## New files

- `backend/agent_tools/__init__.py`
- `backend/agent_tools/github_mcp/__init__.py`
- `backend/agent_tools/github_mcp/contracts.py`
- `backend/agent_tools/github_mcp/safety.py`
- `backend/agent_tools/github_mcp/client.py`
- `backend/agent_tools/github_mcp/server_config.py`
- `backend/agent_tools/github_mcp/cli.py`
- `backend/agent_tools/github_mcp/README.md`
- `backend/tests/test_github_mcp_safety.py`
- `backend/tests/test_github_mcp_cli.py`
- `.pi/AGENTS.md` or `.pi/github-mcp-usage.md`
- `docs/agent-plans/to-implement/pi-github-mcp-safe-workflow.md`

## Reuse

- `/Users/brunocopa/.pi/agent/settings.json` — existing Pi package and subagent configuration pattern.
- `backend/pyproject.toml` and `uv` workflow — reuse backend Python dependency management instead of introducing a separate package manager.
- Existing repo `.gitignore` conventions — rely on ignored `.env`/artifact patterns and reinforce them in safety checks.
- Existing subagent workflow (`scout`, `planner`, `worker`, `reviewer`) — use Scout/Planner for context and Worker only after this plan is approved.

## Steps

- [ ] Confirm Pi’s supported MCP/server loading mechanisms: global settings, project settings, package manifest, extension, or command wrapper.
- [ ] Keep GitHub MCP out of the global always-loaded Pi packages in `/Users/brunocopa/.pi/agent/settings.json`.
- [ ] Add an isolated backend agent tooling area under `backend/agent_tools/github_mcp/`.
- [ ] Add the Python MCP SDK to an agent-only `uv` dependency group, not production backend dependencies.
- [ ] Define typed contracts for allowed GitHub operations: inspect repo, create branch, compare branch, create draft PR, list own PRs.
- [ ] Implement safety checks for dirty worktree, protected paths, secret-like content, branch naming, base branch protection, and destructive operation rejection.
- [ ] Implement a short-lived Python MCP client wrapper that starts/connects to GitHub MCP only for one operation and then closes.
- [ ] Add environment-driven GitHub MCP server configuration using `GITHUB_TOKEN`, `GITHUB_OWNER`, and `GITHUB_REPO`; never commit credentials.
- [ ] Add a narrow CLI such as `mirai-github-mcp` with commands like `preflight`, `create-branch`, `compare`, and `create-draft-pr`.
- [ ] Make dry-run the default; require `--apply` and user confirmation for writes.
- [ ] Add offline tests for contracts, guardrails, dry-run behavior, allowlisted tools, and missing environment variables.
- [ ] Evaluate `context-mode` with before/after context checks; add it only if critical repo instructions still load and artifact noise is reduced.
- [ ] Add project-scoped Pi instructions that GitHub MCP activates only for explicit GitHub/branch/PR workflows.
- [ ] Add a safe PR workflow recipe for future Pi runs.
- [ ] Validate that normal backend tests and Docker/runtime behavior are unchanged.

## Context-mode decision

Recommendation: **trial it, then decide**.

`context-mode` appears relevant because this repo can accumulate large or noisy context from artifacts, data, ML runs, lockfiles, and generated outputs. However, it should not be enabled if it hides important project instructions or active source files.

Acceptance criteria for adding it:

- Pi still sees `AGENTS.md` and project-specific instructions.
- Active source files remain discoverable.
- Heavy artifacts such as `backend/mlruns/`, `backend/data-minio/`, root `/data/`, generated outputs, and irrelevant lockfile noise are not pulled into ordinary context.
- A before/after check shows lower irrelevant context usage in normal coding/planning tasks.

If these criteria are not met, do not add `context-mode` globally.

## How Pi loads GitHub MCP only when needed

Use an on-demand command wrapper instead of an always-on MCP registration.

Activation rule for Pi:

- Use GitHub MCP only when the user explicitly asks for a PR, pull request, branch, GitHub issue, release, remote compare, or an explicit workflow trigger such as `git+:` or `prd:`.
- Do not use GitHub MCP for normal coding, planning, local file reads, tests, refactors, or explanations.
- Before any write action, run preflight and summarize what will happen.
- Require explicit user approval before running any command with `--apply`.
- Never expose raw GitHub MCP tool listings or large remote payloads to context unless needed for the requested operation.

This keeps MCP context and tool metadata out of ordinary Pi sessions while still allowing safe, scoped GitHub automation.

## Verification

- [ ] `cd backend && uv sync --group agent` installs the Python MCP SDK without affecting production dependencies.
- [ ] `cd backend && uv run --group agent mirai-github-mcp preflight` works in dry-run mode.
- [ ] Write actions fail unless `--apply` is present.
- [ ] Offline tests pass: `cd backend && uv run --group agent pytest tests/test_github_mcp_safety.py tests/test_github_mcp_cli.py`.
- [ ] Normal backend tests still pass: `cd backend && uv run pytest`.
- [ ] No Docker production files are changed unless explicitly approved.
- [ ] Starting Pi does not automatically start GitHub MCP.
- [ ] A manual smoke test can create a draft PR in a test branch only after explicit user approval.

## Risks and guardrails

- Pi may not support true lazy MCP loading via settings alone; the CLI wrapper avoids that dependency.
- GitHub MCP may expose destructive tools; the wrapper must allowlist safe tools and reject all others.
- Over-scoped GitHub tokens undermine safety; use a fine-grained token with only repository contents, pull requests, and metadata scopes.
- LLM-generated branch names, PR bodies, and file lists must be validated before use.
- Live GitHub tests can mutate state; default tests must remain offline.
- Adding the MCP SDK to production dependencies could slow deploys or change runtime behavior; keep it in an agent-only group.
