# Railway Deployment

This project is intended to run the web/API, Postgres, object storage, and MLflow on Railway while heavy training can run locally or on a future external worker.

## Preferred deployment paths

### A. GitHub-connected deployment

Use this when the Railway service is connected to the repository/branch.

```bash
git status
git add <changed-files>
git diff --cached --check
git commit -m "your message"
git push origin railway
```

Railway then builds and deploys the connected service from the configured builder or Dockerfile for that Railway service.

### B. Railway CLI deployment

Use this for an intentional local deploy to the linked Railway service.

```bash
railway login
railway link
railway status
railway up
```

If you have multiple Railway projects, environments, or services, confirm the target before deploying:

```bash
railway status
railway variables
```

`railway up` uploads the current local directory to the linked service. Do not rely on it to transfer local datasets or generated training outputs; those belong in Railway object storage and MLflow artifacts.

### C. Optional Docker image / registry deployment

This is not the default path for the current demo. Use GitHub-connected deploys or `railway up` unless there is a specific reason to deploy from an external image registry.

Example external image flow:

```bash
docker build -t mirai-doe:<tag> .
docker tag mirai-doe:<tag> ghcr.io/<org>/mirai-doe:<tag>
docker push ghcr.io/<org>/mirai-doe:<tag>
```

Railway can deploy from that registry if configured, but that adds another release surface and should be used deliberately.

## What gets dockerized

The Docker image should contain:

- application code;
- runtime dependencies;
- static frontend build output where applicable;
- configuration templates and startup scripts.

The Docker image should **not** contain:

- large training datasets;
- `backend/.object-storage-local/` local bucket mirrors;
- `backend/data-minio/` runtime state;
- local `mlruns/` or `backend/mlruns/`;
- real client data;
- generated reports, ONNX models, or training artifacts unless a tiny demo fallback is intentionally packaged and documented.

Durable training outputs should live in Railway MLflow and Railway/S3-compatible object storage.

## Local training against Railway MLflow/S3

For early demos, training can run on a MacBook while Railway remains the durable backend.

1. Data is uploaded to a Railway bucket such as `mirai-fuel-cells-demo`.
2. Optionally mirror the bucket locally under the gitignored path:

   ```text
   backend/.object-storage-local/mirai-fuel-cells-demo/workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv
   ```

3. The equivalent S3 object is:

   ```text
   s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv
   ```

4. The logical key is identical after the bucket name:

   ```text
   workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv
   ```

5. Copy `backend/.env.training.example` to a local-only env file or export the variables in your shell. Never commit real secrets.

6. Validate configuration without printing secrets:

   ```bash
   cd backend
   uv run python -m ml_lifecycle.entrypoints.local_training_check \
     --object-key workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv
   ```

7. Run local training using the object key and an artifact directory that is not committed:

   ```bash
   cd backend
   uv run python -m ml_lifecycle.entrypoints.train_project \
     --project-id fuel-cell \
     --data-object-key workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv \
     --artifact-dir /tmp/mirai-training/fuel-cell
   ```

When `MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=1` and `MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=1`, demo training should fail if MLflow tracking is local or if the MLflow experiment artifact location is not `s3://...`.

## Sanity checks after deploy

Use Railway CLI and service URLs to verify:

```bash
railway status
railway logs
railway variables
```

Check that:

- the Mirai API/web service is online;
- the MLflow service/UI is online;
- Postgres is online and migrations/seeds are applied as expected;
- Railway buckets such as `mirai-fuel-cells-demo` and `mirai-batteries-demo` are reachable;
- the backend health endpoint returns OK;
- the MLflow UI opens from its Railway domain;
- local training runs create MLflow runs and S3 artifacts instead of only local files.

## Secret hygiene

- Never print Railway S3 access keys, Clerk secrets, database URLs, or MLflow credentials in logs or commit messages.
- Keep local env files untracked.
- Run `git diff --check` and `git diff --cached --check` before committing.
- Confirm generated local mirrors, MLflow runs, and ONNX outputs are ignored before staging.
