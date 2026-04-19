"""Engine API — Central abstraction layer for AI Employee's internal engine.

This module is the *only* surface that agents and the orchestrator should call.
All internal complexity (LLM routing, memory persistence, input normalisation)
is hidden behind the functions below.

Usage::

    from engine.api import process_input, generate, embed, memory_store, memory_retrieve

Functions
---------
process_input(raw_input)
    Normalise raw user/agent input and extract intent, entities, and task type.
    Formerly known as ``openclaw_process`` in hermes_agent.py.

generate(prompt, context, system, model, timeout)
    Generate a text completion via the configured LLM backend (Ollama / ai_router).

embed(text, model, timeout)
    Return a vector embedding for the given text.

memory_store(key, value, namespace)
    Persist a value in the engine's internal key/value memory store.

memory_retrieve(key, namespace)
    Retrieve a previously stored value.

memory_search(query, namespace, top_k)
    Substring search across memory entries.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .inference.llm import generate as _generate
from .inference.llm import embed as _embed
from .memory.store import store as _store
from .memory.store import retrieve as _retrieve
from .memory.store import search as _search
from .utilities.helpers import now_iso  # re-exported for convenience

logger = logging.getLogger("engine.api")

# ── Input task-type vocabulary ─────────────────────────────────────────────────

_TASK_TYPES: dict[str, list[str]] = {
    "search":   ["find", "search", "look up", "research", "discover"],
    "generate": ["write", "create", "generate", "compose", "draft"],
    "analyse":  ["analyse", "analyze", "evaluate", "assess", "review", "compare"],
    "code":     ["code", "script", "program", "implement", "debug", "refactor"],
    "summarise":["summarise", "summarize", "brief", "overview", "tldr"],
    "plan":     ["plan", "strategy", "roadmap", "steps", "how to", "outline"],
    "lead":     ["lead", "prospect", "outreach", "email", "contact"],
    "data":     ["data", "report", "metrics", "stats", "numbers"],
}

# Words to exclude from automatic entity detection
_ENTITY_STOP = {
    "The", "This", "That", "When", "What", "How", "Why", "Who",
    "Create", "Write", "Find", "Build", "Make", "Show",
}


# ══════════════════════════════════════════════════════════════════════════════
# Input processing (formerly openclaw_process)
# ══════════════════════════════════════════════════════════════════════════════

def process_input(raw_input: str | dict) -> dict:
    """Normalise raw input and extract intent, entities, and task type.

    This function is the internal replacement for the former
    ``openclaw_process`` function.  Agents should always pass incoming
    requests through here before sending them to an LLM.

    Args:
        raw_input: A plain string or a dict with at least a ``text`` or
                   ``task`` key.

    Returns:
        A normalised task descriptor::

            {
                "text":         str,        # cleaned input text
                "task_type":    str,        # detected task category
                "intent":       str,        # short intent phrase (≤8 words)
                "entities":     list[str],  # key entities / nouns (≤10)
                "input_format": str,        # "text" | "json"
                "original":     ...         # original raw_input
            }
    """
    # ── Normalise input ───────────────────────────────────────────────────────
    if isinstance(raw_input, dict):
        text = str(raw_input.get("text") or raw_input.get("task") or raw_input)
        input_format = "json"
    else:
        text = str(raw_input).strip()
        input_format = "text"

    text = text.strip()

    # ── Detect task type ──────────────────────────────────────────────────────
    text_lower = text.lower()
    task_type = "general"
    for ttype, keywords in _TASK_TYPES.items():
        if any(kw in text_lower for kw in keywords):
            task_type = ttype
            break

    # ── Extract rough entities (quoted strings + capitalised words) ───────────
    entities: list[str] = re.findall(r'"([^"]+)"', text)
    entities += [
        w for w in re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", text)
        if w not in _ENTITY_STOP
    ]
    entities = list(dict.fromkeys(entities))[:10]  # deduplicate, cap at 10

    # ── Build a short intent phrase ───────────────────────────────────────────
    words = text.split()
    intent = " ".join(words[:8]) + ("…" if len(words) > 8 else "")

    logger.debug("engine.process_input: type=%s intent=%s entities=%s", task_type, intent, entities)

    return {
        "text": text,
        "task_type": task_type,
        "intent": intent,
        "entities": entities,
        "input_format": input_format,
        "original": raw_input,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LLM Generation
# ══════════════════════════════════════════════════════════════════════════════

def generate(
    prompt: str,
    context: str | None = None,
    system: str = "You are a helpful AI assistant.",
    model: str | None = None,
    timeout: int = 120,
) -> str:
    """Generate a text completion via the engine's LLM backend.

    Args:
        prompt:  The user-facing prompt.
        context: Optional extra context prepended to the prompt.
        system:  System instruction for the model.
        model:   Optional model override.
        timeout: HTTP timeout in seconds (default 120).

    Returns:
        Generated text as a plain string.
    """
    return _generate(prompt=prompt, system=system, context=context, model=model, timeout=timeout)


# ══════════════════════════════════════════════════════════════════════════════
# Embedding
# ══════════════════════════════════════════════════════════════════════════════

def embed(
    text: str,
    model: str | None = None,
    timeout: int = 60,
) -> list[float]:
    """Return a vector embedding for *text*.

    Args:
        text:    Input string to embed.
        model:   Optional embedding model override.
        timeout: HTTP timeout in seconds (default 60).

    Returns:
        List of floats, or empty list if embedding is unavailable.
    """
    return _embed(text=text, model=model, timeout=timeout)


# ══════════════════════════════════════════════════════════════════════════════
# Memory
# ══════════════════════════════════════════════════════════════════════════════

def memory_store(key: str, value: Any, namespace: str = "default") -> None:
    """Persist *value* under *key* in the engine's memory store.

    Args:
        key:       Lookup key (string).
        value:     Any JSON-serialisable object.
        namespace: Logical namespace / agent name (default: "default").
    """
    _store(key=key, value=value, namespace=namespace)


def memory_retrieve(key: str, namespace: str = "default") -> Any | None:
    """Retrieve the value for *key* from the engine's memory store.

    Args:
        key:       Lookup key.
        namespace: Namespace to search (default: "default").

    Returns:
        The stored value, or None if not found.
    """
    return _retrieve(key=key, namespace=namespace)


def memory_search(query: str, namespace: str = "default", top_k: int = 5) -> list[dict]:
    """Search memory entries by substring match.

    Args:
        query:     Search string (case-insensitive).
        namespace: Namespace to search (default: "default").
        top_k:     Maximum results.

    Returns:
        List of ``{"key": ..., "value": ...}`` dicts.
    """
    return _search(query=query, namespace=namespace, top_k=top_k)
