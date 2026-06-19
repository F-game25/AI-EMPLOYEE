"""Local, OFFLINE image generation via stable-diffusion.cpp (sd-cli).

The default content-creation engine runs entirely on-device — no network at
generation time. Faithful port of the vendored Open-Generative-AI local path
(vendor/open-generative-ai/localInference.reference.js): build sd-cli args by
model type and spawn the binary.

Config (no hardcoded paths):
  SD_CLI_BIN     — path to the sd-cli binary (else vendored runtime/vendor/local-ai
                   /bin, else `sd-cli`/`sd` on PATH).
  SD_MODELS_DIR  — where GGUF/safetensors models live (default ~/.ai-employee/models/sdcpp).

Honest: if the engine binary or the model file is missing it raises a clear
LocalGenError telling the operator to run scripts/setup_local_image_gen.py — it
NEVER silently falls back to a cloud API.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from content.media_models import (
    default_local_model_id, get_local_model, zimage_aux)

logger = logging.getLogger("content.local_image_gen")


class LocalGenError(RuntimeError):
    """Engine/model missing, timeout, or sd-cli failure — never silent."""


def _home() -> Path:
    return Path(os.getenv("AI_HOME") or (Path.home() / ".ai-employee"))


def models_dir() -> Path:
    return Path(os.getenv("SD_MODELS_DIR") or (_home() / "models" / "sdcpp"))


def _bin_candidates():
    if (env := os.getenv("SD_CLI_BIN")):
        yield Path(env)
    repo = Path(__file__).resolve().parents[2]
    base = repo / "runtime" / "vendor" / "local-ai" / "bin"
    yield base / "sd-cli"
    yield base / "sd"
    for name in ("sd-cli", "sd"):
        if (w := shutil.which(name)):
            yield Path(w)


def find_binary() -> Path | None:
    for c in _bin_candidates():
        if c and c.exists() and os.access(c, os.X_OK):
            return c
    return None


def is_available() -> bool:
    return find_binary() is not None


def _build_args(model: dict, model_path: Path, out_path: Path, prompt: str, *,
                negative: str | None, width: int, height: int, seed: int,
                steps: int | None, cfg: float | None) -> list[str]:
    mtype = model.get("type")
    model_flag = "--diffusion-model" if mtype in ("z-image", "flux") else "-m"
    steps = int(steps or model.get("default_steps") or 20)
    cfg = float(cfg if cfg is not None else (model.get("default_guidance") or 7.0))
    sampler = model.get("sampler") or "euler_a"
    seed = int(seed) if seed and int(seed) != -1 else int(time.time()) % 2147483647
    args = [model_flag, str(model_path), "-p", prompt, "-o", str(out_path),
            "--steps", str(steps), "-H", str(height), "-W", str(width),
            "--cfg-scale", str(cfg), "--seed", str(seed),
            "--sampling-method", sampler, "-v"]
    if negative:
        args += ["-n", negative]
    if mtype == "z-image":
        aux = zimage_aux()
        md = models_dir()
        args += ["--llm", str(md / aux.get("llm", {}).get("filename", "")),
                 "--vae", str(md / aux.get("vae", {}).get("filename", ""))]
        if model.get("scheduler"):
            args += ["--scheduler", model["scheduler"]]
    elif mtype == "sdxl":
        args += ["--sd-version", "sdxl"]
    elif mtype == "sd2":
        args += ["--sd-version", "sd2"]
    elif mtype == "flux":
        args += ["--flux"]
    return args


def generate(prompt: str, *, model_id: str | None = None, width: int = 512,
             height: int = 512, negative: str | None = None, seed: int = -1,
             steps: int | None = None, cfg: float | None = None,
             timeout: float = 600.0) -> dict[str, Any]:
    """Generate an image locally. Returns {ok, provider, model, path, ...}.

    Raises LocalGenError if the engine/model is missing or generation fails.
    """
    prompt = str(prompt or "").strip()
    if not prompt:
        raise LocalGenError("prompt required")

    binary = find_binary()
    if not binary:
        raise LocalGenError(
            "Local image engine (sd-cli / stable-diffusion.cpp) is not installed. "
            "Run `python3 scripts/setup_local_image_gen.py` or set SD_CLI_BIN. "
            "Offline generation requires the local binary — refusing to call a cloud API.")

    model = get_local_model(model_id) if model_id else get_local_model(default_local_model_id())
    if not model:
        raise LocalGenError(f"unknown local model '{model_id}'")

    model_path = models_dir() / model["filename"]
    if not model_path.exists():
        raise LocalGenError(
            f"model file missing: {model_path} — run "
            f"`python3 scripts/setup_local_image_gen.py --model {model['id']}`")

    out_dir = _home() / "state" / "media"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gen-{int(time.time() * 1000)}.png"

    args = _build_args(model, model_path, out_path, prompt, negative=negative,
                       width=width, height=height, seed=seed, steps=steps, cfg=cfg)
    env = {**os.environ,
           "LD_LIBRARY_PATH": f"{binary.parent}:{os.environ.get('LD_LIBRARY_PATH', '')}"}
    logger.info("sd-cli %s", " ".join(args))
    t0 = time.time()
    try:
        proc = subprocess.run([str(binary), *args], env=env, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise LocalGenError(f"local generation timed out after {timeout}s")
    if proc.returncode != 0 or not out_path.exists():
        tail = (proc.stderr or proc.stdout or "")[-400:]
        raise LocalGenError(f"sd-cli failed (code {proc.returncode}): {tail}")

    return {"ok": True, "provider": "local", "engine": "stable-diffusion.cpp",
            "model": model["id"], "path": str(out_path), "width": width,
            "height": height, "latency_s": round(time.time() - t0, 1)}
