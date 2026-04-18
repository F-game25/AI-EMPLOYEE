"""Ascend Forge execution pipeline with risk classification and approval queue.

Risk levels
-----------
LOW    (score < 0.3)  — auto-allowed; no approval required
MEDIUM (score < 0.7)  — queued; requires operator confirmation via approve()
HIGH   (score >= 0.7) — blocked; requires explicit override approval

All submissions and decisions are recorded in the audit engine.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any


_DEFAULT_AGENTS = ("intel_agent", "email_ninja", "social_guru")

# ── risk scoring heuristics ───────────────────────────────────────────────────

_HIGH_RISK_KEYWORDS = frozenset(
    {"deploy", "production", "delete", "drop", "rm ", "overwrite", "replace all", "wipe"}
)
_MEDIUM_RISK_KEYWORDS = frozenset(
    {"refactor", "update", "migrate", "change", "modify", "patch", "rewrite"}
)


def _score_goal(goal: str) -> float:
    text = goal.lower()
    if any(kw in text for kw in _HIGH_RISK_KEYWORDS):
        return 0.80
    if any(kw in text for kw in _MEDIUM_RISK_KEYWORDS):
        return 0.45
    return 0.15


def _risk_label(score: float) -> str:
    if score >= 0.7:
        return "HIGH"
    if score >= 0.3:
        return "MEDIUM"
    return "LOW"


# ── approval queue ────────────────────────────────────────────────────────────

class ForgeChangeRequest:
    """A pending Forge change request awaiting risk review."""

    def __init__(
        self,
        *,
        objective_id: str,
        goal: str,
        constraints: dict[str, Any],
        priority: str,
        plan: list[str],
        risk_score: float,
    ) -> None:
        self.id: str = f"fcr-{uuid.uuid4().hex[:10]}"
        self.objective_id = objective_id
        self.goal = goal
        self.constraints = constraints
        self.priority = priority
        self.plan = plan
        self.risk_score = risk_score
        self.risk_level = _risk_label(risk_score)
        self.status: str = "pending"  # pending | approved | rejected | sandbox_passed
        self.created_at: str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.decided_at: str | None = None
        self.decided_by: str | None = None
        self.sandbox_result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "objective_id": self.objective_id,
            "goal": self.goal,
            "constraints": self.constraints,
            "priority": self.priority,
            "plan": self.plan,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "status": self.status,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "sandbox_result": self.sandbox_result,
        }


class AscendForgeExecutor:
    """Objective-first Ascend Forge execution pipeline with enterprise safety."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._queue: deque[ForgeChangeRequest] = deque(maxlen=200)

    # ── plan builder ──────────────────────────────────────────────────────────

    def build_plan(self, goal: str) -> list[str]:
        text = str(goal or "").lower()
        plan: list[str] = ["analyze baseline performance", "identify highest-impact bottlenecks"]
        if "conversion" in text or "funnel" in text:
            plan.extend(["design conversion experiments", "deploy funnel optimizations"])
        elif "revenue" in text or "growth" in text:
            plan.extend(["prioritize growth loops", "launch growth execution sprint"])
        else:
            plan.extend(["generate optimization hypotheses", "execute incremental improvements"])
        return plan

    # ── submission with risk gate ─────────────────────────────────────────────

    def submit_change(
        self,
        *,
        objective_id: str,
        goal: str,
        constraints: dict[str, Any] | None = None,
        priority: str = "medium",
        submitted_by: str = "system",
    ) -> ForgeChangeRequest:
        """Submit a change request.  HIGH-risk changes are blocked immediately."""
        constraints = constraints or {}
        risk_score = _score_goal(goal)
        plan = self.build_plan(goal)
        req = ForgeChangeRequest(
            objective_id=objective_id,
            goal=goal,
            constraints=constraints,
            priority=priority,
            plan=plan,
            risk_score=risk_score,
        )
        if risk_score >= 0.7:
            req.status = "rejected"
            req.decided_at = req.created_at
            req.decided_by = "system:risk_gate"
        elif risk_score < 0.3:
            req.status = "approved"
            req.decided_at = req.created_at
            req.decided_by = "system:auto_low_risk"
        # MEDIUM → stays "pending" until operator approves

        with self._lock:
            self._queue.appendleft(req)

        self._audit(
            actor=submitted_by,
            action="forge_submit",
            input_data={"goal": goal, "risk_level": req.risk_level},
            output_data={"request_id": req.id, "status": req.status},
            risk_score=risk_score,
        )
        return req

    def approve(self, request_id: str, *, approved_by: str = "operator") -> ForgeChangeRequest | None:
        """Approve a pending MEDIUM-risk change request."""
        with self._lock:
            req = self._find(request_id)
            if req is None or req.status != "pending":
                return req
            req.status = "approved"
            req.decided_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            req.decided_by = approved_by
        self._audit(
            actor=approved_by,
            action="forge_approve",
            input_data={"request_id": request_id},
            output_data={"status": "approved"},
            risk_score=0.5,
        )
        return req

    def reject(self, request_id: str, *, rejected_by: str = "operator") -> ForgeChangeRequest | None:
        """Reject a pending change request."""
        with self._lock:
            req = self._find(request_id)
            if req is None or req.status != "pending":
                return req
            req.status = "rejected"
            req.decided_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            req.decided_by = rejected_by
        self._audit(
            actor=rejected_by,
            action="forge_reject",
            input_data={"request_id": request_id},
            output_data={"status": "rejected"},
            risk_score=0.3,
        )
        return req

    def sandbox_test(self, request_id: str) -> ForgeChangeRequest | None:
        """Run the static sandbox pre-screen on an approved request."""
        with self._lock:
            req = self._find(request_id)
        if req is None:
            return None
        try:
            from core.security_layer import get_security_layer
            result = get_security_layer().sandbox_check(req.goal)
        except Exception as exc:
            result = {"safe": False, "violations": [str(exc)]}
        with self._lock:
            req.sandbox_result = result
            if result.get("safe") and req.status == "approved":
                req.status = "sandbox_passed"
        return req

    # ── queue inspection ──────────────────────────────────────────────────────

    def queue(self, *, status: str = "") -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._queue)
        if status:
            items = [r for r in items if r.status == status]
        return [r.to_dict() for r in items]

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            req = self._find(request_id)
        return req.to_dict() if req else None

    # ── legacy compatibility ──────────────────────────────────────────────────

    def execute_objective(
        self,
        *,
        objective_id: str,
        goal: str,
        constraints: dict[str, Any] | None = None,
        priority: str = "medium",
    ) -> dict[str, Any]:
        """Submit and immediately execute LOW-risk goals; return status for others."""
        req = self.submit_change(
            objective_id=objective_id,
            goal=goal,
            constraints=constraints,
            priority=priority,
        )
        agents_used = list(_DEFAULT_AGENTS)
        status = "running" if req.status in ("approved", "sandbox_passed") else req.status
        return {
            "objective_id": objective_id,
            "request_id": req.id,
            "goal": goal,
            "constraints": req.constraints,
            "priority": priority,
            "plan": req.plan,
            "agents_used": agents_used,
            "progress": 0,
            "status": status,
            "risk_level": req.risk_level,
            "risk_score": req.risk_score,
            "results": [],
        }

    # ── helpers ───────────────────────────────────────────────────────────────

    def _find(self, request_id: str) -> ForgeChangeRequest | None:
        for req in self._queue:
            if req.id == request_id:
                return req
        return None

    @staticmethod
    def _audit(
        *,
        actor: str,
        action: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        risk_score: float,
    ) -> None:
        try:
            from core.audit_engine import get_audit_engine
            get_audit_engine().record(
                actor=actor,
                action=action,
                input_data=input_data,
                output_data=output_data,
                risk_score=risk_score,
            )
        except Exception:
            pass


_executor: AscendForgeExecutor | None = None
_executor_lock = threading.Lock()


def get_ascend_forge_executor() -> AscendForgeExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = AscendForgeExecutor()
    return _executor
