# Mirai Data Contract

## Decision

Mirai has exactly one runtime data-intake lifecycle: `generic_tabular_doe`.

Fuel cells, batteries, materials, process engineering, and other engineering tabular projects all enter the same path:

1. upload a Mirai Experiment Package;
2. validate `mirai_manifest.json`, `data_dictionary.csv`, and the canonical fitting table;
3. build canonical preprocessing artifacts;
4. approve the contract/preprocessing report;
5. train with the generic tabular training service;
6. persist runtime pointers in Postgres and heavy artifacts in S3/MLflow.

The Fraunhofer fuel-cell demo is an example dataset reshaped into this generic package structure. It is not a separate user-facing upload mode, lifecycle, runtime processor, or training path.

## Required MVP package shape

A valid MVP package is a folder, or a ZIP containing the same folder structure:

```text
mirai_package/
  mirai_manifest.json
  data_dictionary.csv
  model_table.csv
  metadata/                  # optional, declared only when needed
    runs.csv
    samples.csv
  raw_reference/             # optional audit/source files, not used for fitting
```

`model_table.csv` is the preferred and required MVP fitting surface. It has one row per ML training example and contains all selected input/output columns needed for fitting, plus any traceability IDs, split/group columns, and metadata columns declared by the manifest.

ZIP uploads are package containers only. After safe extraction, the same `mirai_manifest.json`, `data_dictionary.csv`, and `model_table.csv` paths must exist. The core intake path does not infer domain semantics from archive names or folder structure.

## Manifest responsibilities

`mirai_manifest.json` must declare:

- `manifest_version`;
- project identity/display metadata;
- `template_id: "generic_tabular_doe"`;
- tables, including `model_table.csv`;
- every column used by preprocessing/training;
- roles: `id`, `input`, `output`, `metadata`, `context`, `group`, `time`, `cycle`, `sequence`, `curve_axis`, or `ignore`;
- dtypes;
- units for all input/output columns, using `unitless` when dimensionless;
- required flags;
- numeric bounds where known;
- output directions: `maximize`, `minimize`, or `target`;
- split hints, including predefined split columns or group columns when required;
- optional deterministic joins for overview/metadata tables.

Free-form folder crawling, domain-specific filename assumptions, and automatic semantic inference are not part of the runtime contract.

## Data dictionary responsibilities

`data_dictionary.csv` is the compact review surface for variables. It must match the manifest columns and provide column-level mapping/role/dtype/unit/bounds/direction metadata. Mirai admins review and approve this semantic mapping before preprocessing/training.

Required dictionary mapping fields for new fixed source-table packages:

| Field | Meaning |
| --- | --- |
| `source_name` | Exact column name in the uploaded source CSV, including spaces/symbols/client wording. |
| `variable_id` | Stable machine-safe Mirai internal id used in generated `model_table.csv`, schema, training, predictions, and APIs. For new fixed source-table packages, model inputs must be contiguous `x1..xN` and outputs must be contiguous `y1..yM`. Required for new packages. |
| `ui_label` | Human-facing display label. This can be edited/approved in the app without changing `variable_id`. |
| `role` | `id`, `input`, `output`, `metadata`, `group`, `ignore`, etc. Only `input` and `output` are model features/targets. |
| `dtype`, `unit`, `required`, `allowed_min`, `allowed_max`, `direction`, `description`, `join_key`, `split_hint`, `plot_role` | Validation, review, plotting, and optimization metadata. |

Mirai has three naming layers:

1. **Source column name**: client-native raw CSV column, e.g. `Pt/C ratio (%)`.
2. **Internal variable id**: immutable model/API column, e.g. `x1` for the first input or `y1` for the first output.
3. **UI display label**: curated app label, e.g. `Pt/C ratio`.

Training consumes internal `variable_id` columns only. Source names remain provenance. UI labels can be curated during review and persisted in schema/domain metadata. Domain names such as `Pt/C ratio` belong in `source_name`, `ui_label`, unit, and description fields — not in model input/output `variable_id`s for new fixed packages.

## Optional overview and metadata tables

Engineering teams may provide the fixed Mirai source tables (`experiments.csv`, `conditions.csv`, `results.csv`) when they improve traceability. Mirai deterministically joins those tables by `experiment_id` and `condition_id`, then materializes canonical `model_table.csv` by selecting declared `source_name` columns and renaming them to `variable_id`. Metadata/group/id variables are carried for traceability but excluded from training unless their role is `input` or `output`.

For MVP reliability, customer/source workbooks and large run folders should be prepared into `model_table.csv` before runtime upload. Raw source files can be stored as audit/reference material, but they are not required for upload success and are not consumed by training unless their contents are already represented in `model_table.csv`.

## Fraunhofer fuel-cell demo as a generic package

The Fraunhofer package uses normal generic variables. Example input `variable_id`s are:

- `x1`
- `x2`
- `x3`
- `x4`
- `x5`
- `x6`
- `x7`

Their UI/source metadata can still display `Pt/C ratio`, `I/C ratio`, `Operating voltage`, etc. Example output `variable_id`s are:

- `y1`
- `eol_current_density`
- `bol_ecsa`
- `ecsa_loss`

Those variables are represented in `data_dictionary.csv` and `mirai_manifest.json` exactly like any future battery/materials/process dataset variables. Fuel-cell source workbooks, ZIPs, and folders are reference/audit inputs only for runtime upload; the runtime package succeeds based on the generic contract files and canonical `model_table.csv`.

## Runtime architecture

Railway runtime state uses:

- Postgres for workspaces, projects, datasets, schema manifests, training runs, models, and artifact object pointers;
- S3 buckets for durable heavy artifacts under workspace/project/training-run prefixes;
- MLflow for run/model metadata and model artifacts;
- FastAPI endpoints scoped by verified Clerk JWT `workspace_id`.

S3 object presence alone is not enough for UI visibility. Postgres pointers must exist and match actual S3 keys.

## Canonical artifacts

Generic preprocessing writes neutral artifact names such as:

- `canonical/model_table.csv`
- `canonical/rejected_rows.csv`
- `canonical/dataset_profile.json`
- `canonical/validation_report.json`
- `canonical/package_inventory.json`
- `training_artifacts/latest/schema.json`
- `training_artifacts/latest/preprocessing.json`
- `training_artifacts/latest/split_report.json`
- `training_artifacts/latest/validation_report.json`
- `training_artifacts/latest/dataset_profile.json`
- `training_artifacts/latest/eda_report.json`
- `training_artifacts/latest/package_inventory.json`

There is no separate runtime fuel-cell preprocessing or training artifact namespace for generic contract sessions.
