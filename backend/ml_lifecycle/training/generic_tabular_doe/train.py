from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlparse

import joblib
import numpy as np
import pandas as pd

from app.services.control_plane import get_project_storage_config


BACKEND_ROOT = Path(__file__).resolve().parents[3]
MLFLOW_TRACKING_DIR = BACKEND_ROOT / "mlruns"


def _tracking_uri() -> str:
    return os.getenv("MLFLOW_TRACKING_URI", MLFLOW_TRACKING_DIR.resolve().as_uri())


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _remote_mlflow_required() -> bool:
    return _truthy_env("MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW")


def _remote_artifacts_required() -> bool:
    return _truthy_env("MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS")


def _is_remote_tracking_uri(tracking_uri: str) -> bool:
    parsed = urlparse(tracking_uri)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and host not in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _is_remote_artifact_location(artifact_location: str | None) -> bool:
    location = str(artifact_location or "")
    return location.startswith("s3://") or location.startswith("mlflow-artifacts:/")


def _assert_demo_mlflow_contract(*, tracking_uri: str, artifact_location: str | None) -> None:
    if _remote_mlflow_required() and not _is_remote_tracking_uri(tracking_uri):
        raise RuntimeError(
            "MIRAI_TRAINING_REQUIRE_REMOTE_MLFLOW is enabled, but MLFLOW_TRACKING_URI is not a remote http(s) MLflow service URL. "
            "Set MLFLOW_TRACKING_URI to the Railway MLflow URL for demo training."
        )
    if _remote_artifacts_required() and not _is_remote_artifact_location(artifact_location):
        raise RuntimeError(
            "MIRAI_TRAINING_REQUIRE_REMOTE_ARTIFACTS is enabled, but the MLflow experiment artifact location is not s3:// or mlflow-artifacts:/. "
            "Expected s3:// for direct server-side runs or mlflow-artifacts:/ for remote MLflow artifact proxying."
        )


def _registered_model_name_for_project(project_id: str) -> str:
    return f"doe_surrogate_{project_id}"


def _workspace_id_for_project(project_id: str) -> str | None:
    explicit = os.getenv("MIRAI_MLFLOW_WORKSPACE_ID")
    if explicit:
        return explicit
    if project_id == "pem_fuel_cell_real_cathode_degradation" or "fuel" in project_id:
        return "fraunhofer"
    return None


def _use_mlflow_artifact_proxy() -> bool:
    """Prefer MLflow's artifact proxy for local training against remote MLflow.

    This keeps local/on-prem exported-package training from requiring direct S3
    credentials. The remote MLflow server owns S3 access via --serve-artifacts.
    """
    return _remote_mlflow_required() and _remote_artifacts_required() and _is_remote_tracking_uri(_tracking_uri())


def _experiment_artifact_location(project_id: str) -> str | None:
    if _use_mlflow_artifact_proxy():
        return None
    workspace_id = _workspace_id_for_project(project_id)
    if not workspace_id:
        return os.getenv("MLFLOW_ARTIFACT_ROOT")
    project_config = get_project_storage_config(workspace_id, project_id)
    if project_config is not None and project_config.mode == "s3" and project_config.bucket:
        return f"s3://{project_config.bucket}/{project_config.normalized_prefix}/mlflow-artifacts"
    env_prefix = f"MIRAI_{workspace_id.upper().replace('-', '_')}_S3"
    bucket = os.getenv(f"{env_prefix}_BUCKET")
    if not bucket:
        return os.getenv("MLFLOW_ARTIFACT_ROOT")
    return f"s3://{bucket}/workspaces/{workspace_id}/projects/{project_id}/mlflow-artifacts"

from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.impute import SimpleImputer


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


def _stable_json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_2d(values: np.ndarray) -> np.ndarray:
    return values.reshape(-1, 1) if values.ndim == 1 else values


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, outputs: list[str]) -> dict[str, Any]:
    y_true = _ensure_2d(y_true)
    y_pred = _ensure_2d(y_pred)
    by_output: dict[str, Any] = {}
    nrmse_values = []
    for idx, name in enumerate(outputs):
        true = y_true[:, idx]
        pred = y_pred[:, idx]
        rmse = float(np.sqrt(mean_squared_error(true, pred)))
        mae = float(mean_absolute_error(true, pred))
        denom = float(np.nanmax(true) - np.nanmin(true)) or 1.0
        nrmse = rmse / denom
        nrmse_values.append(nrmse)
        by_output[name] = {"rmse": rmse, "mae": mae, "normalized_rmse": nrmse, "r2": float(r2_score(true, pred)) if len(true) > 1 else None}
    return {"by_output": by_output, "weighted_normalized_rmse": float(np.mean(nrmse_values)) if nrmse_values else None}


def _target_reference(train_frame: pd.DataFrame, outputs: list[str], output_units: dict[str, str]) -> dict[str, Any]:
    reference: dict[str, Any] = {}
    for output in outputs:
        values = pd.to_numeric(train_frame[output], errors="coerce").dropna().to_numpy(dtype=float)
        if len(values) == 0:
            continue
        reference[output] = {
            "unit": output_units.get(output, ""),
            "train_mean": float(np.nanmean(values)),
            "train_median": float(np.nanmedian(values)),
            "train_min": float(np.nanmin(values)),
            "train_max": float(np.nanmax(values)),
            "range": float(np.nanmax(values) - np.nanmin(values)) or 1.0,
            "std": float(np.nanstd(values)) or 1.0,
        }
    return reference


def _ui_split_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    baseline_pred: np.ndarray,
    outputs: list[str],
    output_units: dict[str, str],
    reference: dict[str, Any],
) -> dict[str, Any]:
    y_true = _ensure_2d(y_true)
    y_pred = _ensure_2d(y_pred)
    baseline_pred = _ensure_2d(baseline_pred)
    metrics: dict[str, Any] = {}
    for idx, output in enumerate(outputs):
        true = y_true[:, idx]
        pred = y_pred[:, idx]
        base = baseline_pred[:, idx]
        rmse = float(np.sqrt(mean_squared_error(true, pred)))
        mae = float(mean_absolute_error(true, pred))
        baseline_rmse = float(np.sqrt(mean_squared_error(true, base)))
        baseline_mae = float(mean_absolute_error(true, base))
        ref = reference.get(output, {})
        target_range = float(ref.get("range") or (np.nanmax(true) - np.nanmin(true)) or 1.0)
        target_std = float(ref.get("std") or np.nanstd(true) or 1.0)
        split_mean = float(np.nanmean(true)) if len(true) else 0.0
        denom_mean = abs(split_mean) or 1.0
        r2 = float(r2_score(true, pred)) if len(true) > 1 else None
        metrics[output] = {
            "unit": output_units.get(output, ""),
            "mae": mae,
            "rmse": rmse,
            "r2": r2,
            "r2_note": "Negative R² means worse than predicting the split mean." if r2 is not None and r2 < 0 else None,
            "normalized_rmse": rmse / target_range,
            "mae_percent_of_split_mean": mae / denom_mean * 100.0,
            "rmse_percent_of_train_range": rmse / target_range * 100.0,
            "rmse_percent_of_train_std": rmse / target_std * 100.0,
            "baseline_mae": baseline_mae,
            "baseline_rmse": baseline_rmse,
            "baseline_improvement_mae_percent": (baseline_mae - mae) / (baseline_mae or 1.0) * 100.0,
            "baseline_improvement_rmse_percent": (baseline_rmse - rmse) / (baseline_rmse or 1.0) * 100.0,
            "reference": ref,
            "acceptance_status": "pass" if (r2 or 0.0) >= 0.5 else "warning",
            "n": int(len(true)),
            "mean_target": split_mean,
            "mean_abs_target": float(np.nanmean(np.abs(true))) if len(true) else 0.0,
            "scientist_summary": f"MAE {mae:.4g} {output_units.get(output, '')} ({mae / denom_mean * 100.0:.1f}% of this split mean); baseline MAE {baseline_mae:.4g} {output_units.get(output, '')}".strip(),
        }
    return metrics


def _write_predictions_csv(
    *,
    project_id: str,
    artifact_dir: Path,
    model_table: pd.DataFrame,
    inputs: list[str],
    outputs: list[str],
    candidates: list[dict[str, Any]],
) -> None:
    context_columns = [column for column in model_table.columns if column not in outputs]
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        model = joblib.load(candidate["model_path"])
        frame = model_table.copy()
        pred = _ensure_2d(np.asarray(model.predict(frame[inputs].apply(pd.to_numeric, errors="coerce")), dtype=float))
        for row_idx, (_, source_row) in enumerate(frame.iterrows()):
            row = {"project_id": project_id, "model_name": candidate["model_name"], "model_type": candidate.get("model_family", "sklearn"), "source": "training_run_predictions", "row_index": int(row_idx)}
            row.update({column: source_row[column] for column in context_columns if column in source_row})
            for output_idx, output in enumerate(outputs):
                y_true = float(source_row[output])
                y_pred = float(pred[row_idx, output_idx])
                row[f"{output}_true"] = y_true
                row[f"{output}_pred"] = y_pred
                row[f"{output}_residual"] = y_true - y_pred
                row[f"{output}_abs_error"] = abs(y_true - y_pred)
            rows.append(row)
    pd.DataFrame(rows).to_csv(artifact_dir / "predictions.csv", index=False)


def _log_generic_mlflow(
    *,
    project_id: str,
    artifact_dir: Path,
    candidates: list[dict[str, Any]],
    best: dict[str, Any],
    metrics_summary: dict[str, Any],
    schema: dict[str, Any],
    preprocessing: dict[str, Any],
    training_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Log generic candidates like the PEM path: every candidate is a run; only best is registered."""
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        MLFLOW_TRACKING_DIR.mkdir(parents=True, exist_ok=True)
        tracking_uri = _tracking_uri()
        requested_artifact_location = _experiment_artifact_location(project_id)
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_registry_uri(tracking_uri)
        client = MlflowClient(tracking_uri=tracking_uri, registry_uri=tracking_uri)
        existing_experiment = client.get_experiment_by_name(project_id)
        if existing_experiment is not None and existing_experiment.lifecycle_stage == "deleted":
            client.restore_experiment(existing_experiment.experiment_id)
            existing_experiment = client.get_experiment_by_name(project_id)
        if existing_experiment is None:
            client.create_experiment(project_id, artifact_location=requested_artifact_location)
            existing_experiment = client.get_experiment_by_name(project_id)
        experiment_artifact_location = existing_experiment.artifact_location if existing_experiment is not None else requested_artifact_location
        _assert_demo_mlflow_contract(tracking_uri=tracking_uri, artifact_location=experiment_artifact_location)
        mlflow.set_experiment(project_id)
        registered_name = _registered_model_name_for_project(project_id)
        input_schema_hash = _stable_json_hash(schema.get("inputs", []))
        output_schema_hash = _stable_json_hash(schema.get("outputs", []))
        mlflow_cfg = training_config.get("mlflow", {}) if isinstance(training_config, dict) and isinstance(training_config.get("mlflow"), dict) else {}
        extra_tags = mlflow_cfg.get("extra_tags", {}) if isinstance(mlflow_cfg.get("extra_tags"), dict) else {}
        extra_artifacts = mlflow_cfg.get("extra_artifacts", []) if isinstance(mlflow_cfg.get("extra_artifacts"), list) else []
        common_artifacts = ["metrics_summary.json", "metrics.json", "schema.json", "preprocessing.json", "preprocessing_fitted.json", "feature_map.json", "target_map.json", "ml_preprocessing_report.json", "model_table_preprocessed_manifest.json", "metadata.json", "split_report.json", "predictions.csv", "candidate_comparison.csv", "model.onnx", "training_manifest.json"]
        for artifact_name in extra_artifacts:
            if isinstance(artifact_name, str) and artifact_name not in common_artifacts:
                common_artifacts.append(artifact_name)
        run_ids: dict[str, str] = {}
        registered_version: dict[str, Any] | None = None
        for candidate in candidates:
            model_name = str(candidate["model_name"])
            model_family = str(candidate.get("model_family") or "sklearn")
            is_selected = model_name == best["model_name"]
            with mlflow.start_run(run_name=f"generic_tabular_doe__{model_name}") as run:
                run_ids[model_name] = run.info.run_id
                lifecycle_tags = {
                    "project_id": project_id,
                    "schema_project_id": project_id,
                    "template_id": "generic_tabular_doe",
                    "phase_scope": "generic_tabular_doe",
                    "quality_label": "generic_tabular_doe",
                    "model_family": model_family,
                    "model_name": model_name,
                    "candidate_role": "challenger" if is_selected else "candidate",
                    "lifecycle_role": "challenger" if is_selected else "candidate",
                    "selected_candidate": str(is_selected).lower(),
                    **{str(key): str(value) for key, value in extra_tags.items() if value is not None},
                }
                mlflow.set_tags(lifecycle_tags)
                params = {
                    "project_id": project_id,
                    "model_name": model_name,
                    "model_family": model_family,
                    "input_dim": len(metrics_summary.get("input_order", [])),
                    "output_dim": len(metrics_summary.get("output_order", [])),
                    "split_strategy": preprocessing.get("split_strategy") or (preprocessing.get("split", {}).get("strategy") if isinstance(preprocessing.get("split"), dict) else None) or "generic_contract_split",
                    "selection_metric": metrics_summary.get("selection_metric"),
                }
                if model_name.startswith("ridge_alpha_"):
                    params["alpha"] = model_name.removeprefix("ridge_alpha_")
                if model_name == "mlp":
                    mlp_cfg = training_config.get("mlp", {}) if isinstance(training_config, dict) and isinstance(training_config.get("mlp"), dict) else {}
                    params.update({f"mlp_{key}": json.dumps(value) if isinstance(value, (list, dict)) else value for key, value in mlp_cfg.items() if isinstance(value, (str, int, float, bool, list, dict))})
                mlflow.log_params({key: value for key, value in params.items() if value is not None})
                for split_name, split in candidate.get("split_metrics", {}).items():
                    if split.get("weighted_normalized_rmse") is not None:
                        mlflow.log_metric(f"{split_name}_weighted_normalized_rmse", float(split["weighted_normalized_rmse"]))
                    for output_name, output_metrics in split.get("by_output", {}).items():
                        for metric_name, metric_value in output_metrics.items():
                            if isinstance(metric_value, (int, float)) and np.isfinite(metric_value):
                                mlflow.log_metric(f"{split_name}_{output_name}_{metric_name}", float(metric_value))
                for name in common_artifacts:
                    path = artifact_dir / name
                    if path.exists():
                        mlflow.log_artifact(str(path))
                onnx_path = candidate.get("onnx_path")
                if onnx_path and Path(str(onnx_path)).exists():
                    mlflow.log_artifact(str(onnx_path), artifact_path="onnx")
                    report_path = candidate.get("onnx_report_path")
                    if report_path and Path(str(report_path)).exists():
                        mlflow.log_artifact(str(report_path), artifact_path="onnx")
                mlflow.sklearn.log_model(
                    joblib.load(candidate["model_path"]),
                    name="sklearn_pipeline",
                    registered_model_name=None,
                    metadata={"quality_label": "generic_tabular_doe", "model_family": model_family, "model_name": model_name},
                    tags=lifecycle_tags,
                    model_type=model_family,
                )
                if is_selected:
                    if not onnx_path or not Path(str(onnx_path)).exists():
                        raise FileNotFoundError(f"Selected model {model_name} is missing required ONNX export for MLflow registration")
                    import onnx

                    onnx_model = onnx.load(str(onnx_path), load_external_data=True)
                    mlflow.onnx.log_model(
                        onnx_model,
                        name="onnx_model",
                        registered_model_name=registered_name,
                        metadata={"quality_label": "generic_tabular_doe", "model_family": model_family, "model_name": model_name},
                        tags=lifecycle_tags,
                        model_type=model_family,
                    )
                    versions = client.search_model_versions(f"name = '{registered_name}' and run_id = '{run.info.run_id}'")
                    if versions:
                        version = sorted(versions, key=lambda item: int(item.version))[-1]
                        version_tags = {
                            **lifecycle_tags,
                            "source_run_id": run.info.run_id,
                            "source_experiment_name": project_id,
                            "validation_status": "pending_review",
                            "created_by_pipeline": "true",
                            "selection_metric": str(metrics_summary.get("selection_metric")),
                            "selection_score": str(metrics_summary.get("selection_score")),
                            "input_schema_hash": input_schema_hash,
                            "output_schema_hash": output_schema_hash,
                        }
                        for key, value in version_tags.items():
                            client.set_model_version_tag(registered_name, version.version, key, str(value))
                        client.set_registered_model_alias(registered_name, "challenger", str(version.version))
                        client.set_registered_model_tag(registered_name, "project_id", project_id)
                        client.set_registered_model_tag(registered_name, "model_family", "doe_surrogate")
                        registered_version = {"name": registered_name, "version": str(version.version), "run_id": run.info.run_id, "alias": "challenger"}
        return {"run_ids": run_ids, "registered_model": registered_version}
    except Exception as exc:  # noqa: BLE001 - local-only dev runs may continue without MLflow.
        _write_json(artifact_dir / "mlflow_warning.json", {"warning": str(exc), "generated_at": _now()})
        if _remote_mlflow_required() or _remote_artifacts_required():
            raise
        return {"run_ids": {}, "registered_model": None, "warning": str(exc)}


class GenericMLPOnnxModule:
    """Torch module wrapper exported to ONNX for raw-feature generic MLP inference."""

    @staticmethod
    def build(regressor: "GenericTorchMLPRegressor"):
        import torch
        import torch.nn as nn

        class _Module(nn.Module):
            def __init__(self, fitted: GenericTorchMLPRegressor) -> None:
                super().__init__()
                self.network = fitted.model_
                self.register_buffer("input_median", torch.tensor(fitted.input_imputer_.statistics_, dtype=torch.float32))
                self.register_buffer("input_min", torch.tensor(fitted.input_scaler_.data_min_, dtype=torch.float32))
                self.register_buffer("input_scale", torch.tensor(fitted.input_scaler_.data_max_ - fitted.input_scaler_.data_min_, dtype=torch.float32))
                self.register_buffer("output_mean", torch.tensor(fitted.output_scaler_.mean_, dtype=torch.float32))
                self.register_buffer("output_scale", torch.tensor(fitted.output_scaler_.scale_, dtype=torch.float32))

            def forward(self, raw_features):  # noqa: ANN001 - torch export signature
                clean = torch.where(torch.isnan(raw_features), self.input_median, raw_features)
                scale = torch.where(self.input_scale > 0, self.input_scale, torch.ones_like(self.input_scale))
                scaled_features = (clean - self.input_min) / scale
                scaled_outputs = self.network(scaled_features)
                return scaled_outputs * self.output_scale + self.output_mean

        return _Module(regressor)


class GenericTorchMLPRegressor(BaseEstimator, RegressorMixin):
    """Small sklearn-compatible PyTorch MLP for generic tabular DoE surrogates."""

    def __init__(
        self,
        hidden_layers: tuple[int, ...] = (256, 128, 64),
        activation: str = "silu",
        dropout: float = 0.05,
        learning_rate: float = 0.005,
        weight_decay: float = 1e-4,
        max_epochs: int = 1000,
        patience: int = 200,
        seed: int = 7,
        loss: str = "smooth_l1",
    ) -> None:
        self.hidden_layers = tuple(hidden_layers)
        self.activation = activation
        self.dropout = dropout
        self.learning_rate = learning_rate
        self.weight_decay = weight_decay
        self.max_epochs = max_epochs
        self.patience = patience
        self.seed = seed
        self.loss = loss

    def _activation(self):
        import torch.nn as nn

        name = str(self.activation).lower()
        if name == "gelu":
            return nn.GELU
        if name == "relu":
            return nn.ReLU
        return nn.SiLU

    def _build_model(self, input_dim: int, output_dim: int):
        import torch.nn as nn

        layers: list[Any] = []
        previous = input_dim
        activation = self._activation()
        for hidden in self.hidden_layers:
            layers.append(nn.Linear(previous, int(hidden)))
            layers.append(nn.LayerNorm(int(hidden)))
            layers.append(activation())
            if self.dropout > 0:
                layers.append(nn.Dropout(float(self.dropout)))
            previous = int(hidden)
        layers.append(nn.Linear(previous, output_dim))
        return nn.Sequential(*layers)

    def fit(self, X, y, *, X_validation=None, y_validation=None):  # noqa: N803 - sklearn API
        import torch
        import torch.nn as nn

        torch.manual_seed(int(self.seed))
        x_frame = pd.DataFrame(X).apply(pd.to_numeric, errors="coerce")
        y_frame = pd.DataFrame(y).apply(pd.to_numeric, errors="coerce")
        self.input_imputer_ = SimpleImputer(strategy="median")
        self.input_scaler_ = MinMaxScaler()
        self.output_scaler_ = StandardScaler()
        x_train = self.input_scaler_.fit_transform(self.input_imputer_.fit_transform(x_frame)).astype(np.float32)
        y_train = self.output_scaler_.fit_transform(y_frame).astype(np.float32)
        if X_validation is not None and y_validation is not None and len(X_validation) > 0:
            x_val = self.input_scaler_.transform(self.input_imputer_.transform(pd.DataFrame(X_validation).apply(pd.to_numeric, errors="coerce"))).astype(np.float32)
            y_val_raw = pd.DataFrame(y_validation).apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        elif len(x_train) >= 10:
            rng = np.random.default_rng(int(self.seed))
            indices = np.arange(len(x_train))
            rng.shuffle(indices)
            val_size = max(1, int(round(len(indices) * 0.15)))
            val_idx = indices[:val_size]
            train_idx = indices[val_size:]
            x_val = x_train[val_idx]
            y_val_raw = self.output_scaler_.inverse_transform(y_train[val_idx])
            x_train = x_train[train_idx]
            y_train = y_train[train_idx]
        else:
            x_val = x_train
            y_val_raw = self.output_scaler_.inverse_transform(y_train)
        self.model_ = self._build_model(x_train.shape[1], y_train.shape[1])
        optimizer = torch.optim.AdamW(self.model_.parameters(), lr=float(self.learning_rate), weight_decay=float(self.weight_decay))
        loss_fn = nn.MSELoss() if str(self.loss).lower() == "mse" else nn.SmoothL1Loss()
        x_tensor = torch.tensor(x_train, dtype=torch.float32)
        y_tensor = torch.tensor(y_train, dtype=torch.float32)
        x_val_tensor = torch.tensor(x_val, dtype=torch.float32)
        best_score = float("inf")
        best_state = None
        stale_epochs = 0
        check_every = 10
        for epoch in range(int(self.max_epochs)):
            self.model_.train()
            optimizer.zero_grad()
            loss = loss_fn(self.model_(x_tensor), y_tensor)
            loss.backward()
            optimizer.step()
            if epoch % check_every != 0:
                continue
            self.model_.eval()
            with torch.no_grad():
                pred_raw = self.output_scaler_.inverse_transform(self.model_(x_val_tensor).detach().cpu().numpy())
            score = self._selection_score(y_val_raw, pred_raw)
            if score < best_score:
                best_score = score
                best_state = {key: value.detach().cpu().clone() for key, value in self.model_.state_dict().items()}
                stale_epochs = 0
            else:
                stale_epochs += check_every
            if stale_epochs >= int(self.patience):
                break
        if best_state is not None:
            self.model_.load_state_dict(best_state)
        self.n_features_in_ = x_train.shape[1]
        self.n_outputs_ = y_train.shape[1]
        self.training_report_ = {"best_validation_weighted_normalized_rmse": best_score, "epochs_trained": int(epoch + 1)}
        return self

    @staticmethod
    def _selection_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        y_true = _ensure_2d(np.asarray(y_true, dtype=float))
        y_pred = _ensure_2d(np.asarray(y_pred, dtype=float))
        values = []
        for idx in range(y_true.shape[1]):
            true = y_true[:, idx]
            pred = y_pred[:, idx]
            rmse = float(np.sqrt(mean_squared_error(true, pred)))
            denom = float(np.nanmax(true) - np.nanmin(true)) or 1.0
            values.append(rmse / denom)
        return float(np.mean(values)) if values else float("inf")

    def predict(self, X):  # noqa: N803 - sklearn API
        import torch

        x_frame = pd.DataFrame(X).apply(pd.to_numeric, errors="coerce")
        x_values = self.input_scaler_.transform(self.input_imputer_.transform(x_frame)).astype(np.float32)
        self.model_.eval()
        with torch.no_grad():
            pred_scaled = self.model_(torch.tensor(x_values, dtype=torch.float32)).detach().cpu().numpy()
        return self.output_scaler_.inverse_transform(pred_scaled)


def _export_generic_mlp_onnx(model: GenericTorchMLPRegressor, onnx_path: Path, *, sample_x: pd.DataFrame) -> dict[str, Any]:
    import torch

    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper = GenericMLPOnnxModule.build(model).cpu().eval()
    sample = pd.DataFrame(sample_x).apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
    if len(sample) == 0:
        sample = np.zeros((1, int(model.n_features_in_)), dtype=np.float32)
    dummy_input = torch.tensor(sample[: min(len(sample), 16)], dtype=torch.float32)
    torch.onnx.export(
        wrapper,
        dummy_input,
        str(onnx_path),
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=["raw_features"],
        output_names=["raw_outputs"],
        dynamic_axes={"raw_features": {0: "batch_size"}, "raw_outputs": {0: "batch_size"}},
        dynamo=False,
    )
    try:
        import onnx

        onnx_model = onnx.load(str(onnx_path), load_external_data=True)
        onnx.checker.check_model(onnx_model)
        onnx.save_model(onnx_model, str(onnx_path), save_as_external_data=False)
        sidecar_path = onnx_path.with_suffix(onnx_path.suffix + ".data")
        if sidecar_path.exists():
            sidecar_path.unlink()
    except ImportError:
        pass
    report: dict[str, Any] = {"path": str(onnx_path), "input_name": "raw_features", "output_name": "raw_outputs", "opset_version": 17, "verified": False}
    try:
        import onnxruntime as ort

        session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        onnx_pred = session.run([session.get_outputs()[0].name], {session.get_inputs()[0].name: dummy_input.numpy()})[0]
        python_pred = model.predict(sample[: len(dummy_input)])
        max_abs_diff = float(np.max(np.abs(np.asarray(python_pred, dtype=np.float32) - np.asarray(onnx_pred, dtype=np.float32))))
        report.update({"verified": True, "max_abs_diff": max_abs_diff, "sample_rows": int(len(dummy_input))})
        if max_abs_diff > 1e-4:
            raise RuntimeError(f"Generic MLP ONNX verification failed; max diff {max_abs_diff:.3e} exceeds tolerance")
    except ImportError:
        report["verification_warning"] = "onnxruntime unavailable; ONNX checker passed but runtime parity was not verified"
    return report


def _export_generic_sklearn_onnx(model: Any, onnx_path: Path, *, sample_x: pd.DataFrame) -> dict[str, Any]:
    """Export simple sklearn generic candidates as raw-feature ONNX models.

    The generic training candidates are intentionally constrained to mean baseline,
    linear regression, and ridge wrapped in SimpleImputer + MinMaxScaler. This
    exporter mirrors that fitted pipeline with a tiny Torch module so every
    selected champion-capable candidate can be served through ONNX.
    """
    import torch
    import torch.nn as nn

    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    sample = sample_x.apply(pd.to_numeric, errors="coerce")
    dummy_input = torch.tensor(sample.fillna(0.0).head(min(len(sample), 8)).to_numpy(dtype=np.float32), dtype=torch.float32)
    if dummy_input.numel() == 0:
        dummy_input = torch.zeros((1, sample_x.shape[1]), dtype=torch.float32)

    steps = getattr(model, "named_steps", {})
    imputer = steps.get("simpleimputer")
    scaler = steps.get("minmaxscaler")
    estimator = next((steps.get(name) for name in ("linearregression", "ridge", "dummyregressor") if steps.get(name) is not None), None)
    if estimator is None and isinstance(model, (LinearRegression, Ridge, DummyRegressor)):
        estimator = model
    if estimator is None:
        raise TypeError("Generic sklearn ONNX export only supports linear/ridge/baseline estimators or legacy SimpleImputer + MinMaxScaler pipelines")

    if imputer is not None and scaler is not None:
        input_median = np.asarray(imputer.statistics_, dtype=np.float32)
        input_scale = np.asarray(scaler.scale_, dtype=np.float32)
        input_offset = np.asarray(scaler.min_, dtype=np.float32)
    else:
        input_median = np.zeros((sample_x.shape[1],), dtype=np.float32)
        input_scale = np.ones((sample_x.shape[1],), dtype=np.float32)
        input_offset = np.zeros((sample_x.shape[1],), dtype=np.float32)

    if isinstance(estimator, DummyRegressor):
        constant = np.asarray(estimator.constant_, dtype=np.float32).reshape(1, -1)

        class _SklearnModule(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.register_buffer("constant", torch.tensor(constant, dtype=torch.float32))

            def forward(self, raw_features):  # noqa: ANN001 - torch export signature
                return self.constant.repeat(raw_features.shape[0], 1)

    elif isinstance(estimator, (LinearRegression, Ridge)):
        coef = np.asarray(estimator.coef_, dtype=np.float32)
        if coef.ndim == 1:
            coef = coef.reshape(1, -1)
        intercept = np.asarray(estimator.intercept_, dtype=np.float32).reshape(1, -1)

        class _SklearnModule(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.register_buffer("input_median", torch.tensor(input_median, dtype=torch.float32))
                self.register_buffer("input_scale", torch.tensor(input_scale, dtype=torch.float32))
                self.register_buffer("input_offset", torch.tensor(input_offset, dtype=torch.float32))
                self.register_buffer("coef", torch.tensor(coef, dtype=torch.float32))
                self.register_buffer("intercept", torch.tensor(intercept, dtype=torch.float32))

            def forward(self, raw_features):  # noqa: ANN001 - torch export signature
                clean = torch.where(torch.isnan(raw_features), self.input_median, raw_features)
                scaled_features = clean * self.input_scale + self.input_offset
                return torch.matmul(scaled_features, self.coef.t()) + self.intercept

    else:
        raise TypeError(f"Unsupported generic sklearn estimator for ONNX export: {type(estimator).__name__}")

    module = _SklearnModule().eval()
    with torch.no_grad():
        torch.onnx.export(
            module,
            dummy_input,
            str(onnx_path),
            input_names=["raw_features"],
            output_names=["raw_outputs"],
            dynamic_axes={"raw_features": {0: "batch"}, "raw_outputs": {0: "batch"}},
            opset_version=17,
            dynamo=False,
        )
    try:
        import onnx

        onnx_model = onnx.load(str(onnx_path), load_external_data=True)
        onnx.checker.check_model(onnx_model)
        onnx.save_model(onnx_model, str(onnx_path), save_as_external_data=False)
        sidecar_path = onnx_path.with_suffix(onnx_path.suffix + ".data")
        if sidecar_path.exists():
            sidecar_path.unlink()
    except ImportError:
        pass
    report: dict[str, Any] = {"path": str(onnx_path), "input_name": "raw_features", "output_name": "raw_outputs", "opset_version": 17, "verified": False}
    try:
        import onnxruntime as ort

        session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        onnx_pred = session.run([session.get_outputs()[0].name], {session.get_inputs()[0].name: dummy_input.numpy()})[0]
        python_pred = np.asarray(model.predict(sample.head(len(dummy_input))), dtype=np.float32)
        if python_pred.ndim == 1:
            python_pred = python_pred.reshape(-1, 1)
        max_abs_diff = float(np.max(np.abs(python_pred - np.asarray(onnx_pred, dtype=np.float32))))
        report.update({"verified": True, "max_abs_diff": max_abs_diff, "sample_rows": int(len(dummy_input))})
        if max_abs_diff > 1e-4:
            raise RuntimeError(f"Generic sklearn ONNX verification failed; max diff {max_abs_diff:.3e} exceeds tolerance")
    except ImportError:
        report["verification_warning"] = "onnxruntime unavailable; ONNX checker passed but runtime parity was not verified"
    return report


def _candidate_models(config: dict[str, Any] | None = None) -> list[tuple[str, Any]]:
    config = config or {}
    models: list[tuple[str, Any]] = [("mean_baseline", DummyRegressor(strategy="mean")), ("mvlr", LinearRegression())]
    ridge_alphas = config.get("linear", {}).get("ridge_alphas", [0.01, 0.1, 1.0, 10.0]) if isinstance(config.get("linear"), dict) else [0.01, 0.1, 1.0, 10.0]
    for alpha in ridge_alphas:
        models.append((f"ridge_alpha_{alpha}", Ridge(alpha=float(alpha))))
    mlp_cfg = config.get("mlp", {}) if isinstance(config.get("mlp"), dict) else {}
    if mlp_cfg.get("include", True):
        hidden = tuple(int(v) for v in mlp_cfg.get("hidden_layers", [256, 128, 64]))
        models.append(
            (
                "mlp",
                GenericTorchMLPRegressor(
                    hidden_layers=hidden,
                    activation=str(mlp_cfg.get("activation", "silu")),
                    dropout=float(mlp_cfg.get("dropout", 0.05)),
                    learning_rate=float(mlp_cfg.get("learning_rate", 0.005)),
                    weight_decay=float(mlp_cfg.get("weight_decay", 1e-4)),
                    max_epochs=min(int(mlp_cfg.get("max_epochs", 1000)), 1500),
                    patience=int(mlp_cfg.get("patience", 200)),
                    seed=int(mlp_cfg.get("seed", 7)),
                    loss=str(mlp_cfg.get("loss", "smooth_l1")),
                ),
            )
        )
    return models


def train_generic_project(*, project_id: str, data_dir: Path, artifact_dir: Path, training_config: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = _read_json(artifact_dir / "schema.json")
    preprocessing = _read_json(artifact_dir / "preprocessing.json")
    ml_preprocessed = data_dir / "model_table_preprocessed.csv"
    feature_map_path = data_dir / "feature_map.json"
    target_map_path = data_dir / "target_map.json"
    uses_ml_preprocessing_v1 = ml_preprocessed.exists() and feature_map_path.exists()
    model_table = pd.read_csv(ml_preprocessed if uses_ml_preprocessing_v1 else data_dir / "model_table.csv")
    if uses_ml_preprocessing_v1:
        feature_map = _read_json(feature_map_path)
        target_map = _read_json(target_map_path) if target_map_path.exists() else {}
        inputs = list(feature_map.get("feature_columns") or [])
        outputs = list(target_map.get("target_columns") or [item["name"] for item in schema.get("outputs", [])])
    else:
        inputs = list(preprocessing.get("input_order") or [item["name"] for item in schema.get("inputs", [])])
        outputs = list(preprocessing.get("output_order") or [item["name"] for item in schema.get("outputs", [])])
    train = model_table[model_table["split"] == "train"]
    validation = model_table[model_table["split"] == "validation"]
    test = model_table[model_table["split"] == "test"]
    if train.empty:
        raise ValueError("Generic training requires at least one train row")
    if validation.empty:
        validation = train
    x_train = train[inputs].apply(pd.to_numeric, errors="coerce")
    y_train = train[outputs].apply(pd.to_numeric, errors="coerce")
    x_val = validation[inputs].apply(pd.to_numeric, errors="coerce")
    y_val = validation[outputs].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    candidates = []
    models_dir = artifact_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    split_frames = {"train": train, "validation": validation, "test": test}
    output_units = {item.get("name", ""): item.get("unit", "") for item in schema.get("outputs", []) if isinstance(item, dict)}
    reference = _target_reference(train, outputs, output_units)
    for name, estimator in _candidate_models(training_config):
        if isinstance(estimator, GenericTorchMLPRegressor):
            model = estimator
            model.fit(x_train, y_train, X_validation=x_val, y_validation=y_val)
        else:
            if uses_ml_preprocessing_v1:
                model = estimator
            else:
                model = make_pipeline(SimpleImputer(strategy="median"), MinMaxScaler(), estimator)
            model.fit(x_train, y_train)
        val_pred = np.asarray(model.predict(x_val), dtype=float)
        metric = _metrics(y_val, val_pred, outputs)
        path = models_dir / f"{name}.joblib"
        candidate_payload: dict[str, Any] = {"model_name": name, "model_family": name.split("_")[0], "validation": metric, "model_path": str(path)}
        onnx_path = models_dir / f"{name}.onnx"
        if isinstance(model, GenericTorchMLPRegressor):
            onnx_report = _export_generic_mlp_onnx(model, onnx_path, sample_x=x_val)
        else:
            onnx_report = _export_generic_sklearn_onnx(model, onnx_path, sample_x=x_val)
        _write_json(models_dir / f"{name}_onnx_report.json", onnx_report)
        candidate_payload.update({"onnx_path": str(onnx_path), "onnx_report_path": str(models_dir / f"{name}_onnx_report.json"), "onnx_verified": bool(onnx_report.get("verified")), "onnx_max_abs_diff": onnx_report.get("max_abs_diff")})
        joblib.dump(model, path)
        candidates.append(candidate_payload)
    best = min(candidates, key=lambda c: c["validation"].get("weighted_normalized_rmse") if c["validation"].get("weighted_normalized_rmse") is not None else float("inf"))
    baseline = next((candidate for candidate in candidates if candidate["model_name"] == "mean_baseline"), candidates[0])
    baseline_model = joblib.load(baseline["model_path"])

    split_metrics: dict[str, Any] = {}
    models_payload: dict[str, Any] = {}
    comparison_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        model = joblib.load(candidate["model_path"])
        candidate_splits: dict[str, Any] = {}
        candidate_flat_splits: dict[str, Any] = {}
        for split_name, split_frame in split_frames.items():
            if split_frame.empty:
                continue
            x_split = split_frame[inputs].apply(pd.to_numeric, errors="coerce")
            y_true = split_frame[outputs].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
            y_pred = np.asarray(model.predict(x_split), dtype=float)
            baseline_pred = np.asarray(baseline_model.predict(x_split), dtype=float)
            flat = _metrics(y_true, y_pred, outputs)
            candidate_flat_splits[split_name] = flat
            candidate_splits[split_name] = _ui_split_metrics(y_true, y_pred, baseline_pred, outputs, output_units, reference)
        models_payload[candidate["model_name"]] = {
            "model_name": candidate["model_name"],
            "model_type": candidate.get("model_family", "sklearn"),
            "model_path": candidate["model_path"],
            "onnx_path": candidate.get("onnx_path"),
            "onnx_verified": candidate.get("onnx_verified"),
            "onnx_max_abs_diff": candidate.get("onnx_max_abs_diff"),
            "selection_metric": candidate["validation"].get("weighted_normalized_rmse"),
            "splits": candidate_splits,
        }
        validation_r2_values = [np.nan if m.get("r2") is None else m.get("r2", np.nan) for m in candidate_splits.get("validation", {}).values()]
        test_r2_values = [np.nan if m.get("r2") is None else m.get("r2", np.nan) for m in candidate_splits.get("test", {}).values()]
        validation_mean_r2 = np.nanmean(validation_r2_values) if validation_r2_values and not np.all(np.isnan(validation_r2_values)) else np.nan
        test_mean_r2 = np.nanmean(test_r2_values) if test_r2_values and not np.all(np.isnan(test_r2_values)) else np.nan
        candidate["split_metrics"] = candidate_flat_splits
        comparison_rows.append(
            {
                "model_name": candidate["model_name"],
                "model_type": candidate.get("model_family", "sklearn"),
                "validation_weighted_normalized_rmse": candidate_flat_splits.get("validation", {}).get("weighted_normalized_rmse"),
                "test_weighted_normalized_rmse": candidate_flat_splits.get("test", {}).get("weighted_normalized_rmse"),
                "validation_mean_r2": None if np.isnan(validation_mean_r2) else float(validation_mean_r2),
                "test_mean_r2": None if np.isnan(test_mean_r2) else float(test_mean_r2),
                "selected_challenger": candidate["model_name"] == best["model_name"],
            }
        )
        if candidate["model_name"] == best["model_name"]:
            split_metrics = candidate_flat_splits

    pd.DataFrame(comparison_rows).to_csv(artifact_dir / "candidate_comparison.csv", index=False)
    _write_predictions_csv(project_id=project_id, artifact_dir=artifact_dir, model_table=model_table, inputs=inputs, outputs=outputs, candidates=candidates)
    metrics_summary = {
        "project_id": project_id,
        "generated_at": _now(),
        "phase_scope": "generic_tabular_doe",
        "quality_label": "generic_tabular_doe",
        "best_model": best["model_name"],
        "best_model_name": best["model_name"],
        "best_model_type": best.get("model_family", "sklearn"),
        "selection_metric": "validation_weighted_normalized_rmse",
        "selection_score": best["validation"].get("weighted_normalized_rmse"),
        "target_reference": reference,
        "models": models_payload,
        "candidate_comparison": candidates,
        "split_metrics": split_metrics,
        "input_order": inputs,
        "output_order": outputs,
        "predictions_artifact": str(artifact_dir / "predictions.csv"),
        "generic_training": True,
        "deployment_note": "Generic MVP stores sklearn joblib and logs a challenger run to MLflow when available.",
        "ml_preprocessing": {
            "enabled": uses_ml_preprocessing_v1,
            "contract_version": "mirai-ml-preprocessing-v1" if uses_ml_preprocessing_v1 else preprocessing.get("preprocessing_contract_version", "mirai-generic-0.1"),
            "model_table_preprocessed_sha256": _file_sha256(ml_preprocessed) if uses_ml_preprocessing_v1 else None,
        },
    }
    _write_json(artifact_dir / "metrics_summary.json", metrics_summary)
    _write_json(artifact_dir / "metrics.json", metrics_summary)
    _write_json(artifact_dir / "metadata.json", {"project_id": project_id, "created_at": _now(), "best_model": best["model_name"], "model_artifact": best["model_path"], "onnx_artifact": best.get("onnx_path"), "schema_driven": True})
    if best.get("onnx_path") and Path(str(best["onnx_path"])).exists():
        shutil.copyfile(str(best["onnx_path"]), artifact_dir / "model.onnx")
    mlflow_cfg = training_config.get("mlflow", {}) if isinstance(training_config, dict) and isinstance(training_config.get("mlflow"), dict) else {}
    if mlflow_cfg.get("enabled", True):
        mlflow_result = _log_generic_mlflow(
            project_id=project_id,
            artifact_dir=artifact_dir,
            candidates=candidates,
            best=best,
            metrics_summary=metrics_summary,
            schema=schema,
            preprocessing=preprocessing,
            training_config=training_config,
        )
        metrics_summary["mlflow"] = mlflow_result
        _write_json(artifact_dir / "metrics_summary.json", metrics_summary)
    return metrics_summary
