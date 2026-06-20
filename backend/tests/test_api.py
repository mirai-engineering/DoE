import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.domain_metadata import attach_domain_metadata, build_domain_metadata, infer_template_id
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


@pytest.mark.anyio
async def test_create_ingestion_session_writes_project_scoped_object_metadata(tmp_path, monkeypatch):
    object_root = tmp_path / ".object-storage-local"
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(object_root))
    from app.services import data_intake
    from app.services.workspace_storage import WorkspaceStorageConfig

    monkeypatch.setattr(data_intake, "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", object_root / "intake")
    monkeypatch.setattr(data_intake, "postgres_control_plane_enabled", lambda: True)
    monkeypatch.setattr(
        data_intake,
        "ensure_project_record",
        lambda **kwargs: WorkspaceStorageConfig(
            workspace_id=kwargs["workspace_id"],
            mode="local",
            bucket="mirai-user-123-demo",
            prefix=f"workspaces/{kwargs['workspace_id']}/projects/{kwargs['project_id']}",
        ),
    )
    datasets = []
    artifacts = []
    monkeypatch.setattr(data_intake, "record_uploaded_dataset", lambda **kwargs: datasets.append(kwargs))
    monkeypatch.setattr(data_intake, "record_artifact_object", lambda **kwargs: artifacts.append(kwargs))

    class Upload:
        filename = "project.zip"
        content_type = "application/zip"

        def __init__(self):
            self._file = io.BytesIO(b"zip-bytes")

        async def read(self, size: int = -1):
            return self._file.read(size)

    session = await data_intake.create_ingestion_session(
        project_name="Pilot Project",
        uploads=[Upload()],
        workspace_name="Pilot Client",
        workspace_id="user_123",
        uploaded_by="user_123",
    )

    uploaded = session["files"][0]
    assert uploaded["bucket"] == "mirai-user-123-demo"
    assert uploaded["object_key"].startswith(f"workspaces/user_123/projects/{session['project_id']}/raw/{session['dataset_id']}/")
    assert uploaded["object_uri"].endswith(uploaded["object_key"])
    assert datasets[0]["workspace_id"] == "user_123"
    assert datasets[0]["object_uri"] == uploaded["object_uri"]
    assert artifacts[0]["artifact_kind"] == "raw_upload"


@pytest.mark.anyio
async def test_create_ingestion_session_requires_provisioned_storage_when_postgres_enabled(tmp_path, monkeypatch):
    object_root = tmp_path / ".object-storage-local"
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(object_root))
    from app.services import data_intake

    monkeypatch.setattr(data_intake, "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", object_root / "intake")
    monkeypatch.setattr(data_intake, "postgres_control_plane_enabled", lambda: True)
    monkeypatch.setattr(data_intake, "ensure_project_record", lambda **kwargs: (_ for _ in ()).throw(ValueError("Workspace storage is not provisioned yet")))

    class Upload:
        filename = "project.zip"
        content_type = "application/zip"

        async def read(self, size: int = -1):
            return b"zip-bytes"

    with pytest.raises(ValueError, match="not provisioned"):
        await data_intake.create_ingestion_session(
            project_name="Blocked Project",
            uploads=[Upload()],
            workspace_name="Blocked Client",
            workspace_id="user_without_bucket",
            uploaded_by="user_without_bucket",
        )


@pytest.mark.anyio
async def test_create_ingestion_session_uses_authenticated_workspace_id(tmp_path, monkeypatch):
    object_root = tmp_path / ".object-storage-local"
    monkeypatch.setenv("DOE_OBJECT_STORE_ROOT", str(object_root))
    from app.services import data_intake

    monkeypatch.setattr(data_intake, "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", object_root / "intake")

    class Upload:
        filename = "mirai_manifest.json"
        content_type = "application/json"

        def __init__(self):
            self._file = io.BytesIO(b"{}")

        async def read(self, size: int = -1):
            return self._file.read(size)

    session = await data_intake.create_ingestion_session(
        project_name="PEM Fuel Cell Cathode Degradation",
        uploads=[Upload()],
        existing_project_id=PROJECT_ID,
        workspace_name="Battery Demo",
        workspace_id="user_clerk_123",
    )

    assert session["workspace_id"] == "user_clerk_123"
    assert Path(session["storage"]["root"]).is_relative_to(
        Path(".object-storage-local") / "workspaces" / "user_clerk_123" / "intake" / "projects" / PROJECT_ID
    )


def test_projects(client):
    response = client.get("/projects")

    assert response.status_code == 200
    assert any(project["id"] == PROJECT_ID for project in response.json()["projects"])


def test_health_hides_project_fallbacks_when_auth_required(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    with TestClient(app) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 200
    assert response.json()["available_projects"] == []


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


def test_auth_required_does_not_derive_workspace_from_verified_clerk_subject(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_USER_ID", "fraunhofer")
    monkeypatch.delenv("CLERK_AUTH_TEST_WORKSPACE_ID", raising=False)
    with TestClient(app) as test_client:
        response = test_client.get("/projects", headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["projects"] == []
    assert payload["workspaces"] == []
    assert payload["account"]["status"] == "no_workspace_membership"


def test_auth_required_valid_user_without_workspace_row_lists_no_projects(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_USER_ID", "user_without_workspace")
    monkeypatch.delenv("CLERK_AUTH_TEST_WORKSPACE_ID", raising=False)
    with TestClient(app) as test_client:
        response = test_client.get("/projects", headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["projects"] == []
    assert payload["workspaces"] == []
    assert payload["account"]["status"] == "no_workspace_membership"
    assert payload["account"]["can_upload"] is False


def test_auth_required_valid_user_without_workspace_row_cannot_upload(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_USER_ID", "user_without_workspace")
    monkeypatch.delenv("CLERK_AUTH_TEST_WORKSPACE_ID", raising=False)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/data-intake/sessions",
            headers={"Authorization": "Bearer valid-test-token"},
            data={"project_name": "Blocked"},
            files=[("files", ("project.zip", b"zip", "application/zip"))],
        )

    assert response.status_code == 403
    assert response.json() == {"code": "no_workspace_membership", "detail": "Workspace membership required"}


def test_auth_required_valid_user_without_workspace_cannot_probe_project(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_USER_ID", "user_without_workspace")
    monkeypatch.delenv("CLERK_AUTH_TEST_WORKSPACE_ID", raising=False)
    with TestClient(app) as test_client:
        response = test_client.get(f"/projects/{PROJECT_ID}/schema", headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 403
    assert response.json() == {"code": "no_workspace_membership", "detail": "Workspace membership required"}


def test_auth_required_explicit_test_workspace_can_list_multiple_projects(monkeypatch):
    import app.main as main_module

    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_USER_ID", "user_multi_project")
    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "fraunhofer")

    def fake_list_projects(workspace_id=None):
        assert workspace_id == "fraunhofer"
        return [
            {"id": "project_a", "display_name": "Project A", "workspace_id": workspace_id, "workspace_name": "Fraunhofer"},
            {"id": "project_b", "display_name": "Project B", "workspace_id": workspace_id, "workspace_name": "Fraunhofer"},
        ]

    monkeypatch.setattr(main_module, "list_projects", fake_list_projects)
    with TestClient(app) as test_client:
        response = test_client.get("/projects", headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 200
    assert [project["id"] for project in response.json()["projects"]] == ["project_a", "project_b"]


def test_workspace_storage_assignment_rejects_escaping_prefix():
    from app.services.control_plane import assign_workspace_storage

    with pytest.raises(ValueError):
        assign_workspace_storage(workspace_id="user_123", bucket="mirai-user-123-demo", prefix="workspaces/user_456")


def test_auth_required_rejects_cross_workspace_existing_project_intake(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "other_workspace")
    with TestClient(app) as test_client:
        response = test_client.post(
            "/data-intake/sessions",
            headers={"Authorization": "Bearer valid-test-token"},
            data={"project_name": "Bad", "existing_project_id": PROJECT_ID},
            files=[("files", ("project.zip", b"zip", "application/zip"))],
        )

    assert response.status_code == 403


def test_auth_required_rejects_cross_workspace_project_access(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "mirai-engineering")
    with TestClient(app) as test_client:
        response = test_client.get(f"/projects/{PROJECT_ID}/schema", headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 403


def test_workspace_not_derived_from_claims_or_clerk_subject(monkeypatch):
    from app.auth import authenticate_bearer_token

    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_USER_ID", "user_123")
    monkeypatch.delenv("CLERK_AUTH_TEST_WORKSPACE_ID", raising=False)
    principal = authenticate_bearer_token("Bearer valid-test-token")
    assert principal.clerk_user_id == "user_123"
    assert principal.workspace_id is None


def test_authorized_party_validation_rejects_untrusted_origin(monkeypatch):
    from fastapi import HTTPException

    from app.auth import _verify_authorized_party

    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "https://app.example.com,http://localhost:5173")
    _verify_authorized_party({"azp": "https://app.example.com"})
    try:
        _verify_authorized_party({"azp": "https://evil.example.com"})
    except HTTPException as exc:
        assert exc.status_code == 401
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected unauthorized azp to be rejected")


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


def test_approved_domain_metadata_is_rebuilt_when_recipes_do_not_match_generic_schema():
    schema = {
        "project_id": "demo_ccm_degradation_cff1d4ae",
        "inputs": [{"name": "x1", "type": "continuous", "min": 0, "max": 1}],
        "outputs": [{"name": "y1", "direction": "maximize", "unit": ""}],
        "metadata": {"template_id": "generic_tabular_doe"},
        "domain_metadata": {
            "template_id": "fuel_cell",
            "approval_status": "approved",
            "variables": [],
            "ui_config": {
                "plot_recipes": [{"id": "fuel", "kind": "fuel_cell_polarization", "x": {"variables": ["bol_current_density"]}, "y": {"variable": "operating_voltage"}}],
                "model_quality": {"default_output": "bol_current_density"},
            },
        },
    }

    enriched = attach_domain_metadata(schema, template_id="generic_tabular_doe", approval_status="approved")

    assert enriched["domain_metadata"]["template_id"] == "generic_tabular_doe"
    assert enriched["domain_metadata"]["ui_config"]["model_quality"]["default_output"] == "y1"
    assert enriched["domain_metadata"]["ui_config"]["plot_recipes"][0]["kind"] == "parity"


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


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _prepare_export_fixture(tmp_path, monkeypatch, *, approved: bool = True, request_dataset_id: str | None = None):
    from app.services import data_intake

    object_root = tmp_path / "object-store"
    monkeypatch.setenv("DOE_OBJECT_STORE_ROOT", str(object_root))
    monkeypatch.setattr(data_intake, "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", object_root / "intake")

    project_id = "fraunhofer_export_project"
    dataset_id = "dataset_export"
    session_id = "ing_export"
    training_request_id = "train_req_export"
    workspace = data_intake.session_workspace(project_id, dataset_id, session_id)
    for path in workspace.values():
        path.mkdir(parents=True, exist_ok=True)

    session = {
        "project_id": project_id,
        "project_name": "Fraunhofer Export Project",
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "workspace_id": "fraunhofer",
        "status": "approved_for_training" if approved else "ready_for_contract_review",
        "files": [
            {
                "filename": "source.zip",
                "sha256": "source-sha-123",
                "size_bytes": 1234,
                "relative_path": "workspaces/fraunhofer/raw/source.zip",
            }
        ],
    }
    _write_json(workspace["root"] / "session.json", session)
    (workspace["canonical"] / "model_table.csv").write_text("x1,x2,y1\n1,2,3\n4,5,6\n", encoding="utf-8")
    (workspace["canonical"] / "raw_reference_extracted").mkdir(parents=True)
    (workspace["canonical"] / "raw_reference_extracted" / "secret.csv").write_text("do,not,export\n", encoding="utf-8")
    schema = {
        "project_id": project_id,
        "metadata": {"template_id": "generic_tabular_doe", "contract_version": "mirai-generic-0.1"},
        "inputs": [{"name": "x1"}, {"name": "x2"}],
        "outputs": [{"name": "y1"}],
    }
    _write_json(workspace["training_latest"] / "schema.json", schema)
    _write_json(workspace["training_latest"] / "preprocessing.json", {"version": "mirai-generic-0.1", "input_order": ["x1", "x2"], "output_order": ["y1"]})
    _write_json(
        workspace["eda"] / "preprocessing_report.json",
        {
            "project_id": project_id,
            "dataset_id": dataset_id,
            "ingestion_session_id": session_id,
            "status": "approved_for_training" if approved else "preprocessing_complete_needs_approval",
            "approval": {"status": "approved_for_training" if approved else "not_approved"},
            "canonical_artifacts": {"files": ["model_table.csv"], "row_counts": {"model_table.csv": 2}},
        },
    )
    _write_json(workspace["status"] / "preprocessing.json", {"status": "approved_for_training" if approved else "preprocessing_complete_needs_approval"})
    request = {
        "training_request_id": training_request_id,
        "project_id": project_id,
        "dataset_id": request_dataset_id or dataset_id,
        "ingestion_session_id": session_id,
        "status": "staged_for_mirai_execution",
        "requested_by": "test",
        "model_families": ["mean_baseline"],
    }
    _write_json(workspace["training_requests"] / f"{training_request_id}.json", request)
    return session | {"training_request_id": training_request_id}


def _auth_fraunhofer(monkeypatch):
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_USER_ID", "fraunhofer-user")
    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "fraunhofer")


def _export_url(session):
    return (
        f"/data-intake/projects/{session['project_id']}/datasets/{session['dataset_id']}"
        f"/sessions/{session['ingestion_session_id']}/training-requests/{session['training_request_id']}/export-package"
    )


def test_fraunhofer_member_can_export_approved_training_package(tmp_path, monkeypatch):
    import app.main as main_module

    session = _prepare_export_fixture(tmp_path, monkeypatch)
    _auth_fraunhofer(monkeypatch)
    monkeypatch.setattr(main_module, "list_projects", lambda workspace_id=None: [{"id": session["project_id"], "workspace_id": "fraunhofer"}] if workspace_id == "fraunhofer" else [])
    audit_events = []
    monkeypatch.setattr(main_module, "log_audit", lambda **kwargs: audit_events.append(kwargs))

    with TestClient(app) as test_client:
        response = test_client.get(_export_url(session), headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == ["model_table.csv", "schema.json", "training_manifest.json"]
        manifest = json.loads(archive.read("training_manifest.json"))
    assert manifest["workspace_id"] == "fraunhofer"
    assert manifest["project_id"] == session["project_id"]
    assert manifest["dataset_id"] == session["dataset_id"]
    assert manifest["session_id"] == session["ingestion_session_id"]
    assert manifest["training_request_id"] == session["training_request_id"]
    assert manifest["feature_columns"] == ["x1", "x2"]
    assert manifest["target_columns"] == ["y1"]
    assert manifest["source_checksums"]["source.zip"] == "source-sha-123"
    assert manifest["source_checksums"]["model_table.csv"]
    assert manifest["source_checksums"]["schema.json"]
    assert not any("bucket" in json.dumps(manifest).lower() or "object_key" in json.dumps(manifest).lower() for _ in [manifest])
    assert audit_events
    assert audit_events[0]["action"] == "approved_training_package_exported"
    assert audit_events[0]["metadata"]["package_size_bytes"] == len(response.content)
    assert audit_events[0]["metadata"]["package_sha256"]


def test_export_approved_training_package_unassigned_user_gets_no_workspace_403(tmp_path, monkeypatch):
    session = _prepare_export_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_USER_ID", "user_without_workspace")
    monkeypatch.delenv("CLERK_AUTH_TEST_WORKSPACE_ID", raising=False)

    with TestClient(app) as test_client:
        response = test_client.get(_export_url(session), headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 403
    assert response.json() == {"code": "no_workspace_membership", "detail": "Workspace membership required"}


def test_test_client_isolated_user_cannot_export_fraunhofer_package(tmp_path, monkeypatch):
    import app.main as main_module

    session = _prepare_export_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("CLERK_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CLERK_AUTH_TEST_TOKEN", "valid-test-token")
    monkeypatch.setenv("CLERK_AUTH_TEST_USER_ID", "isolated-user")
    monkeypatch.setenv("CLERK_AUTH_TEST_WORKSPACE_ID", "test-client-isolated")
    monkeypatch.setattr(main_module, "list_projects", lambda workspace_id=None: [])

    with TestClient(app) as test_client:
        response = test_client.get(_export_url(session), headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 403
    assert response.json()["code"] == "workspace_access_denied"


def test_export_approved_training_package_rejects_unapproved_preprocessing(tmp_path, monkeypatch):
    import app.main as main_module

    session = _prepare_export_fixture(tmp_path, monkeypatch, approved=False)
    _auth_fraunhofer(monkeypatch)
    monkeypatch.setattr(main_module, "list_projects", lambda workspace_id=None: [{"id": session["project_id"], "workspace_id": "fraunhofer"}])

    with TestClient(app) as test_client:
        response = test_client.get(_export_url(session), headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 400
    assert "approved" in response.json()["detail"]


def test_export_approved_training_package_rejects_mismatched_training_request(tmp_path, monkeypatch):
    import app.main as main_module

    session = _prepare_export_fixture(tmp_path, monkeypatch, request_dataset_id="dataset_other")
    _auth_fraunhofer(monkeypatch)
    monkeypatch.setattr(main_module, "list_projects", lambda workspace_id=None: [{"id": session["project_id"], "workspace_id": "fraunhofer"}])

    with TestClient(app) as test_client:
        response = test_client.get(_export_url(session), headers={"Authorization": "Bearer valid-test-token"})

    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"]


def test_frontend_export_helper_does_not_accept_storage_location_inputs():
    source = (Path(__file__).parents[2] / "frontend" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    start = source.index("export async function exportApprovedTrainingPackage")
    end = source.index("export async function predictExperiment", start)
    helper = source[start:end]
    assert "responseType: 'blob'" in helper
    assert "export-package" in helper
    assert "bucket" not in helper.lower()
    assert "object_key" not in helper.lower()
    assert "objectKey" not in helper
    assert "object_path" not in helper.lower()
    assert "objectPath" not in helper
    assert "presigned" not in helper.lower()


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
