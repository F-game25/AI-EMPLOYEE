"""Strategic Planner — autonomous goal generation and reprioritization.

Runs on cadence (daily/weekly) or on-demand via API.
Uses the LLM to:
  1. Analyze current goal progress and blockers
  2. Identify strategic gaps
  3. Generate new sub-goals or adjust priorities
  4. Produce a weekly plan decomposed into daily tasks
  5. Adapt to changing context from RAG memory
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from infra.planning.goal_engine import GoalEngine, get_goal_engine
from infra.planning.schema import (
    Goal, GoalStatus, Horizon, KeyResult, Priority, StrategicPlan,
)

logger = logging.getLogger("planning.strategic_planner")


class DependencyResolver:
    """Topological sort for goal DAG — detects cycles and orders execution."""

    def resolve(self, goals: list[Goal]) -> list[Goal]:
        goal_map = {g.id: g for g in goals}
        visited: set[str] = set()
        temp: set[str] = set()
        ordered: list[Goal] = []

        def visit(g: Goal) -> None:
            if g.id in visited:
                return
            if g.id in temp:
                logger.warning("Circular dependency detected for goal %s — breaking cycle", g.id)
                return
            temp.add(g.id)
            for dep_id in g.depends_on:
                dep = goal_map.get(dep_id)
                if dep:
                    visit(dep)
            temp.discard(g.id)
            visited.add(g.id)
            ordered.append(g)

        for g in goals:
            visit(g)
        return ordered

    def get_blocked(self, goals: list[Goal]) -> list[Goal]:
        active = {g.id for g in goals if g.status == GoalStatus.ACTIVE}
        completed = {g.id for g in goals if g.status == GoalStatus.COMPLETED}
        return [
            g for g in goals
            if g.status == GoalStatus.ACTIVE
            and any(dep not in completed for dep in g.depends_on if dep in active)
        ]


class PriorityEngine:
    """Scores and ranks goals by business impact + urgency + feasibility."""

    WEIGHTS = {
        "urgency":     0.35,   # time to deadline
        "impact":      0.30,   # key result target magnitude
        "progress":    0.20,   # how close to done (reward near-completion)
        "confidence":  0.15,   # AI confidence score
    }

    def score(self, goal: Goal) -> float:
        now = time.time()
        time_remaining = max(0, goal.due_at - now)
        day_scale = 30 * 86400
        urgency = max(0.0, 1.0 - (time_remaining / day_scale))

        # Impact from KR targets
        if goal.key_results:
            impact = min(1.0, sum(
                min(1.0, kr.target / 1000) for kr in goal.key_results
            ) / len(goal.key_results))
        else:
            impact = 0.5

        progress_reward = min(1.0, goal.overall_progress * 1.5)  # bonus for >67% done
        confidence = goal.confidence

        return (
            urgency     * self.WEIGHTS["urgency"] +
            impact      * self.WEIGHTS["impact"] +
            progress_reward * self.WEIGHTS["progress"] +
            confidence  * self.WEIGHTS["confidence"]
        )

    def rank(self, goals: list[Goal]) -> list[tuple[Goal, float]]:
        scored = [(g, self.score(g)) for g in goals]
        return sorted(scored, key=lambda x: x[1], reverse=True)


class StrategicPlanner:
    """Autonomous executive planning layer."""

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self._engine = get_goal_engine()
        self._resolver = DependencyResolver()
        self._priority = PriorityEngine()

    async def generate_weekly_plan(self, actor: str = "strategic_planner") -> dict:
        """Produce a weekly operational plan from active goals."""
        active_goals = self._engine.list_goals(self._tenant_id, status=GoalStatus.ACTIVE)
        overdue = self._engine.list_goals(self._tenant_id, overdue_only=True)
        due_review = self._engine.get_due_for_review(self._tenant_id)

        # Resolve dependency order
        ordered = self._resolver.resolve(active_goals)
        blocked = self._resolver.get_blocked(active_goals)
        blocked_ids = {g.id for g in blocked}

        # Rank by priority score
        ranked = self._priority.rank([g for g in ordered if g.id not in blocked_ids])

        # Decompose top goals into weekly tasks
        weekly_tasks: list[dict] = []
        for goal, score in ranked[:5]:
            tasks = await self._decompose_to_tasks(goal)
            weekly_tasks.extend(tasks)

        plan = {
            "plan_id": str(uuid.uuid4()),
            "tenant_id": self._tenant_id,
            "generated_at": time.time(),
            "horizon": "weekly",
            "active_goals": len(active_goals),
            "overdue_goals": [g.to_dict() for g in overdue],
            "goals_due_for_review": [g.id for g in due_review],
            "blocked_goals": [g.id for g in blocked],
            "priority_ranking": [{"goal_id": g.id, "title": g.title, "score": round(s, 3)}
                                  for g, s in ranked],
            "weekly_tasks": weekly_tasks,
        }

        # Trigger reviews for overdue review goals
        for g in due_review[:3]:
            await self._auto_review(g)

        logger.info("Weekly plan generated: tenant=%s goals=%d tasks=%d",
                    self._tenant_id, len(active_goals), len(weekly_tasks))
        return plan

    async def reprioritize(self, context: str = "") -> list[dict]:
        """Re-score all active goals and surface priority changes."""
        goals = self._engine.list_goals(self._tenant_id, status=GoalStatus.ACTIVE)
        ranked = self._priority.rank(goals)
        changes: list[dict] = []
        for i, (goal, score) in enumerate(ranked):
            if abs(score - goal.confidence) > 0.15:
                self._engine.mark_reviewed(goal.id, self._tenant_id, score, actor="priority_engine")
                changes.append({"goal_id": goal.id, "title": goal.title,
                                 "old_confidence": goal.confidence, "new_score": round(score, 3)})
        return changes

    async def _decompose_to_tasks(self, goal: Goal) -> list[dict]:
        """Use LLM to break a goal into weekly tasks."""
        try:
            from core.orchestrator import LLMClient
            client = LLMClient()
            prompt = (
                f"Goal: {goal.title}\nDescription: {goal.description}\n"
                f"Progress: {goal.overall_progress:.0%}\nDue: {goal.due_at}\n\n"
                "List 3-5 specific tasks for this week to advance this goal. "
                "Return JSON array: [{\"task\": str, \"estimated_hours\": float, \"type\": str}]"
            )
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client._call_llm(prompt, max_tokens=300)
            )
            import re
            m = re.search(r"\[.*\]", result, re.DOTALL)
            if m:
                tasks = json.loads(m.group(0))
                return [{"goal_id": goal.id, "goal_title": goal.title, **t} for t in tasks]
        except Exception as e:
            logger.debug("Task decomposition LLM failed: %s", e)
        # Fallback: generate from KRs
        return [
            {"goal_id": goal.id, "goal_title": goal.title,
             "task": f"Advance: {kr.description} (current: {kr.current}/{kr.target} {kr.unit})",
             "estimated_hours": 2.0, "type": "execution"}
            for kr in goal.key_results if kr.progress < 1.0
        ][:5]

    async def _auto_review(self, goal: Goal) -> None:
        score = self._priority.score(goal)
        self._engine.mark_reviewed(goal.id, self._tenant_id, score, actor="auto_review")

    def get_objective_tree(self, root_id: str) -> dict:
        return self._engine.get_objective_tree(root_id, self._tenant_id)


# ── Scheduling daemon ──────────────────────────────────────────────────────────

class PlanningScheduler:
    """Runs weekly/daily planning on cadence."""

    def __init__(self) -> None:
        self._tenants: set[str] = set()
        self._task: asyncio.Task | None = None
        self._running = False

    def register_tenant(self, tenant_id: str) -> None:
        self._tenants.add(tenant_id)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="planning_scheduler")
        logger.info("PlanningScheduler started for %d tenants", len(self._tenants))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(3600)  # check every hour
            now = time.gmtime()
            # Monday 06:00 UTC → weekly plan
            if now.tm_wday == 0 and now.tm_hour == 6:
                for tenant_id in self._tenants:
                    try:
                        planner = StrategicPlanner(tenant_id)
                        await planner.generate_weekly_plan()
                    except Exception as e:
                        logger.error("Weekly plan failed tenant=%s: %s", tenant_id, e)


_scheduler: PlanningScheduler | None = None

def get_planning_scheduler() -> PlanningScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = PlanningScheduler()
    return _scheduler


def get_strategic_planner(tenant_id: str) -> StrategicPlanner:
    return StrategicPlanner(tenant_id)
