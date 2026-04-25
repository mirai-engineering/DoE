from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import torch
import torch.nn as nn


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.model import TabularMLP  # noqa: E402
from training.export_onnx import export_checkpoint_to_onnx  # noqa: E402
from training.generate_synthetic_data import (  # noqa: E402
    DATA_PATH,
    PROJECT_ID,
    SCHEMA,
    SCHEMA_PATH,
    generate_dataset,
    write_dataset,
    write_schema,
)


ARTIFACT_DIR = BACKEND_ROOT / "artifacts" / PROJECT_ID
PREPROCESSING_PATH = ARTIFACT_DIR / "preprocessing.json"
METADATA_PATH = ARTIFACT_DIR / "metadata.json"
CHECKPOINT_PATH = ARTIFACT_DIR / "model.pt"
ONNX_PATH = ARTIFACT_DIR / "model.onnx"


def _load_csv(path: Path, input_names: list[str], output_names: list[str]) -> tuple[np.ndarray, np.ndarray]:
    features: list[list[float]] = []
    targets: list[list[float]] = []
    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            features.append([float(row[name]) for name in input_names])
            targets.append([float(row[name]) for name in output_names])
    if not features:
        raise ValueError(f"No rows found in {path}")
    return np.asarray(features, dtype=np.float32), np.asarray(targets, dtype=np.float32)


def _scale_minmax(values: np.ndarray, minimum: np.ndarray, maximum: np.ndarray) -> np.ndarray:
    scale = np.where(maximum > minimum, maximum - minimum, 1.0)
    return ((values - minimum) / scale).astype(np.float32)


def _inverse_minmax(values: np.ndarray, minimum: np.ndarray, maximum: np.ndarray) -> np.ndarray:
    scale = np.where(maximum > minimum, maximum - minimum, 1.0)
    return (values * scale + minimum).astype(np.float32)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _maybe_log_mlflow(params: dict, metrics: dict[str, float], artifacts: list[Path]) -> None:
    try:
        import mlflow
    except ImportError:
        return

    with mlflow.start_run(run_name=f"{PROJECT_ID}_mlp"):
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        for artifact in artifacts:
            if artifact.exists():
                mlflow.log_artifact(str(artifact))


def _ensure_training_data() -> None:
    write_schema()
    if DATA_PATH.exists():
        return
    rows = generate_dataset()
    write_dataset(rows)


def _train_model(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    *,
    input_dim: int,
    output_dim: int,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    seed: int,
) -> tuple[TabularMLP, dict[str, float]]:
    torch.manual_seed(seed)
    np.random.seed(seed)

    model = TabularMLP(input_dim=input_dim, output_dim=output_dim, hidden_dims=(64, 64, 32), dropout=0.02)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=1e-5)
    criterion = nn.MSELoss()

    train_x = torch.from_numpy(x_train)
    train_y = torch.from_numpy(y_train)
    val_x = torch.from_numpy(x_val)
    val_y = torch.from_numpy(y_val)

    n_train = train_x.shape[0]
    for epoch in range(1, epochs + 1):
        model.train()
        permutation = torch.randperm(n_train)
        batch_losses: list[float] = []
        for start in range(0, n_train, batch_size):
            indices = permutation[start : start + batch_size]
            prediction = model(train_x[indices])
            loss = criterion(prediction, train_y[indices])

            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            batch_losses.append(float(loss.item()))

        if epoch == 1 or epoch % 25 == 0 or epoch == epochs:
            model.eval()
            with torch.no_grad():
                val_loss = float(criterion(model(val_x), val_y).item())
            print(
                f"epoch={epoch:03d} train_mse={np.mean(batch_losses):.6f} "
                f"val_mse={val_loss:.6f}"
            )

    model.eval()
    with torch.no_grad():
        train_mse = float(criterion(model(train_x), train_y).item())
        val_mse = float(criterion(model(val_x), val_y).item())

    return model, {"train_scaled_mse": train_mse, "val_scaled_mse": val_mse}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a tabular MLP surrogate for the demo project.")
    parser.add_argument("--epochs", type=int, default=175)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    args = parser.parse_args()

    if not 0.05 <= args.validation_fraction <= 0.5:
        raise ValueError("--validation-fraction must be between 0.05 and 0.5")

    _ensure_training_data()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    schema_artifact_path = ARTIFACT_DIR / "schema.json"
    if SCHEMA_PATH.resolve() != schema_artifact_path.resolve():
        shutil.copyfile(SCHEMA_PATH, schema_artifact_path)

    input_names = [item["name"] for item in SCHEMA["inputs"]]
    output_names = [item["name"] for item in SCHEMA["outputs"]]
    x, y = _load_csv(DATA_PATH, input_names, output_names)

    rng = np.random.default_rng(args.seed)
    indices = rng.permutation(len(x))
    val_size = int(round(len(x) * args.validation_fraction))
    val_indices = indices[:val_size]
    train_indices = indices[val_size:]

    x_train_raw = x[train_indices]
    y_train_raw = y[train_indices]
    x_val_raw = x[val_indices]
    y_val_raw = y[val_indices]

    input_min = np.asarray([float(item["min"]) for item in SCHEMA["inputs"]], dtype=np.float32)
    input_max = np.asarray([float(item["max"]) for item in SCHEMA["inputs"]], dtype=np.float32)
    output_min = y_train_raw.min(axis=0).astype(np.float32)
    output_max = y_train_raw.max(axis=0).astype(np.float32)

    x_train = _scale_minmax(x_train_raw, input_min, input_max)
    x_val = _scale_minmax(x_val_raw, input_min, input_max)
    y_train = _scale_minmax(y_train_raw, output_min, output_max)
    y_val = _scale_minmax(y_val_raw, output_min, output_max)

    preprocessing = {
        "version": "0.1.0",
        "input_order": input_names,
        "output_order": output_names,
        "input_scaler": {
            "method": "minmax",
            "min": input_min.tolist(),
            "max": input_max.tolist(),
        },
        "output_scaler": {
            "method": "minmax",
            "min": output_min.tolist(),
            "max": output_max.tolist(),
            "clip": True,
        },
    }
    _write_json(PREPROCESSING_PATH, preprocessing)

    model, scaled_metrics = _train_model(
        x_train,
        y_train,
        x_val,
        y_val,
        input_dim=len(input_names),
        output_dim=len(output_names),
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        seed=args.seed,
    )

    with torch.no_grad():
        val_pred_scaled = model(torch.from_numpy(x_val)).numpy()
    val_pred = _inverse_minmax(val_pred_scaled, output_min, output_max)
    mae_by_output = np.mean(np.abs(val_pred - y_val_raw), axis=0)
    rmse_by_output = np.sqrt(np.mean((val_pred - y_val_raw) ** 2, axis=0))

    metrics = dict(scaled_metrics)
    for index, output_name in enumerate(output_names):
        metrics[f"val_mae_{output_name}"] = float(mae_by_output[index])
        metrics[f"val_rmse_{output_name}"] = float(rmse_by_output[index])
    metrics["val_mean_mae"] = float(mae_by_output.mean())
    metrics["val_mean_rmse"] = float(rmse_by_output.mean())

    checkpoint = {
        "model_state_dict": model.state_dict(),
        "model_config": {
            "input_dim": len(input_names),
            "output_dim": len(output_names),
            "hidden_dims": [64, 64, 32],
            "dropout": 0.02,
        },
        "input_order": input_names,
        "output_order": output_names,
        "metrics": metrics,
    }
    torch.save(checkpoint, CHECKPOINT_PATH)

    export_checkpoint_to_onnx(CHECKPOINT_PATH, ONNX_PATH, verify=True)

    metadata = {
        "project_id": PROJECT_ID,
        "display_name": SCHEMA["display_name"],
        "model_version": f"{PROJECT_ID}_mlp_v0.1",
        "model_type": "tabular_mlp",
        "input_dim": len(input_names),
        "output_dim": len(output_names),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "source_data": str(DATA_PATH.relative_to(BACKEND_ROOT)),
        "metrics": metrics,
    }
    _write_json(METADATA_PATH, metadata)

    _maybe_log_mlflow(
        {
            "project_id": PROJECT_ID,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "seed": args.seed,
        },
        metrics,
        [CHECKPOINT_PATH, ONNX_PATH, PREPROCESSING_PATH, METADATA_PATH, ARTIFACT_DIR / "schema.json"],
    )

    print("Validation metrics:")
    for output_name in output_names:
        print(
            f"  {output_name}: mae={metrics[f'val_mae_{output_name}']:.4f} "
            f"rmse={metrics[f'val_rmse_{output_name}']:.4f}"
        )
    print(f"Wrote checkpoint to {CHECKPOINT_PATH}")
    print(f"Wrote ONNX model to {ONNX_PATH}")
    print(f"Wrote preprocessing to {PREPROCESSING_PATH}")
    print(f"Wrote metadata to {METADATA_PATH}")


if __name__ == "__main__":
    main()
