"""parallel_executor — run assigned subtasks honestly.

GOVERNANCE (non-negotiable):
- A subtask whose action hits the agent's `requires_approval_for` is NEVER executed;
  it returns status='pending_approval'. No fake autonomy.
- If the LLM engine is unavailable, return status='unavailable' — never fabricate a
  "completed" result with no real output.
- Every executor path is wrapped: it returns a structured status, never throws.

All produced text is a draft/analysis for human review, not a real-world action.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Optional

from .agent_contracts import (
    ACTION_DEPLOY,
    ACTION_OUTREACH,
    ACTION_PUBLISH,
    ACTION_SCAN,
    ACTION_SEND_EMAIL,
    ACTION_SPEND,
    ACTION_TRADE,
    AgentContract,
)
from .dependency_manager import DependencyCycleError, independent_groups

try:
    from engine.api import generate as _engine_generate  # type: ignore
except Exception:  # pragma: no cover - import guard
    _engine_generate = None

# Map a subtask's intent (from needed_capability text) to a consequential action,
# so we can detect when execution would require approval.
_INTENT_ACTION_KEYWORDS: dict[str, list[str]] = {
    ACTION_PUBLISH: ["publish", "post", "schedule"],
    ACTION_OUTREACH: ["outreach", "prospect", "cold"],
    ACTION_SEND_EMAIL: ["send", "email", "campaign"],
    ACTION_SPEND: ["budget", "spend", "ad"],
    ACTION_TRADE: ["trade", "order", "portfolio"],
    ACTION_DEPLOY: ["deploy", "apply", "patch"],
    ACTION_SCAN: ["scan", "recon", "osint"],
}


def _intended_action(subtask: dict[str, Any], contract: AgentContract) -> Optional[str]:
    """Return the consequential action this subtask would perform, if any."""
    text = (
        f"{subtask.get('needed_capability','')} {subtask.get('description','')}"
    ).lower()
    for action in contract.requires_approval_for:
        kws = _INTENT_ACTION_KEYWORDS.get(action, [action])
        if any(kw in text for kw in kws):
            return action
    return None


def _run_one(assignment: dict[str, Any]) -> dict[str, Any]:
    subtask = assignment.get("subtask") or {}
    sid = str(subtask.get("id", "?"))
    contract: Optional[AgentContract] = assignment.get("contract")
    base = {"subtask_id": sid, "agent_id": assignment.get("agent_id")}

    try:
        if contract is None:
            return {**base, "status": "no_agent", "output": None,
                    "detail": "no contract matched this capability"}

        action = _intended_action(subtask, contract)
        if action is not None:
            # APPROVAL-REQUIRED → never executed. Honest pending status.
            return {
                **base,
                "status": "pending_approval",
                "output": None,
                "requires_approval_for": action,
                "risk_level": contract.risk_level,
                "detail": f"{contract.id} requires approval for '{action}' — not auto-executed",
            }

        if _engine_generate is None:
            return {**base, "status": "unavailable", "output": None,
                    "detail": "LLM engine unavailable — no fabricated result"}

        system = (
            f"You are the '{contract.role}' agent (id={contract.id}, "
            f"category={contract.category}). Output contract: {contract.output_contract}. "
            f"Produce a {contract.output_contract} ONLY. This is a draft for human review; "
            f"do not claim any real-world action was performed."
        )
        output = _engine_generate(prompt=str(subtask.get("description", "")), system=system)
        if not output or not str(output).strip():
            return {**base, "status": "unavailable", "output": None,
                    "detail": "engine returned empty output — not fabricating success"}
        return {
            **base,
            "status": "completed",
            "output": str(output),
            "output_contract": contract.output_contract,
            "is_draft": True,
        }
    except Exception as exc:  # never throw — structured status
        return {**base, "status": "error", "output": None, "detail": f"{type(exc).__name__}: {exc}"}


def run(assignments: list[dict[str, Any]], max_workers: int = 4) -> dict[str, Any]:
    """Execute independent subtasks (respecting dependency waves). Never throws."""
    subtasks = [a.get("subtask") or {} for a in assignments]
    by_id = {str(a.get("subtask", {}).get("id")): a for a in assignments}

    try:
        waves = independent_groups(subtasks)
        order = [sid for wave in waves for sid in wave]
    except DependencyCycleError as exc:
        return {"results": [], "order": [], "status": "dependency_error", "detail": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive
        return {"results": [], "order": [], "status": "error", "detail": str(exc)}

    results: list[dict[str, Any]] = []
    for wave in waves:
        wave_assignments = [by_id[sid] for sid in wave if sid in by_id]
        if len(wave_assignments) > 1 and max_workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                results.extend(pool.map(_run_one, wave_assignments))
        else:
            results.extend(_run_one(a) for a in wave_assignments)

    return {"results": results, "order": order, "status": "ok"}
