# Knowledge Intake Target-Contract Loop Plan

## Context

Knowledge Intake should become the step immediately before Data Intake. Its job is to populate a user-provided Mirai target contract/package shape from messy real-world source files, then export a Mirai package ZIP that the user manually uploads into the existing Data Intake flow.

**Non-negotiable boundary:** it is absolutely prohibited to change Data Intake, Preprocessing Review, ML preprocessing, Training, Optimization, or downstream lifecycle behavior for this implementation. The implementation may read/reuse downstream validators and schemas, but product/code changes must be limited to the Knowledge Intake tab/service/API plus additive Knowledge Intake persistence/tests. Existing Data Intake onward code is the contract to satisfy, not a surface to modify.

Current implementation diverges from this product model in a few ways:

- The frontend exposes multiple hardcoded `targetContracts`, including fuel-cell/demo-specific options.
- The backend generic loop uses hardcoded fuel-cell fields in `GENERIC_TABULAR_DOE_FIELDS`.
- Export currently also creates a Data Intake ingestion session automatically.
- The Fraunhofer adapter/demo path is too coupled to the concept of a target option rather than being an optional deterministic tool invoked only when relevant.

Existing downstream Data Intake/preprocessing already supports the desired package goal. The Knowledge Intake implementation should mirror those existing expectations precisely without changing them:

- `backend/app/services/data_intake.py` treats a valid Mirai package as `mirai_manifest.json` + `data_dictionary.csv` + either `model_table.csv` or fixed source tables.
- `backend/app/services/preprocessing_review.py` ultimately validates a generic package with `load_and_validate_contract(...)` and then prepares generic preprocessing artifacts.
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/contract.py` defines the real package contract:
  - supported `template_id`: `generic_tabular_doe`
  - required manifest/dictionary files
  - fixed source-table rules for `experiments.csv`, `conditions.csv`, and `results.csv`
  - input variables must be contiguous `x1..xN`
  - output variables must be contiguous `y1..yN`
  - domain/client names belong in `source_name`, `ui_label`, `description`, and metadata, not in model `variable_id`s
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py` shows what a valid package must enable later:
  - `_prepare_package_root(...)` accepts package ZIPs/direct package folders
  - `_build_joined_table(...)` joins fixed source tables according to manifest joins
  - `build_generic_preprocessing_artifacts(...)` materializes `canonical/model_table.csv`, `schema.json`, `preprocessing.json`, `split_report.json`, and `validation_report.json`
- `backend/app/services/ml_preprocessing.py` then expects the canonical model table/schema from that existing preprocessing flow. Knowledge Intake should not generate ML-preprocessed artifacts directly.

The package forms accepted by downstream code are:

- `mirai_manifest.json`
- `data_dictionary.csv`
- either `model_table.csv` or the fixed source-table set:
  - `experiments.csv`
  - `conditions.csv`
  - `results.csv`

For the Fraunhofer client, `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-cell-01/` is a good first uploaded target contract/package example. It should be treated as an uploaded target shape, not as a hardcoded product option.

## Approach

Treat the existing Data Intake → preprocessing → ML preprocessing flow as a black-box acceptance target. Knowledge Intake should produce an exported ZIP that would pass the same package checks if manually uploaded to Data Intake, but it must not call or alter downstream lifecycle code.

Replace the hardcoded target selector with a target-contract upload workflow:

1. User creates a Knowledge Intake session.
2. User uploads a **target Mirai contract package** as the goal. For MVP this may be a full package example like `fraunhofer2miraicontract-cell-01/`; later it can be manifest/dictionary-only with no real data.
3. Backend validates and stores a target contract snapshot using the existing generic contract validation rules.
4. User uploads messy source files.
5. The LLM/harness inventories source files and proposes how to populate the uploaded target contract.
6. The loop iterates until enough mapping/transform information exists or a blocker/question is reached.
7. Approved ephemeral transform execution materializes a candidate Mirai package matching the uploaded target shape.
8. Backend validates the candidate package by invoking/reusing the same generic contract/preprocessing validator behavior that Data Intake relies on, preferably in a temporary validation workspace so Knowledge Intake can prove downstream compatibility without creating a real Data Intake session.
9. User downloads the package ZIP.
10. User manually uploads the ZIP into Data Intake.

For MVP, the exported package should preserve the target package style:

- If the uploaded target declares `experiments.csv`, `conditions.csv`, and `results.csv`, Knowledge Intake should output those files because the downstream contract/preprocessing path accepts and joins them.
- If the uploaded target declares `model_table.csv`, Knowledge Intake can output that simpler canonical package.

The LLM should not be asked to satisfy hardcoded fuel-cell fields. It should be asked to satisfy the uploaded target contract: required files, tables, columns, roles, `variable_id`s, units, bounds, directions, joins, and split hints. For the Fraunhofer example, those fields come from the uploaded `fraunhofer2miraicontract-cell-01` manifest/dictionary; for any other client, the fields come from that client's uploaded target contract.

## Downstream contract examples to implement against

Implementation should use the existing downstream flow as examples/specification:

- **Target upload parsing:** use the same package-root assumptions as `_prepare_package_root(...)`: direct folder/package files or one ZIP with package files at root or one top-level package folder.
- **Contract extraction:** use `load_and_validate_contract(...)` to parse target manifest/dictionary into normalized columns. The Knowledge Intake mapping board should be generated from these normalized columns.
- **Schema preview:** use `schema_from_contract(...)` to show the target inputs/outputs/metadata as Data Intake/preprocessing would see them later.
- **Fixed source-table output:** if the target manifest declares fixed source tables, generated package files must include valid `experiments.csv`, `conditions.csv`, and `results.csv` with required keys and joins exactly as downstream preprocessing expects.
- **Model-table output:** if the target manifest declares `model_table.csv`, generated package files must include a valid model table with all required input/output/source columns.
- **Validation gate:** before Knowledge Intake approval/export, run candidate package validation equivalent to `load_and_validate_contract(...)` plus enough generic preprocessing artifact build to catch source-column, join, dtype, bounds, split, and row-validity problems.
- **No lifecycle promotion:** do not create ingestion sessions, preprocessing reviews, ML preprocessing outputs, training requests, or optimization artifacts from Knowledge Intake.

## Files to modify

Allowed backend changes:

- `backend/app/services/document_intake.py`
- `backend/app/main.py`, only for Knowledge Intake routes/request models
- `backend/db/migrations/006_project_document_intake.sql` or a new additive Knowledge Intake migration
- `backend/tests/test_document_intake_conversational_mapping.py`
- new tests for target contract upload and export validation

Allowed frontend changes:

- `frontend/src/components/KnowledgeIntakePage.tsx`
- `frontend/src/lib/api.ts`, only for Knowledge Intake API functions/types
- `frontend/src/types/doe.ts`, only if Knowledge Intake-specific types need to be exposed

Explicitly out of scope / do not modify:

- `backend/app/services/data_intake.py`
- `backend/app/services/preprocessing_review.py`
- `backend/app/services/ml_preprocessing.py`
- `backend/app/services/training_requests.py`
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/contract.py`
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py`
- training, optimization, recommendation, and diagnostic services

Those downstream files may be read/imported/reused as stable contracts, but must not be changed for this feature.

## Reuse

Existing contract validation and preprocessing code to reuse without modifying:

- `backend/ml_lifecycle/ingesting/generic_tabular_doe/contract.py`
  - `load_and_validate_contract(...)`
  - `schema_from_contract(...)`
  - fixed source table rules
  - `x1..xN` / `y1..yN` validation rules
  - manifest column normalization from `data_dictionary.csv`
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py`
  - use as behavioral spec for package-root handling, table joining, coercion, required-value validation, split assignment, and artifact expectations
  - call `build_generic_preprocessing_artifacts(...)` only in temporary Knowledge Intake validation workspaces if needed; do not write to real lifecycle session workspaces
- `backend/app/services/data_intake.py`
  - package upload expectations and workspace artifact patterns as a black-box contract; do not change it
- `backend/app/services/preprocessing_review.py`
  - existing validation/review gate behavior as a black-box contract; do not change it
- `backend/app/services/ml_preprocessing.py`
  - downstream expectation that preprocessing has produced canonical `model_table.csv` and schema; do not change it
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-cell-01/`
  - first user-uploaded target package fixture/example, not a hardcoded UI option
- Existing Knowledge Intake source inventory code in `backend/app/services/document_intake.py`
- Existing Anthropic provider/config pattern in `backend/app/services/document_intake.py`

## Skills and agent/subagent mapping

Planning-mode tool restrictions prevented executing subagents directly here, but I inspected the repo-local and user skill inventory. Meaningful skills/agents to use during implementation/review:

- **api-and-interface-design**: design the target-contract upload API, session state shape, and route boundaries while keeping downstream API contracts untouched.
- **frontend-ui-engineering**: update the Knowledge Intake tab to show target upload, parsed target requirements, loop trace, mapping board, and download-only export.
- **incremental-implementation**: stage changes safely: target upload/parsing first, mapping-board derivation second, export behavior third, ephemeral execution last.
- **test-driven-development**: add failing tests for uploaded target contracts, package style preservation, no downstream handoff, and no hardcoded field usage before/while implementing.
- **security-and-hardening**: review ephemeral generated transform execution, temp workspace isolation, file allowlists, timeouts, and artifact persistence boundaries.
- **code-review-and-quality**: review final diff specifically for the prohibited boundary: no Data Intake/preprocessing/ML preprocessing/training changes.
- **repo-postgres-migrations**: if persistence schema changes are needed, keep them additive and scoped to Knowledge Intake tables.
- **scout subagent**: useful as a read-only reviewer to re-check downstream lifecycle assumptions and ensure the implementation still matches Data Intake/preprocessing contracts.
- **reviewer subagent**: useful after implementation to audit boundary compliance, tests, and UX/API consistency.

## Steps

- [ ] Add target-contract upload API to Knowledge Intake sessions.
  - Accept ZIP or direct files for `mirai_manifest.json`, `data_dictionary.csv`, and optional placeholder/package tables.
  - Store target files separately from messy source files, e.g. a target-contract object prefix distinct from source uploads.
  - Validate/parse using the existing `load_and_validate_contract(...)` behavior or an equivalent target-only parser if placeholder-table support requires missing-data tolerance later.
  - Persist target contract snapshot, schema summary from `schema_from_contract(...)`, required output files, tables, joins, split hints, and normalized columns.

- [ ] Replace hardcoded target contract choices in the frontend.
  - Remove fuel-cell/demo-specific target dropdown options from product UI.
  - Show one target area: **Upload target Mirai contract**.
  - Display parsed target requirements: expected files, inputs, outputs, metadata columns, required fields, joins, and package style.

- [ ] Remove `GENERIC_TABULAR_DOE_FIELDS` from the generic mapping path.
  - Derive mapping board rows from the uploaded contract snapshot.
  - Use `source_name`, `variable_id`, `ui_label`, `role`, `dtype`, `unit`, `required`, `direction`, bounds, `source_table`, joins, and split hints from the uploaded manifest/dictionary.
  - Display both model variable IDs (`x1`, `y1`) and human/client labels (`ui_label`, `source_name`) so the user sees the generic model contract and the domain language together.

- [ ] Update the loop prompt and state model.
  - The goal is the uploaded target contract, not a named target ID.
  - Loop state should track: target snapshot, source inventory, mapping decisions, transform plan, generated package files, validation status, blockers, questions, and conversation.
  - Add a loop policy: run until package validates, user input is needed, budget/time limit is reached, or execution fails safely.

- [ ] Add ephemeral transform execution MVP.
  - Allow generated transformation code only in a controlled ephemeral workspace.
  - Apply strict timeouts, file allowlists, input/output directory constraints, and no persistent code writes.
  - Do not persist generated code as product source.
  - Persist only auditable artifacts: prompt/run summary, visible reasoning trace, generated package files, validation report, and high-level transform notes.
  - Validate generated output with downstream-compatible generic contract/preprocessing validation before enabling approval/export.

- [ ] Keep the Fraunhofer conversion path as an optional tool, not a product target.
  - It may be selected/invoked by the harness when the uploaded target/source shapes match and the user approves.
  - No fuel-cell fields should be hardcoded in the generic target-contract loop UI.

- [ ] Change export behavior.
  - Export/download the validated Mirai package ZIP only.
  - Remove automatic `createIngestionSession(...)` handoff from Knowledge Intake MVP.
  - UI copy should instruct the user to manually upload the ZIP in Data Intake.
  - Do not call Data Intake session creation from Knowledge Intake.

- [ ] Add model configuration.
  - Keep existing Anthropic model env override.
  - Add support for the requested latest Anthropic model name once confirmed.
  - Consider exposing configured model in the agent status panel.

- [ ] Add tests.
  - Upload `fraunhofer2miraicontract-cell-01` as target contract and verify fields are derived from the uploaded contract.
  - Verify no hardcoded fuel-cell fields are used when a different target contract is uploaded.
  - Verify fixed source-table targets require/output `experiments.csv`, `conditions.csv`, and `results.csv`.
  - Verify fixed source-table candidate packages pass `load_and_validate_contract(...)` and temporary generic preprocessing artifact creation.
  - Verify `model_table.csv` targets can output a model-table package.
  - Verify export is blocked until generated package validates.
  - Verify export no longer creates a Data Intake ingestion session.
  - Verify no files from Data Intake onward are modified by the implementation diff.

## Verification

- Run backend tests for document intake and generic contract pipeline.
- Run Python compile checks on modified backend files.
- Run frontend build.
- Run a boundary check before commit: `git diff --name-only` must not include Data Intake, Preprocessing Review, ML preprocessing, Training, Optimization, or generic contract/preprocessing implementation files listed as out of scope.
- Run a downstream compatibility check by validating the Knowledge Intake exported ZIP through the existing generic contract/preprocessing functions in a temporary directory, not by creating a real Data Intake session.
- Manual MVP flow:
  1. Create Knowledge Intake session.
  2. Upload `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-cell-01/` as target contract/package.
  3. Upload Fraunhofer raw/messy source files.
  4. Run loop until candidate package validates.
  5. Download exported Mirai ZIP.
  6. Manually upload ZIP in Data Intake.
  7. Confirm Data Intake/preprocessing accepts it and proceeds through existing review gates without any downstream code changes.

## Decisions confirmed

- Anthropic **Fable 5** should be added to the model options/configuration, using Anthropic's documented model/API identifier from <https://www.anthropic.com/news/redeploying-fable-5> during implementation rather than guessing it in the plan.
- MVP ephemeral transform execution may use an isolated temporary workspace with strict timeouts and file allowlists.
- The UI should not expose hidden chain-of-thought, but should show a Pi-like visible trace: plan, assumptions, mapping rationale, tool actions, validation failures, next questions, and progress.
