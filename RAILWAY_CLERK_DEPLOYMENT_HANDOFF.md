# Mirai DoE Railway + Clerk Deployment Handoff

_Last updated: 2026-06-13_

This document summarizes the deployment/authentication work performed in the current dirty worktree, what changed, what still needs review, and how to test or redeploy safely. It is intentionally detailed so you can audit the changes before staging/committing anything.

> **Important:** No files were staged or committed as part of this handoff. Review the dirty worktree manually before committing.

---

## 0. Current Clerk dev cutover update

Current deployed Railway service state:

- App service: `mirai-doe`
- Public URL: <https://mirai-doe-production.up.railway.app>
- Latest verified deployment: `19bdf8fd-efd7-4f60-a8ea-5cbdc0ce6ba2`
- `CLERK_AUTH_REQUIRED=true`
- `FASTAPI_DOCS_PUBLIC=false`
- Clerk dev issuer/JWKS configured for `https://square-snail-89.clerk.accounts.dev`
- SPA static serving configured with `MIRAI_STATIC_DIR=/app/static`

Implemented in code:

- Frontend requests `getToken({ template: "jwt-doe-template" })`.
- Backend trusts only the verified top-level JWT `workspace_id` claim for workspace authorization.
- Tokens without a trusted workspace claim are rejected with `403`.
- Project/artifact routes reject cross-workspace access via backend middleware.
- `/data-intake/sessions` is filtered by authenticated workspace.
- Static SPA assets are public so signed-out users can load the Clerk sign-in/sign-up UI; protected data endpoints still reject unauthenticated requests.

Verified without secrets:

- Backend tests: `70 passed`.
- Frontend build: passed with existing bundle/browser-data warnings.
- Signed-out API checks: `/projects` and project artifact endpoints return `401` without a bearer token.
- Fuel-cell bucket contains scoped objects under both `training_artifacts/latest/` and `intake/`.
- Battery bucket checked empty.

Remaining operator-only Clerk dashboard work:

- Create/update JWT template `jwt-doe-template` with top-level `workspace_id` and `role` claims from user private metadata.
- Set the existing Clerk dev user private metadata to `workspace_id=fraunhofer` and `role=demo_fuel_cell`.
- Confirm allowed origins/callbacks include `https://mirai-doe-production.up.railway.app`.
- Confirm a real signed-in Clerk dev token includes `workspace_id=fraunhofer` and `role=demo_fuel_cell`, then verify `/projects` returns only the fuel-cell project and direct battery access returns `403`.

The local `.env.local` secret key was present and shaped like `sk_test_...`, but Clerk Backend API calls to list users/templates returned `403` from this environment, so dashboard/API-key-permission completion is still required. No raw secrets were printed or committed.

## 1. Executive Summary

We moved Mirai DoE toward a **single-container Railway deployment** that serves both:

1. the React/Vite SPA frontend, and
2. the FastAPI backend/API,

from one Railway app service named `mirai-doe`.

The Level 2 pilot decision is to use Railway-native services for durable state: the app service, Railway Postgres, and Railway S3-compatible object storage. `kind`/Kubernetes is intentionally not part of the Railway runtime; it remains a possible local-development or future Level 3 path. Any packaged demo/reference artifacts in the current image are smoke-test scaffolding, not the final durable-state mechanism for pilot data.

We also added Clerk-based local/frontend authentication wiring and backend JWT verification scaffolding, but Railway production Clerk enforcement is still intentionally disabled until production Clerk variables are configured.

### Current Railway deployment state

- Railway project: `satisfied-growth`
- Railway project ID: `7e5c11fb-0611-43a2-8806-f7bded80c7ba`
- Environment: `production`
- Environment ID: `9474935c-6264-4b16-a8c2-826f004f9e71`
- App service: `mirai-doe`
- App service ID: `42b63012-f816-45d9-98b6-11dac80dff0f`
- Public URL: <https://mirai-doe-production.up.railway.app>
- Latest successful deployment verified during work: `2d9c53e1-754d-491f-bf37-c14d6716bbbc`

### Current Railway env posture

Configured Clerk dev demo variables:

```text
CLERK_AUTH_REQUIRED=true
FASTAPI_DOCS_PUBLIC=false
CLERK_DEFAULT_WORKSPACE_ID=fraunhofer
CLERK_ISSUER=https://square-snail-89.clerk.accounts.dev
CLERK_JWT_ISSUER=https://square-snail-89.clerk.accounts.dev
CLERK_JWKS_URL=https://square-snail-89.clerk.accounts.dev/.well-known/jwks.json
CLERK_JWT_LEEWAY_SECONDS=5
MIRAI_STATIC_DIR=/app/static
```

This means:

- the SPA/sign-in UI and health routes can be reached signed-out;
- API docs are not exposed as public FastAPI docs;
- protected project/artifact endpoints reject unauthenticated requests;
- authenticated authorization requires a verified top-level `workspace_id` JWT claim from Clerk dev custom JWT template `jwt-doe-template`.

---

## 2. High-Level Change Areas

The current worktree contains changes in these major areas:

1. **Railway deployment packaging**
   - New `Dockerfile.railway`
   - New `railway.toml`
   - New `.railwayignore`
   - Updated `.gitignore`
   - New/changed Docker upload/deployment rules

2. **Frontend Clerk authentication**
   - Added Clerk React dependency
   - Added Clerk provider/sign-in/sign-up/user button flow in `frontend/src/main.tsx`
   - Added bearer-token injection in `frontend/src/lib/api.ts`
   - Pulled Clerk development env vars into ignored env files

3. **Backend Clerk/JWT auth scaffolding**
   - New `backend/app/auth.py`
   - FastAPI middleware in `backend/app/main.py`
   - Docs gating with `FASTAPI_DOCS_PUBLIC`
   - Test-token support for backend tests

4. **Workspace/storage control-plane work**
   - New `backend/app/services/workspace_storage.py`
   - New SQL migration/seed docs under `backend/db/`
   - Data-intake changes in `backend/app/services/data_intake.py`
   - New/updated tests

5. **Documentation/planning artifacts**
   - New Railway Level 2 pilot doc
   - Clerk install prompt doc
   - Railway/Clerk/Postgres master plan docs
   - SQL/S3 implementation planning docs

6. **Git hygiene cleanup**
   - Re-ignored thousands of local/generated MLflow/data artifacts
   - Untracked files dropped from ~2,776 to 15 after `.gitignore` cleanup

---

## 3. Current Dirty Worktree Snapshot

At the time this handoff was created, `git status --short` showed:

```text
 M .gitignore
 M AGENTS.md
 M backend/app/main.py
 M backend/app/services/data_intake.py
 M backend/pyproject.toml
 M backend/tests/test_api.py
 M backend/uv.lock
 M docs/agent-plans/to-implement/railway-brainstorm-bruno.md
 D docs/agent-plans/to-implement/sql-backed-lifecycle-management-plan.md
 M frontend/package-lock.json
 M frontend/package.json
 M frontend/src/lib/api.ts
 M frontend/src/main.tsx
?? .dockerignore
?? .railwayignore
?? Dockerfile.railway
?? backend/app/auth.py
?? backend/app/services/workspace_storage.py
?? backend/db/
?? backend/tests/test_workspace_storage.py
?? docs/agent-plans/to-implement/clerk-installation-prompt.md
?? docs/agent-plans/to-implement/railway-clerk-postgres-master-plan.md
?? docs/agent-plans/to-implement/sql-s3-implementation/
?? docs/railway-level-2-pilot.md
?? railway.toml
?? RAILWAY_CLERK_DEPLOYMENT_HANDOFF.md
```

The exact list may differ after further edits.

### Untracked files still visible after ignore cleanup

These are likely real source/config/docs files worth reviewing manually:

```text
.dockerignore
.railwayignore
Dockerfile.railway
backend/app/auth.py
backend/app/services/workspace_storage.py
backend/db/README.md
backend/db/migrations/001_workspace_control_plane.sql
backend/db/seeds/001_seed_demo_control_plane.sql
backend/tests/test_workspace_storage.py
docs/agent-plans/to-implement/clerk-installation-prompt.md
docs/agent-plans/to-implement/railway-clerk-postgres-master-plan.md
docs/agent-plans/to-implement/sql-s3-implementation/sql-lifecycle-management-with-doe-references-plan.md
docs/agent-plans/to-implement/sql-s3-implementation/sql-s3-data-safe-storage.md
docs/railway-level-2-pilot.md
railway.toml
```

---

## 4. Railway Deployment Details

### 4.1 Architecture chosen for the pilot

The current Railway deployment uses a **single-container** architecture:

```text
Browser
  ↓
Railway public URL
  ↓
FastAPI/Uvicorn container
  ├─ serves API routes
  └─ serves React build from /app/static
```

This is deliberately simple for the Level 2 pilot. It avoids separate frontend/backend services and avoids CORS complexity for production because the SPA can call the API using same-origin URLs.

### 4.2 Key deployment files

#### `railway.toml`

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile.railway"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 300
restartPolicyType = "ON_FAILURE"
```

Meaning:

- Railway builds using `Dockerfile.railway`.
- Railway uses `/health` as the healthcheck endpoint.
- Healthcheck timeout is generous because app startup/model discovery can be slow.
- Failed services restart on failure.

#### `Dockerfile.railway`

The Dockerfile has three stages:

1. `frontend-builder`
   - Uses `node:20-alpine`
   - Runs `npm ci`
   - Runs `npm run build`
   - Produces `frontend/dist`

2. `backend-builder`
   - Uses `python:3.11-slim`
   - Copies `uv` from `ghcr.io/astral-sh/uv`
   - Sets `UV_TORCH_BACKEND=cpu`
   - Installs backend dependencies with:

     ```bash
     uv pip install --system --torch-backend cpu .
     ```

   - This was important because exported locked requirements were causing CUDA/NVIDIA Torch artifacts to be pulled, making the image huge and slow to export.

3. `runtime`
   - Uses `python:3.11-slim`
   - Copies backend deps, backend app code, frontend static build, workspace metadata, MLflow registry state, and selected reference demo artifacts.
   - Defines runtime env defaults:

     ```text
     DOE_OBJECT_STORE_ROOT=/app/data-minio
     DOE_REFERENCE_DATA_ROOT=/app/data/reference
     MIRAI_STATIC_DIR=/app/static
     PORT=8000
     ```

   - Runs sanity checks during image build to fail early if required artifacts are missing.
   - Runs:

     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
     ```

### 4.3 Why CPU Torch matters

The backend uses BoTorch/GPyTorch/Torch. Without forcing CPU Torch, the dependency resolver/build path can pull CUDA/NVIDIA wheels. That caused Railway builds to become very large and slow; one earlier build appeared to hang/fail during export because the image was too large.

The fix was:

```dockerfile
ENV UV_TORCH_BACKEND=cpu
RUN uv pip install --system --torch-backend cpu .
```

The validated local build installed:

```text
torch==2.12.0+cpu
```

### 4.4 `.railwayignore` behavior

`.railwayignore` is used to keep the Railway source upload small and deterministic. It ignores everything by default and then explicitly re-includes only required build inputs.

Important included categories:

- `Dockerfile.railway`
- `railway.toml`
- `.dockerignore`
- `backend/app/**`
- `backend/ml_lifecycle/**`
- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/healthcheck.py`
- `backend/data-minio/workspaces/**`
- `backend/mlruns/**`
- frontend source/package/build config
- selected `data/reference/pem_fuel_cell_cathode_degradation/**`

Important excluded categories:

- `.env`, `.env.*`, `.envrc`
- `node_modules`
- `.venv`
- Python caches
- `frontend/dist`
- `backend/data-minio/intake`
- `backend/.mlflow-cache`

### 4.5 Difference between `.gitignore` and `.railwayignore`

This is important:

- `.gitignore` controls what Git sees.
- `.railwayignore` controls what Railway CLI uploads.

We re-ignored `backend/mlruns/` and `/data/` in Git so the worktree is clean enough to review. However, `.railwayignore` still intentionally includes selected runtime/demo artifacts for the Railway image.

Before relying on this, verify with an actual Railway deploy/build. If Railway CLI changes its behavior or respects Git ignored state unexpectedly, the Docker build checks will fail quickly with messages such as:

```text
ERROR: MLflow registry state missing
ERROR: business-impact real data artifacts missing
ERROR: model-quality preprocessing/split artifacts missing
```

---

## 5. Railway Deployment Mini-Tutorial

### 5.1 Check Railway CLI context

From repo root:

```bash
railway status
```

Expected context should show:

```text
Project: satisfied-growth
Environment: production
Linked service: mirai-doe
```

If it is linked to the wrong service, do **not** deploy. In particular, do not deploy this app image to the Railway `Postgres` service.

### 5.2 Confirm service and env explicitly

Use explicit flags when deploying:

```bash
railway up \
  --service mirai-doe \
  --environment production \
  --detach \
  --json \
  --message "your deployment message"
```

This returns JSON like:

```json
{
  "deploymentId": "...",
  "logsUrl": "https://railway.com/project/..."
}
```

Save the `deploymentId`.

### 5.3 Poll deployment status

```bash
railway deployment list --service mirai-doe --environment production
```

You are looking for the deployment ID to move through:

```text
INITIALIZING → BUILDING → DEPLOYING → SUCCESS
```

If it fails:

```bash
railway logs --service mirai-doe --environment production --lines 220
```

### 5.4 Generate or inspect public domain

If no public URL exists:

```bash
railway domain --service mirai-doe --environment production --port 8000 --json
```

Current generated public URL:

```text
https://mirai-doe-production.up.railway.app
```

### 5.5 Smoke-test endpoints after deploy

```bash
BASE=https://mirai-doe-production.up.railway.app

curl -sS -L -o /tmp/mirai_root.html \
  -w 'status=%{http_code} content_type=%{content_type} bytes=%{size_download}\n' \
  "$BASE/"

curl -sS -L "$BASE/health"

curl -sS -L "$BASE/api/health"
```

Expected:

- `/` returns HTML for the React SPA.
- `/health` returns JSON with `status: healthy`.
- `/api/health` returns JSON with `status: healthy`.

### 5.6 Confirm docs are not exposed

With `FASTAPI_DOCS_PUBLIC=false`, these should not expose FastAPI docs/OpenAPI JSON:

```bash
BASE=https://mirai-doe-production.up.railway.app
for path in /docs /redoc /openapi.json; do
  echo "--- $path"
  curl -sS -L -o /tmp/resp \
    -w 'status=%{http_code} content_type=%{content_type} bytes=%{size_download}\n' \
    "$BASE$path"
  head -c 200 /tmp/resp
  echo
 done
```

Current behavior after the docs fix:

- these routes fall through to the SPA HTML;
- they do not return FastAPI docs or OpenAPI JSON.

### 5.7 Check Railway variables safely

Do not print secrets in logs. For current known non-secret posture:

```bash
railway variables --service mirai-doe --environment production --json > /tmp/railway-vars.json
python3 - <<'PY'
import json
p = '/tmp/railway-vars.json'
data = json.load(open(p))
for key in sorted(data):
    if key.startswith('RAILWAY_') or key in {
        'CLERK_AUTH_REQUIRED',
        'CLERK_DEFAULT_WORKSPACE_ID',
        'FASTAPI_DOCS_PUBLIC',
    }:
        print(key)
PY
```

Avoid dumping values once real Clerk secrets are configured.

---

## 6. Clerk Authentication Details

### 6.1 Local Clerk setup performed

The Clerk installation prompt in `docs/agent-plans/to-implement/clerk-installation-prompt.md` was followed after the missing local sign-up page was reported.

Commands run:

```bash
npm install -g clerk
clerk --version
clerk auth login
cd frontend && clerk init --app app_3EvAvu6InOCLDY2f6ANY6zhm07i
cd frontend && clerk doctor
```

`clerk doctor` reported:

- Clerk CLI up to date
- logged in
- app `DoE Engine` reachable
- `frontend/.env.local` contains development `VITE_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY`
- production instance not configured
- zsh completion not installed

### 6.2 Env files

Clerk dev env values are in ignored files:

```text
.env.local
frontend/.env.local
```

These are ignored by Git:

```gitignore
.env
.env.local
```

The root `.env.local` was updated with the Vite publishable key so direnv can expose it when launching from the repo root. The values were not printed in command output.

Verification command used:

```bash
direnv exec . bash -lc 'if [ -n "$VITE_CLERK_PUBLISHABLE_KEY" ]; then echo direnv_has_vite_clerk_key; else echo direnv_missing_vite_clerk_key; fi'
```

Expected:

```text
direnv_has_vite_clerk_key
```

### 6.3 Frontend behavior

`frontend/src/main.tsx` now does this:

- reads `import.meta.env.VITE_CLERK_PUBLISHABLE_KEY`;
- if present:
  - wraps the app in `ClerkProvider`;
  - shows a signed-out landing page with:
    - **Sign up** button
    - **Sign in** button
  - shows the real app only inside `<SignedIn>`;
  - shows `UserButton` after login;
  - registers a token provider that injects Clerk bearer tokens into API calls;
- if missing:
  - falls back to rendering `<App />` directly.

This fallback is convenient for local no-auth development, but it can hide broken Clerk env setup. If you expect Clerk locally and see the app directly instead of the sign-up page, check `VITE_CLERK_PUBLISHABLE_KEY` first.

### 6.4 Frontend API token injection

`frontend/src/lib/api.ts` now has:

- an Axios client;
- `setAuthTokenProvider()`;
- an Axios request interceptor that calls Clerk `getToken()` and adds:

```http
Authorization: Bearer <token>
```

### 6.5 Backend auth behavior

New file: `backend/app/auth.py`

Key env vars:

```text
CLERK_AUTH_REQUIRED=true|false
FASTAPI_DOCS_PUBLIC=true|false
CLERK_DEFAULT_WORKSPACE_ID=fraunhofer
CLERK_JWT_ISSUER=...
CLERK_ISSUER=...
CLERK_JWKS_URL=...
CLERK_JWT_AUDIENCE=...
CLERK_AUTH_TEST_TOKEN=...
CLERK_AUTH_TEST_USER_ID=...
CLERK_AUTH_TEST_WORKSPACE_ID=...
```

Important functions:

- `auth_required()` reads `CLERK_AUTH_REQUIRED`.
- `docs_public()` controls docs exposure.
- `is_public_path()` allows public health/root paths.
- `authenticate_bearer_token()` verifies JWTs using Clerk JWKS.
- `principal_workspace_id()` resolves the workspace from claims or falls back to `CLERK_DEFAULT_WORKSPACE_ID`.

Public paths:

```text
/
/health
/api/health
```

Docs paths are only public when `FASTAPI_DOCS_PUBLIC=true`:

```text
/docs
/redoc
/openapi.json
```

### 6.6 Current Railway Clerk limitation

Railway currently has:

```text
CLERK_AUTH_REQUIRED=false
```

This is intentional because production Clerk variables are not yet configured. Until they are configured, protected API behavior is effectively bootstrap/public mode.

Before enabling auth in Railway, configure at least:

```text
VITE_CLERK_PUBLISHABLE_KEY=<production publishable key>
CLERK_JWT_ISSUER=<production issuer>
```

Optional but often needed:

```text
CLERK_JWKS_URL=<explicit JWKS URL if not derived from issuer>
CLERK_JWT_AUDIENCE=<expected audience if configured>
```

Then set:

```text
CLERK_AUTH_REQUIRED=true
```

After that, redeploy and test unauthenticated calls return `401` except public paths.

---

## 7. Local Development Mini-Tutorial

### 7.1 Reload direnv

From repo root:

```bash
direnv reload
```

Check Clerk public key presence without printing it:

```bash
direnv exec . bash -lc 'test -n "$VITE_CLERK_PUBLISHABLE_KEY" && echo ok || echo missing'
```

### 7.2 Start backend locally

Typical backend flow:

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If testing auth-required local mode with a test token:

```bash
cd backend
CLERK_AUTH_REQUIRED=true \
CLERK_AUTH_TEST_TOKEN=dev-test-token \
CLERK_AUTH_TEST_USER_ID=local-user \
CLERK_AUTH_TEST_WORKSPACE_ID=fraunhofer \
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7.3 Start frontend locally

```bash
cd frontend
npm run dev
```

Open the Vite URL, usually:

```text
http://localhost:5173
```

Expected Clerk behavior:

- signed out: Mirai landing page with **Sign up** and **Sign in**;
- after signup/signin: app appears and user profile button is visible top-right.

### 7.4 API URL behavior locally

`frontend/src/lib/api.ts` currently defines:

```ts
const DEFAULT_API_URL = typeof window !== 'undefined' && window.location.port === '3000' ? 'http://localhost:8000' : ''
const API_URL = import.meta.env.VITE_API_URL ?? DEFAULT_API_URL
```

Important implication:

- If running Vite on port `5173` and `VITE_API_URL` is unset, API calls use same-origin (`''`), which likely points to Vite, not FastAPI.
- If running frontend on port `3000`, default points to `http://localhost:8000`.

Recommended local env if using Vite default port:

```text
VITE_API_URL=http://localhost:8000
```

Check your `.env.local`/direnv setup if local API calls fail.

### 7.5 Build frontend

```bash
cd frontend
npm run build
```

This was validated after Clerk changes.

### 7.6 Run backend tests

```bash
cd backend
uv run pytest -q
```

This was validated during the session with:

```text
55 passed
```

Warnings appeared from matplotlib, MLflow filesystem backend deprecation, BoTorch expected-improvement numerics, and ONNX/Torch export deprecations. These warnings were not introduced as blockers.

### 7.7 Build Railway image locally

From repo root:

```bash
docker build -f Dockerfile.railway -t mirai-doe-railway .
```

For a clean no-cache validation:

```bash
docker build --no-cache -f Dockerfile.railway -t mirai-doe-railway-clean .
```

Validated local build completed successfully after CPU Torch fix.

### 7.8 Run Railway image locally

After building:

```bash
docker run --rm -p 8000:8000 \
  -e CLERK_AUTH_REQUIRED=false \
  -e FASTAPI_DOCS_PUBLIC=false \
  -e CLERK_DEFAULT_WORKSPACE_ID=fraunhofer \
  mirai-doe-railway
```

Then test:

```bash
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/api/health
open http://localhost:8000/
```

---

## 8. Git Hygiene and Ignored Files

### 8.1 Problem encountered

At one point, there were more than 2,700 untracked files. Main causes:

- `backend/mlruns/` contained MLflow runtime artifacts;
- `/data/` contained large raw/reference/demo data;
- broad `.gitignore` unignore rules made them visible again:

```gitignore
!/data/reference/pem_fuel_cell_cathode_degradation/**
!backend/mlruns/**
```

### 8.2 Fix applied

`.gitignore` now ignores:

```gitignore
backend/data-minio/experiment_logs/
backend/data-minio/bo_configs/
backend/data-minio/model_quality_reviews/
backend/data-minio/intake/
backend/data-minio/preprocessing_reviews/
backend/data-minio/workspaces/*/intake/
backend/data-minio/workspaces/default-workspace/
backend/data-minio/workspaces/mirai-engineering/
backend/mlruns/
backend/.mlflow-cache/
/data/
logs/
context.md
```

After this, visible untracked files dropped to a manageable set of source/config/docs files.

### 8.3 Things not to commit accidentally

Do not commit:

```text
.env
.env.local
frontend/.env.local
.envrc
backend/mlruns/
backend/data-minio/intake/
backend/data-minio/workspaces/*/intake/
data/
logs/
context.md
node_modules/
frontend/dist/
backend/.venv/
```

### 8.4 Before committing, inspect carefully

Suggested commands:

```bash
git status --short

git diff --stat

git diff -- .gitignore .railwayignore Dockerfile.railway railway.toml

git diff -- frontend/src/main.tsx frontend/src/lib/api.ts frontend/package.json

git diff -- backend/app/main.py backend/app/auth.py backend/app/services/data_intake.py backend/app/services/workspace_storage.py
```

For untracked files:

```bash
git ls-files --others --exclude-standard
```

For ignored file sanity:

```bash
git check-ignore -v .env.local frontend/.env.local backend/mlruns/models data/reference/pem_fuel_cell_cathode_degradation/model_table.csv
```

---

## 9. Review Checklist Before Staging

### 9.1 Deployment files

Review:

```text
Dockerfile.railway
.railwayignore
.dockerignore
railway.toml
```

Questions to answer:

- Is it acceptable that the Railway image copies `backend/mlruns` and selected `data/reference` artifacts from the local filesystem?
- Is the image size acceptable?
- Is the demo artifact set non-secret and approved for deployment?
- Should demo artifacts be moved to a dedicated tracked fixture or release artifact path instead of local runtime paths?
- Does `.railwayignore` include exactly what Railway needs and nothing more?

### 9.2 Auth files

Review:

```text
frontend/src/main.tsx
frontend/src/lib/api.ts
backend/app/auth.py
backend/app/main.py
backend/tests/test_api.py
```

Questions:

- Should the frontend fallback to `<App />` when `VITE_CLERK_PUBLISHABLE_KEY` is missing, or should it fail loudly?
- Should local dev always require Clerk, or remain optional?
- Are public paths correct?
- Should docs fall through to SPA or return 404 when disabled?
- Are workspace claims (`workspace_id`, `metadata.workspace_id`, `public_metadata.workspace_id`, `org_id`) aligned with the Clerk/org model you want?

### 9.3 Workspace/storage files

Review:

```text
backend/app/services/workspace_storage.py
backend/app/services/data_intake.py
backend/db/
backend/tests/test_workspace_storage.py
```

Questions:

- Is the current workspace-control-plane SQL schema acceptable?
- Are workspace IDs and project IDs validated strongly enough?
- Are runtime files cleanly separated from source-controlled metadata?
- Is the Fraunhofer demo path still aligned with generic tabular lifecycle rules?

### 9.4 Docs/plans

Review:

```text
docs/railway-level-2-pilot.md
docs/agent-plans/to-implement/clerk-installation-prompt.md
docs/agent-plans/to-implement/railway-clerk-postgres-master-plan.md
docs/agent-plans/to-implement/sql-s3-implementation/
docs/agent-plans/to-implement/railway-brainstorm-bruno.md
```

Questions:

- Are these still plans or should completed ones move to an implemented folder?
- Are any docs stale relative to what was actually done?
- Should the deleted `sql-backed-lifecycle-management-plan.md` be restored, moved, or intentionally removed?

---

## 10. Suggested Test Matrix

### 10.1 Fast local smoke

```bash
cd frontend && npm run build
cd ../backend && uv run pytest -q
```

### 10.2 Docker image smoke

```bash
docker build -f Dockerfile.railway -t mirai-doe-railway .

docker run --rm -p 8000:8000 \
  -e CLERK_AUTH_REQUIRED=false \
  -e FASTAPI_DOCS_PUBLIC=false \
  -e CLERK_DEFAULT_WORKSPACE_ID=fraunhofer \
  mirai-doe-railway
```

In another terminal:

```bash
curl -sS -i http://localhost:8000/
curl -sS -i http://localhost:8000/health
curl -sS -i http://localhost:8000/api/health
curl -sS -i http://localhost:8000/docs
curl -sS -i http://localhost:8000/openapi.json
```

Expected:

- `/`, `/docs`, `/openapi.json` return SPA HTML when docs are disabled;
- `/health` and `/api/health` return JSON health.

### 10.3 Local Clerk UI smoke

```bash
direnv reload
cd frontend
npm run dev
```

Open local Vite URL.

Expected:

- signed-out landing shown;
- **Sign up** opens Clerk modal;
- after account creation/sign-in, app loads;
- user profile button appears top-right.

### 10.4 Backend auth-required smoke with test token

Start backend:

```bash
cd backend
CLERK_AUTH_REQUIRED=true \
CLERK_AUTH_TEST_TOKEN=dev-test-token \
CLERK_AUTH_TEST_USER_ID=local-user \
CLERK_AUTH_TEST_WORKSPACE_ID=fraunhofer \
uv run uvicorn app.main:app --reload --port 8000
```

Test public path:

```bash
curl -i http://localhost:8000/health
```

Test protected path without token:

```bash
curl -i http://localhost:8000/projects
```

Expected: `401`.

Test protected path with token:

```bash
curl -i -H 'Authorization: Bearer dev-test-token' http://localhost:8000/projects
```

Expected: `200`, subject to project/workspace state.

### 10.5 Railway smoke after deploy

```bash
BASE=https://mirai-doe-production.up.railway.app
curl -sS -L "$BASE/health"
curl -sS -L "$BASE/api/health"
curl -sS -L -o /tmp/root.html -w '%{http_code}\n' "$BASE/"
curl -sS -L -o /tmp/docs.html -w '%{http_code} %{content_type}\n' "$BASE/docs"
```

### 10.6 Model/demo path smoke

Useful endpoints:

```bash
BASE=https://mirai-doe-production.up.railway.app
PROJECT=pem_fuel_cell_real_cathode_degradation

curl -sS "$BASE/projects"
curl -sS "$BASE/projects/$PROJECT/schema"
curl -sS "$BASE/projects/$PROJECT/bo/state"
curl -sS "$BASE/projects/$PROJECT/model-quality/summary"
```

Observed during earlier verification:

- `/projects/$PROJECT/schema` returned `200`;
- `/projects/$PROJECT/bo/state` returned `200`;
- `/projects/$PROJECT/model-quality/summary` returned `400` saying model quality was not available yet for that project;
- this should be investigated before claiming the complete demo lifecycle works on Railway.

---

## 11. Known Risks and Open Questions

### 11.1 Production Clerk is not fully configured

Railway still has:

```text
CLERK_AUTH_REQUIRED=false
```

Before a true production/pilot auth posture, configure Clerk production instance and allowed origins/callbacks.

Railway URL to add to Clerk allowed origins/callbacks:

```text
https://mirai-doe-production.up.railway.app
```

Then configure production env vars and set:

```text
CLERK_AUTH_REQUIRED=true
```

### 11.2 Single-container state is not durable

The single-container Railway image is good for bootstrap/demo smoke testing. It is not sufficient for durable client data unless all writable state moves to Railway Postgres/object storage or another external durable layer.

The current docs call this a **Level 2 pilot**. Treat it that way.

### 11.3 Demo artifacts are local-runtime-derived

The Railway image currently expects local MLflow/reference artifacts:

```text
backend/mlruns
data/reference/pem_fuel_cell_cathode_degradation
backend/data-minio/workspaces
```

These are ignored by Git but included by `.railwayignore` for upload. That can work operationally, but it is fragile:

- a fresh checkout may not have the artifacts;
- another machine may deploy a different artifact set;
- accidental local artifact drift can affect deployment.

Recommended future improvement:

- create a small, explicit, versioned demo artifact package;
- or publish artifacts to durable object storage;
- or generate/pull demo artifacts during deployment from a controlled source.

### 11.4 Frontend API default may surprise local Vite users

Current default points to localhost backend only when browser port is `3000`:

```ts
window.location.port === '3000' ? 'http://localhost:8000' : ''
```

Vite default is usually `5173`. If local API calls fail, set:

```text
VITE_API_URL=http://localhost:8000
```

### 11.5 FastAPI docs disabled by route removal, not protected auth

When docs are disabled, `/docs`, `/redoc`, and `/openapi.json` fall through to SPA routing. This prevents docs exposure, but if you prefer explicit `404`, adjust static route fallback behavior.

### 11.6 Dependency/security warnings

Frontend `npm` reported:

```text
17 vulnerabilities (6 moderate, 11 high)
```

These were pre-existing or dependency-tree warnings surfaced during install/build. Do not run `npm audit fix --force` blindly because it may introduce breaking changes. Review separately.

---

## 12. Suggested Commit Breakdown

When you are ready, consider splitting commits instead of one large commit.

### Commit 1: Railway deployment scaffolding

Candidate files:

```text
Dockerfile.railway
.railwayignore
.dockerignore
railway.toml
.gitignore
```

### Commit 2: Clerk auth frontend/backend wiring

Candidate files:

```text
frontend/package.json
frontend/package-lock.json
frontend/src/main.tsx
frontend/src/lib/api.ts
backend/pyproject.toml
backend/uv.lock
backend/app/auth.py
backend/app/main.py
backend/tests/test_api.py
```

### Commit 3: Workspace storage/control-plane

Candidate files:

```text
backend/app/services/data_intake.py
backend/app/services/workspace_storage.py
backend/db/README.md
backend/db/migrations/001_workspace_control_plane.sql
backend/db/seeds/001_seed_demo_control_plane.sql
backend/tests/test_workspace_storage.py
```

### Commit 4: Docs/plans

Candidate files:

```text
docs/railway-level-2-pilot.md
docs/agent-plans/to-implement/clerk-installation-prompt.md
docs/agent-plans/to-implement/railway-clerk-postgres-master-plan.md
docs/agent-plans/to-implement/sql-s3-implementation/
docs/agent-plans/to-implement/railway-brainstorm-bruno.md
```

Then decide what to do with:

```text
docs/agent-plans/to-implement/sql-backed-lifecycle-management-plan.md
```

It is currently deleted.

---

## 13. Command Reference

### Git review

```bash
git status --short
git diff --stat
git ls-files --others --exclude-standard
git check-ignore -v .env.local frontend/.env.local backend/mlruns/models data/reference/pem_fuel_cell_cathode_degradation/model_table.csv
```

### Local build/test

```bash
cd frontend && npm run build
cd backend && uv run pytest -q
```

### Clerk

```bash
clerk --version
clerk auth login
cd frontend && clerk doctor
cd frontend && clerk env pull --app app_3EvAvu6InOCLDY2f6ANY6zhm07i
```

### Railway

```bash
railway status
railway variables --service mirai-doe --environment production --json
railway up --service mirai-doe --environment production --detach --json --message "message"
railway deployment list --service mirai-doe --environment production
railway logs --service mirai-doe --environment production --lines 220
railway domain --service mirai-doe --environment production --port 8000 --json
```

### Docker

```bash
docker build -f Dockerfile.railway -t mirai-doe-railway .
docker build --no-cache -f Dockerfile.railway -t mirai-doe-railway-clean .
docker run --rm -p 8000:8000 -e CLERK_AUTH_REQUIRED=false -e FASTAPI_DOCS_PUBLIC=false -e CLERK_DEFAULT_WORKSPACE_ID=fraunhofer mirai-doe-railway
```

---

## 14. Recommended Next Steps

1. Review this document and the dirty worktree.
2. Decide whether the local artifact-based Railway image is acceptable for the pilot.
3. Run:

   ```bash
   cd frontend && npm run build
   cd ../backend && uv run pytest -q
   docker build -f Dockerfile.railway -t mirai-doe-railway .
   ```

4. Smoke-test local Clerk signup/signin.
5. Smoke-test the Docker image locally.
6. If satisfied, stage files in logical groups.
7. Configure Clerk production instance:
   - allowed origin: `https://mirai-doe-production.up.railway.app`
   - production publishable key
   - production issuer/JWKS/audience as needed
8. Set Railway production Clerk vars.
9. Flip:

   ```text
   CLERK_AUTH_REQUIRED=true
   ```

10. Redeploy and verify unauthenticated protected endpoints return `401`.
11. Investigate Railway model-quality path returning `400` before demoing full lifecycle.

---

## 15. Final Notes

The current deployment is a useful milestone: the Railway service builds, deploys, serves the SPA, exposes health endpoints, and can run with safe bootstrap auth disabled. The main remaining work is hardening the deployment from “bootstrap demo image” to “pilot-safe durable environment” by finalizing Clerk production config and externalizing/pinning stateful artifacts.
