# Mirai Railway Tenancy and Storage Hard-Reset Cutover Plan

## Context

Implement a clean, secure tenancy and storage cutover for the Mirai DoE Railway demo. The approved strategy is a **hard reset of application-level demo state**, not a compatibility migration. It is acceptable to lose current Railway demo records and relevant demo objects when needed for a simpler, faster validation path.

Non-negotiable boundaries:

- Do not delete Railway services, the Postgres service/database itself, the Railway bucket resource, credentials, domains, deployments, Railway project configuration, source code, or Git history.
- Do not expose secrets; environment audits may show variable names only.
- Do not preserve Clerk-user-derived tenancy behavior.
- Do not implement old-prefix read fallback, old object copying/moving, MLflow URI rewriting, or generic try-old-workspace-prefix logic.

Target production model:

```text
Clerk user A -> explicit Postgres membership -> Fraunhofer workspace -> Fraunhofer projects -> mirai-fuel-cells-demo storage
Clerk user B -> authenticated -> no workspace membership -> setup-required state -> no project/upload/train/predict/Fraunhofer access
```

Canonical live workspace:

```text
workspace_id: fraunhofer
display_name: Fraunhofer
storage.mode: s3
storage.bucket: mirai-fuel-cells-demo
storage.prefix: workspaces/fraunhofer
```

## Agent and skill mapping

### Configured agents / subagents

The current Plannotator planning toolset does not expose the `subagent` management tool, so configured agents/chains cannot be listed during this planning pass. Before implementation, follow `AGENTS.md`: list configured agents/chains, run a read-only scout-style agent if available, then use focused implementation/review agents only if they are actually configured.

Recommended meaningful handoff if available:

- **Read-only scout/audit agent**: verify current auth/storage/reset touchpoints and produce a route/table inventory before edits.
- **Backend implementation agent**: implement membership resolver, route guards, storage failure behavior, reset command, and tests.
- **Frontend implementation agent**: implement setup-required UX for no workspace membership without exposing storage details.
- **Reviewer/security agent**: review for auth bypasses, production-only test auth leakage, secret exposure, and destructive reset safety.
- **Railway/deployment agent**: prepare validation runbook commands and env-name-only inspection; do not run destructive reset without explicit approval.

### Local skills

- `.pi/skills/use-railway`: Railway-safe deploy, env-name inspection, `railway run`, and validation runbook. Use only with secret-redaction discipline.
- `.pi/skills/repo-postgres-migrations`: DB schema/seed/reset SQL design, transactions, idempotency, and Postgres verification queries.
- `.pi/skills/clerk-backend-api`: Clerk JWT semantics and backend auth guard behavior; ensure Clerk `sub` identifies user only.
- `.pi/skills/clerk-testing`: auth fixtures for user A/user B, test-only tokens, and production guardrails.
- `.pi/skills/clerk-react-patterns`: frontend handling of authenticated no-workspace state.
- `.pi/skills/project-artifact-cleanup`: destructive application-object cleanup safeguards and reporting.
- `.pi/skills/scientific-ui-clarity`: keep setup-required and training/model states understandable to demo users.
- `.pi/skills/surrogate-model-debugging`: training artifact failure states and model-quality validation.
- `.pi/skills/github-mcp-workflow`: only if GitHub issue/PR workflow is used; not needed for core implementation.

### Global skills

- `security-and-hardening`: fail-closed auth/storage behavior, no secrets in frontend/logs, no local fallback in production.
- `test-driven-development`: add regression tests before/alongside auth/storage/reset changes.
- `incremental-implementation`: land backend guards, reset script, frontend UX, docs, and validation in reviewable chunks.
- `code-review-and-quality`: route coverage review, ownership validation, and destructive-script safety review.
- `ci-cd-and-automation`: Railway runbook and deployment validation steps.
- `documentation-and-adrs`: update env contract, reset runbook, and rollback steps.
- `frontend-ui-engineering`: React/Vite setup-required state and disabled actions.
- `debugging-and-error-recovery`: partial reset/object-delete failure reporting and training artifact failure recovery.
- `shipping-and-launch`: staged deploy/reset/smoke-test process.

## Current code findings to account for

- `backend/app/auth.py` currently derives a workspace from Clerk JWT `sub` via `_workspace_from_subject()` / `_workspace_from_claims()`. This must stop being the production tenancy source.
- `backend/app/main.py::require_clerk_auth()` currently requires `principal_workspace_id()` and path-guards only project ids from URL patterns. It must use membership resolution and return explicit no-membership / multi-workspace states.
- `backend/app/main.py` exposes many route families that need consistent ownership validation: project listing/details, intake, preprocessing, training, prediction, recommendation, BO, design studio/export, impact, model-quality, and artifact status.
- `backend/app/services/control_plane.py` already has workspace/project/storage helpers (`get_workspace_summary`, `list_workspace_projects`, `ensure_project_record`, `get_project_storage_config`, runtime-state functions), but it also has synthetic workspace behavior and workspace auto-creation paths that must not activate for normal authenticated users without membership.
- `backend/app/services/data_intake.py` still contains heuristic/local workspace inference (`_project_workspace_id()`) and local metadata/session paths. Railway production must resolve workspace from auth membership and Postgres, not project-name or Clerk-sub heuristics.
- `backend/app/services/workspace_storage.py` supports generic S3 envs and validates workspace prefixes, but `object_storage_backend()` defaults to `local`. Railway/production must fail closed if `OBJECT_STORAGE_BACKEND=s3` and generic S3 credentials/storage assignment are not present.
- `scripts/` currently only has `bootstrap_demo_artifacts.py`; add a clearly destructive operator script such as `scripts/reset_demo_application_data.py`.

## Approach

Build a canonical membership-based tenancy path and intentionally reset old demo app state instead of preserving compatibility.

1. Introduce a backend membership resolver that maps verified Clerk `sub` to rows in `clerk_user_workspaces`.
2. Represent request tenancy as one of: exactly one workspace, no membership, or multiple memberships requiring selection.
3. Make no-membership a first-class account state for safe read endpoints and a 403 for all state-changing/project-scoped endpoints.
4. Require all project/dataset/session/artifact/model/training references to be validated through membership -> workspace -> owning row.
5. Make storage resolution exclusively Postgres-driven from `workspaces.storage` / project storage, with S3 mandatory and local fallback disabled in Railway/production.
6. Add an explicit destructive-but-bounded reset script that retains/recreates only Fraunhofer and user A membership, removes stale app-level demo records, deletes only approved prefixes inside the existing bucket, and leaves MLflow infrastructure untouched unless safely scoped.
7. Update frontend to show a clear setup-required state for user B and prevent creation/upload/train/predict affordances.
8. Add tests for auth, route ownership, storage key generation, failure behavior, reset safety, and clean ingestion.
9. Update docs/env examples and provide a Railway validation runbook; do not run the destructive reset automatically.

## Files to modify

### Backend auth and route guards

- `backend/app/auth.py`
- `backend/app/main.py`
- `backend/app/schemas.py` if account-status response schemas need to be formalized
- `backend/app/services/control_plane.py`
- `backend/app/services/db.py` if helper transaction/session utilities are needed

### Intake, storage, training, and artifacts

- `backend/app/services/data_intake.py`
- `backend/app/services/workspace_storage.py`
- `backend/app/services/training_requests.py`
- `backend/app/services/preprocessing_review.py`
- `backend/app/services/mlflow_registry.py`
- `backend/app/services/model_quality.py`
- `backend/app/services/project_registry.py`
- `backend/app/services/design_studio.py`
- `backend/app/services/bayesian_optimization.py`
- `backend/app/services/recommendation.py`
- Any service that accepts `project_id`, `dataset_id`, `session_id`, `artifact`, `model_id`, or `training_run_id` without ownership re-checks

### Reset / operations

- `scripts/reset_demo_application_data.py` or `backend/scripts/reset_demo_application_data.py`
- Potentially `backend/app/services/demo_reset.py` for testable reset logic
- `deployments/railway/README.md`
- `backend/RAILWAY_DEPLOYMENT.md`
- `docs/railway-level-2-pilot.md`
- `env.example`
- `backend/.env.training.example`

### Frontend

- `frontend/src/lib/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/DataIntakePage.tsx`
- `frontend/src/components/ProjectHeader.tsx`
- Other components that enable upload/train/predict/model-quality actions based on project availability
- Check `frontend/.env*` files for accidental Clerk secret/backend/S3 secrets; remove from repo-local examples if present

### Tests

- `backend/tests/test_api.py`
- `backend/tests/test_workspace_storage.py`
- `backend/tests/test_runtime_project_schema.py`
- New tests as useful, e.g. `backend/tests/test_membership_tenancy.py`, `backend/tests/test_reset_demo_application_data.py`, `backend/tests/test_storage_fail_closed.py`
- Frontend tests if existing test harness supports them; otherwise build + manual checks in runbook

## Reuse

- Reuse `AuthenticatedPrincipal` and JWT verification in `backend/app/auth.py`, but change `workspace_id` from derived identity to resolved/authorized membership context.
- Reuse `clerk_user_workspaces` schema and `workspaces.storage` JSON from existing migrations.
- Reuse `control_plane` helpers for workspace/project lookups and storage config, adding membership lookup helpers rather than duplicating SQL.
- Reuse `WorkspaceStorageConfig`, `validate_workspace_object_key`, `put_workspace_object`, `list_workspace_objects`, and generic S3 client behavior from `backend/app/services/workspace_storage.py`.
- Reuse existing audit logging, but do not let audit failures or absent workspace create synthetic workspace access.
- Reuse test fixture patterns in `backend/tests/test_api.py` and storage tests, replacing Clerk-sub-as-workspace expectations with membership fixtures.
- Reuse frontend API wrapper in `frontend/src/lib/api.ts` to normalize `account.status` and disable actions.

## Detailed implementation steps

### 1. Membership resolver and request context

- [ ] Add a backend resolver, e.g. `resolve_workspace_membership(clerk_user_id)`, that reads `clerk_user_workspaces` from Postgres.
- [ ] Return structured states:
  - `active_single_workspace` with workspace id and role;
  - `no_workspace_membership`;
  - `workspace_selection_required` for more than one membership.
- [ ] Ensure production requests never derive workspace id from Clerk `sub`, email, org, frontend input, project name, or upload attempt.
- [ ] Keep test-token fixtures available only when explicitly configured and ensure they cannot override production JWT verification accidentally.
- [ ] Update `request.state` helpers so routes can access user id, membership state, workspace id, and role.

### 2. User B no-membership behavior

- [ ] Make `GET /projects` return `200` with empty `projects`, empty `workspaces`, and the requested account object for `no_workspace_membership`.
- [ ] Make `GET /workspaces` return `200` with empty workspaces and account status.
- [ ] Make project-scoped and state-changing actions return `403` with:
  ```json
  {"code":"no_workspace_membership","detail":"Workspace membership required"}
  ```
- [ ] Ensure no DB workspace row is created as a side effect of these requests.
- [ ] Add similar fail-safe behavior for `workspace_selection_required`: do not guess a workspace or accept arbitrary client workspace id for this demo.

### 3. Route ownership validation

- [ ] Centralize ownership helpers such as `require_workspace_access(request)`, `require_project_access(request, project_id)`, and `require_session_access(request, project_id, dataset_id, session_id)`.
- [ ] Apply validation beyond URL project-id guards wherever `dataset_id`, `session_id`, `training_request_id`, artifact/model ids, or export ids are supplied.
- [ ] Cover route families: projects, intake create/append/list/get/inventory, preprocessing, reports, training, prediction/batch prediction/recommendation, BO, design studio/export, model-quality, artifact status, and scientist review.
- [ ] Return consistent 403 responses without leaking whether a Fraunhofer resource exists to unassigned/isolated users.

### 4. Canonical storage behavior

- [ ] Ensure Fraunhofer project creation/storage uses only Postgres workspace storage:
  ```text
  workspaces/fraunhofer/projects/{project_id}/...
  ```
- [ ] Generate canonical keys:
  ```text
  workspaces/fraunhofer/projects/{project_id}/raw/{dataset_id}/{safe_filename}
  workspaces/fraunhofer/projects/{project_id}/normalized/{dataset_id}/{derived_filename}
  workspaces/fraunhofer/projects/{project_id}/manifests/{dataset_id}/manifest.json
  workspaces/fraunhofer/projects/{project_id}/artifacts/{training_run_id}/{filename}
  workspaces/fraunhofer/projects/{project_id}/models/{model_version_id}/{filename}
  workspaces/fraunhofer/projects/{project_id}/exports/{export_id}/{filename}
  ```
- [ ] Adjust current intake keys, which currently include `intake/{dataset_id}/{session_id}/raw`, to the canonical layout unless a small internal session metadata path is separately justified and documented.
- [ ] Reject frontend-supplied bucket, object key, or trusted prefix; only accept domain/project/upload inputs.
- [ ] In Railway/production, require `OBJECT_STORAGE_BACKEND=s3` and fail closed if local storage would be selected silently.
- [ ] Ensure S3 upload failure does not create successful dataset/session metadata. If local staging occurs first, only mark DB success after durable S3 write succeeds.
- [ ] Ensure training artifact upload failure records an explicit recoverable failed/retryable state rather than pretending completion.

### 5. Destructive application-data reset command

- [ ] Add `reset_demo_application_data` script/command with dry-run default and required `--confirm` flag:
  ```bash
  uv run python scripts/reset_demo_application_data.py --confirm
  ```
- [ ] Before deletion, print a redacted summary only:
  - workspaces to retain;
  - memberships to retain/create;
  - projects/datasets/artifacts/training runs/models/session metadata to remove;
  - object prefixes to remove;
  - MLflow state that will remain untouched.
- [ ] Retain/recreate workspace `fraunhofer` with bucket `mirai-fuel-cells-demo` and prefix `workspaces/fraunhofer`.
- [ ] Upsert user A -> `fraunhofer`, role `owner`; accept user A id via safe env/argument and avoid printing full secret-like identifiers.
- [ ] Ensure user B has no membership; accept optional user B id for cleanup, redacted in output.
- [ ] Remove stale user-derived workspace application records and memberships.
- [ ] Remove app-level project/dataset/session/artifact/training-run/model records that depend on old Clerk-user-derived tenancy.
- [ ] Delete only approved demo prefixes in the existing bucket:
  ```text
  workspaces/fraunhofer/
  workspaces/<old-user-derived-workspace>/
  ```
  Never delete the bucket itself.
- [ ] Use one DB transaction for DB reset/upsert where possible; perform object deletion separately and report partial failure clearly.
- [ ] Leave MLflow infrastructure/unknown records untouched and document orphaned demo history if safe scoping is unavailable.

### 6. Frontend setup-required UX

- [ ] Update API types/client parsing for `account.status` and capability flags.
- [ ] Show user B a clear setup-required state:
  ```text
  Your account is active, but no client workspace has been assigned yet.
  ```
- [ ] Hide or disable create project, upload, train, predict, recommendation, export, and model-quality actions when `can_*` flags are false.
- [ ] Do not send bucket, object key, prefix, or workspace id as trusted inputs from the frontend.
- [ ] Preserve existing branding/layout and public route structure.

### 7. Tests

- [ ] User A as Fraunhofer member can list and access Fraunhofer project data.
- [ ] User B receives `no_workspace_membership` on `/projects` and `/workspaces`.
- [ ] User B cannot create a project or upload.
- [ ] User B cannot access Fraunhofer routes by changing project/dataset/session ids.
- [ ] No upload creates a workspace for an unassigned user.
- [ ] Client input cannot set bucket, prefix, or object key.
- [ ] Fresh writes use `workspaces/fraunhofer/...` canonical prefix.
- [ ] `test-client-isolated` fixture cannot access Fraunhofer data.
- [ ] Missing bucket assignment fails closed.
- [ ] S3 upload failure cannot produce false success metadata.
- [ ] Training artifact upload failure has explicit recovery status.
- [ ] Railway/production config cannot select local object storage silently.
- [ ] After reset, a clean ingestion session can be created from scratch.
- [ ] Use only `fraunhofer` and `test-client-isolated` as tenant fixtures.

### 8. Documentation and environment contract

- [ ] Update examples/docs to mark the canonical production env contract:
  ```text
  CLERK_AUTH_REQUIRED=true
  CLERK_JWT_ISSUER
  DATABASE_URL
  MIRAI_REQUIRE_POSTGRES_CONTROL_PLANE=true
  OBJECT_STORAGE_BACKEND=s3
  S3_ENDPOINT_URL
  S3_ACCESS_KEY_ID
  S3_SECRET_ACCESS_KEY
  S3_REGION
  VITE_CLERK_PUBLISHABLE_KEY
  ```
- [ ] Document optional variables separately.
- [ ] Mark these as deprecated but do not delete Railway variables yet:
  ```text
  CLERK_ISSUER
  CLERK_WORKSPACE_ID_MODE
  CLERK_DEFAULT_WORKSPACE_ID
  MIRAI_STORAGE_BACKEND
  MIRAI_WORKSPACE_BUCKET_MAP
  MIRAI_FRAUNHOFER_S3_*
  MIRAI_BATTERY_DEMO_S3_*
  MIRAI_S3_REGION
  DOE_OBJECT_STORE_ROOT
  ```
- [ ] Ensure no frontend `.env` file contains `CLERK_SECRET_KEY`, backend secrets, or S3 secrets.

## Railway validation runbook to provide with implementation

Prepare exact commands but do not execute destructive reset without explicit approval.

- [ ] Deploy code from Git branch to Railway.
- [ ] Inspect environment variable names only, not values.
- [ ] Run reset dry-run summary.
- [ ] After explicit approval, run:
  ```bash
  railway run --service mirai-doe --environment production -- uv run python scripts/reset_demo_application_data.py --confirm
  ```
- [ ] Log in as user A.
- [ ] Create a fresh project.
- [ ] Upload a fresh CSV/ZIP through the Railway UI.
- [ ] Confirm DB metadata for workspace/project/dataset/session uses `fraunhofer`.
- [ ] Confirm S3 bucket `mirai-fuel-cells-demo` and key under `workspaces/fraunhofer/projects/...`.
- [ ] Start a training request.
- [ ] Verify model/artifact state or explicit recoverable failure.
- [ ] Restart/redeploy the service.
- [ ] Verify project/session remain visible.
- [ ] Log in as user B and verify setup-required/no-access behavior.

## Verification

Recommended local verification commands after implementation:

```bash
cd backend && uv run pytest tests/test_api.py tests/test_workspace_storage.py tests/test_runtime_project_schema.py tests/test_membership_tenancy.py tests/test_reset_demo_application_data.py
npm --prefix frontend run build
git diff --cached --check
```

Railway validation should use `railway run` with variable-name-only audits and explicit reset confirmation as described above.

## Rollback plan

- Code rollback: redeploy the previous known-good commit if auth/storage regressions are found.
- DB rollback: restore from pre-reset Postgres backup/snapshot if necessary. Since the reset is intentionally destructive to app-level demo data, backup is the rollback source.
- Object rollback: deleted demo prefixes are not expected to be preserved; re-ingest demo data through the UI after rollback if needed.
- Railway infrastructure rollback: not applicable because services/database/bucket/credentials/domains/config are not deleted or recreated.
- Env rollback: no Railway variables should be deleted during this plan.

## Deliverables

- Implementation summary.
- Changed files.
- Destructive reset script and dry-run/confirmation behavior.
- Test results and exact commands.
- Railway validation runbook.
- Documentation/env updates.
- Variables intentionally left untouched.
- Known limitations, including any MLflow orphaned demo history left untouched.
- Rollback steps.

## Stop rules / blockers

Stop and report blockers instead of weakening security if any of these occur:

- Membership lookup cannot be made authoritative.
- User A's Clerk id is unavailable for explicit membership seeding.
- S3 credentials/storage assignment are missing in Railway.
- Production config would silently use local object storage.
- Reset cannot scope object deletion to the approved demo prefixes.
- Route ownership cannot be verified for dataset/session/artifact/model/training references.
- Training artifacts cannot be made durable or explicitly failed on upload error.
