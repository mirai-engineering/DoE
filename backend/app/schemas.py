from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExperimentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, float]


class PredictRequest(ExperimentInput):
    pass


class PredictResponse(BaseModel):
    project_id: str
    predictions: dict[str, float]
    model_version: str
    warnings: list[str] = Field(default_factory=list)


class BatchPredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: list[dict[str, float]]

    @field_validator("inputs")
    @classmethod
    def inputs_must_not_be_empty(cls, value: list[dict[str, float]]) -> list[dict[str, float]]:
        if not value:
            raise ValueError("inputs must contain at least one experiment row")
        return value


class BatchPredictResponse(BaseModel):
    project_id: str
    predictions: list[dict[str, float]]
    model_version: str
    warnings: list[str] = Field(default_factory=list)


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_weights: dict[str, float]
    fixed_inputs: dict[str, float] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    n_candidates: int = Field(default=2000, ge=1, le=100_000)
    top_k: int = Field(default=5, ge=1, le=100)
    random_seed: int | None = Field(default=13)

    @field_validator("objective_weights")
    @classmethod
    def objective_weights_must_not_be_empty(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("objective_weights must contain at least one output weight")
        return value


class RecommendedExperiment(BaseModel):
    inputs: dict[str, float]
    predictions: dict[str, float]
    score: float


class RecommendResponse(BaseModel):
    project_id: str
    recommendations: list[RecommendedExperiment]
    model_version: str
    warnings: list[str] = Field(default_factory=list)
