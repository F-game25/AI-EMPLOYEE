"""Guarded LLM access for lifecycle engines.

LLM enrichment is opt-in (``FORGE_LIFECYCLE_LLM=1``) and every call is fully
guarded: engines must produce complete results from deterministic heuristics
when the LLM is disabled, unavailable, or fails. Tests run with it disabled.
"""
from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}


def llm_enabled() -> bool:
    return os.environ.get("FORGE_LIFECYCLE_LLM", "").strip().lower() in _TRUTHY


def try_generate(prompt: str, system: str = "You are a precise software engineering assistant.") -> str | None:
    """Return LLM text or None. Never raises; never required for correctness."""
    if not llm_enabled():
        return None
    try:
        from engine.api import generate
        out = generate(prompt, system=system)
        return out if isinstance(out, str) and out.strip() else None
    except Exception:
        return None
