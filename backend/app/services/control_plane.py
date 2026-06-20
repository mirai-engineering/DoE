from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from typing import Any

from .db import execute, fetch_all, fetch_one, jsonb, postgres_control_plane_enabled, postgres_control_plane_required
from .workspace_storage import WorkspaceStorageConfig, validate_workspace_id


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkspaceMembershipState:
    status: str
    clerk_user_id: str
    workspace_id: str | None = None
    role: str | None = None
    memberships: tuple[dict[str, Any], ...] = ()

    @property
    def can_access_workspace(self) -> bool:
        return self.status == "active_single_workspace" and bool(self.workspace_id)


def _candidate_membership_workspaces() -> list[str]:
    configured = os.getenv("MIRAI_TENANT_WORKSPACE_IDS") or os.getenv("MIRAI_ALLOWED_WORKSPACE_IDS")
    if configured:
        values = [item.strip() for item in configured.split(",") if item.strip()]
    else:
        values = ["fraunhofer", "test-client-isolated"]
    # Preserve order while deduplicating.
    return list(dict.fromkeys(values))


def resolve_workspace_membership(clerk_user_id: str) -> WorkspaceMembershipState:
    """Resolve Clerk user -> workspace membership from Postgres.

    RLS-protected demo tables require querying through known workspace scopes.
    The hard-reset demo intentionally provisions only `fraunhofer` plus the
    test-only `test-client-isolated` fixture, configurable by env for tests.
    """

    if not clerk_user_id:
        return WorkspaceMembershipState(status="no_workspace_membership", clerk_user_id="")
    if not postgres_control_plane_enabled():
        return WorkspaceMembershipState(status="no_workspace_membership", clerk_user_id=clerk_user_id)
    memberships: list[dict[str, Any]] = []
    for workspace_id in _candidate_membership_workspaces():
        try:
            rows = fetch_all(
                workspace_id,
                """
                SELECT cuw.clerk_user_id, cuw.workspace_id, cuw.role, w.display_name, w.status, w.storage
                FROM clerk_user_workspaces cuw
                JOIN workspaces w ON w.workspace_id = cuw.workspace_id
                WHERE cuw.clerk_user_id = %s AND cuw.workspace_id = %s
                """,
                (clerk_user_id, workspace_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Membership lookup failed for workspace_id=%s: %s", workspace_id, exc)
            if _should_raise():
                raise
            continue
        memberships.extend(rows)
    if not memberships:
        return WorkspaceMembershipState(status="no_workspace_membership", clerk_user_id=clerk_user_id)
    if len(memberships) > 1:
        return WorkspaceMembershipState(status="workspace_selection_required", clerk_user_id=clerk_user_id, memberships=tuple(memberships))
    membership = memberships[0]
    return WorkspaceMembershipState(
        status="active_single_workspace",
        clerk_user_id=clerk_user_id,
        workspace_id=str(membership["workspace_id"]),
        role=str(membership.get("role") or "member"),
        memberships=(membership,),
    )


def account_capabilities(status: str) -> dict[str, Any]:
    if status == "active_single_workspace":
        return {
            "status": status,
            "message": "Your account is active and assigned to a client workspace.",
            "can_create_project": True,
            "can_upload": True,
            "can_train": True,
            "can_predict": True,
        }
    if status == "workspace_selection_required":
        return {
            "status": status,
            "message": "Multiple client workspaces are assigned. Workspace selection is required before continuing.",
            "can_create_project": False,
            "can_upload": False,
            "can_train": False,
            "can_predict": False,
        }
    return {
        "status": "no_workspace_membership",
        "message": "Your account is active, but no client workspace has been assigned yet.",
        "can_create_project": False,
        "can_upload": False,
        "can_train": False,
        "can_predict": False,
    }


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


def get_workspace_summary(workspace_id: str) -> dict[str, Any] | None:
    if not postgres_control_plane_enabled():
        return None
    try:
        row = fetch_one(
            workspace_id,
            """
            SELECT workspace_id, display_name, status, storage
            FROM workspaces
            WHERE workspace_id = %s
            """,
            (workspace_id,),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres workspace lookup failed for workspace_id=%s: %s", workspace_id, exc)
        if _should_raise():
            raise
        return None
    if not row:
        return None
    storage = row.get("storage") if isinstance(row.get("storage"), dict) else {}
    return {
        "workspace_id": row["workspace_id"],
        "display_name": row.get("display_name") or row["workspace_id"],
        "status": row.get("status") or "active",
        "storage": storage,
        "storage_provisioned": bool(storage.get("bucket")),
        "lifecycle_contract": "generic_tabular_doe",
        "default_template_ids": ["generic_tabular_doe"],
        "allowed_extractors": [],
    }


def synthetic_workspace_summary(workspace_id: str) -> dict[str, Any]:
    return {
        "workspace_id": validate_workspace_id(workspace_id),
        "display_name": "Your workspace",
        "status": "storage_not_provisioned",
        "storage": {},
        "storage_provisioned": False,
        "lifecycle_contract": "generic_tabular_doe",
        "default_template_ids": ["generic_tabular_doe"],
        "allowed_extractors": [],
    }


def ensure_workspace_record(*, workspace_id: str, display_name: str | None = None, clerk_user_id: str | None = None, storage: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not postgres_control_plane_enabled():
        return None
    workspace = validate_workspace_id(workspace_id)
    workspace_storage = storage or {}
    execute(
        workspace,
        """
        INSERT INTO workspaces (workspace_id, display_name, status, storage, created_at, updated_at)
        VALUES (%s, %s, 'active', %s, now(), now())
        ON CONFLICT (workspace_id) DO UPDATE
        SET display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), workspaces.display_name),
            storage = CASE WHEN EXCLUDED.storage = '{}'::jsonb THEN workspaces.storage ELSE EXCLUDED.storage END,
            updated_at = now()
        """,
        (workspace, display_name or workspace, jsonb(workspace_storage)),
    )
    if clerk_user_id:
        execute(
            workspace,
            """
            INSERT INTO clerk_user_workspaces (clerk_user_id, workspace_id, role, created_at)
            VALUES (%s, %s, 'owner', now())
            ON CONFLICT (clerk_user_id, workspace_id) DO UPDATE SET role = EXCLUDED.role
            """,
            (clerk_user_id, workspace),
        )
    return get_workspace_summary(workspace)


def assign_workspace_storage(*, workspace_id: str, bucket: str, mode: str = "s3", prefix: str | None = None, display_name: str | None = None, clerk_user_id: str | None = None) -> dict[str, Any] | None:
    config = WorkspaceStorageConfig(workspace_id=workspace_id, mode=mode, bucket=bucket, prefix=prefix or f"workspaces/{workspace_id}")
    storage = {"mode": config.mode, "bucket": config.bucket, "prefix": config.normalized_prefix}
    return ensure_workspace_record(workspace_id=workspace_id, display_name=display_name, clerk_user_id=clerk_user_id, storage=storage)


def get_workspace_storage_config(workspace_id: str) -> WorkspaceStorageConfig | None:
    summary = get_workspace_summary(workspace_id)
    if not summary:
        return None
    storage = summary.get("storage") if isinstance(summary.get("storage"), dict) else {}
    bucket = storage.get("bucket")
    if not bucket:
        return None
    mode = str(storage.get("mode") or "s3")
    prefix = storage.get("prefix") or f"workspaces/{workspace_id}"
    return WorkspaceStorageConfig(workspace_id=workspace_id, mode=mode, bucket=bucket, prefix=prefix)


def _storage_config_from_project(project: dict[str, Any]) -> WorkspaceStorageConfig:
    workspace_id = str(project["workspace_id"])
    project_id = str(project["project_id"])
    metadata = project.get("metadata") if isinstance(project.get("metadata"), dict) else {}
    storage = project.get("storage") if isinstance(project.get("storage"), dict) else {}
    mode = str(storage.get("mode") or metadata.get("storage_mode") or ("s3" if storage.get("bucket") or metadata.get("bucket") else "local"))
    bucket = storage.get("bucket") or metadata.get("bucket")
    prefix = storage.get("prefix") or metadata.get("prefix") or f"workspaces/{workspace_id}/projects/{project_id}"
    return WorkspaceStorageConfig(workspace_id=workspace_id, mode=mode, bucket=bucket, prefix=prefix)


def ensure_project_record(*, workspace_id: str, project_id: str, display_name: str, workspace_name: str | None = None, clerk_user_id: str | None = None) -> WorkspaceStorageConfig | None:
    if not postgres_control_plane_enabled():
        return None
    workspace_summary = get_workspace_summary(workspace_id)
    if not workspace_summary:
        raise ValueError("Workspace membership required")
    workspace_config = get_workspace_storage_config(workspace_id)
    if not workspace_config:
        raise ValueError("Workspace storage is not provisioned yet. Ask a Mirai admin to assign a private storage bucket before uploading data.")
    project_config = WorkspaceStorageConfig(
        workspace_id=workspace_id,
        mode=workspace_config.mode,
        bucket=workspace_config.bucket,
        prefix=f"{workspace_config.normalized_prefix}/projects/{project_id}",
    )
    execute(
        workspace_id,
        """
        INSERT INTO projects (project_id, workspace_id, display_name, lifecycle_contract, metadata, storage, created_at, updated_at)
        VALUES (%s, %s, %s, 'generic_tabular_doe', %s, %s, now(), now())
        ON CONFLICT (project_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            lifecycle_contract = EXCLUDED.lifecycle_contract,
            metadata = projects.metadata || EXCLUDED.metadata,
            storage = EXCLUDED.storage,
            updated_at = now()
        WHERE projects.workspace_id = EXCLUDED.workspace_id
        """,
        (
            project_id,
            workspace_id,
            display_name or project_id,
            jsonb({"runtime_visible": True, "template_id": "generic_tabular_doe"}),
            jsonb({"mode": project_config.mode, "bucket": project_config.bucket, "prefix": project_config.normalized_prefix}),
        ),
    )
    if not get_workspace_project(workspace_id, project_id):
        raise ValueError("Project id already belongs to another workspace")
    return project_config


def record_uploaded_dataset(*, workspace_id: str, project_id: str, dataset_id: str, filename: str, object_uri: str, sha256: str | None, size_bytes: int | None, uploaded_by: str | None, metadata: dict[str, Any] | None = None) -> None:
    if not postgres_control_plane_enabled():
        return
    execute(
        workspace_id,
        """
        INSERT INTO datasets (dataset_id, workspace_id, project_id, filename, object_uri, sha256, size_bytes, uploaded_by, status, metadata, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'uploaded', %s, now(), now())
        ON CONFLICT (dataset_id) DO UPDATE
        SET filename = EXCLUDED.filename,
            object_uri = EXCLUDED.object_uri,
            sha256 = EXCLUDED.sha256,
            size_bytes = EXCLUDED.size_bytes,
            uploaded_by = EXCLUDED.uploaded_by,
            status = EXCLUDED.status,
            metadata = EXCLUDED.metadata,
            updated_at = now()
        """,
        (dataset_id, workspace_id, project_id, filename, object_uri, sha256, size_bytes, uploaded_by, jsonb(metadata or {})),
    )


def record_artifact_object(*, workspace_id: str, project_id: str, artifact_kind: str, object_uri: str, sha256: str | None, size_bytes: int | None, metadata: dict[str, Any] | None = None) -> None:
    if not postgres_control_plane_enabled():
        return
    execute(
        workspace_id,
        """
        INSERT INTO artifact_objects (workspace_id, project_id, artifact_kind, object_uri, sha256, size_bytes, metadata, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (workspace_id, project_id, artifact_kind, object_uri) DO UPDATE
        SET sha256 = EXCLUDED.sha256,
            size_bytes = EXCLUDED.size_bytes,
            metadata = EXCLUDED.metadata
        """,
        (workspace_id, project_id, artifact_kind, object_uri, sha256, size_bytes, jsonb(metadata or {})),
    )


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
        candidate = fetch_one(
            workspace_id,
            """
            SELECT * FROM models
            WHERE workspace_id = %s AND project_id = %s AND status = 'candidate' AND NOT is_champion
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
        "candidate_model": candidate,
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
    model_artifact_uri: str | None = None,
    preprocessing_uri: str | None = None,
    schema_uri: str | None = None,
) -> None:
    """Mark training execution complete without implicitly approving a champion.

    Candidate and champion model records are written by explicit helpers below so
    local/Railway challenger completion cannot accidentally become active serving
    state.
    """
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


def record_candidate_model(
    *,
    workspace_id: str,
    project_id: str,
    training_run_id: str,
    model_name: str,
    version: str,
    artifact_uri: str,
    preprocessing_uri: str | None,
    schema_uri: str | None,
    metrics: dict[str, Any] | None,
) -> None:
    """Record a reviewable candidate without making it active for serving."""
    if not postgres_control_plane_enabled():
        return
    model_id = f"mdl_{training_run_id}_candidate"
    execute(
        workspace_id,
        """
        INSERT INTO models (
            model_id, workspace_id, project_id, training_run_id, model_name, version, status,
            artifact_s3_uri, preprocessing_s3_uri, schema_s3_uri, is_champion, metrics_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'candidate', %s, %s, %s, false, %s)
        ON CONFLICT (model_id) DO UPDATE
        SET status = 'candidate', artifact_s3_uri = EXCLUDED.artifact_s3_uri,
            preprocessing_s3_uri = EXCLUDED.preprocessing_s3_uri,
            schema_s3_uri = EXCLUDED.schema_s3_uri,
            is_champion = false,
            metrics_json = EXCLUDED.metrics_json,
            updated_at = now()
        """,
        (model_id, workspace_id, project_id, training_run_id, model_name, version, artifact_uri, preprocessing_uri, schema_uri, jsonb(metrics or {})),
    )


def get_training_run_by_mlflow_run_id(workspace_id: str, project_id: str, mlflow_run_id: str) -> dict[str, Any] | None:
    if not postgres_control_plane_enabled():
        return None
    return fetch_one(
        workspace_id,
        """
        SELECT * FROM training_runs
        WHERE workspace_id = %s AND project_id = %s AND mlflow_run_id = %s AND status = 'completed'
        ORDER BY COALESCE(finished_at, started_at, created_at) DESC
        LIMIT 1
        """,
        (workspace_id, project_id, mlflow_run_id),
    )


def activate_champion_model(
    *,
    workspace_id: str,
    project_id: str,
    training_run_id: str,
    model_name: str,
    version: str,
    artifact_uri: str,
    preprocessing_uri: str | None,
    schema_uri: str | None,
    metrics: dict[str, Any] | None,
) -> None:
    """Explicitly activate a reconciled champion after MLflow alias verification."""
    if not postgres_control_plane_enabled():
        return
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
    model_id = f"mdl_{training_run_id}_champion"
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
        (model_id, workspace_id, project_id, training_run_id, model_name, version, artifact_uri, preprocessing_uri, schema_uri, jsonb(metrics or {})),
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
