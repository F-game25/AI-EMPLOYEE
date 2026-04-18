"""Engine — Inference: LLM generation and embedding via Ollama or ai_router."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("engine.inference")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
DEFAULT_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
DEFAULT_TIMEOUT = int(os.environ.get("ENGINE_INFERENCE_TIMEOUT", "120"))

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
    chosen_model = model or DEFAULT_MODEL

    _ensure_ai_router()
    if _AI_ROUTER and _query_ai is not None:
        try:
            result: Any = _query_ai(
                agent="engine",
                prompt=full_prompt,
                system=system,
                model=chosen_model,
            )
            if isinstance(result, dict):
                return str(result.get("response") or result.get("content") or result)
            return str(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_router failed (%s) — falling back to direct Ollama", exc)

    payload = {
        "model": chosen_model,
        "prompt": full_prompt,
        "system": system,
        "stream": False,
    }
    response = _ollama_post("/api/generate", payload, timeout)
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
