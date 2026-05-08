# Real Fuel Cell Data Transformation Plan

## Purpose

Move Mirai DoE from the synthetic PEM fuel-cell demo data toward the real cathode catalyst degradation dataset now placed under `data/`. This plan describes how to inventory the scattered zip/CSV/XLSX/PDF assets, transform them into canonical tabular files, and produce the model/replay format required by the existing DoE engine without silently changing units, feature order, or scientific meaning.

This is a planning document only. Do not modify backend/frontend code or train a new model from this file without a separately approved implementation step.

## Review-Ready Summary

### Context

The synthetic `pem_fuel_cell_demo` data is no longer sufficient for validation. The next goal is to prove the data pipeline against real published fuel-cell catalyst degradation data, starting with `Cell_01` only.

### Approach

Build a staged, auditable transformation path from `Cell_01` raw CSV/workbook/PDF context into a paper-aligned model table. Keep the synthetic demo untouched. Match the paper's seven inputs and four outputs rather than the synthetic demo's simplified 5-output schema.

### Files to modify in a later implementation

- `backend/training/build_real_fuel_cell_dataset.py`
- `backend/training/real_fuel_cell_schema.py`
- `backend/tests/test_real_fuel_cell_data_pipeline.py`
- `docs/REAL_FUEL_CELL_DATASET.md`
- `backend/data/real/pem_fuel_cell_cathode_degradation/*.csv`
- `backend/artifacts/pem_fuel_cell_real_cathode_degradation/schema.json`

### Reuse

- Existing artifact conventions from `backend/artifacts/pem_fuel_cell_demo/`.
- Existing preprocessing/model-export caution from `.pi/skills/surrogate-model-debugging/SKILL.md`.
- Source evaluation logic from `data/Cathode Catalyst Degradation/03-Evaluation_scripts/`.
- PDF-derived paper schema and protocol details from the extracted markdown.

### Steps

- [ ] Parse only `Cell_01` metadata from `data_overview.xlsx`.
- [ ] Inventory only `Cell_01` raw files.
- [ ] Create `Cell_01` canonical long tables for IV, CV/ECSA, and diagnostics.
- [ ] Align BoL/EoL raw IV curves using measured BoL voltages with EoL interpolation inside overlap.
- [ ] Produce a paper-aligned 7-input / 4-output `model_table.csv`.
- [ ] Validate units, schema order, provenance, and no synthetic/proxy outputs.
- [ ] Decide separately whether to train/export a real model or stop at audited CSVs.

### Verification

- Confirm `Cell_01` maps to workbook test number `1`.
- Confirm no `Cell_02`–`Cell_42` rows are processed in Phase 1.
- Confirm `durability_score` and `cost_score` are absent from the real validation schema.
- Confirm every model row has source-file provenance and no voltage extrapolation.

## Source Material Reviewed

### Local data tree

Root data path:

```text
data/
```

Important files/folders observed:

```text
data/PEM Fuel Cell Catalyst Optimization.pdf
data/Cathode Catalyst Degradation/01-Data/Cell_01/
data/Cathode Catalyst Degradation/01-Data/Cell_01.zip
data/Cathode Catalyst Degradation/01-Data/Cell_02.zip
...
data/Cathode Catalyst Degradation/01-Data/Cell_42.zip
data/Cathode Catalyst Degradation/02-Testing_overview/data_overview.xlsx
data/Cathode Catalyst Degradation/03-Evaluation_scripts/eval_CV.py
data/Cathode Catalyst Degradation/03-Evaluation_scripts/eval_EIS_H2N2.py
data/Cathode Catalyst Degradation/03-Evaluation_scripts/eval_limiting_current.py
data/Cathode Catalyst Degradation/03-Evaluation_scripts/eval_LSV.py
data/Cathode Catalyst Degradation/03-Evaluation_scripts/raw_data_files/*.csv
```

The `Cell_01` folder is already extracted. `Cell_02.zip` through `Cell_42.zip` remain zipped and should be read directly from zip archives rather than bulk-extracted unless a later implementation explicitly needs an extraction cache.

### PDF content processed

The PDF was processed through the web/fetch extension by serving it locally and fetching:

```text
http://127.0.0.1:8765/PEM%20Fuel%20Cell%20Catalyst%20Optimization.pdf
```

The extracted markdown was saved by the extension at:

```text
/Users/brunocopa/Downloads/optimizing-catalyst-layer-composition-of-pem-fuel-cell-via-machine-learning-insights-from-in-house-e.md
```

Key PDF findings relevant to the data format:

- The paper models PEM fuel-cell cathode catalyst-layer behavior using ANN regression.
- A local `Cell_NN` means one physical CCM/fuel-cell test article, not one component in a larger stacked fuel cell. In this dataset, one `Cell_NN` maps to one workbook `Test no.` / one tested CCM configuration with one cathode catalyst-layer composition and one AST condition. That same cell is then characterized repeatedly across operating RH values, life stages, diagnostic methods, and cycle counts.
- The 42 local `Cell_NN` entries are therefore 42 separate tests/samples. They are not stacked together to recreate a single fuel cell.
- Input features described in the paper:
  - Pt/C ratio
  - I/C ratio
  - ionomer equivalent weight
  - operating RH
  - operating voltage
  - AST relative humidity
  - AST upper potential limit
- The paper explicitly states that its ANN uses seven input features to predict four outputs. The real-data project must follow that paper schema for validation, not the simplified synthetic demo outputs.
- Paper-aligned output working names for this repo:
  - `bol_current_density`
  - `eol_current_density`
  - `bol_ecsa`
  - `ecsa_loss`
- The exact output labels should be documented as paper-derived names in `metadata.json`; do not include synthetic-only `durability_score` or `cost_score` in the real validation model.
- Reported experimental structure:
  - cathode catalyst layer composition is controlled in-house
  - testing covers BoL characterization, AST degradation, and EoL characterization
  - IV / U-I performance curves at 100%, 70%, and 40% RH
  - CV-derived ECSA measurements across life
  - H2/N2 and H2/Air EIS diagnostics
  - limiting-current and LSV diagnostics
- The paper mentions 49 CCMs, while the local published data overview currently shows 42 rows/cells. Treat this as a provenance note: the local dataset appears to be a published subset/exclusion set, not something to patch manually.

## Existing DoE Format And Required Real-Data Divergence

The current synthetic project is `pem_fuel_cell_demo`. It is useful for understanding the backend artifact shape, but it is not the scientific target for this migration.

Current synthetic model input order already matches the seven paper inputs:

```text
pt_c_ratio
i_c_ratio
ionomer_ew
operating_rh
operating_voltage
ast_rh
ast_upl
```

Current synthetic output order does **not** match the paper because it includes simplified demo outputs:

```text
bol_current_density
eol_current_density
ecsa_loss
durability_score
cost_score
```

The real validation project must use the paper-aligned 7-input / 4-output contract instead:

```text
pt_c_ratio
i_c_ratio
ionomer_ew
operating_rh
operating_voltage
ast_rh
ast_upl
bol_current_density
eol_current_density
bol_ecsa
ecsa_loss
```

Current synthetic training/replay files use flat CSV rows with one experiment point per row:

```text
backend/data/synthetic/pem_fuel_cell_demo.csv
backend/data/replay/pem_fuel_cell_demo_initial_observed.csv
backend/data/replay/pem_fuel_cell_demo_hidden_pool.csv
backend/artifacts/pem_fuel_cell_demo/schema.json
backend/artifacts/pem_fuel_cell_demo/preprocessing.json
backend/artifacts/pem_fuel_cell_demo/model.onnx
```

The real-data transformation should initially produce the same kind of flat supervised-learning table, but under a new real-data project ID so the synthetic demo remains available.

Recommended new project ID:

```text
pem_fuel_cell_real_cathode_degradation
```

## Phase Boundary

Do not process all 42 cells in the first implementation. Phase 1 should process only `Cell_01` / test number `1` to validate parsing, unit conversion, BoL/EoL curve alignment, paper-schema output construction, and artifact generation. After `Cell_01` is validated end-to-end, a later phase can generalize the same code path to the remaining cells.

## Observed Data Inventory

### Cell archives

Observed:

- `Cell_01/` is already extracted and `Cell_01.zip` also exists.
- `Cell_02.zip` through `Cell_42.zip` are present for later phases, but Phase 1 must ignore them except for optional inventory notes.
- A `Cell_NN` corresponds to one tested CCM/fuel-cell sample / workbook test number. It has one sample-level catalyst-layer and AST configuration, then many measurement files from the test protocol.
- Most later cell archives contain roughly 191–200 CSV files.
- Later-phase caveat: `Cell_06.zip` is notably sparse with 71 files and lacks many EIS/IR-corrected artifacts.
- Later-phase caveat: `Cell_37.zip` appears to lack at least the RH40 EoL raw/IR-corrected IV pair.
- `.DS_Store` files are present and must be ignored.

Common top-level measurement folders:

```text
01-BreakIn
02-Limiting_Current_Measurements
03-IV-curve_RH100
04-EIS_H2Air_RH100
05-EIS_H2N2_RH100
06-IV-curve_RH70
07-EIS_H2Air_RH70
08-IV-curve_RH40
09-EIS_H2Air_RH40
10-CV
11-LSV
12-AST
```

Common lifecycle cycle folders:

```text
0cycles
10cycles
100cycles
1000cycles
3000cycles
5000cycles
10000cycles
20000cycles
30000cycles
```

### Testing overview workbook

`data_overview.xlsx` contains 42 rows matching the 42 `Cell_NN` test samples. For Phase 1, parse row/test number `1` only and map it to `Cell_01`. The workbook maps each test/cell to catalyst-layer metadata:

```text
Test no.
Pt load [mg/cm2]
I/C ratio
Ionomer EW [g/mol]
Pt/C ratio [%]
Catalyst type
Support type
AST UPL [V]
AST RH [%]
```

Observed factor values:

```text
I/C ratio: 0.5, 0.8, 1.2
Ionomer EW: 720, 790, 830, 980 g/mol
Pt/C ratio: 20, 30, 40, 50, 60 %
AST UPL: 0.95, 1.15 V
AST RH: 40, 70, 100 %
Catalyst type: Pt (SUP1), Pt (SUP2), PtCo (SUP1)
Support type: HSA, LSA
```

Important unit conversion:

```text
Pt/C ratio in workbook is percent; current DoE schema expects fraction.
20, 30, 40, 50, 60 % -> 0.2, 0.3, 0.4, 0.5, 0.6
```

Phase 1 `Cell_01` metadata parsed from workbook row/test number `1`:

```text
cell_id = Cell_01
test_no = 1
pt_loading_mg_cm2 = 0.3839
i_c_ratio = 0.5
ionomer_ew_g_mol = 790
pt_c_ratio_percent = 50
pt_c_ratio_fraction = 0.5
catalyst_type = Pt (SUP1)
support_type = HSA
ast_upl_v = 0.95
ast_rh_percent = 100
```

### CSV file types and useful columns

Representative CSV columns:

| File | Columns | Main use |
|---|---|---|
| `IV_data.csv` | `U.C[V]`, `I.C[A/cm2]` | Raw polarization curve points. |
| `IV_data_IR_corr.csv` | `U.C[V]`, `I.C[A/cm2]` | IR-corrected polarization curve points. |
| `ECSA_mean.csv` | `ECSA_90mV_mean [cm2/cm2]` | BoL/EoL ECSA and ECSA loss. |
| `C_DL_mean.csv` | `C_DL_mean [mF/cm2]` | CV-derived double-layer capacity summary. |
| `EIS_data_raw.csv` | `f.C[Hz]`, `Z.Re.C[mOhm*cm2]`, `Z.Im.C[mOhm*cm2]` | EIS spectra. |
| `R_ion.csv` | `R_ion[mOhm*cm2]` | H2/N2 EIS fitted protonic resistance. |
| `HFR.csv` | `HFR[mOhm*cm2]` | H2/N2 EIS fitted high-frequency resistance. |
| `C_DL.csv` | `C_dl[mF*cm-2]` | H2/N2 EIS fitted capacitance. |
| `HFR_data.csv` | `I.C[A/cm2]`, `HFR[mOhm*cm2]` | HFR vs current from IV/EIS measurement. |
| `iLim_data.csv` | `c_mean[mol/m³]`, `iLim[A/cm2]`, `p[bar]` | Limiting-current raw data. |
| `R_p_indep.csv` | `R_p_indep[s/m]` | Pressure-independent O2 transport resistance. |
| `R_p_dep.csv` | `R_p_dep[s/(m*bar)]` | Pressure-dependent O2 transport resistance slope. |
| `R_total_p.csv` | `p[bar]`, `R_T[s/m]` | Total O2 transport resistance by pressure. |
| `LSV_data_raw.csv` | `Time[s]`, `U.C[V]`, `I.C[mA/cm2]` | LSV raw curve. |
| `I_xover.csv` | `I_xover_RANSAC [mA/cm2]` | Hydrogen crossover current. |
| `pot_cycles_*.csv` | `Time[s]`, `U.C[V]`, `I.C[A/cm2]` | AST voltage-cycling traces. |

## Proposed Target Data Products

Create a staged data pipeline with durable intermediate files before training any model. Phase 1 writes the same file shapes that the full dataset will use, but only contains `Cell_01` rows.

### 1. Data inventory manifest

Path:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/inventory_manifest.csv
```

Phase 1 scope: one row per discovered file inside `data/Cathode Catalyst Degradation/01-Data/Cell_01/` or, if the implementation chooses zip reading for parity, inside `Cell_01.zip` only.

Suggested columns:

```text
cell_id
source_container
relative_path
measurement_group
operating_rh
cycle_count
load_or_voltage_condition
file_kind
exists
file_size_bytes
row_count
columns_hash
parse_status
parse_warning
```

Purpose:

- validate the parser on one complete-ish real cell first,
- make missing files visible for `Cell_01`,
- avoid silent folder/zip assumptions,
- create a manifest format that can later scale to `Cell_02`–`Cell_42`.

### 2. Cell metadata table

Path:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/cell_metadata.csv
```

Phase 1 scope: one row for `Cell_01` / workbook test number `1`.

Suggested columns:

```text
cell_id
test_no
material_variation
ast_variation
pt_loading_mg_cm2
i_c_ratio
ionomer_ew_g_mol
pt_c_ratio_fraction
pt_c_ratio_percent
catalyst_type
support_type
ast_upl_v
ast_rh_percent
source_workbook_row
```

Purpose:

- separate sample-level features from curve-level measurements,
- preserve categorical variables even if the first model does not use them,
- keep unit conversions auditable.

### 3. Long polarization table

Path:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/polarization_long.csv
```

One row per curve point.

Suggested columns:

```text
cell_id
cycle_count
life_stage
operating_rh_percent
curve_variant
voltage_v
current_density_a_cm2
source_file
source_row
```

Where:

```text
life_stage = bol for 0cycles
life_stage = eol for 30000cycles
curve_variant = raw or ir_corrected
```

Paper-aligned recommendation:

- Use `IV_data.csv` / `curve_variant=raw` as the primary current-density source. The extracted paper text describes U-I / polarization curves and an in-house cleaning/filtering algorithm, but it does not state that the ANN was trained on IR-corrected curves.
- Preserve `IV_data_IR_corr.csv` in the long table for QA and future comparison, but do not use it for the validation model because the reviewed paper text does not identify IR-corrected curves as ANN targets.
- Do not mix raw and IR-corrected curves in the same target column.

### 4. ECSA by cycle table

Path:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/ecsa_by_cycle.csv
```

One row per cell/cycle.

Suggested columns:

```text
cell_id
cycle_count
ecsa_90mv_mean_cm2_cm2
c_dl_mean_mf_cm2
source_ecsa_file
source_cdl_file
parse_status
```

Purpose:

- support endpoint ECSA loss for the first model,
- retain intermediate degradation trajectory for future durability models.

### 5. Diagnostic long tables

Recommended paths:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/eis_h2n2_summary.csv
backend/data/real/pem_fuel_cell_cathode_degradation/eis_h2air_long.csv
backend/data/real/pem_fuel_cell_cathode_degradation/limiting_current_summary.csv
backend/data/real/pem_fuel_cell_cathode_degradation/lsv_summary.csv
backend/data/real/pem_fuel_cell_cathode_degradation/ast_trace_manifest.csv
```

These are not required for the first replacement of the synthetic table, but they should be parsed into canonical files rather than ignored. They can later power additional KPIs or data-quality checks.

### 6. Model-ready supervised table

Path:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/model_table.csv
```

One row per `(cell_id, operating_rh, operating_voltage)` point after aligning BoL and EoL curves.

Minimum columns matching the paper-aligned validation schema:

```text
pt_c_ratio
i_c_ratio
ionomer_ew
operating_rh
operating_voltage
ast_rh
ast_upl
bol_current_density
eol_current_density
bol_ecsa
ecsa_loss
```

Recommended additional provenance/QA columns in a sidecar file or optional extended table:

```text
cell_id
pt_loading_mg_cm2
catalyst_type
support_type
curve_variant
bol_source_file
eol_source_file
ecsa_bol
ecsa_eol
voltage_alignment_method
interpolation_warning
```

The training script should consume only the schema-declared model columns. QA/provenance files must remain available so we can prove each row comes from `Cell_01` source measurements and not from synthetic/proxy values.

## Transformation Method

### Step 1 — Apply reviewed target assumptions

Use these decisions for the next implementation plan:

1. Phase 1 processes only `Cell_01` / workbook test number `1`. Do not process all 42 cells until the `Cell_01` pipeline is validated.
2. The real validation model must match the paper, not the synthetic demo. Use the paper's seven inputs and four outputs.
3. Keep the seven paper inputs: `pt_c_ratio`, `i_c_ratio`, `ionomer_ew`, `operating_rh`, `operating_voltage`, `ast_rh`, `ast_upl`.
4. Use four paper-aligned outputs: `bol_current_density`, `eol_current_density`, `bol_ecsa`, `ecsa_loss`.
5. Remove synthetic-only `durability_score` and `cost_score` from the real validation schema.
6. Preserve `pt_loading_mg_cm2`, `catalyst_type`, and `support_type` only as metadata/provenance for Phase 1. Do not add them as model inputs because the paper's seven inputs exclude them.
7. Use all cells in a later full-data phase, but not in the first implementation.
8. Use raw `IV_data.csv` as the current-density source because the paper describes measured U-I / polarization curves and raw-data cleaning, while the extracted text does not mention IR-corrected ANN targets. Keep `IV_data_IR_corr.csv` for QA only.
9. Use measured curve voltages where scientifically possible. The paper reports 294 polarization curves / about 6700 data points and includes `voltage` as an ANN input, which implies curve-point rows rather than an arbitrary generated fixed voltage grid. For paired BoL/EoL rows, use BoL measured voltages within the EoL voltage overlap and interpolate the EoL current at those voltages without extrapolation.

### Step 2 — Build `Cell_01` source inventory

Implement a read-only inventory pass that:

- scans only `data/Cathode Catalyst Degradation/01-Data/Cell_01/` for Phase 1,
- optionally cross-checks `Cell_01.zip` to confirm the extracted folder matches the archive,
- ignores `.DS_Store` and `__MACOSX`,
- records every CSV path inside `Cell_01`,
- computes row counts and column names,
- profiles missing expected files for `Cell_01`,
- writes `inventory_manifest.csv`.

Acceptance evidence:

- manifest has exactly one unique `cell_id`: `Cell_01`,
- manifest records the expected `Cell_01` measurement groups (`01-BreakIn` through `12-AST`),
- file-kind counts are summarized in a generated profile report,
- the manifest format is explicitly designed so a later phase can add `Cell_02`–`Cell_42` without changing column names.

### Step 3 — Parse workbook metadata

Implement a stdlib XLSX parser or a carefully justified dependency-based parser.

Given the project preference to avoid new dependencies unless justified, the first implementation can parse XLSX as a zip of XML files using Python stdlib. If the implementation becomes too brittle, ask before adding `openpyxl` through `uv`.

Acceptance evidence:

- `cell_metadata.csv` has exactly one Phase 1 row,
- `Cell_01` maps to test number `1`,
- Pt/C percent is preserved and converted to fraction,
- all units are explicit in column names,
- categorical catalyst/support labels are preserved exactly as metadata even though they are not Phase 1 model inputs.

### Step 4 — Parse canonical long tables for `Cell_01`

Implement parsers for each `Cell_01` measurement family:

- IV curves: `03-IV-curve_RH100`, `06-IV-curve_RH70`, `08-IV-curve_RH40`.
- CV summaries: `10-CV/*cycles/ECSA_mean.csv`, `C_DL_mean.csv`.
- EIS H2/N2 summaries: `05-EIS_H2N2_RH100/*mV/*cycles/R_ion.csv`, `HFR.csv`, `C_DL.csv`.
- EIS H2/Air curves: `04`, `07`, `09` folders.
- Limiting current: `02-Limiting_Current_Measurements`.
- LSV: `11-LSV`.
- AST traces: `12-AST` manifest first, raw traces later if needed.

Acceptance evidence:

- all parsers are unit-aware,
- tab-delimited CSV files are read correctly,
- parsing failures become row-level warnings rather than silent drops,
- intermediate canonical files include source file and source row references.

### Step 5 — Align BoL/EoL polarization curves for `Cell_01`

For each `Cell_01` operating RH pair (`RH100`, `RH70`, `RH40`):

1. Load BoL raw IV curve from `0cycles/IV_data.csv`.
2. Load EoL raw IV curve from `30000cycles/IV_data.csv`.
3. Sort each curve by voltage.
4. Use measured BoL voltage points that lie within the EoL voltage overlap.
5. Interpolate EoL current density at those BoL voltage points.
6. Keep the original BoL current density at its measured voltage.
7. Attach `Cell_01` metadata and ECSA endpoint metrics.
8. Write rows to `model_table.csv`.

Why this alignment is recommended:

- The paper says the ANN uses voltage as an input and was trained on thousands of polarization-curve data points.
- That supports a row-per-curve-point table, not a synthetic fixed-grid design.
- Interpolating only the paired EoL curve is a minimal scientific compromise that enables a single row to contain both BoL and EoL current density at the same operating voltage.
- Extrapolation is forbidden.

Recommended treatment of missing curves:

- If a `Cell_01` RH pair lacks either BoL or EoL curve, exclude that pair from `model_table.csv` and record it in a rejected-row report.
- Do not fill missing EoL values from surrogate predictions.
- Do not mix RH conditions to patch missing curves.
- Do not substitute IR-corrected data into the raw-data target.

Acceptance evidence:

- every `model_table.csv` row has a measured BoL value and measured/interpolated EoL value sourced from real `Cell_01` curves,
- no row uses synthetic generated outputs,
- excluded pairs are listed with reasons,
- voltage interpolation never extrapolates outside the curve overlap,
- raw and IR-corrected curves remain separate.

### Step 6 — Compute paper-aligned real outputs

For the paper-aligned 7-input / 4-output format:

```text
bol_current_density = measured BoL current density at operating_voltage
eol_current_density = EoL current density at the same operating_voltage, interpolated from measured EoL curve when necessary
bol_ecsa = ECSA_0cycles from 10-CV/0cycles/ECSA_mean.csv
ecsa_loss = (ECSA_0cycles - ECSA_30000cycles) / ECSA_0cycles
```

Rules:

- Do not create `durability_score`.
- Do not create `cost_score`.
- Do not use Pt loading as a cost proxy in the paper-validation model.
- If `ecsa_loss` is negative because of measurement noise, do not silently clip it; log it and decide explicitly whether to keep the physical value or mark the row for review.
- Mark `ecsa_loss` as a derived paper output computed from measured ECSA endpoints.

### Step 7 — Create a real project artifact boundary

Do not overwrite the synthetic demo artifacts. Add a new project directory only after the data pipeline is validated.

Potential target:

```text
backend/artifacts/pem_fuel_cell_real_cathode_degradation/schema.json
backend/artifacts/pem_fuel_cell_real_cathode_degradation/preprocessing.json
backend/artifacts/pem_fuel_cell_real_cathode_degradation/model.onnx
backend/artifacts/pem_fuel_cell_real_cathode_degradation/metadata.json
```

The schema must reflect the final model columns and ranges from the real data, not copied blindly from the synthetic schema.

Minimum metadata fields:

```text
source_pdf
source_data_root
phase_scope
source_cell_count
source_cell_ids
source_archive_count
model_table_path
curve_variant
voltage_alignment_method
measured_outputs
derived_outputs
excluded_rows_report
known_limitations
```

For Phase 1, `phase_scope` should explicitly say `Cell_01 only`, `source_cell_count` should be `1`, and `source_cell_ids` should be `Cell_01`.

### Step 8 — Defer full replay files until after `Cell_01` validation

Do not create the final BO replay split in Phase 1 unless it is needed for a smoke test. A meaningful grouped replay split requires multiple cells; `Cell_01` alone cannot validate generalization across cells.

If a smoke replay is needed for UI/API plumbing, create clearly labeled temporary files only after user approval:

```text
backend/data/replay/pem_fuel_cell_real_cathode_degradation_cell_01_smoke_initial.csv
backend/data/replay/pem_fuel_cell_real_cathode_degradation_cell_01_smoke_hidden.csv
```

Smoke replay constraints:

- label it as `Cell_01` smoke data, not a scientific replay benchmark,
- split rows by voltage/RH only, since there is only one cell,
- never present smoke replay metrics as model generalization evidence,
- keep hidden outputs measured/interpolated from real `Cell_01` rows,
- never treat surrogate predictions as observed truth.

Full replay generation belongs to the later all-cell phase, where grouped splitting by `cell_id` becomes possible.

## Proposed Implementation Files For A Later Approved Step

Do not implement these from this plan without approval.

```text
backend/training/build_real_fuel_cell_dataset.py
backend/training/real_fuel_cell_schema.py
backend/tests/test_real_fuel_cell_data_pipeline.py
docs/REAL_FUEL_CELL_DATASET.md
backend/data/real/pem_fuel_cell_cathode_degradation/*.csv
backend/artifacts/pem_fuel_cell_real_cathode_degradation/schema.json
```

If training support must become multi-project-aware, likely touched files include:

```text
backend/training/train_mlp.py
backend/training/export_onnx.py
backend/app/services/project_registry.py
```

Touch these only if necessary and keep the existing synthetic project working.

## Validation And QA Plan

### Data integrity checks

- Phase 1 discovers and processes only `Cell_01`.
- `cell_metadata.csv` contains exactly one row mapped from workbook test number `1`.
- Every model row has `cell_id = Cell_01` and joins to that metadata row.
- Pt/C percent-to-fraction conversion is tested.
- Required paper-schema inputs are numeric and within schema ranges.
- Required paper-schema outputs are present: `bol_current_density`, `eol_current_density`, `bol_ecsa`, `ecsa_loss`.
- No row contains NaN, infinity, or missing required model columns.
- The transformer rejects extrapolated voltage points.
- The only derived output in Phase 1 is `ecsa_loss`, and its formula is documented.

### Scientific checks

- BoL and EoL current density units remain `A/cm2`.
- ECSA units remain `cm2/cm2` in intermediate tables.
- ECSA loss is dimensionless fraction.
- `operating_rh` comes from measurement folder name, not AST RH.
- `ast_rh` comes from the testing overview workbook, not measurement RH.
- `ast_upl` comes from the testing overview workbook.
- Raw and IR-corrected IV curves are never mixed in the same target.

### Model-readiness checks

- `model_table.csv` columns match the selected `schema.json` input/output order.
- Train/validation split strategy is cell-aware if generalization across cells matters.
- Preprocessing min/max values are computed from training data and saved.
- ONNX predictions are compared against native PyTorch predictions on the same sample batch.
- At least one sample is traced end-to-end from raw archive path to frontend prediction output.

### Replay checks

For Phase 1:

- No full scientific replay split is required.
- If a smoke replay is explicitly approved, initial and hidden rows must come from real `Cell_01` model rows.
- Hidden pool retains outputs but does not reveal them until replay reveal.
- No duplicate replay IDs.
- Smoke replay files are clearly labeled as non-benchmark plumbing data.

For the later all-cell phase:

- Replay splitting should be grouped by `cell_id` unless the user explicitly chooses row-level interpolation replay.

## Open Questions / Ask-Before Rules

Resolved by review and PDF inspection:

1. Phase 1 processes only `Cell_01`.
2. A `Cell_NN` is one tested CCM/fuel-cell sample / one workbook test configuration, not a component in a stack.
3. The real validation schema follows the paper's seven inputs and four outputs.
4. Synthetic-only `durability_score` and `cost_score` are not part of the real validation schema.
5. Raw `IV_data.csv` is the Phase 1 current-density source; `IV_data_IR_corr.csv` remains QA-only.
6. Voltage alignment uses measured BoL voltages with EoL interpolation inside overlap; no arbitrary fixed grid for Phase 1.

Still ask before implementation if any of these become necessary:

1. Is `data/` intended to be versioned in git, stored with Git LFS, or treated as local-only raw data?
2. Should Phase 1 create a temporary `Cell_01` smoke replay split, or only produce model-ready data?
3. Should the next approved implementation also train/export a model, or stop after producing audited CSV artifacts?
4. If exact paper figure labels differ from the working output names here, should we rename repo columns to match the paper labels verbatim?

Hard stop conditions:

- Do not overwrite synthetic demo artifacts.
- Do not train on synthetic and real rows mixed together unless explicitly requested.
- Do not invent missing measurements.
- Do not fill EoL outputs with model predictions.
- Do not add dependencies outside `uv` workflow without approval.
- Do not change public API routes unless explicitly requested.

## Acceptance Criteria For This Plan

This plan is complete when:

- it explains what a `Cell_NN` represents scientifically,
- it documents the observed `data/` layout while scoping Phase 1 to `Cell_01`,
- it maps `Cell_01` source files to the paper-aligned 7-input / 4-output model table,
- it records PDF-derived context and experimental feature/target definitions,
- it identifies high-risk unit conversions and later-phase missing-cell caveats,
- it lists concrete future implementation files and validation checks,
- it keeps implementation as a separate approval step.

## Suggested Local Verification Commands For Future Implementation

Once an implementation exists, use commands like:

```bash
uv run python backend/training/build_real_fuel_cell_dataset.py --cell-id Cell_01 --dry-run --profile
uv run python backend/training/build_real_fuel_cell_dataset.py --cell-id Cell_01 --output backend/data/real/pem_fuel_cell_cathode_degradation/model_table.csv
uv run python -m pytest backend/tests/test_real_fuel_cell_data_pipeline.py backend/tests/test_api.py
```

If model training is included in a later approved step:

```bash
uv run python backend/training/train_mlp.py --project-id pem_fuel_cell_real_cathode_degradation
```

The exact training command may require a small trainer refactor because the current `train_mlp.py` is tied to `pem_fuel_cell_demo` constants.
