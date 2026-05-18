# Metadata & Plot Setup Admin UI Plan

## Goal
Add the missing user-facing layer for OEM-generic behavior: during Preprocessing Review, Mirai admins can review inferred project semantics, adjust labels/units/roles and safe plot recipes, then approve the metadata that downstream Design Studio and Model Quality use.

## Scope
MVP, minimal but useful:
- Backend endpoints to get/update/approve inferred domain metadata for an ingestion session.
- Frontend Preprocessing Review panel named `Metadata & Plot Setup`.
- Variable table with editable label, unit, role.
- Template selector with two options: `fuel_cell`, `generic_tabular_doe`.
- Safe/recommended plot recipe selector/editor for one primary plot:
  - recipe kind
  - x variable
  - y variable
  - group variable/filter optional for future but not overbuilt.
- Approval button that writes approved metadata so downstream schema/project registry uses it.

## Non-goals
- No arbitrary unsafe plotting everywhere yet.
- No backend retraining changes.
- No autonomous preprocessing changes.
- No ONNX/inference/recommendation changes.
- No full multi-recipe builder; just primary safe plot recipe for MVP.

## Files
- `backend/app/services/domain_metadata.py`
- `backend/app/services/preprocessing_review.py`
- `backend/app/main.py`
- `backend/app/schemas.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/PreprocessingReviewPage.tsx`
- `backend/tests/test_api.py`

## Steps
1. Add backend service functions to get inferred metadata, update draft metadata, and approve metadata for a session.
2. Add FastAPI routes for metadata get/update/approve.
3. Add request schemas for metadata update/approval.
4. Add frontend API client functions and types.
5. Add Preprocessing Review `Metadata & Plot Setup` panel.
6. Wire editable template/variable table/primary plot recipe fields.
7. Persist edits as draft metadata and approve metadata.
8. Ensure approved metadata is reflected by `get_project_schema` for uploaded project sessions.
9. Validate backend tests and frontend build.

## Acceptance Criteria
- Admin can see Mirai-inferred template and variable metadata in Preprocessing Review.
- Admin can edit labels, units, roles.
- Admin can choose a safe/recommended primary plot recipe by selecting x/y variables.
- Admin can save draft and approve metadata.
- Approved metadata is stored in session status and attached to schema artifacts if available.
- Design Studio `Plot Options` reads the approved selected recipe.
- Existing fuel-cell project continues to work.
- Generic metadata test remains green.
