"""Thin LLM caller for use by tools.

Priority:
  1. Ollama (local) — always tried first
  2. Groq (free cloud, OpenAI-compatible) — fallback when Ollama unavailable

No Anthropic or OpenAI dependencies. Add GROQ_API_KEY to ~/.ai-employee/.env
to enable cloud fallback. Get a free key at https://console.groq.com
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
TIMEOUT = 60


def call_llm_for_tool(prompt: str) -> str | None:
    """Call the available LLM. Ollama first, Groq as cloud fallback. Returns text or None."""
    if _ollama_reachable():
        result = _call_ollama(prompt)
        if result:
            return result
    if GROQ_API_KEY:
        return _call_groq(prompt)
    return None


def _ollama_reachable() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _call_ollama(prompt: str) -> str | None:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip() or None
    except Exception as exc:
        logger.warning("ollama call failed: %s", exc)
        return None


def _call_groq(prompt: str) -> str | None:
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
        "temperature": 0.4,
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip() or None
    except Exception as exc:
        logger.warning("groq call failed: %s", exc)
        return None
