# Postgres + S3 + MLflow Railway Runtime Cutover Plan

## Execution orchestration and skills

Before any implementation edits, run a read-only discovery pass and use agent support where available:

1. If the agent runner is available, first list configured agents/chains.
2. Choose an available scout-style/read-only discovery agent or chain if one exists; do not invent an agent name if none is configured.
3. Scout must inspect current bootstrap-script state, Railway/Postgres/MLflow-related config, DB migrations/seeds, storage helpers, training code, and current tests before implementation starts.
4. Use the scout output to confirm this plan's tasks are still valid, identify reusable utilities, and avoid duplicating existing code.
5. After scout discovery, run focused implementation/review steps or the current task at hand with the relevant skills below.

Available project skills checked:

- `.pi/skills`: `bayesian-optimization-feature`, `clerk-backend-api`, `clerk-cli`, `clerk-custom-ui`, `clerk-orgs`, `clerk-react-patterns`, `clerk-setup`, `clerk-testing`, `clerk-webhooks`, `github-mcp-workflow`, `project-artifact-cleanup`, `scientific-ui-clarity`, `surrogate-model-debugging`, `use-railway`.
- User/global skills: `api-and-interface-design`, `browser-testing-with-devtools`, `ci-cd-and-automation`, `code-review-and-quality`, `code-simplification`, `context-engineering`, `debugging-and-error-recovery`, `deprecation-and-migration`, `documentation-and-adrs`, `doubt-driven-development`, `frontend-ui-engineering`, `git-workflow-and-versioning`, `idea-refine`, `incremental-implementation`, `interview-me`, `performance-optimization`, `planning-and-task-breakdown`, `security-and-hardening`, `shipping-and-launch`, `source-driven-development`, `spec-driven-development`, `test-driven-development`, `using-agent-skills`.

Skill mapping:

| Work area | Primary skills to use |
|---|---|
| Railway service/env/deploy topology | `use-railway`, `shipping-and-launch`, `ci-cd-and-automation`, `security-and-hardening` |
| Postgres runtime control plane and migrations | `api-and-interface-design`, `deprecation-and-migration`, `test-driven-development`, `security-and-hardening` |
| S3/object storage and artifact bootstrap | `project-artifact-cleanup`, `use-railway`, `test-driven-development`, `security-and-hardening` |
| MLflow backend/artifacts/UI service | `ci-cd-and-automation`, `shipping-and-launch`, `surrogate-model-debugging`, `use-railway` |
| In-process training loop integration | `surrogate-model-debugging`, `bayesian-optimization-feature`, `incremental-implementation`, `test-driven-development` |
| Clerk workspace authorization verification | `clerk-backend-api`, `clerk-testing`, `security-and-hardening`, `browser-testing-with-devtools` |
| API contract changes | `api-and-interface-design`, `spec-driven-development`, `test-driven-development` |
| Documentation/handoff | `documentation-and-adrs`, `git-workflow-and-versioning`, `code-review-and-quality` |

## Context

The current Railway demo has Clerk dev auth, per-workspace S3 buckets, and fuel-cell artifacts uploaded under the Fraunhofer workspace prefix. However, the app still mostly discovers projects/artifacts from packaged files and local/static registries. The existing Railway `postgres-volume` belongs to the managed Railway Postgres service; it should not be mounted into the FastAPI app container. The app should connect to Postgres via `DATABASE_URL` and use Postgres as the runtime control plane.

Target mental model:

- Clerk JWT provides the trusted `workspace_id`.
- Postgres stores queryable, permission-relevant state: workspaces, projects, datasets, manifests, training runs, model pointers, recommendations, observations, audit logs.
- S3/object storage stores heavy files: raw CSVs, processed Parquet, manifests, ONNX/models, preprocessing JSON, MLflow artifacts, reports, plots, batch outputs.
- FastAPI only reads/writes rows and objects authorized by the verified JWT workspace.
- MLflow UI is available as a separate Railway service, with its backend metadata in Railway Postgres and artifacts in the workspace/user bucket.

User decisions captured:

1. Postgres should become the immediate runtime source of truth.
2. Use MLflow-integrated path: MLflow backend in Postgres, artifacts in S3, Mirai app tables as product-level source of truth.
3. Storage model is one bucket per user/workspace; a workspace/user can have multiple projects. MLflow artifacts for that workspace belong inside that workspace bucket.
4. Seed only the Fraunhofer fuel-cell workspace/project/artifacts now; leave battery out of queryable project lists until the next implementation.
5. Training runs inside the FastAPI app process for now.
6. Create this plan before code changes.

## Approach

Use a two-service Railway architecture, sharing managed Postgres and per-workspace S3 buckets:

```text
Browser
  ├─ Mirai FastAPI/SPA Railway service `mirai-doe`
  │    ├─ DATABASE_URL -> Railway Postgres app/control-plane tables
  │    ├─ MLFLOW_TRACKING_URI -> MLflow tracking service or DB URI
  │    └─ S3 credentials -> per-workspace bucket access
  │
  └─ MLflow UI Railway service `mirai-mlflow`
       ├─ backend-store-uri -> Railway Postgres MLflow DB/schema
       └─ default-artifact-root -> Fraunhofer bucket for current demo
```

Important Railway clarification:

- Do **not** mount `postgres-volume` into the app service.
- Railway's Postgres volume is coupled to the managed `Postgres` service.
- `mirai-doe` and `mirai-mlflow` should connect over Postgres connection variables.

For the current one-user demo, configure MLflow artifact root under the Fraunhofer bucket, for example:

```text
s3://<fraunhofer-bucket>/workspaces/fraunhofer/mlflow-artifacts/
```

For multiple future users/projects, set MLflow experiment `artifact_location` per workspace/project rather than relying only on one global artifact root:

```text
s3://<workspace-bucket>/workspaces/{workspace_id}/projects/{project_id}/mlflow-artifacts/{experiment_name}/
```

Mirai's own `training_runs` and `models` tables remain the product source of truth. MLflow can keep detailed experiment/run metadata and provide UI inspection, but FastAPI should answer product questions from Mirai app tables:

- Which projects can this user see?
- Which dataset is current?
- Which model is champion?
- Which training run produced it?
- Where are the S3 artifacts?

## Files to modify

Likely application files:

- `backend/pyproject.toml` / `backend/uv.lock` — add Postgres/S3 runtime deps such as `psycopg[binary]` or `psycopg2-binary`, SQLAlchemy/Alembic if chosen, and `boto3` or compatible S3 client.
- `backend/app/services/project_registry.py` — replace packaged/static project listing with Postgres-backed queries, falling back only for local dev/tests.
- `backend/app/services/mlflow_registry.py` — configure MLflow tracking/backend and artifact locations for Railway; stop treating durable pointers as pointer-only for seeded fuel-cell state.
- `backend/app/services/workspace_storage.py` — extend from validation-only to object client helpers for per-workspace buckets.
- `backend/app/services/data_intake.py` — persist dataset/session metadata in Postgres and place files in workspace bucket.
- `backend/app/main.py` — ensure all project/dataset/artifact/training/model endpoints resolve through Postgres with workspace scoping.
- `backend/ml_lifecycle/...` — route training outputs to S3 and record `training_runs`/`models` rows.
- `scripts/bootstrap_demo_artifacts.py` — add optional Postgres seeding/backfill of artifact rows for already-uploaded fuel-cell objects.
- `Dockerfile.railway` — include any new runtime dependencies and optionally add an MLflow service command target.
- `railway.toml` or deployment docs — document service-specific start commands.

Likely DB files:

- `backend/db/migrations/002_runtime_control_plane.sql` — add normalized tables for datasets, schemas/manifests, training runs, model registry pointers, recommendations/candidates, observations, audit logs.
- `backend/db/seeds/002_seed_fraunhofer_fuel_cell_runtime.sql` — seed only Fraunhofer + fuel-cell rows and current artifact pointers.
- `backend/db/README.md` — document migration/apply procedure and Railway Postgres connection workflow.

Likely deployment docs:

- `deployments/railway/README.md`
- `docs/railway-level-2-pilot.md`
- `RAILWAY_CLERK_DEPLOYMENT_HANDOFF.md`

Tests:

- `backend/tests/test_api.py`
- `backend/tests/test_workspace_storage.py`
- `backend/tests/test_mlflow_durable_pointers.py`
- new tests for Postgres-backed registry and training-run/model pointer rows.

## Reuse

Existing pieces to reuse rather than replacing wholesale:

- `backend/app/auth.py` — already verifies Clerk JWT and exposes a trusted workspace principal.
- `backend/app/main.py` — already enforces authenticated workspace checks around project routes.
- `backend/app/services/workspace_storage.py` — already validates workspace-scoped object keys and S3 URIs.
- `backend/app/services/mlflow_registry.py` — already centralizes MLflow naming/tracking/model-loading helpers.
- `backend/app/services/project_registry.py` — current API-facing project registry surface; use it as the adapter boundary while changing internals to Postgres.
- `backend/db/migrations/001_workspace_control_plane.sql` — existing base tables and RLS pattern.
- `backend/db/seeds/001_seed_demo_control_plane.sql` — seed style and current Fraunhofer/fuel-cell values, but remove battery from runtime seed for this phase.
- `scripts/bootstrap_demo_artifacts.py` — already uploads fuel-cell artifacts to approved workspace/project S3 prefixes.

## Data model additions

Add or evolve tables so Postgres can answer product-state questions:

### `datasets`

- `dataset_id`
- `workspace_id`
- `project_id`
- `filename`
- `object_uri`
- `schema_hash`
- `manifest_version`
- `row_count`
- `column_count`
- `uploaded_by`
- `status`
- `created_at`

### `schema_manifests`

- `schema_id`
- `workspace_id`
- `project_id`
- `manifest_object_uri`
- `input_columns jsonb`
- `output_columns jsonb`
- `unit_map jsonb`
- `schema_json jsonb`
- `validation_status`
- `created_at`

### `training_runs`

- `training_run_id`
- `workspace_id`
- `project_id`
- `dataset_id`
- `mlflow_run_id`
- `status`
- `started_at`
- `finished_at`
- `best_model_type`
- `metrics_json jsonb`
- `artifact_s3_prefix`
- `created_by`

### `models`

- `model_id`
- `workspace_id`
- `project_id`
- `training_run_id`
- `model_name`
- `version`
- `status`
- `artifact_s3_uri`
- `preprocessing_s3_uri`
- `schema_s3_uri`
- `is_champion`
- `created_at`

### `recommendations`

- `candidate_id`
- `workspace_id`
- `project_id`
- `model_id`
- `input_json jsonb`
- `predicted_outputs_json jsonb`
- `score`
- `rank`
- `status`
- `created_at`

### `observations`

- `observation_id`
- `workspace_id`
- `project_id`
- `candidate_id`
- `dataset_id`
- `input_json jsonb`
- `observed_outputs_json jsonb`
- `source`
- `created_at`
- `validated_by`

### `audit_logs`

- `audit_id`
- `workspace_id`
- `user_id`
- `action`
- `resource_type`
- `resource_id`
- `timestamp`
- `ip_address`

All tables should include indexes on `(workspace_id, project_id)` where relevant and RLS using `current_setting('app.workspace_id', true)` or equivalent connection/session scoping.

## MLflow deployment design

Create a separate Railway service, likely named `mirai-mlflow`, from the same repo/image or a small dedicated MLflow Dockerfile.

Recommended command shape:

```bash
mlflow server \
  --host 0.0.0.0 \
  --port ${PORT:-5000} \
  --backend-store-uri "$MLFLOW_BACKEND_STORE_URI" \
  --artifacts-destination "$MLFLOW_ARTIFACT_ROOT" \
  --serve-artifacts
```

For the current demo:

```text
MLFLOW_BACKEND_STORE_URI=postgresql+psycopg2://.../mlflow-or-schema
MLFLOW_ARTIFACT_ROOT=s3://<fraunhofer-bucket>/workspaces/fraunhofer/mlflow-artifacts/
```

Security note:

- MLflow UI must not be public/unauthenticated for real client data.
- For immediate demo use, either keep it private/internal, protect it with Railway/network access if available, or place it behind an auth proxy before sharing externally.
- Document any temporary exposure and removal step.

Future multi-workspace note:

- One global MLflow service can use per-experiment `artifact_location` to write into each workspace bucket if credentials can access all needed buckets.
- If Railway bucket credentials are isolated per bucket and cannot be safely shared with one central MLflow service, move toward one MLflow service per workspace or make FastAPI the artifact mediator while MLflow stores metadata/pointers.

## Steps

- [ ] 0. List configured agents/chains if the runner is available; run an available scout/read-only discovery pass before edits, with focus on bootstrap-script state, DB migrations/seeds, Railway service config, MLflow hooks, storage helpers, training code, and tests.
- [ ] 1. Confirm Railway Postgres connection strategy: app service uses `DATABASE_URL`; no app volume mount is needed.
- [ ] 2. Decide migration runner approach for this phase: simple SQL scripts via operator command vs app startup migration vs Alembic.
- [ ] 3. Add runtime DB/S3 dependencies needed for Postgres and S3 artifact writes.
- [ ] 4. Add `002_runtime_control_plane.sql` with datasets, schema manifests, training runs, models, recommendations, observations, and audit logs.
- [ ] 5. Add RLS policies and workspace/project indexes for all new tables.
- [ ] 6. Add Fraunhofer-only seed/backfill script for workspace, fuel-cell project, dataset rows, schema manifest row, current training/model pointers, and already uploaded S3 artifact keys.
- [ ] 7. Remove battery from runtime seed/query path for this phase; keep battery docs/placeholders only for future implementation.
- [ ] 8. Implement a small DB access layer that sets `app.workspace_id` per request/transaction before querying RLS-protected tables.
- [ ] 9. Convert `list_projects()` and project detail lookup to query Postgres for the authenticated workspace.
- [ ] 10. Convert artifact-status/model registry responses to read current dataset/training/model pointers from Postgres.
- [ ] 11. Extend workspace storage from validation-only to S3 read/write/list helpers using per-workspace bucket env vars.
- [ ] 12. Update the FastAPI training path to create a `training_runs` row, run existing training in-process, write artifacts to the workspace bucket, update MLflow, and mark the row completed/failed.
- [ ] 13. Configure MLflow experiment creation so the fuel-cell experiment artifact location is under the Fraunhofer bucket/project prefix.
- [ ] 14. Add/update model champion logic: completed training writes `models` rows and sets one champion for a workspace/project.
- [ ] 15. Add audit logging for key actions: project opened, training triggered, artifact status viewed/downloaded, recommendations generated.
- [ ] 16. Create Railway MLflow service `mirai-mlflow` with Postgres backend store and Fraunhofer S3 artifact root.
- [ ] 17. Configure `mirai-doe` `MLFLOW_TRACKING_URI` to point to the MLflow tracking service/URI.
- [ ] 18. Protect or restrict MLflow UI access before using real client data.
- [ ] 19. Update docs/handoff with exact runtime topology, env var names, and known limitations.
- [ ] 20. Run local/backend tests and Railway smoke tests.
- [ ] 21. Apply migrations/seeds to Railway Postgres.
- [ ] 22. Verify signed-in Fraunhofer user sees only fuel-cell project from Postgres.
- [ ] 23. Verify direct battery project access remains `403` or `404` for the Fraunhofer user.
- [ ] 24. Verify MLflow UI shows fuel-cell experiment/run and artifact links resolve to S3-backed artifacts.
- [ ] 25. Verify retraining loop creates Postgres `training_runs`/`models` rows, MLflow run metadata, and S3 artifacts under the Fraunhofer bucket.

## Verification

Local/tests:

```bash
cd backend && uv run pytest -q
cd frontend && npm run build
```

Database verification:

- Apply migrations to a local/test Postgres or Railway Postgres test connection.
- Query as Fraunhofer workspace and confirm only `fraunhofer` rows are visible under RLS.
- Confirm battery rows are absent from the runtime seed for this phase.
- Confirm object URI constraints reject unscoped paths and wrong workspace prefixes.

Railway app verification:

- Signed out:
  - SPA loads.
  - `/projects` returns `401`.
- Signed in as existing Clerk dev user with `workspace_id=fraunhofer`:
  - `/projects` returns only `pem_fuel_cell_real_cathode_degradation`.
  - fuel-cell artifact status reads from Postgres-backed pointers.
  - direct battery project endpoint returns `403` or `404`.

S3 verification:

- Fuel-cell bucket contains:
  - `workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/...`
  - `workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/...`
  - new MLflow/training run artifacts under the Fraunhofer workspace/project prefix.
- Battery bucket remains empty for this phase.

MLflow verification:

- `mirai-mlflow` starts successfully against Railway Postgres.
- MLflow UI is reachable only through the approved protected/private access path.
- Fuel-cell experiment/run appears in MLflow.
- MLflow artifact root points into the Fraunhofer workspace bucket/prefix.
- New in-process FastAPI training creates both:
  - MLflow run/artifacts; and
  - Mirai app `training_runs`/`models` rows.

## Risks and constraints

- Do not print or commit Railway, Clerk, Postgres, or S3 secrets.
- Do not mount Postgres volume into the app; connect via Postgres URL.
- Do not make MLflow UI public for real client data unless protected.
- Per-workspace buckets are clean for isolation, but a single central MLflow service needs credentials capable of writing the relevant workspace bucket. If Railway credentials are per-bucket and not shareable, future multi-user MLflow may require per-workspace MLflow services or FastAPI-mediated artifact writes.
- Running training inside FastAPI is acceptable for this demo, but long-running jobs should later move to a worker service with queue/status tracking.
- Battery project/data remains deferred and should not appear in the existing user's project list in this implementation.
