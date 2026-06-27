import json

from app.services.lifecycle_artifacts import persist_session_artifact_set, public_artifact_persistence_summary
from app.services.workspace_storage import WorkspaceStorageConfig, read_object_storage_bytes


def test_persist_session_artifact_set_uploads_session_scoped_objects(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(tmp_path / "mirror"))
    source = tmp_path / "canonical"
    source.mkdir()
    (source / "model_table.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    config = WorkspaceStorageConfig(
        workspace_id="user_123",
        mode="local",
        bucket="mirai-user-123-demo",
        prefix="workspaces/user_123/projects/project_a",
    )

    manifest = persist_session_artifact_set(
        project_id="project_a",
        dataset_id="dataset_a",
        session_id="ing_a",
        workspace_id="user_123",
        artifact_set="canonical",
        local_dir_or_files=source,
        storage_config=config,
    )

    assert manifest["status"] == "uploaded"
    assert manifest["objects"][0]["object_key"] == "workspaces/user_123/projects/project_a/canonical/dataset_a/ing_a/model_table.csv"
    assert read_object_storage_bytes("mirai-user-123-demo", manifest["objects"][0]["object_key"]) == b"x,y\n1,2\n"
    latest_key = "workspaces/user_123/projects/project_a/latest/artifact_manifest.json"
    latest = json.loads(read_object_storage_bytes("mirai-user-123-demo", latest_key).decode("utf-8"))
    assert latest["dataset_id"] == "dataset_a"
    assert latest["session_id"] == "ing_a"


def test_artifact_persistence_summary_removes_raw_object_pointers(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(tmp_path / "mirror"))
    source = tmp_path / "eda"
    source.mkdir()
    (source / "preprocessing_report.json").write_text('{"ok": true}', encoding="utf-8")
    config = WorkspaceStorageConfig(
        workspace_id="user_123",
        mode="local",
        bucket="mirai-user-123-demo",
        prefix="workspaces/user_123/projects/project_a",
    )

    manifest = persist_session_artifact_set(
        project_id="project_a",
        dataset_id="dataset_a",
        session_id="ing_a",
        workspace_id="user_123",
        artifact_set="eda",
        local_dir_or_files=source,
        storage_config=config,
    )
    public = public_artifact_persistence_summary(manifest)
    serialized = json.dumps(public)

    assert "object_key" not in serialized
    assert "object_uri" not in serialized
    assert "s3://" not in serialized
    assert "workspaces/user_123" not in serialized
    assert public["objects"][0]["name"] == "preprocessing_report.json"


def test_artifact_directory_upload_enforces_allowlist_and_skips_raw_references(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(tmp_path / "mirror"))
    source = tmp_path / "preprocessing"
    (source / "raw_reference_extracted").mkdir(parents=True)
    (source / "schema.json").write_text("{}", encoding="utf-8")
    (source / "raw_reference_extracted" / "secret.csv").write_text("secret", encoding="utf-8")
    (source / "unexpected.txt").write_text("do not upload", encoding="utf-8")
    config = WorkspaceStorageConfig(
        workspace_id="user_123",
        mode="local",
        bucket="mirai-user-123-demo",
        prefix="workspaces/user_123/projects/project_a",
    )

    manifest = persist_session_artifact_set(
        project_id="project_a",
        dataset_id="dataset_a",
        session_id="ing_a",
        workspace_id="user_123",
        artifact_set="preprocessing_artifacts",
        local_dir_or_files=source,
        storage_config=config,
    )

    assert [item["name"] for item in manifest["objects"]] == ["schema.json"]
    assert read_object_storage_bytes("mirai-user-123-demo", manifest["objects"][0]["object_key"]) == b"{}"


def test_list_ingestion_sessions_restores_latest_persisted_session(monkeypatch, tmp_path):
    from app.services import data_intake

    object_root = tmp_path / "object-root"
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(object_root))
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "mirai-user-123-local")
    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", object_root / "intake")

    project_id = "project_a"
    dataset_id = "dataset_a"
    session_id = "ing_a"
    workspace_id = "user_123"
    session = {
        "project_id": project_id,
        "project_name": "Project A",
        "workspace_id": workspace_id,
        "workspace_name": "User",
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "status": "ready_for_contract_review",
        "approval_status": "not_ready",
        "created_at": "now",
        "updated_at": "now",
        "storage": {"provider": "local"},
        "files": [],
    }
    source = tmp_path / "source"
    (source / "inventory").mkdir(parents=True)
    (source / "session.json").write_text(json.dumps(session), encoding="utf-8")
    (source / "inventory" / "file_inventory.json").write_text(json.dumps({"files": [], "generated_at": "now"}), encoding="utf-8")
    config = WorkspaceStorageConfig(
        workspace_id=workspace_id,
        mode="local",
        bucket="mirai-user-123-local",
        prefix=f"workspaces/{workspace_id}/projects/{project_id}",
    )
    persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=workspace_id,
        artifact_set="session_metadata",
        local_dir_or_files={
            "session.json": source / "session.json",
            "inventory/file_inventory.json": source / "inventory" / "file_inventory.json",
        },
        storage_config=config,
    )

    restored = data_intake.list_ingestion_sessions(project_id=project_id, workspace_id=workspace_id)

    assert [item["ingestion_session_id"] for item in restored] == [session_id]
    restored_path = object_root / "workspaces" / workspace_id / "intake" / "projects" / project_id / "datasets" / dataset_id / "ingestion_sessions" / session_id / "session.json"
    assert restored_path.exists()
    public = data_intake.public_ingestion_session(restored[0])
    assert public["project_id"] == project_id
    assert public["storage"]["provider"] == "local"


def test_public_ingestion_payload_scrubs_storage_paths_and_object_pointers():
    from app.services.data_intake import public_file_inventory, public_ingestion_session

    session = {
        "project_id": "project_a",
        "project_name": "Project A",
        "workspace_id": "user_123",
        "workspace_name": "User",
        "dataset_id": "dataset_a",
        "ingestion_session_id": "ing_a",
        "status": "ready_for_contract_review",
        "approval_status": "not_ready",
        "created_at": "now",
        "updated_at": "now",
        "storage": {
            "provider": "s3",
            "bucket": "secret-bucket",
            "prefix": "workspaces/user_123/projects/project_a",
            "root": "backend/.object-storage-local/workspaces/user_123/intake",
            "raw_dir": "backend/.object-storage-local/workspaces/user_123/intake/raw",
        },
        "files": [
            {
                "filename": "project.zip",
                "original_filename": "project.zip",
                "relative_path": "workspaces/user_123/intake/raw/project.zip",
                "content_type": "application/zip",
                "size_bytes": 3,
                "sha256": "abc",
                "suffix": ".zip",
                "bucket": "secret-bucket",
                "object_key": "workspaces/user_123/projects/project_a/raw/dataset_a/project.zip",
                "object_uri": "s3://secret-bucket/workspaces/user_123/projects/project_a/raw/dataset_a/project.zip",
                "storage_provider": "s3",
            }
        ],
        "object_storage": {"session_metadata": {"object_key": "workspaces/user_123/projects/project_a/intake/session.json", "status": "uploaded"}},
    }

    public_session = public_ingestion_session(session)
    public_inventory = public_file_inventory({"files": session["files"], "generated_at": "now"})
    serialized = json.dumps({"session": public_session, "inventory": public_inventory})

    assert "object_key" not in serialized
    assert "object_uri" not in serialized
    assert "s3://" not in serialized
    assert "secret-bucket" not in serialized
    assert "raw_dir" not in serialized
    assert "relative_path" not in serialized
    assert public_session["storage"] == {"provider": "s3", "durable": True}


def test_public_preprocessing_status_and_report_scrub_paths(monkeypatch, tmp_path):
    from app.services import data_intake, preprocessing_review

    object_root = tmp_path / "object-root"
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(object_root))
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "mirai-user-123-local")
    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", object_root / "intake")
    monkeypatch.setattr(preprocessing_review, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(preprocessing_review, "DATA_INTAKE_ROOT", object_root / "intake")

    project_id = "project_a"
    dataset_id = "dataset_a"
    session_id = "ing_a"
    workspace_id = "user_123"
    project_dir = object_root / "workspaces" / workspace_id / "intake" / "projects" / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(json.dumps({"workspace_id": workspace_id}), encoding="utf-8")
    session_dir = project_dir / "datasets" / dataset_id / "ingestion_sessions" / session_id
    (session_dir / "eda").mkdir(parents=True)
    (session_dir / "status").mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps({"project_id": project_id, "dataset_id": dataset_id, "ingestion_session_id": session_id, "workspace_id": workspace_id}),
        encoding="utf-8",
    )
    (session_dir / "status" / "preprocessing.json").write_text(
        json.dumps({"status": "preprocessing_complete_needs_approval", "report_path": "backend/local/report.json", "canonical_dir": "backend/local/canonical", "training_artifact_dir": "backend/local/training", "object_storage": {"layouts": [{"artifact_set": "eda", "status": "uploaded", "prefix": "workspaces/user_123/projects/project_a/eda"}]}}),
        encoding="utf-8",
    )
    (session_dir / "eda" / "preprocessing_report.json").write_text(
        json.dumps({
            "status": "preprocessing_complete_needs_approval",
            "canonical_artifacts": {"canonical_dir": "backend/local/canonical", "training_artifact_dir": "backend/local/training", "files": ["backend/local/canonical/model_table.csv"], "row_counts": {"model_table.csv": 1}},
            "preprocessing_artifacts": {"schema_path": "backend/local/schema.json", "artifact_dir": "backend/local/training", "row_count": 1},
            "object_storage": {"layouts": [{"artifact_set": "eda", "status": "uploaded", "objects": [{"name": "preprocessing_report.json", "object_key": "workspaces/user_123/projects/project_a/eda/dataset_a/ing_a/preprocessing_report.json"}]}]},
        }),
        encoding="utf-8",
    )

    public_status = preprocessing_review.get_public_preprocessing_status(project_id, dataset_id, session_id)
    public_report = preprocessing_review.get_public_preprocessing_review_report(project_id, dataset_id, session_id)
    serialized = json.dumps({"status": public_status, "report": public_report})

    assert "report_path" not in serialized
    assert "canonical_dir" not in serialized
    assert "training_artifact_dir" not in serialized
    assert "schema_path" not in serialized
    assert "artifact_dir" not in serialized
    assert "object_key" not in serialized
    assert "workspaces/user_123" not in serialized
    assert public_report["canonical_artifacts"]["files"] == ["model_table.csv"]


def test_domain_metadata_hydrates_schema_from_object_storage(monkeypatch, tmp_path):
    from app.services import data_intake, preprocessing_review

    object_root = tmp_path / "object-root"
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(object_root))
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "mirai-user-123-local")
    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", object_root / "intake")
    monkeypatch.setattr(preprocessing_review, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(preprocessing_review, "DATA_INTAKE_ROOT", object_root / "intake")

    project_id = "project_a"
    dataset_id = "dataset_a"
    session_id = "ing_a"
    workspace_id = "user_123"
    project_dir = object_root / "workspaces" / workspace_id / "intake" / "projects" / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(json.dumps({"workspace_id": workspace_id, "project_id": project_id, "display_name": "Project A"}), encoding="utf-8")
    session_dir = project_dir / "datasets" / dataset_id / "ingestion_sessions" / session_id
    training_latest = session_dir / "training_artifacts" / "latest"
    training_latest.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps({"project_id": project_id, "project_name": "Project A", "dataset_id": dataset_id, "ingestion_session_id": session_id, "workspace_id": workspace_id}),
        encoding="utf-8",
    )
    schema = {
        "project_id": project_id,
        "template_id": "generic_tabular_doe",
        "inputs": [{"name": "temperature", "role": "input", "dtype": "float", "unit": "C", "min": 20, "max": 80}],
        "outputs": [{"name": "efficiency", "role": "output", "dtype": "float", "unit": "%", "direction": "maximize"}],
    }
    schema_path = training_latest / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    config = WorkspaceStorageConfig(
        workspace_id=workspace_id,
        mode="local",
        bucket="mirai-user-123-local",
        prefix=f"workspaces/{workspace_id}/projects/{project_id}",
    )
    persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=workspace_id,
        artifact_set="preprocessing_artifacts",
        local_dir_or_files={"schema.json": schema_path},
        storage_config=config,
    )
    schema_path.unlink()

    status = preprocessing_review.get_domain_metadata_status(project_id, dataset_id, session_id)

    assert status["approval_status"] == "needs_admin_approval"
    assert schema_path.exists()
    variable_names = {item["name"] for item in status["domain_metadata"]["variables"]}
    assert {"temperature", "efficiency"}.issubset(variable_names)


def test_ydata_report_returns_object_storage_bytes_when_local_cache_missing(monkeypatch, tmp_path):
    from app.services import data_intake, preprocessing_review

    object_root = tmp_path / "object-root"
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(object_root))
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "mirai-user-123-local")
    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", object_root / "intake")
    monkeypatch.setattr(preprocessing_review, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(preprocessing_review, "DATA_INTAKE_ROOT", object_root / "intake")

    project_id = "project_a"
    dataset_id = "dataset_a"
    session_id = "ing_a"
    workspace_id = "user_123"
    project_dir = object_root / "workspaces" / workspace_id / "intake" / "projects" / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(json.dumps({"workspace_id": workspace_id}), encoding="utf-8")
    session_dir = project_dir / "datasets" / dataset_id / "ingestion_sessions" / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps({"project_id": project_id, "dataset_id": dataset_id, "ingestion_session_id": session_id, "workspace_id": workspace_id}),
        encoding="utf-8",
    )
    local_eda = session_dir / "eda"
    local_eda.mkdir()
    html = local_eda / "ydata_profile.html"
    html.write_text("<html>persisted</html>", encoding="utf-8")

    config = WorkspaceStorageConfig(
        workspace_id=workspace_id,
        mode="local",
        bucket="mirai-user-123-local",
        prefix=f"workspaces/{workspace_id}/projects/{project_id}",
    )
    persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=workspace_id,
        artifact_set="eda",
        local_dir_or_files={"ydata_profile.html": html},
        storage_config=config,
    )
    html.unlink()

    result = preprocessing_review.get_ydata_html_report_file_or_bytes(project_id, dataset_id, session_id)

    assert result["kind"] == "bytes"
    assert result["body"] == b"<html>persisted</html>"
    assert not html.exists()


def test_preprocessing_report_hydrates_from_object_storage(monkeypatch, tmp_path):
    from app.services import data_intake, preprocessing_review

    object_root = tmp_path / "object-root"
    monkeypatch.setenv("LOCAL_OBJECT_STORAGE_ROOT", str(object_root))
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "mirai-user-123-local")
    monkeypatch.setattr(data_intake, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(data_intake, "DATA_INTAKE_ROOT", object_root / "intake")
    monkeypatch.setattr(preprocessing_review, "OBJECT_STORE_ROOT", object_root)
    monkeypatch.setattr(preprocessing_review, "DATA_INTAKE_ROOT", object_root / "intake")

    project_id = "project_a"
    dataset_id = "dataset_a"
    session_id = "ing_a"
    workspace_id = "user_123"
    project_dir = object_root / "workspaces" / workspace_id / "intake" / "projects" / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(json.dumps({"workspace_id": workspace_id}), encoding="utf-8")
    session_dir = project_dir / "datasets" / dataset_id / "ingestion_sessions" / session_id
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(
        json.dumps({"project_id": project_id, "dataset_id": dataset_id, "ingestion_session_id": session_id, "workspace_id": workspace_id}),
        encoding="utf-8",
    )
    report_path = session_dir / "eda" / "preprocessing_report.json"
    report_path.parent.mkdir()
    report_path.write_text(json.dumps({"status": "preprocessing_complete_needs_approval"}), encoding="utf-8")

    config = WorkspaceStorageConfig(
        workspace_id=workspace_id,
        mode="local",
        bucket="mirai-user-123-local",
        prefix=f"workspaces/{workspace_id}/projects/{project_id}",
    )
    persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=workspace_id,
        artifact_set="eda",
        local_dir_or_files={"preprocessing_report.json": report_path},
        storage_config=config,
    )
    report_path.unlink()

    report = preprocessing_review.get_preprocessing_review_report(project_id, dataset_id, session_id)

    assert report["status"] == "preprocessing_complete_needs_approval"
    assert report_path.exists()
