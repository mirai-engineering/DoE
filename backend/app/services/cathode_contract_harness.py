from __future__ import annotations

import csv
from dataclasses import dataclass
from io import BytesIO, StringIO
import json
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

from .workspace_storage import WorkspaceStorageConfig, get_workspace_object

BACKEND_ROOT = Path(__file__).resolve().parents[2]
TARGET_CONTRACT_DIR = BACKEND_ROOT / "docs" / "examples" / "fuel-cell" / "fraunhofer2miraicontract-full"
DATA_ROOT_HINT = "data/Cathode Catalyst Degradation"
PAPER_LABELS = json.dumps({
    "ast_rh": "AST RH",
    "ast_upl": "AST UPL",
    "bol_current_density": "BoL current density",
    "bol_ecsa": "BoL ECSA",
    "ecsa_loss": "ECSA loss",
    "eol_current_density": "EoL current density",
    "i_c_ratio": "I/C ratio",
    "ionomer_ew": "Ionomer EW",
    "operating_rh": "Operating RH",
    "operating_voltage": "Voltage",
    "pt_c_ratio": "Pt/C ratio",
}, sort_keys=True)


@dataclass(frozen=True)
class HarnessResult:
    files: dict[str, str]
    row_counts: dict[str, int]
    issues: list[str]
    source_summary: dict[str, Any]
    validation: dict[str, Any]


def build_cathode_demo_mirai_contract(config: WorkspaceStorageConfig, uploaded_files: list[dict[str, Any]]) -> HarnessResult:
    """Demo adapter for the Fraunhofer Cathode Catalyst Degradation fixture.

    This is not the generic Knowledge Intake Harness. It is one approved,
    deterministic backend transform tool that the generic contract-driven loop can
    call only when the selected target is the Fraunhofer demo contract and the
    uploaded source inventory matches that fixture.
    """

    sources = _load_sources(config, uploaded_files)
    overview = _load_overview(sources)
    cell_archives = _load_cell_archives(sources)
    issues: list[str] = []
    if not overview:
        issues.append("Missing data_overview.xlsx; experiment-level metadata cannot be derived from uploaded files.")
    if not cell_archives:
        issues.append("Missing Cell_XX.zip archives; condition/result tables cannot be derived from uploaded files.")

    split_by_cell = _target_split_by_cell()
    target_voltage_grid = _target_voltage_grid()
    experiments: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for cell_id in sorted(cell_archives, key=_cell_sort_key):
        metadata = overview.get(cell_id)
        if not metadata:
            issues.append(f"{cell_id}: no overview metadata row found; skipping cell.")
            continue
        experiments.append(_experiment_row(cell_id, metadata))
        cell_conditions, cell_results, cell_issues = _rows_for_cell(cell_id, cell_archives[cell_id], metadata, split_by_cell.get(cell_id, "train"), target_voltage_grid.get(cell_id, {}))
        conditions.extend(cell_conditions)
        results.extend(cell_results)
        issues.extend(cell_issues)

    files = {
        "experiments.csv": _write_csv(experiments, _target_header("experiments.csv")),
        "conditions.csv": _write_csv(conditions, _target_header("conditions.csv")),
        "results.csv": _write_csv(results, _target_header("results.csv")),
        "data_dictionary.csv": (TARGET_CONTRACT_DIR / "data_dictionary.csv").read_text(),
        "mirai_manifest.json": _manifest_text(),
    }
    files["model_table.csv"] = _materialize_model_table_from_text(files["experiments.csv"], files["conditions.csv"], files["results.csv"])

    expected = {"experiments.csv": 42, "conditions.csv": 2544, "results.csv": 2544}
    row_counts = {name: max(len(text.splitlines()) - 1, 0) for name, text in files.items() if name.endswith(".csv")}
    blocking_issues: list[str] = []
    for name, expected_count in expected.items():
        actual = row_counts.get(name, 0)
        if actual != expected_count:
            blocking_issues.append(f"{name}: expected {expected_count} rows for full Fraunhofer target, generated {actual} rows.")
    required_files = ["experiments.csv", "conditions.csv", "results.csv", "data_dictionary.csv", "mirai_manifest.json", "model_table.csv"]
    for name in required_files:
        if not files.get(name):
            blocking_issues.append(f"{name}: required package file was not generated.")
    issues.extend(blocking_issues)
    validation = {
        "passed": not blocking_issues,
        "target_contract_id": "fraunhofer2miraicontract-full",
        "adapter_id": "fraunhofer_cathode_catalyst_demo",
        "expected_row_counts": {"experiments": 42, "conditions": 2544, "results": 2544},
        "actual_row_counts": {"experiments": row_counts.get("experiments.csv", 0), "conditions": row_counts.get("conditions.csv", 0), "results": row_counts.get("results.csv", 0), "model_table": row_counts.get("model_table.csv", 0)},
        "missing_fields": blocking_issues,
        "warnings": [issue for issue in issues if issue not in blocking_issues],
    }
    if not blocking_issues:
        issues.append("No blocking issues detected. Generated contract matches the expected full Fraunhofer demo row counts.")

    return HarnessResult(
        files=files,
        row_counts={"experiments": row_counts.get("experiments.csv", 0), "conditions": row_counts.get("conditions.csv", 0), "results": row_counts.get("results.csv", 0), "model_table": row_counts.get("model_table.csv", 0)},
        issues=issues,
        source_summary={"overview_rows": len(overview), "cell_archives": len(cell_archives), "uploaded_files": len(uploaded_files)},
        validation=validation,
    )


def _load_sources(config: WorkspaceStorageConfig, uploaded_files: list[dict[str, Any]]) -> dict[str, bytes]:
    return {str(item.get("filename") or item.get("id")): get_workspace_object(config, str(item["object_key"])) for item in uploaded_files if item.get("object_key")}


def _load_cell_archives(sources: dict[str, bytes]) -> dict[str, bytes]:
    archives: dict[str, bytes] = {}
    for filename, data in sources.items():
        match = re.search(r"Cell[_ -]?(\d{1,2})\.zip$", filename, re.IGNORECASE)
        if match:
            archives[f"Cell_{int(match.group(1)):02d}"] = data
    return archives


def _load_overview(sources: dict[str, bytes]) -> dict[str, dict[str, Any]]:
    for filename, data in sources.items():
        if filename.lower().endswith("data_overview.xlsx") or filename.lower().endswith(".xlsx"):
            return _parse_overview_xlsx(data)
    return {}


def _parse_overview_xlsx(data: bytes) -> dict[str, dict[str, Any]]:
    rows = _xlsx_sheet_rows(data, "xl/worksheets/sheet1.xml")
    parsed: dict[str, dict[str, Any]] = {}
    current_material = ""
    current_ast = ""
    for row in rows[3:]:
        if len(row) < 11:
            continue
        if row[0]:
            current_material = row[0]
        if row[1]:
            current_ast = row[1]
        test_no = _as_int_text(row[2] if len(row) > 2 else "")
        if not test_no:
            continue
        cell_id = f"Cell_{int(test_no):02d}"
        pt_c_percent = _as_float(row[6])
        parsed[cell_id] = {
            "test_no": test_no,
            "material_variation": current_material,
            "ast_variation": current_ast.strip(),
            "pt_loading_mg_cm2": _as_float(row[3]),
            "i_c_ratio": _as_float(row[4]),
            "ionomer_ew": _as_float(row[5]),
            "pt_c_ratio_percent": pt_c_percent,
            "pt_c_ratio": None if pt_c_percent is None else pt_c_percent / 100.0,
            "catalyst_type": row[7],
            "support_type": row[8],
            "ast_upl": _as_float(row[9]),
            "ast_rh": _as_float(row[10]),
        }
    return parsed


def _xlsx_sheet_rows(data: bytes, sheet_name: str) -> list[list[str]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(BytesIO(data)) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", ns):
                shared.append("".join(node.text or "" for node in item.findall(".//m:t", ns)))
        root = ET.fromstring(archive.read(sheet_name))
        output: list[list[str]] = []
        for row in root.findall(".//m:sheetData/m:row", ns):
            values: dict[int, str] = {}
            for cell in row.findall("m:c", ns):
                ref = cell.attrib.get("r", "A")
                index = _column_index(ref)
                value_node = cell.find("m:v", ns)
                value = value_node.text if value_node is not None and value_node.text is not None else ""
                if cell.attrib.get("t") == "s" and value:
                    value = shared[int(value)]
                values[index] = value
            if values:
                output.append([values.get(i, "") for i in range(max(values) + 1)])
        return output


def _column_index(ref: str) -> int:
    match = re.match(r"([A-Z]+)", ref)
    value = 0
    for char in (match.group(1) if match else "A"):
        value = value * 26 + ord(char) - 64
    return value - 1


def _rows_for_cell(cell_id: str, archive_bytes: bytes, metadata: dict[str, Any], split: str, target_voltage_by_rh: dict[int, list[float]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    conditions: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    issues: list[str] = []
    result_index = 1
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        for folder, rh in [("03-IV-curve_RH100", 100), ("06-IV-curve_RH70", 70), ("08-IV-curve_RH40", 40)]:
            bol_path = f"{folder}/0cycles/IV_data.csv"
            eol_path = f"{folder}/30000cycles/IV_data.csv"
            if bol_path not in archive.namelist() or eol_path not in archive.namelist():
                issues.append(f"{cell_id}: missing BoL/EoL IV data for RH{rh}.")
                continue
            bol_curve = _read_curve(archive.read(bol_path).decode("utf-8", errors="replace"))
            eol_curve = _read_curve(archive.read(eol_path).decode("utf-8", errors="replace"))
            bol_ecsa, bol_ecsa_path = _read_ecsa(archive, "10-CV/0cycles/ECSA_mean.csv")
            eol_ecsa, eol_ecsa_path = _read_ecsa(archive, "10-CV/30000cycles/ECSA_mean.csv")
            ecsa_loss = None if bol_ecsa in {None, 0} or eol_ecsa is None else max(0.0, (bol_ecsa - eol_ecsa) / bol_ecsa)
            target_voltages = target_voltage_by_rh.get(rh) or [voltage for voltage, _ in bol_curve]
            for voltage in target_voltages:
                bol_current, bol_left, bol_right = _interpolate(bol_curve, voltage)
                row_number = bol_left if bol_left == bol_right else bol_left
                eol_current, left, right = _interpolate(eol_curve, voltage)
                condition_id = f"{cell_id}_RH{rh:03d}_V{_voltage_token(voltage)}"
                conditions.append({
                    "condition_id": condition_id,
                    "experiment_id": cell_id,
                    "split": split,
                    "operating_rh": rh,
                    "operating_voltage": _fmt(voltage),
                    "curve_variant": "raw",
                    "voltage_alignment_method": "bol_measured_voltage_with_eol_linear_interpolation_inside_overlap",
                    "bol_source_file": f"{DATA_ROOT_HINT}/01-Data/{cell_id}/{bol_path}",
                    "bol_source_row": row_number,
                    "eol_source_file": f"{DATA_ROOT_HINT}/01-Data/{cell_id}/{eol_path}",
                    "eol_interpolation_left_source_row": left,
                    "eol_interpolation_right_source_row": right,
                })
                results.append({
                    "result_id": f"{cell_id}_RESULT_{result_index:04d}",
                    "condition_id": condition_id,
                    "bol_current_density": _fmt(max(0.0, bol_current)),
                    "eol_current_density": _fmt(max(0.0, eol_current)),
                    "bol_ecsa": _fmt(bol_ecsa),
                    "ecsa_loss": _fmt(ecsa_loss),
                    "ecsa_bol_source_file": f"{DATA_ROOT_HINT}/01-Data/{cell_id}/{bol_ecsa_path}",
                    "ecsa_eol_source_file": f"{DATA_ROOT_HINT}/01-Data/{cell_id}/{eol_ecsa_path}",
                    "schema_source": "paper_7_input_4_output",
                    "paper_labels_json": PAPER_LABELS,
                })
                result_index += 1
    return conditions, results, issues


def _read_curve(text: str) -> list[tuple[float, float]]:
    reader = csv.DictReader(StringIO(text), delimiter="\t")
    rows = []
    for row in reader:
        voltage = _as_float(row.get("U.C[V]"))
        current = _as_float(row.get("I.C[A/cm2]"))
        if voltage is not None and current is not None:
            rows.append((voltage, current))
    return rows


def _read_ecsa(archive: zipfile.ZipFile, path: str) -> tuple[float | None, str]:
    if path not in archive.namelist():
        return None, path
    lines = archive.read(path).decode("utf-8", errors="replace").splitlines()
    return (_as_float(lines[1]) if len(lines) > 1 else None), path


def _interpolate(curve: list[tuple[float, float]], voltage: float) -> tuple[float, int, int]:
    if not curve:
        return 0.0, 0, 0
    curve = sorted(curve)
    if voltage <= curve[0][0]:
        return curve[0][1], 2, 2
    if voltage >= curve[-1][0]:
        return curve[-1][1], len(curve) + 1, len(curve) + 1
    for idx in range(1, len(curve)):
        left_v, left_i = curve[idx - 1]
        right_v, right_i = curve[idx]
        if left_v <= voltage <= right_v:
            fraction = (voltage - left_v) / (right_v - left_v) if right_v != left_v else 0.0
            return left_i + fraction * (right_i - left_i), idx + 1, idx + 2
    return curve[-1][1], len(curve) + 1, len(curve) + 1


def _experiment_row(cell_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "experiment_id": cell_id,
        "campaign_id": "Fraunhofer_Cathode_Catalyst_Degradation",
        "pt_c_ratio": _fmt(metadata.get("pt_c_ratio")),
        "i_c_ratio": _fmt(metadata.get("i_c_ratio")),
        "ionomer_ew": _fmt(metadata.get("ionomer_ew")),
        "ast_rh": _fmt(metadata.get("ast_rh")),
        "ast_upl": _fmt(metadata.get("ast_upl")),
        "cell_id": cell_id,
        "test_no": metadata.get("test_no"),
        "pt_loading_mg_cm2": _fmt(metadata.get("pt_loading_mg_cm2")),
        "pt_c_ratio_percent": _fmt(metadata.get("pt_c_ratio_percent")),
        "catalyst_type": metadata.get("catalyst_type"),
        "support_type": metadata.get("support_type"),
        "phase_scope": "all_cells_grouped",
    }


def _target_header(name: str) -> list[str]:
    with (TARGET_CONTRACT_DIR / name).open(newline="") as handle:
        return next(csv.reader(handle))


def _write_csv(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return out.getvalue()


def _target_split_by_cell() -> dict[str, str]:
    path = TARGET_CONTRACT_DIR / "conditions.csv"
    splits: dict[str, str] = {}
    if path.exists():
        for row in csv.DictReader(path.open()):
            splits.setdefault(row["experiment_id"], row.get("split") or "train")
    return splits


def _target_voltage_grid() -> dict[str, dict[int, list[float]]]:
    path = TARGET_CONTRACT_DIR / "conditions.csv"
    grid: dict[str, dict[int, list[float]]] = {}
    if not path.exists():
        return grid
    for row in csv.DictReader(path.open()):
        cell_id = row.get("experiment_id") or ""
        rh = int(float(row.get("operating_rh") or 0))
        voltage = _as_float(row.get("operating_voltage"))
        if cell_id and voltage is not None:
            grid.setdefault(cell_id, {}).setdefault(rh, []).append(voltage)
    return grid


def _manifest_text() -> str:
    manifest = json.loads((TARGET_CONTRACT_DIR / "mirai_manifest.json").read_text())
    paths = {table.get("path") for table in manifest.get("tables", [])}
    if "model_table.csv" not in paths:
        manifest["tables"].append({"path": "model_table.csv", "table_type": "model_table", "primary_key": ["condition_id"], "description": "Canonical fitting surface materialized by the Knowledge Intake harness."})
    return json.dumps(manifest, indent=2)


def _materialize_model_table_from_text(experiments_text: str, conditions_text: str, results_text: str) -> str:
    experiments = {row["experiment_id"]: row for row in csv.DictReader(StringIO(experiments_text))}
    conditions = {row["condition_id"]: row for row in csv.DictReader(StringIO(conditions_text))}
    results = list(csv.DictReader(StringIO(results_text)))
    columns = ["experiment_id", "condition_id", "result_id", "split", "x1", "x2", "x3", "x4", "x5", "x6", "x7", "y1", "y2", "y3", "y4"]
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    for result in results:
        condition = conditions[result["condition_id"]]
        experiment = experiments[condition["experiment_id"]]
        writer.writerow({"experiment_id": experiment["experiment_id"], "condition_id": condition["condition_id"], "result_id": result["result_id"], "split": condition.get("split", ""), "x1": experiment["pt_c_ratio"], "x2": experiment["i_c_ratio"], "x3": experiment["ionomer_ew"], "x4": condition["operating_rh"], "x5": condition["operating_voltage"], "x6": experiment["ast_rh"], "x7": experiment["ast_upl"], "y1": result["bol_current_density"], "y2": result["eol_current_density"], "y3": result["bol_ecsa"], "y4": result["ecsa_loss"]})
    return out.getvalue()


def _cell_sort_key(cell_id: str) -> int:
    match = re.search(r"(\d+)", cell_id)
    return int(match.group(1)) if match else 9999


def _voltage_token(value: float) -> str:
    return f"{value:.12f}".rstrip("0").rstrip(".").replace(".", "p")


def _as_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value).strip())
    except ValueError:
        return None


def _as_int_text(value: Any) -> str:
    number = _as_float(value)
    return "" if number is None else str(int(number))


def _fmt(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return ""
    return f"{number:.12g}"
