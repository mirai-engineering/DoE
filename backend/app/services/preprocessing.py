import math
from typing import Any

import numpy as np


NEAR_BOUND_FRACTION = 0.02


def input_names(schema: dict) -> list[str]:
    return [item["name"] for item in schema.get("inputs", [])]


def output_names(schema: dict) -> list[str]:
    return [item["name"] for item in schema.get("outputs", [])]


def _input_map(schema: dict) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in schema.get("inputs", [])}


def _as_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Input '{name}' must be numeric, not boolean")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Input '{name}' must be numeric") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"Input '{name}' must be finite")
    return numeric


def validate_row(
    schema: dict,
    row: dict[str, Any],
    *,
    require_all: bool = True,
    allow_unknown: bool | None = None,
    warn_near_bounds: bool = True,
    row_index: int | None = None,
) -> tuple[list[float], list[str]]:
    variables = _input_map(schema)
    expected_names = list(variables)
    allow_unknown_inputs = schema.get("allow_unknown_inputs", False) if allow_unknown is None else allow_unknown

    missing = [name for name in expected_names if name not in row]
    if require_all and missing:
        raise ValueError(f"Missing required inputs: {', '.join(missing)}")

    unknown = [name for name in row if name not in variables]
    if unknown and not allow_unknown_inputs:
        raise ValueError(f"Unknown inputs: {', '.join(sorted(unknown))}")

    values: list[float] = []
    warnings: list[str] = []
    row_prefix = f"row {row_index}: " if row_index is not None else ""

    for name in expected_names:
        if name not in row:
            continue
        variable = variables[name]
        value = _as_float(row[name], name)
        minimum = float(variable["min"])
        maximum = float(variable["max"])
        if value < minimum or value > maximum:
            raise ValueError(
                f"{row_prefix}Input '{name}'={value:g} is outside allowed bounds "
                f"[{minimum:g}, {maximum:g}]"
            )

        if warn_near_bounds:
            span = maximum - minimum
            if span > 0:
                threshold = span * NEAR_BOUND_FRACTION
                if value - minimum <= threshold:
                    warnings.append(f"{row_prefix}Input '{name}' is near its lower bound")
                elif maximum - value <= threshold:
                    warnings.append(f"{row_prefix}Input '{name}' is near its upper bound")
        values.append(value)

    return values, warnings


def rows_to_feature_matrix(
    schema: dict,
    rows: list[dict[str, Any]],
    *,
    warn_near_bounds: bool = True,
) -> tuple[np.ndarray, list[str]]:
    if not rows:
        raise ValueError("At least one input row is required")

    matrix: list[list[float]] = []
    warnings: list[str] = []
    for index, row in enumerate(rows):
        values, row_warnings = validate_row(
            schema,
            row,
            require_all=True,
            warn_near_bounds=warn_near_bounds,
            row_index=index if len(rows) > 1 else None,
        )
        matrix.append(values)
        warnings.extend(row_warnings)

    return np.asarray(matrix, dtype=np.float32), warnings


def transform_inputs(input_matrix: np.ndarray, preprocessing: dict) -> np.ndarray:
    values = np.asarray(input_matrix, dtype=np.float32).copy()

    imputer = preprocessing.get("input_imputer")
    if imputer:
        method = imputer.get("method")
        if method != "median":
            raise ValueError(f"Unsupported input imputer method: {method}")
        statistics = np.asarray(imputer["statistics"], dtype=np.float32)
        if statistics.shape[0] != values.shape[1]:
            raise ValueError("Input imputer statistics do not match feature count")
        missing_mask = ~np.isfinite(values)
        if missing_mask.any():
            values[missing_mask] = np.take(statistics, np.where(missing_mask)[1])

    scaler = preprocessing.get("input_scaler", {})
    method = scaler.get("method")
    if method != "minmax":
        raise ValueError(f"Unsupported input scaler method: {method}")

    minimum = np.asarray(scaler["min"], dtype=np.float32)
    maximum = np.asarray(scaler["max"], dtype=np.float32)
    scale = np.where(maximum > minimum, maximum - minimum, 1.0)
    return ((values - minimum) / scale).astype(np.float32)


def inverse_transform_outputs(output_matrix: np.ndarray, preprocessing: dict) -> np.ndarray:
    scaler = preprocessing.get("output_scaler", {})
    method = scaler.get("method")
    if method != "minmax":
        raise ValueError(f"Unsupported output scaler method: {method}")

    minimum = np.asarray(scaler["min"], dtype=np.float32)
    maximum = np.asarray(scaler["max"], dtype=np.float32)
    scale = np.where(maximum > minimum, maximum - minimum, 1.0)
    outputs = (output_matrix * scale + minimum).astype(np.float32)
    if scaler.get("clip", True):
        outputs = np.clip(outputs, minimum, maximum)
    return outputs.astype(np.float32)
