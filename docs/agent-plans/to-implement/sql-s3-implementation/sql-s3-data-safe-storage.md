Here’s the updated agent task, with the **why SQL is needed** included more clearly.

```markdown
# Task: Implement SQL-backed lifecycle management for Mirai manifest ingestion

## Context

Mirai now has a manifest-driven generic intake system.

OEMs/scientists upload a package containing:

```text
mirai_manifest.json
data_dictionary.csv
declared CSV/XLSX tables
optional raw/reference files
```

The manifest/data dictionary define what the uploaded data means: column roles, units, dtypes, bounds, output directions, joins, grouping/split hints, and metadata.

This solves the “custom Python script per customer” problem by moving customer-specific meaning into a declarative data contract instead of hardcoded preprocessing code.

However, Mirai still needs a persistent application-level source of truth for tracking the lifecycle around these uploads.

The manifest answers:

```
What does this data mean?
```

SQL should answer:

```
What happened to this data?
Who approved it?
Which canonical dataset came from it?
Which training run used it?
Which MLflow model version came from it?
Which model is challenger/champion for this project?
```

## **Why SQL is needed**

Mirai is no longer just a script that transforms files into models. It is becoming a workflow system for customer data, validation, approval, training, model governance, and optimization.

Without SQL, state becomes hidden in folders, filenames, JSON files, and implicit Python assumptions, for example:

```
backend/data/intake/projects/fraunhofer_demo/upload_1/
backend/data/intake/projects/fraunhofer_demo/upload_2/
backend/artifacts/fraunhofer_demo/latest/
backend/mlruns/...
```

Then the backend has to guess:

```
Which upload is latest?
Which one passed validation?
Which one was approved?
Which model_table.csv is approved for training?
Which training request produced the current challenger?
Which model is allowed to be served?
Which artifacts are stale?
```

That is fragile.

SQL gives Mirai an explicit, queryable source of truth:

```
project_id = fraunhofer_demo
latest_ingestion_status = approved
current_approved_dataset = dataset_003
current_challenger_model = model_version_8
current_champion_model = model_version_5
```

The manifest is like a passport: it proves what the data means.

SQL is like airport control: it records when the package arrived, whether it passed checks, whether it was approved, where it went next, and what state it is currently in.

Mirai needs both.

## **Separation of responsibilities**

Do not use SQL to store large datasets or model binaries.

Use this architecture:

```
Manifest / data dictionary:
  declares the meaning of uploaded data

Filesystem / MinIO / S3:
  stores uploaded packages, raw files, canonical datasets, reports, preprocessing artifacts, model artifacts

MLflow:
  stores experiment runs, metrics, params, model artifacts, registered model versions, aliases

SQL:
  stores application state, ownership, lifecycle, lineage, approvals, statuses, and pointers
```

SQL should store paths, hashes, IDs, statuses, timestamps, and relationships.

It should not duplicate the full training data.

The existing Mirai data contract already defines that preprocessing creates canonical artifacts like:

```
canonical/model_table.csv
canonical/rejected_rows.csv
canonical/dataset_profile.json
canonical/validation_report.json
training_artifacts/latest/schema.json
training_artifacts/latest/preprocessing.json
training_artifacts/latest/split_report.json
training_artifacts/latest/eda_report.json
```

SQL should reference these artifacts, not replace them. The contract also states that training should consume only approved canonical/model artifacts such as `schema.json`, `preprocessing.json`, and `model_table.csv`.

## **Product reason**

Eventually the frontend needs to show real lifecycle state:

```
Project: Fraunhofer Demo

Latest upload:
  Status: Needs review
  Rows: 1,248
  Inputs: 7
  Outputs: 5
  Validation: 3 warnings

Current model:
  Champion: Ridge v5
  Challenger: MLP v8
  Status: Pending approval
```

This should not come from scanning folders or parsing MLflow alone.

It should come from SQL.

## **MLflow relationship**

Do not replace MLflow.

MLflow remains responsible for model training history and registry governance.

The current intended MLflow flow is:

```
1. Train multiple candidate models.
2. Log every candidate as an MLflow experiment run.
3. Select the best candidate by validation metric.
4. Register only the selected best candidate as a new model version.
5. Set the selected version as challenger.
6. Never overwrite champion automatically.
```

SQL should record the application-side lineage around this flow:

```
Which dataset started this training request?
Which ingestion session produced that dataset?
Which MLflow experiment was used?
Which MLflow run was selected?
Which registered model version was created?
Which app project owns that model?
```

The MLflow README already defines this governance pattern: experiments are training workspaces, runs are individual training attempts, registered models are stable deployable surrogate families, and aliases like `challenger`/`champion` are mutable role pointers.

## **Target lifecycle**

Implement this persistent lifecycle:

```
Project
  → Ingestion Session
    → Canonical Dataset
      → Training Request
        → MLflow Runs
          → Selected Registered Model Version
            → Challenger / Champion governance
```

Or in pipeline form:

```
Uploaded OEM package
  ↓
SQL ingestion_session created
  ↓
Manifest + data_dictionary validation
  ↓
Canonical artifacts created
  ↓
SQL dataset record created
  ↓
Mirai-admin approval
  ↓
Training request created
  ↓
Generic training pipeline runs
  ↓
MLflow logs candidate runs
  ↓
Best candidate registered as challenger
  ↓
SQL stores MLflow pointers and model lifecycle state
```

## **Initial database scope**

Implement the smallest useful SQL layer first.

Required tables:

```
projects
ingestion_sessions
datasets
training_requests
model_registry_records
```

Optional later:

```
clients
users
project_memberships
optimization_campaigns
candidate_recommendations
experiment_observations
prediction_logs
```

For this task, do not overbuild SaaS permissions yet. Focus on project/data/training/model lineage.

## **Suggested schema**

### **projects**

Purpose: track Mirai projects.

Fields:

```
id
project_id              # stable string, e.g. fraunhofer_demo_39e89ec9
name
template_id             # generic_tabular_doe or fuel_cell
created_at
updated_at
```

### **ingestion_sessions**

Purpose: track each uploaded package and its validation lifecycle.

Fields:

```
id
project_id
upload_path
manifest_path
data_dictionary_path
template_id
status                  # uploaded, validating, validation_failed, needs_review, approved, rejected
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

### **datasets**

Purpose: track canonical datasets produced by ingestion.

Fields:

```
id
project_id
ingestion_session_id
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
status                  # created, approved_for_training, deprecated, rejected
created_at
approved_at
approved_by
```

### **training_requests**

Purpose: track model training jobs started from approved datasets.

Fields:

```
id
project_id
dataset_id
ingestion_session_id
status                  # queued, running, completed, failed
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

### **model_registry_records**

Purpose: store app-level pointers to MLflow model state.

Fields:

```
id
project_id
training_request_id
dataset_id
registered_model_name
mlflow_experiment_name
mlflow_run_id
mlflow_model_version
alias                   # challenger, champion, baseline
model_type              # sklearn_pipeline, onnx, etc.
model_family            # ridge, mlp, xgboost, etc.
validation_status       # pending_review, approved, rejected
artifact_uri
local_cache_path
created_at
updated_at
approved_at
approved_by
```

## **Required behavior**

### **1. On project creation or discovery**

Ensure a `projects` row exists.

Required values:

```
project_id
name
template_id
```

The project ID should match the existing Mirai project ID convention used by ingestion/training/MLflow.

### **2. On upload**

When an OEM/scientist package is uploaded, create an `ingestion_sessions` row:

```
status = uploaded
```

Store:

```
upload_path
manifest_path
data_dictionary_path
template_id
manifest_hash
data_dictionary_hash
```

### **3. On validation start**

Update the ingestion session:

```
status = validating
```

Run the existing manifest/data dictionary validation.

### **4. On validation failure**

Update the ingestion session:

```
status = validation_failed
failure_reason = ...
validation_report_path = ...
```

Do not allow training from this upload.

### **5. On validation success**

Write canonical artifacts.

Create a `datasets` row pointing to:

```
canonical/model_table.csv
canonical/rejected_rows.csv
training_artifacts/latest/schema.json
training_artifacts/latest/preprocessing.json
training_artifacts/latest/split_report.json
training_artifacts/latest/dataset_profile.json
training_artifacts/latest/validation_report.json
training_artifacts/latest/eda_report.json
```

Update ingestion session:

```
status = needs_review
```

Dataset starts as:

```
status = created
```

### **6. On Mirai-admin approval**

Update ingestion session:

```
status = approved
approved_at = now()
approved_by = ...
```

Update dataset:

```
status = approved_for_training
approved_at = now()
approved_by = ...
```

Only datasets with `status = approved_for_training` can be used for training.

This matches the Mirai contract rule that a project cannot proceed to training until the manifest, data dictionary, joins, split hints, metadata/plot setup, and preprocessing artifacts are approved.

### **7. On training request**

Create a `training_requests` row:

```
status = queued
```

The training request must reference:

```
project_id
dataset_id
ingestion_session_id
schema_path
preprocessing_path
canonical_model_table_path
```

Reject the request if the dataset is not approved for training.

### **8. On training start**

Update:

```
status = running
started_at = now()
```

### **9. On training failure**

Update:

```
status = failed
failure_reason = ...
completed_at = now()
```

### **10. On training completion**

Update `training_requests`:

```
status = completed
completed_at = now()
mlflow_experiment_name = ...
registered_model_name = ...
selected_run_id = ...
selected_model_version = ...
selected_model_name = ...
selection_metric = ...
selection_score = ...
```

Create a `model_registry_records` row for the selected candidate:

```
alias = challenger
validation_status = pending_review
```

Do not automatically mark anything as `champion`.

### **11. On champion approval later**

Provide a clean service/repository method to promote a model record to champion.

This method should:

```
1. Verify the model record exists.
2. Verify it belongs to the project.
3. Verify it has validation_status = approved, or explicitly mark it approved.
4. Update MLflow alias champion if needed.
5. Update SQL app-level model_registry_records accordingly.
6. Never silently delete previous champion history.
```

This can be implemented later if too large for the first pass, but the schema should not block it.

## **Implementation constraints**

- Do not store large uploaded datasets directly in SQL.
- Do not replace MLflow with SQL.
- Do not replace manifest validation with SQL.
- Do not create customer-specific preprocessing tables.
- Do not create customer-specific Python packages.
- Keep the generic manifest ingestion pipeline as the main abstraction.
- Keep `fuel_cell` as a template-specific extractor path, but still write the same SQL lifecycle records after canonicalization.
- Avoid “latest folder” logic for approved datasets/models.
- Backend decisions should query lifecycle state from SQL.

Bad pattern:

```python
latest_dataset = sorted(os.listdir(project_dir))[-1]
model_path = f"backend/artifacts/{project_id}/latest/model.onnx"
```

Preferred pattern:

```sql
SELECT *
FROM datasets
WHERE project_id = :project_id
AND status = 'approved_for_training'
ORDER BY approved_at DESC
LIMIT 1;
```

And:

```sql
SELECT *
FROM model_registry_records
WHERE project_id = :project_id
AND alias = 'champion';
```

## **Recommended stack**

Use a lightweight DB abstraction compatible with local development and future Postgres.

Preferred:

```
SQLAlchemy or SQLModel
Alembic migrations
SQLite for local MVP if needed
PostgreSQL-ready models
```

Suggested file layout:

```
backend/app/db/session.py
backend/app/db/base.py
backend/app/models/project.py
backend/app/models/ingestion.py
backend/app/models/dataset.py
backend/app/models/training.py
backend/app/repositories/project_repository.py
backend/app/repositories/ingestion_repository.py
backend/app/repositories/dataset_repository.py
backend/app/repositories/training_repository.py
backend/app/repositories/model_registry_repository.py
```

Add service-level integration points where existing ingestion/training code can call repository methods without making ML lifecycle code too tightly coupled to FastAPI.

Suggested service files:

```
backend/app/services/ingestion_lifecycle.py
backend/app/services/training_lifecycle.py
backend/app/services/model_lifecycle.py
```

## **Suggested API endpoints**

If the backend already has similar endpoints, adapt instead of duplicating.

Potential MVP endpoints:

```
POST   /projects/{project_id}/ingestions
GET    /projects/{project_id}/ingestions
GET    /projects/{project_id}/ingestions/{ingestion_id}
POST   /projects/{project_id}/ingestions/{ingestion_id}/validate
POST   /projects/{project_id}/datasets/{dataset_id}/approve
GET    /projects/{project_id}/datasets
POST   /projects/{project_id}/training-requests
GET    /projects/{project_id}/training-requests
GET    /projects/{project_id}/models
```

The first implementation can be repository/service-only if API integration is too much for one pass, but the DB models should support these screens later.

## **Acceptance criteria**

After implementation, Mirai should be able to persistently answer:

```
Which upload packages exist for this project?
Which upload passed or failed validation?
Where is the validation report?
Which canonical dataset was produced?
Is the dataset approved for training?
Which training request used this dataset?
Which MLflow experiment/run/model version came from this training request?
Which selected model is the current challenger?
Which model is the current champion, if any?
```

There should be no need to infer critical lifecycle state from folder names.

## **Final expected outcome**

The manifest remains the customer data abstraction.

MLflow remains the experiment/model registry abstraction.

File/artifact storage remains the physical artifact store.

SQL becomes the lifecycle brain connecting them.

Final architecture:

```
Manifest/Data Dictionary
  → defines data meaning

Filesystem / MinIO / S3
  → stores physical files and artifacts

MLflow
  → tracks model experiments and registry versions

SQL
  → tracks project state, data lineage, approval, training lifecycle, and serving governance
```

This makes Mirai’s generic intake production-ready because every upload, validation, approval, dataset, training request, and model version becomes traceable.