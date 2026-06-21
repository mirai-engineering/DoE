from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import torch
import torch.nn as nn

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ml_lifecycle.training.common.model_definitions import TabularMLP  # noqa: E402
from ml_lifecycle.training.fuel_cell_doe_demo.export_onnx import export_model_to_onnx  # noqa: E402
from ml_lifecycle.training.fuel_cell_doe_demo.mlflow import configure_mlflow, set_model_alias, set_model_version_tags  # noqa: E402
from ml_lifecycle.ingesting.fuel_cell_doe_demo.preprocess import build_preprocessing_artifacts  # noqa: E402
from ml_lifecycle.ingesting.fuel_cell_doe_demo.schema import (  # noqa: E402
    MLFLOW_REGISTERED_MODEL_NAME,
    MODEL_COLUMNS,
    PAPER_INPUT_COLUMNS,
    PAPER_OUTPUT_COLUMNS,
    PHASE_SCOPE,
    PROJECT_ID,
    REAL_PROJECT_SCHEMA,
    TRAINING_ARTIFACT_DIR,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stable_json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _inverse_minmax(values: np.ndarray, minimum: np.ndarray, maximum: np.ndarray) -> np.ndarray:
    scale = np.where(maximum > minimum, maximum - minimum, 1.0)
    return (values * scale + minimum).astype(np.float32)


def _scaled_arrays(frame: pd.DataFrame, split: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    subset = frame[frame["split"] == split]
    x_scaled = subset[[f"scaled_{name}" for name in PAPER_INPUT_COLUMNS]].to_numpy(dtype=np.float32)
    y_scaled = subset[[f"scaled_{name}" for name in PAPER_OUTPUT_COLUMNS]].to_numpy(dtype=np.float32)
    x_raw = subset[PAPER_INPUT_COLUMNS].to_numpy(dtype=np.float32)
    y_raw = subset[PAPER_OUTPUT_COLUMNS].to_numpy(dtype=np.float32)
    return x_scaled, y_scaled, x_raw, y_raw


def _target_reference(y_train_raw: np.ndarray) -> dict[str, dict[str, float | str]]:
    reference: dict[str, dict[str, float | str]] = {}
    for index, output_name in enumerate(PAPER_OUTPUT_COLUMNS):
        values = y_train_raw[:, index].astype(np.float64)
        minimum = float(np.min(values))
        maximum = float(np.max(values))
        reference[output_name] = {
            "unit": OUTPUT_UNITS.get(output_name, ""),
            "train_mean": float(np.mean(values)),
            "train_median": float(np.median(values)),
            "train_min": minimum,
            "train_max": maximum,
            "range": max(maximum - minimum, 1e-12),
            "std": max(float(np.std(values)), 1e-12),
        }
    return reference


def _safe_r2(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float | None, str | None]:
    if y_true.shape[0] < 2:
        return None, "undefined_less_than_two_samples"
    if np.allclose(y_true, y_true[0]):
        return None, "undefined_constant_target"
    score = float(r2_score(y_true, y_pred))
    if not np.isfinite(score):
        return None, "undefined_non_finite"
    return score, None


DEFAULT_SELECTION_WEIGHTS = {
    "bol_current_density": 0.30,
    "eol_current_density": 0.40,
    "bol_ecsa": 0.15,
    "ecsa_loss": 0.15,
}

OUTPUT_UNITS = {output["name"]: output.get("unit", "") for output in REAL_PROJECT_SCHEMA["outputs"]}


def _activation(name: str) -> nn.Module:
    key = str(name).lower()
    if key == "gelu":
        return nn.GELU()
    if key == "relu":
        return nn.ReLU()
    if key == "tanh":
        return nn.Tanh()
    return nn.SiLU()


def _norm(name: str, width: int) -> nn.Module | None:
    key = str(name).lower()
    if key in {"layernorm", "layer_norm"}:
        return nn.LayerNorm(width)
    if key in {"batchnorm", "batch_norm", "batch_norm1d"}:
        return nn.BatchNorm1d(width)
    return None


def _mlp_block(previous: int, hidden: int, *, activation: str, normalization: str, dropout: float) -> list[nn.Module]:
    layers: list[nn.Module] = [nn.Linear(previous, hidden)]
    norm = _norm(normalization, hidden)
    if norm is not None:
        layers.append(norm)
    layers.append(_activation(activation))
    if dropout > 0:
        layers.append(nn.Dropout(dropout))
    return layers


class ScientificTabularANN(nn.Module):
    """Configurable small-data ANN for tabular scientific regression."""

    def __init__(self, input_dim: int, output_dim: int, hidden_dims: tuple[int, ...] = (128, 64, 32), dropout: float = 0.05, activation: str = "SiLU", normalization: str = "layer_norm"):
        super().__init__()
        layers: list[nn.Module] = []
        previous = input_dim
        for hidden in hidden_dims:
            layers.extend(_mlp_block(previous, hidden, activation=activation, normalization=normalization, dropout=dropout))
            previous = hidden
        layers.append(nn.Linear(previous, output_dim))
        self.network = nn.Sequential(*layers)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.network(features)


class SharedTrunkMultiHeadANN(nn.Module):
    """Shared representation with separate output heads to reduce target interference."""

    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        *,
        trunk_layers: tuple[int, ...] = (128, 128),
        head_layers: tuple[int, ...] = (64,),
        secondary_head_layers: tuple[int, ...] = (32,),
        dropout: float = 0.05,
        activation: str = "SiLU",
        normalization: str = "layer_norm",
        primary_output_count: int = 2,
    ):
        super().__init__()
        trunk: list[nn.Module] = []
        previous = input_dim
        for hidden in trunk_layers:
            trunk.extend(_mlp_block(previous, hidden, activation=activation, normalization=normalization, dropout=dropout))
            previous = hidden
        self.trunk = nn.Sequential(*trunk)
        trunk_width = previous
        primary_count = min(max(1, primary_output_count), output_dim)
        secondary_count = output_dim - primary_count
        self.primary_count = primary_count
        self.secondary_count = secondary_count
        self.primary_head = self._head(trunk_width, primary_count, head_layers, activation=activation, dropout=dropout)
        self.secondary_head = self._head(trunk_width, secondary_count, secondary_head_layers, activation=activation, dropout=dropout) if secondary_count > 0 else None

    @staticmethod
    def _head(input_dim: int, output_dim: int, hidden_layers: tuple[int, ...], *, activation: str, dropout: float) -> nn.Sequential:
        layers: list[nn.Module] = []
        previous = input_dim
        for hidden in hidden_layers:
            layers.extend([nn.Linear(previous, hidden), _activation(activation)])
            if dropout > 0:
                layers.append(nn.Dropout(dropout))
            previous = hidden
        layers.append(nn.Linear(previous, output_dim))
        return nn.Sequential(*layers)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        representation = self.trunk(features)
        primary = self.primary_head(representation)
        if self.secondary_head is None:
            return primary
        return torch.cat([primary, self.secondary_head(representation)], dim=1)


def _relative_percent(numerator: float, denominator: float | None) -> float | None:
    if denominator is None or abs(denominator) < 1e-12:
        return None
    return float(100.0 * numerator / abs(denominator))


def _status_for_nrmse(nrmse: float | None, variance_defined: bool) -> str:
    if not variance_defined:
        return "not_enough_variance"
    if nrmse is None:
        return "not_enough_variance"
    if nrmse <= 0.15:
        return "pass"
    if nrmse <= 0.30:
        return "warning"
    return "fail"


def _evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    split: str,
    model_name: str,
    output_scale: np.ndarray,
    reference: dict[str, dict[str, float | str]],
    baseline_pred: np.ndarray | None = None,
    selection_weights: dict[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, Any], list[dict[str, Any]]]:
    mlflow_metrics: dict[str, float] = {}
    report: dict[str, Any] = {}
    residual_rows: list[dict[str, Any]] = []
    for index, output_name in enumerate(PAPER_OUTPUT_COLUMNS):
        true_col = y_true[:, index]
        pred_col = y_pred[:, index]
        mae = float(mean_absolute_error(true_col, pred_col))
        rmse = float(mean_squared_error(true_col, pred_col) ** 0.5)
        r2, r2_note = _safe_r2(true_col, pred_col)
        scale = float(output_scale[index]) if float(output_scale[index]) > 0 else None
        nrmse = None if scale is None else float(rmse / scale)
        variance_defined = bool(r2_note != "undefined_constant_target" and np.std(true_col) > 1e-12)
        ref = reference[output_name]
        baseline_mae = baseline_rmse = baseline_improvement_mae = baseline_improvement_rmse = None
        if baseline_pred is not None:
            baseline_col = baseline_pred[:, index]
            baseline_mae = float(mean_absolute_error(true_col, baseline_col))
            baseline_rmse = float(mean_squared_error(true_col, baseline_col) ** 0.5)
            baseline_improvement_mae = None if baseline_mae <= 1e-12 else float(100.0 * (baseline_mae - mae) / baseline_mae)
            baseline_improvement_rmse = None if baseline_rmse <= 1e-12 else float(100.0 * (baseline_rmse - rmse) / baseline_rmse)
        mean_target = float(np.mean(true_col)) if len(true_col) else 0.0
        report[output_name] = {
            "unit": ref["unit"],
            "mae": mae,
            "rmse": rmse,
            "r2": r2,
            "r2_note": r2_note,
            "normalized_rmse": nrmse,
            "mae_percent_of_split_mean": _relative_percent(mae, mean_target),
            "rmse_percent_of_train_range": _relative_percent(rmse, float(ref["range"])),
            "rmse_percent_of_train_std": _relative_percent(rmse, float(ref["std"])),
            "baseline_mae": baseline_mae,
            "baseline_rmse": baseline_rmse,
            "baseline_improvement_mae_percent": baseline_improvement_mae,
            "baseline_improvement_rmse_percent": baseline_improvement_rmse,
            "reference": ref,
            "acceptance_status": _status_for_nrmse(nrmse, variance_defined),
            "n": int(len(true_col)),
            "mean_target": mean_target,
            "mean_abs_target": float(np.mean(np.abs(true_col))) if len(true_col) else 0.0,
            "scientist_summary": f"MAE {mae:.4g} {ref['unit']} ({_relative_percent(mae, mean_target) or 0:.1f}% of this split mean); baseline MAE {baseline_mae:.4g} {ref['unit']}" if baseline_mae is not None else f"MAE {mae:.4g} {ref['unit']}",
        }
        mlflow_metrics[f"{split}_{output_name}_mae"] = mae
        mlflow_metrics[f"{split}_{output_name}_rmse"] = rmse
        if r2 is not None:
            mlflow_metrics[f"{split}_{output_name}_r2"] = float(r2)
        mlflow_metrics[f"{split}_{output_name}_r2_defined"] = 1.0 if r2 is not None else 0.0
        if nrmse is not None:
            mlflow_metrics[f"{split}_{output_name}_normalized_rmse"] = nrmse
        if baseline_mae is not None:
            mlflow_metrics[f"{split}_{output_name}_baseline_mae"] = baseline_mae
        if baseline_improvement_mae is not None:
            mlflow_metrics[f"{split}_{output_name}_baseline_improvement_mae_percent"] = baseline_improvement_mae
        for row_index, (truth, pred) in enumerate(zip(true_col, pred_col, strict=True)):
            residual_rows.append(
                {
                    "model_name": model_name,
                    "split": split,
                    "row_index": row_index,
                    "output": output_name,
                    "y_true": float(truth),
                    "y_pred": float(pred),
                    "residual": float(truth - pred),
                    "abs_error": float(abs(truth - pred)),
                }
            )
    report["mean_mae"] = float(np.mean([item["mae"] for item in report.values() if isinstance(item, dict)]))
    report["mean_rmse"] = float(np.mean([item["rmse"] for item in report.values() if isinstance(item, dict)]))
    nrmse_values = [item["normalized_rmse"] for item in report.values() if isinstance(item, dict) and item["normalized_rmse"] is not None]
    report["mean_normalized_rmse"] = float(np.mean(nrmse_values)) if nrmse_values else None
    weights = selection_weights or DEFAULT_SELECTION_WEIGHTS
    report["weighted_normalized_rmse"] = float(sum(
        weights.get(name, 0.0) * item["normalized_rmse"]
        for name, item in report.items()
        if isinstance(item, dict) and item["normalized_rmse"] is not None
    ))
    finite_r2 = [item["r2"] for item in report.values() if isinstance(item, dict) and item["r2"] is not None]
    report["mean_r2"] = float(np.mean(finite_r2)) if finite_r2 else None
    mlflow_metrics[f"{split}_mean_mae"] = report["mean_mae"]
    mlflow_metrics[f"{split}_mean_rmse"] = report["mean_rmse"]
    if report["mean_normalized_rmse"] is not None:
        mlflow_metrics[f"{split}_mean_normalized_rmse"] = report["mean_normalized_rmse"]
    mlflow_metrics[f"{split}_weighted_normalized_rmse"] = report["weighted_normalized_rmse"]
    if report["mean_r2"] is not None:
        mlflow_metrics[f"{split}_mean_r2"] = report["mean_r2"]
    mlflow_metrics[f"{split}_mean_r2_defined"] = 1.0 if report["mean_r2"] is not None else 0.0
    return mlflow_metrics, report, residual_rows


def _prediction_rows(
    frame: pd.DataFrame,
    *,
    split: str,
    model_name: str,
    model_type: str,
    y_pred: np.ndarray,
    project_id: str = PROJECT_ID,
) -> list[dict[str, Any]]:
    """Build curve-friendly wide prediction rows with inputs, metadata, truths, and predictions."""
    subset = frame[frame["split"] == split].copy()
    context_columns = [
        column
        for column in [
            *PAPER_INPUT_COLUMNS,
            "cell_id",
            "test_no",
            "pt_loading_mg_cm2",
            "pt_c_ratio_percent",
            "catalyst_type",
            "support_type",
            "curve_variant",
            "voltage_alignment_method",
            "phase_scope",
            "schema_source",
        ]
        if column in subset.columns
    ]
    rows: list[dict[str, Any]] = []
    for position, (_, source_row) in enumerate(subset.iterrows()):
        row: dict[str, Any] = {
            "project_id": project_id,
            "model_name": model_name,
            "model_type": model_type,
            "source": "training_run_predictions",
            "split": split,
            "row_index": int(source_row.name),
        }
        for column in context_columns:
            value = source_row[column]
            row[column] = value.item() if hasattr(value, "item") else value
        for output_index, output_name in enumerate(PAPER_OUTPUT_COLUMNS):
            truth = float(source_row[output_name])
            pred = float(y_pred[position, output_index])
            row[f"{output_name}_true"] = truth
            row[f"{output_name}_pred"] = pred
            row[f"{output_name}_residual"] = truth - pred
            row[f"{output_name}_abs_error"] = abs(truth - pred)
        rows.append(row)
    return rows


def _export_linear_onnx(model: LinearRegression, path: Path, *, input_dim: int, output_dim: int) -> None:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    path.parent.mkdir(parents=True, exist_ok=True)
    coef = np.asarray(model.coef_, dtype=np.float32)
    if coef.shape == (output_dim, input_dim):
        weight = coef.T
    elif coef.shape == (input_dim, output_dim):
        weight = coef
    else:
        raise ValueError(f"Unexpected linear coefficient shape: {coef.shape}")
    intercept = np.asarray(model.intercept_, dtype=np.float32).reshape(output_dim)

    graph = helper.make_graph(
        [
            helper.make_node("MatMul", ["features", "linear_weight"], ["linear_output"]),
            helper.make_node("Add", ["linear_output", "linear_intercept"], ["predictions"]),
        ],
        "linear_regression",
        [helper.make_tensor_value_info("features", TensorProto.FLOAT, [None, input_dim])],
        [helper.make_tensor_value_info("predictions", TensorProto.FLOAT, [None, output_dim])],
        [
            numpy_helper.from_array(weight, name="linear_weight"),
            numpy_helper.from_array(intercept, name="linear_intercept"),
        ],
    )
    model_proto = helper.make_model(graph, producer_name="mirai-doe-engine")
    model_proto.ir_version = 8
    model_proto.opset_import[0].version = 17
    onnx.checker.check_model(model_proto)
    onnx.save(model_proto, path)


def _weighted_loss(pred: torch.Tensor, target: torch.Tensor, *, loss_name: str, weights: torch.Tensor | None) -> torch.Tensor:
    key = str(loss_name).lower()
    if "smooth" in key or "huber" in key:
        loss_by_output = torch.nn.functional.smooth_l1_loss(pred, target, reduction="none")
    else:
        loss_by_output = torch.nn.functional.mse_loss(pred, target, reduction="none")
    if weights is not None or key.startswith("weighted"):
        if weights is None:
            weights = torch.ones(loss_by_output.shape[1], dtype=loss_by_output.dtype, device=loss_by_output.device)
        loss_by_output = loss_by_output * weights.reshape(1, -1)
    return loss_by_output.mean()


def _train_mlp(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_validation: np.ndarray,
    y_validation: np.ndarray,
    *,
    config: dict[str, Any],
    seed: int,
) -> tuple[nn.Module, dict[str, Any]]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    architecture_family = str(config.get("architecture_family", "plain_mlp"))
    hidden_layers = tuple(int(value) for value in config.get("hidden_layers", [128, 64, 32]))
    trunk_layers = tuple(int(value) for value in config.get("trunk_layers", [128, 128]))
    head_layers = tuple(int(value) for value in config.get("head_layers", [64]))
    secondary_head_layers = tuple(int(value) for value in config.get("secondary_head_layers", [32]))
    dropout = float(config.get("dropout", 0.05))
    activation = str(config.get("activation", "SiLU"))
    normalization = str(config.get("normalization", "layer_norm"))
    if architecture_family == "shared_trunk_multi_head":
        model: nn.Module = SharedTrunkMultiHeadANN(
            input_dim=x_train.shape[1],
            output_dim=y_train.shape[1],
            trunk_layers=trunk_layers,
            head_layers=head_layers,
            secondary_head_layers=secondary_head_layers,
            dropout=dropout,
            activation=activation,
            normalization=normalization,
        )
    else:
        model = ScientificTabularANN(
            input_dim=x_train.shape[1],
            output_dim=y_train.shape[1],
            hidden_dims=hidden_layers,
            dropout=dropout,
            activation=activation,
            normalization=normalization,
        )
    optimizer_name = str(config.get("optimizer", "AdamW"))
    optimizer_cls = torch.optim.Adam if optimizer_name.lower() == "adam" else torch.optim.AdamW
    optimizer = optimizer_cls(model.parameters(), lr=float(config.get("learning_rate", 0.003)), weight_decay=float(config.get("weight_decay", 1e-4)))
    patience = int(config.get("early_stopping_patience", 100))
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=max(10, patience // 4))
    train_x = torch.from_numpy(x_train)
    train_y = torch.from_numpy(y_train)
    validation_x = torch.from_numpy(x_validation)
    validation_y = torch.from_numpy(y_validation)
    output_weights_map = config.get("output_weights") if isinstance(config.get("output_weights"), dict) else {}
    weights_array = np.asarray([float(output_weights_map.get(name, 1.0)) for name in PAPER_OUTPUT_COLUMNS], dtype=np.float32)
    if np.sum(weights_array) > 0:
        weights_array = weights_array / float(np.mean(weights_array))
    weights = torch.from_numpy(weights_array) if output_weights_map or str(config.get("loss", "")).startswith("weighted") else None
    batch_size = config.get("batch_size", "full_batch")
    full_batch = batch_size == "full_batch" or batch_size is None
    batch_size_int = len(train_x) if full_batch else max(1, int(batch_size))
    best_state = deepcopy(model.state_dict())
    best_validation_loss = float("inf")
    best_epoch = 0
    stale_epochs = 0
    epochs = int(config.get("max_epochs", 500))
    for epoch in range(epochs):
        model.train()
        permutation = torch.randperm(len(train_x)) if not full_batch else torch.arange(len(train_x))
        for start in range(0, len(train_x), batch_size_int):
            indices = permutation[start:start + batch_size_int]
            pred = model(train_x[indices])
            loss = _weighted_loss(pred, train_y[indices], loss_name=str(config.get("loss", "mse")), weights=weights)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            validation_loss = float(_weighted_loss(model(validation_x), validation_y, loss_name=str(config.get("loss", "mse")), weights=weights).item())
        scheduler.step(validation_loss)
        if validation_loss < best_validation_loss - 1e-7:
            best_validation_loss = validation_loss
            best_epoch = epoch + 1
            best_state = deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
        if epoch + 1 >= min(100, epochs) and stale_epochs >= patience:
            break
    model.load_state_dict(best_state)
    model.eval()
    return model, {
        "architecture": "SharedTrunkMultiHeadANN" if architecture_family == "shared_trunk_multi_head" else "ScientificTabularANN",
        "architecture_family": architecture_family,
        "hidden_dims": list(hidden_layers),
        "trunk_layers": list(trunk_layers),
        "head_layers": list(head_layers),
        "secondary_head_layers": list(secondary_head_layers),
        "activation": activation,
        "normalization": normalization,
        "dropout": dropout,
        "optimizer": optimizer_name,
        "learning_rate": float(config.get("learning_rate", 0.003)),
        "weight_decay": float(config.get("weight_decay", 1e-4)),
        "loss": str(config.get("loss", "mse")),
        "batch_size": batch_size,
        "seed": seed,
        "best_epoch": best_epoch,
        "best_validation_loss_scaled": best_validation_loss,
        "epochs_run": epoch + 1,
        "early_stopping_patience": patience,
    }


def _predict_mlp(model: nn.Module, x: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        return model(torch.from_numpy(x)).numpy().astype(np.float32)


def _log_run(
    *,
    mlflow,
    model_name: str,
    params: dict[str, Any],
    metrics: dict[str, float],
    artifact_paths: list[Path],
    onnx_path: Path,
    register: bool,
    is_selected_candidate: bool,
    dataset_id: str | None = None,
    ingestion_session_id: str | None = None,
    preprocessing_report_id: str | None = None,
    training_request_id: str | None = None,
    mlflow_project_id: str = PROJECT_ID,
    registered_model_name: str = MLFLOW_REGISTERED_MODEL_NAME,
) -> str:
    import onnx

    # Do not pass run_name: let MLflow generate distinctive UI names while
    # keeping project/model identity searchable through tags and params.
    with mlflow.start_run() as run:
        lifecycle_tags = {
            "project_id": mlflow_project_id,
            "schema_project_id": PROJECT_ID,
            "phase_scope": PHASE_SCOPE,
            "quality_label": "all-cells MVP",
            "model_family": "ridge" if model_name.startswith("ridge") else "mlp" if model_name.startswith("mlp") else model_name,
            "model_name": model_name,
            "candidate_role": "challenger" if is_selected_candidate else "candidate",
            "lifecycle_role": "challenger" if is_selected_candidate else "candidate",
            "selected_candidate": str(is_selected_candidate).lower(),
        }
        optional_tags = {
            "dataset_id": dataset_id,
            "ingestion_session_id": ingestion_session_id,
            "preprocessing_report_id": preprocessing_report_id,
            "training_request_id": training_request_id,
        }
        lifecycle_tags.update({key: value for key, value in optional_tags.items() if value})
        mlflow.set_tags(lifecycle_tags)
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        for artifact in artifact_paths:
            if artifact.exists():
                if artifact.is_dir():
                    mlflow.log_artifacts(str(artifact), artifact_path=artifact.name)
                else:
                    mlflow.log_artifact(str(artifact))
        mlflow.onnx.log_model(
            onnx.load(str(onnx_path)),
            name="onnx",
            registered_model_name=registered_model_name if register else None,
            metadata={"quality_label": "all-cells MVP", "model_family": model_name},
            tags={
                **{key: value for key, value in optional_tags.items() if value},
                "project_id": mlflow_project_id,
                "schema_project_id": PROJECT_ID,
                "model_family": "ridge" if model_name.startswith("ridge") else "mlp" if model_name.startswith("mlp") else model_name,
                "model_name": model_name,
                "candidate_role": "challenger" if is_selected_candidate else "candidate",
                "lifecycle_role": "challenger" if is_selected_candidate else "candidate",
            },
            model_type=model_name,
        )
        return run.info.run_id


def train_models(
    *,
    project_id: str = PROJECT_ID,
    register_mlflow: bool = True,
    set_alias: str = "challenger",
    epochs: int = 500,
    learning_rate: float = 1e-2,
    seed: int = 7,
    dataset_id: str | None = None,
    ingestion_session_id: str | None = None,
    preprocessing_report_id: str | None = None,
    training_request_id: str | None = None,
    data_dir: Path | None = None,
    artifact_dir: Path | None = None,
    mlflow_experiment_name: str | None = None,
    registered_model_name: str | None = None,
    training_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if project_id != PROJECT_ID:
        raise ValueError(f"Unsupported real project id: {project_id}")
    mlflow_experiment_name = mlflow_experiment_name or project_id
    registered_model_name = registered_model_name or MLFLOW_REGISTERED_MODEL_NAME
    training_config = training_config or {}
    linear_config = training_config.get("linear", {}) if isinstance(training_config.get("linear"), dict) else {}
    mlp_config = training_config.get("mlp", {}) if isinstance(training_config.get("mlp"), dict) else {}
    search_config = training_config.get("search", {}) if isinstance(training_config.get("search"), dict) else {}

    preprocessing_kwargs: dict[str, Any] = {"project_id": project_id}
    if data_dir is not None:
        preprocessing_kwargs["data_dir"] = data_dir
    if artifact_dir is not None:
        preprocessing_kwargs["artifact_dir"] = artifact_dir
    preprocess_result = build_preprocessing_artifacts(**preprocessing_kwargs)
    artifact_dir = Path(preprocess_result["artifact_dir"])
    frame = pd.read_csv(artifact_dir / "model_table_preprocessed.csv")
    preprocessing = _load_json(artifact_dir / "preprocessing.json")
    output_min = np.asarray(preprocessing["output_scaler"]["min"], dtype=np.float32)
    output_max = np.asarray(preprocessing["output_scaler"]["max"], dtype=np.float32)
    output_scale = np.where(output_max > output_min, output_max - output_min, 1.0).astype(np.float32)
    configured_output_weights = mlp_config.get("output_weights") if isinstance(mlp_config.get("output_weights"), dict) else {}
    if configured_output_weights:
        weight_sum = sum(float(configured_output_weights.get(name, 0.0)) for name in PAPER_OUTPUT_COLUMNS)
        selection_weights = {name: float(configured_output_weights.get(name, 0.0)) / weight_sum for name in PAPER_OUTPUT_COLUMNS} if weight_sum > 0 else {name: 1.0 / len(PAPER_OUTPUT_COLUMNS) for name in PAPER_OUTPUT_COLUMNS}
    else:
        selection_weights = {name: 1.0 / len(PAPER_OUTPUT_COLUMNS) for name in PAPER_OUTPUT_COLUMNS}

    x_train, y_train, _x_train_raw, y_train_raw = _scaled_arrays(frame, "train")
    x_validation, y_validation, _x_validation_raw, _y_validation_raw = _scaled_arrays(frame, "validation")
    target_reference = _target_reference(y_train_raw)
    baseline_raw = np.asarray([target_reference[name]["train_mean"] for name in PAPER_OUTPUT_COLUMNS], dtype=np.float32)

    model_reports: dict[str, Any] = {}
    mlflow_metrics_by_model: dict[str, dict[str, float]] = {}
    residual_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    model_artifacts: dict[str, dict[str, Path]] = {}

    trained_models: dict[str, Any] = {}
    training_reports: dict[str, dict[str, Any]] = {}

    if linear_config.get("include_mvlr", True):
        linear_dir = artifact_dir / "models" / "mvlr"
        linear = LinearRegression(fit_intercept=bool(linear_config.get("fit_intercept", True)))
        linear.fit(x_train, y_train)
        linear_onnx = linear_dir / "model.onnx"
        _export_linear_onnx(linear, linear_onnx, input_dim=x_train.shape[1], output_dim=y_train.shape[1])
        trained_models["mvlr"] = linear
        training_reports["mvlr"] = {"model_type": "multi_output_linear_regression", "fit_intercept": bool(linear_config.get("fit_intercept", True))}
        model_artifacts["mvlr"] = {"onnx": linear_onnx}

    if linear_config.get("include_ridge", True):
        for alpha in linear_config.get("ridge_alphas", [0.01, 0.1, 1.0, 10.0]):
            model_name = f"ridge_alpha_{str(alpha).replace('.', '_')}"
            ridge_dir = artifact_dir / "models" / model_name
            ridge = Ridge(alpha=float(alpha), fit_intercept=bool(linear_config.get("fit_intercept", True)))
            ridge.fit(x_train, y_train)
            ridge_onnx = ridge_dir / "model.onnx"
            _export_linear_onnx(ridge, ridge_onnx, input_dim=x_train.shape[1], output_dim=y_train.shape[1])
            trained_models[model_name] = ridge
            training_reports[model_name] = {"model_type": "ridge_regression", "ridge_alpha": float(alpha), "fit_intercept": bool(linear_config.get("fit_intercept", True))}
            model_artifacts[model_name] = {"onnx": ridge_onnx}

    if mlp_config.get("include", True):
        mlp_candidates: list[dict[str, Any]] = [
            {**{"max_epochs": epochs, "learning_rate": learning_rate, "seed": seed}, **mlp_config},
        ]
        mode = str(search_config.get("mode", "single_config"))
        if mode in {"small_sweep_1h", "balanced_sweep_2h"}:
            base = {**mlp_config, "output_weights": mlp_config.get("output_weights", {})}
            mlp_candidates = [
                {**base, "architecture_family": "plain_mlp", "hidden_layers": [64, 32], "activation": "SiLU", "dropout": 0.05, "learning_rate": 0.003, "weight_decay": 1e-4, "loss": "smooth_l1"},
                {**base, "architecture_family": "plain_mlp", "hidden_layers": [128, 64, 32], "activation": "SiLU", "dropout": 0.05, "learning_rate": 0.003, "weight_decay": 1e-4, "loss": "smooth_l1"},
                {**base, "architecture_family": "shared_trunk_multi_head", "trunk_layers": [128, 128], "head_layers": [64], "secondary_head_layers": [32], "activation": "SiLU", "dropout": 0.05, "learning_rate": 0.003, "weight_decay": 1e-4, "loss": "weighted_smooth_l1"},
            ]
            if mode == "balanced_sweep_2h":
                mlp_candidates.extend([
                    {**base, "architecture_family": "plain_mlp", "hidden_layers": [192, 96, 48], "activation": "GELU", "dropout": 0.10, "learning_rate": 0.001, "weight_decay": 1e-4, "loss": "weighted_smooth_l1"},
                    {**base, "architecture_family": "shared_trunk_multi_head", "trunk_layers": [192, 128], "head_layers": [64], "secondary_head_layers": [32], "activation": "GELU", "dropout": 0.10, "learning_rate": 0.001, "weight_decay": 1e-4, "loss": "weighted_smooth_l1"},
                ])
        for index, candidate_config in enumerate(mlp_candidates, start=1):
            candidate_seed = int((candidate_config.get("seeds") or [candidate_config.get("seed", seed)])[0]) if isinstance(candidate_config.get("seeds"), list) else int(candidate_config.get("seed", seed))
            candidate_config = {**candidate_config, "seed": candidate_seed, "max_epochs": int(candidate_config.get("max_epochs", epochs)), "learning_rate": float(candidate_config.get("learning_rate", learning_rate))}
            model_name = "mlp" if len(mlp_candidates) == 1 else f"mlp_trial_{index:02d}"
            mlp_dir = artifact_dir / "models" / model_name
            mlp, mlp_training_report = _train_mlp(x_train, y_train, x_validation, y_validation, config=candidate_config, seed=candidate_seed)
            mlp_onnx = mlp_dir / "model.onnx"
            export_model_to_onnx(mlp, mlp_onnx, input_dim=x_train.shape[1], verify=True)
            torch.save(
                {
                    "model_state_dict": mlp.state_dict(),
                    "model_config": {"input_dim": x_train.shape[1], "output_dim": y_train.shape[1], **mlp_training_report},
                    "input_order": PAPER_INPUT_COLUMNS,
                    "output_order": PAPER_OUTPUT_COLUMNS,
                },
                mlp_dir / "model.pt",
            )
            trained_models[model_name] = mlp
            training_reports[model_name] = mlp_training_report
            model_artifacts[model_name] = {"onnx": mlp_onnx, "checkpoint": mlp_dir / "model.pt"}

    for model_name in ["mean_baseline", *trained_models.keys()]:
        split_reports: dict[str, Any] = {}
        mlflow_metrics: dict[str, float] = {}
        for split in ["train", "validation", "test"]:
            x_scaled, _y_scaled, _x_raw, y_raw = _scaled_arrays(frame, split)
            baseline_pred = np.tile(baseline_raw, (len(y_raw), 1)).astype(np.float32)
            if model_name == "mean_baseline":
                pred = baseline_pred
            else:
                model = trained_models[model_name]
                if isinstance(model, nn.Module):
                    pred_scaled = _predict_mlp(model, x_scaled)
                else:
                    pred_scaled = model.predict(x_scaled).astype(np.float32)
                pred = _inverse_minmax(pred_scaled, output_min, output_max)
            if model_name != "mean_baseline":
                prediction_rows.extend(
                    _prediction_rows(
                        frame,
                        split=split,
                        model_name=model_name,
                        model_type=training_reports.get(model_name, {}).get("model_type") or training_reports.get(model_name, {}).get("architecture_family") or "candidate_model",
                        y_pred=pred,
                    )
                )
            split_metrics, split_report, split_residuals = _evaluate_predictions(
                y_raw,
                pred,
                split=split,
                model_name=model_name,
                output_scale=output_scale,
                reference=target_reference,
                baseline_pred=baseline_pred,
                selection_weights=selection_weights,
            )
            mlflow_metrics.update(split_metrics)
            split_reports[split] = split_report
            residual_rows.extend(split_residuals)
        report_splits = split_reports
        model_reports[model_name] = {
            "model_name": model_name,
            "model_type": "train_mean_reference" if model_name == "mean_baseline" else training_reports.get(model_name, {}).get("model_type") or training_reports.get(model_name, {}).get("architecture_family") or "candidate_model",
            "splits": report_splits,
            "diagnostic_splits": split_reports,
            "selection_metric": split_reports["validation"]["weighted_normalized_rmse"],
            "selection_metric_name": "validation_weighted_normalized_rmse",
            "deployable_onnx": str(model_artifacts[model_name]["onnx"]) if model_name in model_artifacts else None,
        }
        if model_name != "mean_baseline":
            mlflow_metrics_by_model[model_name] = mlflow_metrics

    # Lower validation weighted normalized RMSE wins among deployable models.
    deployable_model_names = [name for name in trained_models if name in model_reports]
    if not deployable_model_names:
        raise ValueError("No deployable model candidates were trained")
    best_model_name = min(deployable_model_names, key=lambda name: model_reports[name]["selection_metric"])
    best_report = model_reports[best_model_name]

    residuals_path = artifact_dir / "residuals.csv"
    residual_frame = pd.DataFrame(residual_rows)
    residual_frame.to_csv(residuals_path, index=False)
    predictions_path = artifact_dir / "predictions.csv"
    prediction_frame = pd.DataFrame(prediction_rows)
    prediction_frame.to_csv(predictions_path, index=False)
    plots_dir = artifact_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    residual_plot_path = plots_dir / "residual_abs_error_by_output.png"
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 3.5))
        residual_frame.groupby(["model_name", "output"])["abs_error"].mean().unstack(0).plot(kind="bar", ax=ax)
        ax.set_ylabel("Mean absolute error")
        ax.set_title("Residual error by output")
        fig.tight_layout()
        fig.savefig(residual_plot_path, dpi=120)
        plt.close(fig)
    except Exception:
        residual_plot_path = None

    metrics_summary = {
        "project_id": PROJECT_ID,
        "generated_at": _utc_now(),
        "phase_scope": PHASE_SCOPE,
        "quality_label": "all-cells MVP",
        "selection_metric": "validation_weighted_normalized_rmse",
        "selection_weights": selection_weights,
        "best_model_name": best_model_name,
        "best_model_type": best_report["model_type"],
        "target_reference": target_reference,
        "models": model_reports,
        "residual_plot": str(residual_plot_path) if residual_plot_path else None,
        "predictions_artifact": str(predictions_path),
        "scientist_metric_guidance": [
            "MAE/RMSE are reported in each output's physical unit.",
            "MAE percent-of-mean and RMSE percent-of-train-range provide scale-aware interpretation.",
            "Baseline improvement compares each model with simply predicting the train-cell mean for that output.",
            "Negative R² means the model is worse than the mean baseline on that split/output.",
        ],
        "notes": [
            "All-cells MVP uses grouped-by-cell train/validation/test splits. BO replay uses train+validation rows and keeps test untouched.",
            "Acceptance thresholds are provisional/report-only until scientific criteria are finalized.",
            "R² can still be negative when held-out cells differ strongly from training cells.",
        ],
    }
    metrics_summary_path = artifact_dir / "metrics_summary.json"
    _write_json(metrics_summary_path, metrics_summary)
    candidate_rows = [
        {
            "model_name": name,
            "model_type": report.get("model_type"),
            "selection_metric": report.get("selection_metric"),
            "validation_weighted_normalized_rmse": report.get("splits", {}).get("validation", {}).get("weighted_normalized_rmse"),
            "test_weighted_normalized_rmse": report.get("splits", {}).get("test", {}).get("weighted_normalized_rmse"),
            "validation_mean_r2": report.get("splits", {}).get("validation", {}).get("mean_r2"),
            "test_mean_r2": report.get("splits", {}).get("test", {}).get("mean_r2"),
            "selected_challenger": name == best_model_name,
        }
        for name, report in sorted(model_reports.items(), key=lambda item: float(item[1].get("selection_metric", 999)) if item[0] != "mean_baseline" else 999)
    ]
    candidate_table_path = artifact_dir / "candidate_comparison.csv"
    pd.DataFrame(candidate_rows).to_csv(candidate_table_path, index=False)
    _write_json(artifact_dir / "top_trials.json", {"candidates": candidate_rows[:10], "training_config": training_config})

    metadata = {
        "project_id": mlflow_experiment_name,
        "display_name": REAL_PROJECT_SCHEMA["display_name"],
        "schema_project_id": PROJECT_ID,
        "model_version": f"{registered_model_name}@{set_alias}",
        "model_type": best_report["model_type"],
        "trained_at": _utc_now(),
        "source_data": "data/reference/pem_fuel_cell_cathode_degradation/model_table.csv",
        "quality_label": "all-cells MVP",
        "scientific_evidence_warning": "Grouped-by-cell MVP; scientific thresholds are still provisional/report-only.",
        "metrics": metrics_summary,
        "mlflow_experiment_name": mlflow_experiment_name,
        "mlflow_registered_model_name": registered_model_name,
        "training_config": training_config,
        "candidate_comparison": str(candidate_table_path),
    }
    metadata_path = artifact_dir / "metadata.json"
    _write_json(metadata_path, metadata)

    mlflow = configure_mlflow(mlflow_experiment_name)
    run_ids: dict[str, str] = {}
    common_artifacts = [
        artifact_dir / "schema.json",
        artifact_dir / "preprocessing.json",
        artifact_dir / "eda_report.json",
        artifact_dir / "preprocessing_report.json",
        artifact_dir / "split_report.json",
        metrics_summary_path,
        residuals_path,
        predictions_path,
        candidate_table_path,
        artifact_dir / "top_trials.json",
        metadata_path,
        artifact_dir / "plots",
    ]
    schema_payload = _load_json(artifact_dir / "schema.json")
    input_schema_hash = _stable_json_hash(schema_payload.get("inputs", []))
    output_schema_hash = _stable_json_hash(schema_payload.get("outputs", []))
    for model_name in deployable_model_names:
        report_params = training_reports.get(model_name, {})
        params = {
            "project_id": mlflow_experiment_name,
            "schema_project_id": PROJECT_ID,
            "phase_scope": PHASE_SCOPE,
            "model_name": model_name,
            "model_family": "ridge" if model_name.startswith("ridge") else "mlp" if model_name.startswith("mlp") else model_name,
            "model_architecture_family": report_params.get("architecture_family", report_params.get("model_type", model_name)),
            "seed": report_params.get("seed", seed),
            "input_dim": len(PAPER_INPUT_COLUMNS),
            "output_dim": len(PAPER_OUTPUT_COLUMNS),
            "split_strategy": "metadata-aware grouped_by_cell_id; BO uses train+validation and test remains untouched",
            "search_mode": search_config.get("mode", "single_config"),
            "output_weights": json.dumps(selection_weights, sort_keys=True),
        }
        params.update({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in report_params.items() if isinstance(v, (int, float, str, list, dict, bool))})
        is_selected_candidate = model_name == best_model_name
        # Model-version tagging helpers may touch MLflow global state; reset the
        # active experiment before every candidate run so uploaded projects keep
        # all model-family runs together.
        configure_mlflow(mlflow_experiment_name)
        run_id = _log_run(
            mlflow=mlflow,
            model_name=model_name,
            params=params,
            metrics=mlflow_metrics_by_model[model_name],
            artifact_paths=common_artifacts + list(model_artifacts[model_name].values()),
            onnx_path=model_artifacts[model_name]["onnx"],
            register=register_mlflow and is_selected_candidate,
            is_selected_candidate=is_selected_candidate,
            dataset_id=dataset_id,
            ingestion_session_id=ingestion_session_id,
            preprocessing_report_id=preprocessing_report_id,
            training_request_id=training_request_id,
            mlflow_project_id=mlflow_experiment_name,
            registered_model_name=registered_model_name,
        )
        run_ids[model_name] = run_id
        if register_mlflow and is_selected_candidate:
            set_model_version_tags(
                run_id,
                {
                    "project_id": mlflow_experiment_name,
                    "schema_project_id": PROJECT_ID,
                    "source_run_id": run_id,
                    "source_experiment_name": mlflow_experiment_name,
                    "model_type": model_reports[model_name].get("model_type", model_name),
                    "model_family": "ridge" if model_name.startswith("ridge") else "mlp" if model_name.startswith("mlp") else model_name,
                    "model_name": model_name,
                    "candidate_role": "challenger",
                    "lifecycle_role": "challenger",
                    "validation_status": "pending_review",
                    "created_by_pipeline": "true",
                    "selected_candidate": "true",
                    "selection_metric": "validation_weighted_normalized_rmse",
                    "selection_score": model_reports[model_name]["selection_metric"],
                    "input_schema_hash": input_schema_hash,
                    "output_schema_hash": output_schema_hash,
                    **{
                        key: value
                        for key, value in {
                            "dataset_id": dataset_id,
                            "ingestion_session_id": ingestion_session_id,
                            "preprocessing_report_id": preprocessing_report_id,
                            "training_request_id": training_request_id,
                        }.items()
                        if value
                    },
                },
                model_name=registered_model_name,
            )

    production_model = None
    alias_model = None
    if register_mlflow:
        alias_model = set_model_alias(run_ids[best_model_name], set_alias, model_name=registered_model_name)
        metadata["mlflow_alias_model"] = alias_model
        metadata["mlflow_registered_candidate_role"] = set_alias
        _write_json(metadata_path, metadata)

    artifact_summary = {
        "project_id": PROJECT_ID,
        "mlflow_experiment_name": mlflow_experiment_name,
        "mlflow_registered_model_name": registered_model_name,
        "artifact_dir": str(artifact_dir),
        "mlflow_run_ids": run_ids,
        "production_model": production_model,
        "alias_model": alias_model,
        "files": sorted(str(path) for path in artifact_dir.rglob("*") if path.is_file()),
    }
    _write_json(artifact_dir / "artifact_summary.json", artifact_summary)

    return {
        "project_id": PROJECT_ID,
        "mlflow_experiment_name": mlflow_experiment_name,
        "mlflow_registered_model_name": registered_model_name,
        "artifact_dir": str(artifact_dir),
        "best_model_name": best_model_name,
        "production_model": production_model,
        "alias_model": alias_model,
        "run_ids": run_ids,
        "dataset_id": dataset_id,
        "ingestion_session_id": ingestion_session_id,
        "preprocessing_report_id": preprocessing_report_id,
        "training_request_id": training_request_id,
        "metrics_summary_path": str(metrics_summary_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train all-cells real fuel-cell MVLR and scientific ANN models with MLflow.")
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--register-mlflow", action="store_true", help="Log models and register the selected candidate in local MLflow")
    parser.add_argument("--set-alias", default="challenger", help="MLflow alias to assign to the selected candidate")
    parser.add_argument("--epochs", type=int, default=1000)
    parser.add_argument("--learning-rate", type=float, default=3e-3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--dataset-id", default=None)
    parser.add_argument("--ingestion-session-id", default=None)
    parser.add_argument("--preprocessing-report-id", default=None)
    parser.add_argument("--training-request-id", default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--artifact-dir", type=Path, default=None)
    args = parser.parse_args()
    result = train_models(
        project_id=args.project_id,
        register_mlflow=args.register_mlflow,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        seed=args.seed,
        set_alias=args.set_alias,
        dataset_id=args.dataset_id,
        ingestion_session_id=args.ingestion_session_id,
        preprocessing_report_id=args.preprocessing_report_id,
        training_request_id=args.training_request_id,
        data_dir=args.data_dir,
        artifact_dir=args.artifact_dir,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
