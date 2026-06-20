# Remote MLflow access for Mirai operator training

MLflow is operator/internal tooling for Mirai demos and model lifecycle work. It is not a customer-facing Mirai UI and must not be exposed without authentication.

## Architecture

```text
MacBook / operator browser
  -> HTTPS Railway public domain
  -> same-container HTTP Basic auth proxy on Railway public port
  -> MLflow built-in basic-auth app on 127.0.0.1 inside the container
  -> MLflow UI + Tracking REST API
  -> private Railway Postgres backend store and MLflow artifact storage
```

The Mirai app service should continue to use Railway private networking for service-to-service access where applicable. Do not switch internal app calls to the public MLflow URL unless there is a specific need.

## Auth mechanism

The `mirai-mlflow` service uses MLflow's built-in `basic-auth` app:

```bash
mlflow server --app-name basic-auth
```

For MLflow 3.13.0 this is the official supported username/password mechanism. The service also requires `MLFLOW_FLASK_SERVER_SECRET_KEY` for CSRF protection and starts with a generated auth config file built from Railway variables at runtime.

MLflow 3.13 still leaves a small set of discovery routes open by design. To meet the Mirai demo requirement that the public endpoint is never useful without credentials, the Railway public port is fronted by `scripts/mlflow_basic_auth_proxy.py`, which enforces the same HTTP Basic credentials for every non-`/health` UI/API request before proxying to the local MLflow `basic-auth` app.

## Required Railway variables by name only

Do not print or commit values.

Core MLflow storage/config:

- `MLFLOW_BACKEND_STORE_URI`
- `MLFLOW_ARTIFACT_ROOT`
- `MLFLOW_S3_ENDPOINT_URL`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION`
- `MLFLOW_SERVER_ENABLE_JOB_EXECUTION`
- `MLFLOW_DISABLE_TELEMETRY`

Auth/security:

- `MLFLOW_FLASK_SERVER_SECRET_KEY`
- `MLFLOW_AUTH_ADMIN_USERNAME`
- `MLFLOW_AUTH_ADMIN_PASSWORD`
- `MLFLOW_AUTH_DEFAULT_PERMISSION`
- `MLFLOW_AUTH_GRANT_DEFAULT_WORKSPACE_ACCESS`
- `MLFLOW_ALLOWED_HOSTS`
- `MLFLOW_CORS_ALLOWED_ORIGINS`

Optional if using a separate auth database from the tracking backend:

- `MLFLOW_AUTH_DATABASE_URI`

## Local `backend/.env.training.local`

This file is gitignored and loaded by direnv through `.envrc`.

```bash
MLFLOW_TRACKING_URI=https://<railway-mlflow-domain>
MLFLOW_TRACKING_USERNAME=<operator-user>
MLFLOW_TRACKING_PASSWORD=<operator-password>
MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true
MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=true
```

Do not add Railway Postgres credentials, Clerk secrets, Mirai API tokens, direct app S3 credentials, `OBJECT_STORAGE_BACKEND`, or `.object-storage-local` settings.

## Browser login

Open `MLFLOW_TRACKING_URI` in a browser. The public endpoint will prompt for the operator username and password using HTTP Basic authentication. Use only the operator credentials stored in the local gitignored env file or password manager.

## Smoke test

After direnv has loaded `backend/.env.training.local`:

```bash
cd backend
uv run python - <<'PY'
from pathlib import Path
import tempfile
import mlflow
from mlflow.tracking import MlflowClient

client = MlflowClient()
experiment_name = "mirai-auth-smoke"
experiment = client.get_experiment_by_name(experiment_name)
experiment_id = experiment.experiment_id if experiment else client.create_experiment(experiment_name)

with tempfile.TemporaryDirectory() as tmp:
    artifact = Path(tmp) / "smoke.txt"
    artifact.write_text("authenticated mlflow smoke test\n", encoding="utf-8")
    with mlflow.start_run(experiment_id=experiment_id, run_name="authenticated-smoke"):
        mlflow.log_param("auth", "basic")
        mlflow.log_metric("smoke_metric", 1.0)
        mlflow.log_artifact(str(artifact))

print("authenticated MLflow smoke test completed")
PY
```

Unauthenticated checks should return HTTP 401/403, not the MLflow UI or API data:

```bash
curl -i "$MLFLOW_TRACKING_URI/"
curl -i -X POST -H 'Content-Type: application/json' -d '{}' \
  "$MLFLOW_TRACKING_URI/api/2.0/mlflow/experiments/search"
```

## Credential rotation/reset

1. Generate a new strong password outside Git.
2. Update Railway secret `MLFLOW_AUTH_ADMIN_PASSWORD` for `mirai-mlflow`.
3. If the admin user already exists in MLflow auth storage, update the user password through the authenticated MLflow auth API or admin UI/API using current admin credentials.
4. Redeploy/restart `mirai-mlflow`.
5. Update only local gitignored `backend/.env.training.local` and any password manager entry.
6. Verify authenticated smoke test succeeds and unauthenticated access still fails.

Never commit credentials and never paste passwords into logs, issues, docs, or chat.

## Rollback

If the public endpoint must be disabled quickly:

1. Remove the Railway public domain from `mirai-mlflow`, or set `MLFLOW_ALLOWED_HOSTS` to a non-public internal host list and redeploy.
2. Keep `--app-name basic-auth` enabled; do not roll back to unauthenticated public MLflow.
3. If needed, restore the previous `Dockerfile.mlflow` command only while the service has no public domain.
4. Remove or blank local `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME`, and `MLFLOW_TRACKING_PASSWORD` from `backend/.env.training.local`.
