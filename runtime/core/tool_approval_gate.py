"""Tool Approval Gate — HITL for risk-2+ tool executions.

When a ReActAgent wants to call a risk-2+ tool, it registers a pending
approval here. The Python API exposes these via GET /tools/pending, and
the Node.js forge backend exposes POST /api/forge/tools/:id/approve.

The gate uses an event-based blocking mechanism with a configurable timeout
(default 120s). If no human approves within the timeout, the tool is blocked
and the agent receives an observation indicating approval was required.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

_pending: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

_DEFAULT_TIMEOUT_S = 120  # 2 minutes


def request_approval(
    tool_name: str,
    payload: dict[str, Any],
    agent_id: str = "react_agent",
    timeout_s: int = _DEFAULT_TIMEOUT_S,
    auto_approve_risk: int | None = None,
) -> dict[str, Any]:
    """Register a pending tool approval and block until approved, rejected, or timed out.

    Args:
        tool_name:         The tool requested.
        payload:           The tool's input payload.
        agent_id:          The agent making the request.
        timeout_s:         Seconds to wait for human approval.
        auto_approve_risk: If set, tools at or below this risk level are auto-approved.

    Returns:
        {"approved": bool, "request_id": str, "status": "approved"|"rejected"|"timeout"}
    """
    request_id = str(uuid.uuid4())
    event = threading.Event()
    entry = {
        "id": request_id,
        "tool": tool_name,
        "payload": payload,
        "agent_id": agent_id,
        "status": "pending",
        "submitted_at": time.time(),
        "approved": False,
        "_event": event,
    }

    with _lock:
        _pending[request_id] = entry

    approved = event.wait(timeout=timeout_s)

    with _lock:
        result = _pending.pop(request_id, entry)

    if not approved:
        result["status"] = "timeout"
        result["approved"] = False

    return {"approved": result["approved"], "request_id": request_id, "status": result["status"]}


def approve(request_id: str) -> bool:
    """Approve a pending tool call. Returns True if found, False if already gone."""
    with _lock:
        entry = _pending.get(request_id)
        if not entry:
            return False
        entry["approved"] = True
        entry["status"] = "approved"
        entry["_event"].set()
    return True


def reject(request_id: str) -> bool:
    """Reject a pending tool call. Returns True if found."""
    with _lock:
        entry = _pending.get(request_id)
        if not entry:
            return False
        entry["approved"] = False
        entry["status"] = "rejected"
        entry["_event"].set()
    return True


def pending_approvals() -> list[dict[str, Any]]:
    """Return list of pending tool approval requests (without internal _event field)."""
    with _lock:
        return [
            {k: v for k, v in e.items() if k != "_event"}
            for e in _pending.values()
            if e["status"] == "pending"
        ]
