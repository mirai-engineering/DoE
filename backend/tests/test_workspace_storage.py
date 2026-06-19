from pathlib import Path

import pytest

from app.services.workspace_storage import (
    DEFAULT_LOCAL_OBJECT_STORAGE_ROOT,
    WorkspaceStorageConfig,
    WorkspaceStorageError,
    assert_same_workspace_path,
    local_object_storage_path,
    local_object_storage_root,
    object_storage_backend,
    object_storage_uri,
    put_workspace_object,
    read_object_storage_bytes,
    validate_object_key,
    validate_workspace_object_uri,
    workspace_scoped_path,
)


def test_object_storage_backend_and_local_root_are_explicit(monkeypatch, tmp_path):
    monkeypatch.delenv("OBJECT_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("LOCAL_OBJECT_STORAGE_ROOT", raising=False)
    monkeypatch.delenv("DOE_OBJECT_STORE_ROOT", raising=False)

    assert object_storage_backend() == "local"
    assert local_object_storage_root() == DEFAULT_LOCAL_OBJECT_STORAGE_ROOT

    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(tmp_path / "mirror"))
    assert object_storage_backend() == "s3"
    assert local_object_storage_root() == tmp_path / "mirror"

    monkeypatch.delenv("LOCAL_OBJECT_STORAGE_ROOT")
    monkeypatch.setenv("DOE_OBJECT_STORE_ROOT", str(tmp_path / "legacy"))
    assert local_object_storage_root() == tmp_path / "legacy"

    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "ftp")
    with pytest.raises(WorkspaceStorageError):
        object_storage_backend()


def test_bucket_aware_local_object_storage_path_and_uri(monkeypatch, tmp_path):
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(tmp_path / "mirror"))
    key = "workspaces/fraunhofer/projects/fuel-cell/intake/model_table.csv"

    path = local_object_storage_path("mirai-fuel-cells-demo", key)

    assert path == (tmp_path / "mirror" / "mirai-fuel-cells-demo" / "workspaces" / "fraunhofer" / "projects" / "fuel-cell" / "intake" / "model_table.csv").resolve()
    assert object_storage_uri("mirai-fuel-cells-demo", key) == str(path)

    path.parent.mkdir(parents=True)
    path.write_text("x1,y1\n1,2\n", encoding="utf-8")
    assert read_object_storage_bytes("mirai-fuel-cells-demo", key) == b"x1,y1\n1,2\n"


def test_object_storage_uri_uses_s3_for_s3_backend(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "s3")

    assert object_storage_uri("mirai-fuel-cells-demo", "workspaces/fraunhofer/model_table.csv") == "s3://mirai-fuel-cells-demo/workspaces/fraunhofer/model_table.csv"


def test_bucket_level_object_key_rejects_unsafe_values():
    for key in ["", "/absolute/path.csv", "../escape.csv", "workspaces/fraunhofer/../escape.csv"]:
        with pytest.raises(WorkspaceStorageError):
            validate_object_key(key)
    with pytest.raises(WorkspaceStorageError):
        local_object_storage_path("../bad-bucket", "workspaces/fraunhofer/model_table.csv")


def test_workspace_scoped_path_requires_safe_workspace_and_relative_parts(tmp_path):
    path = workspace_scoped_path(tmp_path, "client-a", "uploads", "file.csv")

    assert path == (tmp_path / "workspaces" / "client-a" / "uploads" / "file.csv").resolve()

    with pytest.raises(WorkspaceStorageError):
        workspace_scoped_path(tmp_path, "../client-a", "uploads")
    with pytest.raises(WorkspaceStorageError):
        workspace_scoped_path(tmp_path, "client-a", "..", "client-b", "file.csv")
    with pytest.raises(WorkspaceStorageError):
        workspace_scoped_path(tmp_path, "client-a", Path("/tmp/escape.csv"))


def test_assert_same_workspace_path_rejects_unscoped_and_cross_workspace_paths(tmp_path):
    scoped = tmp_path / "workspaces" / "client-a" / "uploads" / "file.csv"
    unscoped = tmp_path / "uploads" / "file.csv"
    cross_workspace = tmp_path / "workspaces" / "client-b" / "uploads" / "file.csv"

    assert assert_same_workspace_path(tmp_path, "client-a", scoped) == scoped.resolve()
    with pytest.raises(WorkspaceStorageError):
        assert_same_workspace_path(tmp_path, "client-a", unscoped)
    with pytest.raises(WorkspaceStorageError):
        assert_same_workspace_path(tmp_path, "client-a", cross_workspace)


def test_workspace_object_uri_accepts_workspace_scoped_s3_paths():
    fuel = WorkspaceStorageConfig(
        workspace_id="fraunhofer",
        mode="s3",
        bucket="mirai-fuel-cells-demo",
        prefix="workspaces/fraunhofer",
    )
    battery = WorkspaceStorageConfig(
        workspace_id="battery-demo",
        mode="s3",
        bucket="mirai-batteries-demo",
        prefix="workspaces/battery-demo",
    )

    assert (
        validate_workspace_object_uri(
            fuel,
            "s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/onnx/model.onnx",
        )
        == "workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/onnx/model.onnx"
    )
    assert (
        validate_workspace_object_uri(
            battery,
            "workspaces/battery-demo/projects/battery_tabular_doe_demo/mlflow-artifacts/run-1/model.onnx",
        )
        == "workspaces/battery-demo/projects/battery_tabular_doe_demo/mlflow-artifacts/run-1/model.onnx"
    )


def test_workspace_object_uri_rejects_cross_workspace_and_wrong_bucket():
    fuel = WorkspaceStorageConfig(
        workspace_id="fraunhofer",
        mode="s3",
        bucket="mirai-fuel-cells-demo",
        prefix="workspaces/fraunhofer",
    )
    battery = WorkspaceStorageConfig(
        workspace_id="battery-demo",
        mode="s3",
        bucket="mirai-batteries-demo",
        prefix="workspaces/battery-demo",
    )

    with pytest.raises(WorkspaceStorageError):
        validate_workspace_object_uri(
            fuel,
            "s3://mirai-batteries-demo/workspaces/battery-demo/projects/battery_tabular_doe_demo/onnx/model.onnx",
        )
    with pytest.raises(WorkspaceStorageError):
        validate_workspace_object_uri(
            fuel,
            "workspaces/battery-demo/projects/battery_tabular_doe_demo/onnx/model.onnx",
        )
    with pytest.raises(WorkspaceStorageError):
        validate_workspace_object_uri(
            battery,
            "workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/onnx/model.onnx",
        )


def test_workspace_object_uri_rejects_escapes_and_filesystem_paths():
    config = WorkspaceStorageConfig(
        workspace_id="fraunhofer",
        mode="s3",
        bucket="mirai-fuel-cells-demo",
        prefix="workspaces/fraunhofer",
    )

    for uri in [
        "/app/backend/mlruns/model.onnx",
        "../workspaces/fraunhofer/projects/model.onnx",
        "workspaces/fraunhofer/../battery-demo/model.onnx",
        "file:///app/backend/mlruns/model.onnx",
    ]:
        with pytest.raises(WorkspaceStorageError):
            validate_workspace_object_uri(config, uri)


def test_put_workspace_object_writes_local_mirror_and_rejects_prefix_escape(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(tmp_path / "mirror"))
    config = WorkspaceStorageConfig(
        workspace_id="user_123",
        mode="local",
        bucket="mirai-user-123-demo",
        prefix="workspaces/user_123/projects/project_a",
    )

    key = put_workspace_object(config, "workspaces/user_123/projects/project_a/intake/raw.zip", b"zip-bytes", content_type="application/zip")

    assert key == "workspaces/user_123/projects/project_a/intake/raw.zip"
    assert read_object_storage_bytes("mirai-user-123-demo", key) == b"zip-bytes"
    with pytest.raises(WorkspaceStorageError):
        put_workspace_object(config, "workspaces/user_456/projects/project_a/intake/raw.zip", b"bad")


def test_local_config_rejects_s3_uri_but_accepts_workspace_key():
    config = WorkspaceStorageConfig(workspace_id="fraunhofer", mode="local")

    assert (
        validate_workspace_object_uri(
            config,
            "workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/reviews/latest.json",
        )
        == "workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/reviews/latest.json"
    )
    with pytest.raises(WorkspaceStorageError):
        validate_workspace_object_uri(
            config,
            "s3://mirai-fuel-cells-demo/workspaces/fraunhofer/projects/pem_fuel_cell_real_cathode_degradation/reviews/latest.json",
        )
