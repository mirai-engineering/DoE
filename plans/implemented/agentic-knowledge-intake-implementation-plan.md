# Agentic Knowledge Intake MVP Implementation Plan

## Goal
Add a small, additive per-project Document/Knowledge Intake MVP that converts messy Cathode Catalyst Degradation source files into a reviewed deterministic structured table/package candidate matching the existing Mirai data contract, without changing the current Data Intake → Preprocessing → ML preprocessing → Training flow.

## Non-goals
- Do not replace `generic_tabular_doe`.
- Do not bypass current preprocessing/training approval gates.
- Do not auto-create training requests or auto-promote data into the existing lifecycle.
- Do not add graph DB, vector DB, pgvector dependency, or new infrastructure.
- Do not implement broad production-grade document processing, OCR, or background workers in MVP.

## Approved MVP Decisions
- Option A: additive upstream document discovery layer.
- Per-project feature/tab.
- Demo fixture: three gitignored folders under `/Users/brunocopa/Public/Git/Mirai/AI_Development/Analytics/DoE/data/"Cathode Catalyst Degradation"`.
- Target contract: `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md` and `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full`.
- Source file types: PDF, DOCX, XLSX, CSV only.
- Review UX: document review table plus chat/questions/notes.
- Add deterministic **Match Mirai contract** action.
- User/dev approves or rejects final table persistence.
- Rejected draft tables are deleted in demo.
- Source references shown as filename + page/sheet.

## Step 1 — Baseline Contract + Example Audit
Read and document the exact target package structure from:
- `backend/ml_lifecycle/MIRAI_DATA_CONTRACT.md`
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full/mirai_manifest.json`
- `backend/docs/examples/fuel-cell/fraunhofer2miraicontract-full/data_dictionary.csv`
- `experiments.csv`, `conditions.csv`, `results.csv`

Deliverable: concise contract map listing required tables, keys, columns, roles, dtypes, units, and outputs.

## Step 2 — Demo Source Audit
Inspect the three gitignored source folders under `data/"Cathode Catalyst Degradation"`.

Deliverable: source inventory containing file names, detected type, likely role, and whether each can be parsed synchronously in MVP.

## Step 3 — Backend Data Model Plan
Design additive Postgres tables only, following existing migration style and workspace/project separation:
- document intake sessions
- uploaded/source documents metadata
- extraction runs
- extracted table drafts
- extracted table rows/cells or JSON payloads
- issue/notes artifacts
- approval status

Keep implementation easiest/robust: prefer SQL metadata + JSONB for draft payloads where normalized modeling would slow MVP.

Deliverable: migration design, not applied until implementation is explicitly requested.

## Step 4 — Backend Service/API Plan
Design project-scoped APIs for:
- create/list document intake sessions
- upload PDF/DOCX/XLSX/CSV files
- parse small demo files
- send chat instruction / expected table shape
- run **Match Mirai contract** extraction
- view draft review table
- view notes/issues `.txt`
- approve persistence
- reject/delete draft
- export Mirai package candidate

Deliverable: route list and schemas.

## Step 5 — Extraction/Contract Matching Plan
Define deterministic target contract mapper:
- Inputs: user instruction, source files, target contract package.
- Output: draft fixed-source tables and/or `model_table.csv`-compatible structure.
- Preserve variable IDs from Mirai contract (`x1..x7`, outputs including `y1`, `eol_current_density`, `bol_ecsa`, `ecsa_loss`).
- Keep source/display labels in metadata, not model variable names.
- Record filename + page/sheet source reference.
- Emit issues for missing/ambiguous fields.

Deliverable: extraction algorithm outline and validation checks.

## Step 6 — Frontend UX Plan
Add a new tab that flows before current Data Intake, likely **Knowledge Intake** or **Document Intake**.

UX components:
- project-scoped session selector
- multi-file upload area
- chat/instruction box
- **Match Mirai contract** button
- review table
- issues/notes panel
- approve persistent storage button
- reject/delete draft button
- export/download Mirai package candidate button

Deliverable: frontend component/API integration plan.

## Step 7 — Safety/Isolation Review
Verify the implementation plan does not alter existing current-flow services unless only adding navigation/API clients.

Must preserve:
- existing data intake routes
- preprocessing approval gates
- ML preprocessing plan approval gates
- training request flow
- workspace/project storage isolation
- object storage pointer pattern

Deliverable: explicit list of files likely touched and files intentionally not touched.

## Step 8 — Implementation Readiness Report
Produce a final implementation readiness report with:
- recommended sequence of code changes
- migrations to add
- backend APIs to add
- frontend components to add
- demo acceptance criteria
- rollback/safety notes

No production code changes should be made during this planning pass unless explicitly requested.
