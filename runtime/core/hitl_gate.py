"""Human-in-the-Loop (HITL) gate for high-risk AI agent actions.

EU AI Act compliance — Article 14 (Human oversight)
----------------------------------------------------
The following agent categories are classified as *high-risk* under the EU AI
Act and/or present material ethical risks:

  * Recruitment / HR  — hr-manager, recruiter
  * Lead scoring      — lead-scorer, qualification-agent, lead-intelligence
  * Profiling         — (any agent whose action type is "profiling")

For these agents every *consequential action* (score, rank, hire/reject
recommendation, send outreach to a specific person) must be:

  1. Queued as a pending HITL request.
  2. Shown to a human operator in the dashboard.
  3. Either approved or rejected before execution.

Architecture
------------
``HITLGate`` is a singleton.  Agents call ``require_approval()`` before
executing a consequential action.  The call blocks until the operator acts
(or a timeout elapses).  The dashboard polls ``pending_requests()`` and
calls ``approve()`` / ``reject()``.

All requests and decisions are written to the AuditEngine.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

# ── Agents that always require HITL for consequential actions ─────────────────

HITL_REQUIRED_AGENTS: frozenset[str] = frozenset({
    "hr-manager",
    "recruiter",
    "lead-scorer",
    "lead-intelligence",
    "qualification-agent",
    "lead-hunter-elite",
})

# Action keywords that trigger HITL regardless of agent
HITL_TRIGGER_ACTIONS: frozenset[str] = frozenset({
    "hire",
    "reject_candidate",
    "send_offer",
    "profile",
    "score_lead",
    "rank_candidate",
    "disqualify",
})

# How long (seconds) a pending request will wait before auto-timing-out
_DEFAULT_TIMEOUT_S = 3600  # 1 hour


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _audit(*, actor: str, action: str, data: dict[str, Any]) -> None:
    try:
        from core.audit_engine import get_audit_engine
        get_audit_engine().record(
            actor=actor,
            action=action,
            input_data=data,
            output_data={},
            risk_score=0.85,
        )
    except Exception:
        pass


# ── Request model ──────────────────────────────────────────────────────────────

class HITLRequest:
    """A pending human-approval request."""

    def __init__(
        self,
        *,
        agent: str,
        action: str,
        payload: dict[str, Any],
        submitted_by: str,
        timeout_s: int = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self.id: str = f"hitl-{uuid.uuid4().hex[:10]}"
        self.agent = agent
        self.action = action
        self.payload = payload
        self.submitted_by = submitted_by
        self.timeout_s = timeout_s
        self.status: str = "pending"   # pending | approved | rejected | timeout
        self.created_at: str = _ts()
        self.decided_at: str | None = None
        self.decided_by: str | None = None
        self.reason: str | None = None
        self._event = threading.Event()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "action": self.action,
            "payload": self.payload,
            "submitted_by": self.submitted_by,
            "status": self.status,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "reason": self.reason,
            "requires_human_approval": True,
        }


# ── Gate singleton ─────────────────────────────────────────────────────────────

class HITLGate:
    """Thread-safe HITL approval gate.

    Usage (agent side)
    ------------------
    ::

        gate = get_hitl_gate()
        result = gate.require_approval(
            agent="recruiter",
            action="send_offer",
            payload={"candidate_id": "c-123", "offer": "..."},
            submitted_by="recruiter-agent",
        )
        if not result["approved"]:
            # do not proceed
            return {"status": "blocked", "reason": result.get("reason")}

    Usage (dashboard side)
    ----------------------
    ::

        gate.pending_requests()    → list[dict]
        gate.approve(request_id)   → dict
        gate.reject(request_id)    → dict
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._requests: dict[str, HITLRequest] = {}

    # ── Agent-facing ──────────────────────────────────────────────────────────

    def is_required(self, agent: str, action: str = "") -> bool:
        """Return True if the given agent/action combination requires HITL."""
        if agent in HITL_REQUIRED_AGENTS:
            return True
        action_lower = (action or "").lower()
        return any(kw in action_lower for kw in HITL_TRIGGER_ACTIONS)

    def require_approval(
        self,
        *,
        agent: str,
        action: str,
        payload: dict[str, Any] | None = None,
        submitted_by: str = "system",
        timeout_s: int = _DEFAULT_TIMEOUT_S,
        blocking: bool = False,
    ) -> dict[str, Any]:
        """Submit a HITL request and optionally block until decided.

        Parameters
        ----------
        agent        : Agent that wants to perform the action.
        action       : Human-readable description of the consequential action.
        payload      : Data that describes what will be done.
        submitted_by : Actor submitting the request (agent id or user id).
        timeout_s    : Seconds to wait when *blocking* is True.
        blocking     : If True, block until a human decides or timeout elapses.
                       If False (default), return immediately with status=pending.

        Returns
        -------
        dict with keys: ``approved`` (bool), ``status``, ``request_id``.
        """
        req = HITLRequest(
            agent=agent,
            action=action,
            payload=payload or {},
            submitted_by=submitted_by,
            timeout_s=timeout_s,
        )
        with self._lock:
            self._requests[req.id] = req

        _audit(
            actor=submitted_by,
            action="hitl_submitted",
            data={"request_id": req.id, "agent": agent, "action": action},
        )

        if blocking:
            approved = req._event.wait(timeout=timeout_s)
            with self._lock:
                if not approved:
                    req.status = "timeout"
                    req.decided_at = _ts()
            _audit(
                actor="system",
                action="hitl_timeout" if req.status == "timeout" else f"hitl_{req.status}",
                data={"request_id": req.id, "agent": agent},
            )
            return {
                "approved": req.status == "approved",
                "status": req.status,
                "request_id": req.id,
            }

        return {
            "approved": False,
            "status": "pending",
            "request_id": req.id,
            "message": (
                f"Action '{action}' by agent '{agent}' requires human approval. "
                f"Request ID: {req.id}"
            ),
        }

    # ── Dashboard-facing ──────────────────────────────────────────────────────

    def pending_requests(self) -> list[dict[str, Any]]:
        """Return all requests currently awaiting human decision."""
        with self._lock:
            return [r.to_dict() for r in self._requests.values() if r.status == "pending"]

    def all_requests(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return all requests (any status), most recent first."""
        with self._lock:
            items = sorted(self._requests.values(), key=lambda r: r.created_at, reverse=True)
            return [r.to_dict() for r in items[:limit]]

    def approve(
        self,
        request_id: str,
        *,
        decided_by: str = "operator",
        reason: str = "",
    ) -> dict[str, Any]:
        """Approve a pending HITL request."""
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                return {"ok": False, "error": "request not found"}
            if req.status != "pending":
                return {"ok": False, "error": f"request already {req.status}"}
            req.status = "approved"
            req.decided_at = _ts()
            req.decided_by = decided_by
            req.reason = reason
            req._event.set()

        _audit(
            actor=decided_by,
            action="hitl_approved",
            data={"request_id": request_id, "agent": req.agent, "reason": reason},
        )
        return {"ok": True, "request_id": request_id, "status": "approved"}

    def reject(
        self,
        request_id: str,
        *,
        decided_by: str = "operator",
        reason: str = "",
    ) -> dict[str, Any]:
        """Reject a pending HITL request."""
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                return {"ok": False, "error": "request not found"}
            if req.status != "pending":
                return {"ok": False, "error": f"request already {req.status}"}
            req.status = "rejected"
            req.decided_at = _ts()
            req.decided_by = decided_by
            req.reason = reason
            req._event.set()

        _audit(
            actor=decided_by,
            action="hitl_rejected",
            data={"request_id": request_id, "agent": req.agent, "reason": reason},
        )
        return {"ok": True, "request_id": request_id, "status": "rejected"}

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            req = self._requests.get(request_id)
        return req.to_dict() if req else None


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: HITLGate | None = None
_instance_lock = threading.Lock()


def get_hitl_gate() -> HITLGate:
    """Return the process-wide HITLGate singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = HITLGate()
    return _instance
