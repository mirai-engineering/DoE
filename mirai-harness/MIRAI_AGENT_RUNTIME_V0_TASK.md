# Task: Build Mirai Agent Runtime v0 as an Isolated “Data Scientist” Tab

## Objective

Implement the first safe, production-minded vertical slice of **Mirai Agent Runtime** as a new **Data Scientist** tab in the existing application.

The tab should let an authenticated user ask read-only questions about the currently active project’s uploaded experimental data, preprocessing, and trained models. It should feel like a trustworthy industrial data-science assistant, not a generic chat interface.

Examples of intended questions:

- What data has been uploaded for this project?
- Which tables, columns, targets, and input features are available?
- Are there missing values, duplicates, suspicious ranges, or inconsistent units?
- What does the preprocessing pipeline do?
- Which model is currently champion and how did it perform?
- Where is the model likely unreliable or extrapolating?

---

## Reference Implementations to Study First

Before designing the implementation, inspect the following references and extract only the ideas that fit Mirai’s constraints. Do not copy either project wholesale and do not introduce their architecture as a dependency unless it is clearly necessary.

### 1. Local Pi installation — MVP inspiration

Pi is installed locally and is the preferred reference for a lightweight, explicit harness.

Study Pi’s actual local installation/source and relevant documentation for ideas around:

- explicit session and message history;
- tool registry and typed tool calls;
- event emission for terminal/UI rendering;
- abort/cancellation support;
- context management and compaction;
- prompt/project-instruction discovery;
- model/provider configuration;
- extension/skill boundaries;
- simple, inspectable loops rather than opaque orchestration.

Use Pi as inspiration for keeping the MVP small, observable, and hackable.

### 2. Attractor coding-agent loop specification — architectural inspiration

Read: `https://github.com/strongdm/attractor/blob/main/coding-agent-loop-spec.md`

Use it as a language-agnostic reference for the architecture of an explicit agent loop, especially:

- a session as the central orchestrator;
- session history, configuration, lifecycle state, stop conditions, and event emission;
- a bounded loop that alternates between model calls and tool execution;
- typed lifecycle events suitable for a UI;
- tool output truncation and context limits;
- cancellation, timeouts, loop detection, and limits;
- provider-aware configurations;
- an execution/tool boundary that keeps host control outside the LLM.

For this Mirai v0, do **not** add subagents, an MCP server, a generic execution environment, or a multi-agent framework unless the repository already has a clear and justified need.

---

## Non-Negotiable Security Invariant

The agent must never access another workspace’s, project’s, dataset’s, or session’s data.

The LLM must never choose, infer, or override:

- `workspace_id`
- `project_id`
- `dataset_id`
- `session_id`
- filesystem paths
- object-store keys
- arbitrary SQL queries

The authenticated backend context and currently active UI project must determine scope server-side. Every data tool must enforce that scope internally, even when model-generated tool arguments attempt to inject another ID, path, object key, or raw SQL-like query.

Do not rely on prompt instructions, client-provided IDs, frontend state, embeddings, or RAG metadata as authorization controls.

---

## Change-Scope Constraint

Build this as a new, isolated vertical slice.

- Add one new app tab named **Data Scientist**.
- Keep current intake, preprocessing, training, recommendation, storage, routing, and deployment behavior unchanged.
- Touch existing frontend files only where strictly necessary to register and render the new tab.
- Put all new backend and frontend feature logic in isolated new modules/files where possible.
- Do not perform broad refactors.
- Do not add write, delete, deployment, training, retraining, arbitrary shell, arbitrary filesystem, arbitrary object-storage, or arbitrary SQL capabilities.

The goal is a minimal safe MVP that can evolve, not a generic agent platform.

---

## Backend v0 Requirements

Implement a small read-only tenant-scoped agent endpoint and supporting service layer. 

### Agent Tool Design

The agent may use a small set of narrow tools with typed JSON inputs. Proposed capabilities include:

```text
get_dataset_contract()
list_uploaded_artifacts()
describe_table(table_name)
sample_rows(table_name, limit)
profile_column(table_name, column)
run_safe_aggregate(query_spec)
get_preprocessing_status()
get_training_run_summary()
get_model_metrics()
get_feature_importance()
```

Adapt names to repository conventions, but preserve these rules:

- Tool input schemas must be typed and validated.
- The server must bind workspace/project/dataset/session scope from authenticated backend context.
- Tools must not accept scope overrides from the model.
- Reject or ignore injected workspace/project/dataset/session IDs, filesystem paths, object keys, raw SQL, and shell-like input.
- Bound row samples, aggregation complexity, output size, execution time, and total tool calls.
- Prefer structured data sources: manifest, data dictionary, artifact inventory, persisted EDA summaries, bounded DuckDB/Polars queries, and MLflow/model metadata.
- Do not introduce a vector database for this v0 unless existing repository evidence proves it is immediately necessary.
- Do not introduce MCP or a multi-agent system for this v0.

### Anthropic / Opus

The repository has a folder-local `.env.local` containing an Anthropic API key. Use that configuration safely only if it fits the existing architecture.

- Never commit secrets.
- Never print API keys or environment values.
- Never add secrets to frontend code.
- Keep model/provider configuration server-side.
- Prefer `claude-opus-4-8` for the first implementation if the configured SDK/provider supports it.
- Make the provider/model configurable through safe server-side configuration rather than hardcoding it across the app.

### Explicit Agent Loop

Implement a small explicit loop inspired by Pi and Attractor, rather than hiding all behavior in a high-level SDK call.

It should include:

- session/message history;
- a small tool registry;
- max turns;
- max tool calls or tool rounds;
- tool output truncation;
- bounded tool execution time;
- cancellation support where practical;
- basic repeated-call / loop detection;
- usage/cost metadata when available;
- clear stop reasons.

Supported stop reasons should include:

```text
completed
max_turns_reached
max_tool_calls_reached
cancelled_by_user
authorization_denied
tool_error
loop_detected
context_limit
```

### Activity Trace

Return or persist a sanitized event trace suitable for a UI activity timeline.

Do **not** expose hidden chain-of-thought or provider reasoning.

Safe event examples:

```text
Loaded dataset contract
Inspected model-table schema
Profiled operating_voltage
Retrieved champion-model metrics
Prepared answer
```

Each event should contain only safe metadata such as:

- event type;
- tool/action name;
- concise user-safe summary;
- step number;
- duration;
- success/error outcome;
- stop reason where relevant.

---

## Frontend v0 Requirements

Create a polished but simple **Data Scientist** tab using the existing design system.

It should include:

- a clear current project/dataset context indicator;
- an empty state when no active project/dataset/session is available;
- suggested starter questions;
- chat-style user questions and assistant answers;
- a compact visible activity timeline while the agent works;
- clear loading, cancellation, error, and stop-limit states;
- no hidden-reasoning display;
- no behavioral changes to existing tabs.

The user should understand what the assistant inspected without seeing private reasoning.

---

## Tests: Tenant Isolation Is Mandatory

Add focused tests proving that an authenticated request in Workspace A cannot retrieve Workspace B’s data.

At minimum, test that Workspace A cannot obtain Workspace B’s:

- session metadata;
- uploaded artifact inventory;
- table schema/data samples;
- preprocessing status;
- training/model metadata.

Also test model/tool argument injection attempts involving:

- another workspace/project/dataset/session ID;
- a filesystem path;
- an object-storage key;
- raw SQL-style input;
- unsafe aggregation or oversized sample requests.

The authorization test should pass even if the model attempts malicious or confused tool arguments.

---

## Documentation Deliverables

Create:

1. `docs/mirai-agent-runtime-v0.md`
   - architecture;
   - threat model;
   - server-side scope-binding rules;
   - tool contracts;
   - agent-loop/session/event model;
   - stop conditions;
   - UI behavior;
   - explicit non-goals;
   - phased roadmap.

2. `docs/mirai-harness-evals.md`
   - realistic Mirai coding and data-agent tasks;
   - scoring rubric;
   - tenant-isolation regression fixtures;
   - cost/token/tool-round/trace reporting;
   - methodology for comparing Pi configurations and future harness changes;
   - a clear distinction between evaluating the coding harness and evaluating the in-product Data Scientist agent.

---

## Required Process

1. Inspect the repository, including auth/workspace resolution, data intake/session storage, Postgres control-plane models, object storage, preprocessing/training lifecycle, current frontend navigation, tests, and `AGENTS.md`.
2. Inspect local Pi for relevant implementation patterns and read the Attractor loop specification.
3. Before coding, write a concise implementation plan that lists:
   - new files;
   - unavoidable existing files to touch;
   - exact tab-registration surface;
   - security assumptions;
   - tests to add;
   - which parts are real versus intentionally stubbed in v0.
4. Make the smallest coherent additive change set.
5. Run relevant backend tests, frontend type checks/build, and focused security tests after each substantial stage.
6. Finish with a report containing:
   - changed files;
   - commands run;
   - test results;
   - architecture decisions;
   - unresolved decisions;
   - explicit security assumptions;
   - known v0 limitations.

---

## Guardrails

- Do not weaken existing authentication or authorization.
- Do not modify deployment infrastructure.
- Do not alter current intake, preprocessing, training, recommendation, or storage behavior.
- Do not add a vector database, MCP server, or multi-agent framework unless strictly required by existing repository code.
- Do not expose hidden reasoning in the UI.
- Do not commit or reveal API keys.
- Do not make broad architectural refactors.
- Prefer a thin, safe, testable vertical slice over speculative completeness.
