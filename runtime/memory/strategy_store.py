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
_SUCCESS_SCORE_THRESHOLD = 0.6


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
        outcome_status: str | None = None,
        context: dict | None = None,
        outcome: dict | None = None,
        notes: str = "",
    ) -> dict:
        """Record a strategy result and return the stored entry."""
        score = max(0.0, min(1.0, outcome_score))
        status = (outcome_status or ("success" if score >= _SUCCESS_SCORE_THRESHOLD else "failed")).lower()
        if status not in ("success", "failed"):
            status = "failed"
        pattern = (goal_type or "general").strip().lower()
        entry = {
            "strategy_id": str(uuid.uuid4())[:8],
            "goal_type": goal_type,
            "pattern": pattern,
            "agent": agent,
            "best_agent": agent,
            "success_rate": score if status == "success" else 0.0,
            "config": config or {},
            "outcome_score": score,
            "outcome_status": status,
            "context": context or {},
            "outcome": outcome or {},
            "notes": notes,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self._lock:
            data = self._read()
            data.append(entry)
            aggregated = self._pattern_success_rates_locked(data)
            row = aggregated.get(pattern)
            if row:
                entry["best_agent"] = row.get("best_agent", entry["best_agent"])
                entry["success_rate"] = row.get("success_rate", entry["success_rate"])
                data[-1] = entry
            self._write(data)
        return entry

    def get_best_strategy(self, goal_type: str, *, top_n: int = 3) -> list[dict]:
        """Return the top-N strategies for *goal_type* sorted by outcome_score."""
        with self._lock:
            data = self._read()
        filtered = [d for d in data if d.get("goal_type") == goal_type]
        weighted = sorted(
            filtered,
            key=lambda d: (
                1 if d.get("outcome_status", "success") == "success" else 0,
                d.get("outcome_score", 0.0),
            ),
            reverse=True,
        )
        return weighted[:top_n]

    def all_strategies(self) -> list[dict]:
        """Return all recorded strategies."""
        with self._lock:
            return self._read()

    def top_performers(self, *, limit: int = 5) -> list[dict]:
        """Return globally best-performing strategies across all goal types."""
        with self._lock:
            data = self._read()
        ranked = sorted(
            data,
            key=lambda d: (
                1 if d.get("outcome_status", "success") == "success" else 0,
                d.get("outcome_score", 0.0),
            ),
            reverse=True,
        )
        return ranked[:limit]

    def performance_summary(self, *, goal_type: str | None = None, limit: int = 5) -> dict:
        """Return compact success/failure summary with top and weak strategies."""
        with self._lock:
            data = self._read()
        if goal_type:
            data = [d for d in data if d.get("goal_type") == goal_type]

        total = len(data)
        successful = [d for d in data if d.get("outcome_status", "") == "success"]
        failed = [d for d in data if d.get("outcome_status", "") != "success"]
        success_rate = round(len(successful) / max(total, 1), 3)

        top = sorted(successful, key=lambda d: d.get("outcome_score", 0.0), reverse=True)[:limit]
        weak = sorted(failed, key=lambda d: d.get("outcome_score", 0.0))[:limit]
        return {
            "goal_type": goal_type or "all",
            "total_attempts": total,
            "successful_attempts": len(successful),
            "failed_attempts": len(failed),
            "success_rate": success_rate,
            "top_strategies": top,
            "failed_strategies": weak,
        }

    def learn_for_goal(self, goal_type: str) -> dict:
        """Return learning insights that can influence planning decisions."""
        summary = self.performance_summary(goal_type=goal_type, limit=10)
        winners = [s.get("agent", "") for s in summary["top_strategies"] if s.get("agent")]
        losers = [s.get("agent", "") for s in summary["failed_strategies"] if s.get("agent")]
        pattern_summary = self.pattern_success_rates(pattern=goal_type)
        return {
            "goal_type": goal_type,
            "success_rate": summary["success_rate"],
            "promote_agents": list(dict.fromkeys(winners[:3])),
            "deprioritize_agents": list(dict.fromkeys(losers[:3])),
            "patterns": pattern_summary[:5],
            "insight": (
                "Promote agents with successful outcomes and deprioritize repeated failures."
                if summary["total_attempts"] > 0
                else "No prior outcomes yet; use default planning."
            ),
        }

    def _pattern_success_rates_locked(self, data: list[dict]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in data:
            pattern = str(row.get("pattern") or row.get("goal_type") or "general").strip().lower()
            agent = row.get("agent", "")
            status = row.get("outcome_status", "failed")
            g = grouped.setdefault(pattern, {"total": 0, "success": 0, "by_agent": {}})
            g["total"] += 1
            if status == "success":
                g["success"] += 1
            by_agent = g["by_agent"].setdefault(agent, {"total": 0, "success": 0})
            by_agent["total"] += 1
            if status == "success":
                by_agent["success"] += 1

        result: dict[str, dict[str, Any]] = {}
        for pattern, g in grouped.items():
            best_agent = "task_orchestrator"
            best_rate = 0.0
            for agent, stats in g["by_agent"].items():
                rate = stats["success"] / max(stats["total"], 1)
                if rate > best_rate:
                    best_rate = rate
                    best_agent = agent
            result[pattern] = {
                "pattern": pattern,
                "best_agent": best_agent,
                "success_rate": round(g["success"] / max(g["total"], 1), 3),
            }
        return result

    def pattern_success_rates(self, *, pattern: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            rows = self._pattern_success_rates_locked(data)
        values = list(rows.values())
        if pattern:
            key = pattern.strip().lower()
            values = [v for v in values if v.get("pattern") == key]
        return sorted(values, key=lambda x: x.get("success_rate", 0.0), reverse=True)


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
