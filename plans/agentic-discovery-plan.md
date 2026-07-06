# Plan: Agentic Engineering Knowledge Intake Discovery

## Context

Mirai currently implements a generic tabular DoE lifecycle: package upload, contract validation, preprocessing review, optional ML preprocessing, training request/execution, MLflow-backed model artifacts, model quality, recommendations, Design Studio, and Bayesian optimization. The requested work is an investigation/report only: understand today’s architecture and identify the safest future integration point for an Agentic Engineering Knowledge Intake layer that converts engineering documents into structured data feeding the existing Mirai pipeline.

Initial repo scan found:

- FastAPI backend in `backend/app/main.py` with route groups for data intake, preprocessing review, ML preprocessing, training requests, project schema, data scientist messages, prediction, recommendation, BO, design studio, business impact, and model quality.
- Data/session storage services in `backend/app/services/data_intake.py`, `workspace_storage.py`, and `lifecycle_artifacts.py`.
- Current approval/review services in `backend/app/services/preprocessing_review.py` and `ml_preprocessing.py`.
- Training lifecycle in `backend/app/services/training_requests.py` and `backend/ml_lifecycle/training/generic_tabular_doe/train.py`.
- Postgres control-plane migrations in `backend/db/migrations/`.
- Existing docs that state the architectural intent: `generic_tabular_doe` is the source of truth; production objects live in Railway S3-compatible buckets; Postgres stores metadata/logical keys; local mirrors live under ignored `backend/.object-storage-local/`.

## Approach

Produce a single markdown discovery report, not code. The work should be read-only and should preserve the current product assumptions. The report will first map the current system precisely, then evaluate document/knowledge intake as an additive layer that eventually produces structured tables compatible with the existing Mirai contract and training flow.

The recommended investigation order is:

1. Map current backend/API routes and user-facing lifecycle.
2. Trace the tabular data path from upload through training artifacts.
3. Audit Postgres schema/control-plane tables and how filesystem/S3 object storage complements them.
4. Audit current agentic/preprocessing responsibilities, inputs, outputs, and approval states.
5. Identify integration seams where future document-derived structured data could enter without replacing intake, preprocessing, or training.
6. Compare multiple architecture options and recommend the safest incremental approach.

## Files to inspect

No production files should be modified. Critical files/directories to read during discovery:

- `README.md`
- `backend/app/main.py`
- `backend/app/schemas.py`
- `backend/app/auth.py`
- `backend/app/services/data_intake.py`
- `backend/app/services/preprocessing_review.py`
- `backend/app/services/ml_preprocessing.py`
- `backend/app/services/domain_metadata.py`
- `backend/app/services/training_requests.py`
- `backend/app/services/control_plane.py`
- `backend/app/services/db.py`
- `backend/app/services/workspace_storage.py`
- `backend/app/services/lifecycle_artifacts.py`
- `backend/app/services/project_registry.py`
- `backend/app/services/data_scientist/`
- `backend/app/services/model_quality.py`
- `backend/app/services/recommendation.py`
- `backend/app/services/design_studio.py`
- `backend/app/services/bayesian_optimization.py`
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/`
- `backend/ml_lifecycle/training/generic_tabular_doe/`
- `backend/db/migrations/*.sql`
- `backend/tests/`
- `frontend/` route/components that call data-intake, review, training, and model-quality APIs
- Deployment/storage docs: `backend/README.md`, `backend/RAILWAY_DEPLOYMENT.md`, `railway.toml`, `Dockerfile.railway`, `RAILWAY_CLERK_DEPLOYMENT_HANDOFF.md`

## Reuse

Existing concepts/utilities to reference rather than duplicate in future implementation planning:

- Session workspace layout via `session_workspace()` / `ensure_session_workspace()` in `backend/app/services/data_intake.py`.
- Workspace-scoped object paths and S3/local abstraction in `backend/app/services/workspace_storage.py`.
- Artifact persistence and public summaries in `backend/app/services/lifecycle_artifacts.py`.
- Contract validation and canonical table generation in `backend/ml_lifecycle/ingesting/generic_tabular_doe/`.
- Review/approval status conventions in `backend/app/services/preprocessing_review.py`.
- Typed, deterministic ML preprocessing plan/report models in `backend/app/services/ml_preprocessing.py`.
- Training request gating on preprocessing approval in `backend/app/services/training_requests.py`.
- Control-plane metadata patterns in `backend/app/services/control_plane.py` and `backend/db/migrations/`.

## Steps

- [ ] Build a complete FastAPI route inventory from `backend/app/main.py`, grouped by product area and noting request/response schemas.
- [ ] Trace the current happy path: create ingestion session → upload files → inventory/contract validation → preprocessing start/report → domain metadata approval → preprocessing approval → ML preprocessing contract/start/approval/execute → training request → training start/status/export → MLflow/artifacts → model quality/recommendations.
- [ ] Document current file/session statuses and state transitions, including which endpoints are compatibility/deprecated wrappers.
- [ ] Audit Postgres usage by reading `backend/db/migrations/*.sql`, `control_plane.py`, and `db.py`; summarize tables, logical ownership, and which runtime state still lives as JSON artifacts.
- [ ] Audit storage behavior: local mirror, Railway/S3 requirements, object key organization, workspace/project/session isolation, artifact persistence, and MLflow storage assumptions.
- [ ] Audit the current agentic layer: `data_scientist` message endpoints, provider/tool scope, preprocessing plan/report generation, deterministic ML preprocessing tools, and any frontend review UI behavior.
- [ ] Audit training pipeline internals and artifact contracts, especially required inputs (`model_table.csv` vs `model_table_preprocessed.csv`), training package export, MLflow registration, champion/challenger handling, and fallback behavior.
- [ ] Inspect frontend API usage to confirm actual UX flows and approval interactions, not just backend affordances.
- [ ] Identify future document-intake fit points that preserve the existing tabular contract, likely as a pre-intake or parallel discovery layer that produces a Mirai package/model table candidate rather than replacing the current session pipeline.
- [ ] Evaluate storage/data modeling principles for future structured engineering knowledge: source documents, chunks, extraction runs, entities, relationships, structured tables, schema versions, and ML dataset candidates.
- [ ] Evaluate embeddings/vector search as optional and deferred unless clearly required; compare Postgres-only, pgvector, and separate vector DB tradeoffs.
- [ ] Produce Option A/B/C with pros, cons, risk level, likely files affected, DB impact, and Railway impact.
- [ ] Select a recommended low-risk incremental path and define explicit non-goals.
- [ ] Compile exhaustive questions requiring human decisions before implementation.

## Verification

Because this is a discovery/report task, verification means validating the report against the repo rather than running new code:

- Cross-check every route named in the architecture map against `backend/app/main.py`.
- Cross-check schema/table claims against `backend/db/migrations/*.sql` and service queries.
- Cross-check storage claims against `workspace_storage.py`, `lifecycle_artifacts.py`, and deployment docs.
- Cross-check current lifecycle claims against existing tests in `backend/tests/` and README lifecycle descriptions.
- Ensure the final recommendation explicitly preserves the existing CSV/tabular intake → preprocessing review → training → optimization flow.
- Ensure no production files, migrations, routes, storage paths, dependencies, or infrastructure are changed during the investigation.

## Deliverable outline

The final discovery report should contain:

1. Current Architecture Map
2. Current Storage Architecture
3. Current Agentic Layer Analysis
4. Current Training Pipeline Analysis
5. Integration Opportunities
6. Integration Risks
7. Multiple Architecture Options
8. Recommended Approach
9. Questions Requiring Human Decisions
10. Explicit Non-Goals

## Initial recommended direction to validate

The likely safest path is to treat future engineering document intake as an additive, upstream capability that creates reviewed structured outputs and Mirai-compatible dataset candidates. It should not alter the existing data-intake, preprocessing, training, or optimization contracts until a document-derived table has passed review and can enter the current tabular lifecycle as a normal Mirai package/session.
