from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import (
    BOConfig,
    BOConfigUpdate,
    BOInitializeReplayRequest,
    BORevealReplayResponse,
    BOReviewRequest,
    BOReviewResponse,
    BOStateResponse,
    BOSuggestResponse,
    BatchPredictRequest,
    BatchPredictResponse,
    PredictRequest,
    PredictResponse,
    RecommendRequest,
    RecommendResponse,
)
from .services.bayesian_optimization import (
    get_bo_state,
    initialize_replay,
    reveal_replay_result,
    review_suggestion,
    save_bo_config_update,
    suggest_next_experiment,
)
from .services.model_loader import are_models_loaded, load_all_models
from .services.prediction import predict_rows
from .services.project_registry import (
    ProjectNotFoundError,
    get_project_schema,
    list_projects,
)
from .services.recommendation import recommend_experiments


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
    return {"projects": list_projects()}


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
