# Scientist Preprocessing Agent Plan

## Context

Model Quality currently contains two outdated placeholder cards for preprocessing review and a future AI preprocessing assistant. The intended product direction is to move preprocessing review artifacts into **Preprocessing Review** and create a bounded scientist-facing agent that helps explain EDA/preprocessing decisions for uploaded data.

The user is considering a repo-local Pi harness installation, guided by repo `AGENTS.md`/`SKILL.md` files, ideally using a local Ollama model such as `qwen3.6:35b-a3b-coding-nvfp4`, without interfering with their global/personal Pi installation. The agent should begin as an explanatory ML-engineer assistant, not an autonomous code-writing system. MVP scope is free-form Q&A for Mirai admin/scientists; later scope can become a global product assistant.

## Approach

Recommended direction so far:

1. Separate UI cleanup from agent capability:
   - Remove stale preprocessing/assistant placeholder cards from Model Quality.
   - Surface preprocessing artifacts, review status, and eventual assistant controls in Preprocessing Review.
2. Add an **EDA / Preprocessing Q&A agent** as a narrow, read-only assistant:
   - Reads approved ingestion/session artifacts: EDA summary, preprocessing report, schema, data profile, transformation choices, training plan/status.
   - Answers scientist questions with citations to artifacts and clear uncertainty.
   - Can propose preprocessing options for scientist review, but cannot execute transformations, write files, run scripts, or approve data in MVP.
3. Prefer a **Pi SDK-based agent service spike** over plain direct Ollama calls, because the desired value is not just LLM completion:
   - Pi contributes context/resource loading, skills, prompt templates, sessions, and tool orchestration.
   - The product assistant can use Pi SDK with a restricted toolset instead of the default coding-agent CLI behavior.
   - The first production-facing tools should be custom read-only tools such as `get_eda_summary`, `get_preprocessing_report`, `get_uploaded_file_profile`, and `get_sample_rows`, not `bash`, `edit`, or unrestricted filesystem reads.
4. Isolate Pi from the user's personal/global setup:
   - Use `PI_CODING_AGENT_DIR=agent-runtime/pi-agent` to override the default global config directory (`~/.pi/agent`).
   - Use `PI_CODING_AGENT_SESSION_DIR=agent-runtime/sessions` or SDK `SessionManager` settings for product sessions.
   - Use SDK `AuthStorage.create("agent-runtime/pi-agent/auth.json")` and `ModelRegistry.create(customAuth, "agent-runtime/pi-agent/models.json")` so custom model config is repo/product-local.
   - Avoid default CLI resource discovery for product runtime where possible; use SDK explicit `agentDir`, explicit model registry, and either custom `ResourceLoader` or a controlled `cwd`/resource set.
   - If CLI experiments are needed, run with wrapper scripts that set `PI_CODING_AGENT_DIR`, `PI_CODING_AGENT_SESSION_DIR`, `PI_OFFLINE=1`, and `PI_SKIP_VERSION_CHECK=1`.
5. Use local Ollama as the first model provider:
   - Current personal Pi model config shows `ollama/qwen3.6:35b-a3b-coding-nvfp4` at `http://127.0.0.1:11434/v1`.
   - Product-local `models.json` should copy this model entry without touching `~/.pi/agent/models.json`.
   - Future deployment target is a Mirai-hosted isolated GPU server, still exposed behind an OpenAI-compatible endpoint if possible.
6. Treat `docs/agent-plans/implemented/autoresearch-for-doe-plan.md` as conceptually related but operationally distinct:
   - Shared pattern: skills, bounded context, reproducible evidence, explicit constraints, no uncontrolled autonomy.
   - Autoresearch = autonomous optimizer/research experiments in a sandbox with metrics.
   - Scientist preprocessing agent = interactive Q&A and decision support over uploaded project artifacts.
   - The two can share skills and safety conventions, but should not share the same runtime permissions.

## Recommended MVP architecture

Use a two-layer design:

1. **FastAPI product API** remains the only frontend-facing service.
   - Endpoint shape likely: `POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing/assistant/questions`.
   - It authenticates/validates the selected session, assembles safe context, calls the agent runtime, streams answer tokens, and returns structured final answer metadata.
2. **Agent runtime/bridge** provides Pi context/skills/model orchestration.
   - Preferred spike: Node/TypeScript Pi SDK bridge with product-local `agentDir` and model registry.
   - Safety-leaning MVP execution mode: on-demand Node subprocess per question rather than a long-lived shared process, unless implementation testing shows latency is unacceptable.
   - No built-in coding tools in product mode.
   - Only custom read-only tools registered, backed by existing backend/session artifacts or a generated context bundle.
   - If Pi SDK is too heavy for the first increment, keep the same FastAPI contract and temporarily implement direct Ollama calls behind the same interface.
3. **Strict project/session isolation** is a non-negotiable product requirement.
   - No persisted cross-project conversation memory in MVP.
   - No shared Pi session file across projects or clients.
   - Prefer one ephemeral/in-memory Pi session per Q&A request for MVP, seeded only with that request's `project_id`, `dataset_id`, `ingestion_session_id`, question, and context bundle.
   - Custom tools must receive a scoped context token or explicit session identifiers and must refuse any artifact path outside the selected session workspace.
   - The frontend must pass the selected uploaded session; the backend must not let the model choose or infer another project/session.
   - Any future persistent memory must be explicitly tenant/project scoped, encrypted/segregated, and audited before use.

Initial custom tools/concepts for the Pi agent:

- `get_preprocessing_eda_summary` — structured EDA summary already exposed by backend.
- `get_preprocessing_report` — preprocessing decisions, approval status, artifact paths.
- `get_training_artifact_index` — list available JSON/CSV artifacts without dumping them blindly.
- `get_column_profile` — missingness, min/mean/max, outlier hints, and units for requested columns.
- `get_sample_rows` — bounded, representative sample from canonical/raw tables with row/column caps.

Initial raw-data context policy:

- Always include schema, file inventory, row counts, missingness, distributions, split strategy, preprocessing methods, and approval status.
- Include raw/sample rows only when useful for the user question.
- MVP limits accepted by user: full numeric summaries, artifact reports, up to ~50 representative canonical rows, up to ~20 rows per uploaded workbook sheet when relevant, and no huge raw dumps unless explicitly requested.
- Cap sample rows and columns to avoid blowing the 65k context window; prefer summaries first, sample rows second.
- Never include secrets or credentials; uploaded scientific data is allowed for this project but should remain local/private.

Initial streaming/session policy:

- Stream tokens to the UI for a professional assistant feel.
- Keep conversations ephemeral for MVP: do not persist chat history, do not use cross-session memory, do not feed prior client/project conversations into later calls.
- The user may ask follow-up questions, but MVP follow-ups should either include visible prior turns from the current browser state or be treated as independent questions; no backend memory store yet.

## Files to modify

Likely implementation candidates:

- `frontend/src/components/ModelQualityPage.tsx` — remove old placeholder preprocessing/assistant cards.
- `frontend/src/components/PreprocessingReviewPage.tsx` — add/move preprocessing review artifacts and agent panel.
- `frontend/src/lib/api.ts` — add agent API client calls.
- `frontend/src/types/doe.ts` or `backend/app/schemas.py` — add typed request/response contracts if needed.
- `backend/app/main.py` — add agent routes.
- `backend/app/services/preprocessing_review.py` — reuse artifact loading/EDA context and possibly remove/update placeholder `pi_assistant_recommendations` content.
- `backend/app/services/data_intake.py` — reuse session/project artifact paths.
- New backend service, likely `backend/app/services/scientist_agent.py` — context assembly, guardrails, prompt construction, provider abstraction.
- New optional Node/Pi bridge if SDK integration is chosen, preferably under repo-local `agent-runtime/` with its own `package.json` to avoid contaminating frontend package concerns.
- Product-local Pi runtime files if SDK integration is chosen:
  - `agent-runtime/package.json` — isolated Node dependency boundary for Pi SDK/bridge spike.
  - `agent-runtime/pi-agent/models.json` — Ollama/OpenAI-compatible model config.
  - `agent-runtime/pi-agent/settings.json` — runtime-safe settings, telemetry disabled, no personal packages.
  - `agent-runtime/skills/ml-engineering-preprocessing/SKILL.md` — ML-engineering assistant guidance.
  - `agent-runtime/prompts/preprocessing-qa.md` — system/task prompt template.
  - `agent-runtime/README.md` — local usage and isolation notes.

Do not add Pi to the production Docker image until the SDK spike proves stable and safe. If added later, treat it as a product runtime dependency with pinned versions and license notices.

## Reuse

Already found:

- Existing placeholder UI in `frontend/src/components/ModelQualityPage.tsx` around the `Preprocessing aftermath` and `AI preprocessing assistant` cards.
- Existing preprocessing page state/loading in `frontend/src/components/PreprocessingReviewPage.tsx`.
- Existing backend endpoints in `backend/app/main.py`:
  - `GET .../preprocessing/status`
  - `GET .../preprocessing/eda-summary`
  - `GET .../preprocessing-report`
  - `POST .../preprocessing-approval`
  - `GET .../preprocessing/ydata-report.html`
- Existing artifact aggregation in `backend/app/services/preprocessing_review.py`, especially `get_preprocessing_eda_summary(...)`.
- Existing plan `docs/agent-plans/implemented/autoresearch-for-doe-plan.md` for bounded autonomous research patterns; useful safety principles, but not the same agent.
- Existing repo skills:
  - `skills/scientific-ui-clarity/SKILL.md`
  - `skills/surrogate-model-debugging/SKILL.md`
  - `skills/bayesian-optimization-feature/SKILL.md`
  - mirrored `.agents/skills/...` copies.
- Existing repo instructions in `AGENTS.md`.

Pi/web research findings so far:

- `@mariozechner/pi-coding-agent` npm package is MIT licensed, version `0.73.1`, Node `>=20.6.0`.
- Its companion packages checked so far (`@mariozechner/pi-agent-core`, `@mariozechner/pi-ai`, `@mariozechner/pi-tui`) also report MIT license on npm.
- Pi docs provide SDK and RPC modes for embedding/headless use, but default CLI behavior is a coding-agent tool loop.
- Pi CLI supports `--no-tools`, `--no-builtin-tools`, `--tools`, `--no-skills`, `--skill`, `--no-context-files`, and `--no-session`, useful for safe experiments.
- Pi SDK supports custom tools via `defineTool(...)` and custom session/model/auth/resource configuration.
- Pi project settings override global settings via `.pi/settings.json`; sessions can be isolated with `sessionDir` / `--session-dir` / `PI_CODING_AGENT_SESSION_DIR`.
- Pi has a documented `PI_CODING_AGENT_DIR` environment variable to override the default global config directory (`~/.pi/agent`). This is the key to not touching the user's personal Pi config.
- Pi has startup telemetry/version checks; docs say `enableInstallTelemetry: false`, `PI_SKIP_VERSION_CHECK=1`, `PI_OFFLINE=1`, or `--offline` can control this.
- Pi supports Ollama/OpenAI-compatible endpoints via model config: `baseUrl: http://localhost:11434/v1`, `api: openai-completions`, dummy `apiKey: ollama`, plus compatibility flags for local servers.
- The user's active local Pi model is `ollama/qwen3.6:35b-a3b-coding-nvfp4`, display name `Qwen 3.6 35B A3B Coding local`, context window `65536`, max output `8192`.
- Qwen model license spot-checks from Hugging Face for Qwen3 4B/8B and Qwen2.5 Coder 7B show Apache-2.0, but the exact `qwen3.6:35b-a3b-coding-nvfp4` distribution/license must be verified before commercial deployment.

## Steps

- [x] Scan current placeholder UI and preprocessing review artifacts.
- [x] Read related autoresearch plan and identify overlap/non-overlap.
- [x] Research initial Pi package/license/local model support without changing package state.
- [ ] Confirm product/legal posture with user and, before commercialization, counsel.
- [ ] Choose Pi SDK spike architecture vs direct Ollama fallback; current recommendation is Pi SDK with custom read-only tools plus a fallback direct provider interface if SDK integration becomes too heavy.
- [ ] Use repo-local `agent-runtime/package.json` as the isolated Pi dependency boundary if Pi is installed.
- [ ] Implement ephemeral per-request sessions for MVP to avoid cross-client/project contamination.
- [ ] Prefer an on-demand Node subprocess per question for the first Pi SDK bridge unless startup latency proves unacceptable.
- [ ] Define a safe MVP agent contract: free-form Q&A, read-only artifacts, no code execution, no data mutation, no autonomous preprocessing.
- [ ] Define artifact context bundle for each uploaded project/session, including raw upload inventory, bounded raw/sample rows, EDA reports, schema, missingness, distributions, preprocessing decisions, split reports, and training status when available.
- [ ] Use accepted raw-data limits: full summaries, up to ~50 canonical rows, up to ~20 workbook rows per relevant sheet, no large dumps by default.
- [ ] Define answer format: concise explanation, artifact citations, assumptions, suggested follow-up checks, and explicit "no changes applied" marker.
- [ ] Move preprocessing placeholder/review UI from Model Quality into Preprocessing Review.
- [ ] Add backend Q&A endpoint for Preprocessing Review that talks to the Pi SDK/bridge and streams tokens plus final structured metadata.
- [ ] Add frontend free-form streaming Q&A panel in Preprocessing Review.
- [ ] Keep approval actor as `mirai_admin` for MVP.
- [ ] Defer structured proposal cards, persistent memory, global assistant, and Mirai-hosted GPU abstraction until after the Q&A MVP is proven useful.
- [ ] Add tests and manual verification path.

## Verification

Planned verification:

- Confirm Model Quality no longer shows stale preprocessing/agent placeholders.
- Confirm Preprocessing Review shows preprocessing artifacts and review status.
- Ask the agent artifact-grounded questions such as:
  - What columns were imputed and why?
  - Was scaling fit only on train data?
  - Which uploaded files and cells were included?
  - Which features have missingness/outliers?
  - What preprocessing options should a scientist consider before retraining?
  - Why are grouped cell splits used, and what leakage risks were checked?
- Confirm answers cite session artifacts and avoid claiming autonomous changes were made.
- Confirm no agent response can execute scripts, write files, start training, or approve preprocessing.
- Confirm local model calls use the isolated product/runtime config rather than `~/.pi/agent`.
- Confirm no project/session cross-contamination:
  - custom tools reject mismatched `project_id`, `dataset_id`, or `session_id`,
  - no persisted server-side chat memory is read across requests,
  - sample rows and artifacts come only from the selected session workspace.
- Confirm streaming works and still produces a final complete answer object.
- Confirm the feature can be disabled cleanly if no Ollama/Pi runtime is configured.
- Backend tests: `cd backend && uv run pytest tests/test_api.py -q`.
- Frontend build: `cd frontend && npm run build`.

## Legal/commercial notes to verify

This is not legal advice. Initial evidence suggests:

- MIT-licensed Pi packages generally allow commercial use, modification, and distribution if copyright/license notices are preserved.
- Apache-2.0 Qwen model weights generally allow commercial use subject to Apache notice/patent/redistribution terms, but the exact model card/license must be checked for the exact Ollama/Hugging Face model shipped or recommended.
- Selling software to OEMs changes the risk profile: keep a dependency/license SBOM, preserve notices, and have counsel review Pi, Ollama, model weights, and any transitive dependencies before distribution.
- If OEM/customer data is confidential, a local/private model endpoint is strategically better than sending uploaded data to OpenAI/Anthropic/etc.

## Current user decisions

- MVP interaction mode: free-form Q&A only.
- Agent value desired: Pi-like context management, skills, and ML-engineering guidance, not just bare LLM calls.
- Raw uploaded data may be used along with EDA/preprocessing artifacts, subject to sensible context limits.
- Accepted raw-data limits: full summaries, up to ~50 representative canonical rows, up to ~20 rows per relevant workbook sheet, no huge dumps by default.
- Approval actor: Mirai admin for now.
- MVP chat memory: ephemeral.
- MVP answer UX: token-by-token streaming.
- Future deployment target: Mirai-hosted isolated server/GPU, but do not design that abstraction now.
- Long-term direction: eventually a global software assistant, but MVP lives in Preprocessing Review.
- Cross-client/project contamination would be catastrophic; isolation must be designed as a hard requirement.
- Approved isolation rule: one fresh in-memory Pi agent session per question; no backend-persisted chat memory in MVP.
- Approved dependency boundary: if Pi is installed, install it under repo-local `agent-runtime/package.json`, not outside the repo and not in root/frontend package concerns.
- Approved config separation: preserve existing repo `.pi/` for the user's developer/plannotator Pi workflow; product runtime config belongs only under repo-local `agent-runtime/pi-agent/` using `PI_CODING_AGENT_DIR`.
- Accepted MVP tradeoff: follow-up questions may be slightly less conversational in exchange for stronger project/client isolation.

## Open questions

- During implementation, should the first Pi SDK bridge be built as a long-lived local service process, or as an on-demand Node subprocess per question? Current safety-leaning recommendation: on-demand subprocess for MVP, because process lifetime is short and state cannot leak, even if startup latency is higher.
