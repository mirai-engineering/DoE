# Fuel-Cell Upload → Preprocess → Train Click Path

## Package to upload

Use the files under:

```text
data/Cathode Catalyst Degradation/
```

Select these files in **Data Intake**:

```text
mirai_manifest_template.json
data_dictionary_template.csv
02-Testing_overview/data_overview.xlsx
01-Data/Cell_01.zip
...
01-Data/Cell_42.zip
```

For the current MVP, upload `data_overview.xlsx` and the individual `Cell_NN.zip` archives directly. Do not upload one outer folder zip yet; nested package unpacking is a future enhancement.

## UI click path

1. Start backend/frontend.
2. Open **Tailored ML Model → Data Intake**.
3. Enter a project name, e.g. `PEM Fuel Cell Upload Validation`.
4. Select:
   - `data_overview.xlsx`
   - all `Cell_*.zip` files
   - `mirai_manifest_template.json`
   - `data_dictionary_template.csv`
5. Click **Create ingestion session**.
6. Confirm the session card shows:
   - `project_id`
   - `dataset_id`
   - `ingestion_session_id`
   - uploaded file count
7. Click **Review preprocessing**.
8. In **Preprocessing Review**, confirm the package validation card shows `Valid` and the expected cell archive count.
9. Click **Start preprocessing**.
10. Wait until status becomes `preprocessing_complete_needs_approval`.
11. Review canonical row counts and artifact paths.
12. Click **Approve preprocessing**.
13. Click **Create training request**.
14. Click **Start training**.
15. Wait until training status is `completed`.
16. Open **Tailored ML Model → Model Quality**.

## MVP artifact behavior

The upload session stores its own raw, extracted, canonical, and training artifacts under:

```text
backend/data/intake/projects/{project_id}/datasets/{dataset_id}/ingestion_sessions/{ingestion_session_id}/
```

After training completes, the MVP copies the selected session's active artifacts into the existing runtime `latest` locations so Model Quality immediately shows the new trained result:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/
backend/data/real/pem_fuel_cell_cathode_degradation/training_artifacts/latest/
data/reference/pem_fuel_cell_cathode_degradation/training_artifacts/latest/
```

For professional multi-client deployment, this mutable-copy activation should be replaced by immutable MinIO/S3 artifact URIs and per-project activation records. That follow-up is tracked in:

```text
docs/agent-plans/to-implement/minio-data-intake-object-storage-followup-todo.md
```
