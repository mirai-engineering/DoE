# Mirai Data Contract for OEM/Scientist Uploads

This document is owned by the ML lifecycle package because it defines what the offline ingesting/preprocessing/training pipeline accepts.

Runtime data and artifacts still live outside this package, for example:

```text
backend/data-minio/intake/projects/...      # mutable upload/session/training state
backend/mlruns/...                          # local MLflow experiments, run artifacts, and registry state
root data/reference/...                     # local reference/source data
```

Customer separation should remain data/metadata/artifact based. Do **not** create a Python package per customer.

## Core rule

Mirai does **not** train from ambiguous uploaded columns.

OEMs/scientists may use their own variable names, but every generic package must include a Mirai contract that defines what each table and column means.

Required contract files:

```text
mirai_manifest.json
data_dictionary.csv   # preferred for MVP
```

Declared model data tables may be:

```text
.csv
.xlsx
```

## MVP ingestion paths

Mirai currently supports two user-facing ingestion paths.

### 1. Generic Mirai Contract

Use for normal OEM/scientist tabular DoE projects.

Technical template:

```text
generic_tabular_doe
```

Expected package shape is realistic multi-table data, for example:

```text
my_project_upload/
  mirai_manifest.json
  data_dictionary.csv
  cells.csv
  tests.csv
  cycle_metrics.csv
  raw_reference/*.zip      # optional audit/reference files
```

The generic path:

- validates the manifest and data dictionary,
- loads declared CSV/XLSX tables,
- applies explicit constrained joins,
- canonicalizes to `model_table.csv`,
- validates dtypes, required values, units, bounds, and output directions,
- assigns approved splits,
- trains generic tabular surrogate candidates.

Column names may be arbitrary, but roles, units, dtypes, bounds, joins, grouping/split hints, output directions, and optional plot metadata must be explicit.

### 2. Fuell Cell DoE Demo

Use for the pitch/demo PEM fuel-cell package.

Visible UI label:

```text
Fuell Cell DoE Demo
```

Expected package shape:

```text
fuel_cell_demo_upload/
  mirai_manifest.json
  data_dictionary.csv
  data_overview.xlsx
  Cell_01.zip
  Cell_02.zip
  ...
```

This path uses the manifest-declared raw extractor:

```text
pem_cell_zip_bundle
```

The extractor converts `data_overview.xlsx` + `Cell_NN.zip` archives into canonical PEM tables such as `model_table.csv`. The downstream Mirai contract validation/preprocessing/training flow then consumes the generated canonical table.

## Template IDs

For MVP, supported template IDs are:

```text
fuel_cell
generic_tabular_doe
```

`custom_tabular` is intentionally not supported in the MVP.

### `generic_tabular_doe`

Default template for generic OEM/scientist tabular DoE packages.

### `fuel_cell`

PEM-specific demo/template compatibility path. The more user-friendly upload dropdown label is `Fuell Cell DoE Demo`.

## Allowed column roles

Each column must have one of these roles:

```text
id
input
output
metadata
context
group
time
cycle
sequence
curve_axis
ignore
```

| Role | Meaning | Used by model? |
|---|---|---:|
| `id` | Stable row/sample/test identifier | No |
| `input` | Model feature controlled or selected by the user | Yes |
| `output` | Supervised target predicted by the surrogate | Yes |
| `group` | Sample/cell/batch/campaign/station grouping for splits and diagnostics | No |
| `metadata` / `context` | Filtering, lineage, labels, diagnostics | No |
| `time` / `cycle` / `sequence` | Ordered test/cycle/time variable | No by default |
| `curve_axis` | Independent axis for curve-like plots | No by default |
| `ignore` | Uploaded but explicitly excluded | No |

For MVP model training, model `input` and `output` columns should normally be numeric.

## Allowed dtypes

```text
float
int
integer
number
numeric
string
str
category
categorical
bool
boolean
```

## Required output directions

Every `output` must declare one of:

```text
maximize
minimize
target
```

Examples:

```json
{"name": "capacity_retention_pct", "role": "output", "dtype": "float", "unit": "%", "direction": "maximize"}
{"name": "dc_internal_resistance_mohm", "role": "output", "dtype": "float", "unit": "mOhm", "direction": "minimize"}
{"name": "target_viscosity_cp", "role": "output", "dtype": "float", "unit": "cP", "direction": "target"}
```

## Required units and bounds

- Every `input` must declare a unit. Use `unitless` if dimensionless.
- Every `output` must declare a unit. Use `unitless` if dimensionless.
- Numeric inputs should declare `allowed_min` and `allowed_max`.
- Numeric outputs should declare bounds when physically meaningful.

## Generic multi-table example

Example files:

```text
mirai_manifest.json
data_dictionary.csv
cells.csv
tests.csv
cycle_metrics.csv
raw_reference/BATCH_01_cycler_raw_exports.zip
```

Example join pattern:

```text
cells.csv
  one_to_many on cell_id
tests.csv
  one_to_many on test_id
cycle_metrics.csv
```

Manifest join excerpt:

```json
"joins": [
  {"left_table": "cells.csv", "right_table": "tests.csv", "keys": ["cell_id"], "relationship": "one_to_many"},
  {"left_table": "tests.csv", "right_table": "cycle_metrics.csv", "keys": ["test_id"], "relationship": "one_to_many"}
]
```

Allowed relationship values:

```text
one_to_one
one_to_many
many_to_one
```

Not supported in MVP:

- free-form relational schemas,
- many-to-many joins,
- undeclared join keys,
- ambiguous table relationships.

## Raw/reference ZIP files

Generic packages may declare raw/reference archives, for example:

```json
"raw_reference_files": {
  "archive_globs": ["raw_reference/*.zip"]
}
```

For the generic path, these ZIPs are extracted/inventoried for auditability only. Generic training still consumes declared CSV/XLSX tables.

For the Fuell Cell DoE Demo path, `pem_cell_zip_bundle` is different: it is an explicit raw extractor that parses `data_overview.xlsx` + `Cell_NN.zip` files and generates `model_table.csv`.

## What preprocessing creates

After the contract is validated and approved, generic preprocessing writes:

```text
canonical/model_table.csv
canonical/rejected_rows.csv
canonical/dataset_profile.json
canonical/validation_report.json
canonical/raw_reference_inventory.json
canonical/raw_extractor_report.json
training_artifacts/latest/schema.json
training_artifacts/latest/preprocessing.json
training_artifacts/latest/split_report.json
training_artifacts/latest/dataset_profile.json
training_artifacts/latest/validation_report.json
training_artifacts/latest/eda_report.json
training_artifacts/latest/raw_reference_inventory.json
training_artifacts/latest/raw_extractor_report.json
```

Training consumes only approved canonical/model artifacts, especially:

```text
schema.json
preprocessing.json
model_table.csv
```

## Approval rule

For now, contract approval is Mirai-admin-only.

A project cannot proceed to training until:

1. manifest and data dictionary are present,
2. required roles/dtypes/units/bounds/directions are complete,
3. joins and split hints are valid,
4. Metadata & Plot Setup is approved,
5. preprocessing artifacts are approved.

## Example packages in this repo

Generic battery-cycling contract demo:

```text
data/generic-battery-cycling-schema/
```

Fuell Cell DoE Demo raw-bundle contract demo:

```text
data/generic-fc-schema/
```
