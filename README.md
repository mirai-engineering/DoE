# Mirai DoE Engine

Industrial R&D teams pay for every experiment twice: once in bench time — a single PEM fuel-cell sample needs roughly **130 hours** of automated characterization — and once in the search cost of deciding what to run next, because the knowledge that should inform that decision is scattered across PDFs, spreadsheets, bench exports, maintenance logs, and people's heads. Mirai DoE Engine attacks both halves. It replaces one-off, per-customer ETL scripts with a **single declarative data contract** (`mirai_manifest.json` + `data_dictionary.csv`) that describes what an uploaded dataset *means* — units, bounds, input/output roles, optimization directions — so onboarding a new domain is a configuration change rather than a code fork. On top of that contract it runs the full lifecycle: validation and an explicit human approval gate, canonical table construction, multi-candidate surrogate training with MLflow-governed `challenger`/`champion` promotion, model-quality diagnostics, an interactive Design Studio, BoTorch-driven Bayesian optimization, and a scoped read-only LLM agent that answers questions about a project's own data without ever seeing another tenant's. The result is a working, deployed platform: fuel-cell, battery, materials, and process-engineering datasets all travel the same code path; models are traceable from raw upload to registered version; and on the published Fraunhofer PEM catalyst study the virtual-screening workflow narrows **72 candidate configurations to 5** worth building — a 93% reduction in physical candidates, or roughly **8,700 equivalent bench-hours** of characterization avoided ([how that number is derived](docs/reference/BUSINESS_IMPACT_CALCULATION.md)).

---

## At a Glance

| | |
|---|---|
| **Backend** | Python 3.11, FastAPI, Pydantic v2, `uv` |
| **ML** | scikit-learn, ONNX Runtime (serving), BoTorch + GPyTorch (Bayesian optimization), Optuna, ydata-profiling |
| **Model governance** | MLflow tracking + model registry, candidate runs → selected challenger → manual champion promotion |
| **Agent runtime** | Anthropic SDK, server-side bounded tool loop, tenant-scoped read-only tools |
| **Frontend** | React 18, TypeScript, Vite, Tailwind, Plotly, react-three-fiber |
| **Data plane** | Railway Postgres (control plane) + S3-compatible object storage (payloads) |
| **Auth** | Clerk, workspace/project scoped |
| **Deploy** | Docker, Docker Compose + nginx locally, Railway in production |

---

## What Mirai Solves

Scientific organizations usually hold DoE data as project-specific exports:

- CSV/XLSX files with domain-specific column names
- separate experiment, sample, recipe, and result tables
- metadata, units, bounds, and target directions living in spreadsheets or tribal knowledge
- one-off scripts that turn one customer dataset into one model

Mirai replaces that pattern with a declarative package contract:

```text
my_project_upload/
  mirai_manifest.json
  data_dictionary.csv
  model_table.csv
  metadata/
    runs.csv
    samples.csv
  raw_reference/   # optional audit/source files only
```

The manifest and data dictionary define:

- table roles and joins
- input/output/metadata/grouping/split columns
- units and dtypes
- numeric bounds
- output directions: maximize, minimize, or target
- grouping and split hints
- plot and scientific-review metadata

Mirai then owns the whole lifecycle around that data:

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

The MVP is intentionally **generic first**:

- `generic_tabular_doe` is the source-of-truth lifecycle for tabular DoE projects.
- Customer/project meaning lives in `mirai_manifest.json` and `data_dictionary.csv`, not in customer-specific Python packages.
- The Fraunhofer fuel-cell demo is reshaped into the same generic Mirai package structure as every other tabular engineering project; it is not a separate upload or training path.
- MLflow remains the model experiment and registry layer.
- Production/demo object payloads live in Railway S3-compatible buckets, with Postgres storing metadata and logical object keys.
- Local runtime mirrors/caches live under ignored `backend/.object-storage-local/`.
- Immutable/reference evidence belongs under root `data/reference/` and is not part of normal app runtime state.

---

## Product Capabilities

### Knowledge Intake

- Upload heterogeneous engineering sources (PDF, DOCX, XLSX, CSV, ZIP) alongside structured packages.
- Map fragmented sources onto the Mirai contract through a conversational mapping loop.
- Persist review state and hand off an approved target contract to the structured intake path.

### Data Intake

- Create a new project under a workspace/client, or add a new dataset/session to an existing project.
- Upload one generic Mirai Experiment Package for every domain; ZIP uploads are containers for the same structure.
- Persist project/session metadata in Postgres + Railway object storage (production) or ignored `backend/.object-storage-local/` (local).
- Keep tiny seed workspace metadata under `backend/seeds/object_storage/`.

### Preprocessing Review

- Inventory uploaded files and validate manifest/data-dictionary structure.
- Build canonical artifacts and generate schema, preprocessing, split, profile, and EDA reports.
- Require explicit Mirai-admin approval before any training can start.

### Training Lifecycle

- Train multiple candidate models per generic tabular DoE project.
- Log every candidate as its own MLflow run.
- Select the best candidate by validation weighted normalized RMSE.
- Register only the selected best candidate as a new model version and set it as `challenger`.
- Never promote `champion` automatically.
- Restore a deleted local MLflow experiment when retraining a project whose experiment sits in the file-store trash.

### Model Quality

- Resolve the latest complete training artifacts from active intake sessions, falling back to packaged reference artifacts only when complete.
- Show candidate comparison, split metrics, prediction diagnostics, preprocessing context, and active model metadata.
- Support session-trained models even when MLflow registration is unavailable.

### Design Studio

- Schema-driven controls derived from the active project schema — no hardcoded domain widgets.
- Explore project-specific input ranges, predicted outputs, response surfaces, and multi-objective trade-offs.
- Batch search over thousands of virtual candidates before committing bench time.

### Bayesian Optimization

- BoTorch/GPyTorch surrogate + acquisition loop over train + validation observations.
- Test split stays untouched so model-quality evaluation remains honest.
- Fantasy rollouts and experiment logging for replay and what-if analysis.

### Data Scientist Agent

- Read-only, per-project assistant over the project's own contract, artifacts, preprocessing status, training runs, and model quality.
- Scope is derived server-side from the authenticated request; the model cannot supply workspace IDs, object keys, paths, or SQL.
- Tool output and answers are deterministically sanitized before they reach prompts, logs, or the UI.
- See `docs/mirai-agent-runtime-v0.md` for the threat model and tool contracts.

### Business Impact

- PEM case-study impact calculator translating avoided characterization into bench-hours and salary-equivalent engineering capacity.
- Every figure is explicitly framed as a planning scenario with its caveats stated in API and UI.
- Reference evidence lives under `data/reference/`; mutable assumptions use Postgres/object storage.

---

## Architecture

```text
Manifest / Data Dictionary
  Defines what uploaded data means.

Postgres + Railway S3-compatible object storage
  Stores runtime metadata, logical object keys, uploaded files, canonical datasets,
  generated reports, training artifacts, workspace metadata, and durable app state.

Local filesystem mirror / backend/.object-storage-local
  Optional ignored developer cache for local training and debugging.

MLflow
  Tracks experiments, candidate runs, metrics, params, artifacts, registered model
  versions, and aliases such as challenger/champion.

FastAPI Backend
  Orchestrates intake, validation, preprocessing, training, prediction, Model Quality,
  Design Studio, Business Impact, agent runtime, and BO APIs.

React + Vite Frontend
  Scientist/admin UI for project selection, intake, review, training, quality,
  design exploration, optimization, and impact storytelling.
```

The Railway Level 2 pilot uses a SQL-backed control plane for runtime state. See:

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
│   │   ├── auth.py                         # Clerk-backed request authentication
│   │   ├── schemas.py                      # API schemas
│   │   ├── agent_runtime/                  # Bounded tool loop, providers, sanitization
│   │   └── services/
│   │       ├── knowledge_intake/           # Document → contract mapping loop
│   │       ├── data_intake.py              # Upload/project/session metadata
│   │       ├── data_preprocessing/         # Validation, EDA, approval gate
│   │       ├── training_requests.py        # Training request lifecycle
│   │       ├── model_quality/              # Quality artifacts and active-model metadata
│   │       ├── design_studio/              # Design exploration, predictions, impact
│   │       ├── model_serving/              # ONNX/registry-backed prediction
│   │       ├── optimization/               # BoTorch engine, BO loop, replay mapping
│   │       └── platform/                   # Control plane, DB, workspace storage
│   ├── db/
│   │   ├── migrations/                     # SQL control-plane schema
│   │   └── seeds/
│   ├── seeds/object_storage/workspaces/    # Tiny tracked object-storage seed metadata
│   ├── .object-storage-local/              # Ignored local mirror/cache, if created
│   ├── ml_lifecycle/
│   │   ├── MIRAI_DATA_CONTRACT.md
│   │   ├── ingesting/
│   │   │   ├── generic_tabular_doe/        # Generic contract validation/preprocessing
│   │   │   └── extractors/                 # Generic extractor extension point
│   │   ├── training/
│   │   │   └── generic_tabular_doe/        # Generic candidate training + ONNX/MLflow
│   │   ├── deprecated_fuel_cell_reference/ # Quarantined historical reference code
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
│   ├── agent-plans/{implemented,to-implement}/
│   ├── reference/
│   └── tutorials/
├── deployments/                            # Deployment helper scripts
├── docker-compose.yml
├── railway.toml
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
allowed_extractors: []
lifecycle_contract: generic_tabular_doe
```

**Create new project** — use when the upload starts a separate scientific or business context. Creates a new project ID and leaves existing projects/sessions/artifacts untouched.

**Add data to existing project** — use for a repeat campaign, retraining package, or new dataset under the same project ID. It does not overwrite files, but future training can update that project's challenger/session model.

Ingestion path — the same Mirai Experiment Package shape for fuel cells, batteries, materials, process engineering, and every other tabular engineering project:

```text
template_id = generic_tabular_doe
lifecycle_contract = generic_tabular_doe
```

The preferred MVP package includes `mirai_manifest.json`, `data_dictionary.csv`, and `model_table.csv`. Optional overview/metadata tables must be declared with deterministic joins into `model_table.csv`. ZIP uploads are generic containers for the same structure.

---

## MLflow Lifecycle Policy

1. Train multiple candidate models.
2. Log every candidate as its own MLflow run.
3. Select the best candidate by validation weighted normalized RMSE.
4. Register only the selected best candidate as a new model version.
5. Set the selected registered version as `challenger`.
6. Never overwrite or promote `champion` automatically.

Registered model naming convention:

```text
doe_surrogate_<project_id>

# for example
doe_surrogate_pem_fuel_cell_real_cathode_degradation
```

Champion promotion is a manual governance decision.

---

## Quick Start: Local Development

### Backend

This repo uses `uv`, not `pip`, and `direnv` for local environment loading.

```bash
cd backend
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health check and discovery:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/projects
curl http://127.0.0.1:8000/workspaces
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The Vite dev server proxies `/api` to the backend.

### Docker Compose

For a production-like local setup:

```bash
docker compose up --build
```

Detailed deployment notes: `docs/tutorials/DOCKER_DEPLOYMENT.md`.

---

## Common Validation Commands

```bash
# Backend API and generic lifecycle tests
cd backend && uv run pytest tests/test_api.py tests/test_generic_contract_pipeline.py -q

# Broader backend suite
cd backend && uv run pytest -q

# Frontend
cd frontend && npm run build && npm test
```

---

## Important API Areas

See `backend/app/main.py` and `backend/README.md` for route details. Key route families:

| Area | Example Routes |
|---|---|
| App health | `GET /`, `GET /health` |
| Projects/workspaces | `GET /projects`, `GET /workspaces`, `GET /projects/{project_id}/schema` |
| Knowledge intake | document upload, mapping, and contract handoff endpoints |
| Data intake | `POST /data-intake/sessions`, `GET /data-intake/sessions` |
| Session files/inventory | `GET /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}` |
| Preprocessing review | `POST /.../sessions/{session_id}/preprocessing-report` |
| Approval gate | `POST /.../sessions/{session_id}/preprocessing-approval` |
| Training requests | `POST /.../sessions/{session_id}/training-requests` |
| Training execution | `POST /.../training-requests/{training_request_id}/start` |
| Prediction | `POST /projects/{project_id}/predict`, `POST /projects/{project_id}/batch-predict` |
| Model Quality | `GET /projects/{project_id}/model-quality/summary` |
| Design Studio | `GET /projects/{project_id}/design-studio`, prediction/design endpoints |
| BO | optimization loop and candidate recommendation endpoints |
| Data Scientist agent | `POST /projects/{project_id}/data-scientist/messages` |
| Business Impact | `GET /projects/{project_id}/impact/summary` |

---

## CLI Lifecycle Entrypoints

```bash
cd backend
uv run python -m ml_lifecycle.entrypoints.validate_manifest --help
uv run python -m ml_lifecycle.entrypoints.preprocess_project --help
uv run python -m ml_lifecycle.entrypoints.train_project --help
```

---

## Documentation Map

Core lifecycle:

```text
backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md
backend/ml_lifecycle/README.md
docs/reference/MLFLOW_MODEL_LIFECYCLE.md
docs/tutorials/MIRAI_CONTRACT_INTAKE_TO_TRAINING_FLOW.md
docs/mirai-agent-runtime-v0.md
```

User/tutorial docs:

```text
docs/tutorials/FUEL_CELL_UPLOAD_PREPROCESS_TRAIN_CLICK_PATH.md
docs/tutorials/BO_OPTIMIZATION_LOOP_GUIDE.md
docs/tutorials/DESIGN_STUDIO_PLAYGROUND.md
docs/tutorials/DESIGN_STUDIO_OBJECTIVES_AND_PARETO_MATH.md
docs/tutorials/DOCKER_DEPLOYMENT.md
```

Reference and provenance:

```text
docs/reference/BUSINESS_IMPACT_CALCULATION.md
docs/reference/REAL_FUEL_CELL_DATASET.md
docs/railway-level-2-pilot.md
```

Planning docs live under `docs/agent-plans/implemented/` and `docs/agent-plans/to-implement/`.

---

## Development Principles

- Keep `generic_tabular_doe` as the MVP source of truth.
- Do not add customer-specific Python packages.
- Treat workspace/client separation as metadata and storage layout, not code forks.
- Keep the Docker workflow intact.
- Do not rename public API routes unless explicitly planned.
- Use the MLflow registry when available for model lifecycle state.
- Avoid fallback artifact buckets such as `backend/artifacts/` or `runtime-projects/`.
- Keep the test split untouched for model-quality evaluation.
- Use Railway Postgres/S3/MLflow for production/demo runtime state.
- Use ignored `backend/.object-storage-local/` for mutable local app state.
- Use `data/reference/` for immutable reference data.

---

## Current Status

Working today:

- generic manifest contract intake, preprocessing, and training
- conversational knowledge intake for unstructured engineering sources
- Clerk-authenticated multi-tenant workspaces with a SQL control plane
- persistent workspace/project/session metadata on Postgres + object storage
- MLflow candidate-run and selected-challenger lifecycle
- session-aware Model Quality artifact resolution
- schema-driven Design Studio, batch search, and BO on train + validation artifacts
- tenant-scoped read-only Data Scientist agent runtime
- Railway deployment for API, frontend, and MLflow

Next architectural step: complete SQL-backed lifecycle management for
`project -> ingestion -> dataset -> training -> model` lineage
(`docs/agent-plans/to-implement/sql-s3-implementation/`).

---

## License

See `LICENSE`.
