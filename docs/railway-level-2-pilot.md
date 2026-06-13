# Railway Level 2 Pilot Deployment Notes

Railway single-container deployment is intended for Level 2 virtual isolation, not Level 3 physical tenant isolation.

## Level 2 runtime decision

The active Level 2 pilot runtime is Railway-native:

- Railway app service runs the Mirai React SPA and FastAPI backend.
- Railway Postgres stores workspace, project, control-plane, and artifact-pointer metadata.
- Railway S3-compatible object storage stores durable datasets, preprocessing artifacts, MLflow artifacts, ONNX models, BO files, and review files.
- Optional Railway services may expose MLflow or admin/debug views only when explicitly approved and protected.

Do **not** run `kind` or Kubernetes inside Railway for Level 2. `kind` is useful for local Kubernetes development and future prod-like experiments, but nested Kubernetes/Docker-in-Docker inside Railway adds runtime, networking, volume, and debugging complexity without delivering Level 3 physical tenant isolation. Future Level 3 work should use a managed Kubernetes or cloud-native runtime with namespace/cluster boundaries, network policies, external secrets, and per-tenant IAM; it should not be presented as part of this Railway Level 2 pilot.

## Canonical demo IDs

Use stable IDs that are safe for Postgres rows, object prefixes, URLs/API identifiers, and Clerk workspace or organization mapping.

| Demo | Workspace ID | Project ID | Preferred bucket/root |
|---|---|---|---|
| Fuel-cell / Fraunhofer | `fraunhofer` | `pem_fuel_cell_real_cathode_degradation` | `mirai-fuel-cells-demo` |
| Battery / generic tabular DoE | `battery-demo` | `battery_tabular_doe_demo` | `mirai-batteries-demo` |

The fuel-cell project is the existing PEM adapter demo and must continue to feed the generic tabular DoE lifecycle. The battery project is the second generic tabular DoE demo workspace. The exact battery dataset/model source is still an explicit open question until the user confirms it; do not invent or upload a dataset as part of the architecture documentation step.

## Object storage layout

Preferred Level 2 layout is one object bucket per demo workspace, with every object under a workspace/project prefix:

```text
s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/
  intake/
  canonical/
  preprocessing/
  mlflow-artifacts/
  onnx/
  bo/
  reviews/

s3://mirai-batteries-demo/workspaces/battery-demo/projects/battery_tabular_doe_demo/
  intake/
  canonical/
  preprocessing/
  mlflow-artifacts/
  onnx/
  bo/
  reviews/
```

If Railway account/product limits require a single bucket, use hard workspace roots instead:

```text
s3://mirai-demo-artifacts/workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/...
s3://mirai-demo-artifacts/workspaces/battery-demo/projects/battery_tabular_doe_demo/...
```

Unscoped global artifact paths are not allowed. Object pointers should include enough workspace/project context to reject cross-workspace access and to map cleanly to future Level 3 isolation, where these bucket roots can become per-tenant buckets, IAM policies, Kubernetes namespaces, or dedicated service accounts.

## Railway resource summary

Current non-secret Railway resources for this pilot:

| Resource | Name | ID | Region | Notes |
|---|---|---|---|---|
| App service | `mirai-doe` | `42b63012-f816-45d9-98b6-11dac80dff0f` | `sfo` | React SPA + FastAPI service. |
| Postgres service | `Postgres` | `e35cb567-d10b-4999-ab59-44bcd1139e07` | Railway-managed | Metadata/control-plane database. |
| Fuel-cell Railway bucket resource | `mirai-fuel-cells-demo` | `7c878c8c-e7cd-4f8b-ab18-ca0d95cb44af` | `sjc` | Preferred artifact root for `fraunhofer`. Runtime S3 credentials may expose a generated bucket name; treat it as non-secret but distinct from the Railway resource label. |
| Battery Railway bucket resource | `mirai-batteries-demo` | `3be7e99f-65a8-458d-8fa1-310ce256ec33` | `sjc` | Preferred artifact root for `battery-demo`. Runtime S3 credentials may expose a generated bucket name; treat it as non-secret but distinct from the Railway resource label. |

The bucket list was verified with `railway bucket list --json`. Bucket credentials are intentionally not recorded here.

## Clerk dev-auth cutover status

As of the Clerk development cutover work, Railway service `mirai-doe` is configured for auth-required Level 2 demo mode using the Clerk development issuer:

```text
CLERK_AUTH_REQUIRED=true
FASTAPI_DOCS_PUBLIC=false
CLERK_ISSUER=https://square-snail-89.clerk.accounts.dev
CLERK_JWT_ISSUER=https://square-snail-89.clerk.accounts.dev
CLERK_JWKS_URL=https://square-snail-89.clerk.accounts.dev/.well-known/jwks.json
CLERK_JWT_LEEWAY_SECONDS=5
MIRAI_STATIC_DIR=/app/static
```

The frontend requests Clerk custom JWT template `jwt-doe-template` and sends it as `Authorization: Bearer <token>`. The backend treats the verified top-level JWT `workspace_id` claim as the only trusted workspace source; workspace IDs from route params, request bodies, query strings, or frontend state are not trusted for authorization.

The existing Clerk dev user must have private metadata equivalent to:

```json
{
  "workspace_id": "fraunhofer",
  "role": "demo_fuel_cell"
}
```

The Clerk JWT template `jwt-doe-template` must include top-level claims:

```json
{
  "workspace_id": "{{user.private_metadata.workspace_id}}",
  "role": "{{user.private_metadata.role}}"
}
```

If private metadata cannot be used in the dev template, public metadata may be used for this demo only. Do not configure JWT audience until Clerk is intentionally configured to emit one and the backend is updated to enforce it.

Signed-out users can load the SPA/sign-in UI and public health routes, but protected project/artifact endpoints return `401` without a bearer token. Cross-workspace project access must return `403` for a fuel-cell user.

## Environment variable contract

Non-secret configuration should be safe to document by name and value:

```text
MIRAI_STORAGE_BACKEND=s3
MIRAI_WORKSPACE_BUCKET_MAP={"fraunhofer":"mirai-fuel-cells-demo","battery-demo":"mirai-batteries-demo"}
MIRAI_S3_REGION=sjc
FASTAPI_DOCS_PUBLIC=false
CLERK_AUTH_REQUIRED=true              # enabled for Clerk dev demo cutover
CLERK_DEFAULT_WORKSPACE_ID=fraunhofer # legacy/dev fallback only; authenticated authorization requires verified JWT workspace_id
```

Secret or connection-bearing values must live only in Railway variables or ignored local env files and must not be printed in docs, logs, or PR text. Current Railway bucket variables are per workspace so each bucket can rotate independently:

```text
DATABASE_URL
MIRAI_FRAUNHOFER_S3_BUCKET
MIRAI_FRAUNHOFER_S3_ENDPOINT
MIRAI_FRAUNHOFER_S3_ACCESS_KEY_ID
MIRAI_FRAUNHOFER_S3_SECRET_ACCESS_KEY
MIRAI_FRAUNHOFER_S3_REGION
MIRAI_FRAUNHOFER_S3_URL_STYLE
MIRAI_BATTERY_DEMO_S3_BUCKET
MIRAI_BATTERY_DEMO_S3_ENDPOINT
MIRAI_BATTERY_DEMO_S3_ACCESS_KEY_ID
MIRAI_BATTERY_DEMO_S3_SECRET_ACCESS_KEY
MIRAI_BATTERY_DEMO_S3_REGION
MIRAI_BATTERY_DEMO_S3_URL_STYLE
MLFLOW_TRACKING_URI                  # may include DB/service details depending on deployment shape
MLFLOW_ARTIFACT_ROOT                 # may include bucket/service details depending on deployment shape
VITE_CLERK_PUBLISHABLE_KEY           # publishable but environment-specific; configure through Railway/frontend env
CLERK_ISSUER or CLERK_JWT_ISSUER
CLERK_JWKS_URL                       # optional
CLERK_JWT_AUDIENCE                   # optional
```

Local development may continue to use filesystem-backed storage when `MIRAI_STORAGE_BACKEND=local` or when the variable is unset, as long as Railway mode rejects unscoped local-image-only runtime paths for pilot data.

## MLflow, model-quality, and ONNX artifact strategy

Follow CAI's durable-state pattern:

- MLflow tracking/backend metadata should use Railway Postgres through the separate `mirai-mlflow` service once enabled.
- MLflow artifacts, ONNX exports, preprocessing outputs, predictions, BO state, and review files should use Railway S3-compatible object storage under the workspace/project layout above.
- Mirai stores or derives durable artifact pointers for each project; runtime code must not assume `backend/mlruns/` or `data/reference/.../training_artifacts/latest` has been copied into the Railway image for pilot data.
- Local development may continue to use filesystem MLflow/artifact paths for tests and iteration.

Current implementation status:

- The fuel-cell project still has packaged/local artifacts available for bootstrap smoke tests and local tests.
- Model/artifact metadata now includes durable object-pointer conventions for the fuel-cell and battery projects.
- `model-quality/summary` remains available only when complete quality artifacts exist. If training/bootstrap has not produced metrics, predictions, and candidate comparison artifacts, the API should explain that model quality is unavailable until training/bootstrap instead of pretending state exists.
- The battery demo's durable metadata can be represented before data/model upload, but its real model-quality output is deferred until the battery dataset/model source is confirmed and bootstrapped.

## Artifact bootstrap workflow

Use `scripts/bootstrap_demo_artifacts.py` to preview or upload approved demo artifacts into the workspace/project-scoped bucket paths.

Safe dry-run example:

```bash
python3 scripts/bootstrap_demo_artifacts.py --project all --dry-run
```

Properties:

- The script reads bucket names/endpoints/access keys only from env vars; secrets are never accepted as CLI arguments.
- Dry-run output lists target bucket names, object keys, source file paths, byte sizes, and boolean env-var presence only. It does not print access keys, secret keys, endpoint credentials, or Railway variable values.
- Fuel-cell bootstrap uploads approved reference artifacts under:
  - `workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/`
  - `workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/`
- The fuel-cell bucket has been bootstrapped with scoped real demo objects for the current dev-auth demo.
- Battery bootstrap is explicitly deferred until `MIRAI_BATTERY_ARTIFACT_SOURCE` points at an approved battery dataset/model artifact source; the battery bucket remains empty for now.
- The script refuses to upload `backend/data-minio/intake` wholesale.
- Real upload is optional and requires `--upload` plus env credentials and `boto3` availability.

## Operator visibility workflow

Level 2 visibility should not require Kubernetes:

- Mirai UI/API should be the default way for demo users to inspect project state, model status, BO state, and model-quality availability.
- Operators can inspect Postgres with local `psql`, TablePlus, DBeaver, or the Railway dashboard/connection details. Do not publish a public unauthenticated Postgres admin UI.
- Operators can inspect buckets with Railway bucket views, S3-compatible tools, or the bootstrap/listing scripts. Do not record bucket credentials in docs or logs.
- MLflow UI runs as a separate Railway service `mirai-mlflow` when enabled. It must use Railway Postgres for backend metadata and the Fraunhofer workspace bucket/prefix for current demo artifacts, and it must be protected or private before real client data is used.
- Any temporary admin/object UI must have an explicit owner, access-control mechanism, and removal/disable step.

## Bootstrap-only stateless mode

The container image may be used statelessly only for internal smoke tests:

- verifying the React SPA loads;
- verifying `/health` and `/api/health`;
- verifying Clerk sign-in wiring;
- validating that protected APIs reject missing/invalid bearer tokens.

Do not use stateless mode for real pilot client data. The container filesystem is ephemeral and can lose uploads, training outputs, MLflow artifacts, BO observations, preprocessing reviews, and model-quality review state across rebuilds/restarts.

## Pilot gate for real client data

Before onboarding any real pilot client data, enable and verify durable Level 2 storage:

1. Railway Postgres stores tenant/workspace/project/control-plane metadata.
2. RLS or equivalent backend authorization prevents workspace A from reading workspace B.
3. Every upload, canonical artifact, training output, MLflow artifact pointer, BO artifact, and review artifact is under a workspace-scoped storage prefix/root.
4. Storage adapter tests reject unscoped paths and cross-workspace paths.
5. Secrets are configured only in Railway environment variables and are never committed, logged, or included in PR text.

## Current single-container behavior

`Dockerfile.railway` builds one image containing:

- Vite React static assets;
- FastAPI backend served by Uvicorn on `${PORT:-8000}`;
- packaged demo/reference artifacts required for smoke tests.

The backend serves the SPA only when `MIRAI_STATIC_DIR` is set, so the existing Compose workflow remains multi-container and unchanged.
