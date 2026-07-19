import csv
from pathlib import Path
from typing import Any

import numpy as np

from ...schemas import ReplayInitializationSelection, ReplayMatch
from ..data_preprocessing.ingestion_sessions import list_ingestion_sessions, session_workspace
from .experiment_log import load_experiment_log
from ..model_serving.preprocessing import input_names, output_names
from ..platform.project_registry import REAL_FUEL_CELL_PROJECT_ID, REAL_REFERENCE_ARTIFACT_DIR, get_project_schema


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Training split table not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _latest_ingestion_workspace(project_id: str) -> dict[str, Path] | None:
    sessions = [session for session in list_ingestion_sessions() if session.get("project_id") == project_id]
    if not sessions:
        return None
    latest = sorted(sessions, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)[0]
    return session_workspace(str(latest["project_id"]), str(latest["dataset_id"]), str(latest["ingestion_session_id"]))


def _training_split_table_path(project_id: str) -> Path:
    workspace = _latest_ingestion_workspace(project_id)
    if workspace is not None:
        canonical = workspace["canonical"] / "model_table.csv"
        if canonical.exists():
            return canonical
        training = workspace["training_latest"] / "model_table_preprocessed.csv"
        if training.exists():
            return training
    if project_id == REAL_FUEL_CELL_PROJECT_ID:
        return REAL_REFERENCE_ARTIFACT_DIR / "model_table_preprocessed.csv"
    raise FileNotFoundError(f"No train/validation split table is available for BO replay project_id={project_id}")


def _numeric_row(row: dict[str, str], schema: dict, *, index: int) -> dict[str, Any]:
    names = input_names(schema) + output_names(schema)
    missing = [name for name in names if name not in row or row[name] == ""]
    if missing:
        raise ValueError(f"Training split row is missing required columns: {', '.join(missing)}")
    replay_id = row.get("replay_id") or row.get("row_id") or f"{row.get('split', 'trainval')}_{index:06d}"
    return {
        "replay_id": replay_id,
        "source_split": row.get("split", "train_validation"),
        "inputs": {name: float(row[name]) for name in input_names(schema)},
        "outputs": {name: float(row[name]) for name in output_names(schema)},
    }


def _load_train_validation_rows(project_id: str) -> list[dict[str, Any]]:
    schema = get_project_schema(project_id)
    rows = _load_csv_rows(_training_split_table_path(project_id))
    train_validation = [row for row in rows if str(row.get("split", "")).lower() in {"train", "validation"}]
    if not train_validation:
        raise ValueError(f"No train/validation rows are available for BO replay project_id={project_id}")
    return [_numeric_row(row, schema, index=index) for index, row in enumerate(train_validation, start=1)]


def load_initial_observed(project_id: str) -> list[dict[str, Any]]:
    return [row for row in _load_train_validation_rows(project_id) if row.get("source_split") == "train"]


def load_hidden_replay_pool(project_id: str) -> list[dict[str, Any]]:
    return _load_train_validation_rows(project_id)


def get_used_replay_ids(project_id: str) -> set[str]:
    used: set[str] = set()
    for experiment in load_experiment_log(project_id):
        for key in ("matched_replay_id", "replay_id"):
            replay_id = experiment.metadata.get(key)
            if isinstance(replay_id, str) and replay_id:
                used.add(replay_id)
    return used


def _normalized_input_matrix(schema: dict, rows: list[dict[str, Any]]) -> np.ndarray:
    columns: list[np.ndarray] = []
    for variable in schema.get("inputs", []):
        name = variable["name"]
        minimum = float(variable["min"])
        maximum = float(variable["max"])
        scale = max(maximum - minimum, 1e-12)
        columns.append(np.asarray([(row["inputs"][name] - minimum) / scale for row in rows], dtype=np.float64))
    return np.vstack(columns).T


def _normalized_input_vector(schema: dict, inputs: dict[str, float]) -> np.ndarray:
    values: list[float] = []
    for variable in schema.get("inputs", []):
        name = variable["name"]
        minimum = float(variable["min"])
        maximum = float(variable["max"])
        scale = max(maximum - minimum, 1e-12)
        values.append((float(inputs[name]) - minimum) / scale)
    return np.asarray(values, dtype=np.float64)


def select_initial_observed(
    project_id: str,
    n_initial: int,
    selection: ReplayInitializationSelection,
) -> list[dict[str, Any]]:
    rows = load_initial_observed(project_id)
    if len(rows) < n_initial:
        raise ValueError(f"Only {len(rows)} initial train-split rows are available")

    if selection == ReplayInitializationSelection.first_n:
        return rows[:n_initial]

    rng = np.random.default_rng(42)
    if selection == ReplayInitializationSelection.random:
        indices = rng.choice(len(rows), size=n_initial, replace=False)
        return [rows[int(index)] for index in indices]

    schema = get_project_schema(project_id)
    matrix = _normalized_input_matrix(schema, rows)
    center = np.full(matrix.shape[1], 0.5, dtype=np.float64)
    first_index = int(np.argmin(np.linalg.norm(matrix - center, axis=1)))
    selected_indices = [first_index]
    remaining = set(range(len(rows))) - {first_index}

    while len(selected_indices) < n_initial:
        selected_matrix = matrix[selected_indices]
        best_index = max(
            remaining,
            key=lambda index: float(np.min(np.linalg.norm(selected_matrix - matrix[index], axis=1))),
        )
        selected_indices.append(int(best_index))
        remaining.remove(int(best_index))

    return [rows[index] for index in selected_indices]


def find_nearest_hidden_experiment(
    project_id: str,
    suggested_inputs: dict[str, float],
    used_replay_ids: set[str] | None = None,
) -> ReplayMatch:
    schema = get_project_schema(project_id)
    used = used_replay_ids or get_used_replay_ids(project_id)
    hidden_rows = [row for row in load_hidden_replay_pool(project_id) if str(row["replay_id"]) not in used]
    if not hidden_rows:
        raise ValueError("No unused train/validation replay experiments remain")

    x_star = _normalized_input_vector(schema, suggested_inputs)
    matrix = _normalized_input_matrix(schema, hidden_rows)
    distances = np.linalg.norm(matrix - x_star, axis=1)
    selected_index = int(np.argmin(distances))
    row = hidden_rows[selected_index]

    return ReplayMatch(
        replay_id=str(row["replay_id"]),
        matched_inputs={name: float(value) for name, value in row["inputs"].items()},
        observed_outputs={name: float(value) for name, value in row["outputs"].items()},
        distance=float(distances[selected_index]),
    )
