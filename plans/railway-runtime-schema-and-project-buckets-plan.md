# Railway Clerk Workspace and Project-Bucket Architecture Plan

## Context

We already diagnosed and locally implemented the immediate Railway backend fix for the current UI failure:

- Railway `/projects` returns the Fraunhofer project from Postgres/control-plane runtime state.
- The UI then calls `/projects/pem_fuel_cell_real_cathode_degradation/schema` and `/artifact-status`.
- Those endpoints were still resolving through the old local/reference registry path, so Railway raised `Unknown project_id: pem_fuel_cell_real_cathode_degradation` when local reference artifacts were absent.
- The local fix makes schema/artifact-status resolution use authenticated `workspace_id + project_id` runtime state before falling back to local/reference projects.

The next plan is about the intended production model:

```text
Clerk user id = client = workspace
workspace/client -> many projects
each project -> one dedicated S3 bucket
```

This means Clerk identity must become the authoritative tenancy boundary, Postgres must store project ownership and bucket routing, backend services must resolve all object locations from that runtime metadata, and Railway logs/tests must prove the mapping works without hardcoded demo assumptions.

## Approach

Use a staged, low-risk rollout:

1. **Ship the Railway runtime schema hotfix** so the current Fraunhofer UI is unblocked.
2. **Canonicalize identity mapping from the verified Clerk session JWT** so a verified Clerk `sub` maps deterministically to exactly one workspace/client. The backend must verify signature, issuer, expiry, optional audience, and authorized party before deriving tenancy.
3. **Add project-owned storage routing** so every project row declares or resolves its own S3 bucket while remaining under the Clerk-derived workspace.
4. **Refactor artifact/data/training code paths** to use runtime project storage metadata instead of static Python maps or workspace-wide defaults.
5. **Verify with Railway read-only diagnostics and local regression tests** before any production mutations.

Keep existing public API routes unchanged unless explicitly approved.

## Files to modify

Likely code changes:

- `backend/app/auth.py`
- `backend/app/main.py`
- `backend/app/services/control_plane.py`
- `backend/app/services/project_registry.py`
- `backend/app/services/workspace_storage.py`
- `backend/app/services/mlflow_registry.py`
- `backend/app/services/data_intake.py`
- `backend/ml_lifecycle/entrypoints/train_project.py`
- `backend/db/migrations/*.sql`
- `backend/db/seeds/*.sql`
- `backend/tests/test_api.py`
- `backend/tests/test_runtime_project_schema.py`
- `backend/tests/test_workspace_storage.py`
- `backend/tests/test_mlflow_durable_pointers.py`
- `backend/tests/test_training_mlflow_contract.py`
- `backend/RAILWAY_DEPLOYMENT.md`

Possible frontend touchpoints, only if response payloads or workspace/project selection UX need adjustment:

- `frontend/src/lib/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/ProjectHeader.tsx`
- `frontend/src/components/DataIntakePage.tsx`

## Reuse

Existing implementation to reuse:

- `backend/app/auth.py`
  - JWT verification, top-level verified `workspace_id` claim parsing, and principal helpers.
- `backend/app/main.py`
  - `_authorized_workspace_id(...)`, `_request_user_id(...)`, route-level audit logging, and current schema/artifact endpoints.
- `backend/app/services/control_plane.py`
  - `list_workspace_projects(...)`, `get_workspace_project(...)`, and `get_project_runtime_state(...)` as the canonical Postgres runtime access layer.
- `backend/app/services/project_registry.py`
  - Runtime schema hotfix, local/reference fallback, uploaded-session fallback, and domain metadata attachment.
- `backend/app/services/workspace_storage.py`
  - Object-key normalization and workspace-prefix validation.
- `backend/app/services/mlflow_registry.py`
  - Existing durable artifact pointer response shape, but replace static bucket maps with runtime metadata.
- `.pi/skills/use-railway/SKILL.md`
  - Railway read-only diagnostics, logs, service/env inspection, and deploy verification.
- `.pi/skills/clerk-backend-api/`, `.pi/skills/clerk-react-patterns/`, `.pi/skills/clerk-testing/`, `.pi/skills/clerk-webhooks/`, `.pi/skills/clerk-orgs/`, `.pi/skills/clerk-setup/`, `.pi/skills/clerk-cli/`
  - Clerk JWT/session/user mapping, frontend auth token handling, and testing patterns.
- `.pi/skills/project-artifact-cleanup/SKILL.md`
  - Avoid committing generated datasets, S3 mirrors, MLflow outputs, reports, and model artifacts.
- `.pi/skills/github-mcp-workflow/SKILL.md`
  - Scoped branch/commit/push workflow if GitHub operations are needed.
- `.pi/skills/surrogate-model-debugging/SKILL.md`
  - Validate training/artifact/model-quality paths after bucket routing changes.

## Subagent and skill map

Use these execution roles when implementing the plan:

| Workstream | Recommended subagent role | Skills to load | Output expected |
| --- | --- | --- | --- |
| Railway diagnosis and deploy validation | Railway infra scout / deployment verifier | `use-railway`, `project-artifact-cleanup` | Read-only service/log/env summary; proof deployed commit handles `/projects`, `/schema`, `/artifact-status` |
| Clerk identity and workspace model | Clerk auth/backend reviewer | `clerk-backend-api`, `clerk-testing`, `clerk-webhooks`, `clerk-setup`, `clerk-cli` | Contract for `clerk_user_id -> workspace_id`; JWT/template/webhook notes; tests for missing/cross-workspace auth |
| Backend control-plane/storage design | Backend architecture implementer | `use-railway`, `project-artifact-cleanup` | Migration and service changes for `workspace -> projects -> per-project bucket` |
| ML/training artifact routing | Surrogate/model lifecycle reviewer | `surrogate-model-debugging`, `project-artifact-cleanup` | Confirm data intake, preprocessing, training, MLflow, reports, and model pointers use project bucket metadata |
| Frontend auth/project UX sanity | Frontend Clerk/UI reviewer | `clerk-react-patterns`, `scientific-ui-clarity` | Confirm UI no longer relies on hardcoded demo defaults and displays workspace/project state clearly |
| GitHub/ship workflow | Release/ship reviewer | `github-mcp-workflow`, `project-artifact-cleanup` | Scoped staged diff, `git diff --cached --check`, commit, push, and no secrets/artifacts staged |

If using actual configured subagents, first list available agents and bind these roles to the closest installed agents. Do not run mutating Railway or GitHub actions until the user approves.

## Steps

### Phase 0 — Ship the current hotfix safely

- [ ] Review the local runtime schema fix in `backend/app/main.py` and `backend/app/services/project_registry.py`.
- [ ] Keep the new regression test for a Postgres-only runtime project.
- [ ] Run targeted tests:
  - `tests/test_runtime_project_schema.py`
  - relevant auth/schema tests in `tests/test_api.py`
  - artifact pointer tests in `tests/test_mlflow_durable_pointers.py`
- [ ] Stage only scoped backend/test files.
- [ ] Run `git diff --cached --check`.
- [ ] Commit and push to the Railway branch if approved.
- [ ] Verify Railway logs show the Fraunhofer schema/artifact endpoints returning `200`.

### Phase 1 — Make Clerk session JWT `sub` the workspace/client authority

- [ ] Decide whether the workspace id is exactly Clerk `sub` or a stable derived id such as `clerk_<sub>`.
- [ ] Use the Clerk session JWT as the authoritative security boundary:
  - verify JWT signature against Clerk JWKS or configured public key;
  - require the configured Clerk issuer;
  - verify expiry/not-before with small clock skew;
  - verify audience when `CLERK_JWT_AUDIENCE` is configured;
  - verify authorized party / `azp` against allowed frontend origins when configured;
  - derive the backend workspace/client only from the verified `sub` claim.
- [ ] Update auth/workspace logic so authenticated requests resolve a single workspace/client from the verified Clerk user id.
- [ ] Remove the current custom JWT `workspace_id` claim from the production tenancy decision. Keep only a clearly named local/test/demo compatibility override, if needed.
- [ ] Ensure `/projects` only lists projects for the derived workspace.
- [ ] Ensure cross-workspace project access returns `403`, not fallback local data.
- [ ] Add tests for:
  - missing token;
  - valid Clerk user with no workspace row;
  - valid Clerk user with multiple projects;
  - cross-workspace project id;
  - local/test-token compatibility.

### Phase 2 — Add canonical project bucket metadata

- [ ] Add canonical project storage metadata in Postgres.
- [ ] Preferred schema: add `storage jsonb NOT NULL DEFAULT '{}'::jsonb` to `projects`, shaped like:

```json
{
  "mode": "s3",
  "bucket": "mirai-project-<project-id>",
  "prefix": "workspaces/<workspace_id>/projects/<project_id>"
}
```

- [ ] Seed Fraunhofer with its own bucket mapping.
- [ ] Seed/demo batteries with its own bucket mapping.
- [ ] Validate bucket names are not secrets and can be logged safely only when necessary.
- [ ] Keep object keys workspace/project scoped even though buckets are project-specific:

```text
s3://<project-bucket>/workspaces/<workspace_id>/projects/<project_id>/...
```

### Phase 3 — Refactor backend storage resolution

- [ ] Add a `get_project_storage_config(workspace_id, project_id)` helper in `control_plane.py` or `workspace_storage.py`.
- [ ] Refactor `durable_artifact_pointer_for_project(...)` to use runtime project storage metadata instead of `PROJECT_STORAGE_METADATA` static maps.
- [ ] Refactor data intake/preprocessing/training request paths that currently assume workspace buckets or static demo buckets.
- [ ] Ensure local mirrors preserve project bucket shape:

```text
backend/.object-storage-local/<project-bucket>/workspaces/<workspace_id>/projects/<project_id>/...
```

- [ ] Keep validation preventing path traversal, cross-workspace prefixes, and accidental writes outside the project prefix.

### Phase 4 — Training/MLflow alignment

- [ ] Ensure `train_project.py --data-object-key` and MLflow artifact paths resolve against project storage metadata.
- [ ] Ensure durable outputs are logged to Railway MLflow + project S3 bucket, not local `mlruns` or local object mirrors in demo mode.
- [ ] Add tests for two projects in one workspace writing to different buckets.
- [ ] Confirm artifact-status returns bucket/object pointers per project.

### Phase 5 — Frontend and UX sanity

- [ ] Confirm frontend gets projects exclusively from `/projects`.
- [ ] Remove or neutralize any remaining hardcoded default project assumptions that bypass the authenticated project list.
- [ ] Keep `Edit labels/details` preserved.
- [ ] Show selected workspace/client and project clearly enough to diagnose tenant/project context.
- [ ] Run frontend build if API response shapes change.

### Phase 6 — Railway validation and release

- [ ] Use Railway read-only diagnostics first:
  - active project/environment/service;
  - deployed commit;
  - backend logs;
  - non-secret env names and safe values only.
- [ ] Verify Clerk-authenticated user maps to expected workspace/client.
- [ ] Verify one workspace can list multiple projects.
- [ ] Verify each project resolves a distinct S3 bucket.
- [ ] Verify Fraunhofer project lifecycle:
  - project selection;
  - schema load;
  - artifact-status load;
  - upload/intake path;
  - preprocessing path;
  - training request path.
- [ ] Commit and push only after tests and secret/artifact hygiene checks pass.

## Verification

Local targeted tests after Phase 0:

```bash
cd backend && uv run pytest \
  tests/test_runtime_project_schema.py \
  tests/test_api.py::test_auth_required_allows_test_token_and_filters_workspace \
  tests/test_api.py::test_auth_required_rejects_cross_workspace_project_access \
  tests/test_api.py::test_project_schema \
  tests/test_mlflow_durable_pointers.py

git diff --check
```

Expanded tests after project-bucket work:

```bash
cd backend && uv run pytest \
  tests/test_workspace_storage.py \
  tests/test_mlflow_durable_pointers.py \
  tests/test_training_mlflow_contract.py \
  tests/test_api.py
```

Frontend check if touched:

```bash
npm --prefix frontend run build
```

Railway checks:

- `/projects` returns only the Clerk user's workspace/client projects.
- `/projects/<project_id>/schema` returns `200` for runtime projects.
- `/projects/<project_id>/artifact-status` returns `200` and points at that project's bucket.
- Logs contain no `Unknown project_id` stack trace for valid runtime projects.
- No secrets are printed, staged, committed, or copied into docs.

## Open decisions

- Should workspace id be exactly Clerk `sub`, or a normalized id derived from it?
- Should project bucket provisioning be manual/pre-created in Railway S3, or should the control plane eventually create buckets automatically?
- Should project bucket live in `projects.storage jsonb`, `projects.metadata.storage`, or a separate `project_storage` table?
- Do we keep a demo/admin override where one Clerk user can access seeded workspaces such as `fraunhofer`, or should seeded demos be assigned to that user's Clerk-derived workspace?
