# Intake, Canonical, and EDA S3 Persistence Plan

## Context

Before ML preprocessing v1, Mirai needs durable persistence for the earlier lifecycle stages in Railway object storage. Today the uploaded ZIP can persist, and MLflow artifacts are linked to S3, but generated intake/preprocessing/EDA outputs can remain on Railway-local ephemeral filesystem paths. This breaks downloading EDA reports and makes downstream lifecycle steps fragile across redeploys.

The goal is a small, robust improvement: persist generated intake artifacts, canonical artifacts, preprocessing-review artifacts, and EDA artifacts to the existing workspace/project S3 prefix without hardcoded client-specific paths or duplicating MLflow storage logic.

## Approach

Make object storage the durable source of truth for generated lifecycle artifacts, while keeping Railway-local files as temporary working/cache files.

1. **Reuse existing storage abstractions.** Do not introduce a new S3 client path. Use `WorkspaceStorageConfig`, `put_workspace_object()`, `upload_workspace_directory_tree()`, `get_workspace_object()`, `validate_workspace_object_key()`, and `get_project_storage_config()` / `workspace_s3_config_from_env()`.
2. **Persist generated artifacts immediately after generation, not only on approval.** Today `_persist_preprocessing_outputs()` runs from `approve_preprocessing()`, which is too late for EDA download/review and loses artifacts across redeploys. Persist canonical, preprocessing, EDA, status, inventory, and session metadata as soon as they are generated/updated.
3. **Use versioned session-scoped prefixes, plus optional latest pointers.** Avoid overwriting every session into `canonical/latest` or `eda/latest` only. Persist immutable/session-scoped artifacts under dataset/session keys, then optionally write lightweight `latest` manifests/pointers.
4. **Record artifact metadata.** Store object URI/key, sha256, size, content type, artifact kind, dataset ID, session ID, lifecycle stage, and generated timestamp in the local report/status JSON and `artifact_objects` where Postgres is enabled.
5. **Make readers object-storage aware.** Endpoints such as y-data HTML download should resolve in this order: local cache path if present and checksum-valid → object storage object key from report/status metadata → regenerate only when canonical source exists and regeneration is safe. In Railway, object storage fallback must handle the normal case where local files were lost.
6. **Keep raw uploads separate from generated artifacts.** Raw ZIP/object upload persistence already exists. This plan covers generated outputs: extracted inventory, canonical model table, schema, preprocessing/validation/split reports, y-data HTML/JSON, EDA summaries, and review reports.
7. **No hardcoded clients or buckets.** Prefixes derive from the project storage config and authenticated workspace/project/session context. The Fraunhofer `mirai-fuel-cells-demo` bucket shown in Railway is just one configured bucket, not a code path.

### Recommended object layout

Under the existing configured project prefix, e.g. `workspaces/{workspace_id}/projects/{project_id}`:

```text
raw/{dataset_id}/...                         # already exists for uploaded ZIP/files
intake/{dataset_id}/{session_id}/session.json
intake/{dataset_id}/{session_id}/inventory/file_inventory.json
canonical/{dataset_id}/{session_id}/model_table.csv
canonical/{dataset_id}/{session_id}/rejected_rows.csv
canonical/{dataset_id}/{session_id}/dataset_profile.json
preprocessing/{dataset_id}/{session_id}/schema.json
preprocessing/{dataset_id}/{session_id}/preprocessing.json
preprocessing/{dataset_id}/{session_id}/split_report.json
preprocessing/{dataset_id}/{session_id}/validation_report.json
preprocessing/{dataset_id}/{session_id}/eda_report.json
eda/{dataset_id}/{session_id}/preprocessing_report.json
eda/{dataset_id}/{session_id}/ydata_profile.html
eda/{dataset_id}/{session_id}/ydata_profile.json
status/{dataset_id}/{session_id}/preprocessing.json
manifests/{dataset_id}/{session_id}/artifact_manifest.json
latest/artifact_manifest.json                # optional pointer to active dataset/session
```

This preserves all sessions and makes `latest` a pointer, not the only durable location.

## Files to modify

- `backend/app/services/data_intake.py`
  - Persist `session.json` and `inventory/file_inventory.json` to object storage when sessions are created/appended.
  - Update session storage metadata to include durable generated-artifact manifest pointers, not just raw upload object metadata.
- `backend/app/services/preprocessing_review.py`
  - Split current `_persist_preprocessing_outputs()` into reusable, stage-aware persistence helpers.
  - Call persistence after `start_generic_preprocessing()` writes canonical/training/EDA artifacts, after y-data report generation, after report generation, and after approval/status updates.
  - Make `ensure_ydata_html_report()` object-storage aware.
  - Make `get_preprocessing_eda_summary()` and `get_preprocessing_review_report()` optionally hydrate from object storage when local files are absent.
- `backend/app/services/workspace_storage.py`
  - Reuse existing functions; possibly add small helper(s) for object metadata/checksum calculation or object-to-local-cache hydration if needed.
- `backend/app/services/control_plane.py`
  - Reuse `record_artifact_object()` for generated artifacts; no schema change unless metadata queries need stronger indexing later.
- `backend/app/main.py`
  - Keep route shapes stable; update y-data/report endpoints to call object-storage-aware service functions.
- `backend/tests/test_workspace_storage.py`, `backend/tests/test_api.py`, and focused new tests for lifecycle artifact persistence and S3 fallback behavior.
- Docs: update Railway/object-storage docs to explain required env vars and expected bucket layout.

## Reuse

Existing reusable code found:

- `backend/app/services/data_intake.py`
  - `_store_upload()` already persists raw uploads to S3/local object storage and records object metadata.
  - `session_workspace()` centralizes local working directories for raw, canonical, training artifacts, EDA, status, inventory.
  - `write_status()` / `read_status()` centralize status files but currently local-only.
- `backend/app/services/preprocessing_review.py`
  - `start_generic_preprocessing()` already produces canonical and training artifacts.
  - `ensure_ydata_html_report()` generates y-data HTML from canonical `model_table.csv`.
  - `_persist_preprocessing_outputs()` already uploads `canonical`, `training_latest`, and `eda`, but only on approval and only to `canonical/latest`, `preprocessing/latest`, `eda/latest`.
- `backend/app/services/workspace_storage.py`
  - `WorkspaceStorageConfig`, `put_workspace_object()`, `upload_workspace_directory_tree()`, `get_workspace_object()`, `list_workspace_objects()`, and validation helpers already support local and S3 modes with workspace prefix enforcement.
  - Railway/production already requires `OBJECT_STORAGE_BACKEND=s3`.
- `backend/app/services/control_plane.py`
  - `record_uploaded_dataset()` and `record_artifact_object()` already model durable object metadata in Postgres.
- Existing tests verify raw upload persistence, workspace prefix safety, directory-tree upload, and current local y-data HTML route.

## Agent and skill mapping

Use the configured Pi subagents and repo skills as follows during implementation. If the subagent runner is unavailable or still has connection issues, perform the same scoped work directly and note that in the handoff.

### Subagents

- `scout`
  - First implementation step, read-only.
  - Re-scan `backend/app/services/data_intake.py`, `backend/app/services/preprocessing_review.py`, `backend/app/services/workspace_storage.py`, `backend/app/main.py`, and relevant tests before editing.
  - Confirm no existing helper already persists or hydrates generated artifacts by session-scoped object key.
- `planner`
  - Use only if implementation scope changes after scout findings.
  - Keep this plan aligned with repo instructions, object layout, and the ML preprocessing v1 dependency chain.
- `worker`
  - Implement the backend changes in small phases:
    1. artifact manifest/persistence helpers,
    2. generated-artifact upload trigger points,
    3. object-storage-aware read/hydration paths,
    4. tests and docs.
  - Avoid frontend/API route renames unless the user explicitly approves.
- `reviewer`
  - Review for tenant isolation, object-key validation, accidental local path/S3 key leakage in UI-facing payloads, and Railway behavior after local filesystem loss.
  - Check that no new S3 client path bypasses `workspace_storage.py` validation.
- `context-builder`
  - Optional for larger follow-up work: summarize the final durable artifact model for the ML preprocessing v1 implementation handoff.
- `researcher`
  - Optional only if external Railway/S3 behavior is unclear. Prefer existing repo abstractions before web research.
- `delegate` / `oracle`
  - Reserve for targeted second opinions on tricky edge cases, such as manifest versioning semantics or backwards-compatible fallback behavior.

### Skills

- `.pi/skills/use-railway/SKILL.md`
  - Use for Railway verification, bucket/object-storage inspection, env-variable checks, redeploy/restart smoke tests, and CLI/MCP routing.
  - Do not print secrets or bucket credentials. Report only presence/absence and object layout/status.
- `.pi/skills/mlflow-onboarding/SKILL.md`
  - Not a primary implementation skill, but use its traditional-ML framing to avoid disrupting existing MLflow training/artifact flows.
  - Verify this work does not move MLflow model artifacts or change the generic tabular DoE training lifecycle.
- `.pi/skills/querying-mlflow-metrics/SKILL.md`
  - Optional post-change diagnostic only if MLflow runs/metrics are suspected to be impacted. Not required for the core intake/EDA persistence change.
- `.pi/skills/clerk-testing/SKILL.md`
  - Optional if adding browser/E2E checks around authenticated EDA downloads. Backend route tests remain the primary verification for this plan.
- `.pi/skills/github-mcp-workflow/SKILL.md`
  - Optional for PR/commit workflow after implementation, if the user asks for GitHub operations.
- Clerk setup/custom UI/org/webhook skills
  - Not needed for this plan unless auth behavior or organization-scoped access changes unexpectedly.

## Gaps Found

- Raw uploaded files persist through `_store_upload()`, but generated session/inventory/status artifacts are written only to the local object-root mirror.
- Generated canonical/EDA/preprocessing artifacts are uploaded only during `approve_preprocessing()`. Users need to download/review EDA before approval, so this is too late.
- `ensure_ydata_html_report()` serves/generates from local `workspace["eda"]` and local `canonical/model_table.csv`; it cannot read a persisted y-data HTML or canonical table from S3 after redeploy.
- `get_preprocessing_eda_summary()` returns local relative paths such as `training_artifacts/latest/eda_report.json`; these are not durable object pointers and may not exist in Railway after redeploy.
- Current generated artifact upload prefixes use project-level `canonical/latest`, `preprocessing/latest`, `eda/latest`, which can overwrite or obscure dataset/session lineage.
- `artifact_objects` records raw uploads today, but generated canonical/EDA/preprocessing artifacts are not consistently recorded as separate artifact kinds.
- The screenshot confirms the bucket has workspace-level folders (`mlflow-artifacts/`, `projects/`), but the prior lifecycle artifacts need a complete `projects/{project_id}/...` layout under the same bucket/prefix.

## Steps

- [ ] Define constants/helpers for lifecycle artifact sets:
  - `session_metadata`: `session.json`, inventory.
  - `canonical`: `model_table.csv`, `rejected_rows.csv`, canonical profiles/reports.
  - `preprocessing_artifacts`: `schema.json`, `preprocessing.json`, split/validation/dataset/EDA reports.
  - `eda`: `preprocessing_report.json`, `ydata_profile.html`, `ydata_profile.json`.
  - `status`: relevant status JSON files.
- [ ] Add a small generic persistence helper, e.g. `persist_session_artifact_set(project_id, dataset_id, session_id, artifact_set, local_dir_or_files)`:
  - Resolve workspace ID from session.
  - Resolve project storage config.
  - Upload under session-scoped prefix.
  - Compute/store sha256 and size for each object.
  - Return an `artifact_manifest.json` payload.
  - Record each object with `record_artifact_object()` when Postgres is enabled.
  - In local/dev without configured S3, keep current behavior and report `status: skipped/local` rather than failing.
- [ ] Persist session metadata immediately after `create_ingestion_session()` and `append_ingestion_files()`.
- [ ] Persist generated canonical/preprocessing/EDA artifacts immediately at the end of `start_generic_preprocessing()` before returning `preprocessing_complete_needs_approval`.
- [ ] Persist y-data HTML/JSON immediately after `ensure_ydata_html_report()` generates them; if the report already exists in object storage, hydrate it to local cache instead of regenerating.
- [ ] Persist `preprocessing_report.json` from both `generate_preprocessing_report()` and `approve_preprocessing()`.
- [ ] Replace project-level-only `canonical/latest`, `preprocessing/latest`, `eda/latest` uploads with session-scoped uploads plus an optional `latest/artifact_manifest.json` pointer.
- [ ] Add read helpers:
  - `load_artifact_from_local_or_object_storage(...)` for JSON/HTML bytes.
  - `hydrate_artifact_set_from_manifest(...)` for canonical/EDA files needed by downstream code.
  - Ensure all object keys are validated under the workspace/project prefix.
- [ ] Update y-data route to return `FileResponse` from local cache when present, or `Response(bytes, media_type="text/html")` from object storage if only S3 exists.
- [ ] Update EDA/report summary payloads to expose durable artifact availability/status and friendly download endpoints, not raw local filesystem paths or raw S3 keys in user-facing UI.
- [ ] Add tests:
  - Generated artifacts are uploaded under `canonical/{dataset_id}/{session_id}`, `preprocessing/{dataset_id}/{session_id}`, and `eda/{dataset_id}/{session_id}` immediately after preprocessing completes.
  - EDA HTML endpoint succeeds after local `eda/ydata_profile.html` is deleted but persisted object exists.
  - Canonical/readiness summary can hydrate from object storage after local cache is missing.
  - `approve_preprocessing()` updates status/report and persists the approved report without losing existing generated artifacts.
  - Cross-workspace object-key attempts are rejected.
  - Raw/reference directories remain excluded from generated artifact uploads.

## Verification

- Focused backend tests for workspace storage, data intake upload, generic preprocessing lifecycle, and y-data download fallback.
- Manual/Railway smoke test:
  1. Upload the Fraunhofer ZIP.
  2. Run preprocessing to `preprocessing_complete_needs_approval`.
  3. Confirm Railway bucket contains session-scoped `canonical/`, `preprocessing/`, `eda/`, `status/`, and `manifests/` objects under `workspaces/fraunhofer/projects/{project_id}`.
  4. Open/download EDA report before approval.
  5. Redeploy/restart the Railway service.
  6. Open/download the same EDA report again from object storage.
  7. Approve preprocessing and verify updated approval report/status persists.
- Confirm no raw source expansion folders or oversized raw references are uploaded as generated artifacts.
- Confirm no frontend or logs expose raw bucket credentials; UI should show availability/download actions, not secrets.
