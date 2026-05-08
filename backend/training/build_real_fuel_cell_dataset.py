from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import ZipFile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.real_fuel_cell_schema import (  # noqa: E402
    DEFAULT_CELL_ID,
    EIS_H2AIR_FOLDERS,
    MODEL_COLUMNS,
    OUTPUT_DIR,
    PAPER_LABELS,
    PHASE_SCOPE,
    PROJECT_ID,
    REPO_ROOT,
    RAW_CELL_DATA_ROOT,
    RAW_DATA_ROOT,
    REQUIRED_PHASE1_OUTPUTS,
    RH_MEASUREMENT_FOLDERS,
    SOURCE_PDF,
    TESTING_OVERVIEW_XLSX,
)

XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
CYCLE_RE = re.compile(r"^(\d+)cycles$")
RH_RE = re.compile(r"RH(\d+)")
LOAD_OR_VOLTAGE_RE = re.compile(r"^(\d+(?:mAcm2|mV)|cycling_[^/]+|galv_steady_state)$")


@dataclass(frozen=True)
class BuildPaths:
    source_root: Path
    cell_data_root: Path
    workbook_path: Path
    output_dir: Path
    source_pdf: Path


@dataclass(frozen=True)
class BuildResult:
    output_dir: Path
    row_counts: dict[str, int]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cell_number(cell_id: str) -> int:
    match = re.fullmatch(r"Cell_(\d{2})", cell_id)
    if not match:
        raise ValueError(f"Unsupported cell id for Phase 1: {cell_id!r}; expected Cell_01")
    return int(match.group(1))


def _enforce_phase1_cell(cell_id: str) -> None:
    if cell_id != DEFAULT_CELL_ID:
        raise ValueError(
            f"Phase 1 is intentionally scoped to {DEFAULT_CELL_ID}. "
            f"Refusing to process {cell_id}."
        )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _read_tab_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file, delimiter="\t"))


def _safe_float(value: object, *, field: str, path: Path | None = None) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        location = f" in {path}" if path else ""
        raise ValueError(f"Could not parse {field}{location}: {value!r}") from exc
    if not math.isfinite(number):
        location = f" in {path}" if path else ""
        raise ValueError(f"Non-finite {field}{location}: {value!r}")
    return number


def _format_number(value: float) -> str:
    return format(value, ".12g")


def _portable_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def _xlsx_shared_strings(zip_file: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []
    root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for si in root.findall("a:si", XLSX_NS):
        strings.append(
            "".join(
                text.text or ""
                for text in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
            )
        )
    return strings


def _xlsx_sheet_rows(path: Path, sheet_xml: str = "xl/worksheets/sheet1.xml") -> list[dict[str, str]]:
    with ZipFile(path) as zip_file:
        shared_strings = _xlsx_shared_strings(zip_file)
        root = ET.fromstring(zip_file.read(sheet_xml))

    rows: list[dict[str, str]] = []
    for row in root.findall(".//a:sheetData/a:row", XLSX_NS):
        values: dict[str, str] = {}
        for cell in row.findall("a:c", XLSX_NS):
            ref = cell.attrib.get("r", "")
            match = re.match(r"[A-Z]+", ref)
            if not match:
                continue
            column = match.group(0)
            value_node = cell.find("a:v", XLSX_NS)
            value = "" if value_node is None else value_node.text or ""
            if cell.attrib.get("t") == "s" and value:
                value = shared_strings[int(value)]
            values[column] = value
        rows.append(values)
    return rows


def parse_cell_metadata(cell_id: str, workbook_path: Path) -> dict[str, object]:
    _enforce_phase1_cell(cell_id)
    expected_test_no = _cell_number(cell_id)
    rows = _xlsx_sheet_rows(workbook_path)

    for row_index, row in enumerate(rows, start=1):
        test_no_raw = row.get("C", "").strip()
        if not test_no_raw:
            continue
        try:
            test_no = int(float(test_no_raw))
        except ValueError:
            continue
        if test_no != expected_test_no:
            continue

        pt_c_percent = _safe_float(row.get("G"), field="Pt/C ratio percent", path=workbook_path)
        metadata = {
            "cell_id": cell_id,
            "test_no": test_no,
            "material_variation": row.get("A", ""),
            "ast_variation": row.get("B", ""),
            "pt_loading_mg_cm2": _format_number(_safe_float(row.get("D"), field="Pt load", path=workbook_path)),
            "i_c_ratio": _format_number(_safe_float(row.get("E"), field="I/C ratio", path=workbook_path)),
            "ionomer_ew_g_mol": _format_number(_safe_float(row.get("F"), field="Ionomer EW", path=workbook_path)),
            "pt_c_ratio_percent": _format_number(pt_c_percent),
            "pt_c_ratio_fraction": _format_number(pt_c_percent / 100.0),
            "catalyst_type": row.get("H", ""),
            "support_type": row.get("I", ""),
            "ast_upl_v": _format_number(_safe_float(row.get("J"), field="AST UPL", path=workbook_path)),
            "ast_rh_percent": _format_number(_safe_float(row.get("K"), field="AST RH", path=workbook_path)),
            "source_workbook": _portable_path(workbook_path),
            "source_workbook_row": row_index,
            "phase_scope": PHASE_SCOPE,
        }
        return metadata

    raise ValueError(f"Could not find workbook row for {cell_id} / test number {expected_test_no}")


def _derive_relative_metadata(relative_path: Path) -> dict[str, object]:
    parts = relative_path.parts
    measurement_group = parts[0] if parts else ""
    cycle_count = ""
    operating_rh = ""
    load_or_voltage_condition = ""

    for part in parts:
        cycle_match = CYCLE_RE.match(part)
        if cycle_match:
            cycle_count = cycle_match.group(1)
        rh_match = RH_RE.search(part)
        if rh_match:
            operating_rh = rh_match.group(1)
        if LOAD_OR_VOLTAGE_RE.match(part):
            load_or_voltage_condition = part

    return {
        "measurement_group": measurement_group,
        "operating_rh": operating_rh,
        "cycle_count": cycle_count,
        "load_or_voltage_condition": load_or_voltage_condition,
        "file_kind": relative_path.stem,
    }


def _tabular_profile(path: Path) -> tuple[int, str, str, str]:
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.reader(file, delimiter="\t")
            header = next(reader, [])
            row_count = sum(1 for _ in reader)
        columns = "|".join(header)
        columns_hash = hashlib.sha256(columns.encode("utf-8")).hexdigest()[:16]
        return row_count, columns, columns_hash, "ok"
    except Exception as exc:  # noqa: BLE001 - inventory should record parse failures.
        return 0, "", "", f"error: {exc}"


def build_inventory(cell_id: str, cell_root: Path) -> list[dict[str, object]]:
    _enforce_phase1_cell(cell_id)
    if not cell_root.exists():
        raise FileNotFoundError(f"Cell data folder not found: {cell_root}")

    rows: list[dict[str, object]] = []
    for path in sorted(item for item in cell_root.rglob("*") if item.is_file()):
        if path.name == ".DS_Store" or "__MACOSX" in path.parts:
            continue
        relative_path = path.relative_to(cell_root)
        row_count, columns, columns_hash, parse_status = _tabular_profile(path) if path.suffix.lower() == ".csv" else (0, "", "", "skipped_non_csv")
        derived = _derive_relative_metadata(relative_path)
        rows.append(
            {
                "cell_id": cell_id,
                "source_container": _portable_path(cell_root),
                "relative_path": str(relative_path),
                **derived,
                "exists": True,
                "file_size_bytes": path.stat().st_size,
                "row_count": row_count,
                "columns": columns,
                "columns_hash": columns_hash,
                "parse_status": parse_status,
                "parse_warning": "",
            }
        )
    return rows


def _read_scalar_csv(path: Path, column: str) -> float:
    rows = _read_tab_csv(path)
    if not rows:
        raise ValueError(f"No rows in scalar CSV: {path}")
    return _safe_float(rows[0].get(column), field=column, path=path)


def build_ecsa_by_cycle(cell_id: str, cell_root: Path) -> list[dict[str, object]]:
    cv_root = cell_root / "10-CV"
    rows: list[dict[str, object]] = []
    for cycle_dir in sorted(cv_root.glob("*cycles"), key=lambda p: int(CYCLE_RE.match(p.name).group(1)) if CYCLE_RE.match(p.name) else -1):
        cycle_match = CYCLE_RE.match(cycle_dir.name)
        if not cycle_match:
            continue
        cycle_count = int(cycle_match.group(1))
        ecsa_path = cycle_dir / "ECSA_mean.csv"
        cdl_path = cycle_dir / "C_DL_mean.csv"
        parse_status = "ok"
        parse_warning = ""
        try:
            ecsa = _read_scalar_csv(ecsa_path, "ECSA_90mV_mean [cm2/cm2]")
            cdl = _read_scalar_csv(cdl_path, "C_DL_mean [mF/cm2]")
        except Exception as exc:  # noqa: BLE001
            ecsa = math.nan
            cdl = math.nan
            parse_status = "error"
            parse_warning = str(exc)
        rows.append(
            {
                "cell_id": cell_id,
                "cycle_count": cycle_count,
                "ecsa_90mv_mean_cm2_cm2": _format_number(ecsa) if math.isfinite(ecsa) else "",
                "c_dl_mean_mf_cm2": _format_number(cdl) if math.isfinite(cdl) else "",
                "source_ecsa_file": _portable_path(ecsa_path),
                "source_cdl_file": _portable_path(cdl_path),
                "parse_status": parse_status,
                "parse_warning": parse_warning,
            }
        )
    return rows


def _curve_rows(path: Path) -> list[tuple[int, float, float]]:
    rows: list[tuple[int, float, float]] = []
    for index, row in enumerate(_read_tab_csv(path), start=2):
        voltage = _safe_float(row.get("U.C[V]"), field="U.C[V]", path=path)
        current = _safe_float(row.get("I.C[A/cm2]"), field="I.C[A/cm2]", path=path)
        rows.append((index, voltage, current))
    return rows


def build_polarization_long(cell_id: str, cell_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    curve_files = [("raw", "IV_data.csv"), ("ir_corrected", "IV_data_IR_corr.csv")]
    for folder, rh in RH_MEASUREMENT_FOLDERS.items():
        folder_root = cell_root / folder
        for cycle_dir in sorted(folder_root.glob("*cycles"), key=lambda p: int(CYCLE_RE.match(p.name).group(1)) if CYCLE_RE.match(p.name) else -1):
            cycle_match = CYCLE_RE.match(cycle_dir.name)
            if not cycle_match:
                continue
            cycle_count = int(cycle_match.group(1))
            life_stage = "bol" if cycle_count == 0 else "eol" if cycle_count == 30000 else "intermediate"
            for curve_variant, filename in curve_files:
                path = cycle_dir / filename
                if not path.exists():
                    continue
                for source_row, voltage, current in _curve_rows(path):
                    rows.append(
                        {
                            "cell_id": cell_id,
                            "cycle_count": cycle_count,
                            "life_stage": life_stage,
                            "operating_rh_percent": rh,
                            "curve_variant": curve_variant,
                            "voltage_v": _format_number(voltage),
                            "current_density_a_cm2": _format_number(current),
                            "source_file": _portable_path(path),
                            "source_row": source_row,
                        }
                    )
    return rows


def _interpolate(x: float, points: list[tuple[int, float, float]]) -> tuple[float, int, int]:
    ordered = sorted(points, key=lambda item: item[1])
    min_x = ordered[0][1]
    max_x = ordered[-1][1]
    if x < min_x or x > max_x:
        raise ValueError(f"voltage {x} outside EoL overlap [{min_x}, {max_x}]")

    for row_index, xp, yp in ordered:
        if abs(x - xp) <= 1e-12:
            return yp, row_index, row_index

    for left, right in zip(ordered, ordered[1:]):
        left_row, x0, y0 = left
        right_row, x1, y1 = right
        if x0 <= x <= x1:
            if x1 == x0:
                return y0, left_row, right_row
            fraction = (x - x0) / (x1 - x0)
            return y0 + fraction * (y1 - y0), left_row, right_row

    raise ValueError(f"voltage {x} could not be interpolated")


def build_model_table(
    cell_id: str,
    cell_root: Path,
    metadata: dict[str, object],
    ecsa_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ecsa_by_cycle = {int(row["cycle_count"]): row for row in ecsa_rows if row.get("parse_status") == "ok"}
    ecsa_bol = _safe_float(ecsa_by_cycle[0]["ecsa_90mv_mean_cm2_cm2"], field="BoL ECSA")
    ecsa_eol = _safe_float(ecsa_by_cycle[30000]["ecsa_90mv_mean_cm2_cm2"], field="EoL ECSA")
    ecsa_loss = (ecsa_bol - ecsa_eol) / ecsa_bol

    model_rows: list[dict[str, object]] = []
    rejected_rows: list[dict[str, object]] = []

    for folder, rh in RH_MEASUREMENT_FOLDERS.items():
        bol_path = cell_root / folder / "0cycles" / "IV_data.csv"
        eol_path = cell_root / folder / "30000cycles" / "IV_data.csv"
        if not bol_path.exists() or not eol_path.exists():
            rejected_rows.append(
                {
                    "cell_id": cell_id,
                    "operating_rh": rh,
                    "operating_voltage": "",
                    "curve_variant": "raw",
                    "source_file": _portable_path(bol_path if not bol_path.exists() else eol_path),
                    "source_row": "",
                    "reason": "missing_bol_or_eol_curve",
                    "detail": "",
                }
            )
            continue

        bol_points = _curve_rows(bol_path)
        eol_points = _curve_rows(eol_path)
        for bol_source_row, bol_voltage, bol_current in bol_points:
            try:
                eol_current, eol_left_row, eol_right_row = _interpolate(bol_voltage, eol_points)
            except ValueError as exc:
                rejected_rows.append(
                    {
                        "cell_id": cell_id,
                        "operating_rh": rh,
                        "operating_voltage": _format_number(bol_voltage),
                        "curve_variant": "raw",
                        "source_file": _portable_path(bol_path),
                        "source_row": bol_source_row,
                        "reason": "voltage_outside_eol_overlap",
                        "detail": str(exc),
                    }
                )
                continue

            if bol_current < 0 or eol_current < 0:
                rejected_rows.append(
                    {
                        "cell_id": cell_id,
                        "operating_rh": rh,
                        "operating_voltage": _format_number(bol_voltage),
                        "curve_variant": "raw",
                        "source_file": _portable_path(bol_path),
                        "source_row": bol_source_row,
                        "reason": "negative_current_density",
                        "detail": f"bol={bol_current}, eol={eol_current}",
                    }
                )
                continue

            row = {
                "pt_c_ratio": metadata["pt_c_ratio_fraction"],
                "i_c_ratio": metadata["i_c_ratio"],
                "ionomer_ew": metadata["ionomer_ew_g_mol"],
                "operating_rh": rh,
                "operating_voltage": _format_number(bol_voltage),
                "ast_rh": metadata["ast_rh_percent"],
                "ast_upl": metadata["ast_upl_v"],
                "bol_current_density": _format_number(bol_current),
                "eol_current_density": _format_number(eol_current),
                "bol_ecsa": _format_number(ecsa_bol),
                "ecsa_loss": _format_number(ecsa_loss),
                "cell_id": cell_id,
                "test_no": metadata["test_no"],
                "pt_loading_mg_cm2": metadata["pt_loading_mg_cm2"],
                "pt_c_ratio_percent": metadata["pt_c_ratio_percent"],
                "catalyst_type": metadata["catalyst_type"],
                "support_type": metadata["support_type"],
                "curve_variant": "raw",
                "voltage_alignment_method": "bol_measured_voltage_with_eol_linear_interpolation_inside_overlap",
                "bol_source_file": _portable_path(bol_path),
                "bol_source_row": bol_source_row,
                "eol_source_file": _portable_path(eol_path),
                "eol_interpolation_left_source_row": eol_left_row,
                "eol_interpolation_right_source_row": eol_right_row,
                "ecsa_bol_source_file": ecsa_by_cycle[0]["source_ecsa_file"],
                "ecsa_eol_source_file": ecsa_by_cycle[30000]["source_ecsa_file"],
                "phase_scope": PHASE_SCOPE,
                "schema_source": "paper_7_input_4_output",
                "paper_labels_json": json.dumps(PAPER_LABELS, sort_keys=True),
            }
            model_rows.append(row)

    if ecsa_loss < 0:
        rejected_rows.append(
            {
                "cell_id": cell_id,
                "operating_rh": "",
                "operating_voltage": "",
                "curve_variant": "cv",
                "source_file": ecsa_by_cycle[30000]["source_ecsa_file"],
                "source_row": 2,
                "reason": "negative_ecsa_loss_requires_review",
                "detail": f"ecsa_bol={ecsa_bol}, ecsa_eol={ecsa_eol}, ecsa_loss={ecsa_loss}",
            }
        )

    return model_rows, rejected_rows


def build_eis_h2n2_summary(cell_id: str, cell_root: Path) -> list[dict[str, object]]:
    root = cell_root / "05-EIS_H2N2_RH100"
    rows: list[dict[str, object]] = []
    for voltage_dir in sorted(root.glob("*mV")):
        voltage_mv = int(voltage_dir.name.replace("mV", ""))
        for cycle_dir in sorted(voltage_dir.glob("*cycles"), key=lambda p: int(CYCLE_RE.match(p.name).group(1)) if CYCLE_RE.match(p.name) else -1):
            cycle_match = CYCLE_RE.match(cycle_dir.name)
            if not cycle_match:
                continue
            cycle_count = int(cycle_match.group(1))
            values: dict[str, object] = {
                "cell_id": cell_id,
                "dc_voltage_mv": voltage_mv,
                "cycle_count": cycle_count,
                "source_dir": _portable_path(cycle_dir),
            }
            scalar_specs = {
                "r_ion_mohm_cm2": ("R_ion.csv", "R_ion[mOhm*cm2]"),
                "hfr_mohm_cm2": ("HFR.csv", "HFR[mOhm*cm2]"),
                "c_dl_mf_cm2": ("C_DL.csv", "C_dl[mF*cm-2]"),
            }
            for output_name, (filename, column) in scalar_specs.items():
                path = cycle_dir / filename
                values[output_name] = _format_number(_read_scalar_csv(path, column)) if path.exists() else ""
                values[f"{output_name}_source_file"] = _portable_path(path)
            rows.append(values)
    return rows


def build_eis_h2air_long(cell_id: str, cell_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for folder, operating_rh in EIS_H2AIR_FOLDERS.items():
        folder_root = cell_root / folder
        for load_dir in sorted(folder_root.glob("*mAcm2")):
            load_ma_cm2 = int(load_dir.name.replace("mAcm2", ""))
            for cycle_dir in sorted(load_dir.glob("*cycles"), key=lambda p: int(CYCLE_RE.match(p.name).group(1)) if CYCLE_RE.match(p.name) else -1):
                cycle_match = CYCLE_RE.match(cycle_dir.name)
                if not cycle_match:
                    continue
                cycle_count = int(cycle_match.group(1))
                path = cycle_dir / "EIS_data_raw.csv"
                if not path.exists():
                    continue
                for source_row, row in enumerate(_read_tab_csv(path), start=2):
                    rows.append(
                        {
                            "cell_id": cell_id,
                            "operating_rh_percent": operating_rh,
                            "load_ma_cm2": load_ma_cm2,
                            "cycle_count": cycle_count,
                            "frequency_hz": row.get("f.C[Hz]", ""),
                            "z_re_mohm_cm2": row.get("Z.Re.C[mOhm*cm2]", ""),
                            "z_im_mohm_cm2": row.get("Z.Im.C[mOhm*cm2]", ""),
                            "source_file": _portable_path(path),
                            "source_row": source_row,
                        }
                    )
    return rows


def build_limiting_current_summary(cell_id: str, cell_root: Path) -> list[dict[str, object]]:
    root = cell_root / "02-Limiting_Current_Measurements"
    rows: list[dict[str, object]] = []
    for cycle_dir in sorted(root.glob("*cycles"), key=lambda p: int(CYCLE_RE.match(p.name).group(1)) if CYCLE_RE.match(p.name) else -1):
        cycle_match = CYCLE_RE.match(cycle_dir.name)
        if not cycle_match:
            continue
        cycle_count = int(cycle_match.group(1))
        r_p_indep_path = cycle_dir / "R_p_indep.csv"
        r_p_dep_path = cycle_dir / "R_p_dep.csv"
        r_p_indep = _read_scalar_csv(r_p_indep_path, "R_p_indep[s/m]") if r_p_indep_path.exists() else math.nan
        r_p_dep = _read_scalar_csv(r_p_dep_path, "R_p_dep[s/(m*bar)]") if r_p_dep_path.exists() else math.nan
        raw_path = cycle_dir / "iLim_data.csv"
        for source_row, row in enumerate(_read_tab_csv(raw_path), start=2):
            rows.append(
                {
                    "cell_id": cell_id,
                    "cycle_count": cycle_count,
                    "c_mean_mol_m3": row.get("c_mean[mol/m³]", ""),
                    "ilim_a_cm2": row.get("iLim[A/cm2]", ""),
                    "pressure_bar": row.get("p[bar]", ""),
                    "r_p_indep_s_m": _format_number(r_p_indep) if math.isfinite(r_p_indep) else "",
                    "r_p_dep_s_m_bar": _format_number(r_p_dep) if math.isfinite(r_p_dep) else "",
                    "source_file": _portable_path(raw_path),
                    "source_row": source_row,
                }
            )
    return rows


def build_lsv_summary(cell_id: str, cell_root: Path) -> list[dict[str, object]]:
    root = cell_root / "11-LSV"
    rows: list[dict[str, object]] = []
    for cycle_dir in sorted(root.glob("*cycles"), key=lambda p: int(CYCLE_RE.match(p.name).group(1)) if CYCLE_RE.match(p.name) else -1):
        cycle_match = CYCLE_RE.match(cycle_dir.name)
        if not cycle_match:
            continue
        cycle_count = int(cycle_match.group(1))
        source_file = cycle_dir / "I_xover.csv"
        i_xover = _read_scalar_csv(source_file, "I_xover_RANSAC [mA/cm2]") if source_file.exists() else math.nan
        rows.append(
            {
                "cell_id": cell_id,
                "cycle_count": cycle_count,
                "i_xover_ransac_ma_cm2": _format_number(i_xover) if math.isfinite(i_xover) else "",
                "source_file": _portable_path(source_file),
            }
        )
    return rows


def build_ast_trace_manifest(cell_id: str, cell_root: Path) -> list[dict[str, object]]:
    root = cell_root / "12-AST"
    rows: list[dict[str, object]] = []
    for path in sorted(root.glob("*cycles/pot_cycles_*.csv")):
        cycle_match = CYCLE_RE.match(path.parent.name)
        if not cycle_match:
            continue
        csv_rows = _read_tab_csv(path)
        times = [_safe_float(row.get("Time[s]"), field="Time[s]", path=path) for row in csv_rows]
        voltages = [_safe_float(row.get("U.C[V]"), field="U.C[V]", path=path) for row in csv_rows]
        currents = [_safe_float(row.get("I.C[A/cm2]"), field="I.C[A/cm2]", path=path) for row in csv_rows]
        rows.append(
            {
                "cell_id": cell_id,
                "cycle_count": int(cycle_match.group(1)),
                "trace_file": path.name,
                "source_file": _portable_path(path),
                "row_count": len(csv_rows),
                "time_min_s": _format_number(min(times)) if times else "",
                "time_max_s": _format_number(max(times)) if times else "",
                "voltage_min_v": _format_number(min(voltages)) if voltages else "",
                "voltage_max_v": _format_number(max(voltages)) if voltages else "",
                "current_min_a_cm2": _format_number(min(currents)) if currents else "",
                "current_max_a_cm2": _format_number(max(currents)) if currents else "",
            }
        )
    return rows


def _fieldnames(rows: list[dict[str, object]], preferred: Iterable[str]) -> list[str]:
    fields = list(preferred)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields


def build_dataset(cell_id: str, paths: BuildPaths, *, dry_run: bool = False) -> BuildResult:
    _enforce_phase1_cell(cell_id)
    cell_root = paths.cell_data_root / cell_id
    metadata = parse_cell_metadata(cell_id, paths.workbook_path)
    inventory = build_inventory(cell_id, cell_root)
    ecsa_by_cycle = build_ecsa_by_cycle(cell_id, cell_root)
    polarization_long = build_polarization_long(cell_id, cell_root)
    model_table, rejected_rows = build_model_table(cell_id, cell_root, metadata, ecsa_by_cycle)
    eis_h2n2_summary = build_eis_h2n2_summary(cell_id, cell_root)
    eis_h2air_long = build_eis_h2air_long(cell_id, cell_root)
    limiting_current_summary = build_limiting_current_summary(cell_id, cell_root)
    lsv_summary = build_lsv_summary(cell_id, cell_root)
    ast_trace_manifest = build_ast_trace_manifest(cell_id, cell_root)

    outputs: dict[str, tuple[list[str], list[dict[str, object]]]] = {
        "inventory_manifest.csv": (
            [
                "cell_id",
                "source_container",
                "relative_path",
                "measurement_group",
                "operating_rh",
                "cycle_count",
                "load_or_voltage_condition",
                "file_kind",
                "exists",
                "file_size_bytes",
                "row_count",
                "columns",
                "columns_hash",
                "parse_status",
                "parse_warning",
            ],
            inventory,
        ),
        "cell_metadata.csv": (_fieldnames([metadata], []), [metadata]),
        "polarization_long.csv": (
            [
                "cell_id",
                "cycle_count",
                "life_stage",
                "operating_rh_percent",
                "curve_variant",
                "voltage_v",
                "current_density_a_cm2",
                "source_file",
                "source_row",
            ],
            polarization_long,
        ),
        "ecsa_by_cycle.csv": (
            [
                "cell_id",
                "cycle_count",
                "ecsa_90mv_mean_cm2_cm2",
                "c_dl_mean_mf_cm2",
                "source_ecsa_file",
                "source_cdl_file",
                "parse_status",
                "parse_warning",
            ],
            ecsa_by_cycle,
        ),
        "model_table.csv": (_fieldnames(model_table, MODEL_COLUMNS), model_table),
        "rejected_rows.csv": (
            ["cell_id", "operating_rh", "operating_voltage", "curve_variant", "source_file", "source_row", "reason", "detail"],
            rejected_rows,
        ),
        "eis_h2n2_summary.csv": (_fieldnames(eis_h2n2_summary, ["cell_id", "dc_voltage_mv", "cycle_count"]), eis_h2n2_summary),
        "eis_h2air_long.csv": (
            [
                "cell_id",
                "operating_rh_percent",
                "load_ma_cm2",
                "cycle_count",
                "frequency_hz",
                "z_re_mohm_cm2",
                "z_im_mohm_cm2",
                "source_file",
                "source_row",
            ],
            eis_h2air_long,
        ),
        "limiting_current_summary.csv": (
            [
                "cell_id",
                "cycle_count",
                "c_mean_mol_m3",
                "ilim_a_cm2",
                "pressure_bar",
                "r_p_indep_s_m",
                "r_p_dep_s_m_bar",
                "source_file",
                "source_row",
            ],
            limiting_current_summary,
        ),
        "lsv_summary.csv": (["cell_id", "cycle_count", "i_xover_ransac_ma_cm2", "source_file"], lsv_summary),
        "ast_trace_manifest.csv": (_fieldnames(ast_trace_manifest, ["cell_id", "cycle_count", "trace_file", "source_file"]), ast_trace_manifest),
    }

    row_counts = {name: len(rows) for name, (_fields, rows) in outputs.items()}
    row_counts["phase1_required_outputs"] = len(REQUIRED_PHASE1_OUTPUTS)

    if not dry_run:
        paths.output_dir.mkdir(parents=True, exist_ok=True)
        for filename, (fieldnames, rows) in outputs.items():
            _write_csv(paths.output_dir / filename, fieldnames, rows)
        readme = {
            "project_id": PROJECT_ID,
            "phase_scope": PHASE_SCOPE,
            "generated_at": _utc_now(),
            "source_pdf": _portable_path(paths.source_pdf),
            "source_data_root": _portable_path(paths.source_root),
            "source_cell_ids": [cell_id],
            "raw_data_policy": "local-only raw data; generated CSV artifacts are audited derivatives",
            "model_columns": MODEL_COLUMNS,
            "paper_labels": PAPER_LABELS,
            "no_training_export_or_replay": True,
            "row_counts": row_counts,
        }
        (paths.output_dir / "dataset_profile.json").write_text(json.dumps(readme, indent=2) + "\n", encoding="utf-8")

    return BuildResult(output_dir=paths.output_dir, row_counts=row_counts)


def _default_paths(output_dir: Path | None = None) -> BuildPaths:
    return BuildPaths(
        source_root=RAW_DATA_ROOT,
        cell_data_root=RAW_CELL_DATA_ROOT,
        workbook_path=TESTING_OVERVIEW_XLSX,
        output_dir=output_dir or OUTPUT_DIR,
        source_pdf=SOURCE_PDF,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build audited Phase 1 real PEM fuel-cell CSV artifacts for Cell_01.")
    parser.add_argument("--cell-id", default=DEFAULT_CELL_ID, help="Phase 1 only supports Cell_01")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR, help="Output directory for audited CSV artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Parse and summarize without writing CSV files")
    parser.add_argument("--profile", action="store_true", help="Print generated row counts")
    args = parser.parse_args(argv)

    paths = _default_paths(args.output)
    result = build_dataset(args.cell_id, paths, dry_run=args.dry_run)

    if args.profile or args.dry_run:
        print(json.dumps({"output_dir": str(result.output_dir), "row_counts": result.row_counts}, indent=2))
    elif not args.dry_run:
        print(f"Wrote audited {args.cell_id} CSV artifacts to {result.output_dir}")


if __name__ == "__main__":
    main()
