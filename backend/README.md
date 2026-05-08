# Mirai DoE Engine Backend — Training

Scripts for generating synthetic tabular data, training surrogate MLP models, and exporting them to ONNX for use by the API.

## Pipeline

```
data/synthetic/{project_id}.csv
                                  ┌──────────────────────────   ┐
artifacts/{project_id}/           │  generate_synthetic_data.py │
  schema.json                     │                             │
  preprocessing.json  ←────────── │    train_mlp.py             │
  model.pt             ←───────── │                             │
  model.onnx ←─────────────────── │    export_onnx.py           │
  metadata.json                   └────────────────────────────-┘
```

The runtime (`backend/app/services/`) only reads the ONNX model and preprocessing params at startup. PyTorch is **not needed in production**.

## Setup

```bash
cd backend
uv sync --locked
```

Run tests:

```bash
uv run pytest
```

## Generate Data

```bash
uv run python training/generate_synthetic_data.py
```

Writes `data/synthetic/{project_id}.csv` and `artifacts/{project_id}/schema.json`.

## Train

```bash
uv run python training/train_mlp.py
```

Reads the CSV, trains an MLP surrogate, and writes 5 artifacts to `artifacts/{project_id}/`:

| File | Purpose |
|---|---|
| `schema.json` | Input/output definitions |
| `preprocessing.json` | Min-max normalization params |
| `model.pt` | PyTorch checkpoint (for reproducibility) |
| `model.onnx` | Inference artifact (used at runtime) |
| `metadata.json` | Training metrics (MAE/RMSE per KPI) |

To re-export ONNX from an existing PyTorch checkpoint:

```bash
uv run python training/export_onnx.py
```

## Train Options

```bash
uv run python training/train_mlp.py --epochs 200 --batch-size 128 --learning-rate 1e-3
```

Defaults: 175 epochs, batch size 256, lr 1e-3, seed 7, 80/20 train/val split.