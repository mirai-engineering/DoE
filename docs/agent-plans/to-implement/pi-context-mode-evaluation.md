# Context-mode Evaluation for This Repo

## Question

Should this project add `npm:context-mode` to optimize Pi context/token usage while implementing GitHub MCP workflows?

## Findings

- `context-mode` is distributed as a Pi package/plugin.
- It can be added via Pi package settings, including global `~/.pi/agent/settings.json` or project `.pi/settings.json`.
- Because it is a package/plugin, adding it globally would make it part of Pi startup behavior rather than an operation-scoped GitHub MCP wrapper.
- This repo has real context-bloat risks: `backend/mlruns/`, `backend/data-minio/`, root `data/`, generated artifacts, lockfiles, and model artifacts.
- This repo also has critical context that must remain available: root `AGENTS.md`, `.pi/skills/`, backend/frontend source files, and active plan docs.

## Decision

Do **not** add `context-mode` globally in `/Users/brunocopa/.pi/agent/settings.json` during this implementation.

Recommended next step is a separate, explicit trial after the GitHub MCP wrapper is working:

1. Add `npm:context-mode` project-locally in `.pi/settings.json`, not globally.
2. Start a new Pi session in this repo.
3. Confirm root `AGENTS.md` and project skills still load.
4. Confirm normal code questions do not pull in `backend/mlruns/`, `backend/data-minio/`, or root `data/` noise.
5. Remove it if it hides important repo instructions or active source files.

## Why not now?

The GitHub MCP safety goal is best served by the on-demand CLI wrapper. Adding another always-loaded plugin at the same time would make it harder to prove that normal Pi startup behavior is unchanged and that GitHub MCP is not loaded unless explicitly requested.

## Acceptance result

- Critical repo instructions are unchanged.
- No new package was added to global Pi settings.
- Context-mode remains an optional project-level trial, not a dependency of the GitHub MCP wrapper.
