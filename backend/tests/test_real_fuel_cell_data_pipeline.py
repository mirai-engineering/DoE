from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.services.project_registry import get_project_model_path
from ml_lifecycle.entrypoints.build_real_fuel_cell_dataset import _default_paths, build_dataset
from ml_lifecycle.entrypoints.preprocess_real_fuel_cell import build_preprocessing_artifacts
from ml_lifecycle.entrypoints.real_fuel_cell_schema import DEFAULT_CELL_ID, MLFLOW_MODEL_CACHE_DIR, MLFLOW_TRACKING_DIR, MODEL_COLUMNS, PROJECT_ID, RAW_CELL_DATA_ROOT, TESTING_OVERVIEW_XLSX, TRAINING_ARTIFACT_DIR
from ml_lifecycle.entrypoints.train_real_fuel_cell_models import train_models


RAW_DATA_AVAILABLE = (RAW_CELL_DATA_ROOT / DEFAULT_CELL_ID).exists() and TESTING_OVERVIEW_XLSX.exists()

pytestmark = pytest.mark.skipif(
    not RAW_DATA_AVAILABLE,
    reason="local-only raw fuel-cell data is not available",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


@pytest.fixture(autouse=True)
def preserve_packaged_model_artifacts(tmp_path):
    """Keep smoke-training tests from replacing the demo champion artifacts."""
    paths = [TRAINING_ARTIFACT_DIR / "latest", MLFLOW_TRACKING_DIR, MLFLOW_MODEL_CACHE_DIR]
    backups: list[tuple[Path, Path]] = []
    for index, path in enumerate(paths):
        if path.exists():
            backup = tmp_path / f"artifact-backup-{index}"
            shutil.copytree(path, backup)
            backups.append((path, backup))
    yield
    for path, backup in backups:
        if path.exists():
            shutil.rmtree(path)
        shutil.copytree(backup, path)


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
            "phase_scope": "all_cells_grouped",
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


def test_preprocessing_artifacts_use_grouped_all_cell_split_and_train_validation_bo_policy():
    result = build_preprocessing_artifacts(project_id=PROJECT_ID)
    artifact_dir = Path(result["artifact_dir"])
    preprocessing = __import__("json").loads((artifact_dir / "preprocessing.json").read_text())
    split_report = __import__("json").loads((artifact_dir / "split_report.json").read_text())

    assert preprocessing["input_imputer"]["method"] == "median"
    assert preprocessing["input_scaler"]["fit_scope"] == "train_split_only"
    assert split_report["future_standard"] == "grouped_by_cell_id"
    assert split_report["strategy"] == "metadata_aware_grouped_by_cell_id"
    assert "bo_holdout" not in split_report["split_cell_ids"]
    assert split_report["bo_holdout_policy"] == "not_reserved; BO uses train+validation and keeps test untouched"
    assert split_report["bo_replay"]["source"] == "train_validation_rows"
    assert set(split_report["split_cell_ids"]["train"]).isdisjoint(split_report["split_cell_ids"]["validation"])
    assert set(split_report["split_cell_ids"]["test"]).isdisjoint(split_report["split_cell_ids"]["train"])
    assert set(split_report["split_cell_ids"]["test"]).isdisjoint(split_report["split_cell_ids"]["validation"])


def test_mlflow_training_registry_and_runtime_resolution():
    result = train_models(project_id=PROJECT_ID, register_mlflow=True, epochs=5)

    assert result["production_model"] is None
    assert result["alias_model"]["alias"] == "challenger"
    assert result["best_model_name"] == "mvlr" or result["best_model_name"] == "mlp" or result["best_model_name"].startswith("ridge_alpha_")
    artifact_dir = Path(result["artifact_dir"])
    predictions_path = artifact_dir / "predictions.csv"
    assert predictions_path.exists()
    prediction_rows = _read_csv(predictions_path)
    assert prediction_rows
    prediction_model_names = {row["model_name"] for row in prediction_rows}
    assert {"mvlr", "mlp"}.issubset(prediction_model_names)
    assert any(name.startswith("ridge_alpha_") for name in prediction_model_names)
    assert "bo_holdout" not in {row["split"] for row in prediction_rows}
    assert "bol_current_density_true" in prediction_rows[0]
    assert "bol_current_density_pred" in prediction_rows[0]
    assert "operating_voltage" in prediction_rows[0]
    metrics = __import__("json").loads(Path(result["metrics_summary_path"]).read_text())
    assert "mean_baseline" in metrics["models"]
    assert metrics["best_model_type"] in {"multi_output_linear_regression", "ridge_regression", "scientific_tabular_ann"}
    output_metrics = metrics["models"][result["best_model_name"]]["splits"]["test"]["bol_current_density"]
    assert output_metrics["unit"] == "A/cm²"
    assert "baseline_improvement_mae_percent" in output_metrics
    assert "mae_percent_of_split_mean" in output_metrics
    model_path = get_project_model_path(PROJECT_ID)
    assert model_path.exists()
    assert model_path.suffix == ".onnx"


def test_business_impact_api_contracts():
    with TestClient(app) as client:
        response = client.get(f"/projects/{PROJECT_ID}/impact/summary")
        assert response.status_code == 200
        summary = response.json()
        assert summary["project_id"] == PROJECT_ID
        assert summary["case_study"]["physical_cells_in_repo"] >= 40
        assert summary["scenario"]["saved_bench_hours"] > 1000
        assert summary["scenario"]["external_capacity_value_saved_usd"]["low"] > 0
        assert summary["sources"]
        assert summary["caveats"]


def test_business_impact_api_supports_fraunhofer_fuel_cell_demo_alias():
    with TestClient(app) as client:
        response = client.get("/projects/fuel_cell_demo_65248559/impact/summary")
        assert response.status_code == 200
        summary = response.json()
        assert summary["project_id"] == "fuel_cell_demo_65248559"
        assert summary["scenario"]["baseline_physical_recipes"] >= 40
        assert summary["scenario"]["saved_bench_hours"] > 1000


def test_model_quality_api_contracts():
    train_models(project_id=PROJECT_ID, register_mlflow=True, epochs=5)
    with TestClient(app) as client:
        summary_response = client.get(f"/projects/{PROJECT_ID}/model-quality/summary")
        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["project_id"] == PROJECT_ID
        assert summary["quality_label"] == "all-cells MVP"
        best_model_name = summary["metrics"]["best_model_name"]
        assert best_model_name == "mvlr" or best_model_name == "mlp" or best_model_name.startswith("ridge_alpha_")
        assert summary["artifact_summary"]["prediction_diagnostics_available"] is True
        assert "champion" in summary["active_model"]["aliases"]
        assert summary["ai_preprocessing_assistant"]["status"] == "placeholder_not_active"

        predictions_response = client.get(f"/projects/{PROJECT_ID}/model-quality/predictions?model_name=mlp&splits=validation,test&limit=25")
        assert predictions_response.status_code == 200
        predictions = predictions_response.json()
        assert predictions["source"] == "training_run_predictions"
        assert predictions["rows"]
        assert set(predictions["columns"]) >= {"model_name", "split", "operating_voltage", "bol_current_density_true", "bol_current_density_pred"}

        export_response = client.get(f"/projects/{PROJECT_ID}/model-quality/predictions/export.zip?model_name=mlp&splits=validation,test")
        assert export_response.status_code == 200
        assert export_response.headers["content-type"] == "application/zip"
        assert export_response.content.startswith(b"PK")

        design_state_response = client.get(f"/projects/{PROJECT_ID}/design-studio/state")
        assert design_state_response.status_code == 200
        design_state = design_state_response.json()
        assert design_state["default_objective_weights"] == {"bol_current_density": 1.0}
        voltage_grid = design_state["presets"]["fuel_cell_polarization"]["observed_voltage_grid"]
        assert len(voltage_grid) > 5
        assert design_state["real_cell_options"]

        default_inputs = design_state["default_inputs"]
        design_predict_response = client.post(f"/projects/{PROJECT_ID}/design-studio/predict", json={"inputs": default_inputs})
        assert design_predict_response.status_code == 200
        design_prediction = design_predict_response.json()
        assert design_prediction["source"] == "served_model_prediction"
        assert len(design_prediction["curve"]["rows"]) == len(voltage_grid)
        assert "bol_current_density" in design_prediction["predictions_at_selected_point"]

        seed_response = client.post(f"/projects/{PROJECT_ID}/design-studio/seed/batch", json={"n_candidates": 50})
        assert seed_response.status_code == 200
        assert seed_response.json()["seed"]["source"] == "batch_search"

        pareto_response = client.post(
            f"/projects/{PROJECT_ID}/design-studio/pareto",
            json={"n_candidates": 80, "max_results": 6, "objective_weights": {"bol_current_density": 0.4, "eol_current_density": 0.4, "ecsa_loss": -0.2}},
        )
        assert pareto_response.status_code == 200
        pareto = pareto_response.json()
        assert pareto["source"] == "pareto_tradeoff_search"
        assert pareto["candidates"]
        assert pareto["pareto_count"] >= pareto["returned_count"]
        assert {objective["name"] for objective in pareto["objectives"]} == {"bol_current_density", "eol_current_density", "ecsa_loss"}
        assert "inputs" in pareto["candidates"][0]
        assert "predictions" in pareto["candidates"][0]

        design_export_response = client.post(f"/projects/{PROJECT_ID}/design-studio/export.zip", json={"inputs": default_inputs})
        assert design_export_response.status_code == 200
        assert design_export_response.headers["content-type"] == "application/zip"
        assert design_export_response.content.startswith(b"PK")

        review_response = client.post(
            f"/projects/{PROJECT_ID}/model-quality/scientist-review",
            json={"decision": "approved", "status": "reviewed", "reviewer": "pytest"},
        )
        assert review_response.status_code == 200
        assert review_response.json()["decision"] == "approved"
