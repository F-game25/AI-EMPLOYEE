"""Application-layer planner emitting deterministic task graphs."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.contracts import TaskGraph, TaskNode

if TYPE_CHECKING:
    from analytics.structured_logger import StructuredLogger


class Planner:
    """Deterministic planner: input goal -> structured task graph."""

    # Keep both UK/US variants ("analyse"/"analyze") for user input robustness.
    _GOAL_KEYWORDS = {
        "content_generation": ("content", "post", "publish", "video"),
        "lead_generation": ("lead", "prospect", "outreach"),
        "email_marketing": ("email", "campaign", "newsletter"),
        "analytics": ("analyse", "analyze", "report", "metric"),
        "task_learn_topic": ("learn about", "learn how to run a business", "research online product sales", "research "),
    }

    def __init__(self, logger: StructuredLogger | None = None) -> None:
        self._logger = logger

    def classify_goal(self, goal: str) -> str:
        text = goal.lower()
        if (
            "learn about" in text or
            "learn how to run a business" in text or
            "research online product sales" in text
        ):
            return "task_learn_topic"
        for goal_type, keywords in self._GOAL_KEYWORDS.items():
            if any(word in text for word in keywords):
                return goal_type
        return "general"

    def plan(
        self,
        *,
        goal: str,
        run_id: str,
        best_strategies: list[dict[str, Any]] | None = None,
    ) -> TaskGraph:
        import time
        start = time.perf_counter()
        tasks = self._build_tasks(goal=goal, run_id=run_id, best=best_strategies or [])
        graph = TaskGraph(run_id=run_id, goal=goal, tasks=tasks)
        graph.validate_no_cycles()
        latency_ms = (time.perf_counter() - start) * 1000
        if self._logger is not None:
            self._logger.log_event(
                component="planner",
                action="plan",
                result="success",
                latency_ms=latency_ms,
                meta={"run_id": run_id, "tasks": len(tasks), "goal_type": self.classify_goal(goal)},
            )
        return graph

    def _build_tasks(
        self,
        *,
        goal: str,
        run_id: str,
        best: list[dict[str, Any]],
    ) -> list[TaskNode]:
        if best:
            return self._tasks_from_strategies(goal=goal, run_id=run_id, best=best)
        goal_type = self.classify_goal(goal)
        flow = self._flow_for_goal_type(goal_type)
        return self._tasks_from_flow(goal=goal, run_id=run_id, flow=flow)

    def _tasks_from_strategies(
        self,
        *,
        goal: str,
        run_id: str,
        best: list[dict[str, Any]],
    ) -> list[TaskNode]:
        tasks: list[TaskNode] = []
        previous: str | None = None
        for idx, strategy in enumerate(best[:2], start=1):
            task_id = f"{run_id}-t{idx}"
            dependencies = [previous] if previous else []
            tasks.append(
                TaskNode(
                    task_id=task_id,
                    skill=strategy.get("agent", "problem-solver"),
                    input={**strategy.get("config", {}), "goal": goal},
                    expected_output={"status": "success"},
                    dependencies=dependencies,
                )
            )
            previous = task_id
        return tasks

    def _tasks_from_flow(self, *, goal: str, run_id: str, flow: list[str]) -> list[TaskNode]:
        tasks: list[TaskNode] = []
        for idx, skill in enumerate(flow, start=1):
            task_id = f"{run_id}-t{idx}"
            dependencies = [tasks[-1].task_id] if tasks else []
            tasks.append(
                TaskNode(
                    task_id=task_id,
                    skill=skill,
                    input={"goal": goal},
                    expected_output=self._expected_output(skill),
                    dependencies=dependencies,
                )
            )
        return tasks

    def _flow_for_goal_type(self, goal_type: str) -> list[str]:
        mapping = {
            "content_generation": ["content-calendar", "social-media-manager"],
            "lead_generation": ["lead-generator", "lead-crm"],
            "email_marketing": ["email-marketing"],
            "analytics": ["ceo-briefing"],
            "task_learn_topic": ["problem-solver"],
            "general": ["problem-solver"],
        }
        return mapping.get(goal_type, ["problem-solver"])

    def _expected_output(self, skill: str) -> dict[str, Any]:
        by_skill = {
            "lead-generator": {"status": "success", "action_result": {}},
            "lead-crm": {"status": "success"},
            "email-marketing": {"status": "success"},
            "ceo-briefing": {"status": "success"},
            "content-calendar": {"status": "success"},
            "social-media-manager": {"status": "success"},
            "problem-solver": {"status": "success"},
        }
        return by_skill.get(skill, {"status": "success"})
