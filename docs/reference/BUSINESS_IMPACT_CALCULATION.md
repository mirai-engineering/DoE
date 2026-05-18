# Business Impact calculation

This document explains how the **Business Impact** tab computes working hours saved and money saved for the real PEM fuel-cell DoE case study.

The implementation lives in:

- Backend calculation: `backend/app/services/business_impact.py`
- API endpoint: `GET /projects/{project_id}/impact/summary`
- Frontend tab: `frontend/src/components/BusinessImpactPage.tsx`

Current case-study project:

```text
pem_fuel_cell_real_cathode_degradation
```

## What the tab is estimating

The tab estimates the impact of using ML-guided Design of Experiments to reduce the number of physical fuel-cell builds in one catalyst-layer campaign.

It is a **planning scenario**, not a completed prospective lab validation. The numbers are intentionally simple and inspectable:

1. Count how many real physical cells exist in the audited dataset.
2. Assume a fixed percentage of physical recipes can be avoided after ML-guided virtual screening.
3. Convert avoided recipes into saved bench-hours using the paper's reported characterization time per sample.
4. Convert saved bench-hours into calendar days and cost proxies.

## Current constants

Defined in `backend/app/services/business_impact.py`:

| Constant | Value | Meaning |
|---|---:|---|
| `PAPER_FULL_CHARACTERIZATION_HOURS_PER_SAMPLE` | `130.0` h/sample | Approximate full characterization time per sample from the Energy and AI 2024 reference paper. |
| `VIRTUAL_CANDIDATES_PER_SCREEN` | `2000` | Planning value for how many virtual recipes the software can screen before lab commitment. |
| `TARGET_EXPERIMENT_REDUCTION_FRACTION` | `0.35` | Scenario assumption: 35% fewer physical recipes. |
| `HANDS_ON_HOURS_PER_PHYSICAL_SAMPLE` | `6.0` h/sample | Conservative planning proxy for setup, assembly, monitoring, transfer, and review labor per avoided sample. |
| `INTERNAL_DIRECT_COST_PER_SAMPLE_USD` | `$1,500–$3,000` / sample | Internal planning proxy for materials, consumables, gases, and setup overhead. Not a quoted price. |
| `EXTERNAL_TESTBED_DAY_RATE_USD` | `$3,000–$5,000` / day | External testbed capacity proxy from public energy-testbed fee examples. Not a quote for this exact PEMFC workflow. |

## Dataset-derived values

The backend reads these generated audited artifacts:

```text
backend/data/real/pem_fuel_cell_cathode_degradation/model_table.csv
backend/data/real/pem_fuel_cell_cathode_degradation/cell_metadata.csv
backend/data/real/pem_fuel_cell_cathode_degradation/ast_trace_manifest.csv
```

Current values:

| Value | Current result | Source |
|---|---:|---|
| Physical cells in repo | `42` | Unique `cell_id` count in `cell_metadata.csv` |
| Model rows in repo | `2,544` | Row count of `model_table.csv` |
| Raw AST trace hours in repo | `430.6` h | Sum of max `time_max_s` per cell from `ast_trace_manifest.csv`, divided by 3600 |
| Physical cells in reference paper | `49` | Energy and AI 2024 reference paper |
| Paper polarization curves | `294` | Energy and AI 2024 reference paper |
| Paper data points | `~6,700` | Energy and AI 2024 reference paper |

## Formulas

### 1. Baseline physical recipes

```text
baseline_physical_recipes = number of unique cell_id values in cell_metadata.csv
```

Current value:

```text
baseline_physical_recipes = 42
```

### 2. Baseline bench-hours

```text
baseline_bench_hours = baseline_physical_recipes × 130 h/sample
```

Current value:

```text
42 × 130 = 5,460 h
```

### 3. Mirai-prioritized physical recipes

The scenario assumes ML-guided screening reduces physical experiments by 35%.

```text
mirai_prioritized_recipes = ceil(baseline_physical_recipes × (1 - 0.35))
```

Current value:

```text
ceil(42 × 0.65) = ceil(27.3) = 28 recipes
```

The calculation uses `ceil` so the estimate does not overstate savings by rounding the number of lab recipes down.

### 4. Avoided physical recipes

```text
avoided_physical_recipes = baseline_physical_recipes - mirai_prioritized_recipes
```

Current value:

```text
42 - 28 = 14 avoided recipes
```

### 5. Mirai-guided bench-hours

```text
mirai_bench_hours = mirai_prioritized_recipes × 130 h/sample
```

Current value:

```text
28 × 130 = 3,640 h
```

### 6. Saved bench-hours

```text
saved_bench_hours = avoided_physical_recipes × 130 h/sample
```

Current value:

```text
14 × 130 = 1,820 h
```

### 7. Saved calendar bench-days

```text
saved_bench_days = saved_bench_hours / 24
```

Current value:

```text
1,820 / 24 = 75.8 days
```

### 8. Saved 40-hour work weeks

```text
saved_work_weeks_40h = saved_bench_hours / 40
```

Current value:

```text
1,820 / 40 = 45.5 work weeks
```

This is a capacity normalization, not a claim that a single person works continuously for that duration.

### 9. Saved hands-on working hours

```text
saved_hands_on_hours = avoided_physical_recipes × 6 h/sample
```

Current value:

```text
14 × 6 = 84 h
```

This is separate from bench-hours. Bench-hours represent specialized equipment/test-station occupancy; hands-on hours represent estimated human setup and supervision effort.

### 10. Internal direct cost savings

```text
internal_low = avoided_physical_recipes × $1,500/sample
internal_high = avoided_physical_recipes × $3,000/sample
```

Current values before display rounding:

```text
14 × $1,500 = $21,000
14 × $3,000 = $42,000
```

Displayed values are rounded to the nearest `$1,000` by the helper function `_money()`.

Current displayed result:

```text
$21k–$42k
```

### 11. External capacity value saved

```text
external_low = saved_bench_days × $3,000/day
external_high = saved_bench_days × $5,000/day
```

Current values before display rounding:

```text
75.833... × $3,000 = $227,500
75.833... × $5,000 = $379,166.67
```

Displayed values are rounded to the nearest `$1,000` by `_money()`.

Current displayed result:

```text
$228k–$379k
```

## Current dashboard headline numbers

For the current 42-cell campaign scenario:

| Metric | Value |
|---|---:|
| Baseline physical recipes | `42` |
| Mirai-prioritized recipes | `28` |
| Avoided physical recipes | `14` |
| Baseline bench-hours | `5,460 h` |
| Mirai-guided bench-hours | `3,640 h` |
| Saved bench-hours | `1,820 h` |
| Saved calendar bench-days | `75.8 days` |
| Saved 40-hour work weeks | `45.5 weeks` |
| Saved hands-on working hours | `84 h` |
| Internal direct savings | `$21k–$42k` |
| External capacity proxy | `$228k–$379k` |

## References used by the tab

These are the references returned by the backend in the `sources` field.

### 1. Energy and AI 2024 PEM fuel-cell ML reference

```text
Label: Reference PDF / Energy and AI 2024
Path: data/PEM Fuel Cell Catalyst Optimization.pdf
```

Claim used in the software:

- 49 fuel cells
- 294 polarization curves
- approximately 6,700 data points
- each full sample characterization takes approximately 130 hours
- ANN modeling predicts BoL/EoL behavior and supports faster development

How it is used:

- Supplies the `130 h/sample` characterization-time assumption.
- Provides context for dataset scale: 49 cells, 294 polarization curves, ~6,700 data points.

### 2. Repo-audited real dataset

```text
Label: Repo-audited dataset
Path: backend/data/real/pem_fuel_cell_cathode_degradation/
```

Claim used in the software:

- Current local artifacts contain 42 extracted cells.
- Current model table contains 2,544 model rows.
- Raw AST traces account for approximately 430.6 hours of recorded bench time.

How it is used:

- Supplies the current `42` physical-cell campaign size.
- Supplies row counts and raw-trace evidence for the local case study.

### 3. Scribner 850 product literature

```text
Label: Scribner 850 product literature
URL: https://scribner.com/products/fuel-cell-test-systems/850-multi-range-fuel-cell-test-system
```

Claim used in the software:

- Fuel-cell test systems are specialized equipment for PEM/AEM/DMFC single-cell and short-stack research.
- Test-bench capacity is therefore treated as a scarce R&D resource.

How it is used:

- Supports the interpretation of saved bench-hours as valuable capacity, not merely elapsed time.

### 4. Published energy-testbed day-rate examples

```text
Label: Published energy-testbed day-rate examples
URL: https://umbatterylab.engin.umich.edu/fees/
```

Claim used in the software:

- External energy test facilities commonly price specialized testing capacity in day-scale reservations.
- The scenario uses `$3,000–$5,000/day` as a planning proxy, not a quote.

How it is used:

- Supplies the external capacity proxy range:

```text
saved_bench_days × $3,000/day
saved_bench_days × $5,000/day
```

### 5. Nature Communications 2025 AI-guided PEMFC design

```text
Label: Nature Communications 2025 AI-guided PEMFC design
URL: https://www.nature.com/articles/s41467-025-61794-y
```

Claim used in the software:

- Closed-loop ANN plus Bayesian optimization can reduce expensive trial-and-error search in PEM fuel-cell component design.

How it is used:

- Supports the broader premise that AI-guided screening and optimization are credible approaches for reducing physical PEMFC experimentation.

## Important caveats

The UI intentionally exposes these caveats:

1. Savings are a planning scenario, not yet a completed prospective lab trial.
2. External day-rate values are public energy-testbed analogs; a fuel-cell CRO quote or internal finance model should replace them for customer-specific ROI.
3. The strongest current predictive evidence is for current-density curves; ECSA targets need more cell-level data before being used alone for business-critical decisions.

## How to reproduce the current numbers

From the backend directory:

```bash
cd backend
uv run python - <<'PY'
from app.services.business_impact import get_business_impact_summary, PROJECT_ID
summary = get_business_impact_summary(PROJECT_ID)
print(summary["case_study"])
print(summary["scenario"])
PY
```

Or through the API when the stack is running:

```bash
curl http://localhost:3000/api/projects/pem_fuel_cell_real_cathode_degradation/impact/summary
```
