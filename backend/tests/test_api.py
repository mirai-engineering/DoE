import pytest
from fastapi.testclient import TestClient

from app.main import app


PROJECT_ID = "pem_fuel_cell_demo"


@pytest.fixture
def client():
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
