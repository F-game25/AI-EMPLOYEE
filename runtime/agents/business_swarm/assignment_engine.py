"""assignment_engine — match each subtask's needed_capability to the best agent."""

from __future__ import annotations

from typing import Any, Optional

from .agent_contracts import AgentContract
from .registry import BusinessSwarmRegistry, get_registry


def _best_match(
    registry: BusinessSwarmRegistry, capability: str, description: str
) -> Optional[AgentContract]:
    # 1) Direct capability match (strongest signal).
    direct = registry.by_capability(capability)
    if direct:
        return direct[0]
    # 2) Fall back to goal-style scoring over the capability + description text.
    ranked = registry.find_for_goal(f"{capability} {description}")
    if ranked:
        return ranked[0]
    return None


def assign(
    subtasks: list[dict[str, Any]], registry: Optional[BusinessSwarmRegistry] = None
) -> list[dict[str, Any]]:
    """Return [{subtask, agent_id, contract}] — agent_id/contract None if unmatched."""
    reg = registry or get_registry()
    assignments: list[dict[str, Any]] = []
    for st in subtasks:
        capability = str(st.get("needed_capability") or "")
        description = str(st.get("description") or "")
        contract = _best_match(reg, capability, description)
        assignments.append(
            {
                "subtask": st,
                "agent_id": contract.id if contract else None,
                "contract": contract,
            }
        )
    return assignments
