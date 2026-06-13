# Railway Deployment

Railway is the active Level 2 deployment target for Mirai DoE.

Use Railway-native primitives instead of running Kubernetes inside Railway:

- App service: React SPA + FastAPI container.
- Postgres service: workspace/project metadata, artifact pointers, and optional MLflow backend store.
- Object storage buckets: S3-compatible durable storage for datasets, preprocessing artifacts, MLflow artifacts, ONNX models, BO outputs, and reviews.
- MLflow service: separate `mirai-mlflow` tracking/UI service with Postgres backend store and S3 artifact root.
- Optional support services: a tightly controlled Postgres/object-browser UI if needed for demos.

## Storage layout

Every durable object must be scoped by workspace and project. Preferred bucket roots:

```text
s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/...
s3://mirai-batteries-demo/workspaces/battery-demo/projects/battery_tabular_doe_demo/...
```

A single shared bucket is acceptable only if hard workspace/project prefixes are preserved, for example:

```text
s3://mirai-demo-artifacts/workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/...
s3://mirai-demo-artifacts/workspaces/battery-demo/projects/battery_tabular_doe_demo/...
```

Do not use unscoped global artifact paths. Local developer mirrors/caches, if needed, belong under ignored `backend/.object-storage-local/`; legacy `backend/data-minio` contents should be renamed there rather than uploaded wholesale.

## Current non-secret resources

- App service: `mirai-doe` (`42b63012-f816-45d9-98b6-11dac80dff0f`).
- Postgres service: `Postgres` (`e35cb567-d10b-4999-ab59-44bcd1139e07`).
- Fuel-cell bucket: `mirai-fuel-cells-demo` (`7c878c8c-e7cd-4f8b-ab18-ca0d95cb44af`, `sjc`).
- Battery bucket: `mirai-batteries-demo` (`3be7e99f-65a8-458d-8fa1-310ce256ec33`, `sjc`).

Do not record bucket credentials here. Store credentials only in Railway variables or ignored local env files.

## Clerk dev-auth demo cutover

The current demo cutover uses Clerk development auth, not production Clerk keys.

Railway service `mirai-doe` should have these non-secret auth values plus the dev publishable key set as Railway variables:

```text
CLERK_AUTH_REQUIRED=true
FASTAPI_DOCS_PUBLIC=false
CLERK_ISSUER=https://square-snail-89.clerk.accounts.dev
CLERK_JWT_ISSUER=https://square-snail-89.clerk.accounts.dev
CLERK_JWKS_URL=https://square-snail-89.clerk.accounts.dev/.well-known/jwks.json
CLERK_JWT_LEEWAY_SECONDS=5
MIRAI_STATIC_DIR=/app/static
```

The Clerk dev dashboard must define custom JWT template `jwt-doe-template` and the frontend requests it with `getToken({ template: "jwt-doe-template" })`. The backend authorizes only from the verified top-level `workspace_id` JWT claim. For the existing demo user, use private metadata `workspace_id=fraunhofer` and `role=demo_fuel_cell`.

## Artifact bootstrap

Preview intended object uploads without secrets:

```bash
python3 scripts/bootstrap_demo_artifacts.py --project all --dry-run
```

For the current fuel-cell demo, the operator upload used Railway-injected bucket variables and a temporary `boto3` venv:

```bash
python3 scripts/bootstrap_demo_artifacts.py --project fuel-cell --dry-run
railway run --service mirai-doe /tmp/mirai-boto3-operator-venv/bin/python scripts/bootstrap_demo_artifacts.py --project fuel-cell --upload
```

Uploaded fuel-cell objects are scoped under:

```text
workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/
workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/
```

Battery upload remains deferred; the battery bucket should remain empty. Real uploads should only run from an operator shell with Railway bucket credentials in environment variables. Do not pass credentials on the command line, and do not upload `backend/data-minio/intake` or `backend/.object-storage-local/legacy-data-minio/intake` wholesale.

## Postgres runtime control plane

Railway's `postgres-volume` is attached to the managed `Postgres` service, not to `mirai-doe`. The app and MLflow services connect with Postgres URLs.

Current migration strategy is explicit operator-applied SQL:

```bash
psql "$DATABASE_URL" -f backend/db/migrations/001_workspace_control_plane.sql
psql "$DATABASE_URL" -f backend/db/migrations/002_runtime_control_plane.sql
psql "$DATABASE_URL" -f backend/db/seeds/002_seed_fraunhofer_fuel_cell_runtime.sql
```

Use `002_seed_fraunhofer_fuel_cell_runtime.sql` for this Clerk/Fraunhofer runtime cutover. It intentionally excludes battery rows from the runtime query path.

`mirai-doe` should receive:

```text
DATABASE_URL                         # Railway Postgres app/control-plane connection
MIRAI_REQUIRE_POSTGRES_CONTROL_PLANE=true  # enable after migrations/seeds are applied
OBJECT_STORAGE_BACKEND=s3            # production/demo object storage is Railway buckets
MLFLOW_TRACKING_URI                  # tracking service URI once mirai-mlflow is available
```

## MLflow service

A separate Railway service `mirai-mlflow` should be created from `Dockerfile.mlflow`.

Expected command is baked into the Dockerfile:

```bash
mlflow server \
  --host 0.0.0.0 \
  --port ${PORT:-5000} \
  --backend-store-uri "$MLFLOW_BACKEND_STORE_URI" \
  --artifacts-destination "$MLFLOW_ARTIFACT_ROOT" \
  --serve-artifacts
```

`mirai-mlflow` needs:

```text
MLFLOW_BACKEND_STORE_URI             # Postgres SQLAlchemy URI; secret-bearing
MLFLOW_ARTIFACT_ROOT                 # Fraunhofer bucket root, e.g. s3://<bucket>/workspaces/fraunhofer/mlflow-artifacts/
MIRAI_FRAUNHOFER_S3_BUCKET
MIRAI_FRAUNHOFER_S3_ENDPOINT
MIRAI_FRAUNHOFER_S3_ACCESS_KEY_ID
MIRAI_FRAUNHOFER_S3_SECRET_ACCESS_KEY
MIRAI_FRAUNHOFER_S3_REGION
```

Do not expose MLflow UI publicly for real client data unless it is protected by an approved auth/private-network mechanism.

## Operator visibility

- Postgres: use Railway connection details with local `psql`, TablePlus, or DBeaver.
- Buckets: use Railway bucket views, S3-compatible tools, or bootstrap/listing scripts.
- MLflow UI: use the protected/private `mirai-mlflow` endpoint for experiment/run inspection.
- Temporary admin UIs must not be public/unauthenticated and must include a removal or disable step.

See `docs/railway-level-2-pilot.md` for the detailed Level 2 contract and `plans/to-implement/railway-stateful-cai-pattern-plan.md` for the implementation plan.
