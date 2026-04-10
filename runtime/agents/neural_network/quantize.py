"""quantize.py — Model quantization and optimization utilities.

Provides three complementary quantization paths:

  1. **Dynamic quantization** (PyTorch) — post-training, weights quantized to
     int8 at model-load time; activations quantized at runtime.  Zero
     calibration data needed.  Best for CPU inference on Linear/LSTM models.

  2. **Static quantization** (PyTorch) — post-training, both weights and
     activations quantized to int8 using a calibration dataset.  Requires a
     representative set of inputs.

  3. **TFLite export with quantization** — converts a PyTorch model to ONNX,
     then to TFLite with optional float16 or dynamic-range int8 quantization.
     Requires ``onnx``, ``onnxruntime``, and ``tensorflow``.

Usage (CLI):
    # Dynamic quantization of an existing PyTorch checkpoint
    python -m agents.neural_network.quantize \\
        --mode dynamic \\
        --checkpoint models/ai_employee_nn.pth \\
        --output models/ai_employee_nn_int8.pth

    # Static quantization with calibration data
    python -m agents.neural_network.quantize \\
        --mode static \\
        --checkpoint models/ai_employee_nn.pth \\
        --calib-data data/processed/val.npz \\
        --output models/ai_employee_nn_static.pth

    # Export to TFLite (float16)
    python -m agents.neural_network.quantize \\
        --mode tflite \\
        --checkpoint models/ai_employee_nn.pth \\
        --tflite-quant float16 \\
        --output models/ai_employee_nn.tflite

Usage (Python API):
    from agents.neural_network.quantize import (
        dynamic_quantize,
        static_quantize,
        benchmark_model,
    )

    int8_model = dynamic_quantize(fp32_model)
    results = benchmark_model(int8_model, sample_inputs, n_runs=200)
    print(results)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("quantize")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [quantize] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

try:
    import torch
    import torch.nn as nn
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

# ─────────────────────────────────────────────────────────────────────────────
# 1. Dynamic Quantization (PyTorch)
# ─────────────────────────────────────# ─────────────────────────────────────

def dynamic_quantize(
    model: "nn.Module",
    layer_types: Optional[Tuple] = None,
    dtype: "torch.dtype | None" = None,
) -> "nn.Module":
    """Apply PyTorch dynamic post-training quantization.

    Weights are quantized to int8; activations are quantized on the fly during
    inference.  No calibration data required.

    Args:
        model:       A PyTorch model in evaluation mode.
        layer_types: Tuple of module types to quantize. Defaults to
                     ``{nn.Linear}`` (covers all fully-connected layers).
        dtype:       Quantization dtype. Defaults to ``torch.qint8``.

    Returns:
        The dynamically-quantized model (a new object; original is unmodified).
    """
    if not _HAS_TORCH:
        raise ImportError("torch is required. Install with: pip install torch")

    if layer_types is None:
        layer_types = {nn.Linear}
    if dtype is None:
        dtype = torch.qint8

    model.eval()
    quantized = torch.quantization.quantize_dynamic(
        model,
        qconfig_spec=layer_types,
        dtype=dtype,
    )
    logger.info(
        "Dynamic quantization complete. Layer types: %s  dtype: %s",
        layer_types, dtype,
    )
    return quantized


# ─────────────────────────────────────────────────────────────────────────────
# 2. Static Quantization (PyTorch)
# ─────────────────────────────────────────────────────────────────────────────

class _QuantizableWrapper(nn.Module):
    """Wraps an existing model with QuantStub / DeQuantStub for static quant."""

    def __init__(self, model: "nn.Module") -> None:
        super().__init__()
        self.quant = torch.quantization.QuantStub()
        self.model = model
        self.dequant = torch.quantization.DeQuantStub()

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        x = self.quant(x)
        x = self.model(x)
        return self.dequant(x)


def static_quantize(
    model: "nn.Module",
    calibration_data: "torch.Tensor",
    backend: str = "qnnpack",
) -> "nn.Module":
    """Apply PyTorch static post-training quantization.

    Both weights and activations are quantized to int8 based on statistics
    collected during a calibration pass over *calibration_data*.

    Args:
        model:            A PyTorch ``nn.Module`` in evaluation mode.
        calibration_data: A representative input tensor ``(N, feature_dim)``
                          used to collect activation statistics.
        backend:          Quantization backend — ``"qnnpack"`` (ARM/mobile) or
                          ``"fbgemm"`` (x86 server).

    Returns:
        The statically-quantized model.
    """
    if not _HAS_TORCH:
        raise ImportError("torch is required. Install with: pip install torch")

    torch.backends.quantized.engine = backend

    wrapper = _QuantizableWrapper(model)
    wrapper.eval()

    # Assign qconfig
    wrapper.qconfig = torch.quantization.get_default_qconfig(backend)
    torch.quantization.prepare(wrapper, inplace=True)

    # Calibration pass
    logger.info("Running calibration pass with %d samples…", len(calibration_data))
    with torch.no_grad():
        batch_size = 64
        for i in range(0, len(calibration_data), batch_size):
            batch = calibration_data[i : i + batch_size]
            wrapper(batch)

    # Convert
    torch.quantization.convert(wrapper, inplace=True)
    logger.info("Static quantization complete (backend=%s).", backend)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# 3. TFLite Export
# ─────────────────────────────────────────────────────────────────────────────

def export_to_tflite(
    model: "nn.Module",
    input_shape: Tuple[int, ...],
    output_path: str,
    quant_type: str = "float16",
    calibration_data: Optional["torch.Tensor"] = None,
) -> str:
    """Export a PyTorch model to a ``.tflite`` file via ONNX.

    Pipeline:  PyTorch → ONNX → TensorFlow SavedModel → TFLite

    Args:
        model:            PyTorch model to export.
        input_shape:      Shape of a single input sample, e.g. ``(64,)``.
        output_path:      Path for the output ``.tflite`` file.
        quant_type:       ``"none"`` (fp32), ``"float16"``, or ``"int8"``
                          (dynamic range).
        calibration_data: Used only for ``"int8"`` quantization — a
                          representative input tensor.

    Returns:
        Absolute path to the saved ``.tflite`` file.
    """
    if not _HAS_TORCH:
        raise ImportError("torch is required.")

    try:
        import onnx  # type: ignore  # noqa: F401
    except ImportError as exc:
        raise ImportError("onnx is required for TFLite export. Run: pip install onnx") from exc

    try:
        import onnx2tf  # type: ignore  # noqa: F401
        _USE_ONNX2TF = True
    except ImportError:
        _USE_ONNX2TF = False

    try:
        import tensorflow as tf  # type: ignore
    except ImportError as exc:
        raise ImportError("tensorflow is required for TFLite export. Run: pip install tensorflow") from exc

    output_path = str(Path(output_path).with_suffix(".tflite"))
    tmp_onnx = str(Path(output_path).with_suffix(".onnx"))

    model.eval()
    dummy_input = torch.zeros(1, *input_shape)

    # Step 1: export to ONNX
    torch.onnx.export(
        model,
        dummy_input,
        tmp_onnx,
        opset_version=13,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
    )
    logger.info("ONNX model exported → %s", tmp_onnx)

    # Step 2: ONNX → TF SavedModel
    import subprocess
    saved_model_dir = tmp_onnx.replace(".onnx", "_tf_saved_model")
    result = subprocess.run(
        [sys.executable, "-m", "onnx_tf.convert", "-i", tmp_onnx, "-o", saved_model_dir],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"onnx-tf conversion failed:\n{result.stderr}\n\n"
            "Install with: pip install onnx-tf"
        )
    logger.info("TF SavedModel written → %s", saved_model_dir)

    # Step 3: TF SavedModel → TFLite
    converter = tf.lite.TFLiteConverter.from_saved_model(saved_model_dir)

    if quant_type == "float16":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]
        logger.info("Using float16 quantization.")
    elif quant_type == "int8":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        if calibration_data is not None:
            calib_np = calibration_data.numpy()

            def representative_dataset():
                for i in range(len(calib_np)):
                    yield [calib_np[i : i + 1].astype(np.float32)]

            converter.representative_dataset = representative_dataset
            converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
            converter.inference_input_type = tf.int8
            converter.inference_output_type = tf.int8
        logger.info("Using int8 dynamic-range quantization.")

    tflite_model = converter.convert()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as fh:
        fh.write(tflite_model)
    logger.info("TFLite model saved → %s  (%.1f KB)", output_path, len(tflite_model) / 1024)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
# Benchmarking & size comparison
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_model(
    model: "nn.Module",
    sample_inputs: "torch.Tensor",
    n_runs: int = 100,
    device: str = "cpu",
) -> Dict[str, Any]:
    """Measure inference latency and throughput for a PyTorch model.

    Args:
        model:         The model to benchmark (will be put in eval mode).
        sample_inputs: A batch of inputs ``(N, …)`` used for all benchmark runs.
        n_runs:        Number of forward passes to time.
        device:        Device to run on (``"cpu"`` or ``"cuda"``).

    Returns:
        Dict with ``mean_ms``, ``std_ms``, ``min_ms``, ``max_ms``,
        ``throughput_samples_per_sec``, and ``batch_size``.
    """
    if not _HAS_TORCH:
        raise ImportError("torch is required.")

    model.eval()
    model.to(device)
    inputs = sample_inputs.to(device)

    # Warm-up
    with torch.no_grad():
        for _ in range(min(10, n_runs)):
            model(inputs)

    latencies: List[float] = []
    with torch.no_grad():
        for _ in range(n_runs):
            t0 = time.perf_counter()
            model(inputs)
            latencies.append((time.perf_counter() - t0) * 1000.0)

    arr = np.array(latencies)
    batch_size = len(inputs)
    mean_ms = float(arr.mean())
    return {
        "batch_size":               batch_size,
        "n_runs":                   n_runs,
        "mean_ms":                  round(mean_ms, 3),
        "std_ms":                   round(float(arr.std()), 3),
        "min_ms":                   round(float(arr.min()), 3),
        "max_ms":                   round(float(arr.max()), 3),
        "throughput_samples_per_sec": round(batch_size / (mean_ms / 1000.0), 1),
    }


def compare_models(
    fp32_model: "nn.Module",
    quantized_model: "nn.Module",
    sample_inputs: "torch.Tensor",
    n_runs: int = 100,
) -> Dict[str, Any]:
    """Benchmark both models and return a side-by-side comparison.

    Returns:
        Dict with keys ``fp32``, ``quantized``, and ``speedup``.
    """
    fp32_results = benchmark_model(fp32_model, sample_inputs, n_runs)
    quant_results = benchmark_model(quantized_model, sample_inputs, n_runs)
    speedup = fp32_results["mean_ms"] / max(quant_results["mean_ms"], 1e-9)

    return {
        "fp32":      fp32_results,
        "quantized": quant_results,
        "speedup":   round(speedup, 3),
    }


def model_size_kb(model: "nn.Module") -> float:
    """Return the approximate in-memory parameter size of *model* in kilobytes."""
    if not _HAS_TORCH:
        raise ImportError("torch is required.")
    total_bytes = sum(
        p.nelement() * p.element_size()
        for p in model.parameters()
    )
    return round(total_bytes / 1024.0, 2)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli() -> None:
    if not _HAS_TORCH:
        print("ERROR: PyTorch is not installed. Run: pip install torch", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Quantize a PyTorch model (dynamic / static / TFLite export)."
    )
    parser.add_argument(
        "--mode", required=True, choices=["dynamic", "static", "tflite"],
        help="Quantization mode",
    )
    parser.add_argument("--checkpoint", required=True, help="Path to the .pth checkpoint")
    parser.add_argument("--output",     required=True, help="Output path (.pth or .tflite)")
    parser.add_argument("--calib-data", default=None,  help="Path to .npz calibration data (static/tflite int8)")
    parser.add_argument("--tflite-quant", default="float16", choices=["none", "float16", "int8"],
                        help="TFLite quantization type (only used with --mode tflite)")
    parser.add_argument("--input-size", type=int, default=64, help="Model input feature size")
    parser.add_argument("--hidden-sizes", type=int, nargs="+", default=[128, 64])
    parser.add_argument("--output-size", type=int, default=8)
    parser.add_argument("--benchmark", action="store_true", help="Run a benchmark after quantization")
    parser.add_argument("--bench-runs", type=int, default=100)
    args = parser.parse_args()

    # Load original model
    _HERE = Path(__file__).resolve()
    sys.path.insert(0, str(_HERE.parents[2]))  # runtime/agents → sys.path
    from agents.neural_network.model import AIEmployeeNet  # noqa: E402

    fp32_model = AIEmployeeNet(
        input_size=args.input_size,
        hidden_sizes=args.hidden_sizes,
        output_size=args.output_size,
    )
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    state = checkpoint.get("model_state_dict", checkpoint)
    fp32_model.load_state_dict(state)
    fp32_model.eval()
    logger.info("Loaded FP32 model from %s  (%.1f KB)", args.checkpoint, model_size_kb(fp32_model))

    # Load calibration data if provided
    calib_tensor: Optional[torch.Tensor] = None
    if args.calib_data:
        data = np.load(args.calib_data)
        calib_tensor = torch.tensor(data["X"], dtype=torch.float32)

    # Quantize
    if args.mode == "dynamic":
        q_model = dynamic_quantize(fp32_model)
        torch.save(q_model.state_dict(), args.output)
        logger.info("Saved dynamic-quantized model → %s  (%.1f KB)", args.output, model_size_kb(q_model))

    elif args.mode == "static":
        if calib_tensor is None:
            parser.error("--calib-data is required for static quantization")
        q_model = static_quantize(fp32_model, calib_tensor)
        torch.save(q_model.state_dict(), args.output)
        logger.info("Saved static-quantized model → %s", args.output)

    elif args.mode == "tflite":
        out = export_to_tflite(
            fp32_model,
            input_shape=(args.input_size,),
            output_path=args.output,
            quant_type=args.tflite_quant,
            calibration_data=calib_tensor,
        )
        logger.info("TFLite model exported → %s", out)

    # Optional benchmark
    if args.benchmark and args.mode in ("dynamic", "static"):
        sample = torch.randn(32, args.input_size)
        comparison = compare_models(fp32_model, q_model, sample, n_runs=args.bench_runs)
        print("\n── Benchmark Results ──────────────────────────────────────────")
        print(f"  FP32  : mean={comparison['fp32']['mean_ms']:.3f} ms  "
              f"throughput={comparison['fp32']['throughput_samples_per_sec']:.0f} samp/s")
        print(f"  INT8  : mean={comparison['quantized']['mean_ms']:.3f} ms  "
              f"throughput={comparison['quantized']['throughput_samples_per_sec']:.0f} samp/s")
        print(f"  Speedup: {comparison['speedup']:.2f}×")
        print(f"  FP32 size : {model_size_kb(fp32_model):.1f} KB")
        if hasattr(q_model, "parameters"):
            print(f"  INT8 size : {model_size_kb(q_model):.1f} KB")


if __name__ == "__main__":
    _cli()
