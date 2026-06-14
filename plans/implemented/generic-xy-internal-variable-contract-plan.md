# Generic X/Y Internal Variable Contract Plan

## Context

Mirai's current generic tabular intake is source-table-first and variable-count flexible, but the implemented/documented `variable_id` layer still allows semantic/domain names such as `pt_c_ratio`, `operating_voltage`, or `capacity_retention_100_cycles_pct` to become internal model-table and training column names.

The intended robustness contract is stricter:

- source/client names stay in `source_name`.
- human/domain names stay in `ui_label` and related metadata.
- internal model/training names are generic immutable IDs only: `x1..xN` for inputs and `y1..yM` for outputs.
- the number of inputs/outputs remains variable per project/client.
- structural/provenance keys remain fixed generic IDs such as `experiment_id`, `condition_id`, `result_id`, and optional metadata IDs/groups.

This makes the runtime pipeline fully generic while still carrying labels/provenance into preprocessing review, ydata-style reports, MLflow artifacts, UI charts, BO, and project detail views.

## AGENTS.md alignment

Repo instructions to preserve during implementation:

- Use `uv` for backend commands, not `pip`.
- Keep React + Vite frontend workflow intact.
- Do not change Docker workflow or public API routes unless explicitly requested.
- Preserve existing Mirai branding/layout structure when changing UI copy.
- Treat `generic_tabular_doe` as the MVP source-of-truth lifecycle for preprocessing, split semantics, MLflow, model quality, serving, BO, and UI behavior.
- Keep Fraunhofer/PEM behavior as an adapter into the same generic Mirai contract; do not create a separate fuel-cell lifecycle.
- Maintain strict generic/workspace separation through metadata/storage layout, not Python package forks.
- Start implementation with configured agent discovery and a scout/read-only pass where available; do not invent agent names.
- Map available skills to implementation tasks.
- After changes, report exact local validation commands.

## Approach

Update the generic contract semantics so new fixed-source-table packages require input/output `variable_id` values to follow role-specific ordinal IDs:

- inputs: `x1`, `x2`, ..., `xN`
- outputs: `y1`, `y2`, ..., `yM`

`variable_id` remains immutable, but it is no longer a semantic domain identifier. Semantic/domain identifiers should be represented with `ui_label`, `source_name`, `description`, `unit`, and optional metadata aliases.

For transitional compatibility, existing `model_table.csv`-first or legacy semantic-`variable_id` packages should continue to work where practical, but new fixed-source-table packages should enforce the stricter generic X/Y pattern.

## Files to modify

Critical backend files:

- `backend/ml_lifecycle/ingesting/generic_tabular_doe/contract.py`
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py`
- `backend/app/services/domain_metadata.py`
- `backend/app/services/preprocessing_review.py`
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py` if MLflow/schema artifacts need label metadata additions
- `backend/tests/test_generic_contract_pipeline.py`
- `backend/tests/test_api.py` if API fixtures/assertions depend on semantic names

Fixtures/templates/docs:

- `AGENTS.md` — small local clarification so future plans explicitly read repo instructions and include concrete agent/skill mapping before submission.
- `backend/tests/fixtures/fuel_cell_fixed_multitable_package/`
- `backend/tests/fixtures/client_native_variable_package/`
- `frontend/public/templates/data_dictionary_multitable_example.csv`
- `frontend/public/templates/mirai_manifest_multitable_template.json`
- `docs/tutorials/MULTI_TABLE_TO_MODEL_TABLE_MAPPING.md`
- `docs/tutorials/MIRAI_CONTRACT_INTAKE_TO_TRAINING_FLOW.md`
- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`
- `frontend/src/components/DataIntakePage.tsx`

Possible frontend touch points if copy or assumptions need adjustment:

- `frontend/src/lib/api.ts`
- `frontend/src/components/PreprocessingReviewPage.tsx`
- `frontend/src/components/ProjectHeader.tsx`
- Design/BO/chart components should continue using `schema.inputs[].name` / `schema.outputs[].name`, but display `label`/`ui_label`.

## Agent and skill mapping

Configured agent use:

- `scout` — run first as read-only discovery to confirm current contract/preprocessing/schema state and prevent duplicate utility work.
- `worker` or main implementation session — apply the approved plan incrementally after scout confirms assumptions.
- `reviewer` — review the diff for API/schema compatibility, generic-lifecycle consistency, and docs/tests coverage before final validation.

Relevant available skills and where to use them:

- `planning-and-task-breakdown` — keep the implementation split into contract, preprocessing, fixtures/tests, docs/templates, and frontend copy phases.
- `spec-driven-development` — convert the clarified X/Y contract into explicit validation rules and tests before broad refactors.
- `api-and-interface-design` — preserve public API route shapes while clarifying schema fields (`name`/`variable_id` vs `label`/`ui_label`).
- `test-driven-development` — add failing regression tests for contiguous `xN`/`yN`, rejection of semantic IDs in new fixed packages, and label/provenance preservation.
- `incremental-implementation` — update backend contract/preprocessing first, then fixtures/docs/templates, then frontend copy/type adjustments.
- `code-review-and-quality` — verify no domain-specific fuel-cell logic leaks into generic runtime and no metadata variables appear as Design Studio model controls.
- `documentation-and-adrs` — update tutorials and contract reference so the three naming layers are unambiguous.
- `frontend-ui-engineering` and project `scientific-ui-clarity` — adjust review/intake UI copy without changing current branding/layout.
- project `surrogate-model-debugging` — check that training/MLflow/model-quality artifacts still use generic feature/output orders and carry label metadata.
- `security-and-hardening` — avoid logging secrets or exposing workspace/client data; keep Clerk/workspace scoping unchanged.
- `git-workflow-and-versioning` — do not stage/commit/push without explicit approval; run `git diff --cached --check` before any approved commit.

## Reuse

Existing reusable behavior found:

- `contract.py` already normalizes `source_name`, `variable_id`, `ui_label`, `role`, provenance, and schema metadata.
- `contract.py::schema_from_contract` already emits `name`, `variable_id`, `label`, `ui_label`, source provenance, and `metadata.all_variables`.
- `preprocessing.py` already validates `source_name` against fixed source tables and renames selected source columns to `variable_id` in generated `model_table.csv`.
- Existing frontend schema-driven Design Studio/BO code already uses schema variable names generically and labels for display in several places.
- Existing preprocessing review label override flow already supports editing display labels while preserving immutable source/internal identifiers.

## Steps

- [ ] Keep the local `AGENTS.md` clarification that future plans must read repo instructions, inspect/list skills, and include a concrete Agent and skill mapping section before plan submission.
- [ ] Run configured agent discovery and a read-only `scout` pass before editing to confirm current code state, reusable utilities, and no newer conflicting changes.
- [ ] Clarify contract semantics in docs before code changes: `variable_id` for model inputs/outputs is an ordinal internal ID (`xN`/`yN`), not a domain name. New fixed-source-table packages must use contiguous input/output IDs: `x1..xN` and `y1..yM` with no gaps.
- [ ] Add backend validation helpers in `contract.py` for new fixed-source-table packages:
  - [ ] input role must use `x1..xN`.
  - [ ] output role must use `y1..yM`.
  - [ ] IDs must be unique and contiguous per model role: `x1..xN` for all inputs and `y1..yM` for all outputs.
  - [ ] structural keys such as `experiment_id`, `condition_id`, `result_id` remain preserved for `id` roles.
  - [ ] metadata/group IDs may remain stable generic/provenance names, but must not collide with reserved `xN`/`yN` model IDs. Metadata/id/group variables are not required to be abstract ordinal IDs because they are not model controls.
- [ ] Decide and implement compatibility rules:
  - [ ] Legacy/root `model_table.csv` packages may keep semantic columns for now.
  - [ ] New fixed-source-table packages with `experiments.csv`/`conditions.csv`/`results.csv` should enforce contiguous X/Y internal IDs.
  - [ ] Error messages should clearly say to put domain names in `ui_label`, not `variable_id`.
- [ ] Update preprocessing so generated `model_table.csv` columns are `x1..xN`, `y1..yM`, plus approved id/group/metadata variables.
- [ ] Ensure schema generation exposes:
  - [ ] `name` / `variable_id`: `x1`, `x2`, `y1`, etc.
  - [ ] `label` / `ui_label`: user/domain label, e.g. `Pt/C ratio`.
  - [ ] `source_name`: exact uploaded source column, e.g. `Pt/C ratio (%)`.
  - [ ] source table/path, role, unit, dtype, direction, description.
- [ ] Ensure training/MLflow artifacts preserve human-readable mappings:
  - [ ] active feature/output order uses `xN`/`yN`.
  - [ ] schema/metadata artifacts include an explicit variable map for reports and UI.
  - [ ] prediction/recommendation APIs still key payloads by internal names while UI displays labels.
- [ ] Update review approval validation so users may edit labels but cannot mutate `variable_id`, `source_name`, or `source_table`.
- [ ] Update frontend copy/templates to teach:
  - [ ] `source_name`: exact source CSV column.
  - [ ] `variable_id`: immutable generic model ID (`x1`, `x2`, `y1`).
  - [ ] `ui_label`: desired human label.
- [ ] Update all fixed multi-table fixtures to use `xN`/`yN` IDs instead of semantic IDs.
- [ ] Add/adjust tests:
  - [ ] fixed package with `Pt/C ratio (%) -> x1 -> Pt/C ratio` materializes `model_table.csv` with `x1` not `pt_c_ratio`.
  - [ ] two projects with different input/output counts both train through the same generic path.
  - [ ] semantic `variable_id` in a new fixed-source-table package is rejected with a clear error.
  - [ ] metadata/id/group variables are retained for traceability but excluded from training unless role is input/output.
  - [ ] UI label overrides do not change `xN`/`yN` IDs.
- [ ] Update docs/tutorials/reference material to remove examples that imply semantic model columns are preferred.
- [ ] Run reviewer/code-quality pass before final validation, focused on generic-lifecycle consistency and public API compatibility.
- [ ] Run final validation.

## Verification

Backend:

```bash
cd backend && uv run pytest tests/test_generic_contract_pipeline.py tests/test_api.py -q
cd backend && uv run pytest -q
```

Frontend:

```bash
cd frontend && npm run build
```

Manual/package checks:

- Confirm `AGENTS.md` clearly instructs future planning sessions to read repo instructions, inspect available skills, and include concrete agent/skill mapping in plans.
- Upload or run fixture preprocessing for a fixed package whose source column is `Pt/C ratio (%)` and whose dictionary maps it to `x1` with `ui_label=Pt/C ratio`.
- Confirm generated `canonical/model_table.csv` uses `x1`/`y1` columns.
- Confirm preprocessing review and project detail show labels/source provenance.
- Confirm Design Studio/BO controls remain schema-driven and do not expose metadata variables as tunable model variables.
- Confirm MLflow/schema artifacts include both internal IDs and human labels/source names.
