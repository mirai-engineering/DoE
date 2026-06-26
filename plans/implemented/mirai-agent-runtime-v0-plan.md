# Mirai Agent Runtime v0 Plan

## Context

Build the `Data Scientist` tab described in `mirai-harness/MIRAI_AGENT_RUNTIME_V0_TASK.md` as a small, isolated, read-only vertical slice. The assistant must answer questions about the active project's uploaded data, preprocessing, and trained models while preserving the non-negotiable tenant isolation invariant: scope comes only from authenticated backend context plus the selected project route, never from LLM-supplied IDs, paths, SQL, object keys, or frontend metadata. Add deterministic, pre-LLM and post-LLM guards so sensitive scope/path/storage values are stripped or replaced before they can reach prompts, tool outputs, activity events, logs, or final assistant text.

Initial repository findings:

- Backend is FastAPI in `backend/app/main.py`, with Pydantic schemas in `backend/app/schemas.py` and service modules under `backend/app/services/`.
- Auth middleware resolves Clerk user membership to one server-side `workspace_id` via `resolve_workspace_membership()` in `backend/app/services/control_plane.py`; project routes are checked through `_request_can_access_project()`.
- Current data sources to reuse are ingestion/session inventory (`data_intake.py`), project schema/contract (`project_registry.py`), preprocessing EDA/status (`preprocessing_review.py`), model quality/MLflow summaries (`model_quality.py`, `mlflow_registry.py`), and workspace/object path guards (`workspace_storage.py`).
- Frontend tab registration is centralized in `frontend/src/types/doe.ts`; rendering is switched in `frontend/src/App.tsx`; shared header/tab UI is `ProjectHeader.tsx` and `Tabs.tsx`.
- No in-product LLM/Anthropic integration exists today; `backend/pyproject.toml` currently has no `anthropic` dependency.
- Pi/Attractor references support an explicit session loop with session history, typed tool registry, event emission, abort/limits, output truncation, and loop detection. For Mirai v0, do not copy subagents, MCP, generic shell/filesystem execution, or a broad framework.

## Agent and skill mapping

Configured/local agents and skills to use during implementation and review:

- **Pi subagent `scout`**: read-only discovery before coding each stage, per `AGENTS.md`; use it to re-check auth/workspace resolution, lifecycle artifacts, and UI registration surfaces before edits.
- **Pi subagent `worker`**: focused implementation of the isolated backend/frontend slice after the scout pass.
- **Pi subagent `reviewer`**: security/code review focused on tenant isolation, unsafe tool arguments, and frontend hidden-reasoning leakage.
- **Skill `security-and-hardening`** (`~/.pi/agent/skills/security-and-hardening/SKILL.md`): threat model, server-side scope binding, injection rejection, path/object-key/raw-SQL hardening, and tests.
- **Skill `api-and-interface-design`** (`~/.pi/agent/skills/api-and-interface-design/SKILL.md`): request/response contracts, typed tool schemas, stop reasons, event trace shape.
- **Skill `test-driven-development`** (`~/.pi/agent/skills/test-driven-development/SKILL.md`): write focused tenant-isolation and unsafe-argument tests before/with implementation.
- **Skill `frontend-ui-engineering`** (`~/.pi/agent/skills/frontend-ui-engineering/SKILL.md`): polished but small Data Scientist tab using existing Tailwind/card patterns.
- **Skill `documentation-and-adrs`** (`~/.pi/agent/skills/documentation-and-adrs/SKILL.md`): create the two required docs and record v0 non-goals/assumptions.
- **Skill `querying-mlflow-metrics`** (`.pi/skills/querying-mlflow-metrics/SKILL.md`): only if validating MLflow metric access or future trace/cost reporting needs; do not use it to broaden v0.
- **Clerk skills** (`.pi/skills/clerk-backend-api`, `.pi/skills/clerk-testing`, `.pi/skills/clerk-react-patterns`): apply only if auth-specific tests or frontend auth behavior need extra validation; avoid Clerk write operations.

Product-side agent/skills mapping for v0:

- **In-product agent**: one `data_scientist` agent loop, not a multi-agent system.
- **Agent skills/tools**: narrow read-only tools grouped conceptually as `dataset_contract`, `artifact_inventory`, `table_profile`, `preprocessing_status`, `training_summary`, and `model_quality`. These are server-side tool registry entries, not separate autonomous agents.

## Approach

Implement a POST endpoint under the project route, for example `POST /projects/{project_id}/data-scientist/messages`, that accepts a user question and optional client conversation history. The endpoint will:

1. Resolve `workspace_id` from `request.state.principal` using existing helpers.
2. Confirm `project_id` is accessible through existing project filtering.
3. Build an immutable `AgentScope(workspace_id, project_id, user_id)` server-side.
4. Run a bounded explicit loop using a small Anthropic provider adapter when configured, or return a clear configuration error if no provider key/model is available.
5. Expose only sanitized assistant text plus safe activity events; never expose hidden reasoning, raw provider reasoning, filesystem paths, object keys, or arbitrary SQL.

The loop will use typed Pydantic tool argument schemas with `extra="forbid"` and reject/ignore any model arguments that try to supply scope IDs, paths, object keys, raw SQL, or oversized limits. Tool implementations will derive all data paths and queries from `AgentScope` and existing services. Every tool result and final response must pass through deterministic sanitization before serialization, e.g. a feature-local `sanitize_agent_payload(value, scope)` / `redact_sensitive_text(text, scope)` layer that removes exact `workspace_id`, `clerk_user_id`, absolute paths, object-store URIs/keys, and known storage prefixes, replacing them with stable labels such as `[workspace]`, `[user]`, `[storage-uri]`, and `[path]`.

Prefer synchronous request/response for v0 to keep the slice small. The frontend can use `AbortController` to cancel the HTTP request. Persisting long-lived agent sessions can be intentionally stubbed/in-memory in v0; persisted storage can be a roadmap item.

## Files to modify

New backend files:

- `backend/app/services/data_scientist/__init__.py`
- `backend/app/services/data_scientist/scope.py` — immutable server-side scope and authorization helpers.
- `backend/app/services/data_scientist/schemas.py` — request/response, event, stop reason, tool schemas.
- `backend/app/services/data_scientist/tools.py` — narrow read-only tool registry and implementations.
- `backend/app/services/data_scientist/sanitization.py` — deterministic recursive payload/text redaction for workspace IDs, Clerk IDs, paths, object-store URIs/keys, storage prefixes, and other sensitive scope values before prompts/events/responses/logs.
- `backend/app/services/data_scientist/agent_loop.py` — explicit loop, limits, event emission, truncation, loop detection.
- `backend/app/services/data_scientist/provider.py` — server-side Anthropic configuration/client adapter.
- `backend/tests/test_data_scientist_isolation.py` — tenant isolation and malicious tool argument tests.

Existing backend files to touch:

- `backend/app/main.py` — import schemas/service and register the isolated `/projects/{project_id}/data-scientist/messages` endpoint.
- `backend/app/schemas.py` — only if shared response/request schemas are preferred over feature-local schemas; otherwise leave unchanged.
- `backend/pyproject.toml` / `backend/uv.lock` — add `anthropic` only if the implementation uses the official SDK; otherwise use an existing/stdlib HTTP path and avoid dependency changes.

New frontend files:

- `frontend/src/components/DataScientistPage.tsx` — tab UI, starter questions, chat, activity timeline, cancel/error/limit states.

Existing frontend files to touch:

- `frontend/src/types/doe.ts` — add `{ id: 'data-scientist', label: 'Data Scientist' }` to `tabs` (exact tab-registration surface).
- `frontend/src/App.tsx` — import/render `DataScientistPage` for the new active tab.
- `frontend/src/lib/api.ts` — add request/response types and `askDataScientist(projectId, payload, signal?)` helper.

Docs to add:

- `docs/mirai-agent-runtime-v0.md`
- `docs/mirai-harness-evals.md`

## Reuse

- `backend/app/auth.py`: `request_principal()`, `principal_workspace_id()` via main helpers.
- `backend/app/main.py`: `_raise_if_no_workspace_access()`, `_request_can_access_project()`, `_authorized_workspace_id()`, `_request_user_id()`, `_raise_api_error()` patterns.
- `backend/app/services/control_plane.py`: `get_project_runtime_state()`, workspace membership/project lookup, audit logging.
- `backend/app/services/data_intake.py`: `list_ingestion_sessions()`, `get_ingestion_session()`, `get_file_inventory()`, `session_workspace()`, status readers.
- `backend/app/services/project_registry.py`: `get_project_schema()`, `list_projects()`.
- `backend/app/services/preprocessing_review.py`: `get_preprocessing_status()`, `get_preprocessing_eda_summary()`, preprocessing report/status structures.
- `backend/app/services/model_quality.py`: `get_metrics()`, `get_artifact_summary()`, `get_latest_runs()`, `get_preprocessing_report()`, `get_active_model_metadata()`.
- `backend/app/services/workspace_storage.py`: path/object-key validation and workspace scoping helpers; do not let model tools call these with arbitrary inputs except as validation guards.
- `ml_lifecycle/ingesting/generic_tabular_doe/contract.py`: canonical contract/schema semantics.
- `frontend/src/components/ui.tsx`, existing page components: card, alert, metadata, and Tailwind design patterns.

## Security assumptions

- `CLERK_AUTH_REQUIRED=true` in production; unauthenticated/local development may return `workspace_id=None`, but tests must cover auth-enabled tenant isolation.
- A user has at most one active workspace until workspace-selection UX exists; existing middleware returns `workspace_selection_required` otherwise.
- Project route `project_id` is the only client-provided scope hint; it must be authorized server-side before the agent runs.
- The LLM may be malicious/confused. Every tool must enforce scope independently and reject IDs/paths/object keys/raw SQL-like inputs even if the model produces them.
- Sensitive values must be deterministically redacted, not left to prompt instructions: before provider calls, after each tool call, before event serialization, before API responses, and before structured logs. Redaction should use exact known values from `AgentScope`, storage configs, and returned artifacts plus conservative regexes for absolute paths, `s3://...`, `file://...`, and `workspaces/<id>/...` keys.
- v0 may summarize from existing files and artifacts, but must avoid exposing raw filesystem paths/object-store keys in events or final answers.

## Real vs intentionally stubbed in v0

Real in v0:

- Authenticated tenant-scoped backend endpoint.
- Explicit bounded agent loop with stop reasons, event trace, tool registry, typed validation, truncation, and loop detection.
- Read-only tools for available contract/schema, uploaded artifacts, table/column profiles where safe local canonical artifacts exist, preprocessing status, training runs, model metrics, and feature/model summaries.
- Frontend Data Scientist tab with context indicator, starter questions, chat-style messages, activity timeline, cancel, errors, and stop-limit display.
- Focused tenant-isolation and tool-injection tests.
- Required architecture/eval docs.

Stubbed/limited in v0:

- No multi-agent system, subagents, MCP server, vector database, arbitrary execution environment, shell, raw SQL, write/delete/train/deploy actions.
- Session persistence can be request-scoped/in-memory; durable per-user agent sessions are a later phase.
- Streaming can be deferred; request/response plus visible loading/cancel is acceptable for v0.
- `run_safe_aggregate` can support only a tiny allowlisted spec over known tables/columns, or be deferred if safe implementation would exceed the slice.
- Provider absence should produce a configuration-safe error; no frontend secrets and no committed keys.

## Steps

- [x] Run a fresh scout pass over auth, data lifecycle artifacts, UI tabs, and tests before implementation.
- [x] Define feature-local Pydantic schemas: request, response, event trace item, stop reasons, message history, and per-tool arguments with `extra="forbid"`.
- [x] Implement `AgentScope` and a single authorization entrypoint that binds `workspace_id` from the authenticated request and verifies `project_id` access before any tool runs.
- [x] Implement read-only data tools using existing services, with independent scope checks, bounded limits, output sanitization, and no raw path/object-key/SQL acceptance.
- [x] Implement deterministic sanitization tests and guards: exact `workspace_id`, `clerk_user_id`, absolute paths, `s3://` URIs, `file://` URIs, object keys, and storage prefixes must be redacted from tool outputs, prompts/events/responses, and agent logs.
- [x] Implement the explicit loop: provider call, tool-call dispatch, max turns/tool calls, repeated-call detection, truncation, timeout/error handling, cancellation-aware checks, usage metadata when available, and stop reasons.
- [x] Add the FastAPI route in `main.py` with minimal imports and no behavior changes to existing routes.
- [x] Add tenant-isolation/security tests proving Workspace A cannot access Workspace B session metadata, artifact inventory, schema/table samples, preprocessing status, or model metadata, including malicious tool argument injection and attempts to force the assistant to reveal raw workspace IDs, storage paths, object keys, or Clerk user IDs.
- [x] Add frontend API types/helper.
- [x] Add `DataScientistPage` and register/render the `Data Scientist` tab in the exact existing tab surfaces.
- [x] Add required docs: architecture/threat model/tool contracts/loop model and harness eval methodology.
- [x] Run focused backend tests, then frontend typecheck/build, and fix only issues in the new slice.
- [x] Run reviewer pass with `security-and-hardening` before final report.

## Verification

Backend:

- `cd backend && uv run pytest tests/test_data_scientist_isolation.py`
- `cd backend && uv run pytest tests/test_workspace_storage.py tests/test_runtime_project_schema.py tests/test_training_mlflow_contract.py`
- If provider code is added, include a mocked-provider unit test so tests never require or print real Anthropic keys.
- Add explicit sanitization assertions: no response/event/log fixture contains raw workspace IDs, Clerk IDs, absolute paths, `s3://`, `file://`, or `workspaces/<id>/...` object keys.

Frontend:

- `cd frontend && npm run build`
- Optionally `cd frontend && npm run lint` if existing lint baseline is clean.

Manual checks:

- Open app, select a project, open `Data Scientist` tab.
- Verify empty state when no project/schema is active.
- Ask starter questions about uploaded data, preprocessing, and model quality.
- Confirm timeline shows safe actions only, no hidden reasoning, no filesystem paths, no object-store keys.
- Cancel an in-flight request and verify UI stop/cancel state.
- Attempt prompt injection asking for another workspace/project/session and verify denial or scoped answer only.
