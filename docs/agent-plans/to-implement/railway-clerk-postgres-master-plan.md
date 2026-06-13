# Master Implementation Plan: Clerk Auth, Railway Single-Container Demo, and Postgres Security Layer

## Agent Execution Prompt

Use this prompt at the start of every implementation session for this master plan:

> Execute this plan with token-efficient agent orchestration. Use agents **in series** where that reduces main-context load: start with `scout` for read/grep/file-discovery work, preferably on the local Gemma model configured for fast repository scanning; then pass Scout's concise findings to `context-builder` or `planner` instead of rereading broad code areas in the parent session. Use parallel agents only for independent planning/review domains. Keep implementation single-writer with `worker` on one approved vertical slice at a time. After each slice, run `/test`, `/review`, and `/code-simplify` as appropriate. Surface assumptions, stop on ambiguity, and avoid loading unrelated files into the parent context.

## Goal
Deliver this refactor safely, in phases, without breaking `main`:

1. Add Clerk auth in the `clerk-auth` branch, with manual Clerk Dashboard setup checkpoints.
2. Build a Railway-specific single-container deployment on the `railway` branch, preserving the existing multi-container/Docker Compose path on `main`.
3. Introduce a Postgres-backed security/control plane that respects the current repo structure, generic tabular DoE lifecycle, MLflow integration, artifact/data storage, model training/serving, and BO state.

This plan is intentionally a master sequencing plan. Implementation should be broken into smaller Plannotator-approved plans per phase.

## Execution Model: Skills, Lifecycle Slash Commands, and Subagents

Before implementing any phase, use the repo/global Pi engineering workflow rather than ad-hoc coding. The goal is to maximize efficiency, best practices, sustainability, and low technical debt.

### Lifecycle slash commands to use
These prompt templates exist under `~/.pi/agent/prompts/` and map to professional SWE skills in `~/.pi/agent/skills/`:

1. `/spec` — use `spec-driven-development` for any phase whose requirements or boundaries are not yet concrete.
2. `/plan` — use `planning-and-task-breakdown` to create the phase-specific Plannotator plan and vertical slices.
3. `/build` — use `incremental-implementation` + `test-driven-development`; implement only the next approved slice unless the user explicitly approves `/build auto`.
4. `/test` — use `test-driven-development`; add failing/regression tests first where practical, then verify targeted and broader suites.
5. `/review` — use `code-review-and-quality`; review correctness, readability, architecture, security, and performance before merge.
6. `/code-simplify` — use `code-simplification` after each implementation slice to reduce complexity without changing behavior.
7. `/ship` — use `shipping-and-launch` for Railway/pilot readiness, rollback plan, environment checks, security checks, and go/no-go decision.

### Skills to explicitly activate by phase
- Always start with `using-agent-skills` to choose the right workflow and surface assumptions.
- Requirements/planning: `spec-driven-development`, `planning-and-task-breakdown`, `context-engineering`, `doubt-driven-development`.
- Clerk/frontend/API work: `frontend-ui-engineering`, `api-and-interface-design`, `security-and-hardening`, `test-driven-development`.
- Railway/deployment work: `ci-cd-and-automation`, `shipping-and-launch`, `documentation-and-adrs`, `git-workflow-and-versioning`.
- Postgres/RLS/storage security: `security-and-hardening`, `api-and-interface-design`, `deprecation-and-migration`, `source-driven-development`, `test-driven-development`.
- Reviews/refinement: `code-review-and-quality`, `code-simplification`, `performance-optimization`, `debugging-and-error-recovery` as needed.

### Pi subagents to use
Use `pi-subagents` for parallel discovery, planning, and independent review, but keep code edits single-writer per branch/worktree.

- `scout`: fast repo/file discovery before each phase; identify existing patterns to reuse.
- `context-builder`: produce focused context packs for Clerk, Railway, Postgres/RLS/storage, MLflow/training/serving, and BO.
- `planner`: convert context into phase-specific implementation plans with acceptance criteria.
- `worker`: implement one approved vertical slice at a time in the active branch/worktree.
- `reviewer`: independently review each slice and pre-merge diff using `/review` criteria.
- `oracle`: use only for high-risk architecture/security tradeoffs or unresolved contradictions.
- `delegate`: use for bounded research or mechanical checks that do not edit code.

Default cadence per phase:
1. `/spec` if requirements are unclear.
2. `scout` + `context-builder` read-only context pass.
3. `/plan` + `planner` creates a phase plan and submits it to Plannotator.
4. `/build` with one `worker` for the next approved slice.
5. `/test`, then `/review` with `reviewer`.
6. `/code-simplify` if the slice added avoidable complexity.
7. Repeat until the phase plan is complete.
8. `/ship` before Railway deploy, branch merge, or pilot-client use.

Guardrails:
- Surface assumptions before each phase and stop on unresolved ambiguity.
- Prefer boring, minimal changes over broad abstractions.
- Touch only files required by the current approved slice.
- No secrets in git, logs, prompts, plans, Docker images, or PR descriptions.
- No GitHub MCP writes, deploys, DB migrations against shared environments, or dashboard changes without explicit human approval.

## Source Inputs
- User brainstorm: `docs/agent-plans/to-implement/railway-brainstorm-bruno.md`
- Subagent scout/planning chain artifacts: `/tmp/pi-subagents-railway-master-plan/e2025a54/`
- Current branch setup:
  - `main` has guarded GitHub MCP workflow.
  - `railway` has guarded GitHub MCP workflow and remains active for Railway work.
  - `clerk-auth` was created from updated `main` for auth work.

## Core Decisions

### Branching
- `clerk-auth`: Clerk frontend/backend auth work starts here.
- `railway`: Railway single-container work starts/stays here.
- `main`: remains stable. Clerk can merge to `main` only after auth checks pass. After that, Clerk must also be merged into `railway` so the Railway pilot/demo is authenticated. Railway-specific deployment should not merge to `main` until explicitly reviewed as non-breaking or intentionally adopted.
- Postgres/security work should be staged behind flags. For the Railway pilot, target Level 2 isolation on `railway`; platform-wide reusable pieces can later be ported back to `main` through a reviewed PR.

### Railway Level 2 pilot security vs future Level 3 isolation
- Railway single-container deployment cannot provide Kubernetes namespace/database-per-client physical isolation.
- The Railway pilot should therefore target **Level 2 virtual isolation** that is safe enough for one or two pilot clients:
  - Clerk authentication.
  - first-login workspace provisioning from Clerk identity/user metadata.
  - explicit workspace/project authorization in backend code.
  - Postgres tenant/workspace tables with Row-Level Security (RLS).
  - per-client storage separation through workspace-scoped object prefixes or buckets, never shared unscoped paths.
  - artifact/object metadata in Postgres, with SQL checks tying every object URI to a workspace.
  - exact CORS origins.
  - no secrets in git/image/logs.
- Level 3 physical isolation remains a future production architecture target, likely AWS/Kubernetes/GitOps, not a Railway constraint.

### Security layer path
- First implement Clerk plus a minimal workspace model: first login creates or resolves a workspace for the Clerk user, then all project/data/model actions are scoped to that workspace.
- Then implement Railway Level 2 security: Postgres metadata/control plane with tenant/workspace scoping, RLS, and per-client storage prefixes/buckets.
- Keep raw datasets, canonical tables, model artifacts, and MLflow artifact blobs in file/object storage, not in SQL.
- SQL stores metadata, artifact URIs/hashes, lifecycle state, model bindings, BO observations/configs, reviews, and audit records.

### Generic lifecycle invariant
`generic_tabular_doe` remains the source of truth. Fraunhofer/PEM behavior must continue to act as an extractor/adapter into the generic contract, not as a separate lifecycle.

## Phase 0: Preconditions and Human Decisions

### Tasks
- [ ] Confirm branch state:
  - `main` is stable.
  - `clerk-auth` points to current `main`.
  - `railway` remains active for Railway work.
- [ ] Confirm Clerk merge path: implement on `clerk-auth`, merge to `main` after auth checks pass, then merge the same Clerk work into `railway` before Railway deployment.
- [ ] Confirm Railway Level 2 persistence mode:
  - bootstrap may start stateless only for the very first smoke test, but the pilot target is durable Railway Postgres plus safe per-client storage separation;
  - preferred durable storage design: one object store or Railway volume root with enforced `workspace_id` prefixes, artifact metadata in Postgres, and no unscoped file paths.
- [ ] Confirm initial Railway pilot should preserve durable uploads/training outputs/BO observations once Level 2 storage is enabled.
- [ ] Confirm Clerk tenancy model defaults to user metadata / first-login workspace provisioning unless later replaced by Clerk Organizations.
- [ ] Clarify FastAPI auto-generated API docs behavior for Railway: this means `/docs`, `/redoc`, and `/openapi.json`, not an agent integration. Default recommendation is local/dev only or auth-protected in Railway.
- [ ] Ensure local secret hygiene:
  - `.env`, `.env.local`, and local Railway/Clerk/GitHub tokens stay ignored.
  - no real token values are copied into plans, prompts, logs, Docker image, or PR descriptions.

### STOP / Human action
Do not start implementation until the human confirms:
1. Clerk tenancy model: default to first-login user-metadata workspace provisioning unless the human chooses Clerk Organizations.
2. Railway Level 2 persistence decision: durable Postgres plus per-client separated storage is the pilot target; stateless mode is allowed only as a temporary bootstrap smoke test.
3. Desired merge order: `clerk-auth` → `main`, then `main`/Clerk auth → `railway` before Railway deployment.
4. Railway handling for FastAPI auto-generated docs (`/docs`, `/redoc`, `/openapi.json`): local-only, disabled, or auth-protected.

### Validation
```bash
git fetch origin
git status --short --branch
git branch --all --verbose --no-abbrev | grep -E 'main|railway|clerk-auth'
```

## Phase 1: Clerk Auth on `clerk-auth`

### Objective
Add visible and enforceable Clerk authentication without destabilizing deployment or data workflows.

### Scope
Frontend first, then backend authorization boundary.

### Likely files
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/vite-env.d.ts`
- optional `frontend/src/components/AuthApiBridge.tsx`
- optional `frontend/src/components/ProjectHeader.tsx`
- `backend/app/main.py`
- new `backend/app/auth.py`
- `backend/pyproject.toml`
- `backend/uv.lock`
- `.env.example` or existing env example file

### Tasks
1. Add Clerk env placeholders only.
   - `VITE_CLERK_PUBLISHABLE_KEY`
   - `CLERK_ISSUER` / `CLERK_JWKS_URL` or equivalent backend verification values.
   - optional `CLERK_AUDIENCE`.
   - exact `CORS_ORIGINS`.
2. Install Clerk React SDK.
3. Wrap frontend in `ClerkProvider`.
4. Add signed-out and signed-in UI states while preserving current Mirai branding/layout.
5. Add a token bridge so API requests include `Authorization: Bearer <Clerk JWT>`.
6. Add backend JWT verification.
7. Protect non-public backend routes.
8. Keep `/health` public.
9. Decide whether FastAPI auto-generated API docs (`/docs`, `/redoc`, `/openapi.json`) stay local/dev only, disabled, or auth-protected in Railway.
10. Start workspace authorization with an explicit `AuthenticatedPrincipal` carrying Clerk identity and resolved workspace.
11. Implement first-login workspace provisioning: if the authenticated Clerk user has no workspace mapping, create a workspace record and persist the mapping in backend metadata/user mapping rather than trusting a client-supplied workspace ID.

### STOP / Human action: Clerk Dashboard
Human must configure:
- Clerk application.
- allowed redirect/origin URLs for local dev and future Railway URL.
- sign-in method/password policy.
- Default choice: user metadata / backend user mapping that provisions a workspace on first login; Clerk Organizations can be deferred unless multi-user company accounts are required immediately.
- JWT template/audience/issuer/JWKS as needed.
- demo users/orgs for Mirai Engineering/Fraunhofer if needed.

### Acceptance criteria
- [ ] Signed-out users cannot see project/data tabs.
- [ ] Signed-in users can use the current UI.
- [ ] Frontend sends bearer token on protected API requests.
- [ ] Backend rejects missing/invalid tokens with 401.
- [ ] Minimum workspace behavior is explicit before merge: either real Clerk-to-workspace authorization is implemented, or protected multi-workspace/domain APIs remain disabled/guarded until the DB/security layer lands.
- [ ] Backend rejects cross-workspace access with 403 once workspace mapping is active.
- [ ] No token is stored in local/session storage.
- [ ] No real Clerk secrets are committed.

### Validation
```bash
cd frontend && npm install
cd frontend && npm run lint
cd frontend && npm run build
cd backend && uv run pytest
```

### Merge gate
Only after validation and human Clerk dashboard confirmation:
- merge `clerk-auth` into `main`.
- then merge/update `railway` from `main` so Railway branch receives auth.

## Phase 2: Railway Single-Container Foundation on `railway`

### Objective
Create a Railway-specific deployment that uses one container and one exposed `$PORT`, with FastAPI serving both API and built React static assets.

### Non-goals
- Do not replace current Compose/Nginx workflow on `main`.
- Do not introduce Nginx inside the Railway container unless a later proof shows FastAPI static serving is insufficient.
- Do not overfit to ECS/Kubernetes concepts.

### Likely files
- `Dockerfile.railway`
- `.dockerignore`
- `railway.json`
- `backend/app/main.py`
- `docs/deployment/railway-single-container.md` or `deployments/railway/README.md`
- possibly frontend env/build config

### Tasks
1. Document Railway deployment contract.
2. Add Railway Dockerfile:
   - build React frontend.
   - install backend with `uv`.
   - copy built static assets into runtime image.
   - run FastAPI/Uvicorn on `$PORT`.
3. Add guarded static SPA serving to FastAPI.
4. Add `/api/*` route compatibility or prefix stripping for Railway mode.
5. Preserve existing root API route compatibility for current local/backend flows.
6. Add `.dockerignore` tuned for Railway:
   - exclude secrets/runtime clutter.
   - do not accidentally exclude required seeded demo/reference artifacts if the demo depends on them.
7. Decide which MLflow/reference/demo artifacts are intentionally baked into the image.
8. Add a bootstrap-vs-pilot storage note: stateless image is allowed only for initial smoke testing; the pilot target requires durable per-client storage separation.
9. Document Railway env vars and setup steps.

### STOP / Human action: Railway Dashboard
Human must:
- create/connect Railway service to `railway` branch only.
- configure Dockerfile path or Railway config.
- set env vars in Railway UI, not git.
- configure public domain after auth is validated.

### Acceptance criteria
- [ ] `docker build -f Dockerfile.railway -t mirai-doe-railway .` passes.
- [ ] Container starts with `PORT=8000` locally.
- [ ] `GET /` returns React app.
- [ ] `GET /health` works.
- [ ] `GET /api/health` works.
- [ ] Existing Compose workflow still builds/runs.
- [ ] No `main` deployment behavior is changed accidentally.
- [ ] Stateless limitations are explicitly documented as bootstrap-only; pilot deployment has a follow-up gate for durable Level 2 storage.

### Validation
```bash
docker build -f Dockerfile.railway -t mirai-doe-railway .
docker run --rm -p 8000:8000 -e PORT=8000 mirai-doe-railway
curl -i http://localhost:8000/health
curl -i http://localhost:8000/api/health
curl -i http://localhost:8000/
docker compose build
```

## Phase 3: Postgres Security / Control Plane Foundation

### Objective
Introduce SQL/Postgres safely as a metadata and security control plane while preserving current file/object/MLflow lifecycle behavior.

### STOP / Human action: choose Phase 3 branch/base
Before any schema, repository, or migration implementation starts, human must decide one of these paths:

1. **Platform-first path:** branch from `main`, build DB/security foundation behind flags, merge to `main`, then merge/update `railway`.
2. **Demo-first path:** branch from `railway`, implement only what the Railway demo needs, then later port the stable platform pieces back to `main` through a reviewed PR.
3. **Split path:** schema/security abstractions from `main`; Railway env/deployment wiring from `railway`.

Acceptance: the selected base branch, merge target, and whether DB is required for the first Railway demo are written into the phase-specific Plannotator plan before implementation.

### Design rules
- DB disabled by default at first.
- Feature flags for DB reads/writes/enforcement.
- Every tenant-scoped table has `workspace_id`.
- Repositories require a security context.
- RLS should protect against forgotten `WHERE workspace_id = ...` clauses.
- Raw data, canonical data files, model artifacts, and MLflow artifact blobs remain outside SQL.

### Likely files
- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/0001_security_control_plane.py`
- `backend/app/db/*`
- `backend/app/security/context.py`
- `backend/app/security/audit.py`
- `backend/app/repositories/*`
- `backend/app/commands/backfill_control_plane.py`

### Tasks
1. Add DB config and dependency scaffold.
2. Add Alembic migration scaffold.
3. Create tables for:
   - workspaces
   - workspace memberships
   - projects
   - datasets
   - ingestion sessions
   - artifact objects
   - training requests
   - MLflow/model bindings
   - BO configs
   - BO observations
   - scientist reviews
   - audit events
4. Add Postgres RLS policies using transaction-scoped workspace context.
5. Add repository layer that refuses missing `SecurityContext`.
6. Add idempotent backfill command from current file/object/MLflow state.
7. Keep file-backed fallback until DB parity is proven.
8. Add a storage adapter contract that requires `workspace_id` for every object path and refuses unscoped paths.
9. Store object/artifact URIs and hashes in Postgres so RLS-backed metadata controls all data/artifact discovery.

### STOP / Human action: DB provisioning
Before DB-enabled deployment, human must choose/provision:
- local dev Postgres and Railway Postgres.
- `DATABASE_URL` secret location.
- whether DB writes are enabled in Railway.
- whether DB reads become source of truth or fallback remains active.
- storage backend for per-client separation: Railway volume root with strict `workspace_id` directories for the pilot, or S3-compatible object storage with per-workspace prefixes/buckets if available.

### Acceptance criteria
- [ ] Existing tests pass with DB flags unset.
- [ ] Fresh migration applies cleanly.
- [ ] RLS tests prove workspace A cannot read workspace B.
- [ ] Backfill is idempotent.
- [ ] `/projects` and core lifecycle metadata responses match current behavior.
- [ ] No raw datasets/model blobs stored in SQL.
- [ ] Per-client storage separation exists for the Railway pilot: every upload, canonical artifact, training output, MLflow artifact pointer, BO artifact, and review artifact is under a workspace-scoped prefix/root.
- [ ] Storage adapter tests prove unscoped or cross-workspace paths are refused.

### Validation
```bash
cd backend && uv run pytest
cd backend && DATABASE_URL=postgresql://... uv run alembic upgrade head
cd backend && DOE_DB_ENABLED=1 DATABASE_URL=postgresql://... uv run pytest -m postgres
cd backend && DOE_DB_ENABLED=1 DATABASE_URL=postgresql://... uv run python -m app.commands.backfill_control_plane
cd backend && DOE_DB_ENABLED=1 DATABASE_URL=postgresql://... uv run python -m app.commands.backfill_control_plane
```

## Phase 4: Lifecycle Integration Slices

These must be mostly serial because each slice depends on the previous security/data contract. Each slice has its own gate; do not start the next slice until parity/auth/security validation for the current slice passes or the human explicitly accepts a documented limitation.

### Slice 4.1: Workspace/project discovery
- DB-backed workspace/project list with file fallback.
- Filter by authorized workspace.
- Preserve current response shapes.
- Gate: workspace/project API parity tests pass in file-backed and DB-enabled modes; unauthorized workspace access is denied.

### Slice 4.2: Data intake/preprocessing metadata
- Register uploads/session statuses/artifact URIs in SQL.
- Keep bytes in object/file storage.
- Add path-root assertions before destructive operations.
- Gate: intake/preprocessing tests prove workspace scoping, artifact URI correctness, and file fallback parity before training work starts.

### Slice 4.3: Training requests and MLflow bindings
- Store training lifecycle records.
- Store MLflow experiment/run/model/version/alias/artifact URI metadata.
- Preserve generic tabular training and challenger/champion rules.
- Gate: generic training pipeline tests pass; MLflow run/model binding is workspace-scoped; unauthorized training is denied before serving work starts.

### Slice 4.4: Serving/model-quality resolution
- Resolve model through workspace-scoped bindings.
- Include `workspace_id`, model version/alias, schema hash, and artifact hash in cache keys.
- Prevent cross-workspace model/preprocessor cache contamination.
- Gate: prediction/model-quality tests prove no cross-workspace cache/artifact leakage before BO work starts.

### Slice 4.5: BO state and observations
- Store BO config/observations with provenance.
- Preserve current BO endpoint shapes.
- Scope all suggestions/reviews/reveals/fantasy rollouts to workspace/project.
- Gate: BO config/state/suggestion/review/reveal/fantasy tests pass with workspace scoping before audit hardening starts.

### Slice 4.6: Audit logging
- Log actor/resource/action/request metadata.
- Never log tokens or raw experimental data contents.
- Gate: audit tests verify required metadata and absence of tokens/raw data before DB mode can be considered deployable.

### Validation
```bash
cd backend && uv run pytest backend/tests/test_generic_contract_pipeline.py
cd backend && uv run pytest
cd backend && DOE_DB_ENABLED=1 DOE_DB_WRITES_ENABLED=1 DATABASE_URL=postgresql://... uv run pytest -m postgres
docker build -f Dockerfile.railway -t mirai-doe-railway .
```

## Phase 5: Railway Deployment and E2E Gate

### Tasks
1. Set Railway env vars manually.
2. Deploy only from `railway`.
3. Verify public health/static routes.
4. Verify signed-out UX.
5. Verify signed-in authorized workspace flow.
6. Verify unauthorized workspace denial.
7. Verify seeded demo prediction/model-quality/BO flows or explicitly disable with clear messages.
8. If the demo is temporarily stateless during bootstrap, show explicit UX/API messaging for non-durable uploads, training outputs, BO observations, and review artifacts.
9. Before pilot use with one or two clients, enable durable Level 2 storage: Railway Postgres plus workspace-scoped storage prefixes/root and RLS-backed artifact metadata.
10. Create draft PR(s) with safe GitHub MCP only after human approval.

### Acceptance criteria
- [ ] Railway build succeeds.
- [ ] Railway URL serves SPA.
- [ ] `/health` and `/api/health` work.
- [ ] Clerk auth works on Railway URL.
- [ ] Protected data APIs require auth.
- [ ] Workspace/project authorization is enforced.
- [ ] MLflow/model-quality/prediction/BO demo path works or is explicitly disabled.
- [ ] For any real pilot client data, durable Level 2 storage is enabled and verified; stateless mode is used only for internal smoke tests.
- [ ] No secrets appear in git diff, Docker image, Railway logs, or PR text.

## Parallel Agent Strategy

Use Pi subagents aggressively for planning/review, but keep code edits single-writer per branch/worktree.

### Safe parallel planning
- Scout branch/repo state.
- Planner A: Clerk/frontend/backend auth.
- Planner B: Railway Docker/static serving.
- Planner C: Postgres/RLS/security control plane.
- Reviewer: architecture/security/MLflow risk review.
- Parent synthesizes into Plannotator plan.

### Safe implementation pattern
For each phase:
1. Scout/context-builder reads relevant files.
2. Planner creates phase-specific implementation plan.
3. Plannotator review/approval.
4. One worker implements in one branch/worktree.
5. Parallel reviewers inspect diff:
   - correctness/regression
   - security/privacy
   - deployment/runtime
   - MLflow/data lifecycle
6. Worker applies accepted fixes.
7. Parent runs validation and asks human before external service actions.

### Do not parallelize
- Multiple writers editing same worktree.
- DB schema and service repository changes without a frozen contract.
- Clerk dashboard/Railway dashboard operations.
- GitHub writes without explicit approval.

## GitHub MCP Usage
- Use GitHub MCP for read-only branch/PR inspection freely when relevant.
- Use guarded wrapper or explicit approval for write actions.
- Before PR creation, summarize:
  - branch
  - base
  - changed files
  - validation run
  - risks
- Do not use MCP to merge PRs, delete branches, force-push, change secrets, or alter branch protection without a separate explicit approval.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Railway demo mistaken for Level 3 isolation | Document Railway as Level 2 pilot security only; keep Level 3 as future production target. |
| Level 2 storage leaks through unscoped paths | Require workspace-scoped storage adapter, Postgres artifact metadata, RLS, and tests that reject unscoped/cross-workspace paths. |
| Clerk only authenticates users but not workspace access | Add first-login workspace provisioning plus explicit backend workspace/project authorization. |
| Static catch-all shadows APIs | Register static fallback after API routes; test `/health`, `/api/health`, API routes, and SPA refresh. |
| Secret exposure | placeholders only; ignored env files; scan diffs before commits/PRs. |
| Railway ephemeral filesystem loses uploads/training/BO state | allow stateless mode only for internal bootstrap smoke tests; require durable Level 2 storage before real pilot client data. |
| MLflow path/artifact breakage in single image | validate seeded artifact resolution locally before Railway deploy. |
| RLS context leaks through pooled connections | use transaction-scoped `SET LOCAL`; test cross-workspace denial. |
| File fallback bypasses DB auth | enforce path roots and security context before file/object access. |
| Model cache cross-tenant contamination | include workspace/project/model/artifact hashes in cache keys. |
| Huge refactor loses reviewability | split into phase-specific Plannotator plans and short-lived branches. |

## Remaining Open Questions for Human
1. Which Railway URL/domain should be configured in Clerk allowed origins once Railway creates the service URL?
2. Which seeded demo artifacts are approved to bake into the Railway image?
3. For the first pilot, should per-client object storage use a Railway volume root with `workspace_id` directories, or an S3-compatible object store with per-workspace prefixes/buckets?
4. Should unauthorized resources return explicit 403 or 404-style concealment?
5. For FastAPI's auto-generated API docs (`/docs`, `/redoc`, `/openapi.json`), should Railway disable them or protect them behind auth? These are HTTP API docs generated by FastAPI, not an agent integration.
6. Which parts of the current file-backed lifecycle must remain available during DB transition?
7. What is the long-term production target for Level 3 isolation: AWS EKS, ECS-per-client, or another platform?

## Immediate Next Plan Candidates
After this master plan is reviewed, create separate implementation plans:

1. `clerk-auth-phase-plan.md`
2. `railway-single-container-phase-plan.md`
3. `postgres-control-plane-phase-plan.md`
4. `lifecycle-db-integration-phase-plan.md`
5. `railway-e2e-deployment-runbook.md`
