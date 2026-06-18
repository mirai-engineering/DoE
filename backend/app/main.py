from contextlib import asynccontextmanager
import logging
import os

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import auth_required, authenticate_bearer_token, docs_public, is_public_path, principal_workspace_id, request_principal
from .schemas import (
    BOConfig,
    BOConfigUpdate,
    BOFantasyRolloutRequest,
    BOFantasyRolloutResponse,
    BOInitializeReplayRequest,
    BORevealReplayResponse,
    BOReviewRequest,
    BOReviewResponse,
    BOStateResponse,
    BOSuggestResponse,
    BatchPredictRequest,
    BatchPredictResponse,
    DomainMetadataApprovalRequest,
    DomainMetadataUpdateRequest,
    FileInventoryResponse,
    IngestionSessionResponse,
    PredictRequest,
    PreprocessingApprovalRequest,
    TrainingRequestCreate,
    PredictResponse,
    RecommendRequest,
    RecommendResponse,
    ScientistReviewUpdate,
)
from .services.bayesian_optimization import (
    get_bo_state,
    initialize_replay,
    reveal_replay_result,
    review_suggestion,
    save_bo_config_update,
    suggest_next_experiment,
)
from .services.business_impact import get_business_impact_summary
from .services.control_plane import get_project_runtime_state, log_audit
from .services.data_intake import append_ingestion_files, create_ingestion_session, get_file_inventory, get_ingestion_session, list_ingestion_sessions
from .services.design_studio import export_design_zip, get_design_studio_state, pareto_tradeoff_candidates, predict_design, seed_batch_candidate
from .services.fantasy_rollout import run_fantasy_rollout
from .services.model_loader import are_models_loaded, load_all_models
from .services.mlflow_registry import durable_artifact_pointer_for_project
from .services.model_quality import (
    get_active_model_metadata,
    get_artifact_summary,
    get_latest_runs,
    get_metrics,
    export_predictions_zip,
    get_model_quality_summary,
    get_predictions,
    get_preprocessing_report,
    get_scientist_review,
    save_scientist_review,
)
from .services.prediction import predict_rows
from .services.preprocessing_review import (
    approve_domain_metadata,
    approve_preprocessing,
    generate_preprocessing_report,
    ensure_ydata_html_report,
    get_domain_metadata_status,
    get_preprocessing_eda_summary,
    get_preprocessing_review_report,
    get_preprocessing_status,
    queue_fuel_cell_preprocessing,
    start_fuel_cell_preprocessing,
    update_domain_metadata,
    validate_fuel_cell_package,
)
from .services.project_registry import (
    ProjectNotFoundError,
    clear_registry_cache,
    get_project_schema,
    list_projects,
)
from .services.recommendation import recommend_experiments
from .services.training_requests import create_training_request, get_training_status, list_training_requests, start_training_request
from .services.workspaces import list_workspaces


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Mirai DoE Engine API")
    load_all_models()
    yield


cors_origins_env = os.getenv("CORS_ORIGINS")
if cors_origins_env:
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
else:
    cors_origins = ["http://localhost:3000", "http://localhost:3001", "http://frontend:3000"]


app = FastAPI(
    title="Mirai DoE Engine API",
    version="0.1.0",
    description="Generic tabular experiment optimization backend",
    lifespan=lifespan,
    docs_url="/docs" if docs_public() else None,
    redoc_url="/redoc" if docs_public() else None,
    openapi_url="/openapi.json" if docs_public() else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_clerk_auth(request: Request, call_next):
    if request.method == "OPTIONS" or not auth_required() or is_public_path(request.url.path):
        return await call_next(request)

    try:
        request.state.principal = authenticate_bearer_token(request.headers.get("Authorization"))
        if not principal_workspace_id(request_principal(request)):
            return JSONResponse(status_code=403, content={"detail": "Authenticated workspace required"})
        project_id = _project_id_from_path(request.url.path)
        if project_id and not _request_can_access_project(request, project_id):
            return JSONResponse(status_code=403, content={"detail": "Workspace access denied"})
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return await call_next(request)


def _raise_api_error(exc: Exception) -> None:
    if isinstance(exc, ProjectNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Internal server error") from exc


def _authorized_workspace_id(request: Request) -> str | None:
    if not auth_required():
        return None
    return principal_workspace_id(request_principal(request))


def _filter_projects_for_request(request: Request, projects: list[dict] | None = None) -> list[dict]:
    workspace_id = _authorized_workspace_id(request)
    if workspace_id:
        return list_projects(workspace_id)
    return projects if projects is not None else list_projects()


def _filter_workspaces_for_request(request: Request, workspaces: list[dict]) -> list[dict]:
    workspace_id = _authorized_workspace_id(request)
    if not workspace_id:
        return workspaces
    return [workspace for workspace in workspaces if workspace.get("workspace_id") == workspace_id]


def _project_id_from_path(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "projects":
        return parts[1]
    if len(parts) >= 3 and parts[0] == "data-intake" and parts[1] == "projects":
        return parts[2]
    return None


def _request_can_access_project(request: Request, project_id: str) -> bool:
    if not auth_required():
        return True
    return any(project.get("id") == project_id for project in _filter_projects_for_request(request))


def _request_user_id(request: Request) -> str | None:
    principal = request_principal(request)
    return principal.clerk_user_id if principal else None


def _static_index_path() -> str | None:
    static_dir = os.getenv("MIRAI_STATIC_DIR")
    if not static_dir:
        return None
    index_path = os.path.join(static_dir, "index.html")
    return index_path if os.path.exists(index_path) else None


@app.get("/")
def api_info():
    index_path = _static_index_path()
    if index_path:
        return FileResponse(index_path)
    return {
        "name": "Mirai DoE Engine API",
        "version": "0.1.0",
        "description": "Generic tabular experiment optimization backend",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "available_projects": [project["id"] for project in list_projects()],
        "models_loaded": are_models_loaded(),
    }


@app.get("/api/health")
def api_health_check():
    return health_check()


@app.get("/projects")
def projects(request: Request):
    workspace_id = _authorized_workspace_id(request)
    log_audit(
        workspace_id=workspace_id,
        user_id=_request_user_id(request),
        action="projects_listed",
        resource_type="project",
        ip_address=request.client.host if request.client else None,
    )
    return {
        "projects": _filter_projects_for_request(request),
        "workspaces": _filter_workspaces_for_request(request, list_workspaces()),
    }


@app.get("/workspaces")
def workspaces(request: Request):
    return {"workspaces": _filter_workspaces_for_request(request, list_workspaces())}


@app.get("/data-intake/sessions")
def data_intake_sessions(request: Request):
    try:
        workspace_id = _authorized_workspace_id(request)
        sessions = list_ingestion_sessions()
        if workspace_id:
            sessions = [session for session in sessions if session.get("workspace_id") == workspace_id]
        return {"sessions": sessions}
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Data intake session listing failed")
        _raise_api_error(exc)


@app.post("/data-intake/sessions", response_model=IngestionSessionResponse)
async def data_intake_create_session(
    project_name: str = Form(...),
    notes: str | None = Form(default=None),
    ingestion_path: str = Form(default="generic_tabular_doe"),
    workspace_name: str | None = Form(default=None),
    existing_project_id: str | None = Form(default=None),
    files: list[UploadFile] = File(...),
):
    try:
        session = await create_ingestion_session(
            project_name=project_name,
            uploads=files,
            notes=notes,
            ingestion_path=ingestion_path,
            workspace_name=workspace_name,
            existing_project_id=existing_project_id,
        )
        clear_registry_cache()
        return session
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Data intake session creation failed")
        _raise_api_error(exc)


@app.post("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/files", response_model=IngestionSessionResponse)
async def data_intake_append_files(project_id: str, dataset_id: str, session_id: str, files: list[UploadFile] = File(...)):
    try:
        return await append_ingestion_files(project_id, dataset_id, session_id, files)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Data intake append files failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}", response_model=IngestionSessionResponse)
def data_intake_get_session(project_id: str, dataset_id: str, session_id: str):
    try:
        return get_ingestion_session(project_id, dataset_id, session_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Data intake session lookup failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/inventory", response_model=FileInventoryResponse)
def data_intake_inventory(project_id: str, dataset_id: str, session_id: str):
    try:
        return get_file_inventory(project_id, dataset_id, session_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Data intake inventory failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/fuel-cell-package/validation")
def data_intake_validate_fuel_cell_package(project_id: str, dataset_id: str, session_id: str):
    try:
        return validate_fuel_cell_package(project_id, dataset_id, session_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Fuel-cell package validation failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing/start")
def data_intake_start_fuel_cell_preprocessing(project_id: str, dataset_id: str, session_id: str, background_tasks: BackgroundTasks):
    try:
        queued = queue_fuel_cell_preprocessing(project_id, dataset_id, session_id)
        if queued.get("status") == "queued":
            background_tasks.add_task(start_fuel_cell_preprocessing, project_id, dataset_id, session_id)
        return queued
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Fuel-cell preprocessing failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing/eda-summary")
def data_intake_get_preprocessing_eda_summary(project_id: str, dataset_id: str, session_id: str):
    try:
        return get_preprocessing_eda_summary(project_id, dataset_id, session_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Preprocessing EDA summary lookup failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing/ydata-report.html")
def data_intake_get_ydata_html_report(project_id: str, dataset_id: str, session_id: str):
    try:
        path = ensure_ydata_html_report(project_id, dataset_id, session_id)
        return FileResponse(path, media_type="text/html", filename="mirai_ydata_profile.html")
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("ydata HTML report failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing/status")
def data_intake_get_preprocessing_status(project_id: str, dataset_id: str, session_id: str):
    try:
        return get_preprocessing_status(project_id, dataset_id, session_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Preprocessing status lookup failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing-report")
def data_intake_generate_preprocessing_report(project_id: str, dataset_id: str, session_id: str):
    try:
        return generate_preprocessing_report(project_id, dataset_id, session_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Preprocessing report generation failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing-report")
def data_intake_get_preprocessing_report(project_id: str, dataset_id: str, session_id: str):
    try:
        return get_preprocessing_review_report(project_id, dataset_id, session_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Preprocessing report lookup failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/domain-metadata")
def data_intake_get_domain_metadata(project_id: str, dataset_id: str, session_id: str):
    try:
        return get_domain_metadata_status(project_id, dataset_id, session_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Domain metadata lookup failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.put("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/domain-metadata")
def data_intake_update_domain_metadata(project_id: str, dataset_id: str, session_id: str, request: DomainMetadataUpdateRequest):
    try:
        return update_domain_metadata(project_id, dataset_id, session_id, request.domain_metadata, updated_by=request.updated_by, notes=request.notes)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Domain metadata update failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/domain-metadata/approval")
def data_intake_approve_domain_metadata(project_id: str, dataset_id: str, session_id: str, request: DomainMetadataApprovalRequest):
    try:
        return approve_domain_metadata(project_id, dataset_id, session_id, approver=request.approver, notes=request.notes)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Domain metadata approval failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/preprocessing-approval")
def data_intake_approve_preprocessing(project_id: str, dataset_id: str, session_id: str, request: PreprocessingApprovalRequest):
    try:
        return approve_preprocessing(project_id, dataset_id, session_id, approver=request.approver, notes=request.notes)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Preprocessing approval failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests")
def data_intake_list_training_requests(project_id: str, dataset_id: str, session_id: str):
    try:
        return {"training_requests": list_training_requests(project_id, dataset_id, session_id)}
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Training request listing failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests/{training_request_id}/start")
def data_intake_start_training_request(project_id: str, dataset_id: str, session_id: str, training_request_id: str, request: Request):
    try:
        workspace_id = _authorized_workspace_id(request)
        log_audit(
            workspace_id=workspace_id,
            user_id=_request_user_id(request),
            action="training_triggered",
            resource_type="training_request",
            resource_id=training_request_id,
            ip_address=request.client.host if request.client else None,
            metadata={"project_id": project_id, "dataset_id": dataset_id, "session_id": session_id},
        )
        return start_training_request(project_id, dataset_id, session_id, training_request_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Training start failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests/{training_request_id}/status")
def data_intake_get_training_request_status(project_id: str, dataset_id: str, session_id: str, training_request_id: str):
    try:
        return get_training_status(project_id, dataset_id, session_id, training_request_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Training status lookup failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/data-intake/projects/{project_id}/datasets/{dataset_id}/sessions/{session_id}/training-requests")
def data_intake_create_training_request(project_id: str, dataset_id: str, session_id: str, request: TrainingRequestCreate):
    try:
        return create_training_request(
            project_id,
            dataset_id,
            session_id,
            requested_by=request.requested_by,
            preset=request.preset,
            model_families=request.model_families,
            training_config=request.training_config.model_dump(),
            notes=request.notes,
        )
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Training request creation failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/schema")
def project_schema(project_id: str, request: Request):
    try:
        workspace_id = _authorized_workspace_id(request)
        log_audit(
            workspace_id=workspace_id,
            user_id=_request_user_id(request),
            action="project_opened",
            resource_type="project",
            resource_id=project_id,
            ip_address=request.client.host if request.client else None,
        )
        return get_project_schema(project_id, workspace_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        _raise_api_error(exc)


@app.get("/projects/{project_id}/artifact-status")
def project_artifact_status(project_id: str, request: Request):
    try:
        authorized_workspace_id = _authorized_workspace_id(request)
        schema = get_project_schema(project_id, authorized_workspace_id)
        workspace_id = authorized_workspace_id or schema.get("workspace_id")
        runtime_state = get_project_runtime_state(workspace_id, project_id) if workspace_id else None
        log_audit(
            workspace_id=workspace_id,
            user_id=_request_user_id(request),
            action="artifact_status_viewed",
            resource_type="project",
            resource_id=project_id,
            ip_address=request.client.host if request.client else None,
        )
        pointers = {}
        for artifact_kind in ["dataset", "canonical_table", "preprocessing_output", "mlflow_artifacts", "onnx_model", "bo_state", "review_file"]:
            try:
                pointers[artifact_kind] = durable_artifact_pointer_for_project(project_id, artifact_kind, workspace_id)
            except Exception as exc:  # noqa: BLE001 - individual artifacts may be intentionally deferred.
                pointers[artifact_kind] = {"status": "unavailable", "detail": str(exc)}

        quality_status = {"available": False, "message": "Model quality is unavailable until training/bootstrap produces complete quality artifacts."}
        try:
            artifacts = get_artifact_summary(project_id)
            quality_status = {
                "available": True,
                "message": "Model quality artifacts are available.",
                "prediction_diagnostics_available": bool(artifacts.get("prediction_diagnostics_available")),
            }
        except Exception as exc:  # noqa: BLE001 - API card should explain partial state instead of failing.
            quality_status["detail"] = str(exc)

        postgres_state = None
        if runtime_state:
            champion = runtime_state.get("champion_model") or {}
            training_run = runtime_state.get("training_run") or {}
            dataset = runtime_state.get("dataset") or {}
            schema_manifest = runtime_state.get("schema_manifest") or {}
            postgres_state = {
                "source": "postgres",
                "dataset_id": dataset.get("dataset_id"),
                "dataset_status": dataset.get("status"),
                "dataset_object_uri": dataset.get("object_uri"),
                "schema_id": schema_manifest.get("schema_id"),
                "schema_manifest_object_uri": schema_manifest.get("manifest_object_uri"),
                "training_run_id": training_run.get("training_run_id"),
                "training_status": training_run.get("status"),
                "mlflow_run_id": training_run.get("mlflow_run_id"),
                "artifact_s3_prefix": training_run.get("artifact_s3_prefix"),
                "champion_model_id": champion.get("model_id"),
                "champion_model_uri": champion.get("artifact_s3_uri"),
            }

        return {
            "project_id": project_id,
            "display_name": schema.get("display_name", project_id),
            "workspace_id": schema.get("workspace_id"),
            "workspace_name": schema.get("workspace_name"),
            "artifact_pointers": pointers,
            "postgres_state": postgres_state,
            "model_quality": quality_status,
            "durability_note": "Level 2 durable state is represented by Postgres metadata plus workspace/project-scoped object pointers.",
        }
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Artifact status failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/predict", response_model=PredictResponse)
def predict(project_id: str, request: PredictRequest):
    try:
        predictions, warnings, model_version = predict_rows(project_id, [request.inputs])
        return PredictResponse(
            project_id=project_id,
            predictions=predictions[0],
            model_version=model_version,
            warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Prediction failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/batch-predict", response_model=BatchPredictResponse)
def batch_predict(project_id: str, request: BatchPredictRequest):
    try:
        predictions, warnings, model_version = predict_rows(project_id, request.inputs)
        return BatchPredictResponse(
            project_id=project_id,
            predictions=predictions,
            model_version=model_version,
            warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Batch prediction failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/recommend", response_model=RecommendResponse)
def recommend(project_id: str, request: RecommendRequest, http_request: Request):
    try:
        result = recommend_experiments(project_id, request)
        log_audit(
            workspace_id=_authorized_workspace_id(http_request),
            user_id=_request_user_id(http_request),
            action="recommendations_generated",
            resource_type="project",
            resource_id=project_id,
            ip_address=http_request.client.host if http_request.client else None,
        )
        return result
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Recommendation failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/bo/state", response_model=BOStateResponse)
def bo_state(project_id: str):
    try:
        return get_bo_state(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("BO state failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/bo/initialize-replay", response_model=BOStateResponse)
def bo_initialize_replay(project_id: str, request: BOInitializeReplayRequest):
    try:
        return initialize_replay(project_id, request)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("BO replay initialization failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/bo/suggest", response_model=BOSuggestResponse)
def bo_suggest(project_id: str, request: BOConfig):
    try:
        return suggest_next_experiment(project_id, request)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("BO suggestion failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/bo/experiments/{experiment_id}/review", response_model=BOReviewResponse)
def bo_review(project_id: str, experiment_id: str, request: BOReviewRequest):
    try:
        return review_suggestion(project_id, experiment_id, request)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("BO review failed for project_id=%s experiment_id=%s", project_id, experiment_id)
        _raise_api_error(exc)


@app.post(
    "/projects/{project_id}/bo/experiments/{experiment_id}/reveal-replay-result",
    response_model=BORevealReplayResponse,
)
def bo_reveal_replay(project_id: str, experiment_id: str):
    try:
        return reveal_replay_result(project_id, experiment_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("BO replay reveal failed for project_id=%s experiment_id=%s", project_id, experiment_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/bo/config", response_model=BOStateResponse)
def bo_config(project_id: str, request: BOConfigUpdate):
    try:
        return save_bo_config_update(project_id, request)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("BO config update failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/design-studio/state")
def design_studio_state(project_id: str):
    try:
        return get_design_studio_state(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Design Studio state failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/design-studio/predict")
def design_studio_predict(project_id: str, request: dict):
    try:
        return predict_design(project_id, request)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Design Studio prediction failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/design-studio/seed/batch")
def design_studio_seed_batch(project_id: str, request: dict):
    try:
        return seed_batch_candidate(project_id, request)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Design Studio batch seed failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/design-studio/pareto")
def design_studio_pareto(project_id: str, request: dict):
    try:
        return pareto_tradeoff_candidates(project_id, request)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Design Studio Pareto search failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/design-studio/export.zip")
def design_studio_export(project_id: str, request: dict, http_request: Request):
    try:
        payload = export_design_zip(project_id, request)
        log_audit(
            workspace_id=_authorized_workspace_id(http_request),
            user_id=_request_user_id(http_request),
            action="artifact_downloaded",
            resource_type="design_studio_export",
            resource_id=project_id,
            ip_address=http_request.client.host if http_request.client else None,
        )
        filename = f"{project_id}_design_studio_export.zip"
        return Response(
            content=payload,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Design Studio export failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/impact/summary")
def impact_summary(project_id: str):
    try:
        return get_business_impact_summary(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Impact summary failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/model-quality/summary")
def model_quality_summary(project_id: str):
    try:
        return get_model_quality_summary(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality summary failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/model-quality/latest-runs")
def model_quality_latest_runs(project_id: str):
    try:
        return {"project_id": project_id, "runs": get_latest_runs(project_id)}
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality latest runs failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/model-quality/metrics")
def model_quality_metrics(project_id: str):
    try:
        return get_metrics(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality metrics failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/model-quality/preprocessing-report")
def model_quality_preprocessing_report(project_id: str):
    try:
        return get_preprocessing_report(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality preprocessing report failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/model-quality/artifacts")
def model_quality_artifacts(project_id: str, request: Request):
    try:
        log_audit(
            workspace_id=_authorized_workspace_id(request),
            user_id=_request_user_id(request),
            action="artifact_status_viewed",
            resource_type="model_quality_artifacts",
            resource_id=project_id,
            ip_address=request.client.host if request.client else None,
        )
        return get_artifact_summary(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality artifacts failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/model-quality/predictions")
def model_quality_predictions(
    project_id: str,
    model_name: str | None = None,
    splits: str | None = None,
    limit: int = Query(default=5000, ge=1, le=50000),
):
    try:
        return get_predictions(project_id, model_name=model_name, splits=splits, limit=limit)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality predictions failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/model-quality/predictions/export.zip")
def model_quality_predictions_export(project_id: str, request: Request, model_name: str | None = None, splits: str | None = None):
    try:
        payload = export_predictions_zip(project_id, model_name=model_name, splits=splits)
        log_audit(
            workspace_id=_authorized_workspace_id(request),
            user_id=_request_user_id(request),
            action="artifact_downloaded",
            resource_type="prediction_diagnostics",
            resource_id=project_id,
            ip_address=request.client.host if request.client else None,
            metadata={"model_name": model_name, "splits": splits},
        )
        filename = f"{project_id}_prediction_diagnostics.zip"
        return Response(
            content=payload,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality predictions export failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/model-quality/active-model")
def model_quality_active_model(project_id: str):
    try:
        return get_active_model_metadata(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality active model failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.get("/projects/{project_id}/model-quality/scientist-review")
def model_quality_scientist_review(project_id: str):
    try:
        return get_scientist_review(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality scientist review failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/model-quality/scientist-review")
def model_quality_save_scientist_review(project_id: str, request: ScientistReviewUpdate):
    try:
        return save_scientist_review(project_id, request.model_dump(exclude_none=True))
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("Model quality scientist review save failed for project_id=%s", project_id)
        _raise_api_error(exc)


@app.post("/projects/{project_id}/bo/fantasy-rollout", response_model=BOFantasyRolloutResponse)
def bo_fantasy_rollout(project_id: str, request: BOFantasyRolloutRequest):
    try:
        return run_fantasy_rollout(project_id, request)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
        logger.exception("BO fantasy rollout failed for project_id=%s", project_id)
        _raise_api_error(exc)


static_dir = os.getenv("MIRAI_STATIC_DIR")
if static_dir and os.path.isdir(static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    index_path = _static_index_path()
    if not index_path:
        raise HTTPException(status_code=404, detail="Not found")
    static_dir = os.getenv("MIRAI_STATIC_DIR") or ""
    candidate = os.path.join(static_dir, full_path)
    if full_path and os.path.exists(candidate) and os.path.isfile(candidate):
        return FileResponse(candidate)
    return FileResponse(index_path)
