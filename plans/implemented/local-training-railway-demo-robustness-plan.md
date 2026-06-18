# Local Training + Railway Demo Robustness Plan

## Context

The current Mirai demo works end-to-end at the platform level: upload/intake, metadata review, EDA-style preprocessing review, ONNX inference, and dynamic plotting are functioning. The next priority is consolidation and robustness, not model-quality optimization yet.

The immediate demo goal is to make local MacBook training reliably connect to Railway as the durable backend:

- User uploads data to Railway object storage buckets.
- Bruno keeps a gitignored local mirror for early-stage training convenience.
- Training runs locally on the MacBook.
- Runs, metrics, ONNX models, preprocessing/schema/metadata, ydata/EDA artifacts, and other training outputs are logged back to Railway MLflow + Railway S3.
- Git and Docker images do not contain large datasets, local mirrors, generated models, or MLflow run outputs.

A later task will add true ML preprocessing after EDA: imputation, scaling, transforms, leakage-safe persisted pipelines, and paper-metric improvement. This plan should not try to optimize RMSE/R2/MAE yet; it should make the data/artifact/training pipeline robust enough to support that future work.

## Current findings

- `.gitignore` already ignores `backend/.object-storage-local/`, selected `backend/data-minio/` runtime subtrees, and `backend/.mlflow-cache/`.
- `.gitignore` does not yet fully match the requested local-training rules for `backend/data-minio/`, root `mlruns/`, and `*.onnx` handling.
- `backend/app/services/workspace_storage.py` already contains local/S3 storage primitives and workspace-scoped key validation.
- Training code already logs several artifacts through MLflow in `backend/ml_lifecycle/training/generic_tabular_doe/train.py`, including metrics, schema, preprocessing, split report, predictions, candidate comparison, and candidate ONNX artifacts when available.
- MLflow artifact-location logic currently derives S3 paths from workspace-specific env vars such as `MIRAI_FRAUNHOFER_S3_BUCKET` and places artifacts under `workspaces/{workspace}/projects/{project_id}/mlflow-artifacts`.
- `docs/agent-plans/to-implement/local-training-remote-serving.md` contains the original task requirements for local training against Railway MLflow/S3.
- The metadata UI `Edit labels/details` feature is useful and should stay, but the current table exposes too many internal/id/provenance variables. In the example screenshot, IDs and internal join keys appear after `y4`, and some ID fields default to `input`, which is confusing for demo users.

## Approach

Implement a focused demo-hardening pass with two primary tracks:

1. **Local training ↔ Railway artifact pipeline**
   - Keep training compute local for the early demo.
   - Formalize a logical object-key contract so local mirror paths and Railway S3 keys match after the bucket name.
   - Add/verify env-driven selection between local mirror reads and S3 reads.
   - Ensure local training fails loudly or clearly reports when MLflow/S3 artifact logging is misconfigured, rather than silently leaving durable outputs only under local folders.
   - Add a secrets-free training env template and deployment documentation.

2. **UI metadata cleanup without removing label editing**
   - Preserve `Edit labels/details`.
   - Make the default table user-facing: inputs/outputs/sweep/group variables first.
   - Move IDs, join keys, split columns, source paths, row indices, and provenance metadata behind a secondary advanced/provenance section or filter.
   - Prevent internal id columns from being shown as normal training inputs in selectors.

Do not add the future “Agentic data engineer” yet. Document it as a later layer after the fuel-cell demo and battery flow are robust.

## Files to modify

Likely files:

- `.gitignore`
- `backend/.env.training.example`
- `backend/RAILWAY_DEPLOYMENT.md`
- `backend/app/services/workspace_storage.py`
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py`
- `backend/ml_lifecycle/training/fuel_cell_doe_demo/mlflow.py`
- `backend/ml_lifecycle/entrypoints/` or a new local-training entrypoint if needed
- `frontend/src/components/PreprocessingReviewPage.tsx`
- tests under `backend/tests/` for storage/MLflow config and artifact behavior

## Reuse

- `backend/app/services/workspace_storage.py`
  - Reuse `object_storage_backend`, `local_object_storage_root`, `WorkspaceStorageConfig`, and object-key validation helpers.
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py`
  - Reuse existing MLflow candidate logging and ONNX artifact logging.
- `backend/ml_lifecycle/training/fuel_cell_doe_demo/mlflow.py`
  - Reuse MLflow configuration and model registry helpers.
- `frontend/src/components/PreprocessingReviewPage.tsx`
  - Reuse the existing metadata draft/edit flow and disclosure-panel UX.
- `docs/agent-plans/to-implement/local-training-remote-serving.md`
  - Use as source context for the training/Railway connection requirements.

## Skills and subagent mapping

Use agents deliberately and sparingly; the main orchestrator remains accountable for final scope, diffs, validation, and Git hygiene.

### Skills to apply

- **use-railway**
  - Use for Railway deployment assumptions, Railway CLI documentation, Railway service/bucket sanity checks, and MLflow/S3 environment guidance.
- **surrogate-model-debugging**
  - Use for training-pipeline robustness, artifact expectations, ONNX/MLflow sanity checks, and future paper-metric validation boundaries.
- **scientific-ui-clarity**
  - Use for metadata-label UI cleanup so the demo remains scientist-friendly without hiding necessary provenance.
- **documentation-and-adrs**
  - Use for `backend/RAILWAY_DEPLOYMENT.md`, `.env.training.example`, and documenting the local mirror/Railway source-of-truth contract.
- **git-workflow-and-versioning**
  - Use before staging/committing to keep changes grouped, avoid secrets, and run `git diff --cached --check`.
- **test-driven-development / debugging-and-error-recovery**
  - Use for targeted storage/MLflow tests and for interpreting local training smoke failures.

### Subagents to use

- **scout**
  - Read-only discovery only. Map current storage helpers, training entrypoints, MLflow configuration, and metadata UI helpers before implementation. If scout output is empty or low quality, discard it and continue manually.
- **planner**
  - Optional only if implementation scope expands. Use to split local-training/S3 work from UI cleanup if the change becomes too broad.
- **worker**
  - Use after plan approval for bounded implementation tasks, preferably one worker for backend local-training/storage/MLflow and one worker for frontend metadata cleanup if parallelism is useful.
- **reviewer**
  - Use after implementation for a blocker-focused review of diffs, especially artifact-storage behavior, secret hygiene, and UI variable filtering.
- **oracle**
  - Use only for high-stakes architectural ambiguity, such as whether a storage change risks breaking Railway runtime behavior. Do not use it for routine coding.

### Suggested execution split after approval

1. **Backend/storage worker**: `.gitignore`, training env template, local/S3 resolver, MLflow hard-failure demo mode, tests.
2. **Frontend/UI worker**: metadata table filtering, read-only provenance section, X/Y selector constraints, frontend build.
3. **Docs worker or main orchestrator**: `backend/RAILWAY_DEPLOYMENT.md` and local-training usage notes.
4. **Reviewer**: final cross-cutting review for demo robustness, secrets, and regression risk.

## Steps

- [ ] Tighten `.gitignore` for local training/runtime artifacts.
  - Add/confirm `backend/.object-storage-local/`.
  - Add broader `backend/data-minio/` ignore if acceptable, or document why specific seed/demo subpaths remain tracked.
  - Add root `mlruns/` and `backend/mlruns/`.
  - Add `*.onnx`, with exceptions only if intentional tiny test fixtures exist.

- [ ] Add `backend/.env.training.example` with no secrets.
  - Include Railway MLflow URI placeholders.
  - Include MLflow S3 artifact env vars.
  - Include local mirror mode env vars.
  - Include direct S3 read mode env vars.
  - Include bucket examples for `mirai-fuel-cells-demo` and `mirai-batteries-demo`.

- [ ] Implement or verify local/S3 data loading for training.
  - Training inputs should be addressed by logical object keys, e.g. `workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv`.
  - Local mode should resolve to `backend/.object-storage-local/<bucket>/<logical-key>` or the final agreed mirror shape.
  - S3 mode should resolve to `s3://<bucket>/<logical-key>` using env credentials.
  - Avoid hardcoded absolute paths.

- [ ] Harden MLflow artifact behavior for local training.
  - Ensure `MLFLOW_TRACKING_URI` points to Railway when configured.
  - Ensure experiment artifact location points to Railway S3.
  - Log `model.onnx`, `preprocessing.json`, `schema.json`, `metadata.json`, `metrics_summary.json`/`metrics.json`, ydata/EDA artifacts when available, split report, and predictions/candidate comparison.
  - Add a clear warning/error mode if MLflow artifact logging fails in a demo-required run.

- [ ] Add a local-training smoke/check command.
  - Prefer a small CLI or documented `uv run python -m ...` command that reads from local mirror mode and logs to configured MLflow.
  - Include a dry-run/config-check mode if straightforward.

- [ ] Clean up the metadata label-edit UI.
  - Keep `Edit labels/details`.
  - Filter X/Y selectors to sensible variables only: X from input/sweep, Y from output.
  - Show the main editable table for user-facing variables first.
  - Move IDs/join keys/provenance metadata to an advanced section, or hide them by default with a toggle.
  - Ensure columns like `experiment_id`, `condition_id`, `result_id`, source file paths, row indices, and provenance fields do not appear as normal trainable inputs.

- [ ] Create `backend/RAILWAY_DEPLOYMENT.md`.
  - Document GitHub-connected deployment.
  - Document Railway CLI deployment: `railway login`, `railway link`, `railway status`, `railway up`.
  - Briefly document optional Docker registry deployment.
  - Clarify what gets dockerized and what must stay out of Docker/Git.
  - Add sanity checks for Railway services, health endpoint, buckets, and MLflow UI.

- [ ] Add tests where practical.
  - Storage key resolution: local mirror vs S3 URI/key construction.
  - MLflow env/artifact-location construction without secrets.
  - Metadata UI filtering logic if it can be extracted into a pure helper; otherwise validate through existing build/typecheck.

- [ ] Verify.
  - `uv run pytest ...` for targeted backend tests.
  - `npm --prefix frontend run build`.
  - Local training smoke with fake/local MLflow or a dry-run if Railway secrets are unavailable.
  - Manual Railway-backed smoke only when real secrets are intentionally loaded locally and never printed.

## Verification

Minimum verification before commit:

- [ ] No secrets printed, staged, or committed.
- [ ] `git diff --check` / `git diff --cached --check` passes before commit.
- [ ] `.gitignore` prevents local mirrors, MLflow runs, and ONNX outputs from being committed accidentally.
- [ ] Frontend build passes after metadata UI cleanup.
- [ ] Backend targeted tests pass.
- [ ] Training config docs are sufficient to run local MacBook training against Railway MLflow/S3.

## Deferred work

- True post-EDA ML preprocessing: imputation, scaling, feature transforms, persisted preprocessing pipeline, inverse transforms, and leakage-safe handling.
- Model metric improvement toward the paper's RMSE/R2/MAE.
- Battery dataset full-flow validation.
- Railway-hosted training compute.
- Agentic data engineer for raw-folder-to-Mirai-contract conversion and ML preprocessing recommendations.

## Decisions confirmed

1. The local mirror path will keep the dot-prefix and include the bucket name:
   - `backend/.object-storage-local/mirai-fuel-cells-demo/workspaces/...`
   - `backend/.object-storage-local/mirai-batteries-demo/workspaces/...`
   This keeps the local mirror aligned with Railway bucket boundaries while preserving identical logical keys after the bucket name.

2. For the Railway demo/local-training command, failure to log to Railway MLflow/S3 should be a hard failure. A separate local-only development mode may exist, but the demo path must not silently leave durable outputs only on the MacBook.

3. Internal/provenance metadata in the advanced UI section should be read-only by default. Labels, units, and roles remain editable only for real user-facing modeling/plotting variables.
