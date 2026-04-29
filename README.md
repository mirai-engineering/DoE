# Mirai DoE Engine

Generic tabular Design of Experiments optimization engine for validating experiment inputs, running ONNX surrogate models, predicting KPIs, and recommending next candidate experiments. The runtime is project-schema driven and not domain-specific.

---

## Features

- ONNX surrogate model inference (CPU-first, no GPU required)
- Multi-project support via JSON schemas (current demo: PEM fuel cell)
- KPI prediction and weighted multi-objective recommendation
- FastAPI backend + React/Vite frontend
- Docker-ready with healthchecks and graceful shutdown

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI · ONNX Runtime · Pydantic |
| Frontend | Vite · React 18 · TypeScript · Tailwind CSS |
| Model | PyTorch → ONNX (MLPMulti-Layer Perceptron surrogate) |
| Deployment | Docker · Docker Compose · Nginx |

---

## Quick Start

For local dev you can do a 2-stage loading of the backend/frontend. For a production-like setup, use `docker compose` 

### Local Dev

#### Backend

```bash
cd backend
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Or with Docker:

```bash
docker build -f backend/Dockerfile -t mirai-doe-engine-api:test .
docker run --rm -p 8000:8000 mirai-doe-engine-api:test
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
# http://localhost:3000
```

The frontend proxies `/api` to `http://localhost:8000`.

---
### Prod Environment 
#### Docker Compose

See [`docs/DOCKER_DEPLOYMENT.md`](./docs/DOCKER_DEPLOYMENT.md) for detailed deployment instructions.

Start all services locally:

```bash
docker compose up --build
```

Then open the browser on http://localhost:3000

---

## Project Structure

```
.
├── backend/
│   ├── app/                  # FastAPI application
│   │   ├── main.py           # Entry point
│   │   ├── schemas.py        # Pydantic models
│   │   └── services/         # Core logic
│   │       ├── project_registry.py   # Schema/project management
│   │       ├── preprocessing.py      # Input normalization
│   │       ├── model_loader.py       # ONNX model loading
│   │       ├── prediction.py          # KPI prediction
│   │       └── recommendation.py      # Next-experiment ranking
│   ├── artifacts/            # Demo project artifacts
│   │   └── pem_fuel_cell_demo/
│   │       ├── schema.json              # Input/output schema
│   │       ├── preprocessing.json       # Normalization params
│   │       └── model.onnx               # Surrogate model
│   ├── training/             # Data generation & model training
│   └── pyproject.toml
├── frontend/                 # React + Vite UI
│   ├── src/
│   │   └── ...               # Components, hooks, pages
│   ├── package.json
│   └── Dockerfile
├── docs/
│   └── DOCKER_DEPLOYMENT.md  # Detailed Docker guide
├── docker-compose.yml
└── model-dev/                # Model registry and research
```

---

## API

See [`backend/README.md`](./backend/README.md) for full API documentation and examples.

Quick reference:

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | App info |
| `GET` | `/health` | Health check |
| `GET` | `/projects` | List available projects |
| `GET` | `/projects/{project_id}/schema` | Project I/O schema |
| `POST` | `/projects/{project_id}/predict` | Single experiment prediction |
| `POST` | `/projects/{project_id}/batch-predict` | Batch prediction |
| `POST` | `/projects/{project_id}/recommend` | Recommend next experiments |

---

## Training (Optional)

The repository ships with pre-generated artifacts. To reproduce them, see [`backend/README.md`](./backend/README.md).