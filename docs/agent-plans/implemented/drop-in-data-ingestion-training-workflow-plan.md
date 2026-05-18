# Drop-In Data Ingestion + Training Workflow Plan

## Context

The current product has a single disabled placeholder, **Upload data & train model**, under **Tailored ML Model**. The next platform step should split that placeholder into a professional, staged ML workflow:

1. **Drop in data** — scientists or Mirai upload raw/scattered experimental data packages.
2. **Data ingestion & preprocessing review** — the engine profiles data, maps schemas, validates units/provenance, runs EDA, and produces auditable preprocessing artifacts.
3. **Model training setup** — once preprocessing is approved, the UI proposes a small set of MVP model families and configurations.
4. **Model Quality** — existing trust/evidence page remains the destination after training.

This should build on the real fuel-cell work, where data was not a single clean CSV. It included zips, folders, workbooks, raw diagnostic files, evaluation scripts, and paper-derived schema decisions. The MVP should therefore support both a simple CSV template and a more realistic "data package" workflow without overbuilding a fully autonomous data platform.

## Current Findings

- `docs/agent-plans/implemented/real-fuel-cell-data-transformation-plan.md` documents the staged raw-data-to-canonical-table process used for the fuel-cell dataset.
- `docs/agent-plans/implemented/mlflow-real-ml-training-plan.md` documents the later preprocessing, MLflow, model training, registry, and Model Quality workflow.
- `frontend/src/components/Tabs.tsx` currently has one disabled item: **Upload data & train model**.
- `frontend/src/types/doe.ts` currently defines active tabs for `model-quality`, `design-studio`, `batch`, `optimization`, and `impact` only.
- `backend/app/services/model_quality.py` already exposes read-only preprocessing/model-quality summaries for the existing real fuel-cell project, including `preprocessing_report`, `artifact_summary`, `latest_runs`, and a placeholder AI preprocessing assistant.
- Current backend model-quality services are project-specific and file-backed around `pem_fuel_cell_real_cathode_degradation`; a generalized upload/ingestion/training workflow will need a project/session abstraction.

## Recommended MVP Approach

Create a staged **Tailored ML Model** workflow with two new tabs, not one overloaded placeholder:

1. **Data Intake**
   - Purpose: upload/request data and create a new project plus dataset ingestion session.
   - Recommended MVP rule: **force a Mirai Experiment Package**, but make that package realistic for OEM/lab exports.
   - The package may contain one clean table, many CSV/XLSX files, or a zip of scattered testbench outputs, but it must include or eventually produce a small Mirai manifest/data dictionary.
   - Output: `project_id`, `dataset_id`, `ingestion_session_id`, uploaded file inventory, declared target outputs, declared input candidates, units, and provenance notes.

2. **Preprocessing Review**
   - Purpose: show whether ingestion and preprocessing are complete and scientifically acceptable.
   - Shows EDA, column/role mapping, missingness, duplicates, unit checks, inferred joins, rejected rows, imputation/scaling choices, split plan, leakage warnings, and generated artifacts.
   - Includes approval gates: `Needs mapping`, `Ready for preprocessing`, `Preprocessing complete`, `Approved for training`.
   - MVP permission model: Mirai/admin users perform or approve mapping first; scientist-facing controls can be mostly review/read-only.

Then connect approved preprocessing artifacts to a **Training Request** panel inside **Preprocessing Review**. For MVP, the UI should create a reviewed training request/job spec rather than launching a fully automatic training job immediately.

## Industry Data-Format Scan

A quick public-doc scan suggests the right product stance is **not** "one CSV per input variable." Automotive and battery/energy testing data usually has common concepts but heterogeneous physical exports:

- Automotive/engine/testbench ecosystems use measurement-data standards such as ASAM MDF for recorded signals and ASAM ODS/openMDM-style structures for test/measurement metadata and data management. The important idea is separation between test metadata, measured channels/signals, units, and result datasets.
- Battery cyclers and battery repositories often expose cycle/channel/time-series data plus cell metadata and summary outputs. Vendors differ greatly, but the recurring pattern is cell/test metadata + repeated measurements + derived features/results.
- Our fuel-cell case matches this: `data_overview.xlsx` was sample/test metadata, while each `Cell_NN` archive had many raw diagnostic CSVs, and our pipeline produced audited intermediate tables plus one final model table.

Conclusion: Mirai can enforce a **semantic package contract** without forcing every customer to reshape their labs into one file. The contract should require identifiers, roles, units, and relationships, while allowing files to remain scattered.

### Recommended Mirai Experiment Package

For MVP, require a zip/folder with one of these shapes:

1. **Simple template package**
   - `model_table.csv` or `.xlsx`: one row per modelable experiment/condition.
   - `data_dictionary.csv` or `manifest.json`: column roles, units, allowed ranges, group keys.

2. **Structured multi-table package**
   - `experiments.csv`: one row per tested sample/campaign/run.
   - `conditions.csv`: controlled variables and settings.
   - `measurements/*.csv`: raw or semi-processed time/curve/cycle/channel tables.
   - `results.csv`: target outputs or derived KPIs if already calculated.
   - `manifest.json`: declares keys, roles, units, and which tables join to produce the model table.

3. **Raw testbench package**
   - Any zip of CSV/XLSX files plus optional manifest.
   - If no manifest is provided, the UI marks the session as `Needs mapping` and creates a Mirai-admin task list rather than attempting magic.

This is more professional than "one CSV per variable" because inputs often belong at different levels: sample-level composition, test-level operating condition, cycle/time-level signals, and derived output-level KPIs.

## Product Workflow

### Step 1 — Data Intake

Scientists or Mirai admins create a **new project ID** and choose one intake path:

- **Fast start: Mirai tabular template**
  - Best for companies willing to export a canonical table.
  - Can support multiple tables if they share keys.
  - Requires a minimal data dictionary: column name, semantic role, unit, input/output/context, optional grouping key.

- **Real-world data package**
  - Best for scattered lab/testbench data.
  - Upload `.zip` with raw CSV/XLSX files and optional manifest.
  - Manifest can describe files, keys, units, target outputs, and expected joins.
  - If no manifest exists, UI creates a `Needs mapping` task list for Mirai/admin review rather than failing.

- **Future assistant placeholder**
  - A disabled/placeholder assistant panel can say: "Generate manifest draft from uploaded files — coming soon."
  - It should not be active in MVP; the first MVP keeps mapping human-reviewed.

### Step 2 — Ingestion & EDA

Backend creates an auditable ingestion run:

- file inventory and checksums
- detected file types/sheets
- column profiling
- missingness matrix
- numeric ranges and outliers
- categorical levels
- duplicate rows/keys
- possible join keys
- unit detection/manual unit confirmation
- target/input/context column classification
- leakage checks
- rejected/ambiguous rows

### Step 3 — Preprocessing Review

UI shows a professional ML engineering checklist:

- Dataset readiness score/status, not a black-box "success" banner.
- EDA cards and downloadable reports. Recommended MVP engine: `ydata-profiling` for an HTML/JSON profile when dataset size is manageable, with a lightweight pandas summary fallback for very large or sensitive uploads.
- Imputation plan: none/median/mean/mode/domain constant/manual exclusion.
- Scaling/encoding plan: standard/min-max/robust/one-hot/ordinal.
- Split plan: random/grouped/time/campaign/cell-aware depending on metadata.
- Future Pi assistant placeholder: suggest imputation, scaling/encoding, feature exclusion, and split strategy from EDA results, but keep all preprocessing decisions Mirai-admin approved before training.
- Warnings requiring human approval.
- Generated artifacts: canonical tables, preprocessing JSON, data dictionary, rejected rows, EDA report.

### Step 4 — Training Request Setup

Once preprocessing is approved, show a focused MVP training request builder. It creates a reviewed training spec for Mirai/admin execution rather than automatically running arbitrary training from the UI.

Lean MVP model set:

- **Mean/median baseline** — sanity baseline.
- **Linear/MVLR** — interpretable baseline.
- **MLP** — neural surrogate option, initially modest architecture presets.

Defer XGBoost/Random Forest and broad AutoML until the ingestion/preprocessing/training lifecycle is proven.

Start with simple request presets:

- `Quick smoke test` — small run, validates pipeline.
- `Balanced training` — recommended default.
- `High-effort search` — disabled/future or admin-only.

Training outputs should flow into existing Model Quality/MLflow lifecycle:

- generated MLflow run names preserved
- `project_id`, `dataset_id`, `ingestion_session_id`, `preprocessing_run_id`, `model_family` as tags
- registered deployable models default to `challenger`
- `champion` remains manual

## Files to Modify

Likely frontend:

- `frontend/src/types/doe.ts` — add `data-intake` and `preprocessing-review` tab IDs.
- `frontend/src/components/Tabs.tsx` — replace disabled **Upload data & train model** with staged Tailored ML Model items.
- `frontend/src/App.tsx` — route new pages.
- `frontend/src/components/DataIntakePage.tsx` — new upload/request workflow.
- `frontend/src/components/PreprocessingReviewPage.tsx` — new EDA/preprocessing readiness page.
- `frontend/src/lib/api.ts` — add typed clients for ingestion sessions, preprocessing reports, approval state, and training launch.

Likely backend:

- `backend/app/main.py` — add ingestion/preprocessing/training endpoints.
- `backend/app/schemas.py` — request/response models for ingestion sessions, manifests, preprocessing approval, training launch.
- `backend/app/services/data_intake.py` — store uploads, manifests, file inventory, checksums.
- `backend/app/services/preprocessing_review.py` — generalized read/write service for EDA/preprocessing reports and approval gates; use `ydata-profiling` where practical plus a lightweight summary fallback.
- `backend/app/services/training_jobs.py` — launch/track training jobs or enqueue command specs.
- `backend/training/real_data_pipeline/` — reuse patterns from fuel-cell data transformation for canonical dataset generation.
- `backend/training/real_training_pipeline/` — reuse preprocessing/training/MLflow code, but generalize around dataset/project descriptors.

Docs:

- `docs/tutorials/TAILORED_ML_MODEL_DATA_INTAKE.md` — scientist-facing data package/template guide.
- `docs/reference/MLFLOW_MODEL_LIFECYCLE.md` — document uploaded dataset IDs and training UI connection.
- `docs/reference/REAL_FUEL_CELL_DATASET.md` — reference as an example of data package mode.

## Reuse

- Fuel-cell transformation approach from `backend/training/real_data_pipeline/build_real_fuel_cell_dataset.py`.
- Real preprocessing/training pattern from `backend/training/real_data_pipeline/preprocess_real_fuel_cell.py` and `backend/training/real_training_pipeline/train_real_fuel_cell_models.py`.
- Existing Model Quality API and UI concepts from `backend/app/services/model_quality.py` and `frontend/src/components/ModelQualityPage.tsx`.
- Existing MLflow lifecycle: register deployable models, default challenger, manual champion.
- Existing artifact conventions: schema, preprocessing JSON, metadata, ONNX/package artifacts.

## Schema Mapping Definition

In this plan, **schema mapping** means translating customer/lab column names and file structures into Mirai's modeling contract. Example mappings:

- `U.C[V]` or `Voltage` -> `operating_voltage`, unit `V`, role `input` or curve axis depending on workflow.
- `I.C[A/cm2]` -> current-density target/measurement, unit `A/cm²`.
- `Cell_01`, `test_no`, `campaign_id` -> grouping/provenance keys used for splits and leakage checks.
- workbook sample metadata -> sample-level inputs such as composition or AST conditions.

For MVP, Mirai/admins should perform or approve this mapping. Scientists can see the result and provide corrections, but the first version does not need a complex self-service mapper.

## Key MVP Boundary

Do **not** build full AutoML, free-form arbitrary data cleaning, or autonomous schema inference in the first iteration. Instead:

- Support upload/session tracking.
- Support file inventory and EDA.
- Support `ydata-profiling`-style downloadable EDA reports where practical, without making the UI dependent on one heavy report format.
- Support a semi-structured manifest/data dictionary.
- Support Pi assistant placeholders for preprocessing recommendations, but require explicit Mirai-admin approval before training.
- Support a small model menu and existing MLflow-backed quality review.

## Resolved Decisions

1. **Data shape:** Force a Mirai template/package contract, but support both one-table and multi-file zip packages.
2. **Mapping:** Start with both scientist-visible and Mirai/admin-operated mapping, but keep MVP controls admin-first to avoid overcomplication.
3. **Training execution:** MVP creates a reviewed training request/job spec; full automatic training launch can come later.
4. **Project creation:** Data intake creates a new `project_id`.
5. **Model families:** Keep MVP lean: mean/median baseline, MVLR/linear, MLP. Defer XGBoost/Random Forest.
6. **Manifest/preprocessing assistant:** Include placeholders for future Pi/smart DoE assistant manifest generation and preprocessing recommendations, but keep the MVP human-reviewed and Mirai-admin approved.
7. **EDA report engine:** Prefer `ydata-profiling` for downloadable HTML/JSON EDA reports, with a lightweight fallback for large/sensitive datasets.
8. **Storage:** Store uploaded raw data locally for the MVP. Add a dedicated follow-up TODO for S3/MinIO-style object storage.
9. **Approval roles:** Mirai admins approve preprocessing before training in the MVP.
10. **Manifest format:** Use JSON internally for backend validation, plus downloadable/editable CSV/XLSX data-dictionary templates for scientists.

## Implementation Depth Decision

The first implementation should include real local upload/inventory/checksum backend from day one, not only mocked UI. The UI can still ship with realistic demo/empty states, and preprocessing/training can remain staged/request-based until the full generalized data pipeline is ready.

## Steps

- [x] Finalize implementation depth: UI skeleton first vs real upload/inventory/checksum backend from day one.
- [x] Add Tailored ML Model navigation items: Data Intake and Preprocessing Review.
- [x] Add frontend skeleton pages with realistic empty/loading/demo states.
- [x] Add a Mirai Experiment Package explainer and downloadable template placeholders.
- [x] Add backend ingestion session model and local raw-data upload storage.
- [x] Add file inventory/checksum endpoint.
- [x] Add JSON manifest contract and downloadable CSV/XLSX data-dictionary templates with one-table and multi-table examples.
- [x] Add `Needs mapping` admin workflow state and placeholder manifest-assistant card.
- [x] Add EDA/preprocessing report artifact model, including `ydata-profiling` HTML/JSON report support and a lightweight fallback summary.
- [x] Add placeholder Pi assistant recommendation panel for imputation, scaling/encoding, feature exclusion, and split strategy.
- [x] Add preprocessing approval state.
- [x] Add small training-request builder connected to approved preprocessing artifacts.
- [x] Log dataset/preprocessing/training request IDs into MLflow once training is executed.
- [x] Route completed training into existing Model Quality page.

## Verification

- Create a new project from Data Intake.
- Upload or stage a simple CSV template and see an ingestion session with file inventory.
- Upload or stage a multi-file zip and see manifest/mapping-required state.
- Confirm the UI explains why Mirai uses a package contract rather than one CSV per variable.
- Generate/read EDA report with missingness, ranges, duplicates, and warnings; verify downloadable `ydata-profiling` report when enabled.
- Verify Pi assistant recommendation area is clearly labeled as a future placeholder and does not change preprocessing automatically.
- Approve preprocessing and unlock training request setup.
- Stage a training request with mean baseline, MVLR, and MLP selected.
- Confirm resulting request captures project/dataset/preprocessing IDs and selected model families.
- Confirm completed training later routes into Model Quality and MLflow metadata.
