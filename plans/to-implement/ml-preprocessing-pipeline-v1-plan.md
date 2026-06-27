# ML Preprocessing Pipeline v1 Plan

## Context

Mirai currently trains from the canonical `model_table.csv` fitting surface. The v1 MLOps gap is a robust, repeatable ML preprocessing layer between canonical table generation and model training. This layer must not mutate upstream intake/source-table behavior; it starts from the final `model_table.csv` and produces training-ready matrices plus reusable preprocessing artifacts for inference.

The harness must use existing after-intake EDA/profile artifacts, especially y-data-profiling analysis, to decide what ML preprocessing is appropriate. The LLM/harness loop must also be given `mirai-harness/MIRAI_MLPREPROCESSING_SKILL.md` every time it plans or executes preprocessing decisions, and it must explicitly combine the EDA evidence with that skill guidance. The central product requirement is: **use EDA/profile evidence to produce a constrained ML preprocessing plan; use the skill as policy/decision guidance; never let the LLM invent arbitrary transforms or code.**

Important implementation context from the after-intake persistence work now in `railway`:

- `backend/app/services/lifecycle_artifacts.py` persists durable, workspace-scoped lifecycle artifact sets: `session_metadata`, `canonical`, `preprocessing_artifacts`, `eda`, and `status` under object-storage prefixes derived from `workspace_id`, `project_id`, `dataset_id`, and `ingestion_session_id`.
- `backend/app/services/data_intake.py` can restore the latest persisted ingestion session via `restore_latest_persisted_ingestion_session(...)` and `list_ingestion_sessions(..., restore_latest=True)` when local runtime cache is empty.
- `backend/app/services/preprocessing_review.py` hydrates EDA/preprocessing/status/schema artifacts from object storage when local files are missing, including `get_preprocessing_eda_summary(...)`, `get_preprocessing_review_report(...)`, `get_preprocessing_status(...)`, `_read_json_local_or_storage(...)`, and y-data report helpers.
- `frontend/src/components/PreprocessingReviewPage.tsx` already selects the restored/latest session and loads preprocessing status, review report, EDA summary, y-data HTML, and training status in-app.
- The new ML preprocessing implementation must reuse these session-scoped artifact readers rather than scanning global folders or inferring paths from user/model input.

Current gap found in code: `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py`, `backend/app/services/preprocessing.py`, and `backend/ml_lifecycle/training/generic_tabular_doe/train.py` contain hardcoded assumptions such as median imputation, minmax input scaling, and standard/minmax output scaling in different places. v1 should replace this with a single approved, persisted, versioned preprocessing contract that both training and inference consume.

## Approach

Implement v1 as a new **ML preprocessing layer after canonical table creation**:

1. **Canonical table remains immutable input.** Existing intake/generic preprocessing continues to materialize and validate `canonical/model_table.csv`, schema, split, validation, and EDA artifacts. v1 must not alter raw uploads, fixed source tables, joins, validation, or the canonical model table.
2. **EDA-driven plan generation.** A scoped harness/agent call reads bounded evidence from the selected session only: `preprocessing_artifacts/eda_report.json`, `canonical/dataset_profile.json`, `preprocessing_artifacts/split_report.json`, optional `eda/ydata_profile.json`, `eda/preprocessing_report.json`, schema/data dictionary roles, and y-data-profiling summaries. The preferred access path is through `preprocessing_review` service functions (`get_preprocessing_eda_summary`, `get_preprocessing_review_report`, `get_public_preprocessing_status`, and internal local-or-storage hydration), not direct unscoped filesystem reads. The LLM prompt/loop must always include `mirai-harness/MIRAI_MLPREPROCESSING_SKILL.md`, and the output must explicitly cite which EDA facts drove each proposed transform.
3. **Typed tool graph, not generated code.** The LLM can only choose and parameterize deterministic Mirai preprocessing tools in a JSON tool graph/spec: `impute_numeric`, `minmax_scaler`, `standard_scaler`, `robust_scaler`, `log1p_feature`, `clip_numeric`, `one_hot_encoder`, `passthrough`, `drop_from_training`, and optional reversible `target_transform`. Each tool is implemented/tested by Mirai code; the agent selects from the allowlist and explains evidence. No arbitrary pandas/Python/SQL/path/tool execution.
4. **Human-approved immutable plan version.** The draft spec/report is stored as `ml_preprocessing/plans/<plan_id>/preprocessing_plan.json` plus a review report. For v1, approval is mandatory for all new training requests; a short-lived legacy compatibility path can remain only for existing demo fixtures/tests and must be visibly marked as legacy.
5. **Deterministic executor fits the plan.** A backend executor loads the approved spec, fits transforms on `split == train` rows only, applies those fitted transforms to train/validation/test rows, and writes versioned artifacts. Validation/test never influence imputer/scaler/encoder fit state.
6. **Fitted artifact is the source of truth for training and inference.** Store enough fitted state to apply raw inputs at inference and inverse-transform outputs where target scaling is enabled. The runtime never hardcodes “minmax” or “standard” assumptions; it dispatches by `method` and `variable_id` from the artifact. Project X can therefore use min-max input scaling plus reversible target de-scaling, while Project Y can use standard/robust scaling, without branching into client-specific code.
7. **Generic across projects by contract, not by client code.** The executor reads variable roles, IDs, dtypes, units, directions, bounds, split/group/time metadata, and input/output order from the approved schema/data dictionary. It dynamically builds the feature map and target map from that contract, so projects with different I/O counts, variable names, units, and sizes use the same tool implementations with different per-variable specs/fitted parameters.
8. **Backward compatibility.** Preserve current `preprocessing.json` consumers by either (a) writing a backward-compatible facade for simple minmax cases or (b) updating runtime prediction/training to support `preprocessing_contract_version: mirai-ml-preprocessing-v1` while still accepting legacy `mirai-generic-0.1` artifacts.
9. **Operator-facing completion state.** Successful execution ends in `ml_preprocessing_ready_for_training`, writes the actual `model_table_preprocessed.csv` used by training, and presents a concise “Preprocessing ready — this is what we did” summary with export/download options for the plan, fitted artifact, report, transformed table, and manifest.

### MLOps practices to follow

External reference checked during planning: scikit-learn “Common pitfalls and recommended practices” warns that data leakage occurs when unavailable-at-prediction-time information is used during model building, and specifically that test data must not be used to make model/preprocessing choices. This plan follows that pattern with Mirai-specific lifecycle controls:

- Split before fitting preprocessing; fit all preprocessing state only on the train split.
- Treat validation/test as transform-only, never fit/choice data.
- Use pipeline-style artifacts: the same fitted preprocessing object used for training must be serialized and reused at inference.
- Version and checksum every input/output artifact for reproducibility.
- Make preprocessing deterministic after approval; the agent drafts/explains the plan, but Mirai code performs fit/apply.
- Keep test data untouched for final evaluation; validation can guide model selection, but test cannot guide preprocessing/tool choice.
- Detect and block leakage-prone features such as row IDs, post-outcome fields, target-derived fields, duplicate leakage, group/time leakage, and test-only categories.

### Data compliance and isolation requirements

- All ML preprocessing APIs must bind `workspace_id`, `project_id`, `dataset_id`, and `ingestion_session_id` from authenticated server context and selected session state. The agent must never choose, override, or infer another scope.
- Evidence tools may only read allowlisted artifact sets for that exact session: `session_metadata`, `canonical`, `preprocessing_artifacts`, `eda`, and `status`.
- Durable reads/writes must use `WorkspaceStorageConfig`, `validate_workspace_object_key`, `session_artifact_prefix(...)`, and existing restore/hydration helpers so object keys remain workspace/project scoped.
- API responses and agent context must expose sanitized public metadata only. Do not leak raw object keys, full object URIs, local absolute paths, raw upload directory names, or artifacts from another workspace/project.
- Planner evidence must be bounded: summaries, profiles, row/column statistics, hashes, and small safe samples only when explicitly needed. Do not stream whole raw datasets into LLM context.
- No split leakage: EDA can describe whole-dataset risks, but all fitted imputer/scaler/encoder/target-transform parameters must be computed from `split == train` rows only.
- Artifact lineage must include checksums for the canonical model table, EDA/profile artifacts used, approved plan, fitted preprocessing, and transformed matrices. If any upstream checksum changes, the approved ML preprocessing version becomes stale and cannot be reused silently.

### Generic project support model

The generic mechanism is:

1. Read the approved project/session contract (`schema.json`, data dictionary/domain metadata, split report, and canonical columns).
2. Build a variable registry from `variable_id`, role (`input`, `output`, `group`, `time`, `metadata`, `exclude`), dtype, unit, bounds, direction, and nullable/category metadata.
3. Let the planner choose deterministic tools per variable, constrained by dtype/role and EDA evidence.
4. Fit each chosen tool into a method-specific parameter block keyed by `variable_id`, not by hardcoded PEM/fuel-cell/client names.
5. Generate `feature_map.json` and `target_map.json` dynamically from the ordered approved variables and encoder expansions.
6. Train and serve against those maps and fitted parameters.

This means different projects can have different numbers of inputs/outputs, column names, scaling choices, categorical encodings, and target transforms while sharing the same Mirai executor/runtime code.

### How this avoids hardcoding

The key design is to separate **preprocessing decision**, **fitted state**, and **application**:

- Decision artifact: `preprocessing_plan.json` says what to do per variable and why, e.g. `x3 -> impute median -> robust_scale`.
- Fitted artifact: `preprocessing_fitted.json` stores method-specific parameters, e.g. median value, IQR center/scale, min/max, category vocabulary, target mean/std, clipping bounds.
- Runtime transformer library: a small allowlisted interpreter applies the artifact generically by method/tool name and variable order. Adding `standard_scaler` or `robust_scaler` means adding one reusable deterministic tool implementation, not per-client code.
- Model metadata points to the exact approved/fitted preprocessing version used during training. Inference loads the same version, applies `transform_inputs`, runs the model, then applies `inverse_transform_outputs` only for outputs that declare reversible transforms.

## Files to modify

Likely critical paths:

- `mirai-harness/MIRAI_MLPREPROCESSING_SKILL.md` — keep as source skill content; implementation must load/include it in each LLM preprocessing loop.
- `backend/app/services/preprocessing_review.py` — reuse existing session-scoped EDA/status/report hydration and add ML preprocessing readiness/evidence entrypoints after canonical preprocessing and EDA.
- `backend/app/services/lifecycle_artifacts.py` — add a new durable `ml_preprocessing` artifact set for approved plans, fitted state, reports, transformed table/matrix metadata, and manifests/checksums.
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py` — stop treating current hardcoded median/minmax artifact as the final ML preprocessing; keep canonical/EDA generation and/or mark legacy artifact clearly.
- `backend/app/services/preprocessing.py` — replace hardcoded minmax-only runtime transform helpers with version-aware generic transformer dispatch.
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py` — train from approved fitted preprocessing artifacts instead of fitting separate hardcoded imputers/scalers inside each estimator.
- `backend/app/services/data_intake.py` — reuse restored latest session/listing behavior; do not add a second session lookup path.
- `backend/app/services/training_requests.py` — require approved ML preprocessing plan/version before training/export; include preprocessing artifact checksums in `training_manifest.json`.
- `backend/app/services/prediction.py` and `backend/app/services/model_loader.py` — load/apply fitted preprocessing v1 artifacts for serving and inverse output transforms.
- `backend/app/main.py` — add minimal API routes for draft plan generation, plan approval, execution/status, and report fetch.
- `frontend/src/components/PreprocessingReviewPage.tsx` and/or `frontend/src/components/DataScientistPage.tsx` — show evidence, draft plan, risks, and approval state.
- Tests under `backend/tests/` for spec validation, leakage prevention, tenant isolation, transform/inverse-transform, and legacy compatibility.
- Docs under `docs/` for the v1 lifecycle and artifact schema.

## Reuse

Existing reusable pieces found:

- `backend/app/services/preprocessing_review.py`
  - `get_preprocessing_eda_summary()` already exposes bounded EDA/status artifacts for the selected session and includes durable artifact availability.
  - `get_preprocessing_review_report()` already hydrates `eda/preprocessing_report.json` locally or from object storage.
  - `get_preprocessing_status()` can restore status from durable artifacts via `_preprocessing_status_from_durable_artifacts(...)`.
  - `ensure_ydata_html_report()` and `get_ydata_html_report_file_or_bytes()` already generate/read y-data-profiling HTML/JSON from canonical `model_table.csv`, including object-storage fallback.
  - `_read_json_local_or_storage(...)`, `_hydrate_artifact_from_storage(...)`, and `_artifact_exists_in_storage(...)` are the patterns to reuse for ML preprocessing evidence reads.
  - `approve_preprocessing()` already models human approval before training.
  - Workspace/session helpers enforce scoped artifact locations.
- `backend/app/services/lifecycle_artifacts.py`
  - `LIFECYCLE_ARTIFACT_SETS` defines allowed persisted artifact groups; add `ml_preprocessing` here instead of inventing new object-storage paths.
  - `persist_session_artifact_set(...)`, `persist_multiple_artifact_sets(...)`, `session_artifact_prefix(...)`, `latest_manifest_key(...)`, and `read_workspace_artifact_bytes(...)` provide reusable, workspace/project/session-scoped persistence and hydration.
  - `public_artifact_persistence_summary(...)` strips raw object keys/URIs before API responses; reuse it for ML preprocessing API payloads.
- `backend/app/services/data_intake.py`
  - `restore_latest_persisted_ingestion_session(...)` and `list_ingestion_sessions(..., restore_latest=True)` restore durable sessions into local cache after app/runtime restart.
  - `ensure_session_workspace(...)`, `get_ingestion_session(...)`, `read_status(...)`, and `write_status(...)` should be reused for scoped local cache/status access.
- `backend/app/main.py`
  - Existing routes around `/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing/status`, `/preprocessing-report`, `/preprocessing/eda-summary`, and `/preprocessing/ydata-report.html` show the route shape and should be mirrored under the same session path for ML preprocessing.
- `frontend/src/components/PreprocessingReviewPage.tsx`
  - Already selects latest/restored sessions via `mirai.latestIngestionSession`, calls session-scoped APIs, loads EDA summaries, and opens authenticated y-data HTML blobs.
  - Reuse this state rather than adding a separate project-global ML preprocessing selector.
- `frontend/src/lib/api.ts`
  - Existing `sessionPath(session)`, preprocessing status/report/EDA/ydata clients, and authenticated blob helper are the client patterns to extend.
- `backend/ml_lifecycle/ingesting/generic_tabular_doe/preprocessing.py`
  - Already materializes `canonical/model_table.csv`, `schema.json`, `dataset_profile.json`, `split_report.json`, `validation_report.json`, and `eda_report.json`.
  - Already assigns `split` before any ML fitting, which is required for train-only preprocessing fit.
- `backend/app/services/data_scientist/*` and `backend/app/agent_runtime/*`
  - Reuse the scoped Anthropic SDK provider pattern, narrow typed tools, redaction, and tenant isolation for preprocessing-plan generation.
- `backend/app/services/preprocessing.py`
  - Existing validation and matrix conversion (`validate_row`, `rows_to_feature_matrix`) can stay, while transform helpers become version-aware.
- `backend/app/services/training_requests.py`
  - Existing training request and exported package manifest flow can carry preprocessing plan/fitted artifact hashes.
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py`
  - Existing candidate training/MLflow artifact logging can be retained once input/output arrays are produced by the approved preprocessor.

## Skills and subagent mapping

Use agents to keep implementation focused, but keep all writes going through one implementation owner per slice.

### Required skills/context

- `mirai-harness/MIRAI_MLPREPROCESSING_SKILL.md` — mandatory context for every ML preprocessing planning/execution loop and for implementation agents touching planner behavior.
- `.pi/skills/scientific-ui-clarity/` — use for the Preprocessing Review UI, especially the streamed “what is happening / what we did” user experience.
- `.pi/skills/surrogate-model-debugging/` — use for runtime/training/inference checks around scaled inputs, inverse-transformed outputs, and model artifact compatibility.
- `.pi/skills/mlflow-onboarding/`, `.pi/skills/querying-mlflow-metrics/`, `.pi/skills/searching-mlflow-docs/` — use when wiring MLflow artifacts/metrics and validating run lineage.
- `.pi/skills/project-artifact-cleanup/` — use when adding the `ml_preprocessing` artifact set to avoid stale/local-only artifacts and unsafe persistence paths.
- `.pi/skills/repo-postgres-migrations/` — use only if the implementation stores plan/execution metadata in SQL beyond existing object-storage/control-plane records.

### Suggested subagent use

- `scout` — first read-only pass per slice: summarize current file locations, route names, tests, and reusable helpers before implementation.
- `context-builder` — build compact implementation context for complex slices such as artifact persistence + planner tools or runtime transformer migration.
- `planner` — refine subplans for high-risk slices: schema/tool contract, train-only leakage prevention, runtime backward compatibility.
- `worker` — single-writer implementation agent for each approved slice. Do not parallelize writes to the same backend/frontend files.
- `reviewer` — review every slice for data leakage, tenant isolation, hardcoding/client-specific logic, raw path/object-key exposure, and test adequacy.
- `oracle` — use for consistency checks before changing public artifact contracts or deciding legacy compatibility behavior.

### Recommended slice ownership

1. Artifact/schema slice: `scout` → `planner` → `worker` → `reviewer`.
2. Evidence/tool planner slice: `context-builder` with `MIRAI_MLPREPROCESSING_SKILL.md` → `worker` → `reviewer`.
3. Deterministic executor + `model_table_preprocessed.csv`: `planner` → `worker` → `reviewer` with `surrogate-model-debugging`.
4. Training/runtime migration: `context-builder` → `worker` → `reviewer` with MLflow and surrogate-model skills.
5. UI streaming/export slice: `worker` → `reviewer` with `scientific-ui-clarity`.
6. Final hardening: `reviewer` + `oracle` for isolation, leakage, and reusable/non-hardcoded design.

## Steps

- [ ] Define the artifact contract:
  - Add `ml_preprocessing` to `LIFECYCLE_ARTIFACT_SETS` with an allowlisted layout. Because current persistence matches exact relative file names, either persist stable filenames such as `plans/current/preprocessing_plan.json` and `runs/current/preprocessing_fitted.json` with `plan_id`/`run_id` inside the JSON, or extend `_iter_named_files(...)` with a tightly validated pattern allowlist for `plans/{safe_id}/...` and `runs/{safe_id}/...`.
  - `ml_preprocessing_plan.schema.json` for typed draft/approved decisions.
  - `ml_preprocessing_fitted.schema.json` for fitted train-only transform state.
  - `ml_preprocessing_report.json` for EDA evidence refs, risks, unresolved questions, approval, lineage, and staleness checks.
  - `model_table_ml_preprocessed.csv` or array artifacts for debugging/training, while preserving `canonical/model_table.csv` unchanged.
  - Include `workspace_id`, `project_id`, `dataset_id`, `ingestion_session_id`, `plan_id`, `run_id`, artifact checksums, and `fit_scope: train_split_only` in persisted metadata.
- [ ] Define deterministic preprocessing tools for MVP v1:
  - `impute_numeric`: `none`, `mean`, `median`, `constant`.
  - `minmax_scaler`: fitted train-only min/max with zero-range handling and reversible metadata.
  - `standard_scaler`: fitted train-only mean/std with zero-variance handling and reversible metadata.
  - `robust_scaler`: fitted train-only median/IQR or quantile range with zero-IQR handling.
  - `log1p_feature`: only for non-negative/support-safe variables when EDA justifies skew reduction; include inverse capability only where mathematically safe and intended.
  - `clip_numeric`: only when EDA and domain bounds justify clipping; preserve clipping report.
  - `one_hot_encoder`: low-cardinality categorical variables with train-only vocabulary and unknown-category policy.
  - `passthrough` and `drop_from_training` for explicit no-op/exclusion decisions.
  - `target_transform`: support `none`, `standard_scaler`, `minmax_scaler` as reversible output transforms, with inverse-transform metadata.
- [ ] Implement deterministic evidence extraction from current EDA/y-data artifacts through narrow read-only tools:
  - Build tools on top of `get_preprocessing_eda_summary(...)`, `get_preprocessing_review_report(...)`, `get_preprocessing_status(...)`, and existing local-or-object-storage hydration helpers.
  - `get_preprocessing_readiness()`.
  - `get_dataset_contract()`.
  - `get_active_model_table_summary()`.
  - `get_eda_overview()`.
  - `get_ydata_profile_summary()` backed by `eda/ydata_profile.json` when available; fall back to `eda_report.json`/`dataset_profile.json` without failing the lifecycle.
  - `get_column_profile(column_name)`.
  - `get_missingness_report()`.
  - `get_distribution_summary(column_name)`.
  - `get_outlier_summary(column_name)`.
  - `get_correlation_summary()`.
  - `get_categorical_cardinality_summary()`.
  - `get_duplicate_summary()`.
  - `get_split_and_leakage_context()`.
  - `get_existing_preprocessing_status()`.
  - `get_training_context()`.
  - Evidence should include missingness rates/patterns, numeric summaries, skewness when available, min/max, percentiles, zero/negative support, IQR/MAD/outlier candidates, categorical cardinality, likely ID flags, correlation/leakage risks, split/group/time metadata, y-data warnings, source artifact hashes, and staleness warnings.
  - Tools must return sanitized, bounded summaries and evidence IDs, not raw object keys/URIs, absolute paths, or full datasets.
- [ ] Implement a scoped preprocessing planner service/agent loop:
  - Server binds workspace/project/dataset/session from authenticated context and selected ingestion session; request bodies may reference only plan options, not alternate artifact paths/scopes.
  - Load `MIRAI_MLPREPROCESSING_SKILL.md` into every LLM call.
  - Provide only bounded evidence and allowlisted actions.
  - Require every column action to include `evidence_refs`, `reason`, `risk_level`, `reversibility` where relevant, and the chosen generic method, e.g. `minmax`, `standard`, or `robust`.
  - Validate LLM output against strict Pydantic schemas with `extra="forbid"`.
  - Persist draft/approved plans with `persist_session_artifact_set(..., artifact_set="ml_preprocessing", ...)` and sanitized public summaries.
- [ ] Implement plan validation/policy gates:
  - Reject free-form code, paths, SQL, scope fields, raw object keys/URIs, absolute local paths, or unknown variable IDs.
  - Reject evidence or artifact references whose `workspace_id`, `project_id`, `dataset_id`, or `ingestion_session_id` do not exactly match the selected session.
  - Reject stale plans when canonical/EDA/schema/split checksums differ from the approved plan lineage.
  - Reject fitting on all rows; all fitted statistics must declare `fit_scope=train_split_only`.
  - Reject irreversible target transforms unless the plan marks outputs as not directly comparable and product approves it.
  - Stop in `preprocessing_plan_needs_input` for ambiguous target columns, IDs, groups, time leakage, high missingness, or questionable transforms.
- [ ] Implement deterministic executor:
  - Read approved plan + canonical table + split column from the selected session through scoped workspace helpers.
  - Fit all imputers/scalers/encoders on train rows only.
  - Apply to train/validation/test consistently.
  - Write the actual training input as `model_table_preprocessed.csv` plus matrix artifacts if needed by trainers.
  - Persist fitted state, transformed table/matrices, feature map, transform warnings, checksums, and lineage under the new `ml_preprocessing` artifact set.
  - Ensure the fitted artifact is generic: method dispatch by variable/action (`minmax_scaler`, `standard_scaler`, `robust_scaler`, etc.), not project/client-specific Python branches.
  - Finish with status `ml_preprocessing_ready_for_training` and a generated summary explaining what changed, why, and any warnings.
- [ ] Update training:
  - Require approved + executed ML preprocessing v1 before training, or explicitly allow legacy fallback for existing demos.
  - Use preprocessed arrays/table and feature map rather than internal hardcoded `SimpleImputer + MinMaxScaler` pipelines.
  - Log plan/fitted/report artifacts to MLflow and include checksums in `training_manifest.json`.
- [ ] Update inference/runtime:
  - Load `preprocessing_fitted.json` with the champion model artifacts.
  - Apply input transforms by method/variable order.
  - Apply output inverse transforms for scaled targets.
  - Keep raw user input/output labels/units from schema and domain metadata.
- [ ] Add deterministic UI workflow:
  - Primary home: existing Preprocessing Review page, because this is a lifecycle gate before training.
  - Add an explicit **Start ML preprocessing** button that deterministically begins the scoped lifecycle for the selected session.
  - Show token-streaming/progress in the existing chat style: evidence loading → skill/policy loaded → plan drafted → validation gates → awaiting approval → executor running → `ml_preprocessing_ready_for_training`.
  - The streaming text should reduce user anxiety but not grant extra tool power; backend status remains the source of truth.
  - Secondary entry: Data Scientist tab can offer “Explain/regenerate ML preprocessing plan” and deep-link to the review page for approval/execution.
  - Surface EDA evidence summary, selected deterministic tools, plan actions, risks, and unresolved questions.
  - Add approve/reject/regenerate controls.
  - On completion, show “Preprocessing ready — this is what we did”, link/download `model_table_preprocessed.csv`, and offer export of the summary/report/manifest.
  - Make it explicit that canonical data is untouched and training uses the approved ML preprocessing version.
- [ ] Add tests:
  - Train-only fit leakage test with validation/test extrema that would change scaler stats if leaked.
  - Standard/minmax/robust scaler transform + inverse-transform tests.
  - Missing-value imputation tests.
  - Target scaling inverse prediction test.
  - Tenant isolation and redaction tests for planner tools.
  - Legacy artifact compatibility tests.

## Verification

- Backend unit tests for schemas, policy validation, transformer fit/apply/inverse, and leakage prevention.
- Integration test: upload/generate canonical `model_table.csv` → ensure y-data/EDA exists → click/start ML preprocessing with mocked provider streaming → approve plan → execute preprocessing → produce `model_table_preprocessed.csv` → train → predict → confirm inverse-scaled outputs are in original units.
- Verify `canonical/model_table.csv` checksum is unchanged before/after ML preprocessing execution.
- Verify `model_table_preprocessed.csv` is the artifact consumed by training and is tied to the approved fitted preprocessing checksum.
- Verify `training_manifest.json` includes model table checksum, schema checksum, EDA/profile checksums, preprocessing plan checksum, and fitted preprocessing checksum.
- Verify MLflow run artifacts include schema, preprocessing plan, fitted preprocessing, report, metrics, predictions, and training manifest.
- Restart/local-cache-miss integration test: restore latest persisted session, hydrate EDA/profile artifacts from object storage, generate/execute ML preprocessing without local-only assumptions.
- Tenant isolation test: two workspaces/projects with similarly named datasets cannot read each other's EDA/profile/ML preprocessing artifacts, and public API payloads do not expose raw object keys/URIs.
- Verify UI reaches `ml_preprocessing_ready_for_training`, displays “Preprocessing ready — this is what we did”, and exports/downloads summary, manifest, fitted artifact, and `model_table_preprocessed.csv`.
- Frontend build after UI changes.

## Product decisions for v1

- Approval should be mandatory for all new training requests. Legacy fallback may remain only for existing fixtures/demos during migration.
- Target/output scaling should be supported as a reversible artifact capability, but default to `none` unless EDA/model-family evidence justifies it and the plan explains metric/inference implications. All reported predictions and metrics must be inverse-transformed into original units.
- The first UI should live in the existing Preprocessing Review lifecycle page, start from an explicit deterministic **Start ML preprocessing** button, and stream progress/explanations in chat style while backend status remains authoritative. The Data Scientist tab acts as a conversational explanation/regeneration entry point against the same backend state.
- v1 should focus on imputation, scaling, safe categorical encoding, target scaling/inverse transforms, and leakage-safe fitting. PCA, target encoding, SMOTE, arbitrary feature engineering, and autonomous code execution remain out of scope by default.
