# Agentic Engineering Knowledge Intake — Discovery Report

## 1. Current Architecture Map

Mirai is currently a generic tabular DoE platform. The canonical runtime flow is:

`Mirai package upload → contract validation → canonical model_table.csv → preprocessing review → Mirai admin approval → optional deterministic ML preprocessing → training request/execution → MLflow/artifacts → model quality/recommendations/optimization`.

### FastAPI route inventory

Core/system:
- `GET /`, `GET /health`, `GET /api/health`.
- `GET /projects`, `GET /workspaces`.
- `POST /admin/workspaces/{workspace_id}/storage` (`WorkspaceStorageProvisionRequest`).

Data intake/session:
- `GET /data-intake/sessions` list sessions.
- `POST /data-intake/sessions` creates session with multipart form/files; returns `IngestionSessionResponse`.
- `POST /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/files` appends uploads; returns `IngestionSessionResponse`.
- `GET /data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}` returns session.
- `GET .../inventory` returns `FileInventoryResponse`.
- `GET .../fuel-cell-package/validation` is a deprecated compatibility wrapper; internally validates the generic Mirai contract.

Preprocessing/review:
- `POST .../preprocessing/start` starts generic preprocessing despite fuel-cell legacy function names.
- `GET .../preprocessing/eda-summary`.
- `GET .../preprocessing/ydata-report.html`.
- `GET .../preprocessing/status`.
- `POST .../preprocessing-report`, `GET .../preprocessing-report`.
- `GET/PUT .../domain-metadata`; `POST .../domain-metadata/approval`.
- `POST .../preprocessing-approval` (`PreprocessingApprovalRequest`).

Deterministic ML preprocessing:
- `POST .../ml-preprocessing/contract` writes schema artifacts.
- `POST .../ml-preprocessing/start` drafts plan/report.
- `GET .../ml-preprocessing/status`.
- `POST .../ml-preprocessing/approval` approves plan.
- `POST .../ml-preprocessing/execute` writes `model_table_preprocessed.csv`.
- `GET .../ml-preprocessing/report`, `GET .../report.md`, `GET .../model-table-preprocessed.csv`.

Training:
- `GET/POST .../training-requests` (`TrainingRequestCreate`).
- `POST .../training-requests/{id}/start`.
- `GET .../training-requests/{id}/status`.
- `POST .../training-requests/{id}/import-mlflow-run` (`ExternalMlflowRunImport`).
- `GET .../training-requests/{id}/export-package`.

Project intelligence/model ops:
- `GET /projects/{project_id}/schema`.
- `POST /projects/{project_id}/data-scientist/messages` (`DataScientistRequest` → `DataScientistResponse`).
- `POST /projects/{project_id}/models/load-champion-model`; `POST /projects/{project_id}/models/refresh-approved-champion`.
- `GET /projects/{project_id}/artifact-status`.

Prediction/optimization/analysis:
- `POST /projects/{project_id}/predict`, `/batch-predict`, `/recommend`.
- BO: `GET /bo/state`, `POST /bo/initialize-replay`, `/bo/suggest`, `/bo/experiments/{experiment_id}/review`, `/bo/config`, `/bo/fantasy-rollout`.
- Design Studio: `GET /design-studio/state`, `POST /predict`, `/seed/batch`, `/pareto`, `/export.zip`.
- Business/model quality: `GET /impact/summary`; `GET /model-quality/summary`, `/latest-runs`, `/metrics`, `/preprocessing-report`, `/artifacts`, `/predictions`, `/predictions/export.zip`, `/active-model`, `/scientist-review`; `POST /model-quality/scientist-review`.

[DONE:1]

## 2. Current Happy Path

1. Create an ingestion session with files. `data_intake.py` creates workspace/project/dataset/session metadata, stores raw files, writes `session.json`, and infers whether the package is `ready_for_contract_review` or `blocked_missing_mirai_contract`.
2. Upload/add files. Files are mirrored locally and, when configured, written to workspace-scoped object storage.
3. Inventory/contract validation. The package must contain a Mirai contract: `mirai_manifest.json`, `data_dictionary.csv`, and either `model_table.csv` or fixed source tables (`experiments.csv`, `conditions.csv`, `results.csv`), or a ZIP containing that structure.
4. Preprocessing start. `preprocessing_review.py` validates the generic contract, prepares package root, builds canonical artifacts and schema, generates EDA/profile artifacts, and writes preprocessing/domain metadata status.
5. Domain metadata review. Backend infers domain metadata from schema; frontend/admin can edit and approve it.
6. Preprocessing approval. Approval requires domain metadata approval and updates report/status to `approved_for_training`.
7. ML preprocessing contract/start. Schema artifacts are written; `start_ml_preprocessing` drafts a deterministic typed plan.
8. ML preprocessing approval/execute. Approved plans are executed by fixed tools only, producing `model_table_preprocessed.csv`, `preprocessing_fitted.json`, `feature_map.json`, `target_map.json`, and a human report. Canonical `model_table.csv` is preserved.
9. Training request. Requires preprocessing approval; may require ML preprocessing if `MIRAI_REQUIRE_ML_PREPROCESSING_V1` is enabled. Otherwise legacy fallback can train from canonical `model_table.csv`.
10. Training start/status/export. Training package is assembled, models are trained, artifacts persisted, and status moves to completed or candidate-ready states.
11. MLflow/artifacts. Candidate model runs are logged; best challenger is selected/registered when possible; champion is not auto-promoted.
12. Model quality/recommendations. Project schema and active artifacts feed prediction, recommendations, Design Studio, BO, model quality, and business impact views.

[DONE:2]

## 3. File/session statuses and state transitions

Important statuses observed:
- Session: `ready_for_contract_review`, `blocked_missing_mirai_contract`; approval initially `not_ready`.
- Inventory review: `ready_for_mirai_admin_review` or `blocked_missing_required_contract`.
- Preprocessing: `not_started`, `queued`, `running`, `failed_validation`, `failed`, `preprocessing_complete_needs_approval`, `eda_complete_needs_mirai_admin_review`, `approved_for_training`.
- Domain metadata: `inferred_needs_admin_approval`, `contract_loaded_needs_admin_approval`, `draft`, `approved` with `approval_status` values like `needs_admin_approval`, `draft`, `approved`.
- ML preprocessing: `not_started`, `ml_preprocessing_contract_defined`, `ml_preprocessing_not_ready`, `preprocessing_plan_needs_approval`, `preprocessing_plan_needs_input`, `ml_preprocessing_plan_approved`, `ml_preprocessing_ready_for_training`.
- Training request/status: `staged_for_mirai_execution`, `running`, `completed`, `candidate_ready_for_review`, `failed_retryable_artifact_upload`, `not_started`.
- Model/champion: `candidate`, `approved_champion_active`.

Compatibility/deprecated wrappers:
- `.../fuel-cell-package/validation` is explicitly deprecated and maps to generic contract validation.
- Several backend names still say `fuel_cell` but now operate on `generic_tabular_doe` packages.
- Legacy local paths are still tolerated when workspace-scoped object paths are absent.

[DONE:3]

## 4. Database Layer

Postgres is a control plane, not a blob store. Heavy files remain in object storage. Migrations define:

- `workspaces`: tenant/workspace record, status, storage JSON.
- `clerk_user_workspaces`: Clerk user membership/role.
- `projects`: workspace-scoped project record, lifecycle contract, schema version, metadata, storage.
- `artifact_objects`: durable pointers to stored artifacts.
- `datasets`: uploaded dataset/package metadata, object URI, hashes, schema/row/column metadata, status.
- `schema_manifests`: manifest/schema pointers and extracted input/output/unit/schema JSON.
- `training_runs`: runtime training state, MLflow run id, metrics JSON, artifact prefix.
- `models`: registered/candidate/champion model pointers, metrics, optional MLflow `models:/...` URI support.
- `recommendations`, `observations`: candidate suggestions and observed experiment outputs.
- `audit_logs`: workspace-scoped audit events.

All major tables are workspace scoped with RLS policies based on `current_setting('app.workspace_id')`. Runtime state still also lives as JSON artifacts under session workspaces: `session.json`, `inventory/*.json`, `status/*.json`, preprocessing reports, domain metadata, ML preprocessing plans/reports/fitted manifests, and training request/status JSON. This hybrid is intentional but means SQL is not yet the single source of truth for every lifecycle detail.

[DONE:4]

## 5. Storage Architecture

Storage abstraction is in `workspace_storage.py` and `lifecycle_artifacts.py`.

- Local development backend defaults to `backend/.object-storage-local/`.
- `DOE_OBJECT_STORE_ROOT` remains a deprecated local alias; `LOCAL_OBJECT_STORAGE_ROOT` is preferred.
- Railway/production requires `OBJECT_STORAGE_BACKEND=s3`; S3 credentials come from environment variables.
- Object keys are workspace scoped, usually under `workspaces/{workspace_id}/...`.
- Intake sessions are organized by workspace/project/dataset/session with subdirs: `raw`, `extracted`, `canonical`, `training_artifacts`, `runs`, `inventory`, `eda`, `status`, `training_requests`.
- Raw uploads, canonical artifacts, reports, ML preprocessing outputs, training packages, and model artifacts are persisted as object keys/pointers.
- MLflow remains experiment/registry infrastructure; model pointers may be S3/object URIs or MLflow `models:/doe_surrogate_{project_id}/...` references.
- Storage validation rejects traversal/unsafe object paths and enforces workspace confinement.

Railway impact of future work should be minimal if it uses the same object-storage abstraction and Postgres control-plane style.

[DONE:5]

## 6. Current Agentic Layer Analysis

The current data scientist agent is project-scoped and read-only/tool-limited. It enters via `POST /projects/{project_id}/data-scientist/messages`; scope authorization binds project/workspace. Tools deliberately reject workspace IDs, paths, object keys, SQL, and storage identifiers in arguments.

Available tool responsibilities:
- `dataset_contract`: safe summary of project inputs/outputs/constraints.
- `artifact_inventory`: safe metadata for latest/selected session files.
- `table_profile`: EDA column/profile summaries.
- `preprocessing_status`: current preprocessing state.
- `ml_preprocessing_summary`: deterministic ML preprocessing plan/report/table metadata.
- `training_summary`: active model metadata.
- `model_quality`: metrics/artifacts/active model summary.

The agent does not currently ingest PDFs/DOCX or create arbitrary code. ML preprocessing is agent-like in UX but deterministic in execution: typed plan models, enumerated tools (`impute_numeric`, scalers, log/clip, one-hot, passthrough/drop, target transform), train-split-only fit scope, user approval before execution, and explicit reports.

Frontend review UI (`PreprocessingReviewPage.tsx` and `frontend/src/lib/api.ts`) drives the approval lifecycle: session selection, report/domain metadata approval, preprocessing approval, draft ML plan, approve/apply plan, download report/table, then create/start training requests. This confirms the actual UX depends on the current tabular session pipeline.

[DONE:6]

## 7. Training Pipeline Analysis

Training is in `training_requests.py` plus `ml_lifecycle/training/generic_tabular_doe/train.py`.

Contracts and behavior:
- Training requires preprocessing report approval (`approved_for_training`).
- ML preprocessing output is optional unless `MIRAI_REQUIRE_ML_PREPROCESSING_V1` is enabled.
- If ML preprocessing is ready, training uses `model_table_preprocessed.csv` and lineage artifacts; otherwise it can fall back to canonical `model_table.csv`.
- Exported packages include approved schema/domain metadata/training config and data artifacts.
- Candidate families include baseline, linear/ridge, and MLP; selection uses validation weighted normalized RMSE.
- Every candidate can be logged to MLflow; the best challenger is registered/set as challenger when registry is available.
- Champion is manual: Mirai does not auto-promote champion; refresh/load endpoints reconcile approved champions.
- Fallback behavior supports session-trained models and durable artifact pointers even when MLflow registration is unavailable.

[DONE:7]

## 8. Frontend UX/API Usage

Frontend confirms the product flow rather than merely backend affordances:
- Main tabs include Data Intake, Preprocessing Review, Training/Quality-related pages, Data Scientist.
- `frontend/src/lib/api.ts` calls the same session route base and approval endpoints.
- `PreprocessingReviewPage.tsx` exposes draft/apply ML preprocessing actions and downloads.
- Training requests are created only from the selected approved session path.
- The Data Scientist UI sends project messages to `/projects/{projectId}/data-scientist/messages` and does not represent a document ingestion workflow today.

[DONE:8]

## 9. Future Document-Intake Fit Points

The safest fit is upstream or parallel to current intake, not inside training and not as a replacement for tabular sessions.

Recommended seam:
`Documents → extraction workspace → reviewed structured engineering knowledge → structured table / Mirai package candidate → existing data-intake session`.

This preserves the current contract: only after document-derived knowledge becomes a validated `mirai_manifest.json` + `data_dictionary.csv` + `model_table.csv` or fixed source tables should it enter the existing pipeline.

Good future entry points:
- New read-only/document discovery area under a workspace/project.
- Document source storage using existing workspace object keys.
- Extraction runs producing structured outputs and provenance.
- Human review/approval that promotes a structured table candidate into a normal Mirai package/session.

Avoid:
- Feeding PDFs directly into training.
- Replacing `generic_tabular_doe`.
- Making vector chat the main product path.
- Letting LLM-generated transformations bypass current contract validation.

[DONE:9]

## 10. Engineering Knowledge Data Model

Canonical engineering knowledge model should be hybrid but structured-first:

- `SourceDocument`: file, type, object key, workspace/project, checksum, provenance.
- `DocumentChunk`: page/section/table chunk with offsets and source refs.
- `ExtractionRun`: model/provider/version, prompts/schema version, status, confidence, reviewer.
- `SchemaVersion`: controlled extraction ontology version.
- `EntityType` / `Entity`: assets, systems, subsystems, components, materials, process steps, requirements, constraints, measurements, operating limits, maintenance actions, failure events, operating conditions, tests, experiments.
- `RelationshipType` / `Relationship`: part-of, depends-on, measured-by, constrained-by, fails-by, maintained-by, observed-under, causes, mitigates, maps-to-column.
- `StructuredTable`: reviewed table with columns, units, dtypes, source lineage.
- `MLDatasetCandidate`: a candidate Mirai package/model table plus manifest/data dictionary drafts.

Intermediate representation: **hybrid relational + graph semantics in Postgres JSON/relational tables first**. Use relational tables for tenancy, source docs, extraction runs, review status, entities, relationships, and table candidates. Use graph semantics in relationship rows rather than introducing a separate graph DB. This supports process engineering/maintenance and product development/DoE without separate systems: both become entities/relationships plus reviewed structured tables, then DoE-specific outputs become Mirai dataset candidates.

How document knowledge becomes model tables:
1. Extract entities/measurements/requirements/events with source refs.
2. Normalize units and identifiers.
3. Review ambiguous fields and schema.
4. Select a task-specific table shape: assets over time, maintenance events, requirement matrix, experiment/results matrix, etc.
5. Generate `data_dictionary.csv` from reviewed columns/units/roles.
6. Generate `mirai_manifest.json` with table roles/joins/targets.
7. Generate or assemble `model_table.csv` where each row is a valid observation/experiment/event.
8. Run through current contract validation and preprocessing review.

[DONE:10]

## 11. Embeddings / Vector Search

Embeddings are optional and should be deferred unless a clear retrieval UX requires them.

- Postgres-only first: lowest risk, enough for source docs, chunks, extraction runs, entities, relationships, schema versions, and dataset candidates. Supports exact filters, provenance, and review workflows.
- pgvector later: reasonable if semantic search over chunks/entities is needed while keeping Railway/Postgres simplicity. Adds extension/indexing concerns but not a separate system.
- Separate vector DB: not justified for Phase 1; introduces infrastructure, tenancy, backup, consistency, and Railway complexity.

Recommendation: design tables so `DocumentChunk` and `Entity` can later have embedding columns, but do not require embeddings for the smallest demo.

[DONE:11]

## 12. Architecture Options

### Option A — Upstream Document Discovery Prototype (Recommended)
Description: Add a separate document-intake/discovery layer that stores documents and extraction outputs, then promotes reviewed structured table candidates into normal Mirai packages.
- Pros: preserves current pipeline; low coupling; reversible; demonstrates value before ML changes; works for maintenance/process and DoE.
- Cons: needs new review concepts later; initial manual promotion may be limited.
- Risk: Low/medium.
- Files likely affected later: new services/routes, frontend document review pages, migrations for document/extraction metadata; reuse storage utilities.
- DB impact: additive tables only.
- Railway impact: uses existing S3/Postgres; no new services.

### Option B — Extend Existing Data Intake to Accept Documents Directly
Description: Add PDFs/DOCX/XLSX as first-class data-intake session files and run extraction inside the existing session.
- Pros: one UX funnel; less new navigation.
- Cons: higher risk of confusing contract statuses; existing session assumes Mirai package readiness; document lifecycle differs from tabular approval.
- Risk: Medium/high.
- Files affected: `data_intake.py`, `preprocessing_review.py`, schemas, frontend intake/review.
- DB impact: may require overloading datasets/sessions.
- Railway impact: still S3/Postgres but more migration risk.

### Option C — Knowledge Platform with Separate Graph/Vector Services
Description: Build a full engineering knowledge service with graph DB/vector DB and later integrate with Mirai.
- Pros: powerful long-term retrieval/reasoning.
- Cons: overbuilt now; risks platform split; more infrastructure and consistency problems; delays value.
- Risk: High.
- Files affected: broad backend/frontend/deployment.
- DB impact: new databases or complex sync.
- Railway impact: new provisioned services likely.

[DONE:12]

## 13. Recommended Low-Risk Path and Non-Goals

Recommendation: **Option A is selected.** Build the future capability as an additive, per-project document discovery layer whose output is a manually reviewed Mirai-compatible package/model-table candidate. Do not automate handoff into the existing lifecycle yet; protect the current flow by keeping manual approval between every step.

Smallest demo implementation that proves value without redesign:
1. In an existing project, upload multiple messy source files: PDF, DOCX, XLSX, and CSV only.
2. User starts with a chat instruction describing the expected final table, e.g. desired columns and expected approximate row count.
3. Provide a deterministic **“Match Mirai contract”** button in the chat/review interface. For the first demo, use the current fuel-cell workspace/package as the target example: messy fragmented folders/files should be iterated into the same kind of Mirai contract the app already accepts today.
4. Use the Anthropic/agentic extractor to parse the documents and extract deterministic structured tables, including requirements, measurements, operating conditions, and any fields needed to satisfy the target Mirai contract.
5. Store raw documents in object storage and extracted deterministic data in Postgres-backed tables, with source lineage retained.
6. Show the resulting table in a document review table UI, plus a small `.txt`/notes artifact describing missing fields, ambiguities, and problems the user should answer in chat.
7. Let the user/dev approve or reject persistence of the final structured table. Approval persists/version-controls the structured output; rejection keeps it draft/non-persistent or superseded.
8. Export the approved candidate as `model_table.csv`, `data_dictionary.csv`, and `mirai_manifest.json`.
9. The user then manually continues into the current Data Intake → Preprocessing → ML preprocessing → Training Request flow. No automatic promotion/handoff in MVP.

Explicit non-goals:
- No direct PDF-to-training.
- No replacement of `generic_tabular_doe`.
- No vector DB in first version.
- No graph DB in first version.
- No arbitrary LLM-generated preprocessing code.
- No automatic champion promotion.
- No changes to current tabular approvals/training gates.
- No Railway infrastructure expansion unless proven necessary.

[DONE:13]

## 14. Resolved Decisions and Remaining Questions

Resolved MVP decisions from review:
- Proceed with **Option A**.
- Keep the first demo simple and general, not industry-specific yet.
- Support exactly four source types in MVP: PDF, DOCX, XLSX, CSV.
- Include requirements extraction in the first ontology scope.
- Document intake should be **per project**. A project remains inside a client/workspace; do not create a separate workspace-level knowledge product yet.
- For the demo, permissions can be open/dev-only; do not introduce real multi-role review logic yet.
- Source documents/chunks should follow the existing pattern: SQL metadata plus S3/local object storage for raw files.
- Use whichever table representation is easiest and robust first, prioritizing implementation simplicity over theoretical purity.
- Use the existing manual SQL migrations folder for any future additive DB tables.
- MVP UX should be a **document review table**, not a graph view.
- Users may ask questions over documents before structured approval.
- Ambiguity should be presented through a small `.txt`/notes artifact and chat follow-up.
- Do not implement or over-design the final handoff to current Data Intake yet.
- No automatic promotion. Between each stage, require manual user/dev approval.
- Use deterministic **“follow/match Mirai contract”** behavior for the first MVP. The current fuel-cell workspace/package is the example target: messy source files should be iterated into the same final Mirai contract shape the existing pipeline accepts.
- Add a UI button/action where the user approves or rejects the final table for persistent storage.

Updated data/modeling stance:
- Canonical source of truth: Postgres structured tables for extracted deterministic data, with raw document objects stored in S3/local storage.
- Keep lineage pragmatic: every extracted row/value should retain enough source reference to trace back to the source document/chunk/page/sheet when available. This is for audit, debugging, and user trust; exact granularity can start simple and improve later.
- Approved `StructuredTable`: a table produced from source documents that matches the user’s initial requested columns/expected shape or the selected Mirai contract target, has unresolved issues documented, and is explicitly approved by the user/dev for persistent storage.
- Version extraction runs; do not silently overwrite prior approved outputs.

Updated Mirai integration stance:
- Stage 1 is only `unstructured/messy data → structured data / Mirai package candidate`.
- After approval/export, the user manually proceeds to current Data Intake, then current Preprocessing Review, ML preprocessing, and Training Request.
- Do not change the current flow.
- Document-derived roles, targets, units, bounds, and constraints should come from the deterministic selected Mirai contract target and user chat clarification when missing.

Architecture/Railway decisions:
- pgvector is allowed later in Railway Postgres, but **not** as a Phase 1 dependency. Do not assume it is enabled. Do not introduce a separate vector DB. Revisit pgvector only after semantic retrieval over approved chunks/entities is proven necessary.
- For the demo, lightweight PDF/text/DOCX/XLSX parsing libraries are acceptable if they do not massively bloat the backend image.
- Simple synchronous parsing is acceptable for small demo files, but parsing should live behind a clean service boundary so it can later move to a worker/background task.
- Avoid OCR unless truly needed.
- Retention defaults: raw docs retained per workspace/project; chunks retained while source doc exists; extraction runs retained for audit/history; approved structured knowledge versioned; deleting source docs should soft-delete first and mark/delete derived knowledge rather than orphaning it.
- Continue following existing workspace/project separation of concerns and security assumptions.
- No special LLM/provider constraints for demo beyond current app assumptions.

Resolved final MVP implementation choices:
- Frontend placement: add a new per-project tab that fits naturally into the current UI/UX flow before the existing Data Intake / Preprocessing / Training path. Working label can be **Document Intake** or **Knowledge Intake**.
- Demo fixture: use the three gitignored folders under `/Users/brunocopa/Public/Git/Mirai/AI_Development/Analytics/DoE/data/"Cathode Catalyst Degradation"`.
- Target contract: read and follow `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md` and the existing resulting contract package at `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full`.
- First **“Match Mirai contract”** goal: transform the messy Cathode Catalyst Degradation sources into the same accepted generic Mirai contract shape as the example package, including `mirai_manifest.json`, `data_dictionary.csv`, and the fixed source tables / canonical fitting surface required by the contract.
- Contract specifics observed from the target package: `template_id: "generic_tabular_doe"`; fixed source tables `experiments.csv`, `conditions.csv`, `results.csv`; 7 main inputs mapped to `x1..x7` (`Pt/C ratio`, `I/C ratio`, `Ionomer EW`, `Operating RH`, `Operating voltage`, `AST RH`, `AST UPL`); key outputs including `y1`, `eol_current_density`, `bol_ecsa`, and `ecsa_loss`; source/display metadata retained in dictionary/manifest rather than model variable names.
- Rejected draft tables: delete for the demo rather than retaining as history.
- UI source reference: show `filename + page/sheet`.

No remaining open questions are required before turning this discovery report into an implementation plan.

[DONE:14]
