# Clerk Dev + Railway Demo Isolation Cutover Plan

## Execution orchestration and skills

Before implementation, run an agent chain and use the scout agent whenever possible:

1. Start with a scout/read-only discovery step to re-check current auth, Railway, bucket, and bootstrap-script state before editing.
2. Use the scout output to confirm the implementation tasks are still valid and to avoid duplicating existing utilities.
3. Then run focused implementation/review steps for frontend auth, backend authorization, artifact bootstrap layout, tests, and docs.
4. If an agent runner is available, first list configured agents/chains and choose the available scout-style agent/chain; do not invent an agent name if none is configured.

Available project skills observed:

- `.pi/skills/clerk-setup`
- `.pi/skills/clerk-react-patterns`
- `.pi/skills/clerk-backend-api`
- `.pi/skills/clerk-testing`
- `.pi/skills/clerk-cli`
- `.pi/skills/use-railway`
- `.pi/skills/project-artifact-cleanup`
- `.pi/skills/scientific-ui-clarity`
- `.pi/skills/github-mcp-workflow`
- user/global skills including planning, security, testing, frontend UI engineering, documentation, shipping, CI/CD, and git workflow.

Skill mapping by task:

- Clerk dev app/template/user metadata setup: `clerk-setup`, `clerk-cli`, `security-and-hardening`.
- Frontend `getToken({ template: "jwt-doe-template" })`: `clerk-react-patterns`, `frontend-ui-engineering`, `test-driven-development`.
- Backend JWT verification and workspace scoping: `clerk-backend-api`, `api-and-interface-design`, `security-and-hardening`, `test-driven-development`.
- Railway variable/deploy/smoke-test work: `use-railway`, `shipping-and-launch`, `ci-cd-and-automation`.
- Fuel-cell bucket bootstrap and artifact layout: `project-artifact-cleanup`, `source-driven-development`, `security-and-hardening`.
- UI hiding/clarity for battery placeholder and durable-state card checks: `scientific-ui-clarity`, `frontend-ui-engineering`.
- Documentation/handoff updates: `documentation-and-adrs`, `git-workflow-and-versioning`.

## Context

The immediate goal is to stop adding product features and make the current Railway demo truthful and isolated:

- Use the existing Clerk **development** instance for the demo, not Clerk production keys yet.
- The only existing Clerk user should map to workspace `fraunhofer`.
- That user should see only the fuel-cell demo project: `pem_fuel_cell_real_cathode_degradation`.
- The placeholder battery workspace/project should remain unavailable to that user because it belongs to `battery-demo`, an uncreated future user/workspace.
- Railway buckets should contain real scoped fuel-cell demo artifacts instead of being empty.
- MLflow/model/artifact metadata should clearly point to one workspace/project at a time, even if full bucket-backed runtime loading remains deferred.

Current Railway state observed by the user:

- App service: `mirai-doe`.
- Buckets: `mirai-fuel-cells-demo` and `mirai-batteries-demo`, currently empty.
- PostgreSQL volume/service exists but is not yet the active app control-plane/MLflow backend.

## Current implementation facts

- `frontend/src/main.tsx` uses `@clerk/clerk-react` and sends Clerk bearer tokens to the API via `setAuthTokenProvider(() => getToken())`. This must be tightened for the demo to request the custom template token with `getToken({ template: "jwt-doe-template" })`.
- `backend/app/auth.py` verifies Clerk JWTs when `CLERK_AUTH_REQUIRED=true`. For the demo cutover, the trusted workspace source must be the verified custom JWT `workspace_id` claim. Do not trust workspace IDs from frontend route params, request bodies, or unverified client state.
- `backend/app/main.py` filters `/projects` and `/workspaces` by the authenticated workspace when auth is required.
- Direct `/projects/{project_id}/...` access is denied with `403` when the project is outside the authenticated workspace.
- `backend/app/services/project_registry.py` currently defines:
  - fuel-cell project under workspace `fraunhofer`,
  - battery placeholder project under workspace `battery-demo`.
- `backend/app/services/mlflow_registry.py` exposes durable pointer metadata for both workspaces/projects.
- `scripts/bootstrap_demo_artifacts.py` can dry-run or upload approved fuel-cell artifacts to the workspace/project-scoped bucket path using env-only S3 credentials.

## Approach

Make the smallest necessary changes to cut over the demo to real Clerk dev authentication and truthful workspace isolation.

The recommended cutover is:

1. Configure the Clerk development instance for the Railway app origin.
2. Configure custom Clerk JWT template `jwt-doe-template` with trusted workspace/role claims from user metadata.
3. Update frontend token acquisition to request `getToken({ template: "jwt-doe-template" })`.
4. Ensure backend authorization scopes every workspace/project/artifact endpoint by the verified JWT `workspace_id` claim.
5. Set Railway app service variables to use Clerk dev keys and require auth.
6. Upload fuel-cell source/reference CSVs and training/runtime artifacts into the fuel-cell bucket under the approved workspace/project prefix.
7. Leave the battery bucket empty and battery workspace inaccessible/hidden until a second authorized user exists.
8. Verify from browser and API that the signed-in demo user sees only fuel-cell.
9. Record what is still metadata-only versus truly durable.

## Files to modify

Expected application changes:

- `frontend/src/main.tsx` or auth token wrapper — request Clerk custom JWT template `jwt-doe-template` via `getToken({ template: "jwt-doe-template" })`.
- `backend/app/auth.py` — treat the verified top-level JWT `workspace_id` claim as the trusted workspace source for demo authorization; keep issuer/signature/time validation and do not trust frontend-supplied workspace IDs.
- `backend/app/main.py` — verify every workspace/project/artifact route remains scoped by the authenticated workspace and returns `403` for cross-workspace project access.
- `scripts/bootstrap_demo_artifacts.py` — ensure upload layout matches the requested fuel-cell object layout, including source/reference CSVs under `intake/` and model/runtime artifacts under `training_artifacts/latest/`.
- Tests under `backend/tests/` and frontend build checks as needed.

Documentation updates after verification:

- `docs/railway-level-2-pilot.md` — record actual demo cutover state.
- `deployments/railway/README.md` — record operator commands and verification results.
- `RAILWAY_CLERK_DEPLOYMENT_HANDOFF.md` or `NEXT_STEPS.md` — update handoff status.

## Reuse

Existing implementation to reuse:

- Clerk token forwarding: `frontend/src/main.tsx`, with the required update to request `jwt-doe-template`.
- API auth/JWT verification/workspace claim extraction: `backend/app/auth.py`, with the trusted source narrowed to the verified custom JWT `workspace_id` claim.
- Workspace/project filtering and cross-workspace denial: `backend/app/main.py`.
- Fuel-cell and battery workspace/project registry: `backend/app/services/project_registry.py`.
- Durable artifact pointer conventions: `backend/app/services/mlflow_registry.py`.
- Workspace-scoped S3 pointer validation: `backend/app/services/workspace_storage.py`.
- Safe artifact upload/dry-run script: `scripts/bootstrap_demo_artifacts.py`.
- Existing tests for auth filtering and artifact pointers:
  - `backend/tests/test_api.py`
  - `backend/tests/test_mlflow_durable_pointers.py`
  - `backend/tests/test_bootstrap_demo_artifacts.py`
  - `backend/tests/test_workspace_storage.py`

## Steps

### 1. Clerk dev configuration inventory

- [ ] In the Clerk dashboard for app `app_3EvAvu6InOCLDY2f6ANY6zhm07i`, development instance `ins_3EvAvvkQslvW21PIkwdmrucJsu3`, collect the needed values without committing them:
  - [ ] Dev publishable key: `VITE_CLERK_PUBLISHABLE_KEY` / `pk_test_...` from the API keys page.
  - [ ] Dev secret key: `sk_test_...` only if needed by an operator script or Clerk CLI; keep it only in `.env.local`, Railway variables, or another secret store.
  - [ ] Issuer: `https://square-snail-89.clerk.accounts.dev`.
  - [ ] JWKS URL: `https://square-snail-89.clerk.accounts.dev/.well-known/jwks.json`.
  - [ ] Audience: leave unset for first dev version unless the custom JWT template explicitly configures one.
- [ ] Configure Clerk dev allowed origins/callbacks for:
  - [ ] `https://mirai-doe-production.up.railway.app`
  - [ ] local dev origin if needed, e.g. `http://localhost:5173`.
- [ ] Use short token lifetime for the demo: 60 seconds is acceptable; if too disruptive, use 5–15 minutes.
- [ ] Allow only small clock skew, e.g. 5 seconds.

### 2. Configure Clerk user metadata and custom JWT template

- [ ] In Clerk dev user settings, set the existing user private metadata to:

```json
{
  "workspace_id": "fraunhofer",
  "role": "demo_fuel_cell"
}
```

- [ ] Prefer private metadata. Public metadata is acceptable only if Clerk dev/template constraints require it for the demo.
- [ ] Create Clerk JWT template named `jwt-doe-template`.
- [ ] Configure template claims using private metadata:

```json
{
  "workspace_id": "{{user.private_metadata.workspace_id}}",
  "role": "{{user.private_metadata.role}}"
}
```

- [ ] If public metadata is used instead, configure claims as:

```json
{
  "workspace_id": "{{user.public_metadata.workspace_id}}",
  "role": "{{user.public_metadata.role}}"
}
```

- [ ] Verify a token from this template includes a top-level verified `workspace_id: "fraunhofer"` claim.

### 3. Update app auth contract for the custom JWT

- [ ] Update frontend token acquisition so API calls use:

```ts
getToken({ template: "jwt-doe-template" })
```

- [ ] Confirm every API request sends the template token as:

```text
Authorization: Bearer <token>
```

- [ ] Update/verify backend JWT validation:
  - [ ] Verify signature using Clerk dev JWKS.
  - [ ] Verify issuer `https://square-snail-89.clerk.accounts.dev`.
  - [ ] Verify standard time claims (`exp`, `iat`, `nbf`) with ~5 seconds clock skew if supported.
  - [ ] Do not enforce audience for the first dev version.
  - [ ] Treat the verified top-level `workspace_id` claim as the only trusted workspace source.
  - [ ] Do not trust `workspace_id` from frontend route params, request bodies, query strings, or local UI state.
- [ ] Verify every workspace/project/artifact endpoint is scoped by the verified JWT workspace.

### 4. Configure Railway app variables for Clerk dev auth

- [ ] Set variables on Railway service `mirai-doe` only; do not set them on the Postgres service.
- [ ] Set:
  - [ ] `VITE_CLERK_PUBLISHABLE_KEY=<dev pk_test publishable key>`
  - [ ] `CLERK_AUTH_REQUIRED=true`
  - [ ] `FASTAPI_DOCS_PUBLIC=false`
  - [ ] `CLERK_DEFAULT_WORKSPACE_ID=fraunhofer` as a dev fallback only; real signed-in access must come from the verified Clerk JWT claim.
  - [ ] `CLERK_ISSUER` or `CLERK_JWT_ISSUER=https://square-snail-89.clerk.accounts.dev`
  - [ ] `CLERK_JWKS_URL=https://square-snail-89.clerk.accounts.dev/.well-known/jwks.json`
  - [ ] Do not set `CLERK_JWT_AUDIENCE` for the first dev version.
- [ ] Redeploy `mirai-doe` after variable changes because the Vite publishable key is compiled into the frontend build.

### 5. Bootstrap real fuel-cell artifacts into the Railway fuel-cell bucket

- [ ] Keep battery bucket empty for now.
- [ ] Use Railway bucket credential variables already configured for `fraunhofer` without printing raw values.
- [ ] Update/verify the bootstrap script layout before upload. Required target layout:

```text
workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/
  model.onnx
  preprocessing.json
  schema.json
  metadata.json
  metrics.json                # if available

workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/
  model_table.csv
  cell_metadata.csv
  ast_trace_manifest.csv
```

- [ ] Do not expose raw intake files to the frontend unless the authenticated user has verified `workspace_id=fraunhofer`.
- [ ] First run a dry-run locally/operator shell:

```bash
python3 scripts/bootstrap_demo_artifacts.py --project fuel-cell --dry-run
```

- [ ] Confirm all listed object keys are under:

```text
workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/
```

- [ ] Install/use an operator environment with `boto3` available if not already available.
- [ ] Run upload only after dry-run looks correct:

```bash
python3 scripts/bootstrap_demo_artifacts.py --project fuel-cell --upload
```

- [ ] Verify in Railway bucket UI that the fuel-cell bucket now contains scoped objects.
- [ ] Verify the battery bucket remains empty.

### 6. Browser verification

- [ ] Open `https://mirai-doe-production.up.railway.app` in a clean/private browser session.
- [ ] Confirm signed-out user sees only Clerk sign-in/sign-up, not the app.
- [ ] Sign in with the existing Clerk dev user.
- [ ] Confirm `/projects` data in the UI shows only:
  - [ ] `pem_fuel_cell_real_cathode_degradation`.
- [ ] Confirm the battery placeholder project is not visible/selectable.
- [ ] Confirm fuel-cell schema/BO/model status pages still load.
- [ ] Confirm artifact-status card points to `fraunhofer` and the fuel-cell bucket/prefix.

### 7. API verification

- [ ] Without a bearer token, protected endpoints should reject:

```bash
curl -i https://mirai-doe-production.up.railway.app/projects
```

Expected: `401`.

- [ ] With the signed-in Clerk dev user token, `/projects` should return only `fraunhofer` projects.
- [ ] Direct cross-workspace access should reject:

```bash
curl -i https://mirai-doe-production.up.railway.app/projects/battery_tabular_doe_demo/artifact-status \
  -H "Authorization: Bearer <dev-user-token>"
```

Expected: `403`.

- [ ] Fuel-cell access should succeed:

```bash
curl -i https://mirai-doe-production.up.railway.app/projects/pem_fuel_cell_real_cathode_degradation/artifact-status \
  -H "Authorization: Bearer <dev-user-token>"
```

Expected: `200`, `workspace_id=fraunhofer`.

### 8. Record final demo truth

- [ ] Document that the demo is Level 2 virtual isolation with Clerk dev auth.
- [ ] Document that the existing user maps to `fraunhofer` and sees only fuel-cell.
- [ ] Document that battery is reserved for a future user/workspace and remains inaccessible/empty.
- [ ] Document that bucket artifacts are bootstrapped for fuel-cell.
- [ ] Document any remaining limitation:
  - [ ] Postgres is not yet the active workspace/project/MLflow control plane if still true.
  - [ ] MLflow runtime may still use packaged/local fallback unless/until the bucket-backed resolver is implemented.

## Verification

Required before calling the demo ready:

- [ ] Backend tests still pass locally:

```bash
cd backend && uv run pytest -q
```

- [ ] Frontend build still passes:

```bash
cd frontend && npm run build
```

- [ ] Railway deployment succeeds.
- [ ] Signed-out browser cannot access app data.
- [ ] Signed-in existing Clerk dev user sees only fuel-cell.
- [ ] Frontend requests Clerk token with template `jwt-doe-template`.
- [ ] Verified JWT contains top-level `workspace_id=fraunhofer` and `role=demo_fuel_cell` claims.
- [ ] Direct battery project API access returns `403` for the fuel-cell user.
- [ ] Battery placeholder is hidden from the UI for the fuel-cell user and enforced backend-side.
- [ ] Fuel-cell bucket contains scoped real artifacts under both:
  - [ ] `workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/`
  - [ ] `workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/`
- [ ] Battery bucket remains empty.
- [ ] No secrets are printed, committed, or copied into docs.

## Decisions captured

- Use Clerk development environment for the demo; do not switch to Clerk production keys yet.
- Use custom Clerk JWT template `jwt-doe-template`.
- Prefer Clerk private metadata for the existing user:

```json
{
  "workspace_id": "fraunhofer",
  "role": "demo_fuel_cell"
}
```

- Use issuer `https://square-snail-89.clerk.accounts.dev` and JWKS URL `https://square-snail-89.clerk.accounts.dev/.well-known/jwks.json`.
- Do not configure JWT audience for the first dev version.
- Hide battery from the UI until a second authorized user/workspace exists, and enforce backend-side `403` for cross-workspace access.
- Upload both fuel-cell training/runtime artifacts and source/reference CSVs to the fuel-cell bucket.
