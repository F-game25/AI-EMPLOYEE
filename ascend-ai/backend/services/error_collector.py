"""
ASCEND AI — Error Collector
Collects runtime errors from the backend and exposes them via API.
"""

import time
from collections import deque
from typing import Any

_errors: deque = deque(maxlen=200)


def record_error(bot: str, message: str, detail: str = "") -> None:
    """Record an error from any backend component."""
    _errors.appendleft(
        {
            "ts": time.time(),
            "bot": bot,
            "message": message,
            "detail": detail,
        }
    )


def get_errors(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent errors."""
    return list(_errors)[:limit]


def clear_errors() -> None:
    _errors.clear()
