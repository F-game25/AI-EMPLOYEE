"""Planner AI — read-only analysis and improvement plan generation.

The Planner AI analyses the system, produces a structured plan, and
writes nothing to disk.  It consults the neural brain for strategy
hints and the strategy store for historical performance data.

Output: ``ImprovementPlan`` with what/where/why + acceptance criteria.
"""
from __future__ import annotations

import time
from typing import Any

from core.knowledge_store import get_knowledge_store
from core.memory_index import get_memory_index
from core.self_improvement.contracts import ImprovementPlan, ImprovementTask, RiskLevel


# ── Risk classification keywords ──────────────────────────────────────────────

_RISK_KEYWORDS: dict[RiskLevel, tuple[str, ...]] = {
    "critical": ("brain", "neural", "model", "security", "auth", "credential"),
    "high": ("api", "server", "database", "payment", "deploy", "config"),
    "medium": ("agent", "skill", "pipeline", "engine", "action"),
    "low": ("test", "docs", "readme", "style", "lint", "format", "comment"),
}

_AREA_TO_TARGETS: dict[str, list[str]] = {
    "core": ["runtime/core/"],
    "agents": ["runtime/agents/"],
    "actions": ["runtime/actions/"],
    "skills": ["runtime/skills/"],
    "memory": ["runtime/memory/"],
    "brain": ["runtime/brain/"],
    "frontend": ["frontend/src/"],
    "backend": ["backend/"],
    "tests": ["tests/"],
    "general": ["runtime/"],
}


class PlannerAI:
    """Read-only improvement planner integrated with brain + memory."""

    def __init__(self) -> None:
        self._brain_registry = None
        self._strategy_store = None

    def _get_brain(self):
        if self._brain_registry is None:
            try:
                from core.brain_registry import brain
                self._brain_registry = brain
            except Exception:
                pass
        return self._brain_registry

    def _get_strategy_store(self):
        if self._strategy_store is None:
            try:
                from memory.strategy_store import get_strategy_store
                self._strategy_store = get_strategy_store()
            except Exception:
                pass
        return self._strategy_store

    def analyze_and_plan(self, task: ImprovementTask) -> ImprovementPlan:
        """Produce an improvement plan for the given task.

        This method is purely analytical — it writes nothing to disk,
        modifies no code, and produces only an immutable plan artifact.

        Neural brain integration:
          - Consults brain for strategy hints (goal_type routing).
          - Uses strategy store history to avoid repeating failures.
        """
        start = time.perf_counter()

        # ── 1. Classify risk ──────────────────────────────────────────────
        risk = self._classify_risk(task.description, task.target_area)

        # ── 2. Determine target paths ─────────────────────────────────────
        targets = _AREA_TO_TARGETS.get(task.target_area, ["runtime/"])

        # ── 3. Build acceptance criteria ──────────────────────────────────
        criteria = self._build_acceptance_criteria(task, risk)

        # ── 4. Consult brain for strategy hint ────────────────────────────
        brain_strategy = self._consult_brain(task)
        task.brain_strategy = brain_strategy

        # ── 5. Consult strategy store for historical insights ─────────────
        learning = self._consult_memory(task)
        context = self._knowledge_context(task)

        # ── 6. Estimate scope ─────────────────────────────────────────────
        estimated_lines = self._estimate_lines(task.description, risk)

        plan = ImprovementPlan(
            task_id=task.task_id,
            what=task.description,
            where=targets,
            why=self._build_why(task, learning, context),
            acceptance_criteria=criteria,
            risk_level=risk,
            estimated_lines=estimated_lines,
        )

        return plan

    def _classify_risk(self, description: str, target_area: str) -> RiskLevel:
        """Classify the risk level based on description keywords."""
        text = f"{description} {target_area}".lower()
        for level in ("critical", "high", "medium", "low"):
            keywords = _RISK_KEYWORDS.get(level, ())
            if any(kw in text for kw in keywords):
                return level  # type: ignore[return-value]
        return "medium"

    def _build_acceptance_criteria(
        self,
        task: ImprovementTask,
        risk: RiskLevel,
    ) -> list[str]:
        """Generate acceptance criteria based on task + risk."""
        criteria = [
            "All existing tests must pass (npm test)",
            "Lint must pass (npm run lint)",
            "No new security vulnerabilities introduced",
        ]
        if risk in ("high", "critical"):
            criteria.append("Manual code review required before merge")
            criteria.append("Rollback procedure must be verified")
        if task.target_area in ("core", "brain", "actions"):
            criteria.append("Architecture contracts must remain stable")
        if any(c for c in task.constraints):
            criteria.extend(task.constraints)
        return criteria

    def _consult_brain(self, task: ImprovementTask) -> dict[str, Any]:
        """Ask the neural brain for a strategy recommendation."""
        brain = self._get_brain()
        if brain is None:
            return {"source": "fallback", "confidence": 0.0}
        try:
            strategy = brain.get_strategy(
                goal=task.description,
                goal_type=f"self_improvement:{task.target_area}",
            )
            return strategy.get("brain", {"source": "brain", "confidence": 0.5})
        except Exception:
            return {"source": "fallback", "confidence": 0.0}

    def _consult_memory(self, task: ImprovementTask) -> dict[str, Any]:
        """Check strategy store for historical insights on this area."""
        store = self._get_strategy_store()
        if store is None:
            return {"insight": "No prior data", "success_rate": 0.0}
        try:
            return store.learn_for_goal(f"self_improvement:{task.target_area}")
        except Exception:
            return {"insight": "No prior data", "success_rate": 0.0}

    def _build_why(self, task: ImprovementTask, learning: dict, context: dict[str, Any]) -> str:
        """Build a human-readable 'why' explanation."""
        parts = [f"Improvement target: {task.description}"]
        rate = learning.get("success_rate", 0.0)
        if rate > 0:
            parts.append(f"Historical success rate for this area: {rate:.0%}")
        promote = learning.get("promote_agents", [])
        if promote:
            parts.append(f"Recommended approaches: {', '.join(promote)}")
        parts.append(
            "You have learned the following relevant context: "
            f"{context}. Use this to make better decisions."
        )
        return ". ".join(parts) + "."

    @staticmethod
    def _knowledge_context(task: ImprovementTask) -> dict[str, Any]:
        try:
            store = get_knowledge_store()
            knowledge = store.get_relevant_context(task.description)
            profile = store.snapshot().get("user_profile", {})
            memories = get_memory_index().get_relevant_memories(task.description, top_k=5)
            return {
                "knowledge": knowledge,
                "memories": [
                    {
                        "id": m.get("id"),
                        "text": m.get("text"),
                        "importance": m.get("importance", 0.0),
                        "usage_count": m.get("usage_count", 0),
                    }
                    for m in memories
                ],
                "user_profile": profile,
            }
        except Exception:
            return {}

    def _estimate_lines(self, description: str, risk: RiskLevel) -> int:
        """Rough estimate of lines that will be changed."""
        base = {"low": 30, "medium": 60, "high": 40, "critical": 20}
        words = len(description.split())
        return base.get(risk, 50) + min(words * 2, 100)
