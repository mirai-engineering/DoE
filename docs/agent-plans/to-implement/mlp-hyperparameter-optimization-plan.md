# UI-Configurable Training, MLflow Lifecycle, and MLP Improvement Plan

## Context

The platform is evolving from a fixed PEM fuel-cell training demo into an OEM-generic DoE engine where non-ML engineers can launch reproducible surrogate-model training runs from approved intake/preprocessing artifacts.

The current Preprocessing Review page shows a fixed "Training plan - Default approved model sweep". That is too rigid. Users should be able to configure MVLR/Ridge/MLP hyperparameters from the UI, run comparable training requests, and use MLflow to manage the lifecycle:

- every trainable candidate is logged to MLflow;
- deployable models are registered;
- best model from a training request becomes `challenger`;
- `champion` is selected manually in the MLflow UI;
- the app reflects champion/challenger state after refresh;
- backend serving prefers `champion`, then `challenger`, then packaged/session artifact fallback.

Current real-data trainer authority:

```text
backend/training/real_training_pipeline/train_real_fuel_cell_models.py
backend/training/real_training_pipeline/mlflow_utils.py
```

Do not use older root-level trainer paths as implementation targets except where compatibility wrappers still exist.

## Approach

Implement a configurable training-request layer that stores user-selected hyperparameters, passes them to the real training pipeline, logs all runs to MLflow, registers deployable model versions, and exposes lifecycle status in Model Quality.

The UI should show advanced settings directly, not hide them behind only a simplified preset. It can still provide quick-start presets, but the actual hyperparameters must be visible and editable.

Recommended training flow:

1. User uploads data.
2. Mirai infers metadata/plot setup.
3. Admin approves metadata and preprocessing.
4. User reviews/edit training configuration.
5. User creates training request.
6. User starts training.
7. Backend runs selected MVLR/Ridge/MLP candidates.
8. Every candidate logs params/metrics/artifacts to MLflow with project/session/request tags.
9. Best validation candidate is registered and assigned `challenger`.
10. User may manually promote `champion` in MLflow UI.
11. App Model Quality reflects champion/challenger aliases and served-model source.

## Training UI design

Location:

```text
frontend/src/components/PreprocessingReviewPage.tsx
```

Replace the fixed static training-plan card with an editable **Training Configuration** section.

### Top-level controls

- Training request name/notes.
- Model families:
  - `mean_baseline` mandatory or default-on sanity baseline.
  - `mvlr` / linear baseline.
  - `ridge` regularized linear baseline.
  - `mlp` neural surrogate.
- Search mode:
  - `single_config`
  - `small_sweep_1h`
  - `balanced_sweep_2h`
- Max wall-clock budget target:
  - default: 1 hour
  - selectable: 30 min, 1 hour, 2 hours
- Seeds:
  - quick: `[7]`
  - stability: `[7, 13, 21]`

### MVLR / Ridge controls

Expose:

- include MVLR: boolean
- fit intercept: boolean
- include Ridge: boolean
- Ridge alpha values:
  - default: `[0.01, 0.1, 1.0, 10.0]`

Rationale:

- Plain MVLR remains an interpretable baseline.
- Ridge is acceptable as a regularized linear baseline and may outperform unconstrained MVLR on grouped OEM datasets.

### MLP advanced controls

Expose advanced settings directly:

- architecture family:
  - `plain_mlp`
  - `shared_trunk_multi_head`
- hidden layer presets for `plain_mlp`:
  - `[64, 32]`
  - `[128, 64, 32]`
  - `[192, 96, 48]`
  - custom comma-separated list
- shared-trunk/head settings:
  - trunk hidden layers, default `[128, 128]`
  - current-density/output-family head layers, default `[64]`
  - secondary output head layers, default `[32]`
- activation:
  - `SiLU`
  - `GELU`
  - `ReLU`
- normalization:
  - `layer_norm`
  - `batch_norm`
  - `none`
- dropout:
  - default options: `0`, `0.02`, `0.05`, `0.10`, `0.15`
- optimizer:
  - `AdamW`
  - `Adam`
- learning rate:
  - default options: `0.0005`, `0.001`, `0.003`, `0.005`
- weight decay:
  - default options: `0`, `1e-5`, `1e-4`, `1e-3`
- batch size:
  - `full_batch`
  - `64`
  - `128`
  - `256`
- max epochs:
  - default `500`
  - max UI guardrail `1500`
- early stopping patience:
  - default `100`
- loss:
  - `mse`
  - `smooth_l1`
  - `weighted_mse`
  - `weighted_smooth_l1`
- output weighting:
  - default use project output weights if available;
  - otherwise equal weights across all outputs.

User decision: optimization priority should be **all outputs**, not only current-density outputs. Therefore the default HPO selection metric should weight all approved outputs equally unless the user explicitly changes weights.

## Recommended MLP architecture for improved results

For the 1–2 hour compute budget, prioritize a compact but more expressive architecture that can reduce target interference.

Recommended new architecture family:

```text
shared_trunk_multi_head
```

Generic structure:

```text
Input features
  -> shared trunk
  -> output-family heads
  -> concatenated outputs in schema order
```

For the PEM project default:

```text
Input dim: 7

Shared trunk:
Linear(7, 128)
LayerNorm
SiLU
Dropout(0.05)
Linear(128, 128)
LayerNorm
SiLU
Dropout(0.05)

Head A: current-density outputs
Linear(128, 64)
SiLU
Linear(64, 2)  # bol_current_density, eol_current_density

Head B: ECSA/degradation outputs
Linear(128, 32)
SiLU
Linear(32, 2)  # bol_ecsa, ecsa_loss
```

For generic OEM projects, head grouping should be inferred from approved metadata when available. If no output groups exist, use one head per output or a single shared output head depending on search setting.

Why this may improve results:

- Shared trunk learns common formulation/process/test representation.
- Separate heads reduce interference between output families with different noise patterns.
- SmoothL1 or weighted SmoothL1 can reduce sensitivity to noisy rows/interpolation artifacts.
- Ridge and MVLR remain strong baselines to avoid overclaiming ANN value.

## 1–2 hour search design

Do not run a huge unconstrained random search. Use a bounded structured search.

### Stage 1: candidate sweep

Target: ~12–24 candidate configs, one seed each.

Candidates:

- MVLR baseline.
- Ridge alphas: `0.01`, `0.1`, `1.0`, `10.0`.
- Plain MLP configs:
  - `[64, 32]`, SiLU, dropout 0.05, lr 0.003, weight decay 1e-4, SmoothL1.
  - `[128, 64, 32]`, SiLU, dropout 0.05, lr 0.003, weight decay 1e-4, SmoothL1.
  - `[192, 96, 48]`, GELU, dropout 0.10, lr 0.001, weight decay 1e-4, weighted SmoothL1.
- Shared-trunk multi-head configs:
  - trunk `[128, 128]`, heads `[64]` / `[32]`, SiLU, dropout 0.05, lr 0.003.
  - trunk `[192, 128]`, heads `[64]` / `[32]`, GELU, dropout 0.10, lr 0.001.
  - trunk `[96, 96]`, heads `[48]` / `[32]`, SiLU, dropout 0.02, lr 0.003.
- Batch variants for best-looking few configs:
  - full batch
  - batch 128

### Stage 2: stability rerun

Take top 3 configs by validation weighted normalized RMSE and rerun with seeds:

```text
[7, 13, 21]
```

Selection remains validation-only. Final test is reported for evidence, not optimized directly.

### Selection metric

Primary:

```text
validation_weighted_normalized_rmSE
```

Default output weights:

- equal across all approved outputs unless user configured otherwise.

Secondary guardrails:

- compare against MVLR and Ridge on validation metrics;
- report final test metrics only after shortlist selection;
- no BO holdout leakage;
- no champion auto-promotion.

## MLflow lifecycle design

### Run naming

Use MLflow-generated run names. Do not manually override run name.

### Required tags

Every candidate run must log:

```text
project_id
schema_project_id
dataset_id
ingestion_session_id
training_request_id
model_family
model_architecture_family
lifecycle_role = candidate | challenger
metadata_template_id
split_strategy
```

### Required params

Log all relevant training params:

```text
fit_intercept
ridge_alpha
architecture_family
hidden_layers
trunk_layers
head_layers
activation
normalization
dropout
optimizer
learning_rate
weight_decay
batch_size
max_epochs
early_stopping_patience
loss
output_weights
seed
search_mode
```

### Required metrics

Log per split and per output:

```text
validation_weighted_normalized_rmse
test_weighted_normalized_rmse
validation_mean_r2
test_mean_r2
per_output_rmse
per_output_mae
per_output_r2
baseline_improvement
```

### Model registration

For every deployable candidate:

- export ONNX;
- log model artifact;
- register model under uploaded/project-specific registered model name;
- tag model version with training request ID and model family.

After training request completion:

```text
challenger -> best validation candidate version
```

Never set:

```text
champion
```

automatically.

Champion is selected manually in MLflow UI.

## Serving and UI lifecycle behavior

Backend serving policy:

1. Serve MLflow `champion` alias if it exists and model loading is enabled.
2. Else serve MLflow `challenger` alias if it exists.
3. Else serve latest session training artifact.
4. Else serve packaged artifact.

Model Quality UI should show:

- registered model name;
- champion version, if present;
- challenger version, if present;
- currently served source:
  - `champion`
  - `challenger`
  - `session artifact`
  - `packaged artifact`
- latest training request ID;
- top candidate table from the request;
- link/instructions to open MLflow UI and promote champion manually.

If the user promotes a champion in MLflow UI, refreshing Model Quality should reflect the new champion alias.

## Backend implementation files

- `backend/app/services/training_requests.py`
  - store full training config in request JSON;
  - pass config into training pipeline;
  - persist candidate summary/top trials.
- `backend/app/schemas.py`
  - add training config request schemas.
- `backend/app/main.py`
  - expose request create/start/status with config payload.
- `backend/training/real_training_pipeline/train_real_fuel_cell_models.py`
  - parameterize MVLR/Ridge/MLP configs;
  - add shared-trunk multi-head architecture;
  - add loss/batch/optimizer/scheduler options;
  - log all MLflow params/metrics;
  - register deployable candidates;
  - set challenger only.
- `backend/training/real_training_pipeline/mlflow_utils.py`
  - strengthen alias lookup/set helpers;
  - add model-version tagging utilities if needed.
- `backend/app/services/mlflow_registry.py`
  - robust champion/challenger alias resolution;
  - expose alias state to Model Quality.
- `backend/app/services/model_loader.py`
  - serve champion > challenger > session artifact > packaged fallback.
- `backend/app/services/model_quality.py`
  - include champion/challenger lifecycle state and request candidate table.
- `backend/tests/test_api.py`
  - training config schema/API tests.
- `backend/tests/test_real_fuel_cell_data_pipeline.py`
  - no BO holdout leakage;
  - configurable training smoke test;
  - challenger alias behavior.

## Frontend implementation files

- `frontend/src/components/PreprocessingReviewPage.tsx`
  - replace fixed training plan with editable Training Configuration form.
- `frontend/src/lib/api.ts`
  - add training config types and payloads.
- `frontend/src/components/ModelQualityPage.tsx`
  - show champion/challenger lifecycle state;
  - show candidate comparison table;
  - show manual champion-promotion guidance.

## Reuse

- Reuse approved metadata and schema labels from the new Metadata & Plot Setup flow.
- Reuse existing session-scoped artifact resolution.
- Reuse existing MLflow alias policy: `challenger` automatic, `champion` manual.
- Reuse existing Model Quality metrics, prediction diagnostics, residuals, and export flows.
- Reuse existing grouped split and BO holdout logic. Do not alter split assignment during HPO.

## Steps

- [ ] Define training configuration schemas for MVLR/Ridge/MLP/search settings.
- [ ] Update training request creation API to accept and persist full config.
- [ ] Replace static training-plan UI with editable advanced Training Configuration controls.
- [ ] Parameterize MVLR and add Ridge candidates.
- [ ] Parameterize existing plain MLP architecture and training hyperparameters.
- [ ] Add shared-trunk multi-head MLP architecture.
- [ ] Add configurable losses: MSE, SmoothL1, weighted MSE, weighted SmoothL1.
- [ ] Add configurable batch size/full-batch training.
- [ ] Implement bounded search modes for 30 min / 1 h / 2 h budgets.
- [ ] Log every candidate to MLflow with required tags/params/metrics.
- [ ] Register deployable ONNX candidates in MLflow.
- [ ] Set best validation candidate as `challenger` only.
- [ ] Update model loader serving priority: champion > challenger > session artifact > packaged.
- [ ] Update Model Quality to display champion/challenger/served-source state.
- [ ] Add candidate comparison table and top-trial artifacts to Model Quality.
- [ ] Add tests for config persistence, no BO holdout leakage, MLflow alias behavior, and generic schema compatibility.

## Verification

Backend:

```bash
cd backend
uv run pytest tests/test_api.py tests/test_real_fuel_cell_data_pipeline.py -q
```

Frontend:

```bash
cd frontend
npm run build
```

Manual end-to-end:

1. Upload PEM package.
2. Run preprocessing.
3. Approve Metadata & Plot Setup.
4. Approve preprocessing.
5. Configure training with advanced settings.
6. Start training.
7. Confirm MLflow experiment uses uploaded `project_id`.
8. Confirm candidate runs have expected params/tags.
9. Confirm registered model versions exist.
10. Confirm `challenger` alias points to best validation candidate.
11. Promote `champion` manually in MLflow UI.
12. Refresh Model Quality and confirm champion/served-source state updates.
13. Confirm BO holdout cells are absent from train/validation/test metrics.

MLflow UI:

```bash
cd backend
uv run mlflow ui --backend-store-uri ./mlruns --host 127.0.0.1 --port 5000
```

## Acceptance Criteria

- Non-ML users can configure advanced MVLR/Ridge/MLP training settings in the UI.
- Training requests persist exact hyperparameters.
- Every candidate logs to MLflow with project/session/request identity.
- Deployable candidates are registered.
- Best validation candidate becomes `challenger`.
- `champion` is never set automatically.
- Manual MLflow champion promotion is reflected in Model Quality after refresh.
- Backend serving prefers champion, then challenger, then fallback artifacts.
- Shared-trunk multi-head MLP can be selected and compared.
- Search can run within ~1–2 hours using bounded structured candidates.
- No BO holdout leakage.
