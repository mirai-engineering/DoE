from contextlib import asynccontextmanager
import logging
import os

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

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
from .services.data_intake import append_ingestion_files, create_ingestion_session, get_file_inventory, get_ingestion_session, list_ingestion_sessions
from .services.design_studio import export_design_zip, get_design_studio_state, pareto_tradeoff_candidates, predict_design, seed_batch_candidate
from .services.fantasy_rollout import run_fantasy_rollout
from .services.model_loader import are_models_loaded, load_all_models
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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _raise_api_error(exc: Exception) -> None:
    if isinstance(exc, ProjectNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/")
def api_info():
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


@app.get("/projects")
def projects():
    return {"projects": list_projects(), "workspaces": list_workspaces()}


@app.get("/workspaces")
def workspaces():
    return {"workspaces": list_workspaces()}


@app.get("/data-intake/sessions")
def data_intake_sessions():
    try:
        return {"sessions": list_ingestion_sessions()}
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
def data_intake_start_training_request(project_id: str, dataset_id: str, session_id: str, training_request_id: str):
    try:
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
def project_schema(project_id: str):
    try:
        return get_project_schema(project_id)
    except Exception as exc:  # noqa: BLE001 - translated to API-safe errors.
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
def recommend(project_id: str, request: RecommendRequest):
    try:
        return recommend_experiments(project_id, request)
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
def design_studio_export(project_id: str, request: dict):
    try:
        payload = export_design_zip(project_id, request)
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
def model_quality_artifacts(project_id: str):
    try:
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
def model_quality_predictions_export(project_id: str, model_name: str | None = None, splits: str | None = None):
    try:
        payload = export_predictions_zip(project_id, model_name=model_name, splits=splits)
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
