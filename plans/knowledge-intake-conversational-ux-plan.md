# Knowledge Intake Conversational UX Plan

## Context

The current Knowledge Intake MVP is safe but too opaque for generic Mirai contract mapping. A user can upload files and type instructions such as “approve everything,” but the UI does not clearly show what source columns were discovered, what mapping the agent proposes, which contract fields are blocked, or how the user should continue the conversation.

The intended outcome is a contract-driven conversational intake loop where the agent first inventories the uploaded files, proposes source-to-Mirai mappings, and the user can refine the mapping in natural language before any deterministic transform/export is allowed.

## Approach

Keep the existing safety model: no arbitrary generated transform code, no bypassing validation, no automatic training/preprocessing. Improve the generic path so it becomes an explicit mapping conversation:

1. Build a richer source inventory from uploaded CSV/XLSX/ZIP contents: file names, sheet/table names, columns, row counts, sample values, inferred units/roles where possible.
2. Give Anthropic/Sonnet the rich inventory plus selected Mirai contract fields and ask it to return a structured mapping proposal.
3. Persist the mapping proposal and conversation turns in the document intake session.
4. Show the user three clear UX surfaces:
   - source inventory / available columns
   - proposed Mirai contract mapping board
   - conversational next step / chat-style instruction loop
5. Interpret short user replies like “approve everything” against the current proposal:
   - if all required fields are mapped and a deterministic executor exists, mark the mapping as user-approved and proceed to validation/execution
   - if blockers remain, respond with specific missing fields and actionable choices instead of repeating generic questions.

## Files to modify

- `backend/app/services/document_intake.py`
  - enrich `_source_inventory`
  - add structured mapping proposal/session state
  - improve generic loop behavior for user replies
- `backend/app/main.py`
  - expose any needed endpoints for conversation/mapping state, likely reusing existing `/messages`, `/instruction`, and `/match-mirai-contract` routes where possible
- `frontend/src/components/KnowledgeIntakePage.tsx`
  - replace one-shot textarea UX with inventory, mapping board, and conversational loop
- `frontend/src/lib/api.ts`
  - expand `KnowledgeIntakeDraft`, `KnowledgeIntakeSession`, and related types for inventory/mapping/conversation fields
- Optional tests to add/update:
  - `backend/tests/...` for source inventory, mapping persistence, and approval semantics
  - frontend component tests if the repo has an established pattern

## Reuse

- Existing session/object persistence in `backend/app/services/document_intake.py`:
  - `_write_json`, `_read_json`, `_json_key`, `_update_session`
  - existing `loop_iterations` state
  - existing draft persistence and approval/export gates
- Existing Anthropic planner hook:
  - `_infer_mapping_plan_with_anthropic`
- Existing upload/session routes in `backend/app/main.py`:
  - `/projects/{project_id}/document-intake/sessions/{session_id}/files`
  - `/instruction`
  - `/messages`
  - `/match-mirai-contract`
  - `/draft-table/approve`
- Existing frontend API functions in `frontend/src/lib/api.ts`:
  - `saveKnowledgeIntakeInstruction`
  - `matchKnowledgeIntakeMiraiContract`
  - `getKnowledgeIntakeSession`
- Existing validation/export gates:
  - `approve_draft_table`
  - `export_mirai_package`

## Steps

- [ ] Define a structured generic mapping contract for draft/session state:
  - `source_inventory`: files, sheets/tables, columns, sample values, inferred units
  - `contract_fields`: required inputs/outputs for selected Mirai contract
  - `proposed_mapping`: contract field → source candidate(s), confidence, rationale, status
  - `blockers`: missing fields, ambiguous units, missing executor, validation failures
  - `conversation`: ordered user/agent turns
- [ ] Enrich backend source inventory:
  - CSV: headers, row count, sample rows/values
  - XLSX: workbook sheet names, per-sheet headers/row count/sample rows
  - ZIP: index inner CSV/XLSX files and sample supported contents where safe/size-limited
  - PDF/DOCX: keep filename/metadata for now unless existing parsers support text extraction
- [ ] Improve Anthropic prompt/output:
  - include rich source inventory
  - include selected Mirai contract fields
  - require JSON with `source_summary`, `available_columns`, `proposed_mapping`, `questions`, `blockers`, and `suggested_user_actions`
  - forbid executable code generation
- [ ] Add deterministic user-intent handling before/around Anthropic:
  - detect “approve everything,” “approve suggested mapping,” “use X as inputs,” “use Y as outputs,” and “mark X constant/unknown”
  - update mapping state instead of treating every instruction as a fresh standalone prompt
- [ ] Make generic loop responses specific:
  - if mappings are proposed, show them
  - if approval is impossible, list exact unmapped contract fields and choices
  - never repeat only generic questions when inventory details are available
- [ ] Update frontend UX:
  - show source inventory / available columns immediately after upload or loop run
  - show a contract mapping board with field, role, source, confidence, status, and rationale
  - show a chat-like transcript or “agent response” panel above the input
  - rename button from “Run intake loop” to context-aware labels such as “Ask agent / Update mapping” and “Approve suggested mapping”
  - keep approve/export buttons disabled until validation passes, but explain exactly why
- [ ] Preserve Fraunhofer demo behavior as deterministic adapter only, while displaying its mapping/validation in the same board format when possible.
- [ ] Add tests:
  - source inventory extracts columns from CSV/XLSX/ZIP
  - “approve everything” with no complete proposal returns specific blockers
  - “approve everything” with complete proposal records user approval but still blocks export without deterministic validation/package files
  - frontend build passes

## Verification

- Run backend syntax/tests:
  - `python3 -m py_compile backend/app/services/document_intake.py backend/app/main.py`
  - targeted backend tests for document intake if present/added
- Run frontend build:
  - `npm --prefix frontend run build`
- Manual Railway/local UX test:
  - create Knowledge Intake session
  - upload `Cell_34.zip` or a small CSV/XLSX
  - run loop and confirm available columns are displayed
  - confirm agent proposes input/output candidates
  - type “approve everything” and confirm response is contextual, not generic
  - type “use A/B as inputs and C as output” and confirm mapping board updates
  - confirm approval/export remain blocked until selected contract validation and package files exist
  - confirm Fraunhofer demo adapter still validates/exports and hands off to Data Intake
