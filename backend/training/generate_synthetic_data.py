from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


PROJECT_ID = "pem_fuel_cell_demo"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = BACKEND_ROOT / "data" / "synthetic" / f"{PROJECT_ID}.csv"
ARTIFACT_DIR = BACKEND_ROOT / "artifacts" / PROJECT_ID
SCHEMA_PATH = ARTIFACT_DIR / "schema.json"


SCHEMA = {
    "project_id": PROJECT_ID,
    "display_name": "PEM Fuel Cell Demo",
    "description": "Synthetic tabular DoE demo project for surrogate KPI prediction.",
    "schema_version": "0.1.0",
    "allow_unknown_inputs": False,
    "inputs": [
        {
            "name": "pt_c_ratio",
            "label": "Pt/C ratio",
            "type": "continuous",
            "min": 0.2,
            "max": 0.6,
            "unit": "fraction",
        },
        {
            "name": "i_c_ratio",
            "label": "I/C ratio",
            "type": "continuous",
            "min": 0.5,
            "max": 1.2,
            "unit": "ratio",
        },
        {
            "name": "ionomer_ew",
            "label": "Ionomer equivalent weight",
            "type": "continuous",
            "min": 720,
            "max": 980,
            "unit": "g/mol",
        },
        {
            "name": "operating_rh",
            "label": "Operating relative humidity",
            "type": "continuous",
            "min": 40,
            "max": 100,
            "unit": "%",
        },
        {
            "name": "operating_voltage",
            "label": "Operating voltage",
            "type": "continuous",
            "min": 0.35,
            "max": 0.9,
            "unit": "V",
        },
        {
            "name": "ast_rh",
            "label": "AST relative humidity",
            "type": "continuous",
            "min": 40,
            "max": 100,
            "unit": "%",
        },
        {
            "name": "ast_upl",
            "label": "AST upper potential limit",
            "type": "continuous",
            "min": 0.95,
            "max": 1.15,
            "unit": "V",
        },
    ],
    "outputs": [
        {
            "name": "bol_current_density",
            "label": "BoL current density",
            "direction": "maximize",
            "unit": "A/cm²",
        },
        {
            "name": "eol_current_density",
            "label": "EoL current density",
            "direction": "maximize",
            "unit": "A/cm²",
        },
        {
            "name": "ecsa_loss",
            "label": "ECSA loss",
            "direction": "minimize",
            "unit": "fraction",
        },
        {
            "name": "durability_score",
            "label": "Durability score",
            "direction": "maximize",
            "unit": "-",
        },
        {
            "name": "cost_score",
            "label": "Cost score",
            "direction": "minimize",
            "unit": "-",
        },
    ],
}


def write_schema(path: Path = SCHEMA_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(SCHEMA, indent=2) + "\n", encoding="utf-8")


def _sample_inputs(rng: np.random.Generator, n_rows: int) -> dict[str, np.ndarray]:
    sampled: dict[str, np.ndarray] = {}
    for variable in SCHEMA["inputs"]:
        sampled[variable["name"]] = rng.uniform(float(variable["min"]), float(variable["max"]), n_rows)
    return sampled


def _generate_outputs(inputs: dict[str, np.ndarray], rng: np.random.Generator) -> dict[str, np.ndarray]:
    pt = inputs["pt_c_ratio"]
    ic = inputs["i_c_ratio"]
    ew = inputs["ionomer_ew"]
    operating_rh = inputs["operating_rh"]
    operating_voltage = inputs["operating_voltage"]
    ast_rh = inputs["ast_rh"]
    ast_upl = inputs["ast_upl"]

    pt_n = (pt - 0.2) / 0.4
    ic_n = (ic - 0.5) / 0.7
    ew_n = (ew - 720.0) / 260.0
    rh_n = (operating_rh - 40.0) / 60.0
    voltage_n = (operating_voltage - 0.35) / 0.55
    ast_rh_n = (ast_rh - 40.0) / 60.0
    upl_n = (ast_upl - 0.95) / 0.20

    pt_performance = 0.48 * (1.0 - np.exp(-3.2 * pt_n))
    ic_window = 0.32 * np.exp(-((ic - 0.86) / 0.22) ** 2)
    high_ic_penalty = 0.16 * np.maximum(ic - 0.98, 0.0) ** 2 / 0.22**2
    rh_window = 0.24 * np.exp(-((operating_rh - 82.0) / 26.0) ** 2)
    voltage_load = 0.95 * (1.0 - voltage_n) ** 0.72
    ew_window = 0.10 * np.exp(-((ew - 820.0) / 95.0) ** 2)

    bol_current_density = (
        0.52
        + voltage_load
        + pt_performance
        + ic_window
        + rh_window
        + ew_window
        + 0.08 * pt_n * ic_n
        - high_ic_penalty
        + rng.normal(0.0, 0.035, len(pt))
    )
    bol_current_density = np.clip(bol_current_density, 0.35, 2.75)

    ast_interaction = ast_rh_n * upl_n
    ecsa_loss = (
        0.035
        + 0.36 * upl_n**1.85
        + 0.13 * ast_interaction
        + 0.035 * pt_n * upl_n
        + 0.035 * np.maximum(ic_n - 0.72, 0.0)
        + rng.normal(0.0, 0.018, len(pt))
    )
    ecsa_loss = np.clip(ecsa_loss, 0.02, 0.78)

    durability_score = (
        1.03
        - 1.10 * ecsa_loss
        - 0.08 * ast_interaction
        + 0.045 * (1.0 - ew_n)
        + 0.025 * rh_n
        + rng.normal(0.0, 0.025, len(pt))
    )
    durability_score = np.clip(durability_score, 0.02, 1.0)

    eol_current_density = (
        bol_current_density * (0.90 - 0.58 * ecsa_loss)
        + 0.06 * durability_score
        - 0.03 * upl_n
        + rng.normal(0.0, 0.028, len(pt))
    )
    eol_current_density = np.minimum(eol_current_density, bol_current_density - 0.05)
    eol_current_density = np.clip(eol_current_density, 0.20, 2.55)

    cost_score = (
        0.16
        + 0.56 * pt_n
        + 0.17 * ew_n
        + 0.055 * ic_n
        + 0.025 * pt_n * ew_n
        + rng.normal(0.0, 0.025, len(pt))
    )
    cost_score = np.clip(cost_score, 0.04, 1.0)

    return {
        "bol_current_density": bol_current_density,
        "eol_current_density": eol_current_density,
        "ecsa_loss": ecsa_loss,
        "durability_score": durability_score,
        "cost_score": cost_score,
    }


def generate_dataset(n_rows: int = 8000, seed: int = 42) -> list[dict[str, float]]:
    rng = np.random.default_rng(seed)
    inputs = _sample_inputs(rng, n_rows)
    outputs = _generate_outputs(inputs, rng)

    rows: list[dict[str, float]] = []
    input_names = [item["name"] for item in SCHEMA["inputs"]]
    output_names = [item["name"] for item in SCHEMA["outputs"]]
    for index in range(n_rows):
        row = {name: float(inputs[name][index]) for name in input_names}
        row.update({name: float(outputs[name][index]) for name in output_names})
        rows.append(row)
    return rows


def write_dataset(rows: list[dict[str, float]], path: Path = DATA_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [item["name"] for item in SCHEMA["inputs"]] + [item["name"] for item in SCHEMA["outputs"]]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic tabular DoE data.")
    parser.add_argument("--n-rows", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.n_rows < 5000:
        raise ValueError("--n-rows must be at least 5000 for the demo dataset")

    write_schema()
    rows = generate_dataset(n_rows=args.n_rows, seed=args.seed)
    write_dataset(rows)
    print(f"Wrote {len(rows)} rows to {DATA_PATH}")
    print(f"Wrote schema to {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
