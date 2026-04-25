# Mirai DoE Engine Backend

Generic tabular Design of Experiments backend for validating experiment inputs,
running ONNX surrogate models, predicting KPIs, and recommending next candidate
experiments. The current included demo project is `pem_fuel_cell_demo`, but the
runtime is project-schema driven and is not fuel-cell specific.

## Structure

```text
backend/
  app/
    main.py
    schemas.py
    services/
      project_registry.py
      preprocessing.py
      model_loader.py
      prediction.py
      recommendation.py
  artifacts/
    pem_fuel_cell_demo/
      schema.json
      preprocessing.json
      metadata.json
      model.onnx
      model.pt
  data/
    synthetic/
      pem_fuel_cell_demo.csv
  training/
    generate_synthetic_data.py
    train_mlp.py
    export_onnx.py
  scripts/
    model.py
```

Legacy CV artifacts from the original copied project are isolated under
`backend/models/` and are not loaded by this backend.

## Setup

```bash
cd backend
uv sync --locked
```

Run tests:

```bash
uv run pytest
```

## Train Demo Model

The repository includes generated artifacts, so training is not required to run
the API. To reproduce the demo data and model:

```bash
cd backend
uv run python training/generate_synthetic_data.py
uv run python training/train_mlp.py
```

To re-export ONNX from the PyTorch checkpoint:

```bash
uv run python convert_to_onnx.py
```

The ONNX model uses input `features` with shape `[batch_size, 7]` and output
`predictions` with shape `[batch_size, 5]`.

## Run API Locally

```bash
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Healthcheck:

```bash
uv run python healthcheck.py
curl http://127.0.0.1:8000/health
```

## Docker

From the repository root:

```bash
docker build -f backend/Dockerfile -t mirai-doe-engine-api:test .
docker run --rm -p 8000:8000 mirai-doe-engine-api:test
curl http://127.0.0.1:8000/health
```

## API Examples

List projects:

```bash
curl http://127.0.0.1:8000/projects
```

Predict one experiment:

```bash
curl -X POST http://127.0.0.1:8000/projects/pem_fuel_cell_demo/predict \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "pt_c_ratio": 0.5,
      "i_c_ratio": 0.8,
      "ionomer_ew": 790,
      "operating_rh": 70,
      "operating_voltage": 0.6,
      "ast_rh": 100,
      "ast_upl": 1.15
    }
  }'
```

Recommend next experiments:

```bash
curl -X POST http://127.0.0.1:8000/projects/pem_fuel_cell_demo/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "objective_weights": {
      "bol_current_density": 0.35,
      "eol_current_density": 0.35,
      "durability_score": 0.2,
      "ecsa_loss": -0.1,
      "cost_score": -0.1
    },
    "fixed_inputs": {
      "operating_rh": 70,
      "operating_voltage": 0.6
    },
    "n_candidates": 2000,
    "top_k": 5
  }'
```

## Endpoints

- `GET /`
- `GET /health`
- `GET /projects`
- `GET /projects/{project_id}/schema`
- `POST /projects/{project_id}/predict`
- `POST /projects/{project_id}/batch-predict`
- `POST /projects/{project_id}/recommend`
