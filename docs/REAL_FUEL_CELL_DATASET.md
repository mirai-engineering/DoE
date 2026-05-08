# Real Fuel Cell Dataset Pipeline

This document describes the Phase 1 real-data transformation for the PEM fuel-cell cathode catalyst degradation dataset.

## Scope

Phase 1 processes **only `Cell_01`** from:

```text
data/Cathode Catalyst Degradation/01-Data/Cell_01/
```

The root `data/` folder is treated as **local-only raw data** for now. Generated audited derivatives are written under:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/
```

No model training, ONNX export, replay split, or production project artifact is created in Phase 1.

## What `Cell_01` Means

A local `Cell_NN` is one tested CCM / fuel-cell sample, corresponding to one `Test no.` row in `data_overview.xlsx`. It is not one component in a stacked fuel cell. `Cell_01` maps to workbook test number `1` and has one sample-level catalyst-layer/AST configuration plus many measurement files collected during the test protocol.

## Paper-Aligned Schema

The validation table follows the paper's seven-input / four-output ANN framing.

Inputs:

```text
pt_c_ratio
i_c_ratio
ionomer_ew
operating_rh
operating_voltage
ast_rh
ast_upl
```

Outputs:

```text
bol_current_density
eol_current_density
bol_ecsa
ecsa_loss
```

Synthetic-only outputs are intentionally excluded:

```text
durability_score
cost_score
```

If later source review identifies exact paper figure labels that differ from these working names, the CSV columns should be renamed to match the paper labels verbatim.

## Generated Files

```text
inventory_manifest.csv        # one row per discovered Cell_01 source file
dataset_profile.json          # run profile, row counts, labels, and phase scope
cell_metadata.csv             # one row from data_overview.xlsx for Cell_01
polarization_long.csv         # raw + IR-corrected IV curve points, kept separate
ecsa_by_cycle.csv             # CV-derived ECSA/C_DL summaries by cycle
model_table.csv               # paper-aligned model-ready Cell_01 rows
rejected_rows.csv             # rows excluded from model_table with reasons
eis_h2n2_summary.csv          # H2/N2 EIS scalar summaries
eis_h2air_long.csv            # H2/Air EIS spectra rows
limiting_current_summary.csv  # limiting-current rows plus resistance summaries
lsv_summary.csv               # LSV crossover-current summary
ast_trace_manifest.csv        # AST trace file profile
```

## Transformation Rules

- Use raw `IV_data.csv` for current-density targets.
- Keep `IV_data_IR_corr.csv` for QA only; do not mix it into model targets.
- Use measured BoL voltages and interpolate EoL current density only inside the EoL voltage overlap.
- Reject, rather than extrapolate, out-of-overlap voltages.
- Reject negative current-density model rows and record them in `rejected_rows.csv`.
- Compute `ecsa_loss = (ECSA_0cycles - ECSA_30000cycles) / ECSA_0cycles`.
- Preserve source-file and source-row provenance in the audited outputs.

## Command

From `backend/`:

```bash
uv run python training/build_real_fuel_cell_dataset.py --cell-id Cell_01 --profile
```

Dry run:

```bash
uv run python training/build_real_fuel_cell_dataset.py --cell-id Cell_01 --dry-run --profile
```

## Current Phase 1 Row Counts

As generated locally:

```text
inventory_manifest.csv: 194
cell_metadata.csv: 1
polarization_long.csv: 320
ecsa_by_cycle.csv: 9
model_table.csv: 57
rejected_rows.csv: 9
eis_h2n2_summary.csv: 18
eis_h2air_long.csv: 984
limiting_current_summary.csv: 32
lsv_summary.csv: 2
ast_trace_manifest.csv: 10
```
