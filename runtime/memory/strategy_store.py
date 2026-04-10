"""Strategy Store — records which agent configurations produced the best outcomes.

Stores strategies locally in ~/.ai-employee/strategies.json.  The Planner uses
``get_best_strategy()`` to warm-start from prior winning configurations.

Usage::

    from memory.strategy_store import get_strategy_store

    store = get_strategy_store()
    store.record(
        goal_type="content_generation",
        agent="faceless_video",
        config={"platform": "tiktok", "length": 60},
        outcome_score=0.87,
    )
    best = store.get_best_strategy("content_generation")
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any


_DEFAULT_PATH = Path.home() / ".ai-employee" / "strategies.json"


class StrategyStore:
    """File-backed store for strategy outcomes."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write(self, data: list[dict]) -> None:
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        goal_type: str,
        agent: str,
        config: dict | None = None,
        outcome_score: float = 0.0,
        notes: str = "",
    ) -> dict:
        """Record a strategy result and return the stored entry."""
        entry = {
            "strategy_id": str(uuid.uuid4())[:8],
            "goal_type": goal_type,
            "agent": agent,
            "config": config or {},
            "outcome_score": max(0.0, min(1.0, outcome_score)),
            "notes": notes,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self._lock:
            data = self._read()
            data.append(entry)
            self._write(data)
        return entry

    def get_best_strategy(self, goal_type: str, *, top_n: int = 3) -> list[dict]:
        """Return the top-N strategies for *goal_type* sorted by outcome_score."""
        with self._lock:
            data = self._read()
        filtered = [d for d in data if d.get("goal_type") == goal_type]
        return sorted(filtered, key=lambda d: d.get("outcome_score", 0.0), reverse=True)[:top_n]

    def all_strategies(self) -> list[dict]:
        """Return all recorded strategies."""
        with self._lock:
            return self._read()

    def top_performers(self, *, limit: int = 5) -> list[dict]:
        """Return globally best-performing strategies across all goal types."""
        with self._lock:
            data = self._read()
        return sorted(data, key=lambda d: d.get("outcome_score", 0.0), reverse=True)[:limit]


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: StrategyStore | None = None
_instance_lock = threading.Lock()


def get_strategy_store(path: Path | None = None) -> StrategyStore:
    """Return the process-wide StrategyStore singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = StrategyStore(path)
    return _instance
