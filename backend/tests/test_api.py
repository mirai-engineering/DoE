import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.replay_mapping import load_hidden_replay_pool


PROJECT_ID = "pem_fuel_cell_demo"


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


def test_projects(client):
    response = client.get("/projects")

    assert response.status_code == 200
    assert {"id": PROJECT_ID, "display_name": "PEM Fuel Cell Demo"} in response.json()["projects"]


def test_project_schema(client):
    response = client.get(f"/projects/{PROJECT_ID}/schema")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == PROJECT_ID
    assert len(payload["inputs"]) == 7
    assert len(payload["outputs"]) == 5
    assert payload["inputs"][0]["name"] == "pt_c_ratio"
    assert payload["outputs"][0]["name"] == "bol_current_density"


def test_predict(client, valid_input_row):
    response = client.post(f"/projects/{PROJECT_ID}/predict", json={"inputs": valid_input_row})

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == PROJECT_ID
    assert payload["model_version"] == "pem_fuel_cell_demo_mlp_v0.1"
    assert set(payload["predictions"]) == {
        "bol_current_density",
        "eol_current_density",
        "ecsa_loss",
        "durability_score",
        "cost_score",
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
    assert payload["model_version"] == "pem_fuel_cell_demo_mlp_v0.1"
    assert len(payload["predictions"]) == 2
    assert all("durability_score" in prediction for prediction in payload["predictions"])


def test_recommend(client):
    response = client.post(
        f"/projects/{PROJECT_ID}/recommend",
        json={
            "objective_weights": {
                "bol_current_density": 0.35,
                "eol_current_density": 0.35,
                "durability_score": 0.2,
                "ecsa_loss": -0.1,
                "cost_score": -0.1,
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
    assert payload["model_version"] == "pem_fuel_cell_demo_mlp_v0.1"
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
                "durability_score": 0.2,
                "ecsa_loss": -0.1,
                "cost_score": -0.1,
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
    assert 0.45 <= suggestion["inputs"]["operating_voltage"] <= 0.65
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
                "durability_score": 0.2,
                "ecsa_loss": -0.1,
                "cost_score": -0.1,
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
                "durability_score": 0.2,
                "ecsa_loss": -0.1,
                "cost_score": -0.1,
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
                    "durability_score": 0.2,
                    "ecsa_loss": -0.1,
                    "cost_score": -0.1,
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
