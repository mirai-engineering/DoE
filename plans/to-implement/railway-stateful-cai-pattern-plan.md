# Implementation Plan: Railway Stateful Demo Following CAI Architecture Patterns

_Last updated: 2026-06-12_

**Agent orchestration reminder:** before starting any non-trivial task in this plan, prefer a token-efficient `scout -> planner -> worker/reviewer` chain when agents in series are useful. In particular, use `scout` for codebase reconnaissance instead of repeatedly loading broad context in the main session, then pass the scout summary into `planner` or `worker`. Use parallel read-only reviewers only for validation/review; keep implementation single-writer. Restart Pi before relying on newly moved repo-local Railway/Clerk skills or the repo-local lazy Railway MCP server, because skill/MCP discovery happens at session startup.

## Overview

Build Mirai's Level 2 demo as a stateful Railway deployment that follows the durable-state architecture patterns proven in CAI, without adopting CAI's Kubernetes runtime yet. The target is two isolated demo workspaces/projects: one for fuel cells and one for batteries. Each project must keep its dataset, preprocessing outputs, MLflow artifacts, ONNX model files, BO state, and review artifacts in durable object storage, with metadata and access control in Postgres.

The key translation from CAI is:

```text
CAI pattern:      MLflow metadata -> Postgres, artifacts/models -> MinIO/S3
Mirai Level 2:    MLflow/project metadata -> Railway Postgres, artifacts/models -> Railway S3-compatible buckets
```

Railway gives us most of the primitives we wanted from the CAI stack as managed services: app services, Postgres, and object storage buckets. Therefore, Level 2 should use Railway-native services instead of running `kind` inside Railway.

## Goals

- [ ] Deploy Mirai as a stateful Railway Level 2 demo.
- [ ] Support two demo workspaces/signups:
  - Fuel-cell/Fraunhofer demo.
  - Battery/generic tabular DoE demo.
- [ ] Store two projects' durable state in separate object buckets or clearly separate bucket roots.
- [ ] Keep MLflow artifacts and ONNX models durable across app redeploys/restarts.
- [ ] Preserve `generic_tabular_doe` as the source-of-truth lifecycle.
- [ ] Keep the PEM fuel-cell path as an intake adapter into the generic lifecycle.
- [ ] Provide practical visibility into Postgres, object storage, and MLflow/model artifacts.
- [ ] Leave a clean future path to Level 3 Kubernetes/security isolation.

## Non-goals

- [ ] Do not run `kind` inside Railway.
- [ ] Do not introduce active Kubernetes manifests as a supported deployment path yet.
- [ ] Do not market Level 2 as physical tenant isolation.
- [ ] Do not commit secrets, generated datasets, MLflow runtime directories, or bucket credentials.
- [ ] Do not fork the fuel-cell lifecycle away from the generic lifecycle.

## Architecture Decisions

### 1. Railway-native Level 2 runtime

Use Railway app/services directly:

```text
Browser / Clerk
  -> Railway app service: mirai-doe
       - React SPA served by FastAPI
       - Clerk auth and workspace authorization
       - Generic tabular DoE lifecycle
       - PEM ZIP adapter only before canonical contract tables
  -> Railway Postgres
       - workspace metadata
       - project metadata
       - artifact pointers
       - optional MLflow backend store
  -> Railway object bucket: mirai-fuel-cells-demo
       - fuel-cell dataset/artifacts/models
  -> Railway object bucket: mirai-batteries-demo
       - battery dataset/artifacts/models
  -> Optional Railway MLflow UI service
       - reads same backend/artifact stores
```

Rationale:

- Railway provides the primitives we need without Kubernetes operational overhead.
- The Level 2 pilot needs speed, clarity, and reliable demos more than full platform abstraction.
- Nested `kind` inside Railway would add Docker-in-Docker, networking, volume, and debugging complexity.
- A Railway-native layout still maps cleanly to Level 3 later.

### 2. Use CAI's durable-state pattern, not CAI's runtime

Relevant CAI patterns:

- `deployments/dev/kind/manifests/mlflow-values.yaml` wires MLflow to external S3/MinIO and external Postgres.
- `deployments/dev/kind/manifests/risingwave-values.yaml` uses Postgres for metadata and MinIO for object/state storage.
- CAI separates `deployments/dev/` and `deployments/prod/`, but this is useful only once Kubernetes is an active runtime.

For Mirai now:

- Keep active runtime files minimal: `Dockerfile.railway`, `railway.toml`, `.railwayignore`, docs.
- Add placeholder folders only:
  - `deployments/railway/`
  - `deployments/local-kind/`
  - `deployments/k8s/`
- Add real Kubernetes manifests later only when Level 3 work begins.

### 3. Storage contract

Prefer one bucket per demo workspace for clarity:

```text
s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/
  intake/
  canonical/
  preprocessing/
  mlflow-artifacts/
  onnx/
  bo/
  reviews/

s3://mirai-batteries-demo/workspaces/battery-demo/projects/<battery_project_id>/
  intake/
  canonical/
  preprocessing/
  mlflow-artifacts/
  onnx/
  bo/
  reviews/
```

If Railway bucket count, pricing, or product limits make two buckets awkward, fallback to one bucket with hard workspace prefixes:

```text
s3://mirai-demo-artifacts/workspaces/fraunhofer/...
s3://mirai-demo-artifacts/workspaces/battery-demo/...
```

But the preferred demo posture is two buckets because it makes the isolation story easier to inspect and reason about.

### 4. UI/admin access without Kubernetes

We still want to inspect what's happening.

Use these options in priority order:

1. Mirai-native artifact/model/run browser.
   - Shows workspace/project metadata, artifact presence, model status, ONNX paths, MLflow run/model-quality summaries.
   - Best long-term product fit.
2. Optional MLflow UI Railway service.
   - Uses Railway Postgres as tracking backend and object storage as artifact root.
   - Protect with Clerk, basic auth, private networking, or temporary demo credentials.
3. Postgres inspection.
   - Prefer local TablePlus/DBeaver/psql through Railway connection details.
   - Optional temporary pgAdmin/Adminer/pgweb service only if needed.
4. Object storage inspection.
   - Prefer S3-compatible tools: `mc`, Cyberduck, DBeaver S3 browser, or CLI scripts.
   - Optional object-browser UI later.

Do not require Kubernetes just to open these UIs.

## Dependency Graph

```text
Naming + storage contract
  -> DB migrations/seeds
      -> workspace/project/artifact pointer APIs
          -> storage resolver
              -> MLflow/ONNX/model resolution
                  -> frontend visibility
                      -> demo signup flows

Railway resources
  -> env vars/secrets
      -> app runtime stateful mode
          -> smoke tests
              -> Clerk required auth
```

## Agent, Skill, and Subagent Routing Map

This repo currently has project-local Clerk/Railway/domain skills and global general-engineering skills. The available executable subagents are builtin only: `scout`, `planner`, `worker`, `reviewer`, `researcher`, `context-builder`, `oracle`, and `delegate`. There are no project/user custom subagents or saved chains at the time this plan was written.

### Inventory summary

**Project-local skills to prefer for this plan:**

- `use-railway`: Railway projects, services, Postgres, buckets, variables, deployments, logs, Railway MCP/CLI workflows.
- `clerk-cli`, `clerk-backend-api`, `clerk-orgs`, `clerk-react-patterns`, `clerk-custom-ui`, `clerk-testing`, `clerk-webhooks`, `clerk-setup`: Clerk production auth, org/workspace mapping, React auth UX, API verification, and auth-flow tests.
- `surrogate-model-debugging`: MLflow, preprocessing, ONNX inference, model registry, model quality, feature pipelines.
- `bayesian-optimization-feature`: BO state, observations, candidate suggestions, optimization UI/API.
- `scientific-ui-clarity`: scientist-facing model/artifact/BO visibility screens.
- `project-artifact-cleanup`: cleanup of generated runtime artifacts, MLflow runs/models, BO/session/review files.
- `github-mcp-workflow`: only when explicitly asked to use GitHub branches/PRs/issues/releases/remote compares.

**Most relevant global skills:**

- `planning-and-task-breakdown`: refining or splitting this plan before implementation.
- `test-driven-development`: storage resolver, auth, API, MLflow/ONNX, and tenant-separation behavior.
- `security-and-hardening`: Clerk auth, bucket credentials, tenant isolation, admin/debug UI exposure, secrets handling.
- `api-and-interface-design`: DB/API/frontend contracts for artifact pointers, workspace storage, and status endpoints.
- `source-driven-development`: verify Railway, Clerk, MLflow, S3/bucket, and Kubernetes/kind claims against official docs.
- `debugging-and-error-recovery`: failed Railway deploys, failing tests, broken artifact/model resolution.
- `frontend-ui-engineering`: React implementation work.
- `browser-testing-with-devtools`: real browser verification of sign-in, project visibility, and artifact/model screens.
- `ci-cd-and-automation`: deployment validation, smoke checks, and eventual CI quality gates.
- `shipping-and-launch`: pre-demo/redeploy checklist, rollback, smoke tests, stakeholder handoff.
- `documentation-and-adrs`: decision records for Level 2/Level 3 boundary and storage architecture.
- `incremental-implementation`: keep each phase small and verifiable.
- `code-review-and-quality`, `doubt-driven-development`, `code-simplification`: review before staging/merge and after broad changes.
- `git-workflow-and-versioning`: staging/commit grouping and dirty-worktree hygiene.

### Subagent usage patterns

- Use `scout` before tasks that require reading several files, especially Tasks 6-12 and 15-17.
- Use `planner` after scout when the next step touches multiple subsystems or needs sequencing.
- Use `worker` only after scope is approved and acceptance criteria are clear; one writer at a time.
- Use fresh-context `reviewer` after implementation for correctness, security, tests, and maintainability.
- Use `researcher` only when current external docs matter, especially Railway bucket/MCP behavior, Clerk production config, MLflow S3 backend behavior, or kind/Kubernetes references.
- Use `context-builder` for large handoffs across auth/storage/model/UI boundaries.
- Use `oracle` for architecture/security decision review when a task could change Level 2/Level 3 boundaries.
- Use `delegate` only for small isolated read-only questions.

### Task-to-agent/skill map

| Plan task(s) | Primary skills | Suggested subagent chain | Notes |
|---|---|---|---|
| Tasks 1-3: architecture contract, IDs, object layout | `documentation-and-adrs`, `planning-and-task-breakdown`, `source-driven-development`, `use-railway` | `scout -> planner` | Scout current docs/config and CAI references; planner updates the architecture contract. Add `researcher` only if Railway bucket details need fresh docs. |
| Tasks 4-5: Railway buckets/env contract | `use-railway`, `security-and-hardening`, `source-driven-development`, `ci-cd-and-automation` | `scout -> planner/worker -> reviewer` | Use repo-local lazy Railway MCP or Railway CLI only after restarting Pi. Never print secrets; record names/status only. |
| Tasks 6 and 8: DB seeds, migrations, artifact pointers | `api-and-interface-design`, `test-driven-development`, `security-and-hardening`, `incremental-implementation` | `scout -> planner -> worker -> reviewer` | Scout existing migrations, seeds, registries, and tests first. Reviewer should focus on RLS/workspace leakage and migration safety. |
| Task 7: bucket-aware workspace storage | `test-driven-development`, `security-and-hardening`, `api-and-interface-design`, `debugging-and-error-recovery` | `scout -> planner -> worker` plus fresh `reviewer` | Start with tests for wrong-bucket, wrong-prefix, `..` escapes, and local-mode compatibility. |
| Tasks 9-10: MLflow and ONNX durable resolution | `surrogate-model-debugging`, `test-driven-development`, `source-driven-development`, `debugging-and-error-recovery` | `scout -> researcher? -> planner -> worker -> reviewer` | Use `researcher` only if MLflow S3/Postgres behavior or ONNX runtime behavior is unclear. Preserve generic lifecycle semantics. |
| Task 11: artifact bootstrap script | `project-artifact-cleanup`, `security-and-hardening`, `test-driven-development`, `use-railway` | `scout -> planner -> worker -> reviewer` | Require dry-run, env-only credentials, no wholesale intake upload, and secret-safe logs. |
| Task 12: Mirai-native artifact/model UI | `frontend-ui-engineering`, `scientific-ui-clarity`, `api-and-interface-design`, `browser-testing-with-devtools` | `scout -> planner -> worker -> reviewer` | Add browser/devtools validation after build. Use scientific clarity for labels and model-quality status explanation. |
| Tasks 13-14: optional MLflow/Postgres/object browser decision | `security-and-hardening`, `shipping-and-launch`, `use-railway`, `documentation-and-adrs` | `scout -> oracle/planner` | Use `oracle` for the exposure/security tradeoff before adding any public admin/debug UI. |
| Tasks 15-16: Clerk production mapping and tenant tests | `clerk-cli`, `clerk-backend-api`, `clerk-orgs`, `clerk-react-patterns`, `clerk-testing`, `security-and-hardening`, `test-driven-development` | `scout -> planner -> worker -> reviewer` | Clerk skills are repo-local; restart Pi first if not visible. Verify unauthenticated `401` and cross-workspace denial. |
| Tasks involving BO state | `bayesian-optimization-feature`, `scientific-ui-clarity`, `test-driven-development` | `scout -> worker -> reviewer` | Use whenever BO observations/state, candidates, acquisition logic, or BO UI/API are touched. |
| Task 17: remove image-bundled mutable state | `use-railway`, `project-artifact-cleanup`, `ci-cd-and-automation`, `shipping-and-launch` | `scout -> planner -> worker -> reviewer` | Do not remove image copies until durable bucket-backed resolution is verified. |
| Task 18: redeploy and smoke test | `use-railway`, `shipping-and-launch`, `debugging-and-error-recovery`, `browser-testing-with-devtools` | `worker` for deploy commands, `reviewer` for post-deploy validation | Poll Railway deployment until terminal `SUCCESS`; do not claim success from queued builds. |
| Any broad implementation batch | `incremental-implementation`, `code-review-and-quality`, `doubt-driven-development`, `git-workflow-and-versioning` | `scout -> planner -> worker -> parallel reviewers -> fix worker` | Keep implementation single-writer; parallelize only read-only review/validation. |
| Cleanup/staging/commit prep | `git-workflow-and-versioning`, `code-review-and-quality`, `project-artifact-cleanup` | `scout -> reviewer` | Stage only intended files; keep env/data/runtime artifacts ignored. |

## Task List

### Phase 1: Architecture contract and documentation

#### Task 1: Record the Level 2 runtime decision

**Description:** Update deployment docs to state that Railway Level 2 uses Railway-native app/Postgres/object-storage services and explicitly defers `kind` to local development or Level 3 preparation.

**Acceptance criteria:**
- [ ] `docs/railway-level-2-pilot.md` explains why `kind` is not part of the Railway runtime.
- [ ] The doc says Railway provides the needed Postgres and S3-compatible storage primitives.
- [ ] Level 2 vs Level 3 boundaries are clear.

**Verification:**
- [ ] Manual review of the doc.

**Dependencies:** None.

**Files likely touched:**
- `docs/railway-level-2-pilot.md`
- optionally `RAILWAY_CLERK_DEPLOYMENT_HANDOFF.md`

**Estimated scope:** S.

#### Task 2: Define canonical workspace/project IDs

**Description:** Choose stable IDs for the two demo workspaces and projects.

**Proposed IDs:**

```text
Workspace: fraunhofer
Project: pem_fuel_cell_real_cathode_degradation
Bucket: mirai-fuel-cells-demo

Workspace: battery-demo
Project: battery_tabular_doe_demo
Bucket: mirai-batteries-demo
```

**Acceptance criteria:**
- [ ] IDs are documented.
- [ ] IDs are valid for DB rows, object prefixes, URLs, and Clerk workspace mapping.
- [ ] The battery demo dataset source is identified or marked as an explicit open question.

**Verification:**
- [ ] Manual review with user.

**Dependencies:** Task 1.

**Files likely touched:**
- `docs/railway-level-2-pilot.md`
- `plans/to-implement/railway-stateful-cai-pattern-plan.md` if IDs change.

**Estimated scope:** XS.

#### Task 3: Document object layout and artifact classes

**Description:** Document the S3-compatible object layout for datasets, canonical tables, preprocessing artifacts, MLflow artifacts, ONNX models, BO data, and reviews.

**Acceptance criteria:**
- [ ] Fuel-cell and battery object layouts are documented.
- [ ] The layout separates workspace and project.
- [ ] The layout avoids unscoped global artifact paths.
- [ ] The layout maps to future Kubernetes/IAM isolation.

**Verification:**
- [ ] Manual review of path examples.

**Dependencies:** Task 2.

**Files likely touched:**
- `docs/railway-level-2-pilot.md`
- `deployments/railway/README.md`

**Estimated scope:** S.

### Checkpoint: Architecture contract

- [ ] User confirms the Level 2 architecture.
- [ ] User confirms workspace/project/bucket names.
- [ ] Battery demo source dataset is confirmed or explicitly deferred.

---

### Phase 2: Railway resources and env contract

#### Task 4: Create or verify Railway buckets

**Description:** Create/verify Railway object storage buckets for the two demos.

**Acceptance criteria:**
- [ ] Bucket exists for fuel-cell artifacts.
- [ ] Bucket exists for battery artifacts.
- [ ] Bucket credentials are stored only in Railway variables or ignored local env files.
- [ ] No bucket secrets are committed or printed in docs.

**Verification:**
- [ ] `railway bucket list --json` or Railway dashboard confirms buckets.
- [ ] A non-secret summary records bucket names and service IDs if available.

**Dependencies:** Task 2.

**Files likely touched:**
- docs only, if recording non-secret setup notes.

**Estimated scope:** S.

#### Task 5: Define Railway env var contract

**Description:** Define the environment variables that map Mirai workspaces to buckets and Postgres.

**Candidate variables:**

```text
DATABASE_URL=...
MIRAI_STORAGE_BACKEND=s3
MIRAI_WORKSPACE_BUCKET_MAP={"fraunhofer":"mirai-fuel-cells-demo","battery-demo":"mirai-batteries-demo"}
MIRAI_S3_ENDPOINT=...
MIRAI_S3_REGION=...
MIRAI_S3_ACCESS_KEY_ID=...
MIRAI_S3_SECRET_ACCESS_KEY=...
MLFLOW_TRACKING_URI=...
MLFLOW_ARTIFACT_ROOT=...
CLERK_AUTH_REQUIRED=true
CLERK_DEFAULT_WORKSPACE_ID=fraunhofer   # only for local/dev or controlled fallback, not real production auth
```

Exact names can change to match existing code conventions.

**Acceptance criteria:**
- [ ] Env var names are documented.
- [ ] Secrets are separated from non-secrets.
- [ ] Production-required auth variables are documented.
- [ ] Local dev fallback remains possible without changing code.

**Verification:**
- [ ] Manual review.
- [ ] `railway variables` can be checked without exposing values.

**Dependencies:** Task 4.

**Files likely touched:**
- `docs/railway-level-2-pilot.md`
- `deployments/railway/README.md`
- maybe `.env.example` if such a pattern exists.

**Estimated scope:** S.

### Checkpoint: Railway resource contract

- [ ] Railway app, Postgres, and buckets are visible in dashboard.
- [ ] Env var contract is approved.
- [ ] No secrets are in Git.

---

### Phase 3: DB and storage model

#### Task 6: Extend/control seed data for two demo workspaces

**Description:** Seed two demo workspaces/projects in the control-plane DB. The PEM/fuel-cell project should remain an adapter into the generic lifecycle; the battery project should use the generic tabular DoE path directly.

**Acceptance criteria:**
- [ ] DB seed has `fraunhofer` workspace and fuel-cell project.
- [ ] DB seed has `battery-demo` workspace and battery project.
- [ ] Rows include storage bucket/prefix metadata or artifact pointer conventions.
- [ ] No project points to a local filesystem-only runtime path in Railway mode.

**Verification:**
- [ ] `cd backend && uv run pytest -q` passes.
- [ ] Direct seed review confirms two workspaces/projects.

**Dependencies:** Tasks 2-5.

**Files likely touched:**
- `backend/db/seeds/001_seed_demo_control_plane.sql`
- `backend/db/migrations/001_workspace_control_plane.sql` if schema adjustments are needed.

**Estimated scope:** M.

#### Task 7: Make workspace storage bucket-aware

**Description:** Extend the storage resolver so it can validate and resolve S3-compatible object URIs by workspace/project, while preserving local filesystem mode for development and tests.

**Acceptance criteria:**
- [ ] Storage resolver supports local and S3 modes.
- [ ] Workspace/project bucket mapping is explicit.
- [ ] Cross-workspace bucket/prefix access is rejected.
- [ ] `..` path escapes and unscoped absolute paths are rejected.
- [ ] Tests cover fuel-cell and battery bucket separation.

**Verification:**
- [ ] `cd backend && uv run pytest -q backend/tests/test_workspace_storage.py`
- [ ] Full backend tests pass.

**Dependencies:** Task 6.

**Files likely touched:**
- `backend/app/services/workspace_storage.py`
- `backend/tests/test_workspace_storage.py`

**Estimated scope:** M.

#### Task 8: Persist artifact pointers as durable metadata

**Description:** Ensure project artifacts are represented as durable object pointers in Postgres/control-plane metadata rather than implicit paths inside the app image.

**Acceptance criteria:**
- [ ] Artifact metadata can represent datasets, preprocessing outputs, MLflow artifacts, ONNX models, BO files, and review files.
- [ ] Pointers are workspace/project-scoped.
- [ ] App can resolve artifact pointers after container restart.
- [ ] Runtime does not depend on `backend/mlruns/` copied into image.

**Verification:**
- [ ] Backend tests for artifact pointer validation.
- [ ] Manual smoke: restart local container and resolve model/schema metadata.

**Dependencies:** Task 7.

**Files likely touched:**
- `backend/db/migrations/001_workspace_control_plane.sql`
- `backend/db/seeds/001_seed_demo_control_plane.sql`
- `backend/app/services/workspace_storage.py`
- model/project registry services as needed.

**Estimated scope:** M.

### Checkpoint: Durable storage foundation

- [ ] Backend tests pass.
- [ ] Two workspaces/projects exist in seed/control plane.
- [ ] Storage resolver rejects cross-workspace access.
- [ ] Artifact pointers are not local-image assumptions.

---

### Phase 4: MLflow and ONNX resolution

#### Task 9: Map MLflow metadata/artifacts to Railway storage

**Description:** Apply CAI's MLflow architecture pattern: tracking metadata in Postgres and artifacts in S3-compatible object storage. Decide whether first implementation uses a full MLflow tracking server, direct MLflow APIs, or Mirai-managed artifact pointers with optional MLflow UI later.

**Acceptance criteria:**
- [ ] MLflow backend/artifact strategy is documented.
- [ ] Existing model registry code can resolve durable artifacts.
- [ ] `model-quality/summary` behavior is understood and fixed or explicitly documented as unavailable until training/bootstrap.
- [ ] No MLflow state is lost on app redeploy.

**Verification:**
- [ ] Backend tests for model/artifact resolution.
- [ ] Railway smoke after redeploy.

**Dependencies:** Task 8.

**Files likely touched:**
- `backend/app/services/mlflow_registry.py`
- `backend/ml_lifecycle/entrypoints/mlflow_utils.py`
- `backend/tests/test_api.py`
- docs.

**Estimated scope:** M.

#### Task 10: Resolve ONNX models from object storage

**Description:** Ensure inference-serving code can resolve ONNX model objects from the correct bucket/prefix for the active workspace/project.

**Acceptance criteria:**
- [ ] ONNX path resolution uses workspace/project metadata.
- [ ] Fuel-cell user cannot resolve battery ONNX model.
- [ ] Battery user cannot resolve fuel-cell ONNX model.
- [ ] Local dev still supports local artifact paths.

**Verification:**
- [ ] Focused backend tests.
- [ ] Manual smoke with both projects.

**Dependencies:** Tasks 7-9.

**Files likely touched:**
- `backend/app/services/mlflow_registry.py`
- inference/model-serving services.
- backend tests.

**Estimated scope:** M.

#### Task 11: Add artifact bootstrap script

**Description:** Add a repeatable script to upload approved demo artifacts to the correct bucket/prefix and verify matching Postgres/control-plane pointers.

**Acceptance criteria:**
- [ ] Script reads credentials from env only.
- [ ] Script supports dry-run mode.
- [ ] Script can bootstrap fuel-cell artifacts.
- [ ] Script can bootstrap battery artifacts once the battery dataset/model is available.
- [ ] Script does not upload `backend/data-minio/intake` wholesale.

**Verification:**
- [ ] Dry-run output lists intended objects without secrets.
- [ ] Optional real upload verified by object listing.

**Dependencies:** Tasks 4, 8, 10.

**Files likely touched:**
- `scripts/bootstrap_demo_artifacts.py` or similar.
- docs.

**Estimated scope:** M.

### Checkpoint: Model/artifact resolution

- [ ] Fuel-cell model/schema/BO endpoints resolve from durable state.
- [ ] Battery project appears and resolves its durable metadata, if data is ready.
- [ ] Container restart does not lose model availability.

---

### Phase 5: UI visibility without Kubernetes

#### Task 12: Add Mirai-native artifact/model visibility

**Description:** Add or improve a Mirai UI/API surface so demo users can see project state without needing raw MinIO/Postgres/MLflow access.

**Possible visible fields:**

- Dataset uploaded/present.
- Canonical tables present.
- Preprocessing artifact present.
- MLflow run ID / model version.
- ONNX model present.
- Model quality summary status.
- BO state status.
- Last updated timestamp.

**Acceptance criteria:**
- [ ] Signed-in fuel-cell user can inspect fuel-cell project state.
- [ ] Signed-in battery user can inspect battery project state.
- [ ] Cross-workspace metadata is not visible.
- [ ] Missing model-quality data is explained clearly.

**Verification:**
- [ ] Frontend build passes.
- [ ] Backend tests pass.
- [ ] Manual browser smoke.

**Dependencies:** Tasks 8-10.

**Files likely touched:**
- backend API routers/services.
- `frontend/src/*`.
- backend/frontend tests if present.

**Estimated scope:** M.

#### Task 13: Decide on optional MLflow UI service

**Description:** Decide whether a stock MLflow UI is needed for the demo, or whether Mirai-native visibility is enough initially.

**Acceptance criteria:**
- [ ] Decision is documented.
- [ ] If yes, service topology and auth protection are documented before implementation.
- [ ] If no, Mirai-native visibility covers the demo need.

**Verification:**
- [ ] Manual review.

**Dependencies:** Task 12.

**Files likely touched:**
- `docs/railway-level-2-pilot.md`
- maybe `deployments/railway/README.md`.

**Estimated scope:** XS/S.

#### Task 14: Decide on optional Postgres/object browser access

**Description:** Define how the developer/demo operator opens Postgres and bucket contents safely without Kubernetes.

**Recommended default:**

- Postgres: local TablePlus/DBeaver/psql using Railway connection details.
- Buckets: `mc`, Cyberduck, DBeaver S3, or script-generated object summaries.
- Temporary admin UI services only when explicitly needed.

**Acceptance criteria:**
- [ ] Operator workflow is documented.
- [ ] No public unauthenticated admin UI is introduced.
- [ ] Any temporary UI service has a removal/disable step.

**Verification:**
- [ ] Manual review.

**Dependencies:** Task 4.

**Files likely touched:**
- `docs/railway-level-2-pilot.md`
- `deployments/railway/README.md`.

**Estimated scope:** S.

### Checkpoint: Observability and demos

- [ ] User can inspect state from Mirai UI and/or approved external UI.
- [ ] Operator can inspect Postgres/buckets safely.
- [ ] No Kubernetes dependency exists for Level 2 visibility.

---

### Phase 6: Clerk and two-signup demo isolation

#### Task 15: Configure Clerk production workspace mapping

**Description:** Configure Clerk so two demo signups/users/orgs map cleanly to the two Mirai workspaces.

**Acceptance criteria:**
- [ ] Production Clerk keys are configured on Railway.
- [ ] `CLERK_AUTH_REQUIRED=true` is enabled only after verification.
- [ ] Fuel-cell demo identity maps to `fraunhofer`.
- [ ] Battery demo identity maps to `battery-demo`.
- [ ] Default workspace fallback is disabled or safe in production.

**Verification:**
- [ ] Unauthenticated protected APIs return `401`.
- [ ] Fuel-cell user can access only fuel-cell project.
- [ ] Battery user can access only battery project.

**Dependencies:** Tasks 6-8.

**Files likely touched:**
- `backend/app/auth.py`
- `frontend/src/main.tsx`
- `frontend/src/lib/api.ts`
- docs.

**Estimated scope:** M.

#### Task 16: Add tenant-separation tests

**Description:** Add backend tests that fail if a user/workspace can resolve or read another workspace's project/artifacts.

**Acceptance criteria:**
- [ ] API denies cross-workspace project access.
- [ ] Storage resolver denies wrong-bucket/wrong-prefix access.
- [ ] Tests include both fuel-cell and battery workspaces.

**Verification:**
- [ ] `cd backend && uv run pytest -q`

**Dependencies:** Tasks 7, 15.

**Files likely touched:**
- `backend/tests/test_api.py`
- `backend/tests/test_workspace_storage.py`

**Estimated scope:** M.

### Checkpoint: Level 2 demo-ready auth

- [ ] Clerk required auth is enabled in Railway.
- [ ] Two demo signups can be tested independently.
- [ ] Cross-workspace access fails closed.

---

### Phase 7: Remove image-bundled mutable state

#### Task 17: Stop copying mutable artifacts into Railway image

**Description:** Once bucket-backed resolution works, remove reliance on copying local MLflow/data/workspace runtime directories into the Railway image.

**Acceptance criteria:**
- [ ] `Dockerfile.railway` does not copy mutable demo runtime state.
- [ ] `.railwayignore` excludes local runtime/generated data.
- [ ] Fresh deploy can resolve demo state from Postgres + buckets.

**Verification:**
- [ ] `docker build -f Dockerfile.railway -t mirai-doe-railway .`
- [ ] Railway deploy succeeds.
- [ ] Smoke endpoints pass after redeploy.

**Dependencies:** Tasks 8-11.

**Files likely touched:**
- `Dockerfile.railway`
- `.railwayignore`
- docs.

**Estimated scope:** S/M.

#### Task 18: Railway redeploy and smoke test

**Description:** Redeploy the stateful Level 2 version and verify core endpoints and demo paths.

**Acceptance criteria:**
- [ ] Railway deployment reaches `SUCCESS`.
- [ ] `/` serves SPA.
- [ ] `/health` and `/api/health` pass.
- [ ] Protected APIs require auth.
- [ ] Fuel-cell project resolves schema/model/BO state.
- [ ] Battery project resolves its configured state.
- [ ] FastAPI docs remain disabled unless explicitly enabled.

**Verification:**
- [ ] `railway deployment list --json`
- [ ] `curl` smoke tests.
- [ ] Browser smoke tests with both demo identities.

**Dependencies:** Tasks 15-17.

**Files likely touched:**
- none unless fixing issues.

**Estimated scope:** M.

### Final checkpoint: Level 2 demo acceptance

- [ ] Two demo signups work.
- [ ] Two workspaces/projects are isolated.
- [ ] Durable artifacts survive redeploy/restart.
- [ ] Operator can inspect Postgres/object/artifact state safely.
- [ ] No secrets or generated data are committed.
- [ ] Docs explain Level 2 and Level 3 path honestly.

---

## Level 3 Migration Path

When moving beyond Level 2:

```text
Railway app service
  -> Kubernetes Deployment + Ingress

Railway Postgres
  -> Managed Postgres with per-tenant DB/schema/RLS, or dedicated DB per client

Railway buckets
  -> Cloud S3/GCS/Azure buckets with per-tenant IAM/service accounts

Workspace ID / Clerk claims
  -> Namespace, service-account, IAM, and network-policy boundaries

Railway variables
  -> Kubernetes Secrets / External Secrets

Optional Railway MLflow UI service
  -> Namespace-scoped MLflow service behind SSO/network policy
```

Stable concepts that should not change:

- Generic tabular DoE lifecycle.
- PEM adapter as an intake adapter only.
- Workspace/project metadata model.
- Object layout under workspace/project prefixes.
- Artifact pointer validation.
- Clerk/workspace authorization model.

Concepts that become stronger in Level 3:

- Runtime isolation.
- Network isolation.
- Secret separation.
- Per-tenant IAM.
- Dedicated admin/observability surfaces.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---:|---|
| Railway bucket feature limits differ from expected S3 semantics | High | Verify bucket credentials, endpoints, object limits, and multi-bucket behavior before coding deep integrations. |
| MLflow UI adds auth/networking complexity | Medium | Start with Mirai-native artifact visibility; add MLflow UI only if needed. |
| Current app depends on image-bundled artifacts | High | Move resolution to Postgres + buckets before removing image copies. |
| Battery demo data/model is not yet defined | Medium | Treat battery project as generic lifecycle; confirm dataset/model before final seed. |
| Auth fallback remains enabled too long | High | Keep `CLERK_AUTH_REQUIRED=false` only for smoke tests; require auth before demo signups. |
| Cross-workspace artifact access bug | High | Add resolver and API tests that fail on wrong bucket/prefix access. |
| Overengineering with unused k8s manifests | Medium | Keep only placeholder folders until Level 3 is active. |
| Secrets leak through docs or logs | High | Use presence checks and variable names only; never print credential values. |

## Open Questions

1. What is the exact battery demo dataset and target column?
2. Should the battery demo have pre-trained ONNX/MLflow artifacts initially, or should it train during bootstrap?
3. Does Railway's current object storage product support the exact two-bucket setup desired in the target account/workspace?
4. Is stock MLflow UI required for demos, or is Mirai-native run/model visibility enough for Level 2?
5. Do the two demo signups map to two Clerk users, two Clerk organizations, or one organization with roles?
6. Should Postgres admin UI be a temporary Railway service, or should inspection stay local-only via DBeaver/TablePlus/psql?

## Suggested Implementation Order

1. Review and approve this plan.
2. Confirm battery dataset/model source.
3. Verify Railway buckets and env var shape.
4. Update docs with the Level 2 architecture decision.
5. Implement seed/control-plane changes for two workspaces.
6. Add bucket-aware storage resolver tests.
7. Implement bucket-aware resolver.
8. Add durable artifact pointers and bootstrap script.
9. Wire MLflow/ONNX resolution to durable state.
10. Add Mirai-native artifact/model visibility.
11. Enable Clerk production auth and test two demo identities.
12. Remove image-bundled mutable state from Railway deployment.
13. Redeploy and complete smoke tests.

## Validation Command Set

Backend:

```bash
cd backend
uv run pytest -q
```

Frontend:

```bash
cd frontend
npm run build
```

Railway image:

```bash
docker build -f Dockerfile.railway -t mirai-doe-railway .
```

Railway smoke:

```bash
BASE=https://mirai-doe-production.up.railway.app
curl -sS -L "$BASE/health"
curl -sS -L "$BASE/api/health"
curl -sS -L -o /tmp/mirai-root.html -w '%{http_code}\n' "$BASE/"
```

Auth smoke after Clerk production setup:

```bash
curl -sS -i "$BASE/projects"
# expected: 401 without token when CLERK_AUTH_REQUIRED=true
```

## Files/Folders Created for Deployment Shape

```text
deployments/railway/README.md
deployments/local-kind/README.md
deployments/k8s/README.md
plans/to-implement/railway-stateful-cai-pattern-plan.md
```

These are placeholders/docs only. They do not introduce Kubernetes as an active deployment path.
