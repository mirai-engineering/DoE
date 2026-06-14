# ML lifecycle package layout

`backend/ml_lifecycle/` is Mirai's offline ML lifecycle package. It is intentionally separate from `backend/app/`, which is the online FastAPI serving/control-plane application.

```text
backend/app/           = API serving, inference, recommendations, status/control plane
backend/ml_lifecycle/  = contract validation, canonicalization, preprocessing, training, evaluation, export, MLflow
```

## Runtime lifecycle

Mirai has one runtime intake/training lifecycle: `generic_tabular_doe`.

All projects — fuel cells, batteries, materials, process engineering, and other tabular engineering datasets — upload the same Mirai Experiment Package:

```text
mirai_manifest.json
data_dictionary.csv
model_table.csv
metadata/        # optional, declared with deterministic joins
raw_reference/   # optional audit/source material only
```

`model_table.csv` is the ML fitting surface: one row per training example with selected inputs, outputs, split/group columns, and traceability IDs. ZIP uploads are only generic package containers; after safe extraction the same files must exist.

## Current organization

```text
backend/ml_lifecycle/
  ingesting/
    generic_tabular_doe/
      contract.py          # Mirai manifest/data-dictionary/model_table validation
      preprocessing.py     # canonical tables, validation reports, splits, preprocessing artifacts
    fuel_cell_doe_demo/    # historical/offline fuel-cell migration/reference scripts
    extractors/            # historical helpers; not a runtime lifecycle selector

  training/
    generic_tabular_doe/
      train.py             # generic sklearn surrogate candidates/evaluation/MLflow
    fuel_cell_doe_demo/    # historical fuel-cell-specific training reference only
    common/
      model_definitions.py # shared model classes, e.g. TabularMLP

  entrypoints/
    validate_manifest.py
    preprocess_project.py
    train_project.py
```

Runtime services must use `generic_tabular_doe` validation, preprocessing, and training. Any remaining `fuel_cell_doe_demo` code is retained only for historical/offline migration or reference until it can be removed.

## Customer/project separation

Do not create a Python subpackage per customer. Customer separation belongs in:

- manifest/project metadata;
- Railway Postgres rows and workspace-scoped Railway object keys in production/demo;
- ignored `backend/.object-storage-local/...` mirrors/caches for local development;
- `backend/mlruns/...` only for local MLflow file-store fallback/cache.

The Python lifecycle package should stay reusable across projects.
