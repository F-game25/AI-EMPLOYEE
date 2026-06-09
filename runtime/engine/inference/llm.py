"""Engine — Inference: LLM generation and embedding via Ollama or ai_router."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from core.model_routing import select_model_route

# ── Model size map (params_b) for installed Ollama models ─────────────────────
# Used by _build_ollama_options to compute num_gpu layers.
_MODEL_PARAMS_B: dict[str, float] = {
    "llama3.2":              3.2,
    "llama3.2:latest":       3.2,
    "gemma3":                4.0,
    "gemma3:latest":         4.0,
    "qwen2.5:7b-instruct":   7.0,
    "qwen2.5-coder:14b":    14.0,
    "llava":                 7.0,
    "llava:latest":          7.0,
    "qwen3.5":               7.0,
    "nomic-embed-text":      0.1,
}

logger = logging.getLogger("engine.inference")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
DEFAULT_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
DEFAULT_TIMEOUT = int(os.environ.get("ENGINE_INFERENCE_TIMEOUT", "120"))


@dataclass(frozen=True)
class RouteDecision:
    tier: str
    estimated_tokens: int
    chosen_model: str


def _route_model(prompt: str, context: str | None, requested_model: str | None) -> RouteDecision:
    default_model = requested_model or DEFAULT_MODEL
    route = select_model_route(prompt=prompt, context=context, requested_route=None, default_route="auto")
    is_long = route.tier == "long" and route.model_route == "wavefield"
    return RouteDecision(
        tier="long" if is_long else "short",
        estimated_tokens=route.estimated_tokens,
        chosen_model=(route.force_model or default_model) if is_long else default_model,
    )

# Optional ai_router integration — resolved lazily on first call to avoid
# import-time path-manipulation side effects and allow AI_HOME to be set
# after this module is imported.
_ai_router_loaded = False
_AI_ROUTER = False
_query_ai = None  # type: ignore[assignment]


def _ensure_ai_router() -> None:
    """Attempt to import ai_router once; result is cached globally."""
    global _ai_router_loaded, _AI_ROUTER, _query_ai
    if _ai_router_loaded:
        return
    _ai_router_loaded = True
    try:
        import pathlib as _pathlib
        import sys as _sys

        _ai_home = _pathlib.Path(
            os.environ.get("AI_HOME", str(_pathlib.Path.home() / ".ai-employee"))
        )
        _router_path = str(_ai_home / "agents" / "ai-router")
        if _router_path not in _sys.path:
            _sys.path.insert(0, _router_path)
        from ai_router import query_ai_for_agent as _qai  # type: ignore

        _AI_ROUTER = True
        _query_ai = _qai
    except ImportError:
        _AI_ROUTER = False
        _query_ai = None


def _ollama_post(endpoint: str, payload: dict, timeout: int) -> dict:
    """POST to the Ollama API and return parsed JSON."""
    url = f"{OLLAMA_HOST.rstrip('/')}/{endpoint.lstrip('/')}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama not reachable at {OLLAMA_HOST}: {exc}") from exc


# ── Lifecycle/quant gate (WS8b) ──────────────────────────────────────────────
# Per-model real GGUF quant, cached so we hit /api/show once per model.
_quant_cache: dict[str, str | None] = {}


def _ollama_quant(model: str) -> str | None:
    """Real GGUF quant of an installed model via /api/show (cached per-model)."""
    if model in _quant_cache:
        return _quant_cache[model]
    quant = None
    try:
        info = _ollama_post("/api/show", {"name": model}, 10)
        quant = (info.get("details") or {}).get("quantization_level")
    except Exception:  # noqa: BLE001
        quant = None
    _quant_cache[model] = quant
    return quant


def _build_ollama_options(model: str) -> dict:
    """Compute Ollama inference options: num_gpu (layers on GPU), num_thread, low_vram.

    Uses the existing disk_offload_config() from turbo_quant and _free_vram_mb()
    from lifecycle_manager to compute how many layers to keep on GPU vs offload
    to CPU/RAM. This stops OOM crashes on models that exceed VRAM (e.g. 14B on 8 GB).
    """
    try:
        from neural_brain.models.lifecycle_manager import _free_vram_mb
        import importlib, pathlib as _pl, sys as _sys
        _tq_path = str(_pl.Path(__file__).parents[2] / "agents" / "turbo-quant")
        if _tq_path not in _sys.path:
            _sys.path.insert(0, _tq_path)
        _tq = importlib.import_module("turbo_quant")
        disk_offload_config = _tq.disk_offload_config
        select_quant = _tq.select_quant

        free_mb = _free_vram_mb()
        params_b = _MODEL_PARAMS_B.get(model, 0.0)
        # Fallback: strip tag and retry
        if params_b == 0.0:
            base = model.split(":")[0]
            params_b = _MODEL_PARAMS_B.get(base, 0.0)

        if params_b <= 0.0:
            # Unknown model — use safe defaults
            return {
                "num_thread": min(8, os.cpu_count() or 4),
                "num_batch": 256 if (free_mb or 0) < 4000 else 512,
            }

        quant = select_quant()
        cfg = disk_offload_config(params_b, quant)

        # RAM pressure check — offloaded layers live in RAM, so check available RAM too.
        # If system RAM < 3 GB free, cap GPU offload to avoid paging to disk.
        import psutil
        try:
            ram_free_gb = psutil.virtual_memory().available / (1024 ** 3)
        except Exception:  # noqa: BLE001
            ram_free_gb = 999.0  # unknown → no restriction
        ram_constrained = ram_free_gb < 3.0

        gpu_layers = cfg.get("gpu_layers_suggested", 0)
        # Under RAM pressure, prefer keeping more layers on GPU (less CPU offload work).
        if ram_constrained and gpu_layers > 0:
            total_layers = max(1, int(params_b * 4))  # ~4 layers per B param
            gpu_layers = min(total_layers, gpu_layers + max(2, int(total_layers * 0.1)))

        opts: dict = {
            "num_thread": min(8, os.cpu_count() or 4),
            "num_batch": 256 if (free_mb or 0) < 4000 else 512,
            "num_gpu": gpu_layers,
        }

        if free_mb is not None and free_mb < 2000:
            opts["low_vram"] = True

        logger.debug(
            "ollama_options model=%s params_b=%.1f quant=%s gpu_layers=%s free_mb=%s low_vram=%s",
            model, params_b, quant, gpu_layers, free_mb, opts.get("low_vram"),
        )
        return opts

    except Exception as exc:  # noqa: BLE001
        logger.debug("_build_ollama_options skipped: %s", exc)
        return {}


_CORE_MODELS = [DEFAULT_MODEL, DEFAULT_EMBED_MODEL]

def warm_core_models() -> None:
    """Send keep_alive=-1 to core models so Ollama never evicts them between calls."""
    for m in _CORE_MODELS:
        try:
            _ollama_post("/api/generate", {"model": m, "prompt": " ", "keep_alive": -1, "stream": False}, 30)
            logger.info("model_warm model=%s keep_alive=-1", m)
        except Exception as exc:  # noqa: BLE001
            logger.debug("model_warm skipped model=%s: %s", m, exc)


def _ollama_unloader(model: str):
    """Callable that drops *model* from VRAM (keep_alive=0 forces an unload)."""
    def _unload():
        try:
            _ollama_post("/api/generate", {"model": model, "prompt": " ",
                                           "keep_alive": 0, "stream": False}, 15)
        except Exception:  # noqa: BLE001
            pass
    return _unload


def _enforce_lifecycle(model: str):
    """Register model + evict-to-fit if not already resident. Returns (mgr, was_loaded).

    Robust by design: any failure returns (None, False) and the caller proceeds —
    inference must never break because the lifecycle manager is unavailable. Does NOT
    take the global heavy lock on the hot path; only ensure_room when not resident.
    """
    try:
        from neural_brain.models.lifecycle_manager import get_lifecycle_manager
        mgr = get_lifecycle_manager()
        e = mgr.register(model, "LLM", "ollama", unloader=_ollama_unloader(model))
        if not e.loaded:
            if not os.environ.get("MODEL_FABRIC_DEV_OVERRIDE"):
                q = _ollama_quant(model)
                if q and ("f16" in q.lower() or "f32" in q.lower() or q.upper() in ("FP16", "FP32")):
                    logger.warning("llm model %s is full-precision (%s) — not quantised", model, q)
            mgr.ensure_room("LLM")
        return mgr, e.loaded
    except Exception as exc:  # noqa: BLE001
        logger.debug("lifecycle gate skipped: %s", exc)
        return None, False


def generate(
    prompt: str,
    system: str = "You are a helpful AI assistant.",
    context: str | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Generate a text completion.

    Tries ai_router first (if available), then falls back to direct Ollama.

    Args:
        prompt:  The user prompt.
        system:  System instruction for the model.
        context: Optional extra context prepended to the prompt.
        model:   Model name override (uses OLLAMA_MODEL env var by default).
        timeout: HTTP timeout in seconds.

    Returns:
        Generated text as a plain string.
    """
    full_prompt = f"{context}\n\n{prompt}" if context else prompt
    decision = _route_model(prompt=prompt, context=context, requested_model=model)
    chosen_model = decision.chosen_model
    logger.info(
        "llm_route tier=%s estimated_tokens=%s model=%s",
        decision.tier,
        decision.estimated_tokens,
        chosen_model,
    )

    _ensure_ai_router()
    if _AI_ROUTER and _query_ai is not None:
        try:
            result: Any = _query_ai(
                agent_type="engine",
                prompt=full_prompt,
                system_prompt=system,
            )
            if isinstance(result, dict):
                # ai_router returns {"answer": "...", "provider": "...", "error": ...}
                if result.get("error") or not result.get("answer"):
                    raise RuntimeError(f"ai_router error: {result.get('error')}")
                return str(result["answer"])
            return str(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_router failed (%s) — falling back to direct Ollama", exc)

    mgr, _ = _enforce_lifecycle(chosen_model)
    offload_opts = _build_ollama_options(chosen_model)
    payload = {
        "model": chosen_model,
        "prompt": full_prompt,
        "system": system,
        "stream": False,
        **({"options": offload_opts} if offload_opts else {}),
    }
    import time as _t
    t0 = _t.time()
    response = _ollama_post("/api/generate", payload, timeout)
    if mgr is not None:
        try:
            mgr.mark_loaded(chosen_model, load_ms=(_t.time() - t0) * 1000,
                            quant=_ollama_quant(chosen_model))
        except Exception:  # noqa: BLE001
            pass
    return response.get("response", "")


def embed(
    text: str,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[float]:
    """Return a vector embedding for *text* via Ollama.

    Args:
        text:    Input string to embed.
        model:   Embedding model name (uses OLLAMA_EMBED_MODEL env var by default).
        timeout: HTTP timeout in seconds.

    Returns:
        List of floats representing the embedding vector, or empty list on error.
    """
    chosen_model = model or DEFAULT_EMBED_MODEL
    try:
        payload = {"model": chosen_model, "prompt": text}
        response = _ollama_post("/api/embeddings", payload, timeout)
        return response.get("embedding", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed failed: %s", exc)
        return []
