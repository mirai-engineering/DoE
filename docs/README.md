# Documentation index

Documentation is grouped by intended reader and use.

## Tutorials / how to use

Use these when running or operating the DoE app.

- `tutorials/DOCKER_DEPLOYMENT.md` — Docker Compose and nginx reverse-proxy workflow.
- `tutorials/BO_OPTIMIZATION_LOOP_GUIDE.md` — how to use Batch Explorer and the Bayesian Optimization loop.

## Reference / explanations

Use these for durable background, calculations, lifecycle details, and data provenance.

- `reference/BUSINESS_IMPACT_CALCULATION.md` — formulas and references behind the Business Impact tab.
- `reference/MLFLOW_MODEL_LIFECYCLE.md` — model registry, champion loading, metrics, and review lifecycle.
- `reference/REAL_FUEL_CELL_DATASET.md` — real PEM fuel-cell dataset schema, artifacts, and transformation rules.

## Agent plans

Use these as implementation plans for coding agents. New feature plans should be created under `agent-plans/to-implement/` and moved to `agent-plans/implemented/` after completion.

- `agent-plans/implemented/` — completed or accepted implementation plans.
- `agent-plans/to-implement/` — follow-ups and active/incomplete plans.

Current follow-ups include:

- `agent-plans/to-implement/minio-data-intake-object-storage-followup-todo.md`
- `agent-plans/to-implement/mlp-hyperparameter-optimization-plan.md`
- `agent-plans/to-implement/scientist-preprocessing-agent-plan.md`
