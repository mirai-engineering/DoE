# Agentic Knowledge Intake MVP Implementation Readiness Report

## Step 1 — Baseline Contract + Example Audit

Target contract sources reviewed:
- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full/mirai_manifest.json`
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full/data_dictionary.csv`
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full/experiments.csv`
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full/conditions.csv`
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full/results.csv`

Contract decision:
- Mirai has one runtime lifecycle: `generic_tabular_doe`.
- Fuel-cell data is an example reshaped into the generic package structure, not a separate runtime path.
- Runtime should validate contract files, then continue through existing Data Intake → Preprocessing → ML preprocessing → Training.

Required MVP package shape:
```text
mirai_package/
  mirai_manifest.json
  data_dictionary.csv
  model_table.csv
  metadata/        # optional
  raw_reference/   # optional audit/source files, not used for fitting
```

Current Fraunhofer full example uses fixed source tables:
- `experiments.csv`: 42 rows.
- `conditions.csv`: 2544 rows.
- `results.csv`: 2544 rows.
- `data_dictionary.csv`: 34 variables.

Target package tables and keys:
- `experiments.csv`
  - table type: `experiments`
  - primary key: `experiment_id`
  - key/group columns: `experiment_id`, `campaign_id`
- `conditions.csv`
  - table type: `conditions`
  - primary key: `condition_id`, `experiment_id`
  - split/condition columns: `condition_id`, `experiment_id`, `split`
- `results.csv`
  - table type: `results`
  - primary key: `result_id`
  - joins to `conditions.csv` through `condition_id`

Primary model inputs:
| variable_id | source_name | UI label | table | dtype | unit | bounds |
| --- | --- | --- | --- | --- | --- | --- |
| `x1` | `pt_c_ratio` | Pt/C ratio | experiments | float | fraction | 0–1 |
| `x2` | `i_c_ratio` | I/C ratio | experiments | float | ratio | 0–2 |
| `x3` | `ionomer_ew` | Ionomer EW | experiments | float | g/mol | 600–1000 |
| `x4` | `operating_rh` | Operating RH | conditions | float | % | 0–100 |
| `x5` | `operating_voltage` | Operating voltage | conditions | float | V | 0–1.1 |
| `x6` | `ast_rh` | AST RH | experiments | float | % | 0–100 |
| `x7` | `ast_upl` | AST UPL | experiments | float | V | 0.5–1.2 |

Primary outputs:
| variable_id | source_name | UI label | table | dtype | unit | direction |
| --- | --- | --- | --- | --- | --- | --- |
| `y1` | `bol_current_density` | BoL current density | results | float | A/cm2 | maximize |
| `y2` | `eol_current_density` | EoL current density | results | float | A/cm2 | maximize |
| `y3` | `bol_ecsa` | BoL ECSA | results | float | cm2/cm2 | maximize |
| `y4` | `ecsa_loss` | ECSA loss | results | float | fraction | minimize |

Important contract rules for the MVP:
- Keep model variable IDs generic/stable (`x1..x7`, `y1..y4`).
- Keep domain names in `source_name`, `ui_label`, descriptions, units, and bounds.
- Generate or export `model_table.csv` as the preferred training surface, even if fixed source tables are also emitted for traceability.
- Raw source files can be audit/reference files, but runtime training consumes the canonical structured tables.

[DONE:1]

## Step 2 — Demo Source Audit

Demo source root inspected:
`/Users/brunocopa/Public/Git/Mirai/AI_Development/Analytics/DoE/data/Cathode Catalyst Degradation`

Top-level source folders:
- `01-Data`
- `02-Testing_overview`
- `03-Evaluation_scripts`

Top-level templates also present:
- `mirai_manifest_template.json`
- `data_dictionary_template.csv`

Detected source inventory summary:
| Area | Contents | Likely role | MVP parsing stance |
| --- | --- | --- | --- |
| `01-Data` | 42 `Cell_XX.zip` archives plus at least one extracted `Cell_01` folder | Main raw per-cell measurements | Parse ZIP metadata and CSV files inside selected archives synchronously for demo; avoid broad unbounded extraction in request cycle |
| `02-Testing_overview` | `data_overview.xlsx` | Experiment/cell design overview, likely material and test metadata | Parse with lightweight XLSX reader |
| `03-Evaluation_scripts` | Python scripts and `raw_data_files/*.csv` | Reference/evaluation logic and pre-aggregated raw data | Treat scripts as reference only; parse CSVs as structured inputs where useful |
| templates | JSON/CSV contract templates | Hints for target output package | Read directly as target scaffolding |

File type counts found:
- CSV: 199
- ZIP: 42
- XLSX: 1
- JSON: 1
- Python: 4
- `.DS_Store`: ignored

Sample `Cell_01.zip` structure includes:
- `03-IV-curve_RH100`, `06-IV-curve_RH70`, `08-IV-curve_RH40` with cycle folders and IV/EIS CSVs.
- `10-CV` with ECSA-related files.
- `12-AST` and other electrochemical test folders.

Approved MVP file types were PDF/DOCX/XLSX/CSV only, but the selected fixture contains ZIP archives. Recommendation: for the demo source fixture, treat ZIP as a container only, not as a new semantic document type. The parser should safely enumerate/extract allowed inner CSV/XLSX files from ZIPs using existing safe extraction patterns or a narrow helper.

[DONE:2]

## Step 3 — Backend Data Model Plan

Additive migration only. Suggested next migration: `backend/db/migrations/006_project_document_intake.sql`.

Design principles:
- Follow current workspace/project scoping and RLS pattern.
- Store raw files in object storage/local mirror; store metadata and pointers in Postgres.
- Store drafts as JSONB for speed/ease; normalize only stable control-plane entities.
- Version extraction runs. Do not silently overwrite approved outputs.
- Rejected draft tables are deleted for the demo.

Proposed tables:

### `document_intake_sessions`
- `id UUID PRIMARY KEY`
- `workspace_id TEXT NOT NULL`
- `project_id TEXT NOT NULL`
- `status TEXT NOT NULL` values: `draft`, `files_uploaded`, `instruction_ready`, `matching_running`, `draft_ready_for_review`, `approved`, `rejected_deleted`, `exported`, `failed`
- `title TEXT`
- `user_instruction TEXT`
- `target_contract_id TEXT DEFAULT 'fraunhofer2miraicontract-full'`
- `created_by TEXT`, `updated_by TEXT`
- `created_at`, `updated_at`
- indexes on `(workspace_id, project_id, created_at)`

### `document_intake_files`
- `id UUID PRIMARY KEY`
- `workspace_id TEXT NOT NULL`
- `project_id TEXT NOT NULL`
- `session_id UUID REFERENCES document_intake_sessions(id) ON DELETE CASCADE`
- `filename TEXT NOT NULL`
- `content_type TEXT`
- `file_type TEXT` (`pdf`, `docx`, `xlsx`, `csv`, `zip_container` for fixture support)
- `object_uri TEXT NOT NULL`
- `sha256 TEXT`, `size_bytes BIGINT`
- `parse_status TEXT`
- `parse_summary JSONB DEFAULT '{}'`
- `created_at`

### `document_extraction_runs`
- `id UUID PRIMARY KEY`
- `workspace_id TEXT NOT NULL`
- `project_id TEXT NOT NULL`
- `session_id UUID REFERENCES document_intake_sessions(id) ON DELETE CASCADE`
- `status TEXT NOT NULL`
- `provider TEXT` (e.g. `anthropic` or `deterministic_fixture_mapper`)
- `model TEXT`
- `prompt_version TEXT`
- `contract_snapshot JSONB NOT NULL`
- `started_at`, `finished_at`
- `error TEXT`
- `metrics JSONB DEFAULT '{}'`

### `document_table_drafts`
- `id UUID PRIMARY KEY`
- `workspace_id TEXT NOT NULL`
- `project_id TEXT NOT NULL`
- `session_id UUID REFERENCES document_intake_sessions(id) ON DELETE CASCADE`
- `extraction_run_id UUID REFERENCES document_extraction_runs(id) ON DELETE SET NULL`
- `status TEXT NOT NULL` (`draft`, `ready_for_review`, `approved_persistent`, `deleted`, `exported`)
- `table_kind TEXT` (`mirai_fixed_source_tables`, `model_table`, `requirements_table`)
- `schema_json JSONB NOT NULL`
- `payload_json JSONB NOT NULL`
- `issues_text_object_uri TEXT`
- `source_refs_json JSONB DEFAULT '{}'`
- `created_at`, `approved_at`, `approved_by`

### `document_intake_exports`
- `id UUID PRIMARY KEY`
- `workspace_id TEXT NOT NULL`
- `project_id TEXT NOT NULL`
- `session_id UUID REFERENCES document_intake_sessions(id) ON DELETE CASCADE`
- `draft_id UUID REFERENCES document_table_drafts(id) ON DELETE SET NULL`
- `status TEXT NOT NULL`
- `package_object_uri TEXT`
- `manifest_object_uri TEXT`
- `data_dictionary_object_uri TEXT`
- `model_table_object_uri TEXT`
- `fixed_source_tables_json JSONB DEFAULT '{}'`
- `created_at`

RLS:
- Enable RLS on all tables.
- Policy mirrors existing workspace pattern: `workspace_id = current_setting('app.workspace_id', true)`.

[DONE:3]

## Step 4 — Backend Service/API Plan

Suggested new module boundaries:
- `backend/app/services/document_intake.py`
- `backend/app/services/document_parsing.py`
- `backend/app/services/mirai_contract_matching.py`
- Add request/response schemas in `backend/app/schemas.py` or dedicated typed module.

Suggested routes, all project-scoped and auth-scoped:

### Sessions
- `GET /projects/{project_id}/document-intake/sessions`
  - list sessions for project.
- `POST /projects/{project_id}/document-intake/sessions`
  - body: `{ title?: string, target_contract_id?: string }`
  - creates draft session.
- `GET /projects/{project_id}/document-intake/sessions/{session_id}`
  - returns session, files, latest run, latest draft/export summary.

### Files
- `POST /projects/{project_id}/document-intake/sessions/{session_id}/files`
  - multipart upload for PDF/DOCX/XLSX/CSV; demo may accept ZIP container with allowed inner CSV/XLSX only.
  - stores in workspace object storage.
- `GET /projects/{project_id}/document-intake/sessions/{session_id}/files`
  - returns safe inventory metadata.

### Instruction/chat
- `POST /projects/{project_id}/document-intake/sessions/{session_id}/instruction`
  - body: `{ message: string, expected_columns?: string[], expected_row_count?: number }`
  - stores/updates user instruction.
- `POST /projects/{project_id}/document-intake/sessions/{session_id}/messages`
  - optional small chat endpoint for clarification; can append to session notes without agent autonomy.

### Match contract
- `POST /projects/{project_id}/document-intake/sessions/{session_id}/match-mirai-contract`
  - deterministic action button.
  - reads target contract and uploaded parsed data.
  - creates extraction run and draft table.
  - response: run/draft status and issue count.

### Review
- `GET /projects/{project_id}/document-intake/sessions/{session_id}/draft-table`
  - returns table preview, schema, counts, source refs filename+page/sheet.
- `GET /projects/{project_id}/document-intake/sessions/{session_id}/issues.txt`
  - returns text/plain notes artifact.
- `POST /projects/{project_id}/document-intake/sessions/{session_id}/draft-table/approve`
  - persists/version-controls final structured draft.
- `POST /projects/{project_id}/document-intake/sessions/{session_id}/draft-table/reject`
  - deletes rejected draft for demo.

### Export
- `POST /projects/{project_id}/document-intake/sessions/{session_id}/export-mirai-package`
  - requires approved draft.
  - writes package files to object storage/local export area.
- `GET /projects/{project_id}/document-intake/sessions/{session_id}/export.zip`
  - downloads package candidate for manual upload into current Data Intake.

Do not auto-create an ingestion session in the current Data Intake lifecycle for MVP.

[DONE:4]

## Step 5 — Extraction/Contract Matching Plan

MVP mapper should be contract-first, not free-form discovery-first.

Inputs:
- User instruction: desired table shape and expectations.
- Uploaded source files and parsed summaries.
- Target contract snapshot from `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full`.
- Contract rules from `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`.

Algorithm outline:
1. Load target `mirai_manifest.json` and `data_dictionary.csv`.
2. Build required field map grouped by fixed source table:
   - experiment-level: `pt_c_ratio`, `i_c_ratio`, `ionomer_ew`, `ast_rh`, `ast_upl`, IDs/metadata.
   - condition-level: `operating_rh`, `operating_voltage`, split, source row refs.
   - result-level: `bol_current_density`, `eol_current_density`, `bol_ecsa`, `ecsa_loss`, source refs.
3. Parse available source files:
   - XLSX sheets for overview/design metadata.
   - CSV files for curves, ECSA, limiting current, pre-aggregated raw data.
   - ZIP container internals only for allowed CSV/XLSX files.
   - PDF/DOCX text if present in future demo docs.
4. Create candidate rows using deterministic joins:
   - one `experiments` row per cell/experiment.
   - one `conditions` row per operating RH/voltage point.
   - one `results` row per condition output vector.
5. Preserve source references as `filename + page/sheet`; for CSV-in-ZIP use `zip filename + inner csv path/sheet-like label`.
6. Use Anthropic/agentic extraction only for ambiguous text/requirements mapping; never let the LLM write executable transformations.
7. Emit issue notes for missing fields, inconsistent units, ambiguous joins, unexpected row counts, and contract validation failures.
8. Generate package files:
   - `experiments.csv`, `conditions.csv`, `results.csv`
   - `model_table.csv`
   - `data_dictionary.csv`
   - `mirai_manifest.json`
   - `raw_reference/` manifest or source pointer summary

Validation checks:
- Required files exist.
- Required columns exist.
- IDs are unique and joins are valid.
- `x1..x7` and `y1..y4` mappings match dictionary/manifest.
- Numeric fields parse as floats.
- Bounds are checked and warnings emitted.
- Row counts match expectations or issue notes explain mismatch.
- No training/preprocessing route is called automatically.

[DONE:5]

## Step 6 — Frontend UX Plan

Add a new tab in the Setup group before Data Intake:
- Label: `Knowledge Intake` or `Document Intake`.
- Suggested short label: `KI`.
- Type addition: extend `ActiveTab` in `frontend/src/types/doe`.
- Navigation addition: `frontend/src/components/Tabs.tsx` Setup group.
- Page render addition: `frontend/src/App.tsx` near current Data Intake/Preprocessing pages.

Suggested new component:
- `frontend/src/components/KnowledgeIntakePage.tsx`

Page layout:
1. Header card explaining this is an upstream demo that creates a Mirai package candidate; current Data Intake remains manual.
2. Session selector/create button.
3. Multi-file upload area.
4. Chat/instruction box:
   - default helper: “Create a Mirai fuel-cell contract package matching the Fraunhofer target. Expected outputs are experiments, conditions, results, model_table, data_dictionary, manifest.”
   - optional expected columns/row count fields.
5. Primary action button: **Match Mirai contract**.
6. Review table:
   - tabs for `experiments`, `conditions`, `results`, `model_table`, and optionally `requirements`.
   - show filename+page/sheet source refs.
   - counts and validation badges.
7. Issues/notes panel:
   - renders `issues.txt`.
   - lets user answer clarifying questions in chat.
8. Approval actions:
   - **Approve for persistent storage**.
   - **Reject and delete draft**.
9. Export action:
   - **Export Mirai package**.
   - **Download package ZIP**.
10. Manual next-step note:
   - “After export, upload this package in Data Intake and continue with the existing approval flow.”

API client additions:
- Add typed functions in `frontend/src/lib/api.ts` for the new route group.
- Keep calls separate from existing data-intake functions to avoid accidental coupling.

[DONE:6]

## Step 7 — Safety/Isolation Review

Files likely touched in a future implementation:
- Backend additions:
  - `backend/db/migrations/006_project_document_intake.sql`
  - `backend/app/services/document_intake.py`
  - `backend/app/services/document_parsing.py`
  - `backend/app/services/mirai_contract_matching.py`
  - `backend/app/schemas.py` or new schema module
  - `backend/app/main.py` only to register additive routes
  - tests under `backend/tests/`
- Frontend additions:
  - `frontend/src/components/KnowledgeIntakePage.tsx`
  - `frontend/src/components/Tabs.tsx`
  - `frontend/src/App.tsx`
  - `frontend/src/lib/api.ts`
  - `frontend/src/types/doe.ts`

Files intentionally not changed for MVP behavior:
- `backend/app/services/data_intake.py`
- `backend/app/services/preprocessing_review.py`
- `backend/app/services/ml_preprocessing.py`
- `backend/app/services/training_requests.py`
- `backend/ml_lifecycle/training/generic_tabular_doe/*`
- Existing migrations `001`–`005`
- Existing model quality/recommendation/optimization services

Protected invariants:
- Existing Data Intake route behavior remains unchanged.
- Existing preprocessing approval gates remain unchanged.
- Existing ML preprocessing plan approval/execution gates remain unchanged.
- Existing training request flow remains unchanged.
- No automatic handoff from Knowledge Intake to Data Intake.
- Workspace/project isolation and object pointer pattern are preserved.
- Rejected demo drafts are deleted, not left as active records.

[DONE:7]

## Step 8 — Implementation Readiness Report

Recommended implementation sequence:
1. Add migration `006_project_document_intake.sql` with RLS policies.
2. Add backend schema models for document intake sessions/files/runs/drafts/exports.
3. Add storage helpers using existing workspace storage conventions.
4. Add upload/session/list APIs.
5. Add lightweight parsers for CSV/XLSX and safe ZIP-contained CSV/XLSX fixture support; defer PDF/DOCX until demo docs require them.
6. Add contract matching service using target example package as deterministic schema.
7. Add review/draft/approve/reject/export APIs.
8. Add frontend API client functions.
9. Add `KnowledgeIntakePage` and tab navigation.
10. Add focused tests:
    - migration/table access smoke tests if test DB available.
    - service unit tests for contract map loading.
    - parser tests on small fixture files.
    - export package contains required files.
    - reject deletes draft.
11. Manually validate by exporting a package and uploading it through current Data Intake.

Demo acceptance criteria:
- User can create a project-scoped Knowledge Intake session.
- User can upload source files from the Cathode Catalyst Degradation fixture.
- User can enter an instruction and click **Match Mirai contract**.
- System produces draft `experiments`, `conditions`, `results`, and `model_table` preview with source refs shown as filename+page/sheet.
- System produces `issues.txt` for missing/ambiguous fields.
- User can approve for persistent storage.
- User can reject/delete draft.
- User can export/download a Mirai package candidate.
- Exported package passes existing Mirai contract validation after manual upload through Data Intake.
- Existing preprocessing, ML preprocessing, training, model quality, and recommendation flows are unaffected.

Rollback/safety notes:
- Additive migration can be rolled back by dropping new document intake tables only.
- New frontend tab can be feature-flagged or hidden without affecting current tabs.
- New routes are namespaced under `/projects/{project_id}/document-intake/...`.
- If parsing fails, current app lifecycle remains usable.
- No new infrastructure is required.

[DONE:8]
