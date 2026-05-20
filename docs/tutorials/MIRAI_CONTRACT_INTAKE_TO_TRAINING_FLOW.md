# Mirai Contract Intake to Training Flow

This tutorial explains the forced-schema workflow for OEM/scientist data packages.

## MVP ingestion paths

Mirai now exposes two user-facing intake paths:

1. **Generic Mirai Contract** — the default OEM/scientist road using `template_id=generic_tabular_doe`, `mirai_manifest.json`, `data_dictionary.csv`, and approved multi-table CSV/XLSX data.
2. **Fuell Cell DoE Demo** — the pitch/demo PEM road using `mirai_manifest.json`, `data_dictionary.csv`, `data_overview.xlsx`, and `Cell_NN.zip` archives through the declared `pem_cell_zip_bundle` extractor.

The MVP has one generic template: `generic_tabular_doe`.

## 1. Start with the Mirai contract

Mirai does not train from ambiguous uploaded columns. Every upload must include:

- `mirai_manifest_*.json`
- `data_dictionary_*.csv` or XLSX
- the declared data table files, usually multi-table CSV/XLSX for generic projects

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
- optional UI labels and plot recipe hooks

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

If the package lacks a manifest or data dictionary, the session is blocked as:

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
2. Loads the declared CSV/XLSX tables.
3. Applies constrained declared joins if needed.
4. Builds canonical `model_table.csv`.
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
training_artifacts/latest/schema.json
training_artifacts/latest/preprocessing.json
training_artifacts/latest/split_report.json
training_artifacts/latest/dataset_profile.json
training_artifacts/latest/validation_report.json
training_artifacts/latest/eda_report.json
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
