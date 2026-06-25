# Implementation Plan: MLflow Pointer-Based Champion Quality Resolution

## Context

The UI still reports missing model-quality / Design Studio data for `ccm_degradation_029a2f61` even though the remote MLflow champion run has the required artifacts (`schema.json`, `metrics_summary.json`, `candidate_comparison.csv`, `predictions.csv`, etc.). The robust fix is to stop treating encrypted/opaque S3 folder names as an app contract. MLflow already owns those artifact locations, and Mirai should resolve them through MLflow Registry + run artifact APIs.

User decisions captured:
- Use **pointer-only durable state** after explicit **Load champion model**.
- Do **not** automatically follow MLflow alias changes; Mirai updates only after the operator clicks Load champion model.
- Railway status currently shows a single bucket resource (`mirai-fuel-cells-demo`) for the project, but implementation should not assume readable S3 key shapes; use MLflow APIs for MLflow artifacts.
- Large `predictions.csv` should not be permanently duplicated unless there is a proven need. Use an app-local ephemeral cache / streamed download via MLflow, not raw S3 path guessing.
- Model Quality and Design Studio should show loaded champion data only after explicit load; otherwise show a clear warning such as “Champion model is not loaded yet.”
- Add operator-facing traceability as a collapsible dropdown.

## Agent and skill mapping

- `scout` agent: read-only discovery before implementation, focused on current MLflow artifact resolution, runtime state, Model Quality, Design Studio, and frontend traceability UI.
- `worker` agent: implement focused slices after plan approval.
- `reviewer` agent: review diff for storage-safety, workspace isolation, and accidental raw-S3 coupling.
- `planning-and-task-breakdown` skill: this plan splits backend pointer resolution, UI warnings, traceability, and tests into verifiable slices.
- `source-driven-development` skill: MLflow MCP / artifact API usage should be checked against official MLflow docs during implementation.
- `incremental-implementation` skill: land backend resolution first, tests second, UI third, avoiding a large mixed change.
- `git-workflow-and-versioning` skill: commit by topic, leaving unrelated untracked files untouched.
- `searching-mlflow-docs` skill: verify the MLflow artifact APIs used for run downloads/listing before changing resolver code.

## Approach

Use MLflow as the source of truth for model artifacts and use Mirai Postgres/runtime state only as the **loaded champion pointer**:

`workspace_id + project_id -> Mirai loaded champion row -> mlflow_import.run_id/model_version/model_uri -> MLflow run artifacts`

Do not build code that guesses or parses MLflow’s S3 object keys. The app should resolve artifacts by immutable MLflow `run_id` after Load champion model. The only persistent Mirai state should be pointer/traceability metadata in existing runtime tables (`training_run`, `champion_model`, metrics JSON). The backend may keep an ephemeral local cache under `.mlflow-cache/<project_id>/run-artifacts/<run_id>/` because MLflow’s Python client downloads artifacts to the local filesystem; this is a runtime cache, not a second durable source of truth.

For `predictions.csv`, prefer a cache-by-run-id model:
- First request after Load champion model downloads the requested run artifact through MLflow if missing.
- Subsequent requests reuse `.mlflow-cache/.../<run_id>/predictions.csv` while the loaded run ID is unchanged.
- Do not load the full CSV into memory unless needed for the existing endpoint response; keep current behavior initially, but make the resolver deterministic. If larger datasets appear, add chunked reads/server pagination as a later performance enhancement.

## Files to modify

Backend:
- `backend/app/services/mlflow_registry.py`
- `backend/app/services/model_quality.py`
- `backend/app/services/project_registry.py`
- `backend/app/services/design_studio.py`
- `backend/app/services/training_requests.py`
- `backend/app/main.py` if response contract additions are needed

Frontend:
- `frontend/src/components/ModelQualityPage.tsx`
- `frontend/src/components/DesignStudioPage.tsx`
- `frontend/src/components/PreprocessingReviewPage.tsx` if Load champion result/traceability display should be improved there

Tests:
- `backend/tests/test_mlflow_durable_pointers.py`
- `backend/tests/test_api.py`
- Add or extend focused tests for model-quality/design-studio loaded-champion behavior.

Docs, if needed:
- `backend/ml_lifecycle/README.md`
- `backend/ml_lifecycle/REMOTE_TRAINING.md`

## Reuse

Existing helpers and patterns to reuse:
- `backend/app/services/mlflow_registry.py::registered_model_name_for_project`
- `backend/app/services/mlflow_registry.py::verify_champion_mlflow_model`
- `backend/app/services/mlflow_registry.py::download_run_artifacts`
- `backend/app/services/mlflow_registry.py::_imported_model_uri_from_runtime`
- `backend/app/services/training_requests.py::load_champion_model`
- `backend/app/services/control_plane.py::get_project_runtime_state`
- `backend/app/services/control_plane.py::activate_champion_model`
- `backend/app/services/model_quality.py::_imported_mlflow_training_artifact_dir`
- `backend/app/services/project_registry.py::_imported_mlflow_artifact_dir`
- Frontend `<details>` dropdown pattern already used in `ModelQualityPage.tsx`.

## Steps

### Phase 1 — Confirm environment/storage assumptions safely

- [ ] After Pi reloads the new MLflow MCP server, inspect MLflow tools with `mcp({ server: "mlflow" })` and use only non-secret queries.
- [ ] Confirm Railway still exposes a single bucket resource via `railway status` / Railway MCP; do **not** print raw variable values.
- [ ] Confirm the champion run artifact location through MLflow client APIs, not direct S3 path parsing.
- [ ] Record in implementation notes that opaque S3 keys are an implementation detail owned by MLflow.

### Phase 2 — Make loaded champion pointer the only workspace runtime source

- [ ] Ensure `load_champion_model()` persists complete pointer metadata in metrics/runtime state: `run_id`, registered model, alias, model version, model URI/source, tracking URI, artifact root/URI if available, loaded timestamp, loaded_by, and required artifact presence.
- [ ] Remove or avoid misleading durable pointer values that imply `training_artifacts/latest/model.onnx` or `mlflow-artifacts/<registered_model>` is the actual loaded champion artifact when using pointer-only MLflow resolution.
- [ ] Keep `download_run_artifacts(..., include_quality=True, include_predictions=True)` as an ephemeral cache step, but describe/cache it as MLflow materialization, not Mirai durable copy.
- [ ] Ensure the cache is keyed by immutable `run_id`, so explicit Load champion to a new version cannot accidentally reuse stale artifacts.

### Phase 3 — Fix backend artifact resolution for Model Quality

- [ ] Update `model_quality._artifact_dir()` to require loaded champion state for workspace projects and resolve artifacts from the loaded champion `mlflow_import.run_id`.
- [ ] Do not fall back to `challenger` alias for authenticated workspace projects.
- [ ] If runtime project exists but no loaded champion pointer exists, raise a clear error: `Champion model is not loaded yet for project_id=...; promote a version to champion in MLflow, then use Load champion model.`
- [ ] Make `_prediction_path()` use the same loaded champion run resolver with `include_predictions=True`.
- [ ] Include traceability metadata in `get_model_quality_summary()` / `active_model` so the UI can show which MLflow run/version backs the quality data.

### Phase 4 — Fix schema and Design Studio workspace propagation

- [ ] Update `project_registry.get_project_schema(project_id, workspace_id)` so a workspace runtime project with loaded champion state can use the champion run’s `schema.json` before returning a pending/empty runtime schema.
- [ ] Ensure output names remain the actual schema output names (`y1`, `y2`, etc.) so they match `predictions.csv` columns (`y1_true`, `y1_pred`, etc.).
- [ ] Pass `workspace_id` through all Design Studio state helpers, especially `get_active_model_metadata(project_id, workspace_id)`.
- [ ] Confirm Design Studio prediction overlays resolve `predictions.csv` from the loaded champion run and do not fall back to `challenger` for workspace projects.

### Phase 5 — Add UI warnings and traceability dropdown

- [ ] In Model Quality, distinguish “missing training” from “champion model is not loaded yet.”
- [ ] Show a small warning when a champion exists in MLflow but Mirai has not loaded it yet, without automatically using that champion.
- [ ] Add a collapsible “MLflow traceability” dropdown showing: workspace ID, project ID, registered model, alias, model version, run ID, model URI/source, tracking URI, loaded_at, loaded_by, and artifact/cache status.
- [ ] Add a similar compact dropdown or status block in Design Studio so operators can see exactly which loaded champion backs predictions.
- [ ] Preserve current UI layout/branding and reuse existing `<details>` styling patterns.

### Phase 6 — Tests and verification

- [ ] Add backend tests proving workspace Model Quality refuses unloaded champions with the new explicit message.
- [ ] Add backend tests proving loaded champion state resolves `metrics_summary.json`, `candidate_comparison.csv`, `schema.json`, and `predictions.csv` by run ID.
- [ ] Add backend tests proving workspace routes do not use `challenger` fallback after Load champion semantics are enabled.
- [ ] Add Design Studio/backend test coverage for `workspace_id` propagation into active model metadata and prediction overlay resolution.
- [ ] Add frontend tests if the project has an established component test pattern; otherwise manually verify UI states.

## Verification

Recommended targeted backend checks:

```bash
cd backend
uv run pytest tests/test_mlflow_durable_pointers.py tests/test_api.py -k "champion or model_quality or design_studio or mlflow" -q
```

Recommended broader backend checks:

```bash
cd backend
uv run pytest tests/test_workspace_storage.py tests/test_local_exported_package_training.py tests/test_mlflow_durable_pointers.py tests/test_training_lifecycle_canonicalization.py -q
```

Manual production/staging checks:
- Load champion for `workspace_id=fraunhofer`, `project_id=ccm_degradation_029a2f61`.
- Open Model Quality and verify outputs are populated, prediction plots use `y1/y2/y3/y4`, and no `0 of 0 outputs` message appears.
- Open Design Studio and verify state loads without `Model quality is not available yet`.
- Confirm the traceability dropdown shows the champion run `ceb304c85b584460a58c28fa2088f9ee` or whichever run is explicitly loaded.
- Promote a different MLflow version to `champion` without clicking Load champion model and verify Mirai continues using the previously loaded pointer until explicit reload.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| MLflow server unavailable at request time | Model Quality/Design Studio may fail after cache miss | Keep run-id cache and return actionable error pointing to MLflow connectivity. |
| `predictions.csv` grows much larger | Pandas full read may become slow/memory-heavy | Keep current behavior for now; add chunked/paginated reads later if real datasets exceed safe size. |
| Runtime schema row is incomplete | UI output dropdown becomes empty | Prefer loaded champion `schema.json` when champion pointer exists. |
| Stale cache after new champion load | Wrong quality data served | Cache path includes immutable run ID and Load champion refreshes the new run. |
| Raw S3 path temptation | Brittle integration with encrypted/opaque folder names | Treat MLflow artifact URIs as opaque and only use MLflow APIs. |

## Commit plan

- `fix: resolve model quality from loaded MLflow champion`
- `fix: propagate workspace champion state to design studio`
- `feat: show MLflow champion traceability in UI`
- `test: cover pointer-only champion artifact resolution`
