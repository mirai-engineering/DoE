# Mirai Agent Runtime v0

Mirai Agent Runtime v0 adds a read-only `Data Scientist` tab for authenticated users. The runtime answers questions about the active project's uploaded data, preprocessing, and model quality using server-side tools only.

## Architecture

- Frontend: `DataScientistPage` posts questions to `POST /projects/{project_id}/data-scientist/messages` and renders sanitized answers plus a tool activity timeline.
- Authorization: the backend builds an immutable `AgentScope` from the authenticated request and route `project_id`. The LLM and frontend cannot supply `workspace_id`, user IDs, paths, object keys, or SQL.
- Runtime loop: `agent_loop.py` runs a bounded provider/tool loop with max turns, max tool calls, repeated-call detection, truncation, timeout handling, and stop reasons.
- Provider: `app/agent_runtime/providers/anthropic_provider.py` uses Anthropic's official Python SDK server-side (`Anthropic().messages.create(...)`). The SDK reads `ANTHROPIC_API_KEY` from the backend process environment.
- Configuration: `app/agent_runtime/config.py` reads `ANTHROPIC_API_KEY`, `MIRAI_AGENT_MODEL` (default `claude-opus-4-1-20250805`), `MIRAI_AGENT_MAX_TOKENS`, `MIRAI_AGENT_PROVIDER_TIMEOUT_SECONDS`, and loop limits from environment variables.
- Tools: `tools.py` exposes narrow read-only tools for project contract, artifact inventory, table profile, preprocessing status, training summary, and model quality.
- Sanitization: `sanitization.py` recursively redacts exact workspace/user values plus absolute paths, `s3://`, `file://`, and `workspaces/...` object keys before prompts, events, responses, and logs.

## Threat model

Primary risks are tenant cross-access, prompt/tool injection, accidental storage-path disclosure, and hidden-reasoning leakage. Mitigations:

- Scope is derived only from Clerk-authenticated request state and server-side project authorization.
- Each tool performs an independent project/workspace availability check.
- Tool schemas use Pydantic `extra="forbid"` and reject scope/path/object-key/SQL-like fields.
- Tool output and final assistant text are deterministically sanitized.
- The UI displays only answers and activity events, never provider hidden reasoning.

## Tool contracts

All tools are read-only. They may accept optional dataset/session selectors where safe, but never workspace IDs, object keys, raw paths, or SQL. Limits are bounded in schema validation.

- `dataset_contract`: project inputs, outputs, constraints.
- `artifact_inventory`: uploaded file metadata, bounded and sanitized.
- `table_profile`: preprocessing EDA/table profile summary when available.
- `preprocessing_status`: latest or selected ingestion-session preprocessing status.
- `training_summary`: latest training runs and active model metadata.
- `model_quality`: quality metrics and artifact status.

## v0 limitations

No arbitrary code execution, raw SQL, filesystem browsing, writes, training/deployment actions, MCP, vector DB, or durable chat sessions are included. Streaming is deferred; v0 uses request/response with browser-side cancellation.

## Local and Railway configuration

Local development uses the repository's existing direnv flow. Put local-only values in the repo root `./.env.local` (gitignored), then run:

```bash
direnv allow
direnv reload
cd backend && uv run uvicorn app.main:app --reload
```

Required local variable:

```bash
ANTHROPIC_API_KEY=...
```

Optional variables:

```bash
MIRAI_AGENT_MODEL=claude-opus-4-1-20250805
MIRAI_AGENT_MAX_TOKENS=1000
MIRAI_AGENT_PROVIDER_TIMEOUT_SECONDS=25
```

`./mirai-harness/.env.local` is not loaded by the backend app when the backend is started from the repo/backend shell. Railway must define the same variables as service variables, not through `.env.local`.

## Smoke test

After `direnv allow` / `direnv reload`, verify presence without printing secrets:

```bash
cd backend && uv run python - <<'PY'
import os
print('ANTHROPIC_API_KEY_present=', bool(os.getenv('ANTHROPIC_API_KEY')))
print('MIRAI_AGENT_MODEL=', os.getenv('MIRAI_AGENT_MODEL', 'claude-opus-4-1-20250805'))
PY
```

Then start backend/frontend, open a project, select **Model setup → Data Scientist**, and ask: "What uploaded data is available for this project?"
