# Project Pi Instructions

## On-Demand GitHub MCP

For explicit GitHub-side workflows, use the repo-local `github-mcp-workflow` skill in `.pi/skills/github-mcp-workflow/SKILL.md`.

Trigger it only when the user asks to create, inspect, compare, or publish GitHub branches, pull requests, issues, releases, remote GitHub compares, or explicitly asks to use GitHub MCP.

Do **not** start GitHub MCP for normal coding, local file reading, planning, refactoring, testing, debugging, documentation, or explanations.

Keep GitHub MCP out of always-loaded global Pi packages. Use the project-local wrapper from `backend/`:

```bash
uv run --group agent mirai-github-mcp <command>
```

Writes require a dry-run summary, explicit user approval, and `--apply --yes`.
