from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .data_intake import ensure_session_workspace, get_ingestion_session, read_status, write_status
from .lifecycle_artifacts import persist_session_artifact_set, public_artifact_persistence_summary


CONTRACT_VERSION = "mirai-ml-preprocessing-v1"
FIT_SCOPE_TRAIN_ONLY = "train_split_only"

ALLOWED_TOOL_METHODS: dict[str, tuple[str, ...]] = {
    "impute_numeric": ("none", "mean", "median", "constant"),
    "minmax_scaler": ("minmax",),
    "standard_scaler": ("standard",),
    "robust_scaler": ("robust",),
    "log1p_feature": ("log1p",),
    "clip_numeric": ("clip",),
    "one_hot_encoder": ("one_hot",),
    "passthrough": ("none",),
    "drop_from_training": ("drop",),
    "target_transform": ("none", "standard", "minmax"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _ml_preprocessing_skill_reference() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[3] / "mirai-harness" / "MIRAI_MLPREPROCESSING_SKILL.md"
    if not path.exists():
        return {"path": "mirai-harness/MIRAI_MLPREPROCESSING_SKILL.md", "available": False}
    return {"path": "mirai-harness/MIRAI_MLPREPROCESSING_SKILL.md", "available": True, "sha256": _sha256_file(path), "bytes": path.stat().st_size}


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ToolName(str, Enum):
    impute_numeric = "impute_numeric"
    minmax_scaler = "minmax_scaler"
    standard_scaler = "standard_scaler"
    robust_scaler = "robust_scaler"
    log1p_feature = "log1p_feature"
    clip_numeric = "clip_numeric"
    one_hot_encoder = "one_hot_encoder"
    passthrough = "passthrough"
    drop_from_training = "drop_from_training"
    target_transform = "target_transform"


class ArtifactChecksum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    sha256: str | None = None
    required: bool = False


class PreprocessingToolAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variable_id: str = Field(min_length=1)
    role: Literal["input", "target", "output", "metadata"] = "input"
    tool: ToolName
    method: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    risk_level: RiskLevel = RiskLevel.low
    reversibility: Literal["reversible", "not_reversible", "not_applicable"] = "not_applicable"

    @field_validator("variable_id", "method")
    @classmethod
    def _reject_pathish_values(cls, value: str) -> str:
        lowered = value.lower()
        if any(token in lowered for token in ("/", "\\", "..", "s3://", "file://", "sql")):
            raise ValueError("path-like or scope-like values are not allowed in preprocessing specs")
        return value

    @model_validator(mode="after")
    def _validate_tool_method(self) -> "PreprocessingToolAction":
        allowed = ALLOWED_TOOL_METHODS.get(self.tool.value, ())
        if self.method not in allowed:
            raise ValueError(f"method {self.method!r} is not allowed for tool {self.tool.value!r}")
        if self.tool in {ToolName.minmax_scaler, ToolName.standard_scaler, ToolName.target_transform} and self.method != "none":
            if self.reversibility == "not_reversible":
                raise ValueError(f"{self.tool.value} with method {self.method!r} must be reversible")
        return self


class MLPreprocessingLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    ingestion_session_id: str = Field(min_length=1)
    artifact_checksums: list[ArtifactChecksum] = Field(default_factory=list)


class MLPreprocessingPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preprocessing_contract_version: Literal["mirai-ml-preprocessing-v1"] = CONTRACT_VERSION
    plan_id: str = Field(default_factory=lambda: f"plan_{uuid4().hex[:12]}")
    status: Literal["draft", "approved", "rejected"] = "draft"
    created_at: str = Field(default_factory=_now)
    approved_at: str | None = None
    approved_by: str | None = None
    fit_scope: Literal["train_split_only"] = FIT_SCOPE_TRAIN_ONLY
    lineage: MLPreprocessingLineage
    actions: list[PreprocessingToolAction]
    unresolved_questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_actions(self) -> "MLPreprocessingPlan":
        if not self.actions:
            raise ValueError("at least one preprocessing action is required")
        return self


class FittedParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variable_id: str
    tool: ToolName
    method: str
    fitted_on: Literal["train"] = "train"
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_columns: list[str] = Field(default_factory=list)


class MLPreprocessingFitted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preprocessing_contract_version: Literal["mirai-ml-preprocessing-v1"] = CONTRACT_VERSION
    run_id: str = Field(default_factory=lambda: f"run_{uuid4().hex[:12]}")
    plan_id: str
    created_at: str = Field(default_factory=_now)
    fit_scope: Literal["train_split_only"] = FIT_SCOPE_TRAIN_ONLY
    lineage: MLPreprocessingLineage
    fitted_parameters: list[FittedParameter]
    feature_columns: list[str] = Field(default_factory=list)
    target_columns: list[str] = Field(default_factory=list)


class MLPreprocessingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preprocessing_contract_version: Literal["mirai-ml-preprocessing-v1"] = CONTRACT_VERSION
    status: str
    summary: str
    plan_id: str | None = None
    run_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    export_files: list[str] = Field(default_factory=list)
    lineage: MLPreprocessingLineage


def _pd():
    import pandas as pd  # type: ignore[import-not-found]

    return pd


def _finite_numeric(series: Any) -> Any:
    pd = _pd()
    numeric = pd.to_numeric(series, errors="coerce").replace([float("inf"), float("-inf")], pd.NA)
    return numeric.dropna()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def fit_preprocessing_action(action: PreprocessingToolAction, train_frame: Any) -> FittedParameter:
    """Fit one deterministic preprocessing tool on train rows only.

    The caller is responsible for passing a frame already filtered to the train split.
    This function never inspects validation/test rows.
    """

    variable = action.variable_id
    if action.tool == ToolName.drop_from_training:
        return FittedParameter(variable_id=variable, tool=action.tool, method=action.method, parameters={}, output_columns=[])
    if variable not in train_frame.columns:
        raise ValueError(f"Unknown variable_id for preprocessing action: {variable}")
    series = train_frame[variable]
    numeric = _finite_numeric(series)
    if action.tool == ToolName.passthrough:
        return FittedParameter(variable_id=variable, tool=action.tool, method=action.method, parameters={}, output_columns=[variable])
    if action.tool == ToolName.impute_numeric:
        if action.method == "none":
            value = None
        elif action.method == "mean":
            value = _safe_float(numeric.mean()) if not numeric.empty else _safe_float(action.parameters.get("fallback", 0.0))
        elif action.method == "median":
            value = _safe_float(numeric.median()) if not numeric.empty else _safe_float(action.parameters.get("fallback", 0.0))
        elif action.method == "constant":
            value = _safe_float(action.parameters.get("value", 0.0))
        else:  # protected by schema, kept for direct callers
            raise ValueError(f"Unsupported impute_numeric method: {action.method}")
        return FittedParameter(variable_id=variable, tool=action.tool, method=action.method, parameters={"value": value}, output_columns=[variable])
    if action.tool == ToolName.minmax_scaler or (action.tool == ToolName.target_transform and action.method == "minmax"):
        minimum = _safe_float(numeric.min()) if not numeric.empty else 0.0
        maximum = _safe_float(numeric.max()) if not numeric.empty else minimum
        scale = maximum - minimum
        if not math.isfinite(scale) or scale == 0:
            scale = 1.0
        return FittedParameter(variable_id=variable, tool=action.tool, method=action.method, parameters={"min": minimum, "max": maximum, "scale": scale}, output_columns=[variable])
    if action.tool == ToolName.standard_scaler or (action.tool == ToolName.target_transform and action.method == "standard"):
        mean = _safe_float(numeric.mean()) if not numeric.empty else 0.0
        std = _safe_float(numeric.std(ddof=0), default=1.0) if not numeric.empty else 1.0
        if std == 0:
            std = 1.0
        return FittedParameter(variable_id=variable, tool=action.tool, method=action.method, parameters={"mean": mean, "std": std}, output_columns=[variable])
    if action.tool == ToolName.robust_scaler:
        median = _safe_float(numeric.median()) if not numeric.empty else 0.0
        q1 = _safe_float(numeric.quantile(0.25)) if not numeric.empty else median
        q3 = _safe_float(numeric.quantile(0.75)) if not numeric.empty else median
        iqr = q3 - q1
        if not math.isfinite(iqr) or iqr == 0:
            iqr = 1.0
        return FittedParameter(variable_id=variable, tool=action.tool, method=action.method, parameters={"median": median, "q1": q1, "q3": q3, "iqr": iqr}, output_columns=[variable])
    if action.tool == ToolName.log1p_feature:
        minimum = _safe_float(numeric.min()) if not numeric.empty else 0.0
        if minimum < 0:
            raise ValueError(f"log1p_feature requires non-negative train values for {variable}")
        return FittedParameter(variable_id=variable, tool=action.tool, method=action.method, parameters={"min": minimum}, output_columns=[variable])
    if action.tool == ToolName.clip_numeric:
        lower = action.parameters.get("lower")
        upper = action.parameters.get("upper")
        if lower is None and upper is None:
            lower = _safe_float(numeric.quantile(0.01)) if not numeric.empty else None
            upper = _safe_float(numeric.quantile(0.99)) if not numeric.empty else None
        return FittedParameter(variable_id=variable, tool=action.tool, method=action.method, parameters={"lower": lower, "upper": upper}, output_columns=[variable])
    if action.tool == ToolName.one_hot_encoder:
        max_categories = int(action.parameters.get("max_categories", 50))
        values = series.dropna().astype(str)
        categories = sorted(values.unique().tolist())[:max_categories]
        return FittedParameter(
            variable_id=variable,
            tool=action.tool,
            method=action.method,
            parameters={"categories": categories, "unknown_policy": action.parameters.get("unknown_policy", "all_zero")},
            output_columns=[f"{variable}__{category}" for category in categories],
        )
    if action.tool == ToolName.target_transform and action.method == "none":
        return FittedParameter(variable_id=variable, tool=action.tool, method=action.method, parameters={}, output_columns=[variable])
    raise ValueError(f"Unsupported preprocessing tool: {action.tool.value}/{action.method}")


def apply_fitted_parameter(frame: Any, fitted: FittedParameter) -> Any:
    """Apply one fitted deterministic preprocessing tool without fitting new state."""

    pd = _pd()
    variable = fitted.variable_id
    if fitted.tool == ToolName.drop_from_training:
        return pd.DataFrame(index=frame.index)
    if variable not in frame.columns:
        raise ValueError(f"Unknown variable_id for fitted preprocessing: {variable}")
    if fitted.tool == ToolName.one_hot_encoder:
        categories = [str(item) for item in fitted.parameters.get("categories", [])]
        values = frame[variable].astype(str)
        return pd.DataFrame({f"{variable}__{category}": (values == category).astype(float) for category in categories}, index=frame.index)
    series = pd.to_numeric(frame[variable], errors="coerce").astype(float)
    params = fitted.parameters
    if fitted.tool == ToolName.impute_numeric:
        value = params.get("value")
        transformed = series if value is None else series.fillna(float(value))
    elif fitted.tool == ToolName.minmax_scaler or (fitted.tool == ToolName.target_transform and fitted.method == "minmax"):
        transformed = (series - float(params.get("min", 0.0))) / float(params.get("scale", 1.0))
    elif fitted.tool == ToolName.standard_scaler or (fitted.tool == ToolName.target_transform and fitted.method == "standard"):
        transformed = (series - float(params.get("mean", 0.0))) / float(params.get("std", 1.0))
    elif fitted.tool == ToolName.robust_scaler:
        transformed = (series - float(params.get("median", 0.0))) / float(params.get("iqr", 1.0))
    elif fitted.tool == ToolName.log1p_feature:
        transformed = series.map(lambda value: math.log1p(value) if value >= 0 else float("nan"))
    elif fitted.tool == ToolName.clip_numeric:
        transformed = series.clip(lower=params.get("lower"), upper=params.get("upper"))
    elif fitted.tool in {ToolName.passthrough, ToolName.target_transform}:
        transformed = series
    else:
        raise ValueError(f"Unsupported fitted preprocessing tool: {fitted.tool.value}/{fitted.method}")
    return pd.DataFrame({fitted.output_columns[0] if fitted.output_columns else variable: transformed}, index=frame.index)


def inverse_transform_series(values: Any, fitted: FittedParameter) -> Any:
    """Reverse supported output transforms back to original target units."""

    pd = _pd()
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    params = fitted.parameters
    if fitted.tool == ToolName.target_transform and fitted.method == "minmax":
        return numeric * float(params.get("scale", 1.0)) + float(params.get("min", 0.0))
    if fitted.tool == ToolName.target_transform and fitted.method == "standard":
        return numeric * float(params.get("std", 1.0)) + float(params.get("mean", 0.0))
    if fitted.tool == ToolName.minmax_scaler:
        return numeric * float(params.get("scale", 1.0)) + float(params.get("min", 0.0))
    if fitted.tool == ToolName.standard_scaler:
        return numeric * float(params.get("std", 1.0)) + float(params.get("mean", 0.0))
    return numeric


def ml_preprocessing_workspace(project_id: str, dataset_id: str, session_id: str) -> dict[str, Path]:
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    root = workspace["root"] / "ml_preprocessing"
    paths = {
        "root": root,
        "plans_current": root / "plans" / "current",
        "runs_current": root / "runs" / "current",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def build_lineage(project_id: str, dataset_id: str, session_id: str) -> MLPreprocessingLineage:
    session = get_ingestion_session(project_id, dataset_id, session_id)
    workspace_id = str(session.get("workspace_id") or "unknown")
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    checksums = [
        ArtifactChecksum(name="canonical/model_table.csv", sha256=_sha256_file(workspace["canonical"] / "model_table.csv"), required=True),
        ArtifactChecksum(name="canonical/dataset_profile.json", sha256=_sha256_file(workspace["canonical"] / "dataset_profile.json"), required=False),
        ArtifactChecksum(name="preprocessing/schema.json", sha256=_sha256_file(workspace["training_latest"] / "schema.json"), required=False),
        ArtifactChecksum(name="preprocessing/split_report.json", sha256=_sha256_file(workspace["training_latest"] / "split_report.json"), required=False),
        ArtifactChecksum(name="preprocessing/eda_report.json", sha256=_sha256_file(workspace["training_latest"] / "eda_report.json"), required=False),
        ArtifactChecksum(name="eda/ydata_profile.json", sha256=_sha256_file(workspace["eda"] / "ydata_profile.json"), required=False),
    ]
    return MLPreprocessingLineage(
        workspace_id=workspace_id,
        project_id=project_id,
        dataset_id=dataset_id,
        ingestion_session_id=session_id,
        artifact_checksums=checksums,
    )


def write_schema_artifacts(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    """Write JSON schema artifacts for the v1 contract into the scoped session.

    This is intentionally deterministic and contains no project-specific decisions.
    """

    paths = ml_preprocessing_workspace(project_id, dataset_id, session_id)
    _write_json(paths["plans_current"] / "ml_preprocessing_plan.schema.json", MLPreprocessingPlan.model_json_schema())
    _write_json(paths["runs_current"] / "ml_preprocessing_fitted.schema.json", MLPreprocessingFitted.model_json_schema())
    _write_json(paths["runs_current"] / "ml_preprocessing_report.schema.json", MLPreprocessingReport.model_json_schema())
    status = write_status(
        project_id,
        dataset_id,
        session_id,
        "ml_preprocessing",
        {
            "status": "ml_preprocessing_contract_defined",
            "preprocessing_contract_version": CONTRACT_VERSION,
            "fit_scope": FIT_SCOPE_TRAIN_ONLY,
        },
    )
    return {"status": status.get("status"), "paths": ["ml_preprocessing/plans/current", "ml_preprocessing/runs/current"]}


def persist_ml_preprocessing_artifacts(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    session = get_ingestion_session(project_id, dataset_id, session_id)
    workspace_id = str(session.get("workspace_id") or "")
    paths = ml_preprocessing_workspace(project_id, dataset_id, session_id)
    result = persist_session_artifact_set(
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        workspace_id=workspace_id,
        artifact_set="ml_preprocessing",
        local_dir_or_files=paths["root"],
        write_latest_pointer=False,
    )
    return public_artifact_persistence_summary(result)


def get_ml_preprocessing_status(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    status = read_status(project_id, dataset_id, session_id, "ml_preprocessing", default={}) or {}
    if "object_storage" in status:
        status["object_storage"] = public_artifact_persistence_summary(status["object_storage"])
    return status


def _read_json_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _schema_path(workspace: dict[str, Path]) -> Path:
    for candidate in (workspace["training_latest"] / "schema.json", workspace["root"] / "preprocessing" / "schema.json"):
        if candidate.exists():
            return candidate
    return workspace["training_latest"] / "schema.json"


def get_dataset_contract(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    schema = _read_json_file(_schema_path(workspace), default={}) or {}
    inputs = schema.get("inputs") or []
    outputs = schema.get("outputs") or []
    variables = []
    for role, items in (("input", inputs), ("output", outputs)):
        for item in items:
            if not isinstance(item, dict):
                continue
            variables.append(
                {
                    "variable_id": item.get("variable_id") or item.get("name"),
                    "name": item.get("name"),
                    "role": item.get("role") or role,
                    "dtype": item.get("dtype") or item.get("type"),
                    "unit": item.get("unit"),
                    "min": item.get("min"),
                    "max": item.get("max"),
                    "direction": item.get("direction"),
                }
            )
    return {
        "schema_version": schema.get("schema_version"),
        "project_id": project_id,
        "dataset_id": dataset_id,
        "ingestion_session_id": session_id,
        "input_count": len(inputs),
        "output_count": len(outputs),
        "variables": variables,
    }


def get_active_model_table_summary(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    pd = _pd()
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    path = workspace["canonical"] / "model_table.csv"
    if not path.exists():
        return {"available": False, "row_count": 0, "columns": [], "sha256": None}
    df = pd.read_csv(path)
    split_counts = df["split"].value_counts(dropna=False).to_dict() if "split" in df.columns else {}
    return {
        "available": True,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": [str(col) for col in df.columns],
        "split_counts": {str(k): int(v) for k, v in split_counts.items()},
        "sha256": _sha256_file(path),
    }


def get_preprocessing_readiness(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    table = get_active_model_table_summary(project_id, dataset_id, session_id)
    contract = get_dataset_contract(project_id, dataset_id, session_id)
    ready = bool(table.get("available") and table.get("row_count", 0) > 0 and contract.get("input_count", 0) > 0)
    reasons = []
    if not table.get("available"):
        reasons.append("canonical/model_table.csv is missing")
    if contract.get("input_count", 0) <= 0:
        reasons.append("schema inputs are missing")
    if "train" not in table.get("split_counts", {}):
        reasons.append("train split is missing; executor requires split == train for fitting")
        ready = False
    return {"ready": ready, "reasons": reasons, "model_table": table, "contract": contract}


def _column_stats(project_id: str, dataset_id: str, session_id: str, column_name: str) -> dict[str, Any]:
    pd = _pd()
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    path = workspace["canonical"] / "model_table.csv"
    if not path.exists():
        return {"available": False, "column": column_name}
    df = pd.read_csv(path)
    if column_name not in df.columns:
        return {"available": False, "column": column_name, "reason": "unknown_column"}
    series = df[column_name]
    result: dict[str, Any] = {
        "available": True,
        "column": column_name,
        "dtype": str(series.dtype),
        "missing_count": int(series.isna().sum()),
        "missing_rate": float(series.isna().mean()) if len(series) else 0.0,
        "unique_count": int(series.nunique(dropna=True)),
    }
    numeric = _finite_numeric(series)
    if not numeric.empty:
        result.update(
            {
                "numeric": True,
                "min": _safe_float(numeric.min()),
                "max": _safe_float(numeric.max()),
                "mean": _safe_float(numeric.mean()),
                "median": _safe_float(numeric.median()),
                "std": _safe_float(numeric.std(ddof=0)),
                "q1": _safe_float(numeric.quantile(0.25)),
                "q3": _safe_float(numeric.quantile(0.75)),
                "skew": _safe_float(numeric.skew(), default=0.0),
                "non_negative": bool((numeric >= 0).all()),
            }
        )
    else:
        top = series.dropna().astype(str).value_counts().head(20).to_dict()
        result.update({"numeric": False, "top_values": {str(k): int(v) for k, v in top.items()}})
    return result


def get_column_profile(project_id: str, dataset_id: str, session_id: str, column_name: str) -> dict[str, Any]:
    return _column_stats(project_id, dataset_id, session_id, column_name)


def get_missingness_report(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    table = get_active_model_table_summary(project_id, dataset_id, session_id)
    columns = table.get("columns", [])
    return {"columns": [{"column": col, **{k: v for k, v in _column_stats(project_id, dataset_id, session_id, col).items() if k in {"missing_count", "missing_rate"}}} for col in columns]}


def get_distribution_summary(project_id: str, dataset_id: str, session_id: str, column_name: str) -> dict[str, Any]:
    profile = _column_stats(project_id, dataset_id, session_id, column_name)
    keys = ["column", "numeric", "min", "max", "mean", "median", "std", "q1", "q3", "skew", "non_negative"]
    return {key: profile.get(key) for key in keys if key in profile}


def get_outlier_summary(project_id: str, dataset_id: str, session_id: str, column_name: str) -> dict[str, Any]:
    pd = _pd()
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    path = workspace["canonical"] / "model_table.csv"
    if not path.exists():
        return {"available": False, "column": column_name}
    df = pd.read_csv(path)
    if column_name not in df.columns:
        return {"available": False, "column": column_name}
    numeric = _finite_numeric(df[column_name])
    if numeric.empty:
        return {"available": True, "column": column_name, "numeric": False}
    q1 = _safe_float(numeric.quantile(0.25)); q3 = _safe_float(numeric.quantile(0.75)); iqr = q3 - q1
    lower = q1 - 1.5 * iqr; upper = q3 + 1.5 * iqr
    count = int(((numeric < lower) | (numeric > upper)).sum())
    return {"available": True, "column": column_name, "numeric": True, "iqr": iqr, "lower_fence": lower, "upper_fence": upper, "outlier_count": count, "outlier_rate": float(count / len(numeric)) if len(numeric) else 0.0}


def get_correlation_summary(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    pd = _pd()
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    path = workspace["canonical"] / "model_table.csv"
    if not path.exists():
        return {"available": False, "pairs": []}
    df = pd.read_csv(path)
    numeric = df.select_dtypes(include="number")
    pairs = []
    if len(numeric.columns) >= 2:
        corr = numeric.corr(numeric_only=True).abs()
        for i, left in enumerate(corr.columns):
            for right in corr.columns[i + 1 :]:
                value = corr.loc[left, right]
                if pd.notna(value) and float(value) >= 0.9:
                    pairs.append({"left": str(left), "right": str(right), "abs_correlation": float(value)})
    return {"available": True, "high_correlation_pairs": pairs[:50]}


def get_categorical_cardinality_summary(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    pd = _pd()
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    path = workspace["canonical"] / "model_table.csv"
    if not path.exists():
        return {"available": False, "columns": []}
    df = pd.read_csv(path)
    columns = []
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            columns.append({"column": str(col), "unique_count": int(df[col].nunique(dropna=True)), "missing_rate": float(df[col].isna().mean())})
    return {"available": True, "columns": columns}


def get_duplicate_summary(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    pd = _pd()
    path = ensure_session_workspace(project_id, dataset_id, session_id)["canonical"] / "model_table.csv"
    if not path.exists():
        return {"available": False}
    df = pd.read_csv(path)
    duplicate_count = int(df.duplicated().sum())
    return {"available": True, "duplicate_count": duplicate_count, "duplicate_rate": float(duplicate_count / len(df)) if len(df) else 0.0}


def get_split_and_leakage_context(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    table = get_active_model_table_summary(project_id, dataset_id, session_id)
    suspicious = [col for col in table.get("columns", []) if any(token in col.lower() for token in ("target", "label", "outcome", "future", "post"))]
    return {"split_counts": table.get("split_counts", {}), "fit_scope": FIT_SCOPE_TRAIN_ONLY, "suspicious_columns": suspicious[:50]}


def get_existing_preprocessing_status(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    from .preprocessing_review import get_public_preprocessing_status

    return get_public_preprocessing_status(project_id, dataset_id, session_id)


def get_training_context(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    status = read_status(project_id, dataset_id, session_id, "training", default={}) or {}
    return {"training_status": status.get("status"), "ml_preprocessing_required": True}


def get_eda_overview(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    from .preprocessing_review import get_preprocessing_eda_summary, get_preprocessing_review_report

    try:
        summary = get_preprocessing_eda_summary(project_id, dataset_id, session_id)
    except Exception:
        summary = {}
    try:
        report = get_preprocessing_review_report(project_id, dataset_id, session_id)
    except Exception:
        report = {}
    return {
        "eda_summary_available": bool(summary),
        "report_available": bool(report),
        "summary_keys": sorted(summary.keys())[:50] if isinstance(summary, dict) else [],
        "report_keys": sorted(report.keys())[:50] if isinstance(report, dict) else [],
        "bounded_summary": summary if isinstance(summary, dict) else {},
    }


def get_ydata_profile_summary(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    profile = _read_json_file(workspace["eda"] / "ydata_profile.json", default=None)
    if not isinstance(profile, dict):
        return {"available": False, "fallback": "eda_report_or_dataset_profile"}
    variables = profile.get("variables") if isinstance(profile.get("variables"), dict) else {}
    return {"available": True, "variable_count": len(variables), "variables": list(variables.keys())[:100], "alerts_count": len(profile.get("alerts") or [])}


def collect_ml_preprocessing_evidence(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    readiness = get_preprocessing_readiness(project_id, dataset_id, session_id)
    contract = readiness.get("contract", {})
    variables = [item.get("variable_id") for item in contract.get("variables", []) if item.get("variable_id")]
    profiles = {name: get_column_profile(project_id, dataset_id, session_id, str(name)) for name in variables[:100]}
    return {
        "readiness": readiness,
        "eda_overview": get_eda_overview(project_id, dataset_id, session_id),
        "ydata_profile": get_ydata_profile_summary(project_id, dataset_id, session_id),
        "missingness": get_missingness_report(project_id, dataset_id, session_id),
        "correlations": get_correlation_summary(project_id, dataset_id, session_id),
        "categorical_cardinality": get_categorical_cardinality_summary(project_id, dataset_id, session_id),
        "duplicates": get_duplicate_summary(project_id, dataset_id, session_id),
        "split_and_leakage": get_split_and_leakage_context(project_id, dataset_id, session_id),
        "column_profiles": profiles,
    }


def _safe_variable_ids(project_id: str, dataset_id: str, session_id: str) -> set[str]:
    contract = get_dataset_contract(project_id, dataset_id, session_id)
    return {str(item.get("variable_id")) for item in contract.get("variables", []) if item.get("variable_id")} | {"split"}


def validate_ml_preprocessing_plan(plan: MLPreprocessingPlan, project_id: str, dataset_id: str, session_id: str) -> list[str]:
    errors: list[str] = []
    expected = build_lineage(project_id, dataset_id, session_id)
    if plan.lineage.workspace_id != expected.workspace_id or plan.lineage.project_id != project_id or plan.lineage.dataset_id != dataset_id or plan.lineage.ingestion_session_id != session_id:
        errors.append("plan lineage does not match selected workspace/project/dataset/session")
    allowed_variables = _safe_variable_ids(project_id, dataset_id, session_id)
    for action in plan.actions:
        if action.variable_id not in allowed_variables:
            errors.append(f"unknown variable_id in plan: {action.variable_id}")
        payload = action.model_dump()
        encoded = json.dumps(payload, default=str).lower()
        if any(token in encoded for token in ("s3://", "file://", "..", "select ", "insert ", "delete ", "drop table")):
            errors.append(f"unsafe path/sql-like content in action for {action.variable_id}")
    if plan.fit_scope != FIT_SCOPE_TRAIN_ONLY:
        errors.append("plan fit_scope must be train_split_only")
    current = {item.name: item.sha256 for item in expected.artifact_checksums}
    planned = {item.name: item.sha256 for item in plan.lineage.artifact_checksums}
    for name, sha in planned.items():
        if sha and current.get(name) and sha != current.get(name):
            errors.append(f"stale artifact checksum for {name}")
    return errors


def _default_actions_from_evidence(project_id: str, dataset_id: str, session_id: str, evidence: dict[str, Any]) -> list[PreprocessingToolAction]:
    contract = get_dataset_contract(project_id, dataset_id, session_id)
    profiles = evidence.get("column_profiles", {}) if isinstance(evidence, dict) else {}
    actions: list[PreprocessingToolAction] = []
    for variable in contract.get("variables", []):
        variable_id = str(variable.get("variable_id") or "")
        role = str(variable.get("role") or "input")
        if not variable_id or role in {"id", "group", "time", "metadata", "ignore"}:
            continue
        profile = profiles.get(variable_id, {}) if isinstance(profiles, dict) else {}
        is_output = role == "output"
        if profile.get("numeric") is False:
            if int(profile.get("unique_count") or 0) <= 25 and not is_output:
                actions.append(PreprocessingToolAction(variable_id=variable_id, role="input", tool=ToolName.one_hot_encoder, method="one_hot", parameters={"max_categories": 25, "unknown_policy": "all_zero"}, evidence_refs=[f"column_profile:{variable_id}"], reason="Low-cardinality categorical input can be one-hot encoded with train-only vocabulary.", risk_level=RiskLevel.low))
            else:
                actions.append(PreprocessingToolAction(variable_id=variable_id, role="input" if not is_output else "output", tool=ToolName.drop_from_training, method="drop", evidence_refs=[f"column_profile:{variable_id}"], reason="Non-numeric high-cardinality or output-like column is excluded in MVP preprocessing pending user guidance.", risk_level=RiskLevel.medium))
            continue
        if is_output:
            actions.append(PreprocessingToolAction(variable_id=variable_id, role="output", tool=ToolName.target_transform, method="none", evidence_refs=[f"column_profile:{variable_id}"], reason="Target remains in original units by default for v1 unless model evidence justifies reversible scaling.", risk_level=RiskLevel.low, reversibility="reversible"))
            continue
        missing_rate = float(profile.get("missing_rate") or 0.0)
        if missing_rate > 0:
            actions.append(PreprocessingToolAction(variable_id=variable_id, role="input", tool=ToolName.impute_numeric, method="median", evidence_refs=[f"missingness:{variable_id}"], reason="Numeric input has missing values; median imputation is robust and fitted on train split only.", risk_level=RiskLevel.medium if missing_rate > 0.2 else RiskLevel.low))
        skew = abs(float(profile.get("skew") or 0.0))
        if skew > 2.0 and profile.get("non_negative"):
            actions.append(PreprocessingToolAction(variable_id=variable_id, role="input", tool=ToolName.log1p_feature, method="log1p", evidence_refs=[f"distribution:{variable_id}"], reason="EDA indicates strong positive skew and non-negative support; log1p is deterministic and support-safe.", risk_level=RiskLevel.medium, reversibility="not_reversible"))
        actions.append(PreprocessingToolAction(variable_id=variable_id, role="input", tool=ToolName.minmax_scaler, method="minmax", evidence_refs=[f"column_profile:{variable_id}"], reason="Default numeric MVP scaling maps train-range inputs to a bounded scale without using validation/test statistics.", risk_level=RiskLevel.low, reversibility="reversible"))
    if not actions:
        actions.append(PreprocessingToolAction(variable_id="split", role="metadata", tool=ToolName.passthrough, method="none", evidence_refs=["readiness"], reason="No contract variables found; placeholder action keeps the draft invalid for training until schema is fixed.", risk_level=RiskLevel.high))
    return actions


def start_ml_preprocessing(project_id: str, dataset_id: str, session_id: str, requested_by: str = "system") -> dict[str, Any]:
    evidence = collect_ml_preprocessing_evidence(project_id, dataset_id, session_id)
    if not evidence.get("readiness", {}).get("ready"):
        write_status(project_id, dataset_id, session_id, "ml_preprocessing", {"status": "ml_preprocessing_not_ready", "reasons": evidence.get("readiness", {}).get("reasons", [])})
        return get_ml_preprocessing_status(project_id, dataset_id, session_id)
    lineage = build_lineage(project_id, dataset_id, session_id)
    plan = MLPreprocessingPlan(lineage=lineage, actions=_default_actions_from_evidence(project_id, dataset_id, session_id, evidence), warnings=evidence.get("readiness", {}).get("reasons", []))
    errors = validate_ml_preprocessing_plan(plan, project_id, dataset_id, session_id)
    paths = ml_preprocessing_workspace(project_id, dataset_id, session_id)
    _write_json(paths["plans_current"] / "preprocessing_plan.json", plan.model_dump(mode="json"))
    skill_ref = _ml_preprocessing_skill_reference()
    report = MLPreprocessingReport(status="preprocessing_plan_needs_approval" if not errors else "preprocessing_plan_needs_input", summary=f"Draft ML preprocessing plan created with {len(plan.actions)} deterministic tool actions. Approval is required before writing model_table_preprocessed.csv.", plan_id=plan.plan_id, evidence_refs=["readiness", "eda_overview", "column_profiles", f"skill:{skill_ref.get('sha256', 'unavailable')}"], risks=errors, warnings=plan.warnings + ([] if skill_ref.get("available") else ["ML preprocessing skill file was not found while drafting the deterministic plan."]), lineage=lineage)
    _write_json(paths["plans_current"] / "preprocessing_plan_report.json", report.model_dump(mode="json"))
    persistence = persist_ml_preprocessing_artifacts(project_id, dataset_id, session_id)
    write_status(project_id, dataset_id, session_id, "ml_preprocessing", {"status": report.status, "plan_id": plan.plan_id, "action_count": len(plan.actions), "requested_by": requested_by, "object_storage": persistence})
    return get_ml_preprocessing_status(project_id, dataset_id, session_id)


def load_ml_preprocessing_plan(project_id: str, dataset_id: str, session_id: str) -> MLPreprocessingPlan:
    path = ml_preprocessing_workspace(project_id, dataset_id, session_id)["plans_current"] / "preprocessing_plan.json"
    payload = _read_json_file(path, default=None)
    if not isinstance(payload, dict):
        raise ValueError("No ML preprocessing plan has been generated for this session")
    return MLPreprocessingPlan.model_validate(payload)


def approve_ml_preprocessing_plan(project_id: str, dataset_id: str, session_id: str, approver: str, notes: str | None = None) -> dict[str, Any]:
    plan = load_ml_preprocessing_plan(project_id, dataset_id, session_id)
    errors = validate_ml_preprocessing_plan(plan, project_id, dataset_id, session_id)
    if errors:
        raise ValueError("ML preprocessing plan cannot be approved: " + "; ".join(errors))
    plan.status = "approved"
    plan.approved_at = _now()
    plan.approved_by = approver
    paths = ml_preprocessing_workspace(project_id, dataset_id, session_id)
    _write_json(paths["plans_current"] / "preprocessing_plan.json", plan.model_dump(mode="json"))
    report = MLPreprocessingReport(status="ml_preprocessing_plan_approved", summary="ML preprocessing plan approved. The executor can now create model_table_preprocessed.csv for training.", plan_id=plan.plan_id, evidence_refs=["approved_plan"], warnings=plan.warnings + ([notes] if notes else []), lineage=plan.lineage)
    _write_json(paths["plans_current"] / "preprocessing_plan_report.json", report.model_dump(mode="json"))
    persistence = persist_ml_preprocessing_artifacts(project_id, dataset_id, session_id)
    write_status(project_id, dataset_id, session_id, "ml_preprocessing", {"status": "ml_preprocessing_plan_approved", "plan_id": plan.plan_id, "approved_by": approver, "approved_at": plan.approved_at, "object_storage": persistence})
    return get_ml_preprocessing_status(project_id, dataset_id, session_id)


def _apply_actions_sequential(frame: Any, fitted_parameters: list[FittedParameter]) -> Any:
    pd = _pd()
    output = pd.DataFrame(index=frame.index)
    working = frame.copy()
    for fitted in fitted_parameters:
        transformed = apply_fitted_parameter(working, fitted)
        if transformed.empty:
            if fitted.variable_id in working.columns:
                working = working.drop(columns=[fitted.variable_id])
            continue
        for col in transformed.columns:
            working[col] = transformed[col]
            output[col] = transformed[col]
    return output


def execute_ml_preprocessing(project_id: str, dataset_id: str, session_id: str, run_by: str = "system") -> dict[str, Any]:
    pd = _pd()
    plan = load_ml_preprocessing_plan(project_id, dataset_id, session_id)
    if plan.status != "approved":
        raise ValueError("ML preprocessing plan must be approved before execution")
    errors = validate_ml_preprocessing_plan(plan, project_id, dataset_id, session_id)
    if errors:
        raise ValueError("ML preprocessing plan failed validation: " + "; ".join(errors))
    workspace = ensure_session_workspace(project_id, dataset_id, session_id)
    source = workspace["canonical"] / "model_table.csv"
    if not source.exists():
        raise ValueError("canonical/model_table.csv is missing")
    df = pd.read_csv(source)
    if "split" not in df.columns:
        raise ValueError("model_table.csv must include split column")
    train = df[df["split"].astype(str) == "train"].copy()
    if train.empty:
        raise ValueError("train split is empty; cannot fit preprocessing")
    fitted_parameters: list[FittedParameter] = []
    train_working = train.copy()
    for action in plan.actions:
        fitted = fit_preprocessing_action(action, train_working)
        fitted_parameters.append(fitted)
        transformed_train = apply_fitted_parameter(train_working, fitted)
        for col in transformed_train.columns:
            train_working[col] = transformed_train[col]
    transformed_parts = []
    for split_name, split_frame in df.groupby(df["split"].astype(str), sort=False):
        transformed = _apply_actions_sequential(split_frame.copy(), fitted_parameters)
        transformed.insert(0, "split", split_name)
        if "cell_id" in split_frame.columns:
            transformed.insert(0, "cell_id", split_frame["cell_id"].values)
        transformed_parts.append(transformed)
    preprocessed = pd.concat(transformed_parts, axis=0).sort_index()
    paths = ml_preprocessing_workspace(project_id, dataset_id, session_id)
    output_path = paths["runs_current"] / "model_table_preprocessed.csv"
    preprocessed.to_csv(output_path, index=False)
    target_columns = [action.variable_id for action in plan.actions if action.role in {"target", "output"}]
    feature_columns = [col for col in preprocessed.columns if col not in {"split", "cell_id", *target_columns}]
    fitted = MLPreprocessingFitted(plan_id=plan.plan_id, lineage=plan.lineage, fitted_parameters=fitted_parameters, feature_columns=feature_columns, target_columns=target_columns)
    _write_json(paths["runs_current"] / "preprocessing_fitted.json", fitted.model_dump(mode="json"))
    _write_json(paths["runs_current"] / "feature_map.json", {"feature_columns": feature_columns, "source": "model_table_preprocessed.csv"})
    _write_json(paths["runs_current"] / "target_map.json", {"target_columns": target_columns})
    manifest = {"status": "available", "run_id": fitted.run_id, "plan_id": plan.plan_id, "row_count": int(len(preprocessed)), "column_count": int(len(preprocessed.columns)), "sha256": _sha256_file(output_path), "source_model_table_sha256": _sha256_file(source), "fit_scope": FIT_SCOPE_TRAIN_ONLY}
    _write_json(paths["runs_current"] / "model_table_preprocessed_manifest.json", manifest)
    report = MLPreprocessingReport(status="ml_preprocessing_ready_for_training", summary=f"Preprocessing ready — generated model_table_preprocessed.csv with {len(preprocessed)} rows and {len(feature_columns)} model columns using {len(fitted_parameters)} fitted deterministic tool steps. Canonical model_table.csv was not modified.", plan_id=plan.plan_id, run_id=fitted.run_id, evidence_refs=["approved_plan", "train_split_only_fit"], export_files=["model_table_preprocessed.csv", "preprocessing_fitted.json", "feature_map.json", "target_map.json", "model_table_preprocessed_manifest.json"], lineage=plan.lineage)
    _write_json(paths["runs_current"] / "ml_preprocessing_report.json", report.model_dump(mode="json"))
    persistence = persist_ml_preprocessing_artifacts(project_id, dataset_id, session_id)
    write_status(project_id, dataset_id, session_id, "ml_preprocessing", {"status": "ml_preprocessing_ready_for_training", "plan_id": plan.plan_id, "run_id": fitted.run_id, "run_by": run_by, "summary": report.summary, "exports": report.export_files, "model_table_preprocessed": {"available": True, "sha256": manifest["sha256"]}, "object_storage": persistence})
    return get_ml_preprocessing_status(project_id, dataset_id, session_id)


def get_ml_preprocessing_report(project_id: str, dataset_id: str, session_id: str) -> dict[str, Any]:
    paths = ml_preprocessing_workspace(project_id, dataset_id, session_id)
    for path in (paths["runs_current"] / "ml_preprocessing_report.json", paths["plans_current"] / "preprocessing_plan_report.json"):
        payload = _read_json_file(path, default=None)
        if isinstance(payload, dict):
            return payload
    return {"status": "missing", "summary": "No ML preprocessing report is available yet."}


def get_ml_preprocessed_table_path(project_id: str, dataset_id: str, session_id: str) -> Path:
    path = ml_preprocessing_workspace(project_id, dataset_id, session_id)["runs_current"] / "model_table_preprocessed.csv"
    if not path.exists():
        raise ValueError("model_table_preprocessed.csv is not available; run ML preprocessing first")
    return path
