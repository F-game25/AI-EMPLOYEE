"""local_chat — minimal localhost-only LLM call for skills that must keep data on
the box (the default model is Qwythos). NEVER calls an external provider: it only
ever hits the loopback Ollama host, and returns None (graceful) on any failure so a
skill can fall back deterministically. Reasoning models answer directly (think=False).
"""
from __future__ import annotations

import json
import os
import urllib.request

_OLLAMA_HOST = (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
_LOCAL_MODEL = os.getenv("OLLAMA_MODEL") or "qwythos:q4"
_TIMEOUT_S = int(os.getenv("LOCAL_LLM_TIMEOUT_S", "120"))


def _is_loopback(host: str) -> bool:
    return host.startswith(("http://localhost", "http://127.0.0.1", "https://localhost", "https://127.0.0.1"))


def local_chat(prompt: str, system: str | None = None, num_predict: int = 512,
               temperature: float = 0.4) -> "str | None":
    """Return the model's reply text, or None if the local model is unavailable.
    Hard loopback guard → the prompt can never leave this machine."""
    if not _is_loopback(_OLLAMA_HOST):
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": str(system)})
    messages.append({"role": "user", "content": str(prompt)})
    body = json.dumps({
        "model": _LOCAL_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,  # reasoning models answer directly instead of into a hidden channel
        "options": {"temperature": temperature, "num_predict": int(num_predict)},
    }).encode("utf-8")
    try:
        req = urllib.request.Request(f"{_OLLAMA_HOST}/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = (data.get("message") or {}).get("content") or ""
        return text.strip() or None
    except Exception:
        return None


def model_name() -> str:
    return _LOCAL_MODEL
