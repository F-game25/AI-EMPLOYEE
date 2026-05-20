"""Atomic tool registry.

Lightweight in-process registry. Each tool advertises:
``name``, ``description``, ``input_schema``, ``output_schema``, and
``call(input_data) -> dict``.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_REGISTRY: dict[str, dict[str, Any]] = {}


def register_tool(
    *,
    name: str,
    description: str,
    call: Callable[[dict[str, Any]], dict[str, Any]],
    input_schema: Optional[dict[str, Any]] = None,
    output_schema: Optional[dict[str, Any]] = None,
    tags: Optional[list[str]] = None,
) -> None:
    with _LOCK:
        _REGISTRY[name] = {
            "name": name,
            "description": description,
            "call": call,
            "input_schema": input_schema or {"type": "object"},
            "output_schema": output_schema or {"type": "object"},
            "tags": list(tags or []),
        }
        logger.debug("tool registered: %s", name)


def get_tool_registry() -> dict[str, dict[str, Any]]:
    with _LOCK:
        return dict(_REGISTRY)


def list_tools() -> list[dict[str, Any]]:
    with _LOCK:
        return [
            {k: v for k, v in entry.items() if k != "call"}
            for entry in _REGISTRY.values()
        ]


def call_tool(name: str, input_data: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        entry = _REGISTRY.get(name)
    if not entry:
        return {"status": "error", "error": f"unknown tool: {name}"}
    try:
        return entry["call"](input_data) or {}
    except Exception as e:
        logger.warning("tool '%s' raised: %s", name, e)
        return {"status": "error", "error": str(e)}


# Auto-register built-in tools when the package is imported
def _autoregister() -> None:
    try:
        from . import web_research_tool  # noqa: F401
        from . import context_score_tool  # noqa: F401
    except Exception as e:
        logger.debug("tool autoregister partial failure: %s", e)


_autoregister()
