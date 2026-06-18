---
name: repo-postgres-migrations
description: >
  Safely create, review, and apply this repo's Postgres SQL migrations for the
  Mirai DoE Railway control plane. Use this skill when changing backend/db/migrations,
  backend/db/seeds, project/workspace/storage schema, RLS, Railway Postgres, or when
  asked how to apply SQL migrations. Emphasizes explicit SQL, idempotent migrations,
  backup/verification queries, Railway secret hygiene, and scoped tenant/storage metadata.
allowed-tools: Bash(git:*), Bash(uv:*), Bash(psql:*), Bash(railway:*), Bash(sed:*), Bash(grep:*), Bash(rg:*), Bash(python3:*), Read, Edit, Write
---

# Repo Postgres Migrations

This repo currently uses explicit SQL files, not Alembic/app-startup migrations.
Treat database changes as operator-applied, auditable production changes.

## Files and order

- Migrations live in `backend/db/migrations/NNN_description.sql`.
- Seeds/backfills live in `backend/db/seeds/NNN_description.sql`.
- Update `backend/db/README.md` whenever apply order or operational assumptions change.
- Apply migrations in numeric order. Do not skip earlier files unless the target DB is known to already contain those schema changes.

Current control-plane order:

```bash
psql "$DATABASE_URL" -f backend/db/migrations/001_workspace_control_plane.sql
psql "$DATABASE_URL" -f backend/db/migrations/002_runtime_control_plane.sql
psql "$DATABASE_URL" -f backend/db/migrations/003_project_storage_metadata.sql
psql "$DATABASE_URL" -f backend/db/seeds/002_seed_fraunhofer_fuel_cell_runtime.sql
```

Use `backend/db/seeds/001_seed_demo_control_plane.sql` only for local/demo compatibility, not as the Railway Fraunhofer cutover seed unless explicitly requested.

## Migration authoring conventions

1. Use `BEGIN; ... COMMIT;` for normal DDL/data backfills.
2. Prefer idempotent statements for operator safety:
   - `CREATE TABLE IF NOT EXISTS`
   - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
   - `CREATE INDEX IF NOT EXISTS`
   - `INSERT ... ON CONFLICT ... DO UPDATE/NOTHING`
3. Keep raw datasets, model blobs, generated artifacts, MLflow runs, and secrets out of SQL.
4. Bucket names and object prefixes are non-secret routing metadata and may be stored/logged sparingly; credentials/endpoints/access keys remain only in Railway/env.
5. Storage metadata should preserve the project scoped object shape:
   - `workspaces/<workspace_id>/projects/<project_id>/...`
6. RLS-sensitive app code should set:

```sql
SELECT set_config('app.workspace_id', '<workspace_id>', false);
```

7. For Clerk tenancy, production workspace ids should derive from verified Clerk JWT `sub` (or configured stable prefixed mode), not frontend-supplied workspace ids or custom editable claims.

## Pre-apply safety checklist

Before applying to Railway Postgres:

1. Confirm branch/commit and migration file content locally:

```bash
git status --short
git log -1 --oneline
sed -n '1,220p' backend/db/migrations/<file>.sql
```

2. Verify Railway context without printing secrets:

```bash
RAILWAY_CALLER=skill:repo-postgres-migrations RAILWAY_AGENT_SESSION=migration-$(date +%s) \
  railway status --json
```

3. Prefer applying through `railway run` so database URLs are injected without being printed. Important Railway nuance: `railway run` injects variables into the local process. If `DATABASE_URL` uses Railway's private hostname such as `postgres.railway.internal`, local `psql` will fail DNS resolution. For local operator commands, prefer `DATABASE_PUBLIC_URL` when it exists; use private `DATABASE_URL` only from code/commands running inside Railway's private network.

Precheck without printing the URL:

```bash
RAILWAY_CALLER=skill:repo-postgres-migrations RAILWAY_AGENT_SESSION=migration-$(date +%s) \
  railway run --environment production --service <app-service> -- \
  sh -lc 'test -n "$DATABASE_PUBLIC_URL" && echo DATABASE_PUBLIC_URL_AVAILABLE || echo DATABASE_PUBLIC_URL_MISSING'
```

Apply from the local repo using the public database URL injected by Railway:

```bash
RAILWAY_CALLER=skill:repo-postgres-migrations RAILWAY_AGENT_SESSION=migration-$(date +%s) \
  railway run --environment production --service <app-service> -- \
  sh -lc 'psql "$DATABASE_PUBLIC_URL" -v ON_ERROR_STOP=1 -f backend/db/migrations/<file>.sql'
```

If `DATABASE_PUBLIC_URL` is missing, do not print secrets. Either add/enable a public DB URL in Railway, use Railway's database shell/connect workflow, or run `psql "$DATABASE_URL"` from an execution context inside Railway's private network.

Do not run `railway variables` or echo `DATABASE_URL`/`DATABASE_PUBLIC_URL` unless the user explicitly asks and secret redaction is guaranteed.

## Post-apply verification

Use read-only SQL checks that do not expose credentials or client data. Examples:

```bash
railway run --environment production --service <app-service> -- sh -lc '
psql "$DATABASE_PUBLIC_URL" -v ON_ERROR_STOP=1 -X -q <<SQL
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = '\''projects'\'' AND column_name = '\''storage'\'';

SELECT workspace_id, project_id, storage->>'\''mode'\'' AS mode,
       storage->>'\''bucket'\'' AS bucket,
       storage->>'\''prefix'\'' AS prefix
FROM projects
ORDER BY workspace_id, project_id;
SQL'
```

The second query prints bucket names/prefixes, which are routing metadata, not secrets; still avoid dumping large rows or unrelated tables.

## Commit hygiene

Before committing migration work:

```bash
git diff --check
git diff --cached --check
```

Stage only scoped SQL/docs/tests/code. Do not stage generated artifacts, local object storage mirrors, MLflow runs, ONNX files, `.env*` secrets, or client datasets.
