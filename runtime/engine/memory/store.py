"""Engine — Memory store: lightweight key/value + search backed by JSON."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("engine.memory")

_AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_MEMORY_DIR = _AI_HOME / "state" / "engine_memory"


def _namespace_path(namespace: str) -> Path:
    """Return the JSON file path for a given memory namespace."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in namespace)
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return _MEMORY_DIR / f"{safe}.json"


def _load(namespace: str) -> dict:
    path = _namespace_path(namespace)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _save(namespace: str, data: dict) -> None:
    path = _namespace_path(namespace)
    try:
        path.write_text(json.dumps(data, indent=2))
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory save failed (%s): %s", namespace, exc)


def store(key: str, value: Any, namespace: str = "default") -> None:
    """Persist *value* under *key* in the given memory *namespace*.

    Args:
        key:       Lookup key (string).
        value:     Any JSON-serialisable value.
        namespace: Logical namespace / agent name (default: "default").
    """
    data = _load(namespace)
    data[key] = {"value": value, "stored_at": time.time()}
    _save(namespace, data)


def retrieve(key: str, namespace: str = "default") -> Any | None:
    """Retrieve the value for *key* from *namespace*, or None if not found.

    Args:
        key:       Lookup key.
        namespace: Namespace to search (default: "default").

    Returns:
        The stored value, or None.
    """
    data = _load(namespace)
    entry = data.get(key)
    if entry is None:
        return None
    # Support both wrapped {"value": ..., "stored_at": ...} and plain values.
    if isinstance(entry, dict) and "value" in entry:
        return entry["value"]
    return entry


def search(query: str, namespace: str = "default", top_k: int = 5) -> list[dict]:
    """Simple substring search across keys and string values in *namespace*.

    Args:
        query:     Search string (case-insensitive substring match).
        namespace: Namespace to search (default: "default").
        top_k:     Maximum number of results to return.

    Returns:
        List of dicts with keys ``key`` and ``value``.
    """
    data = _load(namespace)
    q = query.lower()
    results = []
    for key, entry in data.items():
        val = entry.get("value", entry) if isinstance(entry, dict) else entry
        val_str = str(val).lower()
        if q in key.lower() or q in val_str:
            results.append({"key": key, "value": val})
            if len(results) >= top_k:
                break
    return results
