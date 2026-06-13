# Next Steps Summary

_Last updated: 2026-06-12_

This is the short action-oriented companion to `RAILWAY_CLERK_DEPLOYMENT_HANDOFF.md`.

---

## 1. Review before staging

Start with the dirty worktree:

```bash
git status --short
git diff --stat
```

Important groups to inspect manually:

### Railway/deployment

```text
Dockerfile.railway
.railwayignore
.dockerignore
railway.toml
.gitignore
```

### Clerk/auth

```text
frontend/src/main.tsx
frontend/src/lib/api.ts
frontend/package.json
frontend/package-lock.json
backend/app/auth.py
backend/app/main.py
backend/tests/test_api.py
```

### Workspace/storage/control-plane

```text
backend/app/services/data_intake.py
backend/app/services/workspace_storage.py
backend/db/
backend/tests/test_workspace_storage.py
```

### Docs/plans

```text
RAILWAY_CLERK_DEPLOYMENT_HANDOFF.md
NEXT_STEPS.md
docs/railway-level-2-pilot.md
docs/agent-plans/to-implement/
```

---

## 2. Re-run validation locally

```bash
cd frontend && npm run build
cd ../backend && uv run pytest -q
cd ..
docker build -f Dockerfile.railway -t mirai-doe-railway .
```

Optional no-cache Docker check:

```bash
docker build --no-cache -f Dockerfile.railway -t mirai-doe-railway-clean .
```

---

## 3. Verify local Clerk UX

```bash
direnv reload
direnv exec . bash -lc 'test -n "$VITE_CLERK_PUBLISHABLE_KEY" && echo ok || echo missing'
cd frontend
npm run dev
```

Then open the local Vite URL and verify:

- signed-out landing page appears;
- **Sign up** is visible;
- **Sign in** is visible;
- signup/signin succeeds;
- app appears after auth;
- user profile button appears top-right.

If API calls fail locally, ensure:

```text
VITE_API_URL=http://localhost:8000
```

is available to the frontend/dev shell.

---

## 4. Smoke-test Docker image locally

```bash
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

- `/` returns React SPA HTML;
- `/health` and `/api/health` return healthy JSON;
- docs/openapi do not expose FastAPI docs when `FASTAPI_DOCS_PUBLIC=false`.

---

## 5. Railway redeploy only after review

Check Railway context first:

```bash
railway status
```

Confirm it is linked to:

```text
Project: satisfied-growth
Environment: production
Service: mirai-doe
```

Deploy explicitly:

```bash
railway up \
  --service mirai-doe \
  --environment production \
  --detach \
  --json \
  --message "reviewed railway clerk deployment changes"
```

Poll:

```bash
railway deployment list --service mirai-doe --environment production
```

If failed:

```bash
railway logs --service mirai-doe --environment production --lines 220
```

Smoke-test:

```bash
BASE=https://mirai-doe-production.up.railway.app
curl -sS -L "$BASE/health"
curl -sS -L "$BASE/api/health"
curl -sS -L -o /tmp/root.html -w '%{http_code}\n' "$BASE/"
```

---

## 6. Clerk production setup before real pilot auth

Before enabling required auth on Railway:

1. Configure Clerk production instance.
2. Add allowed origin/callback for:

```text
https://mirai-doe-production.up.railway.app
```

3. Set Railway variables:

```text
VITE_CLERK_PUBLISHABLE_KEY=<production publishable key>
CLERK_JWT_ISSUER=<production issuer>
CLERK_JWKS_URL=<optional explicit JWKS URL>
CLERK_JWT_AUDIENCE=<optional audience>
```

4. Only then flip:

```text
CLERK_AUTH_REQUIRED=true
```

5. Redeploy and verify protected endpoints return `401` when unauthenticated.

---

## 7. Investigate before demoing full lifecycle

These Railway checks passed previously:

- SPA served
- `/health`
- `/api/health`
- project schema endpoint
- BO state endpoint

This still needs investigation:

```text
/projects/pem_fuel_cell_real_cathode_degradation/model-quality/summary
```

It returned a `400` saying model quality was not available yet. Resolve this before claiming full model-quality lifecycle works on Railway.

---

## 8. Recommended commit breakdown

When ready, stage in logical groups.

### Commit 1: Railway deployment scaffold

```text
Dockerfile.railway
.railwayignore
.dockerignore
railway.toml
.gitignore
```

### Commit 2: Clerk auth wiring

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

### Commit 3: Workspace/control-plane changes

```text
backend/app/services/data_intake.py
backend/app/services/workspace_storage.py
backend/db/
backend/tests/test_workspace_storage.py
```

### Commit 4: Documentation/plans

```text
RAILWAY_CLERK_DEPLOYMENT_HANDOFF.md
NEXT_STEPS.md
docs/railway-level-2-pilot.md
docs/agent-plans/to-implement/
```

---

## 9. Do not commit

Double-check these stay ignored/untracked:

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
node_modules/
frontend/dist/
backend/.venv/
```
