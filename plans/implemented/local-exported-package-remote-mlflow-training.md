# Local Exported Package Training with Remote MLflow Plan

## Context

An approved training package exported from the Railway UI is placed locally under a repository path such as:

```text
training-runs/Mirai-DoE-Training-Package-Demo-FuelCell/
  model_table.csv
  schema.json
  training_manifest.json
```

The package is the approved input to the ML pipeline. Railway remains the control plane for upload, preprocessing, approval, and export; local MacBook training should only consume the exported package and log runs/artifacts/models to remote MLflow.

## Approach

Add a focused local-only entrypoint that validates the exported package, copies only the required immutable inputs into a gitignored local working directory, synthesizes the small `preprocessing.json` layout expected by the existing generic trainer, and delegates training to `train_generic_project(...)`.

The implementation should reuse the existing generic tabular DoE trainer instead of creating a parallel trainer:

- `backend/ml_lifecycle/training/generic_tabular_doe/train.py` already provides:
  - candidate model families: mean baseline, multivariate linear regression, Ridge, and MLP;
  - MLflow experiment/run logging;
  - metric and artifact logging;
  - selected challenger registration/aliasing;
  - MLP ONNX export and ONNX artifact logging;
  - remote MLflow/local fallback guard helpers through `MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW` and `MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS`.
- The new entrypoint should only adapt the exported package into the existing expected inputs:
  - `data_dir/model_table.csv`;
  - `artifact_dir/schema.json`;
  - `artifact_dir/preprocessing.json` with `input_order`, `output_order`, package metadata, and split strategy.

Before training starts, the entrypoint must validate package integrity and remote MLflow availability so it fails clearly and never silently writes to `backend/mlruns`.

## Files to modify

- `backend/ml_lifecycle/training/run_exported_package.py` — new local-only CLI module.
- `backend/ml_lifecycle/training/generic_tabular_doe/train.py` — small extension only if needed to accept extra MLflow tags/artifacts from `training_config` without changing existing training behavior.
- `backend/tests/test_local_exported_package_training.py` — lightweight parser/validation/guard tests.
- `.gitignore` — ignore `backend/.local-training-runs/`, `backend/.env.training.local`, and likely root `training-runs/` if exported packages should stay local-only.
- `backend/.env.training.local.example` — local-only remote-MLflow template.
- `docs/local_training_with_remote_mlflow.md` — operator guide.

## Reuse

- `train_generic_project(project_id, data_dir, artifact_dir, training_config)` in `backend/ml_lifecycle/training/generic_tabular_doe/train.py` for actual model training, metrics, MLflow logging, registration, and ONNX export.
- Existing MLflow guard behavior in `backend/ml_lifecycle/training/generic_tabular_doe/train.py`:
  - `MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW` rejects local/file tracking URIs;
  - `MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS` rejects non-`s3://` experiment artifact locations.
- Existing registered model naming convention from `registered_model_name_for_project(...)` in `backend/app/services/mlflow_registry.py` / generic trainer.
- Existing tests in `backend/tests/test_generic_contract_pipeline.py` as patterns for lightweight generic training and MLflow assertions.
- Existing package export manifest format from `build_approved_training_package(...)` in `backend/app/services/training_requests.py`.

## Skills / agents mapping

Use the repo and global skills deliberately during implementation/review:

- **Primary implementation skill:** global `incremental-implementation` for small, reversible changes: CLI module, validation helpers, env example, tests, then docs.
- **Test design skill:** global `test-driven-development` for the package parser, failure-mode tests, and MLflow guard tests before or alongside implementation.
- **MLflow/runtime validation skill:** global `debugging-and-error-recovery` for remote MLflow preflight failures, artifact-location errors, ONNX export problems, and smoke-run troubleshooting.
- **Security/data-boundary skill:** global `security-and-hardening` for verifying no Railway Postgres writes, no direct S3 credential requirements unless proven necessary, no `.object-storage-local` writes, no package mutation, and no local `mlruns` fallback.
- **Documentation skill:** global `documentation-and-adrs` for `docs/local_training_with_remote_mlflow.md` and clear operator instructions.
- **Shipping skill:** global `shipping-and-launch` only for final readiness checks and changed-file/test-result reporting; no Railway deployment is part of this workflow.
- **Railway project skill:** project `.pi/skills/use-railway` should be used only if we need to inspect remote MLflow service reachability/configuration or confirm the Railway MLflow URL. It should not be used to mutate Railway production state for this task.
- **GitHub/project workflow skill:** project `.pi/skills/github-mcp-workflow` is optional for PR/issue workflow only; it is not required for local training implementation.
- **Clerk-related project skills:** not applicable; this workflow does not authenticate to the Mirai API and must not touch Clerk/auth flows.

Recommended subagent/agent split if parallel review is desired after implementation:

- **Implementation agent:** owns `run_exported_package.py`, minimal trainer extension, `.gitignore`, and env example.
- **Test agent:** owns focused pytest coverage for parser failures, MLflow guard behavior, output isolation, and no-local-mlruns fallback.
- **Security review agent:** reviews package immutability, path traversal, local/remote storage boundaries, and secret-surface minimization.
- **Docs/operator agent:** reviews the Markdown guide for exact commands, env setup, common errors, and the explicit no-production-mutation statement.
- **Do not delegate to frontend/browser agents:** no frontend changes are in scope.
- **Do not delegate to Railway deployment agents:** no Railway app deploy or production DB/object-store mutation is in scope.

## Steps

- [ ] Add `backend/ml_lifecycle/training/run_exported_package.py` with an argparse CLI:
  - `--package-dir` required;
  - optional `--output-root backend/.local-training-runs`;
  - optional `--max-epochs` / modest config override for smoke runs if consistent with existing style.
- [ ] Implement package loading/validation:
  - require `training_manifest.json`, `schema.json`, and `model_table.csv`;
  - reject missing/invalid JSON with clear messages;
  - validate manifest identifiers against schema metadata where available;
  - require `project_id`, `workspace_id`, `dataset_id`, `session_id`, `training_request_id`, and `exported_at` where present in the manifest;
  - load feature/target columns from manifest `feature_columns` / `target_columns`, falling back to schema `inputs` / `outputs` only when manifest fields are absent;
  - verify all required feature/target columns exist in `model_table.csv`;
  - verify the table is non-empty;
  - verify a `split` column exists or add a deterministic local split only if this is acceptable with the existing preprocessing assumptions;
  - validate any source checksum metadata supported by the manifest, especially `model_table.csv` and `schema.json` hashes.
- [ ] Implement remote MLflow preflight before training:
  - require `MLFLOW_TRACKING_URI`;
  - require `MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true/1`;
  - require `MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=true/1`;
  - reject `file://`, `localhost`, `127.0.0.1`, and empty tracking URIs;
  - use `mlflow.tracking.MlflowClient` to verify the remote tracking server is reachable before preparing outputs;
  - fail with an actionable error instead of allowing fallback to `backend/mlruns`.
- [ ] Create an immutable-input working layout under `backend/.local-training-runs/<timestamp-or-training-request-id>/`:
  - copy `model_table.csv` to `canonical/model_table.csv`;
  - copy `schema.json` to `artifacts/schema.json`;
  - copy `training_manifest.json` to `artifacts/training_manifest.json`;
  - write `artifacts/preprocessing.json` containing `input_order`, `output_order`, `split_strategy`, package identifiers, and source metadata;
  - never write into the original exported package directory.
- [ ] Build the training config for `train_generic_project(...)`:
  - keep existing default candidate families unless a modest smoke override is supplied;
  - include `mlflow.enabled=true`;
  - include extra MLflow tags/artifact hints if `train_generic_project` is extended to consume them.
- [ ] Add or minimally extend MLflow logging so every candidate run gets package tags:
  - `workspace_id`;
  - `project_id`;
  - `dataset_id`;
  - `session_id`;
  - `training_request_id`;
  - `exported_at`;
  - `source_checksum`;
  - `training_source=approved_export_package`.
- [ ] Ensure source package artifacts are logged to MLflow:
  - `training_manifest.json`;
  - `schema.json`;
  - existing trainer artifacts and ONNX outputs remain logged through `train_generic_project(...)`.
- [ ] Add `backend/.env.training.local.example` with only local-training remote-MLflow variables:
  - `MLFLOW_TRACKING_URI=`;
  - `MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW=true`;
  - `MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS=true`;
  - include artifact-root/S3 variables only if the existing MLflow experiment creation path demonstrably requires them for remote artifact storage, and do not include Railway DB, Clerk, or production API secrets.
- [ ] Update `.gitignore` for real local-only files/directories:
  - `backend/.env.training.local`;
  - `backend/.local-training-runs/`;
  - consider `training-runs/` so exported packages are not accidentally committed.
- [ ] Add focused tests:
  - valid package parses and creates a working layout outside the package directory;
  - missing/invalid manifest/schema/data fails clearly;
  - missing/local MLflow config fails before training;
  - no local `backend/mlruns` fallback is used when remote MLflow is required;
  - generated local output paths are under `backend/.local-training-runs/` and not under the exported package.
- [ ] Add `docs/local_training_with_remote_mlflow.md` covering package placement, `.env.training.local` setup, exact command, MLflow run lookup, common errors/fixes, and the explicit no-Railway-production-mutation statement.

## Verification

From the repository root, after implementation:

```bash
cd backend
uv run pytest tests/test_local_exported_package_training.py -q
```

Static/safety checks:

```bash
git diff --check
```

Expected operator command from the repository root:

```bash
cd backend
set -a
source .env.training.local
set +a
uv run python -m ml_lifecycle.training.run_exported_package \
  --package-dir ../training-runs/Mirai-DoE-Training-Package-Demo-FuelCell
```

If remote MLflow credentials/configuration are available, run a modest smoke training against the real exported package, preferably with a short MLP epoch override if implemented. Confirm:

- remote MLflow has candidate runs under the package project/experiment;
- runs include the package tags;
- `training_manifest.json` and `schema.json` are logged as artifacts;
- model artifacts and ONNX are logged when supported;
- no files are written into the package directory;
- no `backend/mlruns` fallback is created/used;
- no Railway Postgres or direct Railway S3 credentials are needed by the local CLI unless remote MLflow artifact configuration requires them.

## Open decisions / assumptions

- The exported `model_table.csv` is expected to already include the `split` column generated by preprocessing. If not, the implementation should either fail clearly or add a deterministic local split; recommended default is fail clearly unless we confirm local splitting is acceptable for approved package semantics.
- Existing MLflow artifact enforcement expects an `s3://` experiment artifact location when `MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS` is true. If the remote Railway MLflow service already has the experiment configured, the local CLI may not need any bucket variables. If it needs to create a new experiment, it may need a non-secret artifact root/bucket setting; do not add direct S3 credentials to `.env.training.local.example` unless verified necessary.
