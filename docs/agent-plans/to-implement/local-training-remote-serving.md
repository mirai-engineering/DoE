# Task: Configure local training with Railway MLflow + S3 artifacts, and document Railway deployment

## Context

We are deploying the DoE app on Railway, but Railway should not be treated as the main ANN training machine.

Current intended architecture:

txt Railway   → DoE web/API service   → Postgres   → Railway object storage buckets   → MLflow tracking server/UI  Local machine / future external worker   → training compute   → reads data from local mirror or Railway S3   → logs runs to Railway MLflow   → uploads artifacts to Railway S3 through MLflow 

Current Railway buckets:

txt mirai-fuel-cells-demo mirai-batteries-demo 

The local machine may keep a gitignored mirror/cache of the Railway bucket data for training convenience.

Example local mirror path:

txt backend/.object-storage-local/mirai-fuel-cells-demo/workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv 

Equivalent Railway object key:

txt s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv 

The object key should be the same logical path in both places:

txt workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv 

## Goal

Create a clean local-training workflow where:

1. Training can run locally on the MacBook.
2. Training can read data either from:
   - gitignored local object-storage mirror, or
   - Railway S3 bucket.
3. MLflow tracking points to the Railway MLflow server.
4. MLflow artifacts are stored in Railway S3, not in Git and not only locally.
5. The Railway app remains mostly stateless and focused on inference/demo serving.
6. The repo contains clear docs showing how to deploy to Railway manually.

## Important design rule

Do not commit large datasets, real client data, generated training artifacts, MLflow run outputs, ONNX models, reports, or local bucket mirrors to Git.

The durable source of truth for training outputs should be:

txt Railway MLflow + Railway S3 artifact storage 

Local files are allowed only as temporary training outputs or gitignored mirrors/caches.

## Required implementation checks

### 1. Local mirror cleanup

Ensure a gitignored local mirror folder exists or is documented:

txt backend/.object-storage-local/ 

Add to .gitignore:

txt backend/.object-storage-local/ backend/data-minio/ mlruns/ *.onnx 

Be careful with *.onnx: if there are tiny intentional test fixtures, place them in a clearly documented test fixture path and add an exception if needed.

### 2. Storage backend configuration

Ensure training/data-loading code can choose between local and S3 storage via env vars.

Example:

txt OBJECT_STORAGE_BACKEND=local LOCAL_OBJECT_STORAGE_ROOT=backend/.object-storage-local OBJECT_STORAGE_BUCKET=mirai-fuel-cells-demo 

or:

txt OBJECT_STORAGE_BACKEND=s3 S3_ENDPOINT_URL=... S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... S3_REGION=... OBJECT_STORAGE_BUCKET=mirai-fuel-cells-demo 

The code should use logical object keys, not hardcoded absolute paths.

Good:

txt workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv 

Bad:

txt /Users/bruno/.../backend/data-minio/workspaces/fraunhofer/... 

### 3. MLflow local training configuration

Create or verify a local training env template, for example:

txt backend/.env.training.example 

It should include:

txt MLFLOW_TRACKING_URI=https://<railway-mlflow-domain> MLFLOW_EXPERIMENT_NAME=fraunhofer_fuel_cell MLFLOW_S3_ENDPOINT_URL=<railway-s3-endpoint> AWS_ACCESS_KEY_ID=<railway-bucket-access-key> AWS_SECRET_ACCESS_KEY=<railway-bucket-secret-key> AWS_DEFAULT_REGION=<railway-bucket-region> MLFLOW_ARTIFACT_BUCKET=mirai-fuel-cells-demo MLFLOW_ARTIFACT_PREFIX=mlflow 

Do not commit real secrets.

### 4. Training output behavior

Ensure local training scripts:

1. Train locally.
2. Log params, metrics, and tags to Railway MLflow.
3. Log artifacts to MLflow, including:
   - model.onnx
   - preprocessing.json
   - schema.json
   - metadata.json
   - metrics.json, if available
4. Do not leave durable artifacts only in local folders.
5. Optionally update Postgres/model registry pointer to the champion artifact after training.

MLflow artifacts should end up in Railway object storage, not in local mlruns/.

### 5. Railway deployment docs

Create a small markdown file:

txt backend/RAILWAY_DEPLOYMENT.md 

This file should teach me how to deploy the project to Railway.

Include both deployment paths:

## A. GitHub-connected deployment

Explain:

txt git add . git commit -m "..." git push 

Then Railway automatically builds/deploys the connected service.

Mention that Railway builds using the project Dockerfile or detected builder depending on service config.

## B. Railway CLI deployment

Include the basic commands:

bash railway login railway link railway status railway up 

Explain that railway up deploys the current local directory to the linked Railway service.

Also explain how to select the right project/environment/service if needed.

## C. Docker image / registry deployment

Briefly explain that this is optional and probably not our default right now.

Example flow:

bash docker build -t <image-name>:<tag> . docker tag <image-name>:<tag> ghcr.io/<org>/<image-name>:<tag> docker push ghcr.io/<org>/<image-name>:<tag> 

Then Railway can deploy from the external image registry if configured.

Make clear that for now our preferred approach is:

txt GitHub-connected deploy or railway up 

not manual Docker registry pushes.

### 6. Clarify what gets dockerized

In the docs, explain that code changes should be deployed through Railway, which will build the Docker image from the configured Dockerfile/build system.

We do not manually copy local data into the Docker image.

The Docker image should contain:

txt app code dependencies runtime config templates 

The Docker image should not contain:

txt large training datasets local object-storage mirror MLflow artifacts client data generated models, unless intentionally packaged for a tiny demo fallback 

### 7. Add quick sanity checks

Add a section to RAILWAY_DEPLOYMENT.md with commands/checks like:

bash railway status railway logs railway variables 

and explain that after deployment I should verify:

txt - mirai-doe service is online - mirai-mlflow service is online - Postgres is online - Railway buckets are reachable - backend health endpoint returns OK - MLflow UI opens from its Railway domain 

## Deliverables

1. Audit/update .gitignore for local mirror/training artifacts.
2. Confirm or implement storage backend switching: local mirror vs S3.
3. Confirm or implement local training MLflow config that points to Railway MLflow.
4. Ensure artifacts from local training are logged to Railway MLflow/S3.
5. Create backend/.env.training.example.
6. Create backend/RAILWAY_DEPLOYMENT.md.
7. Briefly summarize:
   - how local data mirrors Railway bucket keys,
   - how local training points to Railway MLflow,
   - how deployment to Railway should be performed.