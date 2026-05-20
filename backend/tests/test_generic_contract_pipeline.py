from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from mlflow.tracking import MlflowClient

from ml_lifecycle.ingesting.generic_tabular_doe.contract import ContractValidationError, load_and_validate_contract
from ml_lifecycle.ingesting.generic_tabular_doe.preprocessing import build_generic_preprocessing_artifacts
from ml_lifecycle.training.generic_tabular_doe.train import train_generic_project
from ml_lifecycle.ingesting.fuel_cell_doe_demo.schema import MODEL_COLUMNS, PAPER_INPUT_COLUMNS, PAPER_OUTPUT_COLUMNS
from app.services.training_requests import _copy_tree_contents


def _write_contract(root: Path, *, include_direction: bool = True) -> None:
    direction = "maximize" if include_direction else None
    manifest = {
        "manifest_version": "0.2",
        "project": {"project_id": "generic_widget", "display_name": "Generic Widget", "domain": "generic_tabular_doe", "template_id": "generic_tabular_doe"},
        "tables": [{"path": "model_table.csv", "table_type": "model_table", "primary_key": ["experiment_id"]}],
        "columns": [
            {"table": "model_table.csv", "name": "experiment_id", "role": "id", "dtype": "string", "unit": None, "required": True},
            {"table": "model_table.csv", "name": "batch_id", "role": "group", "dtype": "string", "unit": None, "required": True},
            {"table": "model_table.csv", "name": "temperature_c", "role": "input", "dtype": "float", "unit": "degC", "required": True, "allowed_min": 0, "allowed_max": 120},
            {"table": "model_table.csv", "name": "pressure_bar", "role": "input", "dtype": "float", "unit": "bar", "required": True, "allowed_min": 0, "allowed_max": 20},
            {"table": "model_table.csv", "name": "yield_pct", "role": "output", "dtype": "float", "unit": "%", "required": True, "allowed_min": 0, "allowed_max": 100, "direction": direction},
        ],
        "joins": [],
        "split_hints": {"group_key": "batch_id", "recommended_strategy": "grouped", "validation_fraction": 0.2, "holdout_fraction": 0.2},
    }
    (root / "mirai_manifest_template.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "data_dictionary_template.csv").write_text("table,path,column_name,role,dtype,unit,required\n", encoding="utf-8")


def test_generic_contract_preprocess_and_train(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    canonical = tmp_path / "canonical"
    artifacts = tmp_path / "artifacts"
    raw.mkdir()
    _write_contract(raw)
    rows = []
    for i in range(30):
        rows.append({"experiment_id": f"exp_{i}", "batch_id": f"batch_{i % 6}", "temperature_c": 20 + i, "pressure_bar": 1 + (i % 5), "yield_pct": 40 + i * 0.8})
    pd.DataFrame(rows).to_csv(raw / "model_table.csv", index=False)

    contract = load_and_validate_contract(raw)
    assert contract["project"]["template_id"] == "generic_tabular_doe"
    result = build_generic_preprocessing_artifacts(raw_root=raw, canonical_dir=canonical, artifact_dir=artifacts, project_id="generic_widget")
    assert result["row_count"] == 30
    schema = json.loads((artifacts / "schema.json").read_text())
    assert [item["name"] for item in schema["inputs"]] == ["temperature_c", "pressure_bar"]
    metrics = train_generic_project(project_id="generic_widget", data_dir=canonical, artifact_dir=artifacts, training_config={"mlflow": {"enabled": False}})
    assert metrics["generic_training"] is True
    assert (artifacts / "metrics_summary.json").exists()
    assert (artifacts / "models" / "mlp.onnx").exists()
    onnx_report = json.loads((artifacts / "models" / "mlp_onnx_report.json").read_text())
    assert onnx_report["verified"] is True
    assert onnx_report["max_abs_diff"] < 1e-4


def test_generic_training_logs_each_candidate_and_registers_only_best(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    canonical = tmp_path / "canonical"
    artifacts = tmp_path / "artifacts"
    tracking = tmp_path / "mlruns"
    raw.mkdir()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking.resolve().as_uri())
    _write_contract(raw)
    rows = []
    for i in range(48):
        rows.append({"experiment_id": f"exp_{i}", "batch_id": f"batch_{i % 8}", "temperature_c": 20 + i * 0.7, "pressure_bar": 1 + (i % 5), "yield_pct": 35 + i * 0.5 + (i % 3) * 0.2})
    pd.DataFrame(rows).to_csv(raw / "model_table.csv", index=False)

    build_generic_preprocessing_artifacts(raw_root=raw, canonical_dir=canonical, artifact_dir=artifacts, project_id="generic_widget_mlflow")
    metrics = train_generic_project(project_id="generic_widget_mlflow", data_dir=canonical, artifact_dir=artifacts, training_config={"mlp": {"include": True, "max_epochs": 5}})

    client = MlflowClient(tracking_uri=tracking.resolve().as_uri(), registry_uri=tracking.resolve().as_uri())
    experiment = client.get_experiment_by_name("generic_widget_mlflow")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert len(runs) == 7
    assert {run.data.tags.get("model_name") for run in runs} == {"mean_baseline", "mvlr", "ridge_alpha_0.01", "ridge_alpha_0.1", "ridge_alpha_1.0", "ridge_alpha_10.0", "mlp"}
    selected = [run for run in runs if run.data.tags.get("selected_candidate") == "true"]
    assert len(selected) == 1
    assert selected[0].data.tags.get("model_name") == metrics["best_model_name"]
    versions = client.search_model_versions("name = 'doe_surrogate_generic_widget_mlflow'")
    assert len(versions) == 1
    assert versions[0].run_id == selected[0].info.run_id
    challenger = client.get_model_version_by_alias("doe_surrogate_generic_widget_mlflow", "challenger")
    assert challenger.version == versions[0].version
    logged_models = client.search_logged_models([experiment.experiment_id])
    assert {model.name for model in logged_models} == {"sklearn_pipeline"}
    mlp_run = next(run for run in runs if run.data.tags.get("model_name") == "mlp")
    artifacts_for_mlp = client.list_artifacts(mlp_run.info.run_id, "onnx")
    assert {artifact.path for artifact in artifacts_for_mlp} == {"onnx/mlp.onnx", "onnx/mlp_onnx_report.json"}


def test_artifact_activation_skips_expanded_raw_csv_trees(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    for dirname in ["raw_reference_extracted", "raw_extractor_workspace", "01-Data"]:
        raw_dir = source / dirname / "nested"
        raw_dir.mkdir(parents=True)
        (raw_dir / "raw_generated.csv").write_text("x\n1\n", encoding="utf-8")
    (source / "metrics_summary.json").write_text("{}", encoding="utf-8")
    keep_dir = source / "models"
    keep_dir.mkdir()
    (keep_dir / "best.joblib").write_text("model", encoding="utf-8")

    _copy_tree_contents(source, target)

    assert (target / "metrics_summary.json").exists()
    assert (target / "models" / "best.joblib").exists()
    assert not list(target.rglob("raw_generated.csv"))
    assert not (target / "raw_reference_extracted").exists()
    assert not (target / "raw_extractor_workspace").exists()
    assert not (target / "01-Data").exists()


def test_incomplete_contract_blocks_preprocessing(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_contract(raw, include_direction=False)
    pd.DataFrame([{"experiment_id": "a", "batch_id": "b", "temperature_c": 25, "pressure_bar": 1, "yield_pct": 50}]).to_csv(raw / "model_table.csv", index=False)
    with pytest.raises(ContractValidationError) as exc:
        load_and_validate_contract(raw)
    assert "direction" in str(exc.value)


def test_real_pem_table_can_be_forced_through_contract_with_same_split_counts(tmp_path: Path) -> None:
    source = Path("../data/reference/pem_fuel_cell_cathode_degradation/training_artifacts/latest/model_table_preprocessed.csv")
    if not source.exists():
        pytest.skip("Real PEM preprocessing artifact is not available")
    raw = tmp_path / "raw"
    canonical = tmp_path / "canonical"
    artifacts = tmp_path / "artifacts"
    raw.mkdir()
    frame = pd.read_csv(source)
    upload = frame[["cell_id", "split", *MODEL_COLUMNS]].copy()
    upload.to_csv(raw / "model_table.csv", index=False)
    columns = [
        {"table": "model_table.csv", "name": "cell_id", "role": "group", "dtype": "string", "unit": None, "required": True},
        {"table": "model_table.csv", "name": "split", "role": "metadata", "dtype": "string", "unit": None, "required": True},
    ]
    columns.extend({"table": "model_table.csv", "name": name, "role": "input", "dtype": "float", "unit": "unitless", "required": True, "allowed_min": float(upload[name].min()), "allowed_max": float(upload[name].max())} for name in PAPER_INPUT_COLUMNS)
    columns.extend({"table": "model_table.csv", "name": name, "role": "output", "dtype": "float", "unit": "unitless", "required": True, "direction": "target", "allowed_min": float(upload[name].min()), "allowed_max": float(upload[name].max())} for name in PAPER_OUTPUT_COLUMNS)
    manifest = {
        "manifest_version": "0.2",
        "project": {"project_id": "pem_contract_validation", "display_name": "PEM Contract Validation", "domain": "fuel_cell", "template_id": "generic_tabular_doe"},
        "tables": [{"path": "model_table.csv", "table_type": "model_table", "primary_key": ["cell_id"]}],
        "columns": columns,
        "joins": [],
        "split_hints": {"predefined_split_column": "split", "recommended_strategy": "predefined_column"},
    }
    (raw / "mirai_manifest_template.json").write_text(json.dumps(manifest), encoding="utf-8")
    (raw / "data_dictionary_template.csv").write_text("table,path,column_name,role,dtype,unit,required\n", encoding="utf-8")
    result = build_generic_preprocessing_artifacts(raw_root=raw, canonical_dir=canonical, artifact_dir=artifacts, project_id="pem_contract_validation")
    assert result["row_count"] == len(upload)
    split_report = json.loads((artifacts / "split_report.json").read_text())
    assert split_report["split_counts"] == {str(k): int(v) for k, v in upload["split"].value_counts().to_dict().items()}
    schema = json.loads((artifacts / "schema.json").read_text())
    assert [item["name"] for item in schema["inputs"]] == PAPER_INPUT_COLUMNS
    assert [item["name"] for item in schema["outputs"]] == PAPER_OUTPUT_COLUMNS
