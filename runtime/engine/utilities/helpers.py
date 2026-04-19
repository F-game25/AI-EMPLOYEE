"""Engine — Utilities: shared helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def truncate(text: str, n: int = 80, suffix: str = "…") -> str:
    """Return *text* truncated to *n* characters, appending *suffix* if cut."""
    if len(text) <= n:
        return text
    return text[: n - len(suffix)] + suffix


def safe_json(obj: object) -> str:
    """Serialize *obj* to a JSON string; fall back to ``str()`` on failure."""
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(obj)
