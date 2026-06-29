from dataclasses import dataclass
import logging
from typing import Any

import joblib
import numpy as np
import onnxruntime as ort

from .project_registry import (
    get_project_metadata,
    get_project_model_path,
    get_project_preprocessing,
    get_project_schema,
    is_packaged_project,
    list_projects,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectModel:
    project_id: str
    session: ort.InferenceSession | None
    input_name: str
    output_name: str
    schema: dict
    metadata: dict
    preprocessing: dict
    estimator: Any | None = None
    model_kind: str = "onnx_scaled"


_MODEL_CACHE: dict[str, ProjectModel] = {}


def _cache_key(project_id: str, workspace_id: str | None = None) -> str:
    return f"{workspace_id or '_default'}::{project_id}"


def _requires_external_preprocessing(preprocessing: dict) -> bool:
    return preprocessing.get("preprocessing_contract_version") == "mirai-ml-preprocessing-v1" and bool(preprocessing.get("fitted_parameters"))


def load_model(project_id: str, workspace_id: str | None = None) -> ProjectModel:
    cache_key = _cache_key(project_id, workspace_id)
    cached = _MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    schema = get_project_schema(project_id, workspace_id)
    metadata = get_project_metadata(project_id, workspace_id)
    preprocessing = get_project_preprocessing(project_id, workspace_id)
    model_path = get_project_model_path(project_id, workspace_id)

    if model_path.suffix.lower() in {".joblib", ".pkl"}:
        logger.info("Loading sklearn/joblib-compatible model for project_id=%s from %s", project_id, model_path)
        estimator = joblib.load(model_path)
        model = ProjectModel(
            project_id=project_id,
            session=None,
            input_name="raw_features",
            output_name="raw_outputs",
            schema=schema,
            metadata={**metadata, "model_artifact_format": "joblib"},
            preprocessing=preprocessing,
            estimator=estimator,
            model_kind="sklearn_raw",
        )
        _MODEL_CACHE[cache_key] = model
        return model

    logger.info("Loading ONNX model for project_id=%s from %s", project_id, model_path)
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    template_id = preprocessing.get("template_id") or (schema.get("metadata", {}).get("template_id") if isinstance(schema.get("metadata"), dict) else None)
    requires_preprocessing = _requires_external_preprocessing(preprocessing)
    model_kind = "onnx_scaled" if requires_preprocessing else ("onnx_raw" if template_id == "generic_tabular_doe" and input_name == "raw_features" else "onnx_scaled")
    serving_metadata = {
        **metadata,
        "model_artifact_format": "onnx",
        "serving_input_space": "schema_raw" if not requires_preprocessing else "model_table_preprocessed",
        "requires_ml_preprocessing_v1": bool(requires_preprocessing),
    }

    model = ProjectModel(
        project_id=project_id,
        session=session,
        input_name=input_name,
        output_name=output_name,
        schema=schema,
        metadata=serving_metadata,
        preprocessing=preprocessing,
        model_kind=model_kind,
    )
    _MODEL_CACHE[cache_key] = model
    logger.info(
        "Loaded model for project_id=%s input=%s output=%s providers=%s",
        project_id,
        input_name,
        output_name,
        session.get_providers(),
    )
    return model


def load_all_models() -> bool:
    all_loaded = True
    for project in list_projects():
        if not is_packaged_project(project["id"]):
            continue
        try:
            load_model(project["id"])
        except Exception as exc:  # noqa: BLE001 - health reports the aggregate state.
            all_loaded = False
            logger.warning("Could not load model for project_id=%s: %s", project["id"], exc)
    return all_loaded


def are_models_loaded() -> bool:
    projects = [project for project in list_projects() if is_packaged_project(project["id"])]
    if not projects:
        return False
    return all(any(key.endswith(f"::{project['id']}") for key in _MODEL_CACHE) for project in projects)


def clear_model_cache(project_id: str | None = None, workspace_id: str | None = None) -> None:
    if project_id is None:
        _MODEL_CACHE.clear()
        return
    cache_key = _cache_key(project_id, workspace_id)
    _MODEL_CACHE.pop(cache_key, None)
    if workspace_id is None:
        for key in [key for key in _MODEL_CACHE if key.endswith(f"::{project_id}")]:
            _MODEL_CACHE.pop(key, None)


def get_model_bundle(project_id: str, workspace_id: str | None = None) -> ProjectModel:
    return load_model(project_id, workspace_id)


def predict(project_id: str, input_matrix: np.ndarray, workspace_id: str | None = None) -> np.ndarray:
    model = load_model(project_id, workspace_id)
    features = np.ascontiguousarray(input_matrix, dtype=np.float32)
    if model.model_kind == "sklearn_raw":
        if model.estimator is None:
            raise RuntimeError(f"Sklearn model for {project_id} is not loaded")
        return np.asarray(model.estimator.predict(input_matrix), dtype=np.float32)
    if model.session is None:
        raise RuntimeError(f"ONNX session for {project_id} is not loaded")
    outputs = model.session.run([model.output_name], {model.input_name: features})[0]
    return np.asarray(outputs, dtype=np.float32)
