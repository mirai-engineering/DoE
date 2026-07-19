from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ID = "pem_fuel_cell_real_cathode_degradation"
FRAUNHOFER_FUEL_CELL_DEMO_PROJECT_ID = "fuel_cell_demo_65248559"
SUPPORTED_PROJECT_IDS = {PROJECT_ID, FRAUNHOFER_FUEL_CELL_DEMO_PROJECT_ID}

logger = logging.getLogger(__name__)


BACKEND_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND_ROOT.parent
REFERENCE_DATA_ROOT = Path(os.getenv("DOE_REFERENCE_DATA_ROOT", REPO_ROOT / "data" / "reference"))
REAL_DATA_DIR = REFERENCE_DATA_ROOT / "pem_fuel_cell_cathode_degradation"


# Conservative, explicit business-case assumptions. These are not quotes.
PAPER_FULL_CHARACTERIZATION_HOURS_PER_SAMPLE = 130.0
VIRTUAL_CANDIDATES_PER_SCREEN = 2000
TARGET_EXPERIMENT_REDUCTION_FRACTION = 0.35
HANDS_ON_HOURS_PER_PHYSICAL_SAMPLE = 6.0
INTERNAL_DIRECT_COST_PER_SAMPLE_USD = (1500, 3000)
EXTERNAL_TESTBED_DAY_RATE_USD = (3000, 5000)
DEFAULT_PHYSICAL_CELLS_IN_REPO = 42
DEFAULT_MODEL_ROWS_IN_REPO = 2544
DEFAULT_RAW_AST_TRACE_HOURS_IN_REPO = 430.6


def _money(value: float) -> int:
    return int(round(value / 1000.0) * 1000)


def _fuel_cell_case_study_counts() -> tuple[int, int, float]:
    """Return audited PEM demo counts, falling back to constants in deploy images without reference CSVs."""
    try:
        model_table = pd.read_csv(REAL_DATA_DIR / "model_table.csv")
        metadata = pd.read_csv(REAL_DATA_DIR / "cell_metadata.csv")
        ast_manifest = pd.read_csv(REAL_DATA_DIR / "ast_trace_manifest.csv")
        physical_cells = int(metadata["cell_id"].nunique())
        model_rows = int(len(model_table))
        ast_hours = float(ast_manifest.groupby("cell_id")["time_max_s"].max().sum() / 3600.0)
        return physical_cells, model_rows, ast_hours
    except FileNotFoundError as exc:
        logger.info("Fuel-cell business-impact reference CSVs unavailable; using audited constants: %s", exc)
        return DEFAULT_PHYSICAL_CELLS_IN_REPO, DEFAULT_MODEL_ROWS_IN_REPO, DEFAULT_RAW_AST_TRACE_HOURS_IN_REPO


def get_business_impact_summary(project_id: str) -> dict[str, Any]:
    if project_id not in SUPPORTED_PROJECT_IDS:
        supported = ", ".join(sorted(SUPPORTED_PROJECT_IDS))
        raise ValueError(f"Business-impact case study is only available for: {supported}")

    physical_cells, model_rows, ast_hours_observed_in_raw_files = _fuel_cell_case_study_counts()
    paper_bench_hours = float(physical_cells * PAPER_FULL_CHARACTERIZATION_HOURS_PER_SAMPLE)
    guided_cells = int(math.ceil(physical_cells * (1.0 - TARGET_EXPERIMENT_REDUCTION_FRACTION)))
    avoided_cells = physical_cells - guided_cells
    saved_bench_hours = float(avoided_cells * PAPER_FULL_CHARACTERIZATION_HOURS_PER_SAMPLE)
    saved_bench_days = saved_bench_hours / 24.0
    saved_work_weeks = saved_bench_hours / 40.0
    saved_hands_on_hours = float(avoided_cells * HANDS_ON_HOURS_PER_PHYSICAL_SAMPLE)

    internal_low = avoided_cells * INTERNAL_DIRECT_COST_PER_SAMPLE_USD[0]
    internal_high = avoided_cells * INTERNAL_DIRECT_COST_PER_SAMPLE_USD[1]
    external_low = saved_bench_days * EXTERNAL_TESTBED_DAY_RATE_USD[0]
    external_high = saved_bench_days * EXTERNAL_TESTBED_DAY_RATE_USD[1]

    return {
        "project_id": project_id,
        "title": "Fuel-cell Design of Experiments business impact",
        "headline": {
            "problem": "Fuel-cell catalyst-layer DoE is slow because every candidate recipe consumes a full CCM/fuel-cell build and long characterization campaign.",
            "method": "Mirai converts historical PEM fuel-cell experiments into a surrogate model, screens thousands of candidate recipes virtually, then sends only prioritized candidates to the lab.",
            "measured_by": "Fewer physical recipes, fewer test-bench hours, and lower R&D capacity cost before a scientist commits lab time.",
        },
        "case_study": {
            "physical_cells_in_repo": physical_cells,
            "physical_cells_in_paper": 49,
            "model_rows_in_repo": model_rows,
            "paper_polarization_curves": 294,
            "paper_data_points": 6700,
            "paper_hours_per_sample": PAPER_FULL_CHARACTERIZATION_HOURS_PER_SAMPLE,
            "raw_ast_trace_hours_in_repo": round(ast_hours_observed_in_raw_files, 1),
            "estimated_full_campaign_bench_hours": round(paper_bench_hours),
            "virtual_candidates_per_screen": VIRTUAL_CANDIDATES_PER_SCREEN,
        },
        "scenario": {
            "name": "One 42-recipe catalyst-layer campaign",
            "baseline_physical_recipes": physical_cells,
            "mirai_prioritized_recipes": guided_cells,
            "avoided_physical_recipes": avoided_cells,
            "experiment_reduction_fraction": TARGET_EXPERIMENT_REDUCTION_FRACTION,
            "baseline_bench_hours": round(paper_bench_hours),
            "mirai_bench_hours": round(guided_cells * PAPER_FULL_CHARACTERIZATION_HOURS_PER_SAMPLE),
            "saved_bench_hours": round(saved_bench_hours),
            "saved_bench_days": round(saved_bench_days, 1),
            "saved_work_weeks_40h": round(saved_work_weeks, 1),
            "saved_hands_on_hours": round(saved_hands_on_hours),
            "internal_direct_cost_saved_usd": {"low": _money(internal_low), "high": _money(internal_high)},
            "external_capacity_value_saved_usd": {"low": _money(external_low), "high": _money(external_high)},
        },
        "visuals": {
            "funnel": [
                {"label": "Virtual recipes screened", "value": VIRTUAL_CANDIDATES_PER_SCREEN, "tone": "software"},
                {"label": "Historical physical cells learned from", "value": physical_cells, "tone": "learned"},
                {"label": "Mirai-prioritized lab recipes", "value": guided_cells, "tone": "run"},
                {"label": "Physical recipes avoided", "value": avoided_cells, "tone": "saved"},
            ],
            "time_comparison": [
                {"label": "Traditional DoE", "hours": round(paper_bench_hours)},
                {"label": "Mirai-guided DoE", "hours": round(guided_cells * PAPER_FULL_CHARACTERIZATION_HOURS_PER_SAMPLE)},
                {"label": "Reclaimed capacity", "hours": round(saved_bench_hours)},
            ],
            "cost_comparison": [
                {"label": "Internal direct savings", "low": _money(internal_low), "high": _money(internal_high)},
                {"label": "External testbed capacity", "low": _money(external_low), "high": _money(external_high)},
            ],
        },
        "takeaways": [
            {
                "title": "X: DoE bottleneck",
                "body": "A single candidate CCM/fuel-cell sample can take ~130 hours to break in, characterize, degrade, and retest.",
            },
            {
                "title": "Y: ML-guided prioritization",
                "body": "The software learns from completed cells, ranks thousands of virtual recipes, and keeps scientists in the loop before lab commitment.",
            },
            {
                "title": "Z: measurable business impact",
                "body": f"In this 42-cell campaign scenario, avoiding {avoided_cells} physical recipes reclaims ~{round(saved_bench_hours):,} bench-hours and roughly ${_money(external_low)//1000}k–${_money(external_high)//1000}k of external testbed capacity.",
            },
        ],
        "sources": [
            {
                "label": "Reference PDF / Energy and AI 2024",
                "claim": "49 fuel cells, 294 polarization curves, ~6700 data points; each full sample characterization takes approximately 130 h; ANN predicts BoL/EoL behavior and accelerates development.",
                "url": "data/PEM Fuel Cell Catalyst Optimization.pdf",
            },
            {
                "label": "Repo-audited dataset",
                "claim": f"Current local artifact contains {physical_cells} extracted cells and {model_rows} model rows; raw AST traces alone account for ~{round(ast_hours_observed_in_raw_files):,} h of recorded bench time.",
                "url": "data/reference/pem_fuel_cell_cathode_degradation/",
            },
            {
                "label": "Scribner 850 product literature",
                "claim": "A fuel-cell test system is specialized equipment for PEM/AEM/DMFC single-cell and short-stack research; test-bench capacity is a scarce R&D resource.",
                "url": "https://scribner.com/products/fuel-cell-test-systems/850-multi-range-fuel-cell-test-system",
            },
            {
                "label": "Published energy-testbed day-rate examples",
                "claim": "External energy test facilities commonly price specialized testing capacity in day-scale reservations; scenario uses $3k–$5k/day as a planning proxy, not a quote.",
                "url": "https://umbatterylab.engin.umich.edu/fees/",
            },
            {
                "label": "Nature Communications 2025 AI-guided PEMFC design",
                "claim": "Closed-loop ANN + Bayesian optimization is used to reduce expensive trial-and-error search in PEM fuel-cell component design.",
                "url": "https://www.nature.com/articles/s41467-025-61794-y",
            },
        ],
        "caveats": [
            "Savings are a planning scenario, not yet a completed prospective lab trial.",
            "External day-rate values are public energy-testbed analogs; a fuel-cell CRO or internal finance quote should replace them for customer-specific ROI.",
            "The strongest current predictive evidence is for current-density curves; ECSA targets need more cell-level data before being used alone for business-critical decisions.",
        ],
    }
