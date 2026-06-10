"""OutcomeScorer — offline 7-axis scoring of a finalized trace.

Hard signals (success flag, errors, latency budget, tool errors, tests) dominate
over soft signals. The AI judge is OPTIONAL and env-guarded (EVOLUTION_LLM_SCORE,
default off); per the plan it may *influence* but is never the sole criterion.
Pure/offline — runs on the background path, never on the request path.
"""
from __future__ import annotations

import os
from typing import Any

_AXES = (
    "quality_score", "speed_score", "safety_score", "cost_score",
    "completion_score", "reusability_score", "learning_value_score",
)

# Default per-task latency budgets (ms) for the speed axis.
_LATENCY_BUDGET_MS = {
    "code": 60_000, "research": 120_000, "chat": 8_000,
    "tool": 15_000, "default": 30_000,
}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


class OutcomeScorer:
    def __init__(self):
        self._llm_judge = os.environ.get("EVOLUTION_LLM_SCORE", "false").lower() == "true"

    def score(self, trace: dict[str, Any]) -> dict[str, float]:
        success = bool(trace.get("success"))
        errors = trace.get("errors") or []
        outputs = trace.get("outputs") or []
        latency = float(trace.get("total_latency_ms") or 0.0)
        task_type = trace.get("task_type") or "default"
        tools = trace.get("tools_used") or []

        # completion — primarily the hard success flag.
        completion = 1.0 if success else (0.4 if outputs else 0.0)

        # quality — hard success/error signal, then optional LLM nudge.
        tool_errs = sum(1 for e in errors if "tool" in str(e.get("phase", "")).lower())
        quality = (0.85 if success else 0.25) - 0.1 * min(len(errors), 5)
        quality = _clamp(quality)
        if self._llm_judge:
            quality = _clamp(0.7 * quality + 0.3 * self._llm_quality(trace))

        # speed — within budget = 1.0, degrades past 2x budget.
        budget = _LATENCY_BUDGET_MS.get(task_type, _LATENCY_BUDGET_MS["default"])
        speed = 1.0 if latency <= budget else _clamp(1.0 - (latency - budget) / budget)

        # safety — clean unless an unsafe/blocked signal appears.
        unsafe = any("unsafe" in str(e.get("error", "")).lower()
                     or "blocked" in str(e.get("error", "")).lower() for e in errors)
        safety = 0.0 if unsafe else (1.0 if not errors else 0.95)

        # cost — proxy by model/tool fan-out (fewer hops = cheaper).
        n_models = len(trace.get("models_used") or [])
        cost = _clamp(1.0 - 0.1 * max(0, n_models - 1) - 0.05 * max(0, len(tools) - 3))

        # reusability — generalizable, clean, multi-step success teaches more.
        n_events = len(trace.get("events") or [])
        reusability = _clamp((0.6 if success else 0.2) + 0.04 * min(n_events, 10))

        # learning_value — failures and rich trajectories are high signal.
        learning = _clamp(
            (0.5 if not success else 0.2)
            + 0.05 * min(len(errors), 6)
            + 0.03 * min(n_events, 10)
            + (0.2 if tool_errs else 0.0)
        )

        return {
            "quality_score": round(quality, 4),
            "speed_score": round(speed, 4),
            "safety_score": round(safety, 4),
            "cost_score": round(cost, 4),
            "completion_score": round(completion, 4),
            "reusability_score": round(reusability, 4),
            "learning_value_score": round(learning, 4),
        }

    def _llm_quality(self, trace: dict[str, Any]) -> float:
        """Optional AI-judge nudge. Guarded; any failure → neutral 0.5."""
        try:
            from engine.api import generate  # lazy import; offline path only
            goal = str(trace.get("user_goal", ""))[:400]
            out = str((trace.get("outputs") or [""])[0])[:800]
            resp = generate(
                prompt=f"Goal: {goal}\nOutput: {out}\nReturn ONLY a number 0..1 for quality.",
                system="You are a strict output-quality judge. Reply with one float 0..1.",
                timeout=30,
            )
            import re
            m = re.search(r"[01](?:\.\d+)?", resp or "")
            return _clamp(float(m.group(0))) if m else 0.5
        except Exception:
            return 0.5


__all__ = ["OutcomeScorer"]
