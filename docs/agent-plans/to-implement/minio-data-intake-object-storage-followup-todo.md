# Data Intake Object Storage Follow-Up TODO

## Context

The Data Intake MVP will store uploaded raw data locally in the backend to keep implementation complexity low. This is acceptable for local demos and early pilots, but it is not the right long-term architecture for professional customer deployments.

This TODO exists so the object-storage migration is tracked explicitly and not forgotten.

## Target Outcome

Move raw uploaded datasets, zipped experiment packages, generated EDA artifacts, preprocessing artifacts, and training request bundles into an object-storage abstraction such as MinIO/S3/GCS/Azure Blob.

## Future Requirements

- [ ] Define a storage provider interface used by ingestion/preprocessing/training services.
- [ ] Support local filesystem provider for development.
- [ ] Support MinIO/S3-compatible provider for Docker Compose and production-like deployments.
- [ ] Store raw uploads by `project_id`, `dataset_id`, and `ingestion_session_id`.
- [ ] Store generated canonical tables and training artifacts by `project_id`, `dataset_id`, `ingestion_session_id`, `preprocessing_run_id`, and `training_request_id` instead of relying on a single mutable `latest` folder.
- [ ] Add a project registry/tenant isolation layer so each client only sees their own project IDs, artifacts, model-quality reports, MLflow runs, and served models.
- [ ] Replace the MVP "activate by copying into backend/data/real/.../latest" pattern with explicit model/project activation records pointing to immutable object-storage artifact URIs.
- [ ] Preserve file checksums, sizes, MIME/type detection, upload timestamp, and original filename.
- [ ] Support signed download links or backend-mediated downloads.
- [ ] Add retention/deletion policies for raw customer data.
- [ ] Add security review for customer data isolation.
- [ ] Ensure MLflow artifacts reference dataset/storage metadata without copying large raw uploads into every run.
- [ ] Update Docker Compose with MinIO service and bucket bootstrap script.
- [ ] Add tests for local and MinIO/S3 storage providers.

## Suggested Object Layout

```text
mirai-data-intake/
  projects/{project_id}/
    datasets/{dataset_id}/
      ingestion_sessions/{ingestion_session_id}/
        raw/
        manifests/
        inventory/
        eda/
        preprocessing/
        training_requests/
```

## Priority

Near-term follow-up after the local-storage MVP proves the Data Intake and Preprocessing Review workflow.
