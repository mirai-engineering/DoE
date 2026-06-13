# Mirai DoE Engine

Mirai DoE Engine is a generic, manifest-driven Design of Experiments platform for scientific and engineering teams. It lets a user upload a structured experiment package, validate the data contract, build canonical training tables, train surrogate models, inspect model quality, explore candidate designs, and run Bayesian optimization loops.

The current MVP is intentionally **generic first**:

- `generic_tabular_doe` is the source-of-truth lifecycle for tabular DoE projects.
- Customer/project meaning lives in `mirai_manifest.json` and `data_dictionary.csv`, not in customer-specific Python packages.
- Fraunhofer/PEM fuel-cell support is a demo adapter path: `pem_cell_zip_bundle` converts a PEM ZIP bundle into the same generic Mirai contract before preprocessing/training.
- MLflow remains the model experiment and registry layer.
- Production/demo object payloads live in Railway S3-compatible buckets, with Postgres storing metadata and logical object keys.
- Local runtime mirrors/caches live under ignored `backend/.object-storage-local/`; legacy `backend/data-minio/` data should remain ignored or archived there.
- Immutable/reference evidence belongs under root `data/reference/` and is not part of normal app runtime state.

---

## What Mirai Solves

Scientific organizations often have DoE data in project-specific exports:

- CSV/XLSX files with domain-specific column names
- separate experiment, sample, recipe, and result tables
- metadata, units, bounds, and target directions described in spreadsheets or tribal knowledge
- one-off scripts that transform one customer dataset into one model

Mirai replaces that pattern with a declarative package contract:

```text
my_project_upload/
  mirai_manifest.json
  data_dictionary.csv
  experiments.csv
  samples.csv
  results.csv
  optional_raw_or_reference_files...
```

The manifest/data dictionary define:

- table roles and joins
- input/output/metadata/grouping/split columns
- units and dtypes
- numeric bounds
- output directions: maximize, minimize, or target
- grouping and split hints
- plot and scientific-review metadata

Mirai then handles the lifecycle around that data:

```text
Upload package
  -> validate manifest/data dictionary
  -> build canonical model_table.csv
  -> generate preprocessing and split artifacts
  -> Mirai-admin approval gate
  -> train candidate surrogate models
  -> log candidates in MLflow
  -> register only the selected best challenger
  -> inspect Model Quality
  -> use Design Studio and BO to propose next experiments
```

---

## Current Product Capabilities

### Data Intake

- Create a new project under a workspace/client.
- Add a new dataset/session to an existing project.
- Upload generic Mirai contract packages.
- Upload the PEM fuel-cell demo bundle through the `pem_cell_zip_bundle` extractor.
- Persist project/session metadata in Postgres/Railway object storage for production, or under ignored `backend/.object-storage-local/` for local development.
- Persist tiny seed workspace metadata under `backend/seeds/object_storage/`; generated workspace state belongs in the ignored local mirror/cache.

### Preprocessing Review

- Inventory uploaded files.
- Validate manifest and data dictionary structure.
- Build canonical artifacts.
- Review generated schema, preprocessing, split, profile, and EDA artifacts.
- Require Mirai-admin approval before training.

### Training Lifecycle

- Train multiple candidate models for a generic tabular DoE project.
- Log every candidate model as a separate MLflow run.
- Select the best candidate by validation metric.
- Register only the selected best candidate as a new MLflow model version.
- Set selected registered version as `challenger`.
- Never promote `champion` automatically.
- Restore a deleted local MLflow experiment when retraining a project whose experiment exists in the file-store trash.

### Model Quality

- Resolve the latest complete training artifacts from active intake sessions.
- Fall back to packaged/reference artifacts only when complete.
- Show candidate comparison, split metrics, prediction diagnostics, preprocessing context, and active model metadata.
- Support session-trained models even when MLflow registration is unavailable.

### Design Studio

- Use schema-driven controls from the active project schema.
- Explore project-specific input ranges and predicted outputs.
- Support generic tabular projects instead of hardcoded fuel-cell controls.

### Bayesian Optimization

- Uses train + validation observations for replay/optimization context.
- Keeps test split untouched for model-quality evaluation.
- Avoids the old replay CSV fallback design.

### Business Impact

- Current PEM business-impact case study remains available.
- Business Impact reference evidence belongs under `data/reference/`; mutable assumptions should use Postgres/Railway object storage in production or ignored `backend/.object-storage-local/` for local development.

---

## Architecture

```text
Manifest / Data Dictionary
  Defines what uploaded data means.

Postgres + Railway S3-compatible object storage
  Stores runtime metadata, logical object keys, uploaded files, canonical datasets,
  generated reports, training artifacts, workspace metadata, and durable app state.

Local filesystem mirror / backend/.object-storage-local
  Optional ignored developer cache for local training and debugging. Legacy
  `backend/data-minio` contents should be archived here, not committed.

MLflow
  Tracks experiments, candidate runs, metrics, params, artifacts, registered model
  versions, and aliases such as challenger/champion.

FastAPI Backend
  Orchestrates intake, validation, preprocessing, training, prediction, Model Quality,
  Design Studio, Business Impact, and BO APIs.

React + Vite Frontend
  Scientist/admin UI for project selection, intake, review, training, quality,
  design exploration, optimization, and impact storytelling.
```

The Railway Level 2 pilot now uses a SQL-backed control plane for runtime state. See:

```text
backend/db/migrations/
backend/db/seeds/
docs/railway-level-2-pilot.md
```

---

## Repository Layout

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py                         # FastAPI application and routes
│   │   ├── schemas.py                      # API schemas
│   │   └── services/
│   │       ├── data_intake.py              # Upload/project/session metadata
│   │       ├── preprocessing_review.py     # Validation, EDA, approval gate
│   │       ├── training_requests.py        # Training request lifecycle
│   │       ├── model_quality.py            # Quality artifacts and active-model metadata
│   │       ├── design_studio.py            # Design exploration state/predictions
│   │       ├── prediction.py               # Prediction API helpers
│   │       ├── replay_mapping.py           # BO observation source mapping
│   │       ├── mlflow_registry.py          # MLflow registry/cache helpers
│   │       ├── project_registry.py         # Project/workspace discovery
│   │       └── workspaces.py               # Persistent workspace metadata
│   ├── seeds/
│   │   └── object_storage/workspaces/      # Tiny tracked object-storage seed metadata
│   ├── .object-storage-local/              # Ignored local mirror/cache, if created
│   ├── ml_lifecycle/
│   │   ├── MIRAI_DATA_CONTRACT.md
│   │   ├── MLFLOW_README.md
│   │   ├── ingesting/
│   │   │   ├── generic_tabular_doe/        # Generic contract validation/preprocessing
│   │   │   ├── extractors/                 # PEM ZIP bundle adapter
│   │   │   └── fuel_cell_doe_demo/         # Fuel-cell compatibility path
│   │   ├── training/
│   │   │   ├── generic_tabular_doe/        # Generic candidate training + MLflow
│   │   │   └── fuel_cell_doe_demo/         # Fuel-cell compatibility training
│   │   └── entrypoints/                    # CLI entrypoints for lifecycle steps
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── public/templates/                   # Downloadable manifest/dictionary templates
│   ├── src/components/                     # React UI pages/components
│   ├── src/lib/api.ts                      # API client
│   └── package.json
├── data/
│   └── reference/                          # Immutable/local reference data only
├── docs/
│   ├── agent-plans/
│   │   ├── implemented/
│   │   └── to-implement/
│   ├── reference/
│   └── tutorials/
├── deployments/                            # Future deployment helper scripts
├── docker-compose.yml
└── nginx/proxy.conf
```

---

## Data and Runtime State Policy

Mirai production/demo runtime uses Railway Postgres plus Railway S3-compatible object storage. Local filesystem state is only an optional ignored mirror/cache for development.

### Immutable/reference data

```text
data/reference/
```

Use this for packaged reference evidence, reference PEM artifacts, and local-only source data needed to reproduce demos. Root `data/` is intentionally ignored by Git except for explicitly tracked reference assets when added on purpose.

### Mutable app/object-store state

Production/demo source of truth:

```text
Railway Postgres                  # workspace/project/runtime metadata and logical object keys
Railway S3-compatible buckets     # heavy object payloads and artifacts
Railway MLflow                    # experiment tracking server/UI
```

Local development mirror/cache:

```text
backend/.object-storage-local/
  legacy-data-minio/              # renamed legacy local bucket/cache, if preserved
  <bucket-name>/workspaces/<workspace_id>/projects/<project_id>/...
```

`backend/.object-storage-local/` is ignored and may contain raw uploads, generated training artifacts, BO/session state, and local caches. Do not commit these files. Tiny intentional seed metadata belongs under `backend/seeds/object_storage/`.

### MLflow runtime state

```text
backend/mlruns/
backend/.mlflow-cache/
```

These are local runtime/model-registry stores and are ignored by Git.

---

## Workspaces, Projects, and Upload Modes

The frontend presents a Workspace / Client -> Project hierarchy.

Current seeded workspace:

```text
Fraunhofer
workspace_id: fraunhofer
allowed_extractors: [pem_cell_zip_bundle]
lifecycle_contract: generic_tabular_doe
```

Upload modes:

### Create new project

Use this when the upload starts a separate scientific or business context. It creates a new project ID and leaves existing projects/sessions/artifacts untouched.

### Add data to existing project

Use this for a repeat campaign, retraining package, or new dataset under the same project ID. It does not overwrite files, but future training can update that same project's challenger/session model.

Ingestion paths:

### Generic Mirai Contract

Use when uploaded tables already follow the Mirai manifest/data-dictionary contract.

```text
template_id = generic_tabular_doe
raw_extractor = null
```

### Fuell Cell DoE Demo

Use for the PEM ZIP bundle demo. The extractor adapts the PEM package to the generic contract first.

```text
template_id = generic_tabular_doe
raw_extractor = pem_cell_zip_bundle
```

The user-facing label intentionally remains `Fuell Cell DoE Demo`.

---

## MLflow Lifecycle Policy

Mirai uses MLflow for model training history and registry governance.

Current intended flow:

1. Train multiple candidate models.
2. Log every candidate as its own MLflow run.
3. Select the best candidate by validation weighted normalized RMSE.
4. Register only the selected best candidate as a new model version.
5. Set the selected registered version as `challenger`.
6. Never overwrite or promote `champion` automatically.

Registered model naming convention:

```text
doe_surrogate_<project_id>
```

For example:

```text
doe_surrogate_pem_fuel_cell_real_cathode_degradation
```

Champion promotion is a manual governance decision.

---

## Quick Start: Local Development

### Backend

This repo uses `uv`, not `pip`.

```bash
cd backend
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Projects/workspaces:

```bash
curl http://127.0.0.1:8000/projects
curl http://127.0.0.1:8000/workspaces
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The Vite dev server proxies `/api` to the backend.

---

## Docker Compose

For a production-like local setup:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:3000
```

Detailed deployment notes:

```text
docs/tutorials/DOCKER_DEPLOYMENT.md
```

---

## Common Validation Commands

Backend API and generic lifecycle tests:

```bash
cd backend
uv run pytest tests/test_api.py tests/test_generic_contract_pipeline.py -q
```

Broader backend tests:

```bash
cd backend
uv run pytest -q
```

Frontend build:

```bash
cd frontend
npm run build
```

---

## Important API Areas

See `backend/app/main.py` and `backend/README.md` for route details. Key route families include:

| Area | Example Routes |
|---|---|
| App health | `GET /`, `GET /health` |
| Projects/workspaces | `GET /projects`, `GET /workspaces`, `GET /projects/{project_id}/schema` |
| Data intake | `POST /data-intake/sessions`, `GET /data-intake/sessions` |
| Session files/inventory | `GET /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}` |
| Preprocessing review | `POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing-report` |
| Approval gate | `POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing-approval` |
| Training requests | `POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests` |
| Training execution | `POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests/{training_request_id}/start` |
| Prediction | `POST /projects/{project_id}/predict`, `POST /projects/{project_id}/batch-predict` |
| Model Quality | `GET /projects/{project_id}/model-quality/summary` |
| Design Studio | `GET /projects/{project_id}/design-studio`, prediction/design endpoints |
| BO | optimization loop and candidate recommendation endpoints |
| Business Impact | `GET /projects/{project_id}/business-impact` |

---

## CLI Lifecycle Entrypoints

The backend package exposes lifecycle modules under `backend/ml_lifecycle/entrypoints/`.

Examples:

```bash
cd backend
uv run python -m ml_lifecycle.entrypoints.validate_manifest --help
uv run python -m ml_lifecycle.entrypoints.preprocess_project --help
uv run python -m ml_lifecycle.entrypoints.train_project --help
```

For the real PEM reference preprocessing path:

```bash
cd backend
uv run python -m ml_lifecycle.entrypoints.preprocess_real_fuel_cell --project-id pem_fuel_cell_real_cathode_degradation
```

---

## Documentation Map

Core lifecycle docs:

```text
backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md
backend/ml_lifecycle/README.md
backend/ml_lifecycle/MLFLOW_README.md
docs/reference/MLFLOW_MODEL_LIFECYCLE.md
docs/tutorials/MIRAI_CONTRACT_INTAKE_TO_TRAINING_FLOW.md
```

User/tutorial docs:

```text
docs/tutorials/FUEL_CELL_UPLOAD_PREPROCESS_TRAIN_CLICK_PATH.md
docs/tutorials/BO_OPTIMIZATION_LOOP_GUIDE.md
docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md
docs/tutorials/DOCKER_DEPLOYMENT.md
```

Planning docs:

```text
docs/agent-plans/implemented/
docs/agent-plans/to-implement/
```

Notable future plans:

```text
docs/agent-plans/to-implement/sql-backed-lifecycle-management-plan.md
docs/agent-plans/to-implement/business-impact-reference-data-plan.md
docs/agent-plans/to-implement/minio-data-intake-object-storage-followup-todo.md
```

---

## Development Principles

- Keep `generic_tabular_doe` as the MVP source of truth.
- Do not add customer-specific Python packages.
- Treat workspace/client separation as metadata and storage layout, not code forks.
- Keep Docker workflow intact.
- Do not rename public API routes unless explicitly planned.
- Use MLflow registry when available for model lifecycle state.
- Avoid fallback artifact buckets such as `backend/artifacts/` or `runtime-projects/`.
- Keep test split untouched for model-quality evaluation.
- Use Railway Postgres/S3/MLflow for production/demo runtime state.
- Use ignored `backend/.object-storage-local/` for mutable local app state and legacy bucket mirrors.
- Use `data/reference/` for immutable reference data.

---

## Current Status

The current branch has:

- generic manifest contract intake/preprocessing/training
- PEM ZIP bundle extractor adapter
- persistent workspace metadata
- first-class uploaded project/session metadata
- MLflow candidate-run and selected-challenger lifecycle
- session-aware Model Quality artifact resolution
- schema-driven Design Studio controls
- BO replay based on train + validation artifacts
- cleanup of legacy synthetic PEM demo/runtime fallback paths

Next major architectural step:

```text
SQL-backed lifecycle management for project -> ingestion -> dataset -> training -> model lineage
```

See the plan in:

```text
docs/agent-plans/to-implement/sql-backed-lifecycle-management-plan.md
```
