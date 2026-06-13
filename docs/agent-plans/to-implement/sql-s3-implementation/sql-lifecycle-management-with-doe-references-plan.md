# SQL-Backed Lifecycle Management for Manifest Ingestion

## Context

Mirai now has a manifest-driven generic intake system. Uploaded packages declare data meaning through:

```text
mirai_manifest.json
data_dictionary.csv
declared CSV/XLSX tables
optional raw/reference files
```

The manifest/data dictionary answer: **what does this data mean?**

Mirai still needs a persistent application source of truth for: **what happened to this data?** Today much of that state is encoded in filesystem layout, JSON status files, `latest` folders, and MLflow lookup. That is workable for the local MVP, but fragile for multi-upload, multi-project lifecycle management.

SQL should become the lifecycle brain that connects:

```text
Manifest/Data Dictionary -> data meaning
Filesystem / backend/data-minio / future S3 -> physical files and artifacts
MLflow -> training runs, metrics, model versions, aliases
SQL -> ownership, statuses, approvals, lineage, and pointers
```

This plan aligns with the current repo direction:

- `generic_tabular_doe` remains the source-of-truth lifecycle contract.
- PEM/Fraunhofer uses `raw_extractor=pem_cell_zip_bundle` before entering the generic lifecycle.
- Mutable app/object-store state stays under `backend/data-minio/`.
- SQL stores IDs, statuses, hashes, paths, timestamps, approvals, and lineage — not large datasets or model binaries.
- MLflow remains the model experiment/registry source.
- Public API route names should remain stable unless a compatibility layer is provided.

## Current Repo Touchpoints

Existing lifecycle state is currently spread across:

```text
backend/app/services/data_intake.py
backend/app/services/preprocessing_review.py
backend/app/services/training_requests.py
backend/app/services/project_registry.py
backend/app/services/model_quality.py
backend/app/services/mlflow_registry.py
backend/app/services/workspaces.py
backend/data-minio/intake/projects/<project_id>/...
backend/data-minio/workspaces/<workspace_id>/workspace.json
backend/mlruns/
```

Important existing behavior to preserve:

- `create_ingestion_session()` creates project/dataset/session folders and stores uploads.
- `approve_preprocessing()` is the current Mirai-admin gate for training.
- `create_training_request()` rejects unapproved preprocessing.
- `start_training_request()` runs generic training and writes training status/artifacts.
- Generic training logs all candidate models to MLflow and registers only the selected best candidate as challenger.
- Champion remains manual-only.
- `/projects`, `/workspaces`, Data Intake, Preprocessing Review, Training, Model Quality, Design Studio, and BO must continue working during migration.

## Approach

Add a small SQL layer first, using SQLite locally with SQLAlchemy/SQLModel-compatible models and Alembic migrations. Integrate it behind repository/service methods while keeping filesystem JSON compatibility during migration.

The first implementation should be additive and dual-write critical lifecycle events to SQL and existing JSON/status files. After validation, later work can switch reads away from filesystem scanning toward SQL.

Recommended stack:

```text
SQLAlchemy or SQLModel
Alembic migrations
SQLite for local MVP
PostgreSQL-ready model definitions
```

Add dependencies with `uv`, not `pip`.

Suggested local DB path:

```text
backend/data-minio/app.sqlite3
```

This keeps the SQL database in mutable app/object-store runtime state, not under immutable `data/reference/`.

## Files to Modify / Add

### Dependencies/config

```text
backend/pyproject.toml
backend/alembic.ini
backend/alembic/env.py
backend/alembic/versions/<revision>_initial_lifecycle_tables.py
```

### DB layer

```text
backend/app/db/__init__.py
backend/app/db/base.py
backend/app/db/session.py
backend/app/db/migrate.py
```

### ORM models

```text
backend/app/models/__init__.py
backend/app/models/project.py
backend/app/models/ingestion.py
backend/app/models/dataset.py
backend/app/models/training.py
backend/app/models/model_registry.py
```

### Repositories

```text
backend/app/repositories/__init__.py
backend/app/repositories/project_repository.py
backend/app/repositories/ingestion_repository.py
backend/app/repositories/dataset_repository.py
backend/app/repositories/training_repository.py
backend/app/repositories/model_registry_repository.py
```

### Service integrations

```text
backend/app/services/ingestion_lifecycle.py
backend/app/services/training_lifecycle.py
backend/app/services/model_lifecycle.py
backend/app/services/data_intake.py
backend/app/services/preprocessing_review.py
backend/app/services/training_requests.py
backend/app/services/project_registry.py
backend/app/services/model_quality.py
backend/app/services/mlflow_registry.py
backend/app/main.py
backend/app/schemas.py
```

### Tests/docs

```text
backend/tests/test_lifecycle_db.py
backend/tests/test_api.py
backend/tests/test_generic_contract_pipeline.py
docs/reference/MLFLOW_MODEL_LIFECYCLE.md
docs/tutorials/MIRAI_CONTRACT_INTAKE_TO_TRAINING_FLOW.md
```

## Reuse

Reuse existing functions and conventions instead of creating a separate customer-specific lifecycle:

- `backend/app/services/data_intake.py`
  - `create_ingestion_session`
  - `append_ingestion_files`
  - `session_workspace`
  - `project_metadata_path`
  - `read_project_metadata`
  - `upsert_project_metadata`
- `backend/app/services/preprocessing_review.py`
  - validation, report generation, domain metadata, preprocessing approval
- `backend/app/services/training_requests.py`
  - `create_training_request`
  - `start_training_request`
  - `get_training_status`
- `backend/app/services/mlflow_registry.py`
  - `registered_model_name_for_project`
  - `tracking_uri`
  - `get_registered_model_metadata`
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py`
  - generic candidate logging and selected challenger registration
- `backend/app/services/workspaces.py`
  - workspace metadata remains in object-store JSON for now; SQL project rows should reference `workspace_id` later if useful

## Initial Schema

### `projects`

Purpose: track Mirai projects.

Fields:

```text
id                         integer/uuid primary key
project_id                 unique stable string
name                       display name
template_id                generic_tabular_doe or fuel_cell_doe_demo compatibility label
workspace_id               nullable string, maps to backend/data-minio/workspaces/<workspace_id>
workspace_name             nullable display name
raw_extractor              nullable string, e.g. pem_cell_zip_bundle
lifecycle_contract          string, default generic_tabular_doe
status                     active, archived
created_at
updated_at
```

### `ingestion_sessions`

Purpose: track uploaded packages and validation lifecycle.

Fields:

```text
id                         integer/uuid primary key
ingestion_session_id        stable app id, e.g. ing_<hash>
project_id                 foreign key/logical project id
dataset_id                 stable app id, e.g. dataset_<hash>
upload_path
manifest_path
data_dictionary_path
template_id
raw_extractor
status                     uploaded, validating, validation_failed, needs_review, approved, rejected
validation_report_path
raw_reference_inventory_path
raw_extractor_report_path
manifest_hash
data_dictionary_hash
created_at
updated_at
approved_at
approved_by
failure_reason
```

### `datasets`

Purpose: track canonical datasets produced by ingestion/preprocessing.

Fields:

```text
id                         integer/uuid primary key
dataset_id                 stable app id
project_id                 foreign key/logical project id
ingestion_session_id        logical session id
canonical_model_table_path
rejected_rows_path
schema_path
preprocessing_path
dataset_profile_path
split_report_path
eda_report_path
validation_report_path
input_schema_hash
output_schema_hash
row_count
input_count
output_count
status                     created, approved_for_training, deprecated, rejected
created_at
approved_at
approved_by
```

### `training_requests`

Purpose: track model training jobs started from approved datasets.

Fields:

```text
id                         integer/uuid primary key
training_request_id         stable app id, e.g. train_req_<hash>
project_id                 logical project id
dataset_id                 logical dataset id
ingestion_session_id        logical session id
status                     queued, running, completed, failed
requested_by
started_at
completed_at
mlflow_experiment_name
registered_model_name
selected_run_id
selected_model_version
selected_model_name
selection_metric
selection_score
failure_reason
created_at
updated_at
```

### `model_registry_records`

Purpose: store app-level pointers to MLflow model state.

Fields:

```text
id                         integer/uuid primary key
project_id                 logical project id
training_request_id         logical training request id
dataset_id                 logical dataset id
registered_model_name
mlflow_experiment_name
mlflow_run_id
mlflow_model_version
alias                      challenger, champion, baseline
model_type                 sklearn_pipeline, onnx, etc.
model_family               ridge, mlp, xgboost, etc.
validation_status           pending_review, approved, rejected
artifact_uri
local_cache_path
created_at
updated_at
approved_at
approved_by
```

## Lifecycle Behavior

### 1. Project creation/discovery

When a project is created, discovered, or returned by `/projects`, ensure a `projects` row exists with:

```text
project_id
name
template_id
workspace_id/workspace_name when available
raw_extractor when available
lifecycle_contract=generic_tabular_doe
```

Project IDs must match existing ingestion/training/MLflow convention.

### 2. Upload

When `create_ingestion_session()` succeeds:

- Keep writing the existing object-store files under `backend/data-minio/intake/...`.
- Create/update `projects` row.
- Create `ingestion_sessions` row with `status=uploaded`.
- Store upload path, manifest path, data dictionary path, hashes, template ID, raw extractor, dataset ID, and session ID.

### 3. Validation/preprocessing start

When validation/preprocessing begins:

- Update ingestion session `status=validating`.
- Preserve existing status JSON for UI compatibility.

### 4. Validation failure

On validation/preprocessing failure:

- Update ingestion session:

```text
status=validation_failed
failure_reason=<safe message>
validation_report_path=<path if available>
```

- Do not create an approved dataset.
- Training must be blocked.

### 5. Validation/preprocessing success

After canonical artifacts are written:

- Create/update `datasets` row pointing to:

```text
canonical/model_table.csv
canonical/rejected_rows.csv
training_artifacts/latest/schema.json
training_artifacts/latest/preprocessing.json
training_artifacts/latest/split_report.json
training_artifacts/latest/dataset_profile.json or canonical/dataset_profile.json
training_artifacts/latest/validation_report.json or canonical/validation_report.json
training_artifacts/latest/eda_report.json
```

- Compute/store schema hashes and counts where available.
- Set ingestion session `status=needs_review`.
- Set dataset `status=created`.

### 6. Mirai-admin approval

When `approve_preprocessing()` succeeds:

- Update ingestion session:

```text
status=approved
approved_at=now()
approved_by=<approver>
```

- Update dataset:

```text
status=approved_for_training
approved_at=now()
approved_by=<approver>
```

Only `approved_for_training` datasets can be used for training.

### 7. Training request

When `create_training_request()` is called:

- Query SQL dataset state.
- Reject if the dataset is missing or not `approved_for_training`.
- Create `training_requests` row with `status=queued`.
- Keep existing training request JSON for compatibility during migration.

### 8. Training start

When `start_training_request()` starts:

- Update SQL `training_requests.status=running` and `started_at=now()`.
- Preserve existing status JSON.

### 9. Training failure

On failure:

- Update SQL `training_requests.status=failed`.
- Store `failure_reason` and `completed_at`.
- Preserve existing status JSON.

### 10. Training completion

After generic training returns:

- Parse selected model/run/version data from the training result and/or MLflow registry.
- Update `training_requests`:

```text
status=completed
completed_at=now()
mlflow_experiment_name=<project_id>
registered_model_name=doe_surrogate_<project_id>
selected_run_id=<best run id>
selected_model_version=<registered version>
selected_model_name=<candidate name/family>
selection_metric=validation_weighted_normalized_rmse
selection_score=<score>
```

- Create `model_registry_records` row:

```text
alias=challenger
validation_status=pending_review
```

- Do not automatically mark anything as champion.

### 11. Champion promotion later

Add repository/service methods but defer UI-heavy promotion work if needed:

```text
promote_model_record_to_champion(project_id, model_record_id, approved_by)
```

Method rules:

1. Verify record exists.
2. Verify it belongs to the project.
3. Verify or explicitly set `validation_status=approved`.
4. Set MLflow alias `champion` if needed.
5. Insert/update SQL app-level champion record.
6. Never delete previous champion history silently.

## API Strategy

Keep existing public routes working. Add new lifecycle endpoints only where useful for future UI screens.

Existing endpoints to integrate behind the scenes:

```text
POST /data-intake/sessions
POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing/start
POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing-approval
POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests
POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests/{training_request_id}/start
GET  /projects
GET  /projects/{project_id}/model-quality/summary
```

Potential additive MVP endpoints:

```text
GET  /projects/{project_id}/ingestions
GET  /projects/{project_id}/ingestions/{ingestion_session_id}
GET  /projects/{project_id}/datasets
GET  /projects/{project_id}/training-requests
GET  /projects/{project_id}/models
```

Avoid duplicating existing routes unless a new endpoint exposes SQL lifecycle summaries not available today.

## Migration / Backfill Strategy

1. Add schema and migrations.
2. Create a one-time backfill helper that scans current object-store metadata and inserts rows for visible projects/sessions:

```text
backend/data-minio/workspaces/
backend/data-minio/intake/projects/<project_id>/project.json
backend/data-minio/intake/projects/<project_id>/datasets/<dataset_id>/ingestion_sessions/<session_id>/
```

3. Backfill only metadata/pointers, not full files.
4. For existing PEM reference project, create a project row and optional model registry rows from MLflow aliases when available.
5. Keep backfill idempotent.

## Testing Plan

Add tests for repository and service behavior:

- DB initializes under a temp `DOE_OBJECT_STORE_ROOT`.
- Project row is created on upload/project discovery.
- Upload creates ingestion session SQL row with hashes/paths.
- Validation failure updates status and blocks training.
- Preprocessing success creates dataset row with artifact paths and counts.
- Approval updates ingestion and dataset records.
- Training request is rejected unless dataset is `approved_for_training`.
- Training start/completion updates SQL lifecycle rows.
- Completion creates challenger model registry record.
- Existing API tests still pass.
- Generic contract pipeline still logs all candidate MLflow runs and registers only selected best.

Validation commands:

```bash
cd backend && uv run pytest tests/test_lifecycle_db.py -q
cd backend && uv run pytest tests/test_api.py tests/test_generic_contract_pipeline.py -q
cd frontend && npm run build
```

## Rollout Steps

- [ ] Add SQL dependencies with `uv` and configure SQLite DB under `backend/data-minio/app.sqlite3`.
- [ ] Add Alembic migration scaffold and initial lifecycle tables.
- [ ] Add DB session/base helpers with env-configurable `DOE_DATABASE_URL`.
- [ ] Add ORM models for projects, ingestion sessions, datasets, training requests, and model registry records.
- [ ] Add repository classes/functions with idempotent upsert methods.
- [ ] Add lifecycle service wrappers so FastAPI services do not manipulate ORM objects directly.
- [ ] Integrate project row creation in project discovery and ingestion session creation.
- [ ] Integrate ingestion session status transitions in upload, validation/preprocessing start, success, and failure paths.
- [ ] Integrate dataset row creation and approval updates in preprocessing review/approval flow.
- [ ] Integrate training request row creation, running/failed/completed updates, and selected model metadata capture.
- [ ] Create challenger model registry record after successful training registration.
- [ ] Add read endpoints or lifecycle summary helpers for ingestions, datasets, training requests, and models.
- [ ] Add idempotent backfill helper for existing `backend/data-minio` and MLflow state.
- [ ] Add repository/service tests and update API tests.
- [ ] Update docs to explain manifest vs object store vs MLflow vs SQL responsibilities.

## Acceptance Criteria

After implementation, Mirai can persistently answer from SQL:

- Which upload packages exist for a project?
- Which uploads passed or failed validation?
- Where is the validation report?
- Which canonical dataset was produced?
- Is the dataset approved for training?
- Which training request used the dataset?
- Which MLflow experiment/run/model version came from the training request?
- Which selected model is the current challenger?
- Which model is the current champion, if any?

No critical lifecycle decision should require guessing from folder sort order or `latest` directory names once SQL records exist.

## Non-Goals

- Do not store large uploaded data, canonical CSVs, ONNX files, or model binaries in SQL.
- Do not replace MLflow.
- Do not replace manifest/data-dictionary validation.
- Do not create customer-specific preprocessing tables.
- Do not create customer-specific Python packages.
- Do not overbuild SaaS permissions, users, billing, or memberships in the first pass.
- Do not remove existing JSON/object-store state until SQL reads are validated and UI behavior is stable.
- Do not reintroduce `backend/artifacts/`, `runtime-projects/`, replay CSV fallback folders, or customer-specific Python packages.

## Future Extensions

Later tables/features can include:

```text
clients
users
project_memberships
optimization_campaigns
candidate_recommendations
experiment_observations
prediction_logs
business_impact_profiles
```

These should wait until the core project -> ingestion -> dataset -> training -> model lifecycle is stable.
