# Mirai Contract Intake to Training Flow

This tutorial explains the forced-schema workflow for OEM/scientist data packages.

## MVP ingestion path

Mirai exposes one user-facing intake path: **Mirai Experiment Package**.

The same `generic_tabular_doe` lifecycle is used for fuel cells, batteries, materials, process engineering, and other tabular engineering projects. Domain meaning lives in the manifest, data dictionary, and table columns; it is not selected by a separate upload mode.

## 1. Start with the Mirai contract

Mirai does not train from ambiguous uploaded columns. Every upload must include:

- `mirai_manifest.json`
- `data_dictionary.csv`
- fixed source tables `experiments.csv`, `conditions.csv`, and `results.csv`, from which Mirai materializes `model_table.csv`
- transitional compatibility for packages that already include `model_table.csv`

Users may name variables however they want, but they must define what each variable means.

Required metadata includes:

- role: `id`, `input`, `output`, `group`, `metadata`, `time`, `curve_axis`, or `ignore`
- dtype: `float`, `int`, `string`, `categorical`, `bool`
- unit, using `unitless` if dimensionless
- required/not required
- allowed min/max for model inputs/outputs where applicable
- output direction: `maximize`, `minimize`, or `target`
- split hints such as group key, time column, predefined split column, validation fraction, holdout fraction
- declared joins for constrained multi-table packages
- source-name-to-variable-id mappings: `source_name`, immutable `variable_id`, and editable `ui_label`; for new fixed source-table packages, input/output `variable_id`s are contiguous generic IDs (`x1..xN`, `y1..yM`)
- optional plot recipe hooks

Templates live in:

```text
frontend/public/templates/mirai_manifest_template.json
frontend/public/templates/mirai_manifest_multitable_template.json
frontend/public/templates/data_dictionary_template.csv
frontend/public/templates/data_dictionary_multitable_example.csv
```

## 2. Upload through Data Intake

In the app, open **Data Intake** and upload the package.

The backend stores the files under a session folder, inventories them, and checks whether the required Mirai contract files exist.

If the package lacks the required contract/model-table files, the session is blocked as:

```text
blocked_missing_mirai_contract
```

It cannot proceed to preprocessing.

## 3. Metadata & Plot Setup approval

The manifest/data dictionary become the source of truth for the project schema. Mirai admins review and approve:

- input/output selection
- units
- dtypes
- bounds
- output directions
- grouping/split variables
- joins
- default Model Quality grouping
- plot recipes

For now, approval is **Mirai-only**.

Automated suggestions may exist later, but they are not authoritative until approved.

## 4. Generic preprocessing

For MVP `template_id=generic_tabular_doe`, the generic preprocessing engine:

1. Parses and validates the contract.
2. Loads fixed source tables or a transitional `model_table.csv` package.
3. Applies constrained declared joins if needed.
4. Selects declared `source_name` columns and writes canonical `model_table.csv` with internal `variable_id` columns (`xN`/`yN` for model inputs/outputs in new fixed packages).
5. Coerces dtypes.
6. Rejects rows with missing required values or bounds violations.
7. Assigns splits from approved split hints.
8. Writes canonical artifacts.

Generated artifacts include:

```text
canonical/model_table.csv
canonical/rejected_rows.csv
canonical/dataset_profile.json
canonical/validation_report.json
canonical/package_inventory.json
training_artifacts/latest/schema.json
training_artifacts/latest/preprocessing.json
training_artifacts/latest/split_report.json
training_artifacts/latest/dataset_profile.json
training_artifacts/latest/validation_report.json
training_artifacts/latest/eda_report.json
training_artifacts/latest/package_inventory.json
```

## 5. Training request

After Metadata & Plot Setup and preprocessing are approved, a Mirai admin creates a training request.

Generic training consumes only:

```text
schema.json
preprocessing.json
model_table.csv
```

It does not import PEM/fuel-cell constants.

The MVP generic trainer fits baseline/linear/Ridge/MLP tabular candidates and writes:

```text
training_artifacts/latest/metrics_summary.json
training_artifacts/latest/metadata.json
training_artifacts/latest/models/*.joblib
```

The PEM fuel-cell project remains available as the `fuel_cell` template/demo path, but the generic path is now contract-driven.

## 6. Downstream contract use

Downstream pages should use the approved schema and metadata consistently:

- Design Studio controls from `schema.inputs`
- objective/output controls from `schema.outputs`
- Model Quality diagnostics from generic defaults and approved grouping variables
- domain plots from approved `plot_recipes`
- prediction/recommendation/export behavior from the uploaded project schema

## Validation strategy

The real PEM fuel-cell dataset remains the reference structure. The long-term validation target is:

1. Package the real PEM data using the forced Mirai contract.
2. Upload it through Data Intake.
3. Approve metadata.
4. Run preprocessing/training.
5. Confirm canonical artifacts, splits, and Model Quality results reproduce the current trusted PEM workflow within accepted tolerances.
