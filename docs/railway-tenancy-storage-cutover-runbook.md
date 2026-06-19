# Railway tenancy/storage hard-reset cutover runbook

This runbook validates the canonical Mirai DoE demo model:

```text
Clerk user A -> clerk_user_workspaces -> fraunhofer -> mirai-fuel-cells-demo/workspaces/fraunhofer
Clerk user B -> authenticated, no membership -> setup-required, no project/upload/train/predict access
```

## Safety boundaries

Do not delete Railway services, the Postgres service/database, bucket resources, credentials, domains, deployments, project configuration, source code, or Git history. Do not print secret values.

The reset command is destructive only to application-level demo DB rows and approved object prefixes inside the existing bucket.

## Canonical production variables

Required:

```text
CLERK_AUTH_REQUIRED=true
CLERK_JWT_ISSUER
DATABASE_URL
MIRAI_REQUIRE_POSTGRES_CONTROL_PLANE=true
OBJECT_STORAGE_BACKEND=s3
S3_ENDPOINT_URL
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
S3_REGION
VITE_CLERK_PUBLISHABLE_KEY
```

Optional variables should be documented separately per deployment. Deprecated variables should be left untouched in Railway until after validation:

```text
CLERK_ISSUER
CLERK_WORKSPACE_ID_MODE
CLERK_DEFAULT_WORKSPACE_ID
MIRAI_STORAGE_BACKEND
MIRAI_WORKSPACE_BUCKET_MAP
MIRAI_FRAUNHOFER_S3_*
MIRAI_BATTERY_DEMO_S3_*
MIRAI_S3_REGION
DOE_OBJECT_STORE_ROOT
```

Frontend `.env` files must not contain `CLERK_SECRET_KEY`, backend secrets, or S3 secrets.

## Safe commands

Inspect variable names only:

```bash
railway variables --service mirai-doe --environment production | sed 's/=.*//'
```

Deploy code from the selected Git branch using the normal Railway GitHub deployment flow.

Run reset dry-run summary:

```bash
railway run --service mirai-doe --environment production -- \
  uv run python scripts/reset_demo_application_data.py \
  --user-a-id "$MIRAI_DEMO_USER_A_CLERK_ID" \
  --old-workspace-id '<old-user-derived-workspace-id>'
```

After explicit approval only, run the destructive reset:

```bash
railway run --service mirai-doe --environment production -- \
  uv run python scripts/reset_demo_application_data.py --confirm \
  --user-a-id "$MIRAI_DEMO_USER_A_CLERK_ID" \
  --user-b-id "$MIRAI_DEMO_USER_B_CLERK_ID" \
  --old-workspace-id '<old-user-derived-workspace-id>'
```

The script retains/recreates `fraunhofer`, upserts user A as owner, removes user B memberships when provided, removes app-level demo rows in the scoped workspaces, deletes only approved prefixes, and leaves MLflow infrastructure untouched.

## Browser validation

1. Log in as user A.
2. Confirm `/projects` returns active account capabilities.
3. Create a fresh project.
4. Upload a fresh CSV or ZIP through the Railway UI.
5. Confirm DB metadata uses `workspace_id='fraunhofer'` for project/dataset/session/artifact rows.
6. Confirm S3 bucket `mirai-fuel-cells-demo` and keys under `workspaces/fraunhofer/projects/...`.
7. Start a training request.
8. Verify a model/artifact state or an explicit recoverable training failure state.
9. Restart/redeploy the service.
10. Verify the project/session remain visible.
11. Log in as user B.
12. Confirm `/projects` and `/workspaces` show `no_workspace_membership` setup-required state.
13. Confirm user B cannot create projects, upload, train, predict, export, use recommendations/BO/model-quality, or access Fraunhofer URLs by changing ids.

## Rollback

- Redeploy the previous known-good Git commit for code rollback.
- Restore Postgres from the pre-reset backup/snapshot if old demo application records are needed.
- Re-ingest demo objects through the UI if prefixes were deleted.
- Do not delete or recreate Railway infrastructure during rollback.
