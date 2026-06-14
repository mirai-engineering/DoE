# Fixed Mirai Multi-table Contract Implementation Plan

## Goal
Define and implement a fixed Mirai intake contract where uploaded projects use a stable relational CSV package that Mirai deterministically transforms into `model_table.csv` for generic training.

## Contract decision
A Mirai package should be structured around these fixed root files:

```text
mirai_manifest.json
experiments.csv
conditions.csv
results.csv
data_dictionary.csv
```

`model_table.csv` is the generated canonical training surface. For transitional compatibility, packages may also include `model_table.csv`, but the preferred path is to materialize it from the fixed source tables.

## Fixed tables

### `experiments.csv`
One row per physical sample/test article/experiment.

Required generic columns:
- `experiment_id` string primary key

Optional recommended columns:
- `campaign_id`
- `group_id`
- `sample_id`
- source/provenance columns

### `conditions.csv`
One row per modelable condition/operating point for an experiment.

Required generic columns:
- `condition_id` string primary key
- `experiment_id` foreign key to `experiments.csv`

This table contains input columns such as formulation, process, operating, or degradation settings.

### `results.csv`
One row per measured/averaged result for a condition.

Required generic columns:
- `result_id` string primary key, or enough keys for uniqueness
- `condition_id` foreign key to `conditions.csv`

This table contains output columns/KPIs.

### `data_dictionary.csv`
Declares every model-relevant column, including table, role, dtype, unit, required flag, bounds, direction, and labels.

### `mirai_manifest.json`
Declares project metadata, fixed tables, joins, split hints, UI config, plot recipes, and optional raw reference inventory configuration.

## Implementation tasks

### Task 1: Rewrite tutorial to start with the fixed contract
- Move the contract definition to the top of `docs/tutorials/MULTI_TABLE_TO_MODEL_TABLE_MAPPING.md`.
- Explicitly state accepted root tables and generic naming rules.
- Distinguish source tables from generated `model_table.csv`.

### Task 2: Update public templates to mirror the fixed contract
- Update `frontend/public/templates/mirai_manifest_multitable_template.json`.
- Update `frontend/public/templates/data_dictionary_multitable_example.csv`.
- Ensure examples use `experiments.csv`, `conditions.csv`, `results.csv` and generic keys.

### Task 3: Make backend contract validation enforce the fixed multi-table package
- Teach `contract.py` that packages can be either:
  - generated-model-table package: fixed source tables without `model_table.csv`; or
  - compatibility package: existing `model_table.csv` package.
- Enforce required fixed source table names and required keys when `model_table.csv` is absent.
- Keep `generic_tabular_doe` as the only lifecycle.

### Task 4: Materialize `model_table.csv` from fixed source tables
- Update preprocessing so fixed multi-table packages join:
  - `experiments.csv` → `conditions.csv` on `experiment_id`
  - joined frame → `results.csv` on `condition_id`
- Select columns from `data_dictionary.csv`/manifest roles.
- Write generated canonical `model_table.csv` to canonical artifacts.

### Task 5: Add Fraunhofer fixed-contract fixture
- Add a tiny synthetic Fraunhofer-shaped fixture under backend tests.
- Include `experiments.csv`, `conditions.csv`, `results.csv`, `data_dictionary.csv`, and `mirai_manifest.json`.
- Do not add large raw data or gitignored datasets.

### Task 6: Add tests
- Test fixed multi-table validation.
- Test materialized `model_table.csv` has expected joined rows and input/output columns.
- Test ZIP package upload path works with fixed multi-table package.

### Task 7: Validate app path
- Run backend focused tests.
- Run full backend tests if feasible.
- Run frontend build.

## Verification commands

```bash
cd backend && uv run pytest tests/test_generic_contract_pipeline.py tests/test_api.py -q
cd backend && uv run pytest -q
cd frontend && npm run build
```

## Out of scope for this iteration
- Uploading the full 930 MB raw Fraunhofer folder directly.
- Runtime extraction of all `Cell_NN.zip` raw traces.
- Client-specific fuzzy column-name inference.
- Production signed-in Railway validation.
