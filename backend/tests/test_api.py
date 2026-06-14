from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.domain_metadata import build_domain_metadata, infer_template_id
from app.services.replay_mapping import load_hidden_replay_pool


PROJECT_ID = "pem_fuel_cell_real_cathode_degradation"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def isolated_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DOE_EXPERIMENT_LOG_DIR", str(tmp_path / "experiment_logs"))
    monkeypatch.setenv("DOE_BO_CONFIG_DIR", str(tmp_path / "bo_configs"))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_input_row():
    return {
        "pt_c_ratio": 0.5,
        "i_c_ratio": 0.8,
        "ionomer_ew": 790,
        "operating_rh": 70,
        "operating_voltage": 0.6,
        "ast_rh": 100,
        "ast_upl": 1.15,
    }


def test_api_info(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Mirai DoE Engine API",
        "version": "0.1.0",
        "description": "Generic tabular experiment optimization backend",
    }


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert PROJECT_ID in payload["available_projects"]
    assert payload["models_loaded"] is True


def test_new_ingestion_session_uses_workspace_scoped_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("DOE_OBJECT_STORE_ROOT", str(tmp_path))
    from app.services import data_intake

    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", tmp_path)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", tmp_path / "intake")
    session = data_intake.session_workspace("client_a_project", "dataset_a", "session_a")

    assert session["root"].is_relative_to(tmp_path / "workspaces" / "mirai-engineering")


def test_projects(client):
    response = client.get("/projects")

    assert response.status_code == 200
    assert any(project["id"] == PROJECT_ID for project in response.json()["projects"])


def test_auth_required_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    with TestClient(app) as test_client:
        response = test_client.get("/projects")

    assert response.status_code == 401


def test_auth_required_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    with TestClient(app) as test_client:
        response = test_client.get("/projects", headers={"Authorization": "Bearer invalid-token"})

    assert response.status_code == 401


def test_auth_required_allows_test_token_and_filters_workspace(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "fraunhofer")
    with TestClient(app) as test_client:
        response = test_client.get("/projects", headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 200
    payload = response.json()
    assert any(project["id"] == PROJECT_ID for project in payload["projects"])
    assert {project["workspace_id"] for project in payload["projects"]} == {"fraunhofer"}
    assert {workspace["workspace_id"] for workspace in payload["workspaces"]} == {"fraunhofer"}


def test_auth_required_rejects_valid_token_without_workspace_claim(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "")
    with TestClient(app) as test_client:
        response = test_client.get("/projects", headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Workspace claim required"


def test_auth_required_rejects_cross_workspace_project_access(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "mirai-engineering")
    with TestClient(app) as test_client:
        response = test_client.get(f"/projects/{PROJECT_ID}/schema", headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 403


def test_workspace_claim_uses_only_verified_top_level_custom_jwt_claim():
    from app.auth import _workspace_from_claims

    assert _workspace_from_claims({"workspace_id": "fraunhofer", "public_metadata": {"workspace_id": "battery-demo"}}) == "fraunhofer"
    assert _workspace_from_claims({"metadata": {"workspace_id": "fraunhofer"}}) is None
    assert _workspace_from_claims({"public_metadata": {"workspace_id": "fraunhofer"}}) is None
    assert _workspace_from_claims({"org_id": "fraunhofer"}) is None


def test_project_schema(client):
    response = client.get(f"/projects/{PROJECT_ID}/schema")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == PROJECT_ID
    assert len(payload["inputs"]) == 7
    assert len(payload["outputs"]) == 4
    assert payload["inputs"][0]["name"] == "pt_c_ratio"
    assert payload["outputs"][0]["name"] == "bol_current_density"
    assert payload["domain_metadata"]["approval_status"] == "approved"
    assert payload["domain_metadata"]["template_id"] in {"fuel_cell", "generic_tabular_doe"}


def test_generic_tabular_doe_domain_metadata_uses_non_fuel_cell_names():
    schema = {
        "project_id": "generic_oem_formulation",
        "display_name": "Generic OEM Formulation",
        "inputs": [
            {"name": "mix_temperature", "label": "Mix temperature", "type": "continuous", "min": 20, "max": 90, "unit": "C"},
            {"name": "binder_fraction", "label": "Binder fraction", "type": "continuous", "min": 0.05, "max": 0.25, "unit": "fraction"},
        ],
        "outputs": [
            {"name": "tensile_strength", "label": "Tensile strength", "direction": "maximize", "unit": "MPa"},
            {"name": "defect_rate", "label": "Defect rate", "direction": "minimize", "unit": "%"},
        ],
    }

    assert infer_template_id(schema) == "generic_tabular_doe"
    metadata = build_domain_metadata(schema, approval_status="approved")
    assert metadata["template_id"] == "generic_tabular_doe"
    assert metadata["approval_status"] == "approved"
    variable_names = {variable["name"] for variable in metadata["variables"]}
    assert {"mix_temperature", "binder_fraction", "tensile_strength", "defect_rate"}.issubset(variable_names)
    recipes = metadata["ui_config"]["plot_recipes"]
    assert recipes
    assert all(recipe["safe"] for recipe in recipes)
    assert recipes[0]["kind"] == "parity"


def test_training_config_schema_accepts_advanced_hyperparameters():
    from app.schemas import TrainingRequestCreate

    payload = TrainingRequestCreate(
        training_config={
            "linear": {"include_mvlr": True, "fit_intercept": True, "include_ridge": True, "ridge_alphas": [0.1, 1.0]},
            "mlp": {
                "include": True,
                "architecture_family": "shared_trunk_multi_head",
                "hidden_layers": [128, 64],
                "trunk_layers": [128, 128],
                "head_layers": [64],
                "secondary_head_layers": [32],
                "activation": "GELU",
                "normalization": "layer_norm",
                "dropout": 0.1,
                "optimizer": "AdamW",
                "learning_rate": 0.001,
                "weight_decay": 0.0001,
                "batch_size": 128,
                "max_epochs": 500,
                "early_stopping_patience": 100,
                "loss": "weighted_smooth_l1",
                "output_weights": {"y": 1.0},
                "seeds": [7, 13],
            },
            "search": {"mode": "small_sweep_1h", "wall_clock_budget_minutes": 60, "rerun_top_k": 3},
            "selection_metric": "validation_weighted_normalized_rmse",
        }
    )

    assert payload.training_config.mlp.architecture_family == "shared_trunk_multi_head"
    assert payload.training_config.linear.include_ridge is True
    assert payload.model_families == ["mean_baseline", "mvlr", "ridge", "mlp"]


def test_approved_variable_metadata_overlays_schema_labels():
    from app.services.domain_metadata import apply_variable_metadata_to_schema

    schema = {
        "project_id": "generic_oem_formulation",
        "inputs": [{"name": "mix_temperature", "label": "Old temp", "type": "continuous", "min": 20, "max": 90, "unit": "C"}],
        "outputs": [{"name": "tensile_strength", "label": "Old strength", "direction": "maximize", "unit": "MPa"}],
        "domain_metadata": {
            "approval_status": "approved",
            "variables": [
                {"name": "mix_temperature", "label": "Mixer temperature", "unit": "°C", "role": "input"},
                {"name": "tensile_strength", "label": "Peak tensile strength", "unit": "N/mm²", "role": "output"},
            ],
        },
    }

    enriched = apply_variable_metadata_to_schema(schema)
    assert enriched["inputs"][0]["label"] == "Mixer temperature"
    assert enriched["inputs"][0]["unit"] == "°C"
    assert enriched["outputs"][0]["label"] == "Peak tensile strength"
    assert enriched["outputs"][0]["unit"] == "N/mm²"


def test_predict(client, valid_input_row):
    response = client.post(f"/projects/{PROJECT_ID}/predict", json={"inputs": valid_input_row})

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == PROJECT_ID
    assert payload["model_version"]
    assert set(payload["predictions"]) == {
        "bol_current_density",
        "eol_current_density",
        "bol_ecsa",
        "ecsa_loss",
    }
    assert payload["predictions"]["bol_current_density"] > 0
    assert payload["predictions"]["eol_current_density"] > 0
    assert isinstance(payload["warnings"], list)


def test_batch_predict(client, valid_input_row):
    response = client.post(
        f"/projects/{PROJECT_ID}/batch-predict",
        json={"inputs": [valid_input_row, {**valid_input_row, "pt_c_ratio": 0.35}]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == PROJECT_ID
    assert payload["model_version"]
    assert len(payload["predictions"]) == 2
    assert all("bol_ecsa" in prediction for prediction in payload["predictions"])


def test_recommend(client):
    response = client.post(
        f"/projects/{PROJECT_ID}/recommend",
        json={
            "objective_weights": {
                "bol_current_density": 0.35,
                "eol_current_density": 0.35,
                "ecsa_loss": -0.2,
            },
            "fixed_inputs": {
                "operating_rh": 70,
                "operating_voltage": 0.6,
            },
            "n_candidates": 200,
            "top_k": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == PROJECT_ID
    assert payload["model_version"]
    assert len(payload["recommendations"]) == 5

    scores = [item["score"] for item in payload["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    for item in payload["recommendations"]:
        assert item["inputs"]["operating_rh"] == pytest.approx(70)
        assert item["inputs"]["operating_voltage"] == pytest.approx(0.6)
        assert "predictions" in item


def test_bo_initialize_replay(isolated_client):
    response = isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/initialize-replay",
        json={"reset": True, "n_initial": 5, "selection": "diverse"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == PROJECT_ID
    assert payload["observed_count"] == 5
    assert payload["suggested_count"] == 0
    assert len(payload["history"]) == 5
    assert all(row["source"] == "initial_observed" for row in payload["history"])
    assert all(row["observed_outputs"] is not None for row in payload["history"])


def test_bo_suggestion_respects_constraints(isolated_client):
    isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/initialize-replay",
        json={"reset": True, "n_initial": 6, "selection": "diverse"},
    )

    response = isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/suggest",
        json={
            "objective_weights": {
                "bol_current_density": 0.35,
                "eol_current_density": 0.35,
                "ecsa_loss": -0.2,
            },
            "exploration_level": "balanced",
            "acquisition_function": "ei",
            "input_constraints": {
                "pt_c_ratio": {"fixed": 0.42},
                "operating_voltage": {"min": 0.45, "max": 0.65},
            },
            "n_suggestions": 1,
            "replay_mode": True,
        },
    )

    assert response.status_code == 200
    suggestion = response.json()["suggestion"]
    assert suggestion["status"] == "suggested"
    assert suggestion["observed_outputs"] is None
    assert suggestion["inputs"]["pt_c_ratio"] == pytest.approx(0.42)
    assert suggestion["inputs"]["operating_voltage"] == pytest.approx(0.45, abs=1e-12) or 0.45 <= suggestion["inputs"]["operating_voltage"] <= 0.65
    assert suggestion["predicted_outputs"] is not None
    assert suggestion["uncertainty"]["objective_std"] >= 0
    assert suggestion["objective"]["expected_improvement"] >= 0


def test_bo_reveal_uses_hidden_replay_outputs_not_predictions(isolated_client):
    isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/initialize-replay",
        json={"reset": True, "n_initial": 6, "selection": "diverse"},
    )
    suggest_response = isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/suggest",
        json={
            "objective_weights": {
                "bol_current_density": 0.35,
                "eol_current_density": 0.35,
                "ecsa_loss": -0.2,
            },
            "exploration_level": "balanced",
            "acquisition_function": "ei",
            "n_suggestions": 1,
            "replay_mode": True,
        },
    )
    experiment_id = suggest_response.json()["suggestion"]["experiment_id"]

    accept_response = isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/experiments/{experiment_id}/review",
        json={"decision": "accepted"},
    )
    assert accept_response.status_code == 200

    reveal_response = isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/experiments/{experiment_id}/reveal-replay-result"
    )

    assert reveal_response.status_code == 200
    payload = reveal_response.json()
    logged = payload["logged_experiment"]
    matched_replay_id = logged["metadata"]["matched_replay_id"]
    hidden_row = next(row for row in load_hidden_replay_pool(PROJECT_ID) if row["replay_id"] == matched_replay_id)

    assert logged["status"] == "observed"
    assert logged["source"] == "replay_revealed"
    assert logged["observed_outputs"] == pytest.approx(hidden_row["outputs"])
    assert logged["observed_outputs"] != logged["predicted_outputs"]
    assert payload["experiment"]["prediction_error"] is not None


def test_bo_rejected_suggestion_cannot_reveal(isolated_client):
    isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/initialize-replay",
        json={"reset": True, "n_initial": 6, "selection": "diverse"},
    )
    suggest_response = isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/suggest",
        json={
            "objective_weights": {
                "bol_current_density": 0.35,
                "eol_current_density": 0.35,
                "ecsa_loss": -0.2,
            },
            "exploration_level": "balanced",
            "acquisition_function": "ei",
            "n_suggestions": 1,
            "replay_mode": True,
        },
    )
    experiment_id = suggest_response.json()["suggestion"]["experiment_id"]

    isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/experiments/{experiment_id}/review",
        json={"decision": "rejected", "reason": "infeasible", "notes": "outside current protocol"},
    )
    reveal_response = isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/experiments/{experiment_id}/reveal-replay-result"
    )

    assert reveal_response.status_code == 400
    assert "cannot reveal" in reveal_response.json()["detail"]


def test_data_intake_legacy_fuel_cell_validation_endpoint_reports_mirai_contract_errors(client):
    response = client.post(
        "/data-intake/sessions",
        data={"project_name": "Validation Gate", "notes": "missing Mirai package files"},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert response.status_code == 200
    session = response.json()

    validation = client.get(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/fuel-cell-package/validation"
    )

    assert validation.status_code == 200
    payload = validation.json()
    assert payload["valid"] is False
    assert payload["package_type"] == "mirai_contract_package"
    assert payload["deprecated_endpoint"] is True
    assert any("mirai_manifest.json" in error for error in payload["errors"])
    assert any("data_dictionary.csv" in error for error in payload["errors"])


def test_generic_zip_package_blocks_path_traversal(client, tmp_path):
    archive = tmp_path / "mirai_package.zip"
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("../evil.txt", "nope")

    response = client.post(
        "/data-intake/sessions",
        data={"project_name": "Unsafe Zip"},
        files=[("files", ("mirai_package.zip", archive.read_bytes(), "application/zip"))],
    )
    assert response.status_code == 200
    session = response.json()

    start = client.post(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/preprocessing/start"
    )
    assert start.status_code == 200
    payload = start.json()
    assert payload["status"] == "failed_validation"
    assert any("Unsafe ZIP member" in error for error in payload["validation"]["errors"])


def test_generic_zip_package_queues_through_contract_validation(client, tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "fuel_cell_contract_package"
    archive = tmp_path / "mirai_package.zip"
    with ZipFile(archive, "w") as zip_file:
        for path in fixture.iterdir():
            zip_file.write(path, arcname=f"mirai_package/{path.name}")

    response = client.post(
        "/data-intake/sessions",
        data={"project_name": "Generic Zip"},
        files=[("files", ("mirai_package.zip", archive.read_bytes(), "application/zip"))],
    )
    assert response.status_code == 200
    session = response.json()
    assert session["ingestion_path"] == "generic_tabular_doe"
    assert session["status"] == "ready_for_contract_review"

    start = client.post(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/preprocessing/start"
    )
    assert start.status_code == 200
    payload = start.json()
    assert payload["package_type"] == "mirai_contract_package"
    assert payload["status"] in {"queued", "preprocessing_complete_needs_approval"}


def test_fixed_multitable_zip_package_materializes_model_table_via_api(client, tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "fuel_cell_fixed_multitable_package"
    archive = tmp_path / "mirai_fixed_multitable_package.zip"
    with ZipFile(archive, "w") as zip_file:
        for path in fixture.iterdir():
            zip_file.write(path, arcname=f"mirai_package/{path.name}")

    response = client.post(
        "/data-intake/sessions",
        data={"project_name": "Fraunhofer Fixed Multitable"},
        files=[("files", ("mirai_fixed_multitable_package.zip", archive.read_bytes(), "application/zip"))],
    )
    assert response.status_code == 200
    session = response.json()
    assert session["status"] == "ready_for_contract_review"

    # Exercise the pre-preprocessing fallback schema path first; preprocessing
    # must invalidate that cached fallback so project detail refreshes to the
    # generated contract schema after canonical artifacts are materialized.
    pre_schema = client.get(f"/projects/{session['project_id']}/schema")
    assert pre_schema.status_code == 200
    assert pre_schema.json()["inputs"][0]["name"] == "pt_c_ratio"

    domain_metadata = client.get(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/domain-metadata"
    )
    assert domain_metadata.status_code == 200
    variables = domain_metadata.json()["domain_metadata"]["variables"]
    assert [item["name"] for item in variables if item["role"] == "input"] == ["x1", "x2", "x3", "x4", "x5", "x6", "x7"]
    assert [item["name"] for item in variables if item["role"] == "output"] == ["y1", "y2", "y3", "y4"]
    assert variables[0]["source_name"] == "pt_c_ratio"

    metadata_approval = client.post(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/domain-metadata/approval",
        json={"approver": "test"},
    )
    assert metadata_approval.status_code == 200
    assert metadata_approval.json()["approval_status"] == "approved"

    start = client.post(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/preprocessing/start"
    )
    assert start.status_code == 200
    payload = start.json()
    assert payload["status"] in {"queued", "preprocessing_complete_needs_approval"}

    status = client.get(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/preprocessing/status"
    )
    assert status.status_code == 200
    final_payload = status.json()
    assert final_payload["status"] == "preprocessing_complete_needs_approval"
    assert final_payload["row_counts"]["model_table.csv"] == 8

    schema = client.get(f"/projects/{session['project_id']}/schema")
    assert schema.status_code == 200
    schema_payload = schema.json()
    assert [item["name"] for item in schema_payload["inputs"]] == ["x1", "x2", "x3", "x4", "x5", "x6", "x7"]
    assert [item["name"] for item in schema_payload["outputs"]] == ["y1", "y2", "y3", "y4"]
    assert schema_payload["inputs"][0]["source_name"] == "pt_c_ratio"
    assert schema_payload["outputs"][0]["source_name"] == "bol_current_density"

    report = client.get(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/preprocessing-report"
    )
    assert report.status_code == 200
    assert report.json()["canonical_artifacts"]["row_counts"]["model_table.csv"] == 8

    ydata = client.get(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/preprocessing/ydata-report.html"
    )
    assert ydata.status_code == 200
    assert "text/html" in ydata.headers["content-type"]

    final_metadata = client.get(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/domain-metadata"
    )
    assert final_metadata.status_code == 200
    assert final_metadata.json()["approval_status"] == "approved"

    preprocessing_approval = client.post(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/preprocessing-approval",
        json={"approver": "test"},
    )
    assert preprocessing_approval.status_code == 200
    assert preprocessing_approval.json()["approval"]["status"] == "approved_for_training"

    training_request = client.post(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/training-requests",
        json={"requested_by": "test", "preset": "smoke", "model_families": ["mean_baseline"]},
    )
    assert training_request.status_code == 200
    request_id = training_request.json()["training_request_id"]
    requests = client.get(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/training-requests"
    )
    assert requests.status_code == 200
    assert [item["training_request_id"] for item in requests.json()["training_requests"]] == [request_id]


def test_data_intake_can_append_missing_file_to_existing_session(client):
    response = client.post(
        "/data-intake/sessions",
        data={"project_name": "Append Missing", "notes": "initial"},
        files=[("files", ("data_overview.xlsx", b"fake workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
    )
    assert response.status_code == 200
    session = response.json()

    append = client.post(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/files",
        files=[("files", ("Cell_01.zip", b"not actually used here", "application/zip"))],
    )

    assert append.status_code == 200
    payload = append.json()
    assert len(payload["files"]) == 2
    assert any(file["filename"] == "Cell_01.zip" for file in payload["files"])


def test_training_request_gate_requires_preprocessing_report(client):
    response = client.post(
        "/data-intake/sessions",
        data={"project_name": "Training Gate", "notes": "no preprocessing yet"},
        files=[("files", ("data_dictionary_template.csv", b"column_name,role\nx,input\n", "text/csv"))],
    )
    assert response.status_code == 200
    session = response.json()

    training = client.post(
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}/sessions/{session['ingestion_session_id']}/training-requests",
        json={"requested_by": "Mirai admin", "preset": "balanced_training", "model_families": ["mvlr"]},
    )

    assert training.status_code in {400, 503}


def test_bo_fantasy_rollout_is_not_logged_as_observed(isolated_client):
    isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/initialize-replay",
        json={"reset": True, "n_initial": 6, "selection": "diverse"},
    )
    state_before = isolated_client.get(f"/projects/{PROJECT_ID}/bo/state").json()

    response = isolated_client.post(
        f"/projects/{PROJECT_ID}/bo/fantasy-rollout",
        json={
            "steps": 3,
            "config": {
                "objective_weights": {
                    "bol_current_density": 0.35,
                    "eol_current_density": 0.35,
                    "ecsa_loss": -0.2,
                },
                "exploration_level": "balanced",
                "acquisition_function": "ei",
                "n_suggestions": 1,
                "replay_mode": True,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["not_logged"] is True
    assert len(payload["fantasy_trajectory"]) == 3
    assert all(step["source"] == "mlp_fantasy" for step in payload["fantasy_trajectory"])
    assert all(step["predicted_outputs"] for step in payload["fantasy_trajectory"])

    state_after = isolated_client.get(f"/projects/{PROJECT_ID}/bo/state").json()
    assert len(state_after["history"]) == len(state_before["history"])
    assert state_after["observed_count"] == state_before["observed_count"]
