from __future__ import annotations

from typing import Any


_DEFAULT_AGENTS = ("intel_agent", "email_ninja", "social_guru")


class AscendForgeExecutor:
    """Objective-first Ascend Forge execution pipeline."""

    def build_plan(self, goal: str) -> list[str]:
        text = str(goal or "").lower()
        plan: list[str] = ["analyze baseline performance", "identify highest-impact bottlenecks"]
        if "conversion" in text or "funnel" in text:
            plan.extend(["design conversion experiments", "deploy funnel optimizations"])
        elif "revenue" in text or "growth" in text:
            plan.extend(["prioritize growth loops", "launch growth execution sprint"])
        else:
            plan.extend(["generate optimization hypotheses", "execute incremental improvements"])
        return plan

    def execute_objective(
        self,
        *,
        objective_id: str,
        goal: str,
        constraints: dict[str, Any] | None = None,
        priority: str = "medium",
    ) -> dict[str, Any]:
        constraints = constraints or {}
        plan = self.build_plan(goal)
        agents_used = list(_DEFAULT_AGENTS)
        progress = 0
        status = "running" if plan else "pending"

        return {
            "objective_id": objective_id,
            "goal": goal,
            "constraints": constraints,
            "priority": priority,
            "plan": plan,
            "agents_used": agents_used,
            "progress": progress,
            "status": status,
            "results": [],
        }


_executor: AscendForgeExecutor | None = None


def get_ascend_forge_executor() -> AscendForgeExecutor:
    global _executor
    if _executor is None:
        _executor = AscendForgeExecutor()
    return _executor
