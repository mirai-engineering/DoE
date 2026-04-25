"""Export a trained tabular MLP checkpoint to ONNX.

This compatibility entrypoint exports the tabular MLP artifact.
The exported model uses:
  input name: features
  input shape: [batch_size, 7]
  output name: predictions
  output shape: [batch_size, 5]
"""

from pathlib import Path

from training.export_onnx import export_checkpoint_to_onnx


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ID = "pem_fuel_cell_demo"


def main() -> None:
    artifact_dir = BACKEND_ROOT / "artifacts" / PROJECT_ID
    checkpoint_path = artifact_dir / "model.pt"
    onnx_path = artifact_dir / "model.onnx"

    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"PyTorch checkpoint not found at {checkpoint_path}. "
            "Run `uv run python training/train_mlp.py` first."
        )

    export_checkpoint_to_onnx(checkpoint_path, onnx_path, verify=True)
    print(f"Wrote ONNX model to {onnx_path}")


if __name__ == "__main__":
    main()
