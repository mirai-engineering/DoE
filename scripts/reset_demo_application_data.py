#!/usr/bin/env python3
"""Destructively reset Railway demo application data without deleting infrastructure.

Dry-run is the default. Use --confirm to apply DB changes and delete approved
object prefixes inside the existing demo bucket. This script deliberately leaves
Railway services, the Postgres database/service, bucket resources, credentials,
domains, deployments, project configuration, source code, and unknown MLflow
infrastructure untouched.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Iterable

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise SystemExit("psycopg is required; run with `uv run python scripts/reset_demo_application_data.py`") from exc


APP_TABLES_DELETE_ORDER = [
    "observations",
    "recommendations",
    "models",
    "training_runs",
    "schema_manifests",
    "datasets",
    "artifact_objects",
    "audit_logs",
    "projects",
]


def database_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("MIRAI_DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    return "postgresql://" + url.removeprefix("postgres://") if url.startswith("postgres://") else url


def redact(value: str | None) -> str:
    if not value:
        return "<unset>"
    if len(value) <= 12:
        return value[:2] + "…" + value[-2:]
    return value[:8] + "…" + value[-4:]


def safe_workspace(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value or ""):
        raise SystemExit(f"Unsafe workspace id: {value!r}")
    return value


def set_workspace(cur, workspace_id: str) -> None:
    cur.execute("SELECT set_config('app.workspace_id', %s, true)", (workspace_id,))


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (table,))
    return cur.fetchone()[0] is not None


def count_rows(cur, workspace_id: str, table: str) -> int:
    if not table_exists(cur, table):
        return 0
    set_workspace(cur, workspace_id)
    cur.execute(f"SELECT count(*) FROM {table} WHERE workspace_id = %s", (workspace_id,))
    return int(cur.fetchone()[0])


def delete_workspace_rows(cur, workspace_id: str) -> None:
    set_workspace(cur, workspace_id)
    for table in APP_TABLES_DELETE_ORDER:
        if table_exists(cur, table):
            cur.execute(f"DELETE FROM {table} WHERE workspace_id = %s", (workspace_id,))


def upsert_fraunhofer(cur, *, owner_user_id: str, bucket: str, prefix: str) -> None:
    set_workspace(cur, "fraunhofer")
    cur.execute(
        """
        INSERT INTO workspaces (workspace_id, display_name, status, storage, created_at, updated_at)
        VALUES ('fraunhofer', 'Fraunhofer', 'active', %s::jsonb, now(), now())
        ON CONFLICT (workspace_id) DO UPDATE
        SET display_name = 'Fraunhofer', status = 'active', storage = EXCLUDED.storage, updated_at = now()
        """,
        (f'{{"mode":"s3","bucket":"{bucket}","prefix":"{prefix}"}}',),
    )
    cur.execute(
        """
        INSERT INTO clerk_user_workspaces (clerk_user_id, workspace_id, role, created_at)
        VALUES (%s, 'fraunhofer', 'owner', now())
        ON CONFLICT (clerk_user_id, workspace_id) DO UPDATE SET role = 'owner'
        """,
        (owner_user_id,),
    )


def cleanup_memberships(cur, *, owner_user_id: str, user_b_id: str | None, workspace_ids: Iterable[str]) -> None:
    for workspace_id in workspace_ids:
        set_workspace(cur, workspace_id)
        if table_exists(cur, "clerk_user_workspaces"):
            cur.execute(
                "DELETE FROM clerk_user_workspaces WHERE workspace_id = %s AND clerk_user_id <> %s",
                (workspace_id, owner_user_id if workspace_id == "fraunhofer" else ""),
            )
            if user_b_id:
                cur.execute("DELETE FROM clerk_user_workspaces WHERE clerk_user_id = %s", (user_b_id,))


def delete_old_workspace_rows(cur, workspace_ids: Iterable[str]) -> None:
    for workspace_id in workspace_ids:
        if workspace_id == "fraunhofer":
            continue
        set_workspace(cur, workspace_id)
        if table_exists(cur, "workspaces"):
            cur.execute("DELETE FROM workspaces WHERE workspace_id = %s", (workspace_id,))


def s3_client():
    try:
        import boto3  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("boto3 is required for object-prefix deletion") from exc
    endpoint = os.getenv("S3_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL") or os.getenv("MLFLOW_S3_ENDPOINT_URL")
    access_key = os.getenv("S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("S3_REGION") or os.getenv("AWS_DEFAULT_REGION") or "auto"
    if not endpoint or not access_key or not secret_key:
        raise SystemExit("S3_ENDPOINT_URL/S3_ACCESS_KEY_ID/S3_SECRET_ACCESS_KEY are required for --confirm object deletion")
    return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region)


def delete_prefixes(bucket: str, prefixes: list[str], *, confirm: bool) -> None:
    print("Object prefixes approved for deletion:")
    for prefix in prefixes:
        print(f"  - s3://{bucket}/{prefix}")
    if not confirm:
        return
    client = s3_client()
    for prefix in prefixes:
        paginator = client.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            for chunk_start in range(0, len(objects), 1000):
                chunk = objects[chunk_start : chunk_start + 1000]
                if chunk:
                    client.delete_objects(Bucket=bucket, Delete={"Objects": chunk})
                    deleted += len(chunk)
        print(f"Deleted {deleted} objects under s3://{bucket}/{prefix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset Mirai Railway demo application data")
    parser.add_argument("--confirm", action="store_true", help="Actually delete application DB rows and approved object prefixes")
    parser.add_argument("--user-a-id", default=os.getenv("MIRAI_DEMO_USER_A_CLERK_ID"), help="Clerk user id to make owner of fraunhofer")
    parser.add_argument("--user-b-id", default=os.getenv("MIRAI_DEMO_USER_B_CLERK_ID"), help="Optional Clerk user id to ensure unassigned")
    parser.add_argument("--old-workspace-id", action="append", default=[], help="Old user-derived workspace id/prefix to remove; may be repeated")
    parser.add_argument("--bucket", default=os.getenv("MIRAI_DEMO_BUCKET", "mirai-fuel-cells-demo"))
    parser.add_argument("--prefix", default="workspaces/fraunhofer")
    args = parser.parse_args()

    if not args.user_a_id:
        raise SystemExit("--user-a-id or MIRAI_DEMO_USER_A_CLERK_ID is required")
    old_workspaces = [safe_workspace(item) for item in args.old_workspace_id]
    reset_workspaces = ["fraunhofer", *old_workspaces]
    prefixes = ["workspaces/fraunhofer/", *[f"workspaces/{workspace_id}/" for workspace_id in old_workspaces]]

    print("Mirai demo application reset summary")
    print(f"Mode: {'CONFIRM/APPLY' if args.confirm else 'DRY RUN'}")
    print("Retain/recreate workspace: fraunhofer")
    print(f"Retain/create membership: {redact(args.user_a_id)} -> fraunhofer (owner)")
    if args.user_b_id:
        print(f"Ensure no membership for user B: {redact(args.user_b_id)}")
    print("MLflow infrastructure/unknown records: untouched; may remain as orphaned demo history")

    with psycopg.connect(database_url()) as conn:
        with conn.cursor() as cur:
            print("Application DB rows scoped for removal:")
            for workspace_id in reset_workspaces:
                print(f"  workspace {redact(workspace_id) if workspace_id.startswith('user_') else workspace_id}:")
                for table in APP_TABLES_DELETE_ORDER:
                    try:
                        count = count_rows(cur, workspace_id, table)
                    except Exception:
                        count = 0
                    if count:
                        print(f"    - {table}: {count}")
            if not args.confirm:
                print("Dry run only: no DB rows changed")
                delete_prefixes(args.bucket, prefixes, confirm=False)
                return 0

            try:
                delete_prefixes(args.bucket, prefixes, confirm=True)
            except Exception as exc:  # noqa: BLE001
                print(f"Object-prefix deletion failed before DB reset: {type(exc).__name__}: {exc}", file=sys.stderr)
                return 2

            with conn.transaction():
                for workspace_id in reset_workspaces:
                    delete_workspace_rows(cur, workspace_id)
                upsert_fraunhofer(cur, owner_user_id=args.user_a_id, bucket=args.bucket, prefix=args.prefix)
                cleanup_memberships(cur, owner_user_id=args.user_a_id, user_b_id=args.user_b_id, workspace_ids=reset_workspaces)
                delete_old_workspace_rows(cur, old_workspaces)
            print("Database reset/upsert transaction completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
