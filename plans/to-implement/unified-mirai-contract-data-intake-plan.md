# Unified Mirai Contract Data Intake Plan

## Overview

Unify Mirai data intake so every upload follows one precise contract-driven lifecycle: inventory → Mirai contract validation → canonical tabular model table → preprocessing artifacts → admin approval → generic training → Postgres/S3/MLflow runtime activation. The Fraunhofer fuel-cell demo should no longer be a separate user-facing or service-level ingestion path. It should be reshaped into the same generic Mirai package structure that batteries, fuel cells, materials, process engineering, and other tabular engineering projects will use.

This plan intentionally allows modifying the fuel-cell demo CSV/manifest shape. The goal is not to preserve historical fuel-cell special cases or introduce PEM-specific processors. The goal is to strictly define one Mirai intake structure from day one: a concise package that ideally provides one canonical ML-ready table with X/Y columns for fitting, plus explicit metadata/overview tables when needed for traceability.

## Discovery Summary

### Data folder inspected

Actual path is:

```text
data/Cathode Catalyst Degradation
```

The user mentioned `Cathode Cathalyst Degradation`; the repo folder is spelled `Catalyst`.

Observed structure:

- ~252 files, ~930 MB total.
- 42 `Cell_NN.zip` files under `01-Data/`.
- 1 workbook: `02-Testing_overview/data_overview.xlsx`.
- 199 visible CSV files, mostly from an extracted `Cell_01` tree and evaluation scripts.
- Each `Cell_NN.zip` contains ~70-200 CSV files.
- Raw CSVs include tab-delimited electrochemical traces such as:
  - `EIS_data_raw.csv`: `f.C[Hz]`, `Z.Re.C[mOhm*cm2]`, `Z.Im.C[mOhm*cm2]`
  - `IV_data.csv`, `IV_data_IR_corr.csv`: voltage/current curve data
  - `ECSA_mean.csv`, `C_DL_mean.csv`, `HFR.csv`, `R_ion.csv`
  - limiting-current and LSV summaries
- The root currently includes generic placeholder files:
  - `mirai_manifest_template.json`
  - `data_dictionary_template.csv`
  These are not a real Mirai contract for the fuel-cell demo because they still describe `example_generic_surrogate` and `temperature_c` / `performance_metric` columns instead of the actual ML-ready X/Y table and supporting metadata.

### Current code state

The codebase already has the pieces needed for the desired architecture, but they are not enforced consistently.

Reusable generic path:

- `backend/ml_lifecycle/ingesting/generic_tabular_doe/contract.py`
  - Validates `mirai_manifest*.json` + `data_dictionary*.csv`.
  - Enforces roles, dtypes, units, output directions, joins, input/output presence.
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py`
  - Loads declared tables.
  - Builds `canonical/model_table.csv`, `rejected_rows.csv`, schema, preprocessing, split, validation/profile artifacts.
  - Already has most of the generic table validation and canonicalization behavior we want to keep.
- `backend/ml_lifecycle/ingesting/extractors/pem_cell_zip_bundle.py`
  - Existing historical helper that converts the current Fraunhofer workbook/zip shape into canonical PEM tables.
  - This should be treated as migration/reference code only, not as the future Mirai intake contract. The plan should adapt the fuel-cell files into the generic structure instead of adding a permanent PEM extractor concept.
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py`
  - Trains generic candidates and logs MLflow runs/model versions.

Duplicated / legacy path to remove or demote:

- `backend/app/services/preprocessing_review.py`
  - Still imports both generic and fuel-cell-specific preprocessors.
  - `queue_fuel_cell_preprocessing(...)` branches on `ingestion_path` and can fall back to a legacy fuel-cell-only path.
  - `start_fuel_cell_preprocessing(...)` still performs direct workbook/zip extraction, `build_all_cells(...)`, and `build_preprocessing_artifacts(...)` outside the generic path when a generic contract is absent.
  - `validate_fuel_cell_package(...)` validates raw PEM files independent of the Mirai contract.
- `backend/app/main.py`
  - API names still say `fuel-cell-package/validation` and `data_intake_start_fuel_cell_preprocessing`, even though generic preprocessing is now the intended behavior.
- `frontend/src/components/DataIntakePage.tsx`
  - User still chooses between `Generic Mirai Contract` and `Fuell Cell DoE Demo`.
  - This contradicts the desired product principle: one way to upload/process data.
- `frontend/src/lib/api.ts`
  - Types still include `ingestion_path?: 'generic_tabular_doe' | 'fuel_cell_doe_demo'` and helper calls for fuel-cell validation.
- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`
  - Still documents two user-facing paths.
- `backend/ml_lifecycle/README.md`
  - Still labels `Fuell Cell DoE Demo` as a distinct path.
- `backend/tests/test_api.py`
  - Contains tests around `/fuel-cell-package/validation`.

Railway data visibility concern:

- Railway S3 can contain CSV/artifact files while the UI still shows no data if Postgres/control-plane rows or ingestion-session/artifact pointers are missing, stale, or point to object keys that do not exist.
- Current runtime seed points Fraunhofer to logical object keys under:
  - `workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/intake/model_table.csv`
  - `workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/training_artifacts/latest/...`
- The local mirror currently has only:
  - `backend/.object-storage-local/workspaces/fraunhofer/workspace.json`
- Therefore bucket object presence alone is insufficient; UI visibility depends on the workspace-scoped project list, schema/artifact status endpoints, training/model pointers, and object resolution.

## Strict Mirai Package Structure

The MVP intake contract should be intentionally small and precise. A valid package should be either an uploaded folder or a ZIP containing the same folder structure:

```text
mirai_package/
  mirai_manifest.json        # project, tables, joins, split policy, expected artifacts
  data_dictionary.csv        # every column's role, dtype, unit, bounds, direction
  model_table.csv            # preferred ML-ready table: one row per training example
  metadata/                  # optional, declared only when needed
    runs.csv                 # optional overview/run metadata
    samples.csv              # optional sample/cell/batch metadata
  raw_reference/             # optional audit-only files; not used for fitting unless converted into model_table.csv before upload
```

Core rules:

- `model_table.csv` is the fitting surface. It contains selected X columns, Y columns, group/split columns, and traceability IDs.
- Optional metadata tables may be joined into `model_table.csv` only through manifest-declared keys and simple deterministic relationships.
- ZIP means “container for the same package”, not “special processing mode”. The backend may safely extract/inventory ZIP contents, but then validates the same required files.
- Arbitrary folder traversal, domain-specific file naming conventions, and automatic semantic inference are out of scope for MVP runtime intake.
- If a customer provides a workbook plus many run folders/CSVs, Mirai or the customer must prepare the package into this structure before preprocessing/training.

## Architecture Decisions

1. **Single user-facing intake path**
   - The UI should present one upload model: `Mirai Experiment Package`.
   - Users should not choose `fuel_cell_doe_demo` versus `generic_tabular_doe`.

2. **One lifecycle contract: `generic_tabular_doe`**
   - Every project, including Fraunhofer fuel-cell and future battery projects, validates through the same contract parser and generic preprocessing/training activation flow.
   - Domain-specific information is data in the manifest/data dictionary/metadata tables, not a separate lifecycle or code path.

3. **One canonical ML table is the target shape**
   - The preferred package contains one ML-ready `model_table.csv` with explicit X/Y columns for fitting.
   - Supporting tables are allowed only when they are strictly declared and joinable into `model_table.csv` with simple, deterministic joins.
   - The manifest must make all identifiers, joins, roles, units, bounds, output directions, grouping/split columns, and ignored columns explicit.

4. **ZIP is packaging only, not a domain-specific processor**
   - Mirai may accept `.zip` uploads as a transport/container format.
   - ZIP handling should be generic: safely extract or inventory allowed CSV/XLSX files according to the same Mirai package structure.
   - Do not assume `Cell_NN.zip`, PEM, battery, or any other domain-specific archive naming convention in the core intake path.

5. **Engineering overview + file/folder references are allowed, but constrained**
   - Many engineering teams will naturally provide one overview/metadata sheet plus linked run folders or CSV files.
   - Mirai should support this only through a concise declared structure: overview table, run/file reference table, measurement tables, and a final canonical `model_table.csv` produced by explicit joins/aggregation rules.
   - The MVP should avoid a general-purpose ETL engine; if a package cannot be reduced deterministically to the canonical table, it is blocked for admin preparation.

6. **Postgres remains runtime source of truth**
   - S3 stores heavy objects.
   - Postgres stores workspace/project/dataset/schema/training/model/artifact pointers.
   - UI must be driven by authorized workspace-scoped Postgres state, not by listing buckets directly.

7. **No duplicate training path**
   - Use `train_generic_project(...)` for all contract-valid projects after generic preprocessing.
   - Keep fuel-cell-specific training code only as historical reference until generic parity is proven, then remove/deprecate it from runtime.

8. **Scientific traceability is mandatory**
   - The plan must preserve cell IDs, split policy, units, output directions, source provenance, and raw-reference inventory.
   - Do not silently map ambiguous columns.

## Skill Mapping

- `planning-and-task-breakdown`: this document and phased implementation order.
- `api-and-interface-design`: stabilize the single intake API surface and response semantics.
- `incremental-implementation`: implement in small slices, keeping backend tests and frontend build green after each phase.
- `surrogate-model-debugging`: verify schema/order/units/preprocessing parity before trusting retraining outputs.
- `scientific-ui-clarity`: update data-intake UI language so scientists understand the one required contract, approvals, canonical model table, and data availability.
- `security-and-hardening`: preserve verified `workspace_id` authorization and never trust workspace/project IDs from UI alone.
- `use-railway`: verify Railway Postgres/S3/MLflow state and object pointers without exposing secrets.
- `code-review-and-quality`: review removal of duplicate paths before merge.

## Phase 1: Contract Definition and Demo Package Shape

### Task 1.1: Define the canonical Mirai package structure

**Description:** Strictly define the one generic Mirai package structure that all engineering tabular projects must follow. The fuel-cell demo will be reshaped into this structure instead of adding a domain-specific processor. The target shape should be concise: a required `model_table.csv` with ML-ready X/Y columns, plus optional explicitly declared metadata/overview tables only when they improve traceability.

**Acceptance criteria:**

- [ ] The contract requires `mirai_manifest.json`, `data_dictionary.csv`, and `model_table.csv` as the preferred MVP package shape.
- [ ] `model_table.csv` has one row per ML training example and contains all selected input/output columns needed for fitting.
- [ ] Optional overview/metadata tables are declared with deterministic joins into `model_table.csv`; free-form folder crawling or domain-specific naming assumptions are not part of the contract.
- [ ] ZIP uploads are treated only as generic package containers; after safe extraction, the same required files and paths must exist.
- [ ] Required input/output roles, units, dtypes, bounds, output directions, group/split columns, and ignored columns are explicit in the manifest/dictionary.
- [ ] The Fraunhofer fuel-cell demo variables are represented as normal generic variables, including inputs such as `pt_c_ratio`, `i_c_ratio`, `ionomer_ew`, `operating_rh`, `operating_voltage`, `ast_rh`, `ast_upl` and outputs such as `bol_current_density`, `eol_current_density`, `bol_ecsa`, `ecsa_loss`.

**Files likely touched:**

- `data/Cathode Catalyst Degradation/mirai_manifest_template.json` or new `mirai_manifest.json`
- `data/Cathode Catalyst Degradation/data_dictionary_template.csv` or new `data_dictionary.csv`
- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`

**Verification:**

```bash
cd backend
uv run python -m ml_lifecycle.entrypoints.validate_manifest ../data/"Cathode Catalyst Degradation"
```

**Dependencies:** None.

**Scope:** Medium.

### Task 1.2: Adapt the Fraunhofer demo into the generic package

**Description:** Create or document a Fraunhofer demo package that follows the generic Mirai structure. Recommended: use a prepared canonical `model_table.csv` for the Railway happy path, with the huge original workbook/zips kept as source/reference material outside the runtime intake path.

**Acceptance criteria:**

- [ ] Decision recorded in `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`.
- [ ] The Fraunhofer demo package includes a real `model_table.csv` and matching manifest/dictionary.
- [ ] Any raw workbook/zip/folder source files are reference/audit inputs only; they are not required for runtime upload success.
- [ ] The decision explicitly says there is still only one Mirai intake path for fuel cells, batteries, and all other engineering tabular projects.

**Files likely touched:**

- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`
- `backend/ml_lifecycle/README.md`
- Possibly `docs/railway-level-2-pilot.md`

**Verification:** Manual doc review plus contract validation.

**Dependencies:** Task 1.1.

**Scope:** Small.

## Phase 2: Remove User-Facing Dual Intake Paths

### Task 2.1: Simplify frontend intake UI to one Mirai package path

**Description:** Remove the ingestion-path dropdown. Present one required Mirai Experiment Package structure for all projects. Mention ZIP only as an accepted way to upload that same folder/package, not as a separate processing path.

**Acceptance criteria:**

- [ ] `DataIntakePage` no longer asks the user to choose `Generic Mirai Contract` vs `Fuell Cell DoE Demo`.
- [ ] UI copy says all uploads require `mirai_manifest.json`, `data_dictionary.csv`, and preferably `model_table.csv`.
- [ ] UI copy explains optional overview/metadata files and ZIP packaging in generic terms.
- [ ] Existing project/new project flow remains intact.
- [ ] Frontend type no longer exposes `fuel_cell_doe_demo` as a user-selectable path.

**Files likely touched:**

- `frontend/src/components/DataIntakePage.tsx`
- `frontend/src/lib/api.ts`
- `frontend/public/templates/*`

**Verification:**

```bash
cd frontend
npm run build
```

**Dependencies:** Task 1.1.

**Scope:** Medium.

### Task 2.2: Normalize create-ingestion-session API input

**Description:** Keep API compatibility if needed, but make backend default and canonical value `generic_tabular_doe`. Ignore or reject `fuel_cell_doe_demo` once the UI no longer sends it.

**Acceptance criteria:**

- [ ] New sessions store `ingestion_path: generic_tabular_doe` or replace it with `lifecycle_contract: generic_tabular_doe`.
- [ ] Workspace/project metadata no longer stores a domain processor selected by request field; the accepted structure is the same for every project.
- [ ] Existing legacy sessions can still be read without crashing.
- [ ] API behavior is workspace-authorized and does not trust workspace from request body over verified JWT.

**Files likely touched:**

- `backend/app/services/data_intake.py`
- `backend/app/schemas.py`
- `backend/app/main.py`
- `backend/tests/test_api.py`

**Verification:**

```bash
cd backend
uv run pytest tests/test_api.py -q
```

**Dependencies:** Task 2.1 can run in parallel after contract direction is clear.

**Scope:** Medium.

## Phase 3: Collapse Backend Preprocessing to the Generic Contract

### Task 3.1: Replace fuel-cell preprocessing route implementation with generic preprocessing

**Description:** Rename or internally redirect the preprocessing start path so every session uses `start_generic_preprocessing(...)`. Preprocessing should validate the same generic Mirai package structure for every project and produce the same canonical artifact set.

**Acceptance criteria:**

- [ ] `start_fuel_cell_preprocessing(...)` no longer contains a separate extraction/preprocessing implementation.
- [ ] The preprocessing start endpoint runs generic contract validation first for every package.
- [ ] Missing/incomplete fuel-cell manifest/model table fails as a Mirai contract error, not as a separate fuel-cell validation path.
- [ ] Generic ZIP handling, if implemented, only safely extracts/inventories a Mirai package and then validates the same required files.
- [ ] Reports use neutral names such as `mirai_contract_package`, `package_inventory`, and `canonical_artifacts`.

**Files likely touched:**

- `backend/app/services/preprocessing_review.py`
- `backend/app/main.py`
- `backend/tests/test_api.py`
- `backend/tests/test_generic_contract_pipeline.py`

**Verification:**

```bash
cd backend
uv run pytest tests/test_generic_contract_pipeline.py tests/test_api.py -q
```

**Dependencies:** Task 1.1.

**Scope:** Medium/Large; split further if implementation exceeds one session.

### Task 3.2: Strengthen generic contract tests with the fuel-cell demo shape

**Description:** Add or update tests proving the fuel-cell demo, after being reshaped into the generic package, runs through `build_generic_preprocessing_artifacts(...)` and produces the canonical columns expected by the app.

**Acceptance criteria:**

- [ ] Test does not rely on the full 930 MB folder unless explicitly marked slow/local.
- [ ] Test uses a small generic package fixture or prepared canonical fuel-cell `model_table.csv`.
- [ ] Test asserts no legacy `fuel_cell_doe_demo` branch is required.
- [ ] Test asserts generated schema input/output order and split counts.

**Files likely touched:**

- `backend/tests/test_generic_contract_pipeline.py`
- `backend/tests/fixtures/...` if small fixtures are added

**Verification:**

```bash
cd backend
uv run pytest tests/test_generic_contract_pipeline.py -q
```

**Dependencies:** Task 3.1.

**Scope:** Medium.

## Phase 4: Generic Training and Runtime Activation

### Task 4.1: Remove project-id special casing from training selection

**Description:** Ensure training uses the generic training path based on contract/schema for every project, including the reshaped Fraunhofer fuel-cell package. Avoid `project_id == pem_fuel_cell_real_cathode_degradation` as a reason to switch training implementations.

**Acceptance criteria:**

- [ ] `start_training_request(...)` chooses `train_generic_project(...)` for the Fraunhofer contract path.
- [ ] `activate_session_artifacts_for_model_quality(...)` no longer copies fuel-cell artifacts into old reference locations for generic contract sessions.
- [ ] Training artifact S3 upload writes under workspace/project/training_run prefixes.
- [ ] Postgres training/model/artifact rows are updated after successful training.

**Files likely touched:**

- `backend/app/services/training_requests.py`
- `backend/app/services/control_plane.py`
- `backend/tests/test_generic_contract_pipeline.py`
- `backend/tests/test_mlflow_durable_pointers.py`

**Verification:**

```bash
cd backend
uv run pytest tests/test_generic_contract_pipeline.py tests/test_mlflow_durable_pointers.py -q
```

**Dependencies:** Task 3.1.

**Scope:** Medium.

### Task 4.2: Make model-quality/data UI resolve session/runtime artifacts consistently

**Description:** Ensure the UI can show Fraunhofer data when Postgres points to S3 objects, and when a new uploaded session has local or S3-backed artifacts.

**Acceptance criteria:**

- [ ] Project schema/status endpoints use Postgres control-plane state when enabled.
- [ ] Artifact status includes dataset, schema, preprocessing, model, and MLflow pointers with clear availability.
- [ ] Missing S3 object versus missing Postgres pointer produce distinct UI messages.
- [ ] Battery placeholder remains hidden/denied for the Fraunhofer workspace.

**Files likely touched:**

- `backend/app/services/project_registry.py`
- `backend/app/services/model_quality.py`
- `backend/app/services/workspace_storage.py`
- `frontend/src/components/*ModelQuality*` or project status components
- `backend/tests/test_api.py`
- `backend/tests/test_workspace_storage.py`

**Verification:**

```bash
cd backend
uv run pytest tests/test_api.py tests/test_workspace_storage.py -q
cd ../frontend
npm run build
```

**Dependencies:** Task 4.1.

**Scope:** Medium.

## Phase 5: Railway Data Availability Audit and Backfill

### Task 5.1: Audit Railway Postgres pointers versus S3 objects

**Description:** Verify why Fraunhofer data is not visible on Railway by comparing Postgres runtime rows to S3 object keys. Do not print secrets or raw credentials.

**Acceptance criteria:**

- [ ] Confirm `workspaces`, `projects`, `datasets`, `schema_manifests`, `training_runs`, `models`, and `artifact_objects` rows exist for `workspace_id='fraunhofer'`.
- [ ] Confirm every seeded object key exists in `mirai-fuel-cells-demo`.
- [ ] Identify any mismatch between seed SQL object keys and actual bucket keys.
- [ ] Confirm app endpoints return workspace-scoped project/schema/artifact status for a signed-in Fraunhofer user.

**Tools/skills:** `use-railway`, Railway MCP/CLI, no secret printing.

**Verification examples:**

```bash
# Exact Railway commands should be chosen during implementation using MCP/CLI context.
# Do not print env var values or bucket credentials.
```

**Dependencies:** Can run before implementation if the user wants immediate diagnosis.

**Scope:** Medium.

### Task 5.2: Backfill runtime rows or object keys to match the unified contract

**Description:** Once mismatches are known, update the Railway seed/migration/backfill process so Fraunhofer demo appears with canonical contract artifacts.

**Acceptance criteria:**

- [ ] Seed/backfill writes pointers to actual S3 keys.
- [ ] New contract artifacts are represented in `artifact_objects`.
- [ ] Dataset row records row/column counts and manifest version where available.
- [ ] Runtime seed remains Fraunhofer-only; battery remains hidden/deferred.

**Files likely touched:**

- `backend/db/seeds/002_seed_fraunhofer_fuel_cell_runtime.sql`
- Possibly a new migration/seed if schema needs additional fields
- `deployments/railway/README.md`
- `docs/railway-level-2-pilot.md`

**Verification:**

- Railway signed-in Fraunhofer user sees only `pem_fuel_cell_real_cathode_degradation`.
- Project data/artifact status shows available canonical dataset/schema/preprocessing/model pointers.
- Direct battery access returns `403` or `404`.

**Dependencies:** Task 5.1.

**Scope:** Medium.

## Phase 6: Documentation and Deprecation Cleanup

### Task 6.1: Rewrite Mirai contract docs from two paths to one path

**Description:** Update docs to say there is one Mirai intake lifecycle. Remove typo `Fuell` and avoid describing a separate fuel-cell path or PEM-specific processor. Document ZIP as a generic package/container option only.

**Acceptance criteria:**

- [ ] `MIRAI_DATA_CONTRACT.md` documents one lifecycle.
- [ ] Fuel-cell appears only as an example dataset reshaped into the generic package structure.
- [ ] Generic direct canonical model-table and constrained multi-table examples remain.
- [ ] Railway runtime architecture is linked: Postgres pointers + S3 artifacts + MLflow runs.

**Files likely touched:**

- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`
- `backend/ml_lifecycle/README.md`
- `README.md`
- `docs/railway-level-2-pilot.md`

**Verification:** Manual review.

**Dependencies:** Phases 1-4.

**Scope:** Small/Medium.

### Task 6.2: Remove or quarantine obsolete fuel-cell lifecycle modules

**Description:** After tests prove the generic path handles the reshaped fuel-cell package, remove direct imports/use of fuel-cell-specific preprocessing/training from runtime code. Keep any old parser utilities only as offline migration/reference scripts, not as runtime processors.

**Acceptance criteria:**

- [ ] Runtime services no longer import `fuel_cell_doe_demo.preprocess.build_preprocessing_artifacts`.
- [ ] Runtime services no longer choose `fuel_cell_doe_demo.train.train_models` for Fraunhofer contract sessions.
- [ ] Any remaining `fuel_cell_doe_demo` module is clearly a historical/offline migration script, not an application lifecycle or runtime processor.
- [ ] Tests fail if `fuel_cell_doe_demo` is reintroduced as a user-facing intake path.

**Files likely touched:**

- `backend/app/services/preprocessing_review.py`
- `backend/app/services/training_requests.py`
- `backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/*` as needed
- `backend/ml_lifecycle/training/fuel_cell_doe_demo/*` as needed
- tests/docs

**Verification:**

```bash
rg -n "fuel_cell_doe_demo|Fuell Cell|fuel-cell-package" backend frontend docs README.md
cd backend && uv run pytest -q
cd ../frontend && npm run build
```

**Dependencies:** Phases 3-4.

**Scope:** Medium/Large; do after functional parity is proven.

## Checkpoints

### Checkpoint A: Contract-only proof

Run after Phase 1:

- [ ] The generic Mirai contract validates for the reshaped fuel-cell demo package.
- [ ] Generic test still passes.
- [ ] No runtime behavior changed yet.

### Checkpoint B: UI/API single-path proof

Run after Phase 2:

- [ ] User sees one Mirai package upload path.
- [ ] Upload creates a generic contract session.
- [ ] Existing/legacy sessions still list safely.
- [ ] Frontend builds.

### Checkpoint C: Backend generic preprocessing proof

Run after Phase 3:

- [ ] Generic preprocessing handles normal tabular packages and the reshaped fuel-cell package through the same code path.
- [ ] Legacy fuel-cell preprocessing branch is removed or unreachable.
- [ ] EDA/preprocessing reports remain usable.

### Checkpoint D: Training/runtime proof

Run after Phase 4:

- [ ] Fraunhofer training request uses generic training.
- [ ] MLflow receives candidate runs and registered challenger model.
- [ ] Postgres runtime rows point to S3 artifacts.
- [ ] UI model-quality/data status can explain missing versus available artifacts.

### Checkpoint E: Railway signed-in pilot proof

Run after Phase 5:

- [ ] Signed-in Fraunhofer user sees only the fuel-cell project.
- [ ] Fuel-cell project shows dataset/artifact availability.
- [ ] Direct battery access returns `403` or `404`.
- [ ] MLflow UI contains real run/artifact/model data after retraining.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---:|---|
| Full fuel-cell source folder is huge (~930 MB) | Slow local/Railway preprocessing and accidental artifact explosion | Use canonical CSV demo path for happy path; keep raw zips as reference/audit source material outside runtime artifacts |
| Removing legacy fuel-cell path breaks current demo | High | Prove the reshaped generic package with contract tests before deleting runtime fallback |
| S3 contains files but UI still shows no data | High | Audit Postgres pointers versus S3 keys; make UI explain pointer/object availability separately |
| Generic training differs from old fuel-cell training | Medium | Use surrogate-model debugging checks: input order, units, preprocessing, split counts, ONNX verification |
| Workspace leakage through upload/project params | High | Keep verified JWT `workspace_id` as authority; tests for Fraunhofer-only visibility and battery denial |
| Contract too rigid for real OEM uploads | Medium | Keep the required structure concise and explicit; support only deterministic joins/overview tables, not ambiguous automatic mapping |
| Existing legacy sessions break | Medium | Read legacy session metadata but create only unified sessions going forward |

## Open Questions

1. Should the fuel-cell demo contract package be created from the existing `data/reference/pem_fuel_cell_cathode_degradation/model_table.csv`, or should we regenerate a cleaner canonical `model_table.csv` from the huge source folder before implementing the unified path?
   - Recommendation: start with the existing prepared canonical table for Railway demo reliability, then separately improve the offline source-to-canonical preparation if needed.
2. Should the local `data/Cathode Catalyst Degradation` root be updated in place with real `mirai_manifest.json` / `data_dictionary.csv`, or should we create a smaller `data/reference/fuel_cell_contract_package/` fixture?
   - Recommendation: create a smaller contract package fixture and leave the huge source folder ignored/reference-only.
3. Do we want to preserve backward-compatible API endpoints temporarily (`/fuel-cell-package/validation`) as deprecated no-ops, or remove them immediately?
   - Recommendation: keep compatibility for one release if frontend/tests still reference them, but mark deprecated and route to generic contract validation.
4. Should Railway seed/backfill be part of this implementation, or a follow-up after local contract consolidation?
   - Recommendation: local consolidation first, Railway audit/backfill second.

## Suggested Implementation Order

1. Phase 1: Real generic fuel-cell contract fixture.
2. Phase 3.2: Contract/generic preprocessing proof test.
3. Phase 3.1: Collapse backend preprocessing runtime to generic.
4. Phase 2: Simplify UI/API user-facing path.
5. Phase 4: Generic training/runtime activation cleanup.
6. Phase 5: Railway pointer/object audit and backfill.
7. Phase 6: Docs/deprecation cleanup.

## Exact Local Test Commands

Backend focused:

```bash
cd backend
uv run pytest tests/test_generic_contract_pipeline.py tests/test_api.py tests/test_workspace_storage.py -q
```

Backend full:

```bash
cd backend
uv run pytest -q
```

Frontend:

```bash
cd frontend
npm run build
```

Search for remaining duplicate-path language:

```bash
rg -n "fuel_cell_doe_demo|Fuell Cell|fuel-cell-package|ingestion_path" backend frontend docs README.md
```
