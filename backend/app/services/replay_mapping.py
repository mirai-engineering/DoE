import csv
import os
from pathlib import Path
from typing import Any

import numpy as np

from ..schemas import ReplayInitializationSelection, ReplayMatch
from .experiment_log import load_experiment_log
from .preprocessing import input_names, output_names
from .project_registry import BACKEND_ROOT, get_project_schema


def _replay_dir() -> Path:
    return Path(os.getenv("DOE_REPLAY_DIR", BACKEND_ROOT / "data" / "replay"))


def _synthetic_source_path(project_id: str) -> Path:
    return BACKEND_ROOT / "data" / "synthetic" / f"{project_id}.csv"


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Replay dataset not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _fallback_rows(project_id: str, *, initial: bool) -> list[dict[str, str]]:
    rows = _load_csv_rows(_synthetic_source_path(project_id))
    start = 0 if initial else 25
    stop = 25 if initial else 225
    prefix = "initial" if initial else "hidden"
    selected: list[dict[str, str]] = []
    for index, row in enumerate(rows[start:stop], start=1):
        selected.append({"replay_id": f"{prefix}_{index:03d}", **row})
    return selected


def _load_replay_rows(project_id: str, suffix: str) -> list[dict[str, str]]:
    path = _replay_dir() / f"{project_id}_{suffix}.csv"
    if path.exists():
        return _load_csv_rows(path)
    if not _synthetic_source_path(project_id).exists():
        raise FileNotFoundError(f"Replay dataset not found: {path}")
    return _fallback_rows(project_id, initial=suffix == "initial_observed")


def _numeric_row(row: dict[str, str], schema: dict) -> dict[str, Any]:
    names = input_names(schema) + output_names(schema)
    missing = [name for name in names if name not in row or row[name] == ""]
    if missing:
        raise ValueError(f"Replay row is missing required columns: {', '.join(missing)}")
    return {
        "replay_id": row.get("replay_id") or row.get("experiment_id") or "",
        "inputs": {name: float(row[name]) for name in input_names(schema)},
        "outputs": {name: float(row[name]) for name in output_names(schema)},
    }


def load_initial_observed(project_id: str) -> list[dict[str, Any]]:
    schema = get_project_schema(project_id)
    return [_numeric_row(row, schema) for row in _load_replay_rows(project_id, "initial_observed")]


def load_hidden_replay_pool(project_id: str) -> list[dict[str, Any]]:
    schema = get_project_schema(project_id)
    return [_numeric_row(row, schema) for row in _load_replay_rows(project_id, "hidden_pool")]


def get_used_replay_ids(project_id: str) -> set[str]:
    used: set[str] = set()
    for experiment in load_experiment_log(project_id):
        replay_id = experiment.metadata.get("matched_replay_id")
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
        raise ValueError(f"Only {len(rows)} initial replay rows are available")

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
        raise ValueError("No unused hidden replay experiments remain")

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
