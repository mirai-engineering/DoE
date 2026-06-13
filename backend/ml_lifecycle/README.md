# ML lifecycle package layout

`backend/ml_lifecycle/` is Mirai's offline ML lifecycle package. It is intentionally separate from `backend/app/`, which is the online FastAPI serving/control-plane application.

```text
backend/app/           = API serving, inference, recommendations, status/control plane
backend/ml_lifecycle/  = ingesting, canonicalization, preprocessing, training, evaluation, export, MLflow
```

## Current organization

```text
backend/ml_lifecycle/
  ingesting/
    generic_tabular_doe/
      contract.py          # Mirai manifest/data-dictionary validation
      preprocessing.py     # canonical tables, validation reports, splits, preprocessing artifacts
    fuel_cell_doe_demo/
      schema.py            # PEM demo constants/schema
      ingest.py            # PEM audited canonical builders
      preprocess.py        # PEM grouped split/preprocessing artifacts
    extractors/
      pem_cell_zip_bundle.py # data_overview.xlsx + Cell_NN.zip -> model_table.csv

  training/
    generic_tabular_doe/
      train.py             # generic sklearn surrogate candidates/evaluation
    fuel_cell_doe_demo/
      train.py             # PEM demo candidate training/evaluation
      export_onnx.py       # ONNX export and verification helpers
      mlflow.py            # MLflow setup, aliases, version metadata
    common/
      model_definitions.py # shared model classes, e.g. TabularMLP

  entrypoints/
    validate_manifest.py
    preprocess_project.py
    train_project.py
    build_real_fuel_cell_dataset.py
    preprocess_real_fuel_cell.py
    train_real_fuel_cell_models.py
```

The old `backend/training/` package has been moved out of `backend/` to `legacy/backend_training_compat/` so backend runtime code cannot accidentally import it. New code must import from `ml_lifecycle.*`.

## MVP ingestion paths

### Generic Mirai Contract

Use `template_id=generic_tabular_doe` with:

```text
mirai_manifest.json
data_dictionary.csv
approved multi-table CSV/XLSX files
```

Column names may be customer-specific, but roles, dtypes, units, bounds, joins, grouping/split hints, output directions, and UI metadata must be explicit in the contract.

### Fuell Cell DoE Demo

Use the pitch/demo package with:

```text
mirai_manifest.json
data_dictionary.csv
data_overview.xlsx
Cell_01.zip ... Cell_NN.zip
```

The manifest declares the `pem_cell_zip_bundle` raw extractor. That extractor builds the canonical `model_table.csv`; the generic contract/preprocessing/training flow then validates and consumes the canonical table.

## Customer/project separation

Do not create a Python subpackage per customer. Customer separation belongs in:

- manifest/project metadata
- Railway Postgres rows and workspace-scoped Railway object keys in production/demo
- ignored `backend/.object-storage-local/...` mirrors/caches for local development
- `backend/mlruns/...` only for local MLflow file-store fallback/cache

The Python lifecycle package should stay reusable across projects.
