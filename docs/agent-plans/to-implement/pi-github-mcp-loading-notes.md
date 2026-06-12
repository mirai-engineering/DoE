# Pi GitHub MCP Loading Notes

## Confirmed mechanisms

This repo and local Pi install currently show these relevant mechanisms:

- Global Pi settings: `/Users/brunocopa/.pi/agent/settings.json`
  - Contains the always-loaded `packages` array.
  - Current global packages are Plannotator, web access, subagents, and powerline footer.
- Project Pi settings: `.pi/settings.json`
  - Currently only sets the project theme.
  - Can be used for project-scoped subagent overrides/packages where needed.
- Project-scoped instructions and skills: `.pi/` and root `AGENTS.md`.
- Subagent MCP direct tools: `pi-subagents` supports `mcp:` tool entries when `pi-mcp-adapter` is installed.
  - Docs found in `/Users/brunocopa/.pi/agent/npm/node_modules/pi-subagents/README.md`.
  - It reads MCP config from global/project MCP config paths such as `~/.pi/agent/mcp.json`, `.mcp.json`, or `.pi/mcp.json`.
  - Direct MCP tools require adapter metadata/cache and are therefore not ideal for a safety-first, short-lived GitHub MCP rollout.

## Decision for this plan

Do **not** register GitHub MCP as a global always-loaded Pi package or always-on MCP server.

Use a project-local Python CLI wrapper instead:

- Pi invokes `mirai-github-mcp` only for explicit GitHub/branch/PR workflows.
- The Python wrapper starts/connects to GitHub MCP only for a single operation and then closes.
- Normal Pi sessions, local coding, planning, testing, and explanations do not load GitHub MCP tool metadata into context.

This provides on-demand behavior even if Pi's native MCP configuration is eager/cached at startup.
