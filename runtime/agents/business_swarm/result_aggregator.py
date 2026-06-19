"""result_aggregator — fold executor results into a structured swarm aggregate."""

from __future__ import annotations

from typing import Any


def aggregate(exec_result: dict[str, Any]) -> dict[str, Any]:
    """Summarize results into {summary, deliverables[], approvals_required[], failed[]}."""
    results = list((exec_result or {}).get("results") or [])

    deliverables: list[dict[str, Any]] = []
    approvals_required: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []

    for r in results:
        status = r.get("status")
        if status == "completed":
            deliverables.append(
                {
                    "subtask_id": r.get("subtask_id"),
                    "agent_id": r.get("agent_id"),
                    "output_contract": r.get("output_contract"),
                    "output": r.get("output"),
                    "is_draft": r.get("is_draft", True),
                }
            )
        elif status == "pending_approval":
            approvals_required.append(
                {
                    "subtask_id": r.get("subtask_id"),
                    "agent_id": r.get("agent_id"),
                    "requires_approval_for": r.get("requires_approval_for"),
                    "risk_level": r.get("risk_level"),
                    "detail": r.get("detail"),
                }
            )
        elif status == "unavailable":
            unavailable.append({"subtask_id": r.get("subtask_id"), "detail": r.get("detail")})
        else:  # error / no_agent / dependency_error
            failed.append(
                {"subtask_id": r.get("subtask_id"), "status": status, "detail": r.get("detail")}
            )

    summary = (
        f"{len(deliverables)} draft deliverable(s), "
        f"{len(approvals_required)} pending approval, "
        f"{len(unavailable)} unavailable, "
        f"{len(failed)} failed of {len(results)} subtask(s)."
    )

    return {
        "summary": summary,
        "deliverables": deliverables,
        "approvals_required": approvals_required,
        "unavailable": unavailable,
        "failed": failed,
        "counts": {
            "total": len(results),
            "deliverables": len(deliverables),
            "approvals_required": len(approvals_required),
            "unavailable": len(unavailable),
            "failed": len(failed),
        },
    }
