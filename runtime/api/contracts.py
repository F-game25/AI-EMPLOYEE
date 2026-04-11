"""API-facing response normalizers."""
from __future__ import annotations

from typing import Any


def normalize_task_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Return stable JSON structure for task responses."""
    return {
        "run_id": payload.get("run_id", ""),
        "goal": payload.get("goal", ""),
        "tasks": payload.get("tasks", []),
        "performance_score": payload.get("performance_score", 0.0),
        "success_rate": payload.get("success_rate", 0.0),
    }
