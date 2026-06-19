# Postgres control plane bootstrap

This directory contains the Railway Level 2 Postgres/RLS control plane.

Railway note: the `postgres-volume` belongs to the managed Railway `Postgres` service. Do not mount that volume into the `mirai-doe` app service. App/runtime services connect with `DATABASE_URL`.

For this phase, migrations are simple SQL scripts applied by an operator command (`psql`/Railway shell), not app-startup migrations and not Alembic. This keeps the demo explicit and auditable while the schema is still settling.

- `migrations/001_workspace_control_plane.sql` creates workspace, Clerk-user mapping, project metadata, and artifact-pointer tables.
- `migrations/002_runtime_control_plane.sql` adds datasets, schema manifests, training runs, models, recommendations, observations, and audit logs.
- `migrations/004_dataset_upload_metadata.sql` backfills dataset upload integrity metadata columns used by live intake writes.
- `seeds/001_seed_demo_control_plane.sql` is the earlier broad demo seed.
- `seeds/002_seed_fraunhofer_fuel_cell_runtime.sql` is the current runtime seed/backfill and intentionally seeds only Fraunhofer fuel-cell rows. Battery remains deferred for a later implementation.

Raw datasets, canonical tables, model blobs, MLflow artifacts, BO artifacts, and review artifacts must not be stored in SQL. Bucket names and object prefixes are routing metadata, not credentials; access keys, secret keys, and endpoints remain in Railway/env and must never be printed or committed. Store objects under workspace/project-scoped prefixes such as:

- `workspaces/<workspace_id>/uploads/...`
- `workspaces/<workspace_id>/canonical/...`
- `workspaces/<workspace_id>/training/...`
- `workspaces/<workspace_id>/mlflow/...`
- `workspaces/<workspace_id>/bo/...`
- `workspaces/<workspace_id>/reviews/...`

`artifact_objects.object_uri` has a SQL check constraint that rejects unscoped object paths.

## Apply order

Apply in order after confirming `DATABASE_URL` points to the intended Railway Postgres database:

```bash
psql "$DATABASE_URL" -f backend/db/migrations/001_workspace_control_plane.sql
psql "$DATABASE_URL" -f backend/db/migrations/002_runtime_control_plane.sql
psql "$DATABASE_URL" -f backend/db/migrations/003_project_storage_metadata.sql
psql "$DATABASE_URL" -f backend/db/migrations/004_dataset_upload_metadata.sql
psql "$DATABASE_URL" -f backend/db/seeds/002_seed_fraunhofer_fuel_cell_runtime.sql
```

Use `001_seed_demo_control_plane.sql` only for local/demo compatibility where battery placeholder rows are still useful. Do not use it as the current runtime seed for the Clerk/Fraunhofer-only Railway cutover.

## RLS convention

Application connections must set the current workspace before querying protected tables:

```sql
SELECT set_config('app.workspace_id', '<workspace_id>', false);
```

RLS policies then restrict reads/writes to that workspace. Tests should use a non-superuser role because Postgres superusers bypass RLS.
