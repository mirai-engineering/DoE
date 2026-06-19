# Railway Clerk Project Onboarding and S3 Intake Plan

## Context

The Railway/Clerk workspace isolation fix is working: a new Clerk user sees no Fraunhofer workspace, while the fuel-cell Clerk user sees only the Fraunhofer fuel-cell workspace/project. The remaining gaps are product and durability issues:

- Users with no projects do not have a clear UI path to name their workspace/client and create/upload their first project.
- The current operator view can still create confusing mental models around Railway buckets (for example the Railway canvas shows both `mirai-fuel-cells-demo` and empty `mirai-batteries-demo`, while the app should present user/project storage, not infrastructure buckets). A read-only production check currently shows the fuel-cell Clerk workspace/project in Postgres, plus the legacy `fraunhofer` workspace row; the second empty Clerk user is not yet represented as a workspace row, so it should be provisioned once its Clerk user id is known.
- `DataIntakePage` currently supports new/existing project upload, but it is only reachable when the app already has a selected schema/project. Empty-project users need an onboarding/intake entry point.
- Backend intake currently stores upload files under the local object-storage mirror path (`local_filesystem` in session metadata). In Railway production, uploads should be durably stored as S3 objects under the authenticated Clerk workspace/project prefix, with Postgres metadata/pointers, so storage isolation can be verified independently of local container state.
- The intended tenancy model for this pilot is: Clerk user id = workspace/client; each workspace has one dedicated bucket; each workspace can contain many projects; each project has its own project storage prefix inside that user's bucket.

## Approach

Implement a production-safe onboarding and intake flow that derives tenancy only from authenticated Clerk JWT `sub`, creates missing workspace/project records explicitly in Postgres, assigns project storage metadata, writes uploaded package files to project-scoped S3/object storage, and updates the frontend so empty users can create their workspace/project without seeing irrelevant battery demo/bucket language.

Recommended storage behavior for this increment:

- Use **one Railway bucket per Clerk user/client** for the pilot.
- Allow multiple project folders/prefixes inside that Clerk user's bucket.
- Do **not** let one Clerk user's projects share a bucket with another Clerk user's projects during the demo.
- Do **not** create Railway bucket services automatically from regular user uploads. Railway bucket provisioning should be operator/admin controlled for now, because bucket creation is infrastructure, not project data-plane behavior.
- Add an explicit operator/admin provisioning path for approved demo users: create/assign a bucket, store it in `workspaces.storage`, then let the app create projects/prefixes inside it.
- For the two known Clerk demo users, it is advisable to provision/assign buckets now, before testing upload. The empty user does not need a project yet, but should have a workspace row and dedicated bucket assignment so the first upload cannot accidentally route to a shared/fallback bucket.
- For the current fuel-cell user, keep using the existing assigned bucket only for that Clerk workspace, with project data under `workspaces/<clerk_user_id>/projects/<project_id>/...`.
- For newly created projects, inherit the authenticated workspace's bucket from `workspaces.storage`, and write project-specific objects under `workspaces/<clerk_user_id>/projects/<project_id>/...`.
- If a new user has no assigned bucket yet, the UI should show a clear "workspace storage not provisioned" state rather than silently using a shared fallback bucket.
- Always isolate by verified `workspace_id`, bucket assignment, and project prefix; validate every object key using existing storage validators.

## Files to modify

- `backend/app/main.py`
  - Ensure intake endpoints require/derive authenticated workspace context.
  - Add or update project/workspace creation endpoint behavior if needed.
- `backend/app/services/data_intake.py`
  - Replace upload-only-local persistence with object-storage-aware persistence.
  - Store upload files under project storage prefix, e.g. `.../intake/<dataset_id>/<session_id>/raw/<filename>`.
  - Return S3/object metadata in session responses.
- `backend/app/services/control_plane.py`
  - Add helpers to create/ensure workspace and project rows for authenticated users.
  - Add project storage config assignment for new projects.
  - Insert dataset/session/artifact metadata rows as appropriate.
- `backend/app/services/workspace_storage.py`
  - Reuse existing validation helpers and add write/upload helper if missing.
- `backend/app/schemas.py`
  - Extend response schemas only if needed for object URI / bucket / prefix fields.
- `backend/tests/test_api.py`
  - Add regression tests for empty workspace onboarding, authenticated workspace-only intake, and no cross-workspace access.
- `backend/tests/test_workspace_storage.py`
  - Add tests for S3/local object write key validation and prefix confinement.
- `frontend/src/App.tsx`
  - Render an onboarding/data-intake empty state when `/projects` returns no projects.
- `frontend/src/components/DataIntakePage.tsx`
  - Allow use without a selected schema/project.
  - Make workspace naming explicit but subordinate to authenticated user identity.
  - Remove confusing default workspace/project assumptions for empty users.
- `frontend/src/components/ProjectHeader.tsx`
  - Handle zero-project state gracefully.
- `frontend/src/lib/api.ts`
  - Add/adjust API types and calls for onboarding/intake responses.

## Reuse

- `backend/app/auth.py`
  - Reuse verified Clerk JWT subject as the only authoritative workspace id.
- `backend/app/services/control_plane.py`
  - Reuse `list_workspace_projects`, `get_project_storage_config`, `get_project_runtime_state`, and audit hardening patterns.
- `backend/app/services/workspace_storage.py`
  - Reuse `WorkspaceStorageConfig`, `validate_workspace_object_key`, `object_storage_uri`, `local_object_storage_path`, and S3 client configuration patterns.
- `backend/app/services/data_intake.py`
  - Reuse safe filename handling, ingestion session shape, package validation status, and session workspace lifecycle.
- `frontend/src/components/DataIntakePage.tsx`
  - Reuse the existing guided upload card and lifecycle stepper instead of creating a separate upload UI.
- `frontend/src/components/ui.tsx`
  - Reuse existing `LifecycleStepper`, `SectionCard`, and `DisclosurePanel` styling.

## Skills and subagent assignments

Use repo-local skills during implementation:

- `.pi/skills/use-railway/SKILL.md` for Railway CLI diagnostics, deployment status, service/bucket checks, and safe Railway operations.
- `.pi/skills/repo-postgres-migrations/SKILL.md` for explicit SQL migration design/application and production Postgres verification.
- `.pi/skills/clerk-backend-api/SKILL.md` and other repo Clerk auth skills for Clerk identity, JWT, user id, and protected admin access patterns.
- `.pi/skills/project-artifact-cleanup/SKILL.md` before removing the battery bucket or generated artifacts.

Map global skills where useful; repo-local skills take precedence when they cover the same area:

- Global `frontend-ui-engineering` (`/Users/brunocopa/.pi/agent/skills/frontend-ui-engineering/SKILL.md`) for empty-state UI, upload UX, and polished onboarding flow.
- Global `security-and-hardening` (`/Users/brunocopa/.pi/agent/skills/security-and-hardening/SKILL.md`) for Clerk-derived tenancy, admin-only provisioning, and cross-user isolation review.
- Global `test-driven-development` (`/Users/brunocopa/.pi/agent/skills/test-driven-development/SKILL.md`) for regression test design around no-project users, object storage, and forbidden access.
- Global `git-workflow-and-versioning` (`/Users/brunocopa/.pi/agent/skills/git-workflow-and-versioning/SKILL.md`) for scoped staging, commit hygiene, and push workflow.
- Global `code-review-and-quality` (`/Users/brunocopa/.pi/agent/skills/code-review-and-quality/SKILL.md`) for final implementation review.
- Global `debugging-and-error-recovery` (`/Users/brunocopa/.pi/agent/skills/debugging-and-error-recovery/SKILL.md`) for Railway/runtime troubleshooting if upload or bucket routing fails.

Subagent roles, if the configured agent list contains suitable agents at execution time:

- Backend/storage implementer: object-storage writes, control-plane records, endpoint isolation, SQL migration hooks.
- Frontend/onboarding implementer: empty state, admin provisioning UI, upload UX, no-project handling.
- Security reviewer: Clerk-derived tenancy, admin-only provisioning authorization, object-key confinement, cross-workspace access.
- Railway/operator reviewer: bucket provisioning/removal plan and production smoke checklist.
- Test reviewer: targeted regression coverage for no-project users, bucket assignment, and cross-user isolation.

Before implementation, list available subagents and bind these roles to the closest installed agents; do not invent unavailable agents.

## Steps

- [ ] Verify current production state from CLI before changes:
  - [ ] list workspaces/projects/storage metadata;
  - [ ] confirm the new Clerk user has no project rows;
  - [ ] confirm the fuel-cell user has only the Fraunhofer fuel-cell project;
  - [ ] confirm no runtime project uses `mirai-batteries-demo` unless explicitly assigned.
- [ ] Backend: add object-storage write support for uploads.
  - [ ] Add a safe helper to write bytes to local mirror or S3 based on `WorkspaceStorageConfig`/backend mode.
  - [ ] Store uploaded files under the resolved project storage prefix.
  - [ ] Include bucket/key/object_uri/sha256/size in file metadata without logging secrets.
- [ ] Backend: make new-project intake create durable control-plane records.
  - [ ] Ensure the Clerk workspace row exists for the authenticated user.
  - [ ] Require the authenticated workspace to have an assigned bucket in `workspaces.storage` before accepting production uploads.
  - [ ] Create a project row immediately when uploading a new project, per current product preference.
  - [ ] Assign `projects.storage` by inheriting the workspace bucket and setting a project prefix: `workspaces/<clerk_user_id>/projects/<project_id>`.
  - [ ] Create/update dataset/session metadata rows as needed so `/projects`, `/schema`, `/artifact-status`, and intake session listing work after upload.
- [ ] Backend: enforce isolation.
  - [ ] All intake session lookups/appends/preprocessing/training actions must validate that the requested project belongs to the authenticated workspace.
  - [ ] Object keys must be rejected if they escape `workspaces/<clerk_user_id>/projects/<project_id>/`.
- [ ] Frontend: add zero-project onboarding.
  - [ ] If `/projects` returns no projects, show a professional empty state with “Create your first workspace/project”.
  - [ ] Allow entering a client/workspace display name and project name.
  - [ ] If the user's bucket is not provisioned yet, show a clear "storage setup required" message and prevent upload rather than routing to another bucket.
  - [ ] Include a regular-user "request storage setup" affordance/copy so unprovisioned demo users understand what is blocked and why.
  - [ ] Explain that storage is private to the signed-in user/project without exposing Railway bucket internals.
- [ ] Frontend: remove bucket/demo confusion.
  - [ ] Avoid any “battery bucket” copy in app UI unless the selected project is actually a battery project.
  - [ ] Make templates/domain language generic Mirai package language, with fuel-cell-specific details only when applicable.
- [ ] Frontend: preserve existing fuel-cell user experience.
  - [ ] Existing Fraunhofer user should still land on the Fraunhofer project.
  - [ ] Existing project upload should still add a dataset/session to the selected project.
- [ ] Tests and validation.
  - [ ] Add backend tests for new user onboarding upload, fuel-cell user isolation, cross-user forbidden access, and object prefix confinement.
  - [ ] Add/update frontend build validation.
  - [ ] Run targeted backend tests, then the relevant broader suite.
- [ ] Railway/operator cleanup and provisioning.
  - [ ] Remove the unused `mirai-batteries-demo` bucket from this pilot environment, after confirming no project metadata references it.
  - [ ] For each approved demo Clerk user, provision one dedicated Railway bucket or assign an existing dedicated bucket.
  - [ ] Pre-provision both known demo Clerk users once the empty user's Clerk `sub` is identified: fuel-cell user keeps/gets its dedicated bucket; empty user gets a workspace row plus a dedicated empty bucket but no project until first upload.
  - [ ] Store that assignment in `workspaces.storage` and ensure all projects for that user inherit it.
  - [ ] Add an admin-only/protected provisioning path so an authorized Mirai operator can assign a bucket to a Clerk workspace from the app or an API endpoint, without exposing this control to regular users.
- [ ] Deploy and production smoke.
  - [ ] Push to `railway`.
  - [ ] Wait for Railway deployment success.
  - [ ] Use CLI plus browser Network tab to confirm object URIs, Postgres rows, and UI state for both users.

## Verification

Backend/local:

```bash
cd backend
uv run pytest tests/test_api.py tests/test_workspace_storage.py tests/test_runtime_project_schema.py
```

Frontend:

```bash
npm --prefix frontend run build
```

Production CLI checks after deploy:

```sql
SELECT workspace_id, display_name FROM workspaces ORDER BY workspace_id;
SELECT workspace_id, project_id, display_name, storage FROM projects ORDER BY workspace_id, project_id;
SELECT workspace_id, project_id, dataset_id, object_uri FROM datasets ORDER BY created_at DESC LIMIT 20;
SELECT workspace_id, project_id, artifact_kind, object_uri FROM artifact_objects ORDER BY created_at DESC LIMIT 20;
```

Browser checks:

- New Clerk user:
  - `/projects` returns empty initially.
  - UI shows first-project onboarding.
  - Uploading a valid ZIP creates a project under that Clerk user only.
  - Switching back to the fuel-cell user does not show the new user’s project.
- Fuel-cell Clerk user:
  - `/projects` returns only the Fraunhofer fuel-cell project.
  - Uploading a ZIP for existing project stores objects under the fuel-cell user/project prefix.
- Railway/S3:
  - New objects appear only under `workspaces/<clerk_user_id>/projects/<project_id>/...`.
  - No upload writes to another user’s prefix.
  - No project is accidentally routed to `mirai-batteries-demo` unless the project storage metadata explicitly says so.

## Decisions

- Pilot bucket model: one dedicated Railway bucket per Clerk user/client.
- Project model: many project prefixes/folders can live inside that user's bucket.
- New project creation: create the project immediately on upload, then drive validation/preprocessing from that project/session.
- Workspace naming: users may type a workspace/client display name, but backend identity remains the verified Clerk `sub`.
- Battery bucket: remove `mirai-batteries-demo` from the current pilot environment after verifying nothing references it.
- Bucket creation: regular user uploads should not create Railway infrastructure. For 1–3 real demo users, use an operator/admin provisioning step to create/assign one bucket per Clerk user. This is safer, auditable, and enough before moving away from Railway.
- Unprovisioned users should see a friendly storage setup state, and admins should also have a protected provisioning path.
