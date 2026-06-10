"""Risk-aware safety gate for companion capability calls.

Decides whether a capability may run automatically or needs human approval,
based on the capability's risk level and the request context. When approval
is required it delegates to the existing HITL gate
(``runtime/core/hitl_gate.py``) — it does not reinvent approval queuing.

Fail-closed invariant
----------------------
For any action that requires approval, if the HITL gate is unavailable or
raises, the gate BLOCKS the action (``allowed=False``). A risky action is
never auto-allowed because the approval backend is down.
"""
from __future__ import annotations

import threading
from typing import Any

from companion.schemas import (
    Capability,
    L0,
    L1,
    L2,
    L3,
    L4,
    risk_at_least,
)


class SafetyGate:
    """Decides auto-run vs. human-approval for a capability call."""

    def evaluate(self, cap: Capability, request_context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Evaluate a capability against the request context.

        Returns a dict with: ``allowed``, ``requires_approval``,
        ``risk_level``, ``reason`` (and ``needs_explicit_confirm`` for L4,
        ``approval`` with the HITL request when approval was submitted).
        """
        ctx = request_context or {}
        level = cap.risk_level
        # A capability flagged requires_approval is treated as at least L3.
        force_approval = cap.requires_approval

        result: dict[str, Any] = {
            "allowed": False,
            "requires_approval": False,
            "risk_level": level,
            "reason": "",
        }

        if level == L4 or risk_at_least(level, L4):
            result["needs_explicit_confirm"] = True

        # ── L0 / L1: free to run ────────────────────────────────────────────
        if level in (L0, L1) and not force_approval:
            result["allowed"] = True
            result["requires_approval"] = False
            result["reason"] = f"{level} capability — no approval required"
            return result

        # ── L2: allowed only when explicitly commanded ──────────────────────
        if level == L2 and not force_approval:
            if ctx.get("explicitly_commanded"):
                result["allowed"] = True
                result["requires_approval"] = False
                result["reason"] = "L2 capability explicitly commanded — allowed"
                return result
            # not commanded -> needs approval (fall through to approval path)

        # ── L2 (not commanded) / L3 / L4 / forced: approval required ────────
        result["requires_approval"] = True
        approval = self._submit_for_approval(cap, ctx)
        # Fail closed: only allow if the HITL gate explicitly approved.
        approved = bool(approval.get("approved"))
        result["allowed"] = approved
        result["approval"] = approval
        if approval.get("error"):
            result["reason"] = (
                f"approval backend unavailable ({approval['error']}) — blocked (fail-closed)"
            )
        elif approved:
            result["reason"] = f"{level} capability approved by human operator"
        else:
            result["reason"] = (
                f"{level} capability requires human approval — pending"
            )
        return result

    # ── HITL delegation (defensive) ─────────────────────────────────────────

    def _submit_for_approval(self, cap: Capability, ctx: dict[str, Any]) -> dict[str, Any]:
        """Delegate to the existing HITL gate. Fails closed on any error."""
        try:
            from core.hitl_gate import get_hitl_gate

            gate = get_hitl_gate()
            return gate.require_approval(
                agent=ctx.get("agent", "companion"),
                action=cap.id,
                payload={
                    "capability": cap.id,
                    "subsystem": cap.subsystem,
                    "risk_level": cap.risk_level,
                    "context": {k: ctx[k] for k in ctx if k != "agent"},
                },
                submitted_by=ctx.get("submitted_by", "companion-gateway"),
                blocking=False,
            )
        except Exception as exc:  # fail CLOSED — never auto-allow a risky action
            return {"approved": False, "status": "blocked", "error": str(exc)}


# ── Singleton ────────────────────────────────────────────────────────────────

_instance: SafetyGate | None = None
_instance_lock = threading.Lock()


def get_safety_gate() -> SafetyGate:
    """Return the process-wide ``SafetyGate`` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SafetyGate()
    return _instance
