from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from .db import execute, fetch_all, fetch_one, jsonb, postgres_control_plane_enabled, postgres_control_plane_required
from .workspace_storage import WorkspaceStorageConfig


logger = logging.getLogger(__name__)


def _should_raise() -> bool:
    return postgres_control_plane_required()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_workspace_projects(workspace_id: str) -> list[dict[str, Any]] | None:
    if not postgres_control_plane_enabled():
        return None
    try:
        rows = fetch_all(
            workspace_id,
            """
            SELECT p.project_id,
                   p.workspace_id,
                   p.display_name,
                   w.display_name AS workspace_name,
                   p.lifecycle_contract,
                   p.schema_version,
                   p.metadata,
                   p.storage
            FROM projects p
            JOIN workspaces w ON w.workspace_id = p.workspace_id
            WHERE p.workspace_id = %s
              AND COALESCE(p.metadata->>'runtime_visible', 'true') <> 'false'
            ORDER BY p.display_name
            """,
            (workspace_id,),
        )
    except Exception as exc:  # noqa: BLE001 - optional local fallback remains available.
        logger.warning("Postgres project list failed for workspace_id=%s: %s", workspace_id, exc)
        if _should_raise():
            raise
        return None
    return [
        {
            "id": row["project_id"],
            "display_name": row["display_name"],
            "workspace_id": row["workspace_id"],
            "workspace_name": row.get("workspace_name") or row["workspace_id"],
            "lifecycle_contract": row.get("lifecycle_contract"),
            "schema_version": row.get("schema_version"),
            "metadata": row.get("metadata") or {},
            "storage": row.get("storage") or {},
        }
        for row in rows
    ]


def get_workspace_project(workspace_id: str, project_id: str) -> dict[str, Any] | None:
    projects = list_workspace_projects(workspace_id)
    if projects is None:
        return None
    return next((project for project in projects if project["id"] == project_id), None)


def _storage_config_from_project(project: dict[str, Any]) -> WorkspaceStorageConfig:
    workspace_id = str(project["workspace_id"])
    project_id = str(project["project_id"])
    metadata = project.get("metadata") if isinstance(project.get("metadata"), dict) else {}
    storage = project.get("storage") if isinstance(project.get("storage"), dict) else {}
    mode = str(storage.get("mode") or metadata.get("storage_mode") or ("s3" if storage.get("bucket") or metadata.get("bucket") else "local"))
    bucket = storage.get("bucket") or metadata.get("bucket")
    prefix = storage.get("prefix") or metadata.get("prefix") or f"workspaces/{workspace_id}/projects/{project_id}"
    return WorkspaceStorageConfig(workspace_id=workspace_id, mode=mode, bucket=bucket, prefix=prefix)


def get_project_storage_config(workspace_id: str, project_id: str) -> WorkspaceStorageConfig | None:
    if not postgres_control_plane_enabled():
        return None
    try:
        project = fetch_one(
            workspace_id,
            """
            SELECT project_id, workspace_id, metadata, storage
            FROM projects
            WHERE workspace_id = %s AND project_id = %s
            """,
            (workspace_id, project_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres project storage lookup failed for workspace_id=%s project_id=%s: %s", workspace_id, project_id, exc)
        if _should_raise():
            raise
        return None
    if not project:
        return None
    return _storage_config_from_project(project)


def get_project_runtime_state(workspace_id: str, project_id: str) -> dict[str, Any] | None:
    if not postgres_control_plane_enabled():
        return None
    try:
        project = fetch_one(
            workspace_id,
            """
            SELECT p.project_id, p.workspace_id, p.display_name, p.lifecycle_contract, p.schema_version, p.metadata,
                   p.storage, w.display_name AS workspace_name, w.storage AS workspace_storage
            FROM projects p
            JOIN workspaces w ON w.workspace_id = p.workspace_id
            WHERE p.workspace_id = %s AND p.project_id = %s
            """,
            (workspace_id, project_id),
        )
        if not project:
            return None
        dataset = fetch_one(
            workspace_id,
            """
            SELECT * FROM datasets
            WHERE workspace_id = %s AND project_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_id, project_id),
        )
        schema = fetch_one(
            workspace_id,
            """
            SELECT * FROM schema_manifests
            WHERE workspace_id = %s AND project_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_id, project_id),
        )
        training_run = fetch_one(
            workspace_id,
            """
            SELECT * FROM training_runs
            WHERE workspace_id = %s AND project_id = %s
            ORDER BY COALESCE(finished_at, started_at, created_at) DESC
            LIMIT 1
            """,
            (workspace_id, project_id),
        )
        champion = fetch_one(
            workspace_id,
            """
            SELECT * FROM models
            WHERE workspace_id = %s AND project_id = %s AND is_champion
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_id, project_id),
        )
        artifacts = fetch_all(
            workspace_id,
            """
            SELECT artifact_kind, object_uri, metadata, created_at
            FROM artifact_objects
            WHERE workspace_id = %s AND project_id = %s
            ORDER BY artifact_kind, created_at DESC
            """,
            (workspace_id, project_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres runtime state failed for workspace_id=%s project_id=%s: %s", workspace_id, project_id, exc)
        if _should_raise():
            raise
        return None
    return {
        "project": project,
        "dataset": dataset,
        "schema_manifest": schema,
        "training_run": training_run,
        "champion_model": champion,
        "artifacts": artifacts,
    }


def create_training_run(
    *,
    workspace_id: str,
    project_id: str,
    training_run_id: str,
    dataset_id: str | None,
    artifact_s3_prefix: str | None,
    created_by: str | None,
) -> None:
    if not postgres_control_plane_enabled():
        return
    execute(
        workspace_id,
        """
        INSERT INTO training_runs (
            training_run_id, workspace_id, project_id, dataset_id, status, started_at,
            artifact_s3_prefix, created_by
        )
        VALUES (%s, %s, %s, %s, 'running', now(), %s, %s)
        ON CONFLICT (training_run_id) DO UPDATE
        SET status = 'running', started_at = now(), artifact_s3_prefix = EXCLUDED.artifact_s3_prefix,
            created_by = EXCLUDED.created_by, updated_at = now()
        """,
        (training_run_id, workspace_id, project_id, dataset_id, artifact_s3_prefix, created_by),
    )


def complete_training_run(
    *,
    workspace_id: str,
    project_id: str,
    training_run_id: str,
    mlflow_run_id: str | None,
    best_model_type: str | None,
    metrics: dict[str, Any] | None,
    model_artifact_uri: str | None,
    preprocessing_uri: str | None,
    schema_uri: str | None,
) -> None:
    if not postgres_control_plane_enabled():
        return
    execute(
        workspace_id,
        """
        UPDATE training_runs
        SET status = 'completed', finished_at = now(), mlflow_run_id = %s,
            best_model_type = %s, metrics_json = %s, updated_at = now()
        WHERE workspace_id = %s AND project_id = %s AND training_run_id = %s
        """,
        (mlflow_run_id, best_model_type, jsonb(metrics or {}), workspace_id, project_id, training_run_id),
    )
    if model_artifact_uri:
        model_id = f"mdl_{training_run_id}"
        execute(
            workspace_id,
            """
            UPDATE models
            SET is_champion = false,
                status = CASE WHEN status = 'champion' THEN 'archived' ELSE status END,
                updated_at = now()
            WHERE workspace_id = %s AND project_id = %s AND is_champion
            """,
            (workspace_id, project_id),
        )
        execute(
            workspace_id,
            """
            INSERT INTO models (
                model_id, workspace_id, project_id, training_run_id, model_name, version, status,
                artifact_s3_uri, preprocessing_s3_uri, schema_s3_uri, is_champion, metrics_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'champion', %s, %s, %s, true, %s)
            ON CONFLICT (model_id) DO UPDATE
            SET status = 'champion', artifact_s3_uri = EXCLUDED.artifact_s3_uri,
                preprocessing_s3_uri = EXCLUDED.preprocessing_s3_uri,
                schema_s3_uri = EXCLUDED.schema_s3_uri,
                is_champion = true,
                metrics_json = EXCLUDED.metrics_json,
                updated_at = now()
            """,
            (
                model_id,
                workspace_id,
                project_id,
                training_run_id,
                f"doe_surrogate_{project_id}",
                training_run_id,
                model_artifact_uri,
                preprocessing_uri,
                schema_uri,
                jsonb(metrics or {}),
            ),
        )


def fail_training_run(*, workspace_id: str, project_id: str, training_run_id: str, error_message: str) -> None:
    if not postgres_control_plane_enabled():
        return
    execute(
        workspace_id,
        """
        UPDATE training_runs
        SET status = 'failed', finished_at = now(), error_message = %s, updated_at = now()
        WHERE workspace_id = %s AND project_id = %s AND training_run_id = %s
        """,
        (error_message, workspace_id, project_id, training_run_id),
    )


def log_audit(
    *,
    workspace_id: str | None,
    user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not workspace_id or not postgres_control_plane_enabled():
        return
    try:
        execute(
            workspace_id,
            """
            INSERT INTO audit_logs (workspace_id, user_id, action, resource_type, resource_id, ip_address, metadata, timestamp)
            VALUES (%s, %s, %s, %s, %s, NULLIF(%s, '')::inet, %s, now())
            """,
            (workspace_id, user_id, action, resource_type, resource_id, ip_address or "", jsonb(metadata or {})),
        )
    except Exception as exc:  # noqa: BLE001 - audit must not break user flows.
        logger.warning("Audit log write failed for action=%s workspace_id=%s: %s", action, workspace_id, exc)
