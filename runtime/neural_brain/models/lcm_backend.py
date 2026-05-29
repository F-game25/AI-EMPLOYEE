"""Latent Consistency Model — local image generation via diffusers.

Local-first: runs a true LCM (SimianLuo/LCM_Dreamshaper_v7) on the local GPU in
4 inference steps. No external API. Pipeline is loaded once and cached. Falls back
to an external A1111/ComfyUI endpoint if LCM_BACKEND_URL is set (opt-in remote).
Generated images are written to state/generated_images/ and returned as both a
local path and a base64 data URL.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_PIPE = None          # cached diffusers pipeline
_PIPE_ERR: str | None = None
_MODEL_ID = os.getenv("LCM_MODEL_ID", "SimianLuo/LCM_Dreamshaper_v7")


def _artifacts_dir() -> Path:
    d = Path(os.getenv("AI_EMPLOYEE_REPO_DIR", ".")) / "state" / "generated_images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_pipe():
    """Lazy-load + cache the LCM pipeline. Returns (pipe, error)."""
    global _PIPE, _PIPE_ERR
    if _PIPE is not None or _PIPE_ERR is not None:
        return _PIPE, _PIPE_ERR
    try:
        import torch
        from diffusers import DiffusionPipeline
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        pipe = DiffusionPipeline.from_pretrained(_MODEL_ID, torch_dtype=dtype, safety_checker=None)
        pipe.to(device)
        if device == "cuda":
            try:
                pipe.enable_attention_slicing()
            except Exception:  # noqa: BLE001
                pass
        _PIPE = pipe
        logger.info("LCM pipeline loaded: %s on %s", _MODEL_ID, device)
    except Exception as e:  # noqa: BLE001
        _PIPE_ERR = str(e)
        logger.error("LCM pipeline load failed: %s", e)
    return _PIPE, _PIPE_ERR


def unload() -> bool:
    """Free the diffusion pipeline from GPU/RAM. Called by the lifecycle manager."""
    global _PIPE, _PIPE_ERR
    if _PIPE is None:
        return False
    try:
        del _PIPE
    except Exception:  # noqa: BLE001
        pass
    _PIPE, _PIPE_ERR = None, None
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass
    return True


def is_loaded() -> bool:
    return _PIPE is not None


def _remote_generate(backend_url: str, request: dict) -> dict:
    import httpx
    payload = {
        "prompt": request.get("prompt", ""),
        "negative_prompt": request.get("negative_prompt", ""),
        "num_inference_steps": min(int(request.get("steps", 4)), 50),
        "guidance_scale": request.get("guidance_scale", 1.0),
        "height": request.get("height", 512),
        "width": request.get("width", 512),
    }
    resp = httpx.post(f"{backend_url}/api/generate", json=payload, timeout=120.0)
    resp.raise_for_status()
    result = resp.json()
    return {"status": "success", "output": result.get("image"),
            "provider": "lcm-remote", "model": backend_url}


def route_lcm(request: dict) -> dict:
    """Generate an image from a text prompt. Local diffusers by default."""
    prompt = (request.get("prompt") or "").strip()
    if not prompt:
        return {"status": "error", "arch": "LCM", "error": "Missing prompt"}

    backend_url = os.getenv("LCM_BACKEND_URL")
    if backend_url:
        try:
            return {**_remote_generate(backend_url, request), "arch": "LCM"}
        except Exception as e:  # noqa: BLE001
            logger.warning("LCM remote failed (%s); trying local", e)

    pipe, err = _load_pipe()
    if pipe is None:
        return {"status": "unavailable", "arch": "LCM", "available": False,
                "reason": f"diffusers pipeline unavailable: {err}"}

    try:
        import torch
        steps = max(1, min(int(request.get("steps", 4)), 12))   # LCM needs few steps
        guidance = float(request.get("guidance_scale", 1.0))
        h = int(request.get("height", 512))
        w = int(request.get("width", 512))
        gen = None
        if request.get("seed") is not None:
            dev = "cuda" if torch.cuda.is_available() else "cpu"
            gen = torch.Generator(dev).manual_seed(int(request["seed"]))
        t0 = time.time()
        image = pipe(prompt=prompt, num_inference_steps=steps, guidance_scale=guidance,
                     height=h, width=w, generator=gen).images[0]
        latency_ms = (time.time() - t0) * 1000

        fname = f"lcm_{int(time.time())}.png"
        fpath = _artifacts_dir() / fname
        image.save(fpath)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        return {"status": "success", "arch": "LCM", "provider": "diffusers-local",
                "model": _MODEL_ID, "steps": steps, "latency_ms": latency_ms,
                "image_path": str(fpath), "image": f"data:image/png;base64,{b64}",
                "output": str(fpath)}
    except Exception as e:  # noqa: BLE001
        logger.error("route_lcm generation failed: %s", e)
        return {"status": "error", "arch": "LCM", "error": str(e)}
