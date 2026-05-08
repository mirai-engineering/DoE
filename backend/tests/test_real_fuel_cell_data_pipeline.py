from __future__ import annotations

import csv
from pathlib import Path

import pytest

from training.build_real_fuel_cell_dataset import _default_paths, build_dataset
from training.real_fuel_cell_schema import DEFAULT_CELL_ID, MODEL_COLUMNS, RAW_CELL_DATA_ROOT, TESTING_OVERVIEW_XLSX


RAW_DATA_AVAILABLE = (RAW_CELL_DATA_ROOT / DEFAULT_CELL_ID).exists() and TESTING_OVERVIEW_XLSX.exists()

pytestmark = pytest.mark.skipif(
    not RAW_DATA_AVAILABLE,
    reason="local-only raw fuel-cell data is not available",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def test_cell_01_metadata_only(tmp_path):
    output_dir = tmp_path / "real-data"
    result = build_dataset(DEFAULT_CELL_ID, _default_paths(output_dir))

    assert result.row_counts["cell_metadata.csv"] == 1
    metadata = _read_csv(output_dir / "cell_metadata.csv")
    assert metadata == [
        {
            "cell_id": "Cell_01",
            "test_no": "1",
            "material_variation": "Ionomer to carbon ratio",
            "ast_variation": "UPL 0.95V 100% RH",
            "pt_loading_mg_cm2": "0.3839",
            "i_c_ratio": "0.5",
            "ionomer_ew_g_mol": "790",
            "pt_c_ratio_percent": "50",
            "pt_c_ratio_fraction": "0.5",
            "catalyst_type": "Pt (SUP1)",
            "support_type": "HSA",
            "ast_upl_v": "0.95",
            "ast_rh_percent": "100",
            "source_workbook": "data/Cathode Catalyst Degradation/02-Testing_overview/data_overview.xlsx",
            "source_workbook_row": "4",
            "phase_scope": "Cell_01 only",
        }
    ]


def test_model_table_matches_paper_schema_and_excludes_synthetic_outputs(tmp_path):
    output_dir = tmp_path / "real-data"
    result = build_dataset(DEFAULT_CELL_ID, _default_paths(output_dir))

    assert result.row_counts["model_table.csv"] == 57
    with (output_dir / "model_table.csv").open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames is not None
        assert reader.fieldnames[: len(MODEL_COLUMNS)] == MODEL_COLUMNS
        assert "durability_score" not in reader.fieldnames
        assert "cost_score" not in reader.fieldnames
        rows = list(reader)

    assert {row["cell_id"] for row in rows} == {"Cell_01"}
    assert {row["curve_variant"] for row in rows} == {"raw"}
    assert {row["schema_source"] for row in rows} == {"paper_7_input_4_output"}
    assert {row["pt_c_ratio"] for row in rows} == {"0.5"}
    assert {row["i_c_ratio"] for row in rows} == {"0.5"}
    assert {row["ionomer_ew"] for row in rows} == {"790"}
    assert {row["ast_rh"] for row in rows} == {"100"}
    assert {row["ast_upl"] for row in rows} == {"0.95"}
    assert {row["bol_ecsa"] for row in rows} == {"139.612564223"}
    assert float(rows[0]["ecsa_loss"]) == pytest.approx(0.325027677834, rel=1e-10)
    assert all(float(row["bol_current_density"]) >= 0 for row in rows)
    assert all(float(row["eol_current_density"]) >= 0 for row in rows)


def test_phase1_outputs_are_csv_only_no_replay_or_artifacts(tmp_path):
    output_dir = tmp_path / "real-data"
    result = build_dataset(DEFAULT_CELL_ID, _default_paths(output_dir))

    expected_files = {
        "inventory_manifest.csv",
        "cell_metadata.csv",
        "polarization_long.csv",
        "ecsa_by_cycle.csv",
        "model_table.csv",
        "rejected_rows.csv",
        "eis_h2n2_summary.csv",
        "eis_h2air_long.csv",
        "limiting_current_summary.csv",
        "lsv_summary.csv",
        "ast_trace_manifest.csv",
        "dataset_profile.json",
    }
    assert {path.name for path in output_dir.iterdir()} == expected_files
    assert not any("replay" in path.name.lower() for path in output_dir.iterdir())
    assert not any(path.suffix == ".onnx" for path in output_dir.iterdir())
    assert result.row_counts["inventory_manifest.csv"] == 194


def test_rejected_rows_record_extrapolation_and_negative_current(tmp_path):
    output_dir = tmp_path / "real-data"
    result = build_dataset(DEFAULT_CELL_ID, _default_paths(output_dir))

    assert result.row_counts["rejected_rows.csv"] == 9
    rejected = _read_csv(output_dir / "rejected_rows.csv")
    reasons = {row["reason"] for row in rejected}
    assert "voltage_outside_eol_overlap" in reasons
    assert "negative_current_density" in reasons
    assert {row["cell_id"] for row in rejected} == {"Cell_01"}
