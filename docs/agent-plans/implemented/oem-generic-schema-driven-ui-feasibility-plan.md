# OEM Generic Schema-Driven Intake, Preprocessing, and UI Plan

## Context
The current app has a useful foundation for becoming an OEM-generic ML-guided DoE/design engine, but it is not generic end-to-end yet. The UI/API layer can already render many things from `schema.inputs`, `schema.outputs`, and domain metadata, while the authoritative scientific preprocessing/training schema is still hardcoded for the PEM fuel-cell project.

The intended product direction is not to guess arbitrary customer data semantics automatically. Instead, Mirai should **force scientists/OEMs to provide data in a Mirai-approved manifest/data-dictionary format**. Users may name variables however they want, but every variable must be explicitly mapped to a role, unit, dtype, direction, bounds, grouping/split meaning, and plotting/semantic metadata before preprocessing or training begins.

The existing PEM fuel-cell project should remain as the polished reference/demo and the first template implementation, but its working structure should be generalized into a reusable contract-driven pipeline.

## Approach
Move from a PEM-specific pipeline with schema-driven UI patches to a contract-driven workflow:

1. **Manifest/data dictionary is the starting point.** OEMs/scientists upload data plus Mirai-format metadata. If required metadata is missing, the project cannot proceed beyond intake/review.
2. **Metadata review is authoritative.** The existing “Metadata & Plot Setup” UI becomes the place where scientists/admins complete and approve variable roles, units, bounds, output directions, grouping keys, split hints, plot recipes, and downstream display behavior.
3. **Generic preprocessing consumes approved metadata.** A new generic preprocessing path reads the approved contract, builds `model_table.csv`, validates inputs/outputs, applies split strategy, generates `schema.json` / `preprocessing.json`, and writes audit reports without PEM-specific column assumptions.
4. **Downstream stays contract-driven.** Training, Model Quality, Design Studio, BO, predictions, recommendations, and exports consume the same approved schema/preprocessing artifacts. No downstream component should rediscover or hardcode fuel-cell semantics.
5. **PEM remains a template/demo.** The current PEM ingest/preprocess/train implementation stays available as `template_id=fuel_cell` / demo reference, but fuel-cell assumptions move behind template configuration or explicit project recipes rather than generic paths.
6. **Generic entrypoints become the default.** Add generic commands such as `preprocess_project` and `train_project`; keep existing fuel-cell wrappers as compatibility/demo commands.

## Files to modify
Likely affected files after approval:

- `frontend/public/templates/mirai_manifest_template.json`
- `frontend/public/templates/mirai_manifest_multitable_template.json`
- `frontend/public/templates/data_dictionary_template.csv`
- `frontend/public/templates/data_dictionary_multitable_example.csv`
- `frontend/src/components/DataIntakePage.tsx`
- `frontend/src/components/PreprocessingReviewPage.tsx`
- `frontend/src/components/DesignStudioPage.tsx`
- `frontend/src/components/ModelQualityPage.tsx`
- `frontend/src/components/ModelMap.tsx`
- `frontend/src/components/BusinessImpactPage.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/types/doe.ts`
- `backend/app/schemas.py`
- `backend/app/services/data_intake.py`
- `backend/app/services/domain_metadata.py`
- `backend/app/services/project_registry.py`
- `backend/app/services/preprocessing_review.py`
- `backend/app/services/training_requests.py`
- `backend/app/services/design_studio.py`
- `backend/app/services/model_quality.py`
- `backend/app/services/bayesian_optimization.py`
- `backend/app/services/prediction.py`
- `backend/app/services/recommendation.py`
- `backend/training/common/` new generic manifest/schema/preprocessing utilities
- `backend/training/projects/pem_fuel_cell/` retained as fuel-cell template/demo implementation
- `backend/training/entrypoints/` generic project entrypoints plus compatibility fuel-cell wrappers
- `backend/tests/` API and pipeline tests for generic tabular datasets

## Reuse
Existing reusable foundations:

- `frontend/public/templates/*` already define the right starting point: manifest and data-dictionary files with roles, units, dtypes, bounds, directions, joins, and split hints.
- `backend/app/services/data_intake.py` already stores uploaded sessions and detects manifest/data-dictionary presence.
- `backend/app/services/domain_metadata.py` already defines `VariableMetadata`, `PlotRecipe`, `UiConfig`, and `ProjectDomainMetadata`; these should become stricter approved-contract structures rather than mostly inferred display hints.
- `frontend/src/components/PreprocessingReviewPage.tsx` already has Metadata & Plot Setup-style controls for role/unit metadata; this can become the mandatory approval UI.
- `backend/app/services/project_registry.py` already centralizes schema/artifact resolution and can expose uploaded project contracts consistently.
- `schema.inputs` / `schema.outputs` already drive Model Map, prediction, recommendation, objective weights, and many Design Studio controls.
- Current PEM files under `backend/training/projects/pem_fuel_cell/` provide the working reference structure for ingest → canonicalize → preprocess/split → train/evaluate → export/register.

## Key findings so far

### Already partly generic
- Intake can accept arbitrary uploads and create ingestion sessions.
- Frontend can render many controls from `ProjectSchema`.
- Model Map is schema-driven.
- Design Studio objective controls and weights are mostly schema-driven.
- Prediction/recommendation panels use schema input/output metadata.
- Domain metadata exists as a service layer.

### Still PEM/fuel-cell-specific
- Authoritative training schema lives in `backend/training/projects/pem_fuel_cell/schema.py` as `PAPER_INPUT_COLUMNS`, `PAPER_OUTPUT_COLUMNS`, `MODEL_COLUMNS`, and `REAL_PROJECT_SCHEMA`.
- PEM ingestion expects `data_overview.xlsx`, `Cell_NN.zip`, workbook columns, fuel-cell measurement folders, and fuel-cell raw file semantics.
- PEM preprocessing assumes columns such as `cell_id`, `operating_rh`, `operating_voltage`, `bol_current_density`, `eol_current_density`, `bol_ecsa`, and `ecsa_loss`.
- PEM training uses those exact columns and outputs.
- Uploaded project preprocessing currently calls fuel-cell-specific validation/preprocessing paths.
- Some UI copy and plots still assume cells, RH, voltage sweeps, current density, ECSA, and polarization curves.
- Generic OEM templates exist, but they are not yet the enforced source of truth for preprocessing/training.

## Proposed Mirai data contract
The contract should be stricter than “inferred metadata.” It should be user-provided and admin/scientist-approved.

Required minimum fields for each project:

```json
{
  "manifest_version": "0.2",
  "project": {
    "project_id": "oem_project_id",
    "display_name": "OEM Project Name",
    "domain": "fuel_cell | battery | engine | materials | generic_tabular_doe | other",
    "template_id": "fuel_cell | generic_tabular_doe | custom_tabular"
  },
  "tables": [
    {
      "path": "model_table.csv",
      "table_type": "model_table",
      "primary_key": ["experiment_id"]
    }
  ],
  "columns": [
    {
      "table": "model_table.csv",
      "name": "temperature_c",
      "role": "input",
      "dtype": "float",
      "unit": "degC",
      "required": true,
      "allowed_min": 0,
      "allowed_max": 120,
      "description": "Controlled test temperature."
    },
    {
      "table": "model_table.csv",
      "name": "performance_metric",
      "role": "output",
      "dtype": "float",
      "unit": "domain-specific",
      "direction": "maximize",
      "required": true,
      "description": "Target KPI for surrogate modeling."
    }
  ],
  "joins": [],
  "split_hints": {
    "group_key": "experiment_id",
    "time_column": null,
    "recommended_strategy": "grouped | random | time_ordered | predefined_column"
  },
  "ui_config": {
    "test_article_label": "Sample",
    "default_group_by": "experiment_id",
    "default_output": "performance_metric"
  },
  "plot_recipes": []
}
```

Required column roles for MVP:

- `id`: stable row/sample/test identifier.
- `input`: model feature controlled or selected by the user.
- `output`: supervised target predicted by the surrogate.
- `metadata` / `context`: retained for filtering, grouping, diagnostics, and lineage, but not necessarily a model input.
- `group`: split/grouping key such as sample, part, cell, batch, campaign, or station.
- `time` / `cycle` / `sequence`: optional ordering variable.
- `curve_axis`: optional independent axis for curve-like plots.
- `ignore`: uploaded but intentionally excluded.

Required approval behavior:

- A project/session cannot start preprocessing unless every model input/output has approved role, dtype, unit, and bounds/direction where applicable.
- A project/session cannot start training unless preprocessing produced an approved `schema.json`, `preprocessing.json`, split report, and validation report.
- Automated suggestions may assist the user, but they are not authoritative until approved.

## Generic preprocessing target
Add a generic preprocessing engine that works from the approved contract:

- Load manifest/data dictionary and uploaded CSV/XLSX/parquet files.
- Validate required tables and columns.
- Apply joins for supported one-table and simple multi-table cases.
- Build canonical `model_table.csv` with approved input/output/context columns.
- Coerce dtypes and record rejected rows/reasons.
- Apply missing-value policy from metadata or safe defaults.
- Apply split strategy from `split_hints` and approved group/time columns.
- Write canonical artifacts:
  - `schema.json`
  - `preprocessing.json`
  - `model_table.csv`
  - `split_report.json`
  - `dataset_profile.json`
  - `validation_report.json`
  - `rejected_rows.csv`
- Keep PEM-specific raw parser as a template adapter that outputs the same generic canonical artifacts.

## Generic training target
Training should consume only generic artifacts:

- Read `schema.json` for inputs, outputs, units, bounds, and output directions.
- Read `preprocessing.json` for transforms, input/output order, imputation, scaling, and split definitions.
- Train generic tabular candidates where appropriate: baseline, MVLR/Ridge, MLP.
- Log all candidates as MLflow runs.
- Register only the selected candidate under `doe_surrogate_<project_id>`.
- Use schema-derived tags for lineage, inputs, outputs, and validation status.
- Avoid importing PEM constants in the generic trainer.

## Entry point direction
Add generic-first entrypoints:

- `backend/training/entrypoints/validate_manifest.py`
- `backend/training/entrypoints/preprocess_project.py`
- `backend/training/entrypoints/train_project.py`

Keep compatibility/demo entrypoints:

- `build_real_fuel_cell_dataset.py`
- `preprocess_real_fuel_cell.py`
- `train_real_fuel_cell_models.py`

The PEM entrypoints should eventually call the fuel-cell template adapter and then hand off to the same generic preprocessing/training interfaces where possible.

## Steps
- [ ] Tighten the manifest/data-dictionary templates into the required Mirai data contract, including roles, dtype, unit, bounds, direction, split hints, joins, UI labels, and plot recipe hooks.
- [ ] Update Data Intake copy and validation so users understand the Mirai contract is required, not optional guidance.
- [ ] Convert Metadata & Plot Setup into mandatory schema approval: role, unit, dtype, bounds, direction, grouping, split strategy, and plot recipe selection.
- [ ] Add backend validation for manifest/data-dictionary completeness and produce clear blocking errors for missing required metadata.
- [ ] Implement generic contract parser/normalizer under `backend/training/common/`.
- [ ] Implement generic one-table preprocessing from approved metadata.
- [ ] Add simple multi-table preprocessing support for declared joins where feasible; otherwise fail with actionable unsupported-join messages.
- [ ] Generate generic `schema.json`, `preprocessing.json`, `split_report.json`, `dataset_profile.json`, `validation_report.json`, and `rejected_rows.csv` artifacts.
- [ ] Refactor uploaded-project preprocessing to use the generic engine instead of fuel-cell-specific preprocessing when `template_id` is `generic_tabular_doe` or `custom_tabular`.
- [ ] Keep the PEM parser as `template_id=fuel_cell`, but ensure it outputs the same canonical artifacts and metadata contract.
- [ ] Add generic training path that consumes only `schema.json` and `preprocessing.json` rather than PEM constants.
- [ ] Add generic `preprocess_project` and `train_project` entrypoints; keep old fuel-cell wrappers as demo/compatibility commands.
- [ ] Refactor Design Studio plot rendering to use approved `plot_recipes`; keep fuel-cell polarization as the first template recipe.
- [ ] Refactor Model Quality to use generic defaults: parity, residuals vs predicted, residuals by approved grouping variable, metrics by output/split, and optional recipe-driven domain plots.
- [ ] Refactor BO, prediction, recommendation, and exports to use the uploaded project’s approved schema consistently.
- [ ] Make Business Impact generic/template-driven or hide unavailable sections when a project lacks approved business-impact metadata.
- [ ] Add migration/backward compatibility so existing packaged `pem_fuel_cell_demo` and `pem_fuel_cell_real_cathode_degradation` continue working.
- [ ] Add a validation fixture/path that uploads the existing real PEM fuel-cell dataset through the new forced contract and confirms it reproduces the current canonical outputs and model-quality results.
- [ ] Add tests for a non-fuel-cell generic tabular project with arbitrary variable names.
- [ ] Add tests confirming unapproved/incomplete metadata blocks preprocessing/training.

## Verification
- PEM packaged demo still runs end-to-end and shows the fuel-cell plot recipe as a template/demo, not inline UI hardcoding.
- Existing real PEM project still resolves artifacts, Model Quality, Design Studio, BO, prediction, and recommendation flows.
- The existing real PEM fuel-cell data can be uploaded using the new Mirai contract and produces the same canonical schema, preprocessing outputs, split behavior, and model-quality results as the current PEM reference path within accepted numerical tolerances.
- A generic non-fuel-cell tabular upload with arbitrary variable names can proceed through:
  - intake,
  - metadata approval,
  - generic preprocessing,
  - training request,
  - model training,
  - Model Quality,
  - Design Studio,
  - prediction/recommendation.
- A generic upload missing required roles/units/directions/split metadata is blocked with clear review errors.
- Generated artifacts for uploaded projects include approved `schema.json`, `preprocessing.json`, split report, dataset profile, validation report, and rejected rows.
- Frontend build passes.
- Backend API and pipeline tests pass.
- Tests confirm generic trainer does not import PEM project constants.

## User decisions captured
- The platform should not rely on vague inference for arbitrary OEM data.
- Scientists/OEMs should be forced to follow a Mirai-defined manifest/data-dictionary format.
- Users may choose variable names, but must explicitly define I/O roles, metadata, units, directions, bounds, joins, grouping keys, and split hints.
- Metadata & Plot Setup is a good starting point, but it must become stricter and less hardcoded.
- The current PEM project should stay as the end-to-end demo/reference implementation.
- The PEM structure should guide the generic engine, but PEM-specific parsing/preprocessing/training assumptions should not leak into generic downstream flows.
- Entry points should become generic-first, with fuel-cell commands kept as compatibility/demo wrappers.
- Validation should prove that the real PEM fuel-cell data can go through the new forced contract and reproduce the current trusted results.
- MVP file-format support should prioritize what OEM test teams commonly exchange and what our real cell data already resembles: CSV for canonical/model tables and metadata tables, plus XLSX ingestion for data dictionaries/metadata workbooks. Parquet can wait unless needed for scale.
- MVP multi-table support should be allowed only in a constrained Mirai format: declared tables, declared primary keys, declared joins, shared metadata/sample/test tables, and explicit one-to-one or one-to-many relationships. Unsupported free-form relational structures should fail with clear guidance.
- Metadata approval is Mirai-only for now.

## Open questions for implementation planning
None blocking for this plan. Implementation can refine exact accepted tolerances for PEM equivalence tests and the first supported multi-table join patterns.
