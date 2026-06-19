# Approved Training Package Export Plan

## Context

Mirai DoE currently supports the demo lifecycle:

`Upload → preprocess → approve → create training request → start recommended training`

For the current Railway/Fraunhofer pilot, the next needed step is a governed export between training-request creation and training execution:

`Upload → preprocess → approve → create training request → export approved training package → manually train locally on MacBook → later log/register artifacts remotely`

The export must let an authorized workspace member download only the exact approved training-ready package for a specific project/dataset/session/training request. It must not expose S3 buckets, object keys, storage prefixes, credentials, public URLs, or arbitrary backend file paths to the browser.

The later automated local training CLI and remote artifact registration workflow are context only and are not part of this implementation.

## Approach

Add a protected FastAPI export endpoint nested under the existing data-intake training-request route:

`GET /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests/{training_request_id}/export-package`

The endpoint will:

1. Rely on the existing Clerk middleware path ownership check for `/data-intake/projects/{project_id}/...`.
2. Re-resolve the authorized workspace from `Request` using existing helpers.
3. Validate the project belongs to that workspace through the existing project access checks/control-plane state.
4. Load the ingestion session and training request server-side from canonical backend session storage.
5. Reject if any route IDs do not match the stored session/training request payload.
6. Reject if preprocessing is not `approved_for_training`.
7. Build a ZIP in memory or via a bounded temporary file from server-selected files only:
   - `model_table.parquet` if available;
   - otherwise `model_table.csv`;
   - `schema.json`;
   - generated `training_manifest.json`.
8. Stream the ZIP through the authenticated backend response with `Content-Disposition: attachment`.
9. Compute package checksum/size where practical and record an `approved_training_package_exported` audit event.

No frontend request body/query parameter should specify bucket, key, object path, or file path. The frontend only calls the endpoint derived from the already selected session and known training request ID.

## Agents, subagents, and skills for implementation

Use the following execution support if available in the coding environment:

### Subagents / agents

- **Scout/read-only agent**
  - Purpose: confirm final code locations and edge cases before editing.
  - Scope: `backend/app/main.py`, `backend/app/services/training_requests.py`, `backend/app/services/data_intake.py`, `backend/app/services/preprocessing_review.py`, `backend/app/services/control_plane.py`, `backend/tests/test_api.py`, `frontend/src/lib/api.ts`, `frontend/src/components/PreprocessingReviewPage.tsx`.
  - Output: concise route/service/test/UI pointers; no edits.

- **Backend implementation agent**
  - Purpose: implement export package assembly, endpoint, server-side validation, and audit logging.
  - Acceptance focus: no arbitrary file/path/object export; strict membership/project/session/request validation; ZIP contents limited to approved artifacts.

- **Frontend implementation agent**
  - Purpose: add authenticated download helper and UI button/copy near the training-request area.
  - Acceptance focus: frontend sends no bucket/key/path inputs and clearly warns that the package leaves managed Mirai.

- **Security/code-review agent**
  - Purpose: review authz, route ID validation, archive contents, path traversal resistance, S3 secrecy, and audit behavior.
  - Acceptance focus: no public URLs, no presigned URLs, no direct browser S3 links, no storage metadata in the frontend API contract.

- **Test/QA agent**
  - Purpose: add/extend backend and frontend tests and run verification commands.
  - Acceptance focus: all required positive/negative tests pass; frontend build passes.

### Local project skills

- `.pi/skills/repo-postgres-migrations/SKILL.md`
  - Use only to confirm no migration is needed and to inspect audit-log schema if needed.
  - This change should reuse the existing `audit_logs` table and `log_audit`; no new DB migration is expected.

- `.pi/skills/use-railway/SKILL.md`
  - Use only after local tests pass, if live Railway validation/deploy is requested.
  - Do not print secrets; audit variable names only.

- `.pi/skills/clerk-react-patterns/SKILL.md`
  - Use for Clerk-authenticated frontend calls and avoiding raw `<a href>` downloads that omit auth headers.

- `.pi/skills/project-artifact-cleanup/SKILL.md`
  - Not part of implementation; optional later for cleaning the prior orphan failed-upload object after smoke tests.

### Global skills

- `/Users/brunocopa/.pi/agent/skills/security-and-hardening/SKILL.md`
  - Use for secure download/export review, authorization checks, no credential leakage, and audit expectations.

- `/Users/brunocopa/.pi/agent/skills/api-and-interface-design/SKILL.md`
  - Use for endpoint contract clarity, response headers, and error semantics.

- `/Users/brunocopa/.pi/agent/skills/frontend-ui-engineering/SKILL.md`
  - Use for UI placement, button state, download UX, and warning copy.

- `/Users/brunocopa/.pi/agent/skills/test-driven-development/SKILL.md`
  - Use for implementing the required tests before/with the feature.

- `/Users/brunocopa/.pi/agent/skills/code-review-and-quality/SKILL.md`
  - Use for final self-review and regression checks.

## Files to modify

Backend:

- `backend/app/main.py`
  - Add protected export endpoint under the existing training-request routes.
  - Use `Request` so the endpoint can log Clerk user, workspace, and client IP.
  - Call the new service function and return `StreamingResponse` or `FileResponse` from a temporary ZIP.

- `backend/app/services/training_requests.py`
  - Add server-side export package builder/validator, for example `build_approved_training_package(...)`.
  - Reuse `get_training_request`, `get_preprocessing_review_report`, `get_ingestion_session`, `session_workspace`, and existing JSON helpers.
  - Prefer `canonical/model_table.parquet` if it exists; otherwise include `canonical/model_table.csv`.
  - Include `training_latest/schema.json` or the canonical/session schema path already used by training, whichever is the current source of truth.
  - Generate `training_manifest.json` with the required metadata.

- `backend/app/services/control_plane.py`
  - Reuse existing `log_audit`; no schema change expected.
  - Only adjust if an ergonomic wrapper is needed, but avoid migration unless required.

- `backend/tests/test_api.py`
  - Add backend route tests for authorized export, no-workspace 403, cross-workspace denial, unapproved preprocessing denial, mismatched training request denial, ZIP contents, and audit event.

Possibly backend schema/type files if response helpers are typed:

- `backend/app/schemas.py`
  - Only if a typed response model or request model becomes necessary. The endpoint should likely need no request body.

Frontend:

- `frontend/src/lib/api.ts`
  - Add authenticated `exportApprovedTrainingPackage(session, trainingRequestId)` helper using the existing authenticated Axios instance and `responseType: 'blob'`.
  - Trigger browser download from the returned blob; do not return or expose storage locations.

- `frontend/src/components/PreprocessingReviewPage.tsx`
  - Add “Export approved training package” action near the training-request area.
  - Show only when preprocessing is approved and a valid `trainingRequest` exists.
  - Add governed intent copy and warning that the package leaves the managed Mirai environment.
  - Do not put this action on the unauthenticated/raw `<a href>` pattern used by the current EDA HTML link.

## Reuse

- Existing Clerk/membership/project authorization middleware:
  - `backend/app/main.py`
  - `require_clerk_auth(...)`
  - `_project_id_from_path(...)`
  - `_request_can_access_project(...)`
  - `_raise_if_no_workspace_access(...)`
  - `_authorized_workspace_id(...)`
  - `_request_user_id(...)`

- Existing membership and control-plane utilities:
  - `backend/app/services/control_plane.py`
  - `resolve_workspace_membership(...)`
  - `get_workspace_project(...)`
  - `log_audit(...)`

- Existing session and artifact layout helpers:
  - `backend/app/services/data_intake.py`
  - `session_workspace(...)`
  - `ensure_session_workspace(...)`
  - `get_ingestion_session(...)`
  - `read_status(...)`

- Existing preprocessing approval source of truth:
  - `backend/app/services/preprocessing_review.py`
  - `get_preprocessing_review_report(...)`
  - status/approval value: `approved_for_training`

- Existing training request source of truth:
  - `backend/app/services/training_requests.py`
  - `get_training_request(...)`
  - `list_training_requests(...)`
  - file-backed training requests under the session workspace.

- Existing frontend authenticated API client:
  - `frontend/src/lib/api.ts`
  - Use the configured Axios instance so Clerk bearer headers are included.

## Endpoint contract

### Request

`GET /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests/{training_request_id}/export-package`

No request body. No query parameters required. The frontend must not send bucket, key, object path, filesystem path, or arbitrary artifact selection.

### Success response

- Status: `200 OK`
- Content-Type: `application/zip`
- Content-Disposition: attachment filename similar to:
  - `mirai-training-package-{project_id}-{dataset_id}-{training_request_id}.zip`
- Body: streamed ZIP bytes.

### Error responses

- `403` with existing structured no-membership/access-denied behavior when Clerk user has no workspace or cannot access the project.
- `400` when preprocessing is not approved or the training request/session relationship is invalid.
- `404` or existing API-safe file-not-found mapping when the training request does not exist.
- `503` only when required approved artifacts are unexpectedly missing after preprocessing.

## Package structure

ZIP root should contain only:

```text
model_table.parquet        # preferred if available
# or
model_table.csv            # fallback only if parquet is unavailable
schema.json
training_manifest.json
```

No raw upload ZIPs, no source CSV folders, no S3 metadata, no bucket/key/prefix values, no credentials, no MLflow files, and no arbitrary extra files.

`training_manifest.json` fields:

```json
{
  "workspace_id": "fraunhofer",
  "project_id": "...",
  "dataset_id": "...",
  "session_id": "...",
  "training_request_id": "...",
  "feature_columns": ["..."],
  "target_columns": ["..."],
  "preprocessing_contract_version": "...",
  "source_checksums": {"...": "..."},
  "exported_at": "ISO-8601 timestamp",
  "package_format_version": "1"
}
```

Feature/target columns should come from `schema.json`/approved domain metadata rather than frontend input. Source checksum(s) should reuse dataset upload checksum(s), training request metadata, or canonical-file checksum(s), whichever are available server-side; document any missing source checksum limitation.

## UI location and behavior

In `PreprocessingReviewPage.tsx`, place a secondary governed export card/button inside or immediately below the existing “Recommended training” section, visible when:

- selected session exists;
- preprocessing is approved;
- `trainingRequest` is present.

Button label:

`Export approved training package`

Copy:

`Download the approved, versioned dataset package for authorized local or on-premise training. Export activity is recorded in the project audit trail.`

Warning text:

`This package leaves the managed Mirai environment. Store and handle it according to your workspace data-governance policy.`

On click:

1. Call authenticated API helper with only session IDs already in app state and `training_request_id`.
2. Receive ZIP blob.
3. Create temporary object URL in browser and trigger file download.
4. Revoke object URL.
5. Show success/error message.

Do not use a raw `<a href="...">` to the API, because Clerk auth headers may be omitted in a new tab/download.

## Steps

- [ ] Add tests first for the backend export endpoint around an approved Fraunhofer fixture session and training request.
- [ ] Add `build_approved_training_package(...)` service logic that validates preprocessing approval and training request/session/project/dataset identity.
- [ ] Add safe ZIP assembly with exactly the approved files and generated manifest.
- [ ] Add package checksum/size calculation around ZIP generation.
- [ ] Add protected FastAPI endpoint returning the ZIP through authenticated backend streaming.
- [ ] Add audit logging event `approved_training_package_exported` with user, workspace, project, dataset/session, training request, timestamp, checksum, and size where practical.
- [ ] Add negative tests for no workspace, cross-workspace user, unapproved preprocessing, mismatched training request, and ZIP content allowlist.
- [ ] Add frontend authenticated blob download helper.
- [ ] Add UI button/copy/warning near the training-request area, hidden until preprocessing approval plus training request exist.
- [ ] Add/adjust frontend tests or static assertions proving no bucket/key/path inputs are sent, if the existing frontend test setup supports it.
- [ ] Run backend tests and frontend build.
- [ ] Perform a final security review for storage metadata leakage and path traversal/arbitrary export risks.

## Verification

Run locally:

```bash
cd backend && uv run pytest tests/test_api.py -q
npm --prefix frontend run build
git diff --check
```

If a narrower backend test selection is practical during development, also run the specific new tests by name with `uv run pytest tests/test_api.py -k export -q`.

Manual browser verification after deploy, if requested:

1. Log in as Fraunhofer member.
2. Use an approved preprocessing session with an existing training request.
3. Confirm the button appears only after training request creation.
4. Click export and verify a ZIP downloads.
5. Inspect ZIP locally:
   - exactly `model_table.parquet` or `model_table.csv`, `schema.json`, `training_manifest.json`;
   - no raw upload ZIP;
   - no bucket/key/prefix/credential fields.
6. Confirm an audit log row exists for `approved_training_package_exported`.
7. Log in as/no-token-test unassigned user and confirm 403/no export.
8. Confirm `test-client-isolated` user cannot export Fraunhofer package.

## Test coverage checklist

- [ ] Fraunhofer member can export an approved package for an authorized training request.
- [ ] Unassigned user receives `403` / `no_workspace_membership`.
- [ ] `test-client-isolated` user cannot export Fraunhofer data.
- [ ] Export fails safely if preprocessing is not approved.
- [ ] Export fails safely if the training request does not belong to the dataset/session/project.
- [ ] ZIP contains only approved training artifacts and manifest/schema.
- [ ] Frontend cannot supply bucket/key/path inputs.
- [ ] Audit event is recorded.

## Limitations and risks to document in deliverable

- Parquet may not currently be produced by preprocessing. If unavailable, the first implementation should include `model_table.csv` and document the fallback. Do not add a new parquet dependency unless it is already available in `backend/pyproject.toml` or explicitly approved.
- For large training tables, in-memory ZIP creation may be inefficient. Prefer a temporary file or streaming ZIP implementation if expected package size can exceed comfortable memory bounds.
- Existing EDA HTML download uses a raw link and can miss Clerk auth headers; the export must use authenticated blob download instead.
- Training requests are currently file-backed under the session workspace, not a Postgres table. Validation must compare the stored JSON IDs with route IDs.
- The audit log should not block the export if current `log_audit` remains best-effort, but tests should verify it records during normal operation.

## Deliverables expected after implementation

- Changed files.
- Endpoint contract.
- Package structure.
- UI location/behavior.
- Tests and commands run.
- Any limitations, especially parquet availability or large-file streaming concerns.
