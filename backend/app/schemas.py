from typing import Any
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExperimentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, float]


class PredictRequest(ExperimentInput):
    pass


class IntakeFileInventoryItem(BaseModel):
    filename: str
    original_filename: str | None = None
    relative_path: str
    content_type: str
    size_bytes: int
    sha256: str
    suffix: str
    bucket: str | None = None
    object_key: str | None = None
    object_uri: str | None = None
    storage_provider: str | None = None


class WorkspaceStorageProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: str
    mode: str = "s3"
    prefix: str | None = None
    display_name: str | None = None
    clerk_user_id: str | None = None


class IngestionSessionResponse(BaseModel):
    project_id: str
    project_name: str
    workspace_id: str | None = None
    workspace_name: str | None = None
    dataset_id: str
    ingestion_session_id: str
    status: str
    approval_status: str
    created_at: str
    updated_at: str
    storage: dict[str, Any]
    files: list[IntakeFileInventoryItem]
    notes: str = ""
    ingestion_path: str = "generic_tabular_doe"
    mapping: dict[str, Any] = Field(default_factory=dict)
    manifest_assistant: dict[str, Any] = Field(default_factory=dict)


class FileInventoryResponse(BaseModel):
    files: list[IntakeFileInventoryItem]
    generated_at: str | None = None


class PreprocessingApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approver: str = "Mirai admin"
    notes: str | None = None


class DomainMetadataUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    domain_metadata: dict[str, Any]
    updated_by: str = "Mirai admin"
    notes: str | None = None


class DomainMetadataApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approver: str = "Mirai admin"
    notes: str | None = None


class LinearTrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_mvlr: bool = True
    fit_intercept: bool = True
    include_ridge: bool = True
    ridge_alphas: list[float] = Field(default_factory=lambda: [0.01, 0.1, 1.0, 10.0])


class MLPTrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include: bool = True
    architecture_family: str = "plain_mlp"
    hidden_layers: list[int] = Field(default_factory=lambda: [128, 64, 32])
    trunk_layers: list[int] = Field(default_factory=lambda: [128, 128])
    head_layers: list[int] = Field(default_factory=lambda: [64])
    secondary_head_layers: list[int] = Field(default_factory=lambda: [32])
    activation: str = "SiLU"
    normalization: str = "layer_norm"
    dropout: float = Field(default=0.05, ge=0.0, le=0.8)
    optimizer: str = "AdamW"
    learning_rate: float = Field(default=0.003, gt=0.0)
    weight_decay: float = Field(default=0.0001, ge=0.0)
    batch_size: int | str = "full_batch"
    max_epochs: int = Field(default=500, ge=1, le=1500)
    early_stopping_patience: int = Field(default=100, ge=1, le=500)
    loss: str = "smooth_l1"
    output_weights: dict[str, float] = Field(default_factory=dict)
    seeds: list[int] = Field(default_factory=lambda: [7])


class TrainingSearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = "single_config"
    wall_clock_budget_minutes: int = Field(default=60, ge=1, le=120)
    rerun_top_k: int = Field(default=0, ge=0, le=5)


class TrainingConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linear: LinearTrainingConfig = Field(default_factory=LinearTrainingConfig)
    mlp: MLPTrainingConfig = Field(default_factory=MLPTrainingConfig)
    search: TrainingSearchConfig = Field(default_factory=TrainingSearchConfig)
    selection_metric: str = "validation_weighted_normalized_rmse"


class TrainingRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_by: str = "Mirai admin"
    preset: str = "balanced_training"
    model_families: list[str] = Field(default_factory=lambda: ["mean_baseline", "mvlr", "ridge", "mlp"])
    training_config: TrainingConfiguration = Field(default_factory=TrainingConfiguration)
    notes: str | None = None


class ExternalMlflowRunImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mlflow_run_id: str = Field(min_length=1, max_length=128)
    registered_model_name: str | None = Field(default=None, max_length=256)
    model_version: str | None = Field(default=None, max_length=64)
    alias: str = Field(default="challenger", min_length=1, max_length=64)
    notes: str | None = Field(default=None, max_length=1000)


class ChampionReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=1000)


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


class ExperimentStatus(str, Enum):
    suggested = "suggested"
    accepted = "accepted"
    rejected = "rejected"
    skipped = "skipped"
    tested = "tested"
    observed = "observed"


class ExperimentSource(str, Enum):
    initial_observed = "initial_observed"
    bo_suggested = "bo_suggested"
    replay_revealed = "replay_revealed"
    manual_observed = "manual_observed"


class ReviewDecision(str, Enum):
    none = "none"
    accepted = "accepted"
    rejected = "rejected"
    skipped = "skipped"


class ReviewReason(str, Enum):
    infeasible = "infeasible"
    unsafe = "unsafe"
    too_expensive = "too_expensive"
    outside_protocol = "outside_protocol"
    chemically_implausible = "chemically_implausible"
    duplicate = "duplicate"
    other = "other"


class ExperimentReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision = ReviewDecision.none
    reason: ReviewReason | None = None
    notes: str | None = None


class LoggedExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    project_id: str
    iteration: int
    source: ExperimentSource
    status: ExperimentStatus
    inputs: dict[str, float]
    predicted_outputs: dict[str, float] | None = None
    observed_outputs: dict[str, float] | None = None
    uncertainty: dict[str, Any] | None = None
    objective: dict[str, float | None] | None = None
    review: ExperimentReview | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BOExplorationLevel(str, Enum):
    conservative = "conservative"
    balanced = "balanced"
    exploratory = "exploratory"


class BOAcquisitionFunction(str, Enum):
    ei = "ei"
    ucb = "ucb"


class InputConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float | None = None
    max: float | None = None
    fixed: float | None = None


class BOConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_weights: dict[str, float] = Field(default_factory=dict)
    strategy: BOExplorationLevel = BOExplorationLevel.balanced
    acquisition_function: BOAcquisitionFunction = BOAcquisitionFunction.ei
    exploration_level: BOExplorationLevel = BOExplorationLevel.balanced
    n_suggestions: int = Field(default=1, ge=1, le=5)
    input_constraints: dict[str, InputConstraint] = Field(default_factory=dict)
    forbidden_regions: list[dict[str, Any]] = Field(default_factory=list)
    random_seed: int = 42
    replay_mode: bool = True


class BOConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_weights: dict[str, float] | None = None
    strategy: BOExplorationLevel | None = None
    acquisition_function: BOAcquisitionFunction | None = None
    exploration_level: BOExplorationLevel | None = None
    n_suggestions: int | None = Field(default=None, ge=1, le=5)
    input_constraints: dict[str, InputConstraint] | None = None
    random_seed: int | None = None
    replay_mode: bool | None = None


class ReplayInitializationSelection(str, Enum):
    diverse = "diverse"
    random = "random"
    first_n = "first_n"


class BOInitializeReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reset: bool = True
    n_initial: int = Field(default=10, ge=1, le=100)
    selection: ReplayInitializationSelection = ReplayInitializationSelection.diverse


class BOReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    reason: ReviewReason | None = None
    notes: str | None = None


class ReplayMatch(BaseModel):
    replay_id: str
    matched_inputs: dict[str, float]
    observed_outputs: dict[str, float]
    distance: float


class BOCurrentBest(BaseModel):
    experiment_id: str
    inputs: dict[str, float]
    observed_outputs: dict[str, float]
    observed_score: float


class BOStateResponse(BaseModel):
    project_id: str
    observed_count: int
    suggested_count: int
    rejected_count: int
    current_best: BOCurrentBest | None = None
    latest_suggestion: LoggedExperiment | None = None
    history: list[LoggedExperiment]
    config: BOConfig


class BOSuggestResponse(BaseModel):
    suggestion: LoggedExperiment
    state: BOStateResponse


class BOReviewResponse(BaseModel):
    experiment: LoggedExperiment
    state: BOStateResponse


class BORevealReplayExperiment(BaseModel):
    suggested_inputs: dict[str, float]
    matched_replay_inputs: dict[str, float]
    observed_outputs: dict[str, float]
    predicted_outputs: dict[str, float] | None = None
    prediction_error: dict[str, float] | None = None
    replay_distance: float


class BORevealReplayResponse(BaseModel):
    experiment: BORevealReplayExperiment
    logged_experiment: LoggedExperiment
    state: BOStateResponse


class ScientistReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str | None = None
    decision: str | None = None
    reviewer: str | None = None
    notes: str | None = None


class BOFantasyRolloutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: int = Field(default=5, ge=1, le=10)
    config: BOConfig | None = None


class BOFantasyStep(BaseModel):
    iteration: int
    inputs: dict[str, float]
    predicted_outputs: dict[str, float]
    predicted_score: float
    acquisition_score: float
    expected_improvement: float
    uncertainty: dict[str, Any]
    distance_to_nearest_real: float
    low_confidence_region: bool
    source: str = "mlp_fantasy"


class BOFantasyRolloutResponse(BaseModel):
    project_id: str
    fantasy_trajectory: list[BOFantasyStep]
    metadata: dict[str, Any] = Field(default_factory=dict)
