from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Any, Iterator

from psycopg import Connection, connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def database_url() -> str | None:
    url = os.getenv("DATABASE_URL") or os.getenv("MIRAI_DATABASE_URL")
    if not url:
        return None
    # Railway/Postgres URLs are sometimes postgres://; psycopg expects postgresql://.
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    return url


def postgres_control_plane_enabled() -> bool:
    if os.getenv("MIRAI_DISABLE_POSTGRES_CONTROL_PLANE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return bool(database_url())


def postgres_control_plane_required() -> bool:
    return os.getenv("MIRAI_REQUIRE_POSTGRES_CONTROL_PLANE", "").strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def workspace_connection(workspace_id: str) -> Iterator[Connection]:
    if not workspace_id:
        raise ValueError("workspace_id is required for RLS-protected database access")
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    with connect(url, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.workspace_id', %s, true)", (workspace_id,))
            yield conn


def fetch_all(workspace_id: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with workspace_connection(workspace_id) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def fetch_one(workspace_id: str, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = fetch_all(workspace_id, sql, params)
    return rows[0] if rows else None


def execute(workspace_id: str, sql: str, params: tuple[Any, ...] = ()) -> None:
    with workspace_connection(workspace_id) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def jsonb(value: Any) -> Jsonb:
    return Jsonb(value if value is not None else {})
