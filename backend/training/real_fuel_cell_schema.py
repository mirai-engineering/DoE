from __future__ import annotations

from pathlib import Path


PROJECT_ID = "pem_fuel_cell_real_cathode_degradation"
PHASE_SCOPE = "Cell_01 only"
DEFAULT_CELL_ID = "Cell_01"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
RAW_DATA_ROOT = REPO_ROOT / "data" / "Cathode Catalyst Degradation"
RAW_CELL_DATA_ROOT = RAW_DATA_ROOT / "01-Data"
TESTING_OVERVIEW_XLSX = RAW_DATA_ROOT / "02-Testing_overview" / "data_overview.xlsx"
OUTPUT_DIR = BACKEND_ROOT / "data" / "real" / "pem_fuel_cell_cathode_degradation"
TRAINING_ARTIFACT_DIR = OUTPUT_DIR / "training_artifacts"
SCIENTIST_REVIEW_DIR = BACKEND_ROOT / "data" / "model_quality_reviews"
SOURCE_PDF = REPO_ROOT / "data" / "PEM Fuel Cell Catalyst Optimization.pdf"
ARTIFACT_DIR = BACKEND_ROOT / "artifacts" / PROJECT_ID
MLFLOW_TRACKING_DIR = BACKEND_ROOT / "mlruns"
MLFLOW_MODEL_CACHE_DIR = BACKEND_ROOT / ".mlflow-cache" / PROJECT_ID
MLFLOW_REGISTERED_MODEL_NAME = PROJECT_ID

PAPER_INPUT_COLUMNS = [
    "pt_c_ratio",
    "i_c_ratio",
    "ionomer_ew",
    "operating_rh",
    "operating_voltage",
    "ast_rh",
    "ast_upl",
]

PAPER_OUTPUT_COLUMNS = [
    "bol_current_density",
    "eol_current_density",
    "bol_ecsa",
    "ecsa_loss",
]

MODEL_COLUMNS = PAPER_INPUT_COLUMNS + PAPER_OUTPUT_COLUMNS

REAL_PROJECT_SCHEMA = {
    "project_id": PROJECT_ID,
    "display_name": "PEM Fuel Cell Real Cathode Degradation",
    "description": "Cell_01 smoke MLOps project trained from audited real cathode catalyst degradation data. Smoke/demo quality only; not final scientific evidence.",
    "schema_version": "0.2.0-smoke",
    "allow_unknown_inputs": False,
    "inputs": [
        {"name": "pt_c_ratio", "label": "Pt/C ratio", "type": "continuous", "min": 0.2, "max": 0.6, "unit": "fraction"},
        {"name": "i_c_ratio", "label": "I/C ratio", "type": "continuous", "min": 0.5, "max": 1.2, "unit": "ratio"},
        {"name": "ionomer_ew", "label": "Ionomer equivalent weight", "type": "continuous", "min": 720, "max": 980, "unit": "g/mol"},
        {"name": "operating_rh", "label": "Operating relative humidity", "type": "continuous", "min": 40, "max": 100, "unit": "%"},
        {"name": "operating_voltage", "label": "Operating voltage", "type": "continuous", "min": 0.0, "max": 1.0, "unit": "V"},
        {"name": "ast_rh", "label": "AST relative humidity", "type": "continuous", "min": 40, "max": 100, "unit": "%"},
        {"name": "ast_upl", "label": "AST upper potential limit", "type": "continuous", "min": 0.95, "max": 1.15, "unit": "V"},
    ],
    "outputs": [
        {"name": "bol_current_density", "label": "BoL current density", "direction": "maximize", "unit": "A/cm²"},
        {"name": "eol_current_density", "label": "EoL current density", "direction": "maximize", "unit": "A/cm²"},
        {"name": "bol_ecsa", "label": "BoL ECSA", "direction": "maximize", "unit": "cm²/cm²"},
        {"name": "ecsa_loss", "label": "ECSA loss", "direction": "minimize", "unit": "fraction"},
    ],
    "metadata": {
        "phase_scope": PHASE_SCOPE,
        "quality_label": "smoke/demo quality only",
        "scientific_evidence_warning": "Cell_01-only training validates MLOps plumbing but does not prove cross-cell scientific generalization.",
        "future_split_standard": "grouped_by_cell_id",
    },
}

# Machine-safe repo column -> paper-facing label. If a later source check exposes a
# different exact paper/figure label, update this mapping and the generated CSV
# headers/metadata together.
PAPER_LABELS = {
    "pt_c_ratio": "Pt/C ratio",
    "i_c_ratio": "I/C ratio",
    "ionomer_ew": "Ionomer EW",
    "operating_rh": "Operating RH",
    "operating_voltage": "Voltage",
    "ast_rh": "AST RH",
    "ast_upl": "AST UPL",
    "bol_current_density": "BoL current density",
    "eol_current_density": "EoL current density",
    "bol_ecsa": "BoL ECSA",
    "ecsa_loss": "ECSA loss",
}

RH_MEASUREMENT_FOLDERS = {
    "03-IV-curve_RH100": 100,
    "06-IV-curve_RH70": 70,
    "08-IV-curve_RH40": 40,
}

EIS_H2AIR_FOLDERS = {
    "04-EIS_H2Air_RH100": 100,
    "07-EIS_H2Air_RH70": 70,
    "09-EIS_H2Air_RH40": 40,
}

REQUIRED_PHASE1_OUTPUTS = [
    "inventory_manifest.csv",
    "cell_metadata.csv",
    "polarization_long.csv",
    "ecsa_by_cycle.csv",
    "model_table.csv",
    "rejected_rows.csv",
]
