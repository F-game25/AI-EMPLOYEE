"""Application-layer planner emitting deterministic task graphs."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.contracts import TaskGraph, TaskNode
from core.knowledge_store import get_knowledge_store
from core.learning_engine import get_learning_engine
from core.memory_index import get_memory_index

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
        context = self._build_context(goal)
        tasks = self._build_tasks(goal=goal, run_id=run_id, best=best_strategies or [])
        strategy_hint = "general:task_orchestrator"
        reason_hint = "Based on previous similar tasks, strategy general:task_orchestrator performed best because it produced the most reliable outcomes."
        if best_strategies:
            first = best_strategies[0] or {}
            cfg = first.get("config", {}) if isinstance(first, dict) else {}
            strategy_hint = str(cfg.get("strategy_used") or f"{self.classify_goal(goal)}:{first.get('agent', 'problem-solver')}")
            reason_hint = str(cfg.get("memory_usage_reason") or f"Based on previous similar tasks, strategy {strategy_hint} performed best because it produced stronger outcomes in this context.")
        prompt = (
            "You have learned the following relevant context:\n"
            f"{context}\n\n"
            f"{reason_hint}\n"
            "Use this to make better decisions."
        )
        for task in tasks:
            task.input = {
                **task.input,
                "context": context,
                "context_prompt": prompt,
                "planner_memory_reasoning": reason_hint,
                "planner_strategy_hint": strategy_hint,
            }
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

    @staticmethod
    def _build_context(goal: str) -> dict[str, Any]:
        store = get_knowledge_store()
        memories = get_memory_index().get_relevant_memories(goal, top_k=5)
        learned = get_learning_engine().search_memory(goal, top_k=5)
        return {
            "knowledge": store.get_relevant_context(goal),
            "relevant_memory": learned,
            "memories": [
                {
                    "id": m.get("id"),
                    "text": m.get("text"),
                    "importance": m.get("importance", 0.0),
                    "usage_count": m.get("usage_count", 0),
                }
                for m in memories
            ],
            "user_profile": store.snapshot().get("user_profile", {}),
        }

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
