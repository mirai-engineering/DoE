from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from mlflow.tracking import MlflowClient

from ml_lifecycle.ingesting.generic_tabular_doe.contract import ContractValidationError, load_and_validate_contract
from ml_lifecycle.ingesting.generic_tabular_doe.preprocessing import build_generic_preprocessing_artifacts
from ml_lifecycle.training.generic_tabular_doe.train import train_generic_project
from app.services.training_requests import _copy_tree_contents

FUEL_CELL_INPUT_COLUMNS = ["pt_c_ratio", "i_c_ratio", "ionomer_ew", "operating_rh", "operating_voltage", "ast_rh", "ast_upl"]
FUEL_CELL_OUTPUT_COLUMNS = ["bol_current_density", "eol_current_density", "bol_ecsa", "ecsa_loss"]
FUEL_CELL_MODEL_COLUMNS = [*FUEL_CELL_INPUT_COLUMNS, *FUEL_CELL_OUTPUT_COLUMNS]
FIXED_FUEL_CELL_INPUT_COLUMNS = ["x1", "x2", "x3", "x4", "x5", "x6", "x7"]
FIXED_FUEL_CELL_OUTPUT_COLUMNS = ["y1", "y2", "y3", "y4"]


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
    (root / "mirai_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "data_dictionary.csv").write_text("table,path,column_name,role,dtype,unit,required\n", encoding="utf-8")


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


def test_generic_training_with_tiny_mlp_hpo_writes_artifacts_and_nested_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    canonical = tmp_path / "canonical"
    artifacts = tmp_path / "artifacts"
    tracking = tmp_path / "mlruns"
    raw.mkdir()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking.resolve().as_uri())
    monkeypatch.delenv("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW", raising=False)
    monkeypatch.delenv("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS", raising=False)
    _write_contract(raw)
    rows = []
    for i in range(36):
        rows.append({"experiment_id": f"exp_{i}", "batch_id": f"batch_{i % 6}", "temperature_c": 20 + i, "pressure_bar": 1 + (i % 5), "yield_pct": 40 + i * 0.8})
    pd.DataFrame(rows).to_csv(raw / "model_table.csv", index=False)

    build_generic_preprocessing_artifacts(raw_root=raw, canonical_dir=canonical, artifact_dir=artifacts, project_id="generic_widget_hpo")
    metrics = train_generic_project(
        project_id="generic_widget_hpo",
        data_dir=canonical,
        artifact_dir=artifacts,
        training_config={
            "mlp": {
                "include": True,
                "max_epochs": 2,
                "patience": 1,
                "seed": 7,
                "hpo_min_epochs": 1,
                "hpo_min_patience": 1,
                "hpo": {"enabled": True, "n_trials": 2, "seed": 7},
            },
        },
    )

    assert (artifacts / "mlp_hpo_trials.csv").exists()
    summary = json.loads((artifacts / "mlp_hpo_summary.json").read_text())
    assert summary["enabled"] is True
    assert summary["n_trials_completed"] == 2
    assert summary["selection_metric"] == "validation_weighted_normalized_rmse"
    assert metrics["models"]["mlp"]["mlp_hpo"]["best_trial"] in {0, 1}
    comparison = pd.read_csv(artifacts / "candidate_comparison.csv")
    mlp_row = comparison[comparison["model_name"] == "mlp"].iloc[0]
    assert bool(mlp_row["mlp_hpo_enabled"]) is True
    assert (artifacts / "models" / "mlp.onnx").exists()

    client = MlflowClient(tracking_uri=tracking.resolve().as_uri(), registry_uri=tracking.resolve().as_uri())
    experiment = client.get_experiment_by_name("generic_widget_hpo")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    hpo_runs = [run for run in runs if run.data.tags.get("candidate_role") == "hpo_trial"]
    assert len(hpo_runs) == 2
    assert {run.data.tags.get("selected_trial") for run in hpo_runs} == {"true", "false"}
    assert all(run.data.tags.get("model_name") == "mlp" for run in hpo_runs)
    mlp_candidate = next(run for run in runs if run.data.tags.get("model_name") == "mlp" and run.data.tags.get("candidate_role") != "hpo_trial")
    assert mlp_candidate.data.params["mlp_hpo_enabled"] == "True"
    assert mlp_candidate.data.tags["mlp_hpo_enabled"] == "true"


def test_generic_training_logs_each_candidate_and_registers_only_best(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    canonical = tmp_path / "canonical"
    artifacts = tmp_path / "artifacts"
    tracking = tmp_path / "mlruns"
    raw.mkdir()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking.resolve().as_uri())
    monkeypatch.delenv("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW", raising=False)
    monkeypatch.delenv("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS", raising=False)
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
    assert {model.name for model in logged_models} == {"sklearn_pipeline", "onnx_model"}
    mlp_run = next(run for run in runs if run.data.tags.get("model_name") == "mlp")
    artifacts_for_mlp = client.list_artifacts(mlp_run.info.run_id, "onnx")
    assert {artifact.path for artifact in artifacts_for_mlp} == {"onnx/mlp.onnx", "onnx/mlp_onnx_report.json"}


def test_artifact_activation_skips_expanded_raw_csv_trees(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    for dirname in ["raw_reference_extracted", "01-Data"]:
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
    assert not (target / "01-Data").exists()


def test_incomplete_contract_blocks_preprocessing(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_contract(raw, include_direction=False)
    pd.DataFrame([{"experiment_id": "a", "batch_id": "b", "temperature_c": 25, "pressure_bar": 1, "yield_pct": 50}]).to_csv(raw / "model_table.csv", index=False)
    with pytest.raises(ContractValidationError) as exc:
        load_and_validate_contract(raw)
    assert "direction" in str(exc.value)


def test_fuel_cell_contract_fixture_validates() -> None:
    fixture = Path(__file__).parent / "fixtures" / "fuel_cell_contract_package"
    contract = load_and_validate_contract(fixture)
    schema = contract["columns"]
    assert contract["project"]["template_id"] == "generic_tabular_doe"
    assert [column["name"] for column in schema if column["role"] == "input"] == FUEL_CELL_INPUT_COLUMNS
    assert [column["name"] for column in schema if column["role"] == "output"] == FUEL_CELL_OUTPUT_COLUMNS


def test_fixed_multitable_fuel_cell_contract_materializes_model_table(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "fuel_cell_fixed_multitable_package"
    canonical = tmp_path / "canonical"
    artifacts = tmp_path / "artifacts"

    contract = load_and_validate_contract(fixture)
    assert {table["path"] for table in contract["tables"]} == {"experiments.csv", "conditions.csv", "results.csv"}
    assert [join["keys"] for join in contract["joins"]] == [["experiment_id"], ["condition_id"]]

    result = build_generic_preprocessing_artifacts(raw_root=fixture, canonical_dir=canonical, artifact_dir=artifacts, project_id="pem_fuel_cell_fixed_multitable_demo")

    assert result["row_count"] == 8
    model_table = pd.read_csv(canonical / "model_table.csv")
    assert list(model_table[FIXED_FUEL_CELL_INPUT_COLUMNS].columns) == FIXED_FUEL_CELL_INPUT_COLUMNS
    assert list(model_table[FIXED_FUEL_CELL_OUTPUT_COLUMNS].columns) == FIXED_FUEL_CELL_OUTPUT_COLUMNS
    assert {"experiment_id", "condition_id", "campaign_id", "split"}.issubset(model_table.columns)
    row = model_table.loc[model_table["condition_id"] == "Cell_01_V060"].iloc[0]
    assert row["x1"] == pytest.approx(0.25)
    assert row["x5"] == pytest.approx(0.60)
    assert row["y1"] == pytest.approx(1.42)
    split_report = json.loads((artifacts / "split_report.json").read_text())
    assert split_report["strategy"] == "predefined_column"
    assert split_report["split_counts"] == {"train": 4, "validation": 2, "test": 2}


def test_client_native_source_names_map_to_variable_ids_and_metadata_excluded_from_training(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "client_native_variable_package"
    canonical = tmp_path / "canonical"
    artifacts = tmp_path / "artifacts"

    contract = load_and_validate_contract(fixture)
    assert [column["variable_id"] for column in contract["columns"] if column["role"] == "input"] == ["x1", "x2"]
    assert [column["variable_id"] for column in contract["columns"] if column["role"] == "output"] == ["y1", "y2"]

    result = build_generic_preprocessing_artifacts(raw_root=fixture, canonical_dir=canonical, artifact_dir=artifacts, project_id="client_native_variable_demo")
    assert result["row_count"] == 6
    model_table = pd.read_csv(canonical / "model_table.csv")
    assert {"x1", "x2", "y1", "y2", "operator_note", "client_batch"}.issubset(model_table.columns)
    assert "Pt/C ratio (%)" not in model_table.columns
    assert "@Quality Score" not in model_table.columns

    preprocessing = json.loads((artifacts / "preprocessing.json").read_text())
    assert preprocessing["input_order"] == ["x1", "x2"]
    assert preprocessing["output_order"] == ["y1", "y2"]
    assert "operator_note" not in preprocessing["input_order"]

    schema = json.loads((artifacts / "schema.json").read_text())
    assert [item["name"] for item in schema["inputs"]] == ["x1", "x2"]
    assert schema["inputs"][0]["source_name"] == "Pt/C ratio (%)"
    assert schema["inputs"][0]["label"] == "Pt/C ratio"
    assert {item["name"] for item in schema["metadata"]["variables"]} >= {"operator_note", "client_batch"}
    assert any(item["source_name"] == "@Quality Score" for item in schema["metadata"]["all_variables"])

    metrics = train_generic_project(project_id="client_native_variable_demo", data_dir=canonical, artifact_dir=artifacts, training_config={"mlflow": {"enabled": False}})
    assert metrics["generic_training"] is True
    assert len(metrics["input_order"]) == 2
    assert len(metrics["output_order"]) == 2


def test_fixed_source_package_rejects_semantic_or_gapped_model_variable_ids(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "client_native_variable_package"
    raw = tmp_path / "raw"
    _copy_tree_contents(fixture, raw)
    manifest_path = raw / "mirai_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for column in manifest["columns"]:
        if column.get("role") == "input" and column.get("source_name") == "Pt/C ratio (%)":
            column["variable_id"] = "pt_c_ratio"
            column["name"] = "pt_c_ratio"
        if column.get("role") == "output" and column.get("source_name") == "@Quality Score":
            column["variable_id"] = "y3"
            column["name"] = "y3"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ContractValidationError) as exc:
        load_and_validate_contract(raw)
    message = str(exc.value)
    assert "put domain names in ui_label/source_name" in message
    assert "contiguous y1..yN" in message


def test_fuel_cell_demo_shape_uses_generic_contract_with_same_split_counts(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    canonical = tmp_path / "canonical"
    artifacts = tmp_path / "artifacts"
    raw.mkdir()
    rows = []
    for i in range(36):
        rows.append(
            {
                "cell_id": f"Cell_{i % 6:02d}",
                "split": "test" if i % 6 == 0 else "validation" if i % 6 == 1 else "train",
                "pt_c_ratio": 0.2 + (i % 4) * 0.05,
                "i_c_ratio": 0.7 + (i % 3) * 0.1,
                "ionomer_ew": 700 + (i % 5) * 25,
                "operating_rh": 40 + (i % 4) * 20,
                "operating_voltage": 0.55 + (i % 5) * 0.03,
                "ast_rh": 30 + (i % 3) * 25,
                "ast_upl": 0.85 + (i % 4) * 0.02,
                "bol_current_density": 1.2 + i * 0.01,
                "eol_current_density": 1.0 + i * 0.008,
                "bol_ecsa": 60 - i * 0.2,
                "ecsa_loss": 5 + i * 0.1,
            }
        )
    upload = pd.DataFrame(rows)
    upload.to_csv(raw / "model_table.csv", index=False)
    columns = [
        {"table": "model_table.csv", "name": "cell_id", "role": "group", "dtype": "string", "unit": None, "required": True},
        {"table": "model_table.csv", "name": "split", "role": "metadata", "dtype": "string", "unit": None, "required": True},
    ]
    columns.extend({"table": "model_table.csv", "name": name, "role": "input", "dtype": "float", "unit": "unitless", "required": True, "allowed_min": -1, "allowed_max": 2000} for name in FUEL_CELL_INPUT_COLUMNS)
    columns.extend({"table": "model_table.csv", "name": name, "role": "output", "dtype": "float", "unit": "unitless", "required": True, "direction": "target", "allowed_min": -1, "allowed_max": 2000} for name in FUEL_CELL_OUTPUT_COLUMNS)
    manifest = {
        "manifest_version": "0.2",
        "project": {"project_id": "fuel_cell_contract_validation", "display_name": "Fuel Cell Contract Validation", "domain": "fuel_cell", "template_id": "generic_tabular_doe"},
        "tables": [{"path": "model_table.csv", "table_type": "model_table", "primary_key": ["cell_id"]}],
        "columns": columns,
        "joins": [],
        "split_hints": {"predefined_split_column": "split", "recommended_strategy": "predefined_column"},
    }
    (raw / "mirai_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (raw / "data_dictionary.csv").write_text("table,path,column_name,role,dtype,unit,required\n", encoding="utf-8")
    result = build_generic_preprocessing_artifacts(raw_root=raw, canonical_dir=canonical, artifact_dir=artifacts, project_id="fuel_cell_contract_validation")
    assert result["row_count"] == len(upload)
    split_report = json.loads((artifacts / "split_report.json").read_text())
    assert split_report["split_counts"] == {str(k): int(v) for k, v in upload["split"].value_counts().to_dict().items()}
    schema = json.loads((artifacts / "schema.json").read_text())
    assert [item["name"] for item in schema["inputs"]] == FUEL_CELL_INPUT_COLUMNS
    assert [item["name"] for item in schema["outputs"]] == FUEL_CELL_OUTPUT_COLUMNS
    assert (artifacts / "package_inventory.json").exists()
    assert not (artifacts / "raw_extractor_report.json").exists()
