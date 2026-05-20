import json
import os
from pathlib import Path
from typing import Any

from ..schemas import BOConfig, LoggedExperiment
from .project_registry import BACKEND_ROOT, get_project_schema


def _object_store_root() -> Path:
    return Path(os.getenv("DOE_OBJECT_STORE_ROOT", BACKEND_ROOT / "data-minio"))


def _experiment_log_dir() -> Path:
    return Path(os.getenv("DOE_EXPERIMENT_LOG_DIR", _object_store_root() / "experiment_logs"))


def _bo_config_dir() -> Path:
    return Path(os.getenv("DOE_BO_CONFIG_DIR", _object_store_root() / "bo_configs"))


def _project_file_stem(project_id: str) -> str:
    schema = get_project_schema(project_id)
    return str(schema.get("project_id") or project_id)


def experiment_log_path(project_id: str) -> Path:
    return _experiment_log_dir() / f"{_project_file_stem(project_id)}.jsonl"


def bo_config_path(project_id: str) -> Path:
    return _bo_config_dir() / f"{_project_file_stem(project_id)}.json"


def load_experiment_log(project_id: str) -> list[LoggedExperiment]:
    path = experiment_log_path(project_id)
    if not path.exists():
        return []

    experiments: list[LoggedExperiment] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                experiments.append(LoggedExperiment.model_validate_json(line))
            except Exception as exc:  # noqa: BLE001 - include line number in the log corruption error.
                raise ValueError(f"Invalid experiment log row {line_number} in {path}") from exc
    return experiments


def write_experiment_log(project_id: str, experiments: list[LoggedExperiment]) -> None:
    path = experiment_log_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".jsonl.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        for experiment in experiments:
            file.write(experiment.model_dump_json(exclude_none=True))
            file.write("\n")
    temporary_path.replace(path)


def append_experiment(project_id: str, experiment: LoggedExperiment) -> LoggedExperiment:
    path = experiment_log_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(experiment.model_dump_json(exclude_none=True))
        file.write("\n")
    return experiment


def clear_experiment_log(project_id: str) -> None:
    path = experiment_log_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def update_experiment(project_id: str, experiment_id: str, patch: dict[str, Any]) -> LoggedExperiment:
    experiments = load_experiment_log(project_id)
    for index, experiment in enumerate(experiments):
        if experiment.experiment_id != experiment_id:
            continue
        payload = experiment.model_dump(mode="json")
        payload.update(patch)
        updated = LoggedExperiment.model_validate(payload)
        experiments[index] = updated
        write_experiment_log(project_id, experiments)
        return updated
    raise ValueError(f"Experiment not found: {experiment_id}")


def get_experiment(project_id: str, experiment_id: str) -> LoggedExperiment:
    for experiment in load_experiment_log(project_id):
        if experiment.experiment_id == experiment_id:
            return experiment
    raise ValueError(f"Experiment not found: {experiment_id}")


def load_saved_bo_config(project_id: str) -> BOConfig | None:
    path = bo_config_path(project_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return BOConfig.model_validate(json.load(file))


def save_bo_config(project_id: str, config: BOConfig) -> BOConfig:
    path = bo_config_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(config.model_dump(mode="json", exclude_none=True), file, indent=2)
    temporary_path.replace(path)
    return config
