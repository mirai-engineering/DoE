# Variable-column Mirai contract mapping plan

## Context

Mirai now has a fixed source-table intake shape (`experiments.csv`, `conditions.csv`, `results.csv`) that materializes `model_table.csv`. The next design layer is to make that fixed table shape work for every client even when each client has a different number of inputs, outputs, and metadata columns, and when clients use their own native column names.

The intended model/runtime boundary is:

- The fixed source tables provide deterministic row identity and joins.
- `data_dictionary.csv` is the source of truth for variable roles and display semantics.
- Training only needs arrays of selected X/Y variables.
- The UI shows user/admin-defined names, labels, units, grouping fields, and metadata, not hardcoded domain names.

## Approach

Extend the existing generic contract instead of creating a new ingestion path.

Keep the fixed structural contract:

- `experiments.csv`
- `conditions.csv`
- `results.csv`
- required join keys: `experiment_id`, `condition_id`, `result_id`

Make all domain/scientific columns variable and defined by `data_dictionary.csv` / manifest `columns` metadata.

Introduce explicit variable mapping semantics:

- `source_name`: exact column name in the uploaded CSV table.
- `variable_id`: stable internal Mirai variable identifier used in generated `model_table.csv`, schemas, training artifacts, predictions, and APIs.
- `role`: `input`, `output`, `metadata`, `group`, `id`, `ignore`, etc.
- `ui_label`: user-facing display label.
- `unit`, `dtype`, bounds, required flag, direction, description, plot role, split hints.

Default behavior should be strict for new fixed-source-table packages:

- `variable_id` is required for all declared package columns.
- `source_name` is required for all non-generated uploaded source columns.
- Transitional compatibility may remain only for older `model_table.csv`-first fixtures/packages where `name` already acts as the internal variable id.
- Existing compatibility should not weaken the new fixed multi-table contract.

`model_table.csv` should be generated with internal `variable_id` column names. Training and APIs continue to operate on those internal ids. UI schema surfaces `label`/`ui_label`, units, descriptions, and metadata so the app can display client-preferred names without the model caring about them.

## Files to modify

- `backend/ml_lifecycle/ingesting/generic_tabular_doe/contract.py`
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py`
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py` only if assumptions about column names need minor tightening
- `backend/app/services/preprocessing_review.py`
- `backend/app/services/training_requests.py` only if schema/report payloads need richer variable metadata
- `backend/tests/test_generic_contract_pipeline.py`
- `backend/tests/test_api.py`
- `backend/tests/fixtures/fuel_cell_fixed_multitable_package/`
- `frontend/src/lib/api.ts`
- `frontend/src/components/DataIntakePage.tsx`
- `frontend/src/components/PreprocessingReviewPage.tsx`
- `frontend/public/templates/data_dictionary_multitable_example.csv`
- `frontend/public/templates/mirai_manifest_multitable_template.json`
- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`
- `docs/tutorials/MULTI_TABLE_TO_MODEL_TABLE_MAPPING.md`
- `docs/tutorials/MIRAI_CONTRACT_INTAKE_TO_TRAINING_FLOW.md`

## Reuse

Existing reusable pieces already found:

- `contract.py` already normalizes dictionary/manifest columns, roles, dtype, units, bounds, `ui_label`, descriptions, `split_hint`, `plot_role`, and creates schema `inputs`, `outputs`, and metadata variables.
- `schema_from_contract(...)` already separates `input`, `output`, and metadata-like variables.
- `preprocessing.py` already joins fixed source tables into a single frame and writes canonical artifacts.
- Frontend schema types in `frontend/src/lib/api.ts` already expose `label`, `unit`, inputs, outputs, and metadata variables.
- UI components already use schema `label` for variable display in multiple places.

## Agents and skills mapping

Before implementation, run an available scout/read-only agent or chain if the agent runner is available, per `AGENTS.md`, to confirm the current code state and avoid duplicating existing utilities. Do not invent agent names; list configured agents/chains first and select only available ones.

Recommended skills by task area:

- `planning-and-task-breakdown`: keep the fixed-table/variable-column scope bounded and sequence backend, tests, frontend, and docs work.
- `spec-driven-development`: translate the variable mapping semantics into contract requirements, validation rules, and acceptance criteria.
- `api-and-interface-design`: keep schema/API payloads stable while adding `source_name`, `variable_id`, label overrides, and metadata visibility.
- `test-driven-development`: add regression fixtures before or alongside implementation for source-name mapping, variable counts, metadata exclusion from training, and multi-output training.
- `surrogate-model-debugging`: verify generated `model_table.csv`, schema inputs/outputs, training matrices, prediction payloads, and BO behavior remain generic and variable-count safe.
- `frontend-ui-engineering`: update preprocessing review and project detail panels without surfacing metadata in normal design/training controls.
- `scientific-ui-clarity`: ensure user-facing labels, units, roles, and provenance are understandable to engineers and admins.
- `documentation-and-adrs`: update contract docs, tutorials, and templates with the three naming layers.
- `code-review-and-quality`: review strict validation, backward compatibility boundaries, and absence of domain-specific shortcuts.
- `security-and-hardening`: ensure label editing does not allow schema spoofing, changing immutable `variable_id`, or trusting client-side role changes after approval.
- `incremental-implementation`: land changes in small slices: contract normalization, preprocessing materialization, tests, UI metadata, docs.

Suggested implementation agent workflow:

1. Scout/read-only agent: inspect current contract, preprocessing, schema, frontend display, and tests.
2. Backend/spec implementation agent: implement strict mapping validation and model table materialization.
3. Frontend/UI implementation agent: expose review/detail display and label editing while keeping design controls clean.
4. Test/review agent: verify variable-count behavior, metadata handling, API compatibility, and docs/templates.

## Steps

- [ ] Run an available scout/read-only agent or chain, if configured, to confirm current code state and reusable utilities before editing.
- [ ] Add documented dictionary columns: `source_name`, `variable_id`, `ui_label`, `role`, `dtype`, `unit`, `required`, `allowed_min`, `allowed_max`, `direction`, `description`, `join_key`, `split_hint`, `plot_role`.
- [ ] Require `variable_id` for all new fixed-source-table package columns and fail validation when it is missing.
- [ ] Require `source_name` for uploaded source-table columns and fail validation when it is missing.
- [ ] Update contract normalization so each declared variable has both a source column identity and an internal Mirai variable id.
- [ ] Validate `variable_id` values are unique across generated model columns, stable, machine-safe, and do not collide after joins.
- [ ] Validate `source_name` exists in its declared source table before preprocessing.
- [ ] Preserve fixed structural keys as internal ids: `experiment_id`, `condition_id`, `result_id`.
- [ ] Materialize `model_table.csv` by selecting `source_name` columns from joined source tables and renaming them to `variable_id`.
- [ ] Include metadata/group/id variables in `model_table.csv` for traceability but exclude them from training unless role is `input` or `output`.
- [ ] Ensure schema generation uses `variable_id` as `name` and `ui_label` as `label`.
- [ ] Include original `source_table`, `source_name`, and `role` in schema metadata so UI/admin review can explain where every variable came from.
- [ ] Update frontend API types to carry optional `source_table`, `source_name`, `description`, `role`, and metadata variable details.
- [ ] Support app-side `ui_label` editing/overrides during review, preserving `variable_id` as the immutable internal/model id.
- [ ] Persist approved UI label overrides with the project/schema metadata so downstream UI can display curated names without changing training artifacts.
- [ ] Update the intake/preprocessing review UI copy so users understand that client-native column names are mapped through the contract and displayed by `ui_label`.
- [ ] Show metadata variables only in preprocessing review and project detail panels, not in normal model input/output design controls.
- [ ] Update public templates to show a client-native example, e.g. source column `Pt/C ratio (%)` mapped to internal `pt_c_ratio` with UI label `Pt/C ratio`.
- [ ] Update docs/tutorials to explain the three naming layers: source column name, internal Mirai variable id, and UI display label.
- [ ] Add regression fixture where source column names contain spaces/symbols/client-specific wording and map into clean internal ids.
- [ ] Add regression fixture with a different number of inputs/outputs from the Fraunhofer example to prove the model path is variable-count.
- [ ] Add tests proving metadata columns are carried through reports/schema but not used as model features unless marked `input`.
- [ ] Add tests proving multiple outputs still train/predict using the contract-defined outputs only.
- [ ] Keep transitional compatibility for current `name`-only contracts.

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

Manual end-to-end check:

1. Create a ZIP with `mirai_manifest.json`, `data_dictionary.csv`, `experiments.csv`, `conditions.csv`, and `results.csv`.
2. Use source columns with client-native names, including spaces or units in the names.
3. Map those source columns to clean `variable_id` values and friendly `ui_label` values.
4. Upload through the app.
5. Confirm preprocessing generates `model_table.csv` with internal variable ids.
6. Confirm preprocessing review shows friendly UI labels and source-column provenance.
7. Approve preprocessing and trigger training.
8. Confirm training uses only role=`input` and role=`output` variables.
9. Confirm prediction/design UI displays approved labels for input/output variables.
10. Confirm metadata variables are visible in preprocessing review and project detail panels only.

## Decisions

- `variable_id` is required for all new fixed-source-table packages.
- The app may allow admins/users to edit `ui_label` during review; label edits must not change immutable internal `variable_id` values.
- Metadata should appear only in preprocessing review and project detail panels, not in normal design/training controls.
