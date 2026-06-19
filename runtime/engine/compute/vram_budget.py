"""KV-cache-aware VRAM budgeter.

Replaces the crude ``need <= vram*2`` offload heuristic in ``model_lanes`` with a
real plan: weights VRAM (from ``model_quant_profiles.json``) + KV-cache VRAM
(computed from model architecture and the *planned* context) vs. **live free
VRAM** (measured by ``hardware_profiler``). Context is a first-class VRAM cost.

KV-cache formula (plan §2.4):
    KV_bytes = 2 × n_layers × n_kv_heads × head_dim × bytes_per_elem × ctx × parallel
(2 = K and V; bytes_per_elem = 2 f16, 1 q8_0, 0.5 q4_0).

The system runs Ollama with ``OLLAMA_KV_CACHE_TYPE=q8_0`` + flash-attention
(plan §2.3), so the default KV bytes/elem is 1 — verified-near-free headroom.

``plan()`` returns Ollama runtime knobs:
    {num_gpu, num_ctx, low_vram, kv_cache_type, fits, est_vram_mb, ...}
- fully fits  → num_gpu = -1 (Ollama "all layers on GPU")
- partial fit → num_gpu = N (offload the rest to CPU) — slow fallback, not OOM
- nothing     → fits=False, num_gpu=0, recommend remote
"""
from __future__ import annotations

import functools
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# KV-cache element size in bytes per cache dtype.
_KV_BYTES = {"f16": 2.0, "fp16": 2.0, "q8_0": 1.0, "q4_0": 0.5}
# Default KV-cache dtype — matches the global OLLAMA_KV_CACHE_TYPE the system sets.
_DEFAULT_KV_CACHE_TYPE = os.environ.get("OLLAMA_KV_CACHE_TYPE", "q8_0").strip().lower() or "q8_0"

# VRAM safety reserve (driver overhead + activations) on top of weights + KV.
_VRAM_RESERVE_MB = 350

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "model_quant_profiles.json"
# Arch defaults when a model has no explicit arch block (conservative mid-size).
_DEFAULT_ARCH = {"n_layers": 32, "n_kv_heads": 8, "head_dim": 128}


@functools.lru_cache(maxsize=1)
def _profiles() -> dict:
    try:
        with open(_CONFIG_PATH, "r") as fh:
            data = json.load(fh)
        meta = data.get("_meta", {})
        defaults = meta.get("kv_arch_defaults") or _DEFAULT_ARCH
        return {"models": {k: v for k, v in data.items() if not k.startswith("_")},
                "arch_defaults": defaults}
    except Exception as exc:  # noqa: BLE001 — never break budgeting
        logger.warning("vram_budget: profiles load failed (%s); using built-in defaults", exc)
        return {"models": {}, "arch_defaults": _DEFAULT_ARCH}


def _model_profile(model: str) -> dict:
    return _profiles()["models"].get(model, {})


def _arch_for(model: str) -> dict:
    prof = _model_profile(model)
    arch = dict(_profiles()["arch_defaults"])
    arch.update(prof.get("arch") or {})
    return arch


def _weights_vram_mb(model: str, quant: str | None) -> int | None:
    """Weights VRAM for ``model@quant`` from the profile ladder. None if unknown."""
    quants = _model_profile(model).get("quants") or {}
    if not quants:
        return None
    if quant and quant in quants:
        return int(quants[quant])
    # No exact quant match — use the largest entry (most conservative for fit checks).
    return int(max(quants.values()))


def kv_cache_mb(model: str, ctx: int, *, parallel: int = 1,
                kv_cache_type: str | None = None) -> int:
    """KV-cache VRAM (MB) for ``model`` at ``ctx`` context, ``parallel`` slots."""
    arch = _arch_for(model)
    kv_type = (kv_cache_type or _DEFAULT_KV_CACHE_TYPE).lower()
    bytes_per = _KV_BYTES.get(kv_type, 1.0)
    kv_bytes = (2 * arch["n_layers"] * arch["n_kv_heads"] * arch["head_dim"]
                * bytes_per * max(ctx, 1) * max(parallel, 1))
    return int(kv_bytes / (1024 * 1024))


def _live_free_vram_mb() -> int | None:
    try:
        from engine.compute.hardware_profiler import live_vram_mb
        return live_vram_mb()
    except Exception as exc:  # noqa: BLE001
        logger.debug("vram_budget: live VRAM unavailable: %s", exc)
        return None


def plan(model: str, quant: str | None, ctx: int, *, parallel: int = 1,
         free_vram_mb: int | None = None, kv_cache_type: str | None = None) -> dict:
    """Plan an Ollama load for ``model@quant`` at ``ctx``.

    ``free_vram_mb`` overrides the live probe (used by tests / when a caller has a
    fresher reading). Returns a dict of runtime knobs + the budgeting decision.
    """
    kv_type = (kv_cache_type or _DEFAULT_KV_CACHE_TYPE).lower()
    weights = _weights_vram_mb(model, quant)
    kv = kv_cache_mb(model, ctx, parallel=parallel, kv_cache_type=kv_type)
    free = free_vram_mb if free_vram_mb is not None else _live_free_vram_mb()

    base = {
        "model": model, "quant": quant, "num_ctx": int(ctx),
        "kv_cache_type": kv_type, "kv_cache_mb": kv,
        "weights_mb": weights, "parallel": int(parallel),
    }

    if weights is None:
        # Unknown model — cannot budget honestly. Default to full GPU, flag it.
        return {**base, "num_gpu": -1, "low_vram": False, "fits": None,
                "est_vram_mb": None, "free_vram_mb": free, "recommend_remote": False,
                "reason": f"no quant profile for {model}; cannot budget — caller must verify"}

    est = weights + kv + _VRAM_RESERVE_MB
    base["est_vram_mb"] = est

    if free is None:
        # CPU-only / no GPU probe — Ollama decides placement; report as full attempt.
        return {**base, "num_gpu": -1, "low_vram": False, "fits": True,
                "free_vram_mb": None, "recommend_remote": False,
                "reason": "no VRAM probe (CPU-only host); deferring layer placement to Ollama"}

    if est <= free:
        return {**base, "num_gpu": -1, "low_vram": False, "fits": True,
                "free_vram_mb": free, "recommend_remote": False,
                "reason": f"fits: weights {weights} + kv {kv} + reserve {_VRAM_RESERVE_MB} = {est}MB <= free {free}MB"}

    # Doesn't fully fit — compute a partial offload. KV-cache + reserve must live on
    # GPU; remaining VRAM holds whole layers (per-layer ~ weights/n_layers).
    arch = _arch_for(model)
    n_layers = max(int(arch["n_layers"]), 1)
    per_layer_mb = max(weights / n_layers, 1.0)
    vram_for_layers = free - kv - _VRAM_RESERVE_MB
    if vram_for_layers <= 0:
        return {**base, "num_gpu": 0, "low_vram": True, "fits": False,
                "free_vram_mb": free, "recommend_remote": True,
                "reason": f"KV-cache {kv}MB + reserve alone exceeds free {free}MB at ctx {ctx} — "
                          f"lower ctx or use remote compute"}

    num_gpu = int(vram_for_layers // per_layer_mb)
    num_gpu = max(0, min(num_gpu, n_layers))
    return {**base, "num_gpu": num_gpu, "low_vram": True, "fits": False,
            "free_vram_mb": free, "recommend_remote": num_gpu == 0,
            "reason": f"partial offload: {num_gpu}/{n_layers} layers on GPU "
                      f"(weights {weights}MB > free {free}MB after kv {kv}MB) — slow fallback, not OOM"}
