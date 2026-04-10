"""tflite_inference_api.py — FastAPI inference server for a TensorFlow Lite model.

Exposes a REST API that loads a local ``.tflite`` model and runs predictions.
The server works with any TFLite model that accepts a 2-D float input tensor
and returns a 1-D (or 2-D) float output tensor.

Endpoints:
  GET  /health           — liveness check
  GET  /model/info       — model metadata (input/output shapes & dtypes)
  POST /predict          — single-sample inference
  POST /predict/batch    — multi-sample batch inference

TFLite dependency:
  Install the lightweight runtime-only package:
      pip install tflite-runtime
  Or the full TensorFlow package:
      pip install tensorflow

Usage (CLI):
    python -m agents.neural_network.tflite_inference_api \\
        --model models/my_model.tflite \\
        --host 0.0.0.0 \\
        --port 8080

Usage (Python / testing):
    from fastapi.testclient import TestClient
    from agents.neural_network.tflite_inference_api import build_app

    app = build_app("models/my_model.tflite")
    client = TestClient(app)
    response = client.post("/predict", json={"inputs": [[0.1, 0.2, 0.3]]})
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

logger = logging.getLogger("tflite_inference_api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [tflite_inference_api] %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

# ── TFLite import (try lightweight runtime first, fall back to TF) ─────────────

def _load_tflite_interpreter(model_path: str):
    """Load a TFLite interpreter from *model_path*.

    Tries ``tflite_runtime`` first (smaller package), then falls back to
    ``tensorflow.lite`` from the full TF package.  Raises ``ImportError``
    if neither is installed.
    """
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"TFLite model not found: {model_path}")

    try:
        from tflite_runtime.interpreter import Interpreter  # type: ignore
        interpreter = Interpreter(model_path=str(path))
        logger.info("TFLite interpreter loaded via tflite_runtime")
    except ImportError:
        try:
            import tensorflow as tf  # type: ignore
            interpreter = tf.lite.Interpreter(model_path=str(path))
            logger.info("TFLite interpreter loaded via tensorflow.lite")
        except ImportError as exc:
            raise ImportError(
                "No TFLite runtime found. Install with: "
                "pip install tflite-runtime   OR   pip install tensorflow"
            ) from exc

    interpreter.allocate_tensors()
    return interpreter


# ─────────────────────────────────────────────────────────────────────────────
# TFLite runner
# ─────────────────────────────────────────────────────────────────────────────

class TFLiteRunner:
    """Thin wrapper around a TFLite Interpreter with shape/dtype validation.

    Args:
        model_path: Path to the ``.tflite`` model file.
    """

    def __init__(self, model_path: str) -> None:
        self._interpreter = _load_tflite_interpreter(model_path)
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()
        self.model_path = model_path
        logger.info(
            "Model info — inputs: %s  outputs: %s",
            [(d["name"], d["shape"].tolist(), d["dtype"].__name__) for d in self._input_details],
            [(d["name"], d["shape"].tolist(), d["dtype"].__name__) for d in self._output_details],
        )

    # ── metadata ─────────────────────────────────────────────────────────────

    @property
    def input_details(self) -> List[Dict[str, Any]]:
        return [
            {
                "name":  d["name"],
                "shape": d["shape"].tolist(),
                "dtype": d["dtype"].__name__,
                "index": d["index"],
            }
            for d in self._input_details
        ]

    @property
    def output_details(self) -> List[Dict[str, Any]]:
        return [
            {
                "name":  d["name"],
                "shape": d["shape"].tolist(),
                "dtype": d["dtype"].__name__,
                "index": d["index"],
            }
            for d in self._output_details
        ]

    # ── inference ─────────────────────────────────────────────────────────────

    def run(self, inputs: np.ndarray) -> np.ndarray:
        """Run inference on *inputs* (shape and dtype are validated).

        Args:
            inputs: NumPy array compatible with the model's first input tensor.
                    For batch inference pass ``(N, feature_dim)``; for a single
                    sample pass ``(1, feature_dim)`` or ``(feature_dim,)`` and
                    it will be expanded automatically.

        Returns:
            NumPy array from the model's first output tensor.
        """
        if inputs.ndim == 1:
            inputs = inputs[np.newaxis, :]

        detail = self._input_details[0]
        expected_dtype = detail["dtype"]
        inputs = inputs.astype(expected_dtype)

        # Resize input tensor if the model uses dynamic shapes (first dim -1)
        expected_shape = detail["shape"]
        if expected_shape[0] == -1 or expected_shape[0] != inputs.shape[0]:
            self._interpreter.resize_input_tensor(
                detail["index"],
                [inputs.shape[0]] + list(expected_shape[1:]),
            )
            self._interpreter.allocate_tensors()

        self._interpreter.set_tensor(detail["index"], inputs)
        self._interpreter.invoke()
        output = self._interpreter.get_tensor(self._output_details[0]["index"])
        return output

    def predict_proba(self, inputs: np.ndarray) -> np.ndarray:
        """Run inference and apply softmax if the output looks like raw logits."""
        raw = self.run(inputs)
        if raw.ndim == 2 and raw.shape[1] > 1:
            # Apply softmax for multi-class logits
            shifted = raw - raw.max(axis=1, keepdims=True)
            exp = np.exp(shifted)
            return exp / exp.sum(axis=1, keepdims=True)
        # Binary sigmoid or already-normalised output — return as-is
        return raw


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic request / response models
# ─────────────────────────────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    """Request body for single or multi-sample prediction.

    ``inputs`` should be a 2-D list: ``[[f1, f2, …], [f1, f2, …], …]``.
    A flat 1-D list ``[f1, f2, …]`` is also accepted and treated as one sample.
    """

    inputs: List[Any]
    return_proba: bool = False  # if True, return softmax probabilities

    @field_validator("inputs")
    @classmethod
    def _check_nonempty(cls, v):
        if not v:
            raise ValueError("inputs must not be empty")
        return v


class PredictResponse(BaseModel):
    predictions: List[Any]
    probabilities: Optional[List[List[float]]] = None
    latency_ms: float


# ─────────────────────────────────────────────────────────────────────────────
# App factory
# ─────────────────────────────────────────────────────────────────────────────

def build_app(model_path: str) -> FastAPI:
    """Create and return the FastAPI application.

    Args:
        model_path: Path to the ``.tflite`` model file.

    Returns:
        A configured :class:`FastAPI` application instance.
    """
    app = FastAPI(
        title="TFLite Inference API",
        description="FastAPI inference server for a local TensorFlow Lite model.",
        version="1.0.0",
    )

    # Lazy-load the runner so the app can be imported without a model file
    _runner: Optional[TFLiteRunner] = None

    def _get_runner() -> TFLiteRunner:
        nonlocal _runner
        if _runner is None:
            _runner = TFLiteRunner(model_path)
        return _runner

    # ── endpoints ─────────────────────────────────────────────────────────────

    @app.get("/health", tags=["system"])
    def health_check():
        """Liveness probe — returns 200 if the server is running."""
        return JSONResponse({"status": "ok", "model": model_path})

    @app.get("/model/info", tags=["system"])
    def model_info():
        """Return input/output tensor metadata from the TFLite model."""
        runner = _get_runner()
        return JSONResponse({
            "model_path":    runner.model_path,
            "inputs":        runner.input_details,
            "outputs":       runner.output_details,
        })

    @app.post("/predict", response_model=PredictResponse, tags=["inference"])
    def predict(req: PredictRequest):
        """Run inference on one or more input samples.

        - Send a 2-D list for a batch: ``{"inputs": [[…], […]]}``
        - Send a 1-D list for a single sample: ``{"inputs": [0.1, 0.2, …]}``
        """
        runner = _get_runner()
        try:
            arr = np.array(req.inputs, dtype=np.float32)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid inputs: {exc}") from exc

        t0 = time.perf_counter()
        try:
            output = runner.run(arr)
        except Exception as exc:
            logger.error("Inference error: %s", exc)
            raise HTTPException(status_code=500, detail=f"Inference failed: {exc}") from exc
        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Predicted class indices
        if output.ndim == 2 and output.shape[1] > 1:
            preds = output.argmax(axis=1).tolist()
        else:
            preds = output.flatten().tolist()

        proba = None
        if req.return_proba and output.ndim == 2 and output.shape[1] > 1:
            proba_arr = runner.predict_proba(arr)
            proba = proba_arr.tolist()

        return PredictResponse(
            predictions=preds,
            probabilities=proba,
            latency_ms=round(latency_ms, 3),
        )

    @app.post("/predict/batch", response_model=PredictResponse, tags=["inference"])
    def predict_batch(req: PredictRequest):
        """Alias for ``/predict`` — explicitly handles batched inputs."""
        return predict(req)

    return app


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Start the TFLite FastAPI inference server."
    )
    parser.add_argument("--model", required=True, help="Path to .tflite model file")
    parser.add_argument("--host",  default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port",  type=int, default=8080, help="Bind port (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev only)")
    args = parser.parse_args()

    try:
        import uvicorn  # type: ignore
    except ImportError:
        print("ERROR: uvicorn is required. Install with: pip install uvicorn", flush=True)
        raise SystemExit(1)

    app = build_app(args.model)
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    _cli()
