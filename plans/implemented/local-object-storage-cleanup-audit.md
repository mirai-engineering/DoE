# Plan: Clean Up Legacy Local Object Storage Folders

## Context

The DoE demo has migrated to Railway:

- Railway S3-compatible buckets are the production/demo object-storage source of truth.
- Railway Postgres stores workspace/project/runtime metadata and durable object pointers.
- Railway MLflow provides the experiment tracking server/UI.
- Local machines may still train models and may keep a local object-storage mirror/cache, but that mirror must be clearly named and gitignored.

The current repo still has legacy local object-store folders, especially `backend/data-minio/`. Locally this folder is large (~849 MB) and contains old upload/session/raw ZIP/cache data. Most of it is ignored already, but one small file is tracked:

```text
backend/data-minio/workspaces/fraunhofer/workspace.json
```

Several code paths and Dockerfiles still refer to `backend/data-minio` as the default `DOE_OBJECT_STORE_ROOT`, so deleting it blindly would risk breaking local fallback behavior or Docker builds.

## Approach

Do a staged cleanup rather than a blind delete:

1. Treat `backend/data-minio/` as a **legacy local bucket/cache**, not source code.
2. Rename/move useful local-only contents into a clearly gitignored folder:

   ```text
   backend/.object-storage-local/legacy-data-minio/
   ```

   or, for data worth keeping as a mirror of Railway buckets, into the preferred bucket-shaped structure:

   ```text
   backend/.object-storage-local/mirai-fuel-cells-demo/workspaces/fraunhofer/projects/...
   backend/.object-storage-local/mirai-batteries-demo/workspaces/...
   ```

3. Move tiny intentional seed/test files out of `data-minio` into explicit tracked locations.
4. Delete only folders that are confirmed unused generated traces, empty directories, or duplicate caches.
5. Update runtime defaults/docs so new local development uses `backend/.object-storage-local`, while Railway production uses S3/Postgres/MLflow.
6. Remove Docker/Railway packaging assumptions that depend on `backend/data-minio` once tests pass.

## Files to modify

Likely code/config/docs changes:

- `.gitignore`
- `.railwayignore`
- `Dockerfile.railway`
- `backend/Dockerfile`
- `backend/app/services/workspaces.py`
- `backend/app/services/data_intake.py`
- `backend/app/services/experiment_log.py`
- `backend/app/services/model_quality.py`
- `backend/app/services/project_registry.py`
- `backend/app/services/workspace_storage.py`
- `env.example`
- `README.md`
- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`
- `backend/ml_lifecycle/MLFLOW_README.md`
- `deployments/railway/README.md`

Likely moved/created paths:

- `backend/seeds/object_storage/workspaces/fraunhofer/workspace.json`
- `backend/tests/fixtures/object_storage/` if tiny test fixtures are needed
- `backend/.object-storage-local/` as ignored local mirror/cache

## Reuse

Existing utilities/patterns to reuse:

- `backend/app/services/workspace_storage.py`
  - `WorkspaceStorageConfig`
  - `workspace_scoped_path`
  - `validate_workspace_object_key`
  - `put_workspace_object`
  - `get_workspace_object`
  - `list_workspace_objects`
- `backend/db/seeds/001_seed_demo_control_plane.sql`
- `backend/db/seeds/002_seed_fraunhofer_fuel_cell_runtime.sql`
- `scripts/bootstrap_demo_artifacts.py`
  - already refuses wholesale upload of `backend/data-minio/intake`
- Existing tests:
  - `backend/tests/test_workspace_storage.py`
  - `backend/tests/test_bootstrap_demo_artifacts.py`
  - `backend/tests/test_api.py`

## Skill mapping

Per `AGENTS.md`, available skills were checked before finalizing this plan:

```text
bayesian-optimization-feature
clerk-backend-api
clerk-cli
clerk-custom-ui
clerk-orgs
clerk-react-patterns
clerk-setup
clerk-testing
clerk-webhooks
github-mcp-workflow
project-artifact-cleanup
scientific-ui-clarity
surrogate-model-debugging
use-railway
```

Primary skills for this cleanup:

| Task area | Skill(s) to apply | Why |
|---|---|---|
| Inventory old local bucket folders, generated intake/session artifacts, BO configs, experiment logs, model-quality reviews, MLflow file-store state | `project-artifact-cleanup` | This is the main skill for runtime artifact cleanup. It requires inventory before deletion and protects preserved PEM/Fraunhofer projects and models. |
| Preserve/delete decisions for `pem_fuel_cell_demo`, `pem_fuel_cell_real_cathode_degradation`, MLflow experiment/model folders | `project-artifact-cleanup` | Enforces the preserve list and prevents accidental deletion of approved demo/reference artifacts. |
| Updating local object-storage defaults and validating logical object keys vs local paths | `project-artifact-cleanup`, `surrogate-model-debugging` | Cleanup touches artifact paths that may affect preprocessing/training/serving; surrogate-model checks reduce risk of breaking ONNX/preprocessing artifact resolution. |
| Moving small seed metadata out of `backend/data-minio` into explicit seed/fixture paths | `project-artifact-cleanup` | Keeps source-controlled seed data distinct from generated runtime/customer state. |
| Removing Docker/Railway dependency on `backend/data-minio` and local `backend/mlruns` | `use-railway`, `project-artifact-cleanup` | Railway production must rely on Postgres/S3/MLflow, while cleanup skill ensures packaged demo artifacts are not removed before replacement behavior exists. |
| Verifying Railway app still uses Postgres/S3/MLflow after cleanup | `use-railway`, `clerk-testing` where signed-in checks are needed | Railway smoke checks validate deploy/runtime. Clerk testing is only needed for authenticated Fraunhofer-only visibility checks. |
| Updating README/data-contract/MLflow docs to explain repo vs Railway buckets vs local mirror | `project-artifact-cleanup`, `use-railway` | Documents artifact ownership and deployment boundaries. |
| Backend regression tests for artifact resolution, project registry, workspace storage, and API scoping | `project-artifact-cleanup`, `surrogate-model-debugging`, `clerk-testing` for auth-scoped flows | Ensures cleanup does not break artifact discovery, model serving, or workspace auth behavior. |

Skills intentionally not used for this plan unless scope changes:

- `bayesian-optimization-feature`: only use if changing BO algorithms/UI, not just moving legacy BO config files.
- `scientific-ui-clarity`: only use if the cleanup touches scientist-facing UI text or visuals.
- `clerk-backend-api`, `clerk-cli`, `clerk-setup`, `clerk-orgs`, `clerk-react-patterns`, `clerk-custom-ui`, `clerk-webhooks`: not needed for local folder cleanup; use only if changing Clerk config, auth flows, organizations, or webhooks.
- `github-mcp-workflow`: not needed unless creating/publishing GitHub branches, PRs, issues, or releases.

## Folder decisions

| Current folder | Classification | Action |
|---|---|---|
| `backend/data-minio/intake/` | Legacy local upload/session/raw-artifact cache | Move/rename to ignored `backend/.object-storage-local/legacy-data-minio/intake/` unless user confirms it can be deleted. Do not track. Do not upload wholesale. |
| `backend/data-minio/bo_configs/` | Legacy local BO config cache | Move to ignored legacy cache or delete if superseded by Postgres and not needed locally. |
| `backend/data-minio/experiment_logs/` | Legacy local BO experiment log cache | Move to ignored legacy cache or delete if superseded by Postgres and not needed locally. |
| `backend/data-minio/model_quality_reviews/` | Legacy local scientist-review cache | Move to ignored legacy cache unless migrated to Postgres/S3. |
| `backend/data-minio/workspaces/default-workspace/` | Generated/default local trace | Delete if no local session depends on it; otherwise move to ignored legacy cache. |
| `backend/data-minio/workspaces/mirai-engineering/` | Generated local trace | Delete if no local session depends on it; otherwise move to ignored legacy cache. |
| `backend/data-minio/workspaces/fraunhofer/workspace.json` | Tiny tracked seed | Move to `backend/seeds/object_storage/workspaces/fraunhofer/workspace.json` or remove if SQL seeds fully replace it. |
| `backend/mlruns/` | Local MLflow file-store fallback/cache | Keep ignored for local-only development. Stop packaging into Railway app once Railway MLflow is required. |
| `data/reference/pem_fuel_cell_cathode_degradation/...` | Reference/bootstrap source data | Keep only small, intentional, non-sensitive demo/reference assets; do not mix with runtime object-store cache. |

## Implementation steps

- [ ] Inventory exact local legacy contents before moving/deleting:
  - `find backend/data-minio -maxdepth 5 -print`
  - `git ls-files backend/data-minio`
  - `git status --short --ignored backend/data-minio`
  - `du -sh backend/data-minio/*`
- [ ] Confirm preserve list:
  - preserve `pem_fuel_cell_real_cathode_degradation` data unless already uploaded and no local copy is needed;
  - preserve tiny Fraunhofer seed until Docker/runtime no longer needs it;
  - do not invent or keep battery artifacts as real data.
- [ ] Add/confirm `.gitignore` entries:
  - `backend/.object-storage-local/`
  - legacy generated folders under `backend/data-minio/` until removed.
- [ ] Move tiny intentional seed data out of `backend/data-minio`:
  - create `backend/seeds/object_storage/workspaces/fraunhofer/workspace.json`;
  - update code/tests/Docker references accordingly;
  - remove tracked `backend/data-minio/workspaces/fraunhofer/workspace.json` after replacement passes tests.
- [ ] Introduce explicit local-vs-S3 storage configuration:
  - `OBJECT_STORAGE_BACKEND=s3|local`;
  - `LOCAL_OBJECT_STORAGE_ROOT=backend/.object-storage-local`;
  - keep `DOE_OBJECT_STORE_ROOT` only as backward-compatible deprecated alias during migration.
- [ ] Update local filesystem defaults in services from `backend/data-minio` to `backend/.object-storage-local`:
  - `workspaces.py`;
  - `data_intake.py`;
  - `experiment_log.py`;
  - `model_quality.py`;
  - `project_registry.py`.
- [ ] Ensure Postgres/S3 remains production source of truth:
  - Railway should run with S3/Postgres env and not depend on local object-store paths;
  - Postgres rows should store logical object keys such as `workspaces/fraunhofer/projects/.../model.onnx`, never absolute local paths.
- [ ] Update `Dockerfile.railway`:
  - remove `COPY backend/data-minio/workspaces ./data-minio/workspaces` once seed is moved or no longer required;
  - remove Fraunhofer `workspace.json` build assertion;
  - remove `COPY backend/mlruns ./mlruns` once Railway MLflow is mandatory and app startup does not require local registry state.
- [ ] Update legacy `backend/Dockerfile` similarly or clearly mark it local-only.
- [ ] Rename/move old local bucket data:
  - move useful local cache to `backend/.object-storage-local/legacy-data-minio/` or bucket-shaped mirror folders;
  - delete only clearly unused generated traces after inventory and preserve-list check.
- [ ] Update docs/env examples:
  - `README.md` local storage section;
  - `env.example`;
  - `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`;
  - `backend/ml_lifecycle/MLFLOW_README.md`;
  - `deployments/railway/README.md`.
- [ ] Run validation.
- [ ] Only after successful validation, remove the now-empty/obsolete `backend/data-minio/` tree from tracked repo state.

## Verification

Run local checks:

```bash
cd backend && uv run pytest -q
cd ../frontend && npm run build
```

Run storage-specific checks:

```bash
git ls-files backend/data-minio
find backend/.object-storage-local -maxdepth 4 -type f | head
```

Expected outcomes:

- `git ls-files backend/data-minio` is empty after seed migration.
- `backend/.object-storage-local/` remains ignored.
- Tests do not require large local object payloads.
- Railway app image no longer depends on `backend/data-minio` or local `backend/mlruns` for production/demo runtime.
- Railway production still serves Fraunhofer fuel-cell demo from Postgres/S3/MLflow.

Run production smoke after redeploy if Docker/Railway files change:

```bash
curl -fsS https://mirai-doe-production.up.railway.app/health
curl -fsS https://mirai-doe-production.up.railway.app/api/health
```

Signed-in Clerk checks still require an operator/browser token:

- Fraunhofer user sees only `pem_fuel_cell_real_cathode_degradation`.
- Direct battery access returns `403` or `404`.

## Safety rules

- Do not delete `backend/data-minio/` wholesale in the first implementation step.
- Do not commit large datasets, raw ZIPs, generated training artifacts, processed datasets, reports, or real client/project data.
- Do not upload `backend/data-minio/intake` wholesale to Railway buckets.
- Do not rely on local absolute paths in Postgres metadata.
- Keep local mirror/cache folders gitignored.
- If any local data may be needed later but is not source code, move it to ignored `backend/.object-storage-local/legacy-data-minio/` rather than deleting it immediately.
