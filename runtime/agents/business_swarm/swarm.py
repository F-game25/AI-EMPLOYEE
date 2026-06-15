"""BusinessSwarm — facade chaining decompose → assign → dep-order → execute → aggregate.

Wraps every stage so bad input or subsystem failure returns a valid structured
result instead of raising. Honors all contract approval gates (no fake autonomy).
"""

from __future__ import annotations

from typing import Any, Optional

from . import assignment_engine, result_aggregator, task_decomposer
from .dependency_manager import DependencyCycleError, topological_order
from .parallel_executor import run as _execute
from .registry import BusinessSwarmRegistry, get_registry


def _serialize_assignments(assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for a in assignments:
        contract = a.get("contract")
        out.append(
            {
                "subtask": a.get("subtask"),
                "agent_id": a.get("agent_id"),
                "contract": contract.to_dict() if contract is not None else None,
            }
        )
    return out


class BusinessSwarm:
    """Orchestrates a business goal across formalized agent contracts."""

    def __init__(self, registry: Optional[BusinessSwarmRegistry] = None):
        self.registry = registry or get_registry()

    def run_goal(self, goal: str) -> dict[str, Any]:
        if not isinstance(goal, str) or not goal.strip():
            return {
                "status": "invalid_input",
                "goal": goal,
                "decomposition": [],
                "assignments": [],
                "results": {"results": [], "order": []},
                "aggregate": result_aggregator.aggregate({"results": []}),
            }

        try:
            decomposition = task_decomposer.decompose(goal)
        except Exception as exc:
            decomposition = []
            return self._fail(goal, f"decompose failed: {exc}")

        try:
            assignments = assignment_engine.assign(decomposition, self.registry)
        except Exception as exc:
            return self._fail(goal, f"assign failed: {exc}", decomposition)

        order: list[str] = []
        try:
            order = topological_order(decomposition)
        except DependencyCycleError as exc:
            return {
                "status": "dependency_error",
                "goal": goal,
                "decomposition": decomposition,
                "assignments": _serialize_assignments(assignments),
                "results": {"results": [], "order": [], "detail": str(exc)},
                "aggregate": result_aggregator.aggregate({"results": []}),
            }
        except Exception as exc:
            return self._fail(goal, f"ordering failed: {exc}", decomposition, assignments)

        exec_result = _execute(assignments)
        if not exec_result.get("order"):
            exec_result["order"] = order
        aggregate = result_aggregator.aggregate(exec_result)

        return {
            "status": "ok",
            "goal": goal,
            "decomposition": decomposition,
            "assignments": _serialize_assignments(assignments),
            "results": exec_result,
            "aggregate": aggregate,
        }

    def _fail(
        self,
        goal: str,
        detail: str,
        decomposition: Optional[list] = None,
        assignments: Optional[list] = None,
    ) -> dict[str, Any]:
        return {
            "status": "error",
            "detail": detail,
            "goal": goal,
            "decomposition": decomposition or [],
            "assignments": _serialize_assignments(assignments) if assignments else [],
            "results": {"results": [], "order": []},
            "aggregate": result_aggregator.aggregate({"results": []}),
        }


_SWARM: Optional[BusinessSwarm] = None


def get_business_swarm() -> BusinessSwarm:
    """Singleton accessor."""
    global _SWARM
    if _SWARM is None:
        _SWARM = BusinessSwarm()
    return _SWARM
