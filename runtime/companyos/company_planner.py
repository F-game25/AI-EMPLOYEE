"""CompanyPlanner — turn a validated brief into a roadmap, executed via M7 swarm.

Thin: reuses the Business Swarm (M7) to decompose the company goal into milestones
and to run them (approval-gated, no fake autonomy). No duplicate orchestration.
"""
from __future__ import annotations

import threading
import uuid


def _company_goal(brief: dict) -> str:
    idea = str(brief.get("idea") or "").strip()
    parts = [f"Build and launch: {idea}"]
    if brief.get("target_customer"):
        parts.append(f"for {brief['target_customer']}")
    if brief.get("monetization"):
        parts.append(f"monetized via {brief['monetization']}")
    return " ".join(parts)


class CompanyPlanner:
    def build_roadmap(self, brief: dict, validation: dict | None = None) -> dict:
        """brief → {goal, milestones:[{id,title,needed_capability,depends_on,status}]}."""
        goal = _company_goal(brief or {})
        try:
            from agents.business_swarm.task_decomposer import decompose
            subtasks = decompose(goal)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"planner unavailable: {exc}", "goal": goal, "milestones": []}
        milestones = []
        for s in subtasks:
            milestones.append({
                "id": s.get("id") or str(uuid.uuid4())[:8],
                "title": s.get("description") or "milestone",
                "needed_capability": s.get("needed_capability"),
                "depends_on": s.get("depends_on") or [],
                "status": "pending",
            })
        return {"ok": True, "goal": goal, "milestones": milestones}

    def run_cycle(self, goal: str) -> dict:
        """Execute one orchestrated cycle via the swarm (approval-gated)."""
        try:
            from agents.business_swarm.swarm import get_business_swarm
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"swarm unavailable: {exc}"}
        try:
            out = get_business_swarm().run_goal(goal)
            agg = out.get("aggregate") or {}
            return {
                "ok": True,
                "executed": len((out.get("results") or {}).get("results") or []),
                "approvals_required": agg.get("approvals_required") or [],
                "deliverables": agg.get("deliverables") or [],
                "failed": agg.get("failed") or [],
                "summary": agg.get("summary"),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}


_instance: CompanyPlanner | None = None
_instance_lock = threading.Lock()


def get_company_planner() -> CompanyPlanner:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = CompanyPlanner()
    return _instance
