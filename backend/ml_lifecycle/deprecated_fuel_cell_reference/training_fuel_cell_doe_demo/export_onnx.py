from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import torch


BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ml_lifecycle.training.common.model_definitions import TabularMLP  # noqa: E402


def export_model_to_onnx(
    model: torch.nn.Module,
    onnx_path: Path,
    *,
    input_dim: int,
    opset_version: int = 17,
    verify: bool = True,
) -> None:
    model = model.cpu().eval()
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    dummy_input = torch.randn(1, input_dim, dtype=torch.float32)

    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_path),
        export_params=True,
        opset_version=opset_version,
        do_constant_folding=True,
        input_names=["features"],
        output_names=["predictions"],
        dynamic_axes={
            "features": {0: "batch_size"},
            "predictions": {0: "batch_size"},
        },
        dynamo=False,
    )

    try:
        import onnx

        onnx_model = onnx.load(str(onnx_path), load_external_data=True)
        onnx.save_model(onnx_model, str(onnx_path), save_as_external_data=False)
        sidecar_path = onnx_path.with_suffix(onnx_path.suffix + ".data")
        if sidecar_path.exists():
            sidecar_path.unlink()
    except ImportError:
        pass

    if verify:
        verify_onnx_export(model, onnx_path, dummy_input)


def verify_onnx_export(model: torch.nn.Module, onnx_path: Path, dummy_input: torch.Tensor) -> None:
    try:
        import onnx
        import onnxruntime as ort
    except ImportError:
        print("onnx or onnxruntime is unavailable; skipping ONNX verification")
        return

    onnx_model = onnx.load(str(onnx_path))
    onnx.checker.check_model(onnx_model)

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    onnx_output = session.run([output_name], {input_name: dummy_input.numpy()})[0]

    with torch.no_grad():
        torch_output = model(dummy_input).numpy()

    max_diff = float(np.abs(torch_output - onnx_output).max())
    print(f"Verified ONNX export at {onnx_path}; max PyTorch/ONNX diff={max_diff:.3e}")
    if max_diff > 1e-4:
        raise RuntimeError(f"ONNX verification failed; max diff {max_diff:.3e} exceeds tolerance")


def export_checkpoint_to_onnx(
    checkpoint_path: Path,
    onnx_path: Path,
    *,
    opset_version: int = 17,
    verify: bool = True,
) -> None:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    config = checkpoint["model_config"]
    model = TabularMLP(
        input_dim=int(config["input_dim"]),
        output_dim=int(config["output_dim"]),
        hidden_dims=tuple(config["hidden_dims"]),
        dropout=float(config.get("dropout", 0.0)),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    export_model_to_onnx(
        model,
        onnx_path,
        input_dim=int(config["input_dim"]),
        opset_version=opset_version,
        verify=verify,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a trained tabular MLP checkpoint to ONNX.")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Path to trained PyTorch checkpoint",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write ONNX model",
    )
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args()

    export_checkpoint_to_onnx(
        args.checkpoint,
        args.output,
        opset_version=args.opset,
        verify=not args.no_verify,
    )
    print(f"Wrote ONNX model to {args.output}")


if __name__ == "__main__":
    main()
