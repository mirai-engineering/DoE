import numpy as np

from .loader import get_model_bundle, predict
from .preprocessing import (
    inverse_transform_outputs,
    output_names,
    rows_to_feature_matrix,
    transform_inputs,
)


def predict_rows(
    project_id: str,
    rows: list[dict[str, float]],
    *,
    warn_near_bounds: bool = True,
    workspace_id: str | None = None,
    force_ml_preprocessing_v1: bool = False,
) -> tuple[list[dict[str, float]], list[str], str]:
    model = get_model_bundle(project_id, workspace_id)

    raw_features, warnings = rows_to_feature_matrix(
        model.schema,
        rows,
        warn_near_bounds=warn_near_bounds,
    )
    has_fitted_v1 = model.preprocessing.get("preprocessing_contract_version") == "mirai-ml-preprocessing-v1" and bool(model.preprocessing.get("fitted_parameters"))
    should_apply_preprocessing = getattr(model, "model_kind", "onnx_scaled") not in {"sklearn_raw", "onnx_raw"} or (force_ml_preprocessing_v1 and has_fitted_v1)
    if not should_apply_preprocessing:
        outputs = predict(project_id, raw_features, workspace_id)
    else:
        features = transform_inputs(raw_features, model.preprocessing)
        scaled_outputs = predict(project_id, features, workspace_id)
        outputs = inverse_transform_outputs(scaled_outputs, model.preprocessing)

    names = output_names(model.schema)
    named_predictions: list[dict[str, float]] = []
    for row in np.asarray(outputs, dtype=np.float32):
        named_predictions.append({name: float(value) for name, value in zip(names, row, strict=True)})

    model_version = model.metadata.get("model_version", "unknown")
    return named_predictions, warnings, model_version
