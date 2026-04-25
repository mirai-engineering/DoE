from dataclasses import dataclass
import logging

import numpy as np
import onnxruntime as ort

from .project_registry import (
    get_project_metadata,
    get_project_model_path,
    get_project_preprocessing,
    get_project_schema,
    list_projects,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectModel:
    project_id: str
    session: ort.InferenceSession
    input_name: str
    output_name: str
    schema: dict
    metadata: dict
    preprocessing: dict


_MODEL_CACHE: dict[str, ProjectModel] = {}


def load_model(project_id: str) -> ProjectModel:
    cached = _MODEL_CACHE.get(project_id)
    if cached is not None:
        return cached

    schema = get_project_schema(project_id)
    metadata = get_project_metadata(project_id)
    preprocessing = get_project_preprocessing(project_id)
    model_path = get_project_model_path(project_id)

    logger.info("Loading ONNX model for project_id=%s from %s", project_id, model_path)
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name

    model = ProjectModel(
        project_id=project_id,
        session=session,
        input_name=input_name,
        output_name=output_name,
        schema=schema,
        metadata=metadata,
        preprocessing=preprocessing,
    )
    _MODEL_CACHE[project_id] = model
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
        try:
            load_model(project["id"])
        except Exception as exc:  # noqa: BLE001 - health reports the aggregate state.
            all_loaded = False
            logger.warning("Could not load model for project_id=%s: %s", project["id"], exc)
    return all_loaded


def are_models_loaded() -> bool:
    projects = list_projects()
    if not projects:
        return False
    return all(project["id"] in _MODEL_CACHE for project in projects)


def get_model_bundle(project_id: str) -> ProjectModel:
    return load_model(project_id)


def predict(project_id: str, input_matrix: np.ndarray) -> np.ndarray:
    model = load_model(project_id)
    features = np.ascontiguousarray(input_matrix, dtype=np.float32)
    outputs = model.session.run([model.output_name], {model.input_name: features})[0]
    return np.asarray(outputs, dtype=np.float32)
