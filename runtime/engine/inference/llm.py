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
    payload = {
        "model": chosen_model,
        "prompt": full_prompt,
        "system": system,
        "stream": False,
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
