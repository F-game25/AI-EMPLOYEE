"""Structured JSONL logger for system observability."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


class StructuredLogger:
    """Writes queryable JSON events with stable fields."""

    def __init__(self, log_path: Path | None = None) -> None:
        base = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
        self._path = log_path or (base / "state" / "operations.jsonl")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log_event(
        self,
        *,
        component: str,
        action: str,
        result: str,
        latency_ms: float,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "component": component,
            "action": action,
            "result": result,
            "latency_ms": round(max(latency_ms, 0.0), 3),
            "meta": meta or {},
        }
        line = json.dumps(event, ensure_ascii=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return event

    def recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for raw in self._path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                rows.append(json.loads(raw))
            except Exception:
                continue
        return rows[-limit:]


_instance: StructuredLogger | None = None
_instance_lock = threading.Lock()


def get_structured_logger(log_path: Path | None = None) -> StructuredLogger:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = StructuredLogger(log_path=log_path)
    return _instance
