# ML Lifecycle Ingestion Refactor Plan

## Context

Mirai currently keeps offline ingestion, preprocessing, training, export, and MLflow utilities under `backend/training/`. That name is too narrow for the actual responsibility: this package owns the offline **ML lifecycle**, including intake adapters, canonicalization, preprocessing, training, evaluation, registration, and export.

The current code also blurs two ingestion modes:

1. **Generic Mirai contract ingestion** — customer/OEM data described by `mirai_manifest.json` + `data_dictionary.csv` + declared multi-table CSV/XLSX files.
2. **Fuel Cell DoE Demo ingestion** — pitch/demo path for real PEM fuel-cell data using `mirai_manifest.json`, `data_dictionary.csv`, `data_overview.xlsx`, and `Cell_NN.zip` archives through the declared `pem_cell_zip_bundle` extractor.

For the MVP, `custom_tabular` adds ambiguity without clear value. The generic path should use one template only:

```text
generic_tabular_doe
```

The first phase should be a cleanup/ordering refactor, not new data generation. The goal is to make the Python lifecycle package structure obvious before continuing with synthetic battery-cycling data or richer intake UX.

## Approach

Rename/refactor `backend/training/` into a clearly named ML lifecycle area and make **ingesting** versus **training** responsibilities explicit. Because Python import packages cannot contain hyphens, use a Python-safe package directory while documenting it as the **ML lifecycle** package:

```text
backend/ml_lifecycle/
  ingesting/
    generic_tabular_doe/
      contract.py
      canonicalize.py
      preprocessing.py
    fuel_cell_doe_demo/
      ingest.py
      preprocess.py
      schema.py
    extractors/
      pem_cell_zip_bundle.py
  training/
    generic_tabular_doe/
      train.py
    fuel_cell_doe_demo/
      train.py
      export_onnx.py
      mlflow.py
    common/
      model_definitions.py
  entrypoints/
    validate_manifest.py
    preprocess_project.py
    train_project.py
    ...
```

Notes:

- Treat this as a real rename/refactor from `training` to `ml_lifecycle`, not just adding another wrapper package.
- The old `backend/training/` shim has been moved outside `backend/` to `legacy/backend_training_compat/`; target state is that production imports and docs use `ml_lifecycle`.
- Make customer/project identity data-driven through manifest metadata and artifact/data folders, not through new Python subpackages per customer.
- Keep `fuel_cell_doe_demo` as a first-party adapter/demo under the lifecycle engine, not as the pattern for every customer.
- Delete `custom_tabular` from MVP-supported templates and route all generic contract packages through `generic_tabular_doe` only.

## Files to modify

Primary package refactor:

- `backend/training/**` → renamed/refactored `backend/ml_lifecycle/**`
- `backend/training/common/contract.py` → `backend/ml_lifecycle/ingesting/generic_tabular_doe/contract.py`
- `backend/training/common/preprocessing.py` → `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py`
- `backend/training/common/train.py` → `backend/ml_lifecycle/training/generic_tabular_doe/train.py`
- `backend/training/projects/pem_fuel_cell/ingest.py`, `preprocess.py`, `schema.py` → `backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/`
- `backend/training/projects/pem_fuel_cell/train.py`, `export_onnx.py`, `mlflow.py` → `backend/ml_lifecycle/training/fuel_cell_doe_demo/`
- `backend/training/entrypoints/*` → `backend/ml_lifecycle/entrypoints/*`

Compatibility/import updates:

- `backend/app/services/preprocessing_review.py`
- `backend/app/services/domain_metadata.py`
- `backend/tests/test_api.py`
- `backend/tests/test_generic_contract_pipeline.py`
- `backend/tests/test_real_fuel_cell_data_pipeline.py`
- root/backcompat wrapper files in `backend/training/*.py`

Documentation/UI follow-up references:

- `backend/training/README.md` → move/rewrite as `backend/ml_lifecycle/README.md`
- `docs/tutorials/MIRAI_CONTRACT_INTAKE_TO_TRAINING_FLOW.md`
- `data/generic-fc-schema/README.md`
- `frontend/src/components/DataIntakePage.tsx` later, after backend structure stabilizes

## Reuse

Existing reusable pieces to preserve rather than rewrite:

- Generic contract validation: `backend/training/common/contract.py`
- Generic preprocessing: `backend/training/common/preprocessing.py`
- Generic training: `backend/training/common/train.py`
- PEM raw parser/canonical builder: `backend/training/projects/pem_fuel_cell/ingest.py`
- PEM preprocessing: `backend/training/projects/pem_fuel_cell/preprocess.py`
- PEM training/export/MLflow utilities: `backend/training/projects/pem_fuel_cell/train.py`, `export_onnx.py`, `mlflow.py`
- App intake orchestration/status handling: `backend/app/services/preprocessing_review.py`
- Existing data/artifact separation:
  - `backend/data/intake/projects/...`
  - `backend/data-minio/runtime-projects/...`
  - `backend/data/real/...`

## Steps

### Phase A — Cleanup and ordering refactor

- [ ] Rename/refactor `backend/training/` into `backend/ml_lifecycle/` with explicit `ingesting/`, `training/`, `entrypoints/`, and compatibility-safe `__init__.py` files.
- [ ] Move generic contract/canonicalization/preprocessing code into `backend/ml_lifecycle/ingesting/generic_tabular_doe/`.
- [ ] Move generic model fitting/evaluation code into `backend/ml_lifecycle/training/generic_tabular_doe/`.
- [ ] Move PEM demo ingest/preprocess/schema code into `backend/ml_lifecycle/ingesting/fuel_cell_doe_demo/`.
- [ ] Move PEM demo train/export/MLflow code into `backend/ml_lifecycle/training/fuel_cell_doe_demo/`.
- [ ] Move `pem_cell_zip_bundle` raw extractor logic into `backend/ml_lifecycle/ingesting/extractors/pem_cell_zip_bundle.py`.
- [x] Move the old `backend/training/` shim outside `backend/` once imports/tests/docs use `ml_lifecycle`.
- [ ] Update app imports to use `ml_lifecycle.*` while preserving public API routes.
- [ ] Collapse MVP template support to `generic_tabular_doe` plus the separate Fuell Cell DoE Demo ingestion mode; delete `custom_tabular` from validation/UI copy/tests.
- [ ] Update docs to describe two ingestion paths:
  - `Generic Mirai Contract` → `generic_tabular_doe`
  - `Fuell Cell DoE Demo` → declared `pem_cell_zip_bundle` extractor
- [ ] Ensure no new Python package/subfolder is required per customer; customer separation remains manifest/project metadata plus data/artifact storage.

### Phase B — Post-refactor intake UX and data package work

- [ ] Add UI upload dropdown with user-friendly ingestion-path labels, including `Fuell Cell DoE Demo` and `Generic Mirai Contract`.
- [ ] Wire dropdown selection to backend validation/preprocessing route selection without renaming public API routes unless explicitly approved.
- [x] Later, create a realistic **multi-table battery-cycling** synthetic package following the enforced `generic_tabular_doe` contract.
- [x] Include raw/reference ZIP files in the battery-cycling package, but do not implement this data generation in Phase A.

## Verification

Run backend tests after the package migration:

```bash
cd backend
uv run pytest tests/test_api.py tests/test_real_fuel_cell_data_pipeline.py tests/test_generic_contract_pipeline.py -q
```

Run representative CLI entrypoints through compatibility wrappers and new package paths:

```bash
cd backend
uv run python training/entrypoints/preprocess_project.py --help
uv run python training/entrypoints/train_project.py --help
uv run python -m ml_lifecycle.entrypoints.preprocess_project --help
uv run python -m ml_lifecycle.entrypoints.train_project --help
```

Validate the realistic Fuel Cell DoE Demo raw-bundle path without `model_table.csv`:

```bash
rm -rf /tmp/generic-fc-raw-upload /tmp/mirai-generic-fc-raw-test
mkdir -p /tmp/generic-fc-raw-upload
cp data/generic-fc-schema/mirai_manifest.json \
   data/generic-fc-schema/data_dictionary.csv \
   data/generic-fc-schema/data_overview.xlsx \
   /tmp/generic-fc-raw-upload/
cp data/generic-fc-schema/cell_data/Cell_*.zip /tmp/generic-fc-raw-upload/

cd backend
uv run python -m ml_lifecycle.entrypoints.preprocess_project \
  --project-id generic_fc_schema_raw \
  --raw-root /tmp/generic-fc-raw-upload \
  --canonical-dir /tmp/mirai-generic-fc-raw-test/canonical \
  --artifact-dir /tmp/mirai-generic-fc-raw-test/artifacts
```

Run frontend build after UI copy/selection changes in Phase B:

```bash
cd frontend
npm run build
```

## Decisions captured

- `backend/training/` should be renamed/refactored into the ML lifecycle package; compatibility wrappers are temporary only if needed during migration.
- `custom_tabular` should be deleted from MVP support rather than kept as an alias.
- The upload dropdown label should be exactly `Fuell Cell DoE Demo`.
