"""Decision Engine — profit/speed/complexity scoring.

Ranks candidate actions so the planner can pick the highest-value path.

Scoring formula (default weights):
    score = 0.5 * profit_potential
          + 0.3 * execution_speed
          + 0.2 * (10 - complexity)

Weights are auto-tunable from historical ROI data via ``tune_weights()``.

Usage::

    from core.decision_engine import get_decision_engine, ActionSpec

    engine = get_decision_engine()
    candidates = [
        ActionSpec(id="a", skill="content_calendar", profit_potential=8, execution_speed=9, complexity=2),
        ActionSpec(id="b", skill="lead_generator",   profit_potential=9, execution_speed=5, complexity=7),
    ]
    ranked = engine.rank_actions(candidates)
    best = ranked[0]
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionSpec:
    """Represents a candidate action the system can execute."""

    id: str
    skill: str
    profit_potential: float = 5.0   # 0–10
    execution_speed: float = 5.0    # 0–10  (higher = faster)
    complexity: float = 5.0         # 0–10  (higher = harder; inverted in score)
    metadata: dict = field(default_factory=dict)

    # Filled in by rank_actions
    score: float = 0.0

    def clamp(self) -> "ActionSpec":
        """Clamp all scoring dimensions to [0, 10]."""
        self.profit_potential = max(0.0, min(10.0, self.profit_potential))
        self.execution_speed = max(0.0, min(10.0, self.execution_speed))
        self.complexity = max(0.0, min(10.0, self.complexity))
        return self


_DEFAULT_WEIGHTS = {
    "profit": 0.5,
    "speed": 0.3,
    "simplicity": 0.2,  # = 1 - complexity / 10
}

_BLACKLIGHT_WEIGHTS = {
    "profit": 0.8,
    "speed": 0.15,
    "simplicity": 0.05,
}


class DecisionEngine:
    """Weights-based action scorer with optional auto-tuning."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = dict(weights or _DEFAULT_WEIGHTS)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, action: ActionSpec) -> float:
        """Return the weighted score for a single action."""
        action.clamp()
        w = self._weights
        return (
            w.get("profit", 0.5) * action.profit_potential
            + w.get("speed", 0.3) * action.execution_speed
            + w.get("simplicity", 0.2) * (10.0 - action.complexity)
        )

    def rank_actions(self, candidates: list[ActionSpec]) -> list[ActionSpec]:
        """Return *candidates* sorted by score descending (in-place scoring)."""
        with self._lock:
            for action in candidates:
                action.score = self.score(action)
        return sorted(candidates, key=lambda a: a.score, reverse=True)

    def tune_weights(self, roi_data: list[dict]) -> None:
        """Auto-tune weights from historical ROI records.

        *roi_data* is a list of dicts with keys:
            profit_potential, execution_speed, complexity, revenue

        Uses a simple correlation heuristic — dimensions with higher
        average revenue get proportionally more weight.
        """
        if not roi_data:
            return

        totals: dict[str, float] = {"profit": 0.0, "speed": 0.0, "simplicity": 0.0}
        for rec in roi_data:
            rev = float(rec.get("revenue", 0))
            totals["profit"] += float(rec.get("profit_potential", 5)) * rev
            totals["speed"] += float(rec.get("execution_speed", 5)) * rev
            totals["simplicity"] += (10 - float(rec.get("complexity", 5))) * rev

        total_sum = sum(totals.values()) or 1.0
        with self._lock:
            self._weights = {k: v / total_sum for k, v in totals.items()}

    def set_blacklight_mode(self, enabled: bool) -> None:
        """Switch between default and aggressive profit-maximising weights."""
        with self._lock:
            self._weights = dict(_BLACKLIGHT_WEIGHTS if enabled else _DEFAULT_WEIGHTS)

    @property
    def weights(self) -> dict[str, float]:
        with self._lock:
            return dict(self._weights)


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: DecisionEngine | None = None
_instance_lock = threading.Lock()


def get_decision_engine() -> DecisionEngine:
    """Return the process-wide DecisionEngine singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = DecisionEngine()
    return _instance
