"""Execution broker for the Companion Gateway.

Routes a classified intent to capabilities, runs the SAFE ones through real
read-only calls where one cheaply exists, and turns everything risky into an
*approval request* — it NEVER executes a capability the safety gate did not
clear. The broker sits between the orchestrator (which knows mode/intent) and
the subsystems (which do the actual work).

Honesty invariant
------------------
A capability is either:
  - wired to a genuine read-only subsystem call (real data), OR
  - returned as ``{status: 'not_implemented', cap: <id>}`` — a clearly marked
    stub. The broker never fabricates subsystem data. Adapters for the rest are
    a later phase (P6).

Safety invariant
----------------
Every candidate capability is run through ``safety_gate.evaluate``. Only
``allowed and not requires_approval`` capabilities execute. Anything requiring
approval is added to ``approvals_required`` and NOT executed. Any execution
error is captured as ``{status: 'error', ...}`` — the broker never crashes.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

from companion.capability_registry import get_capability_registry
from companion.safety_gate import get_safety_gate
from companion.schemas import Capability

logger = logging.getLogger("companion.execution_broker")

# How many candidate capabilities to consider per intent (best-first from the
# registry). Keeps a single turn bounded and cheap.
_MAX_CANDIDATES = 4


class ExecutionBroker:
    """Routes an intent to capabilities; executes the safe ones, gates the rest."""

    def __init__(self) -> None:
        self._registry = get_capability_registry()
        self._gate = get_safety_gate()
        # capability id -> real read-only executor. Honest dispatch only:
        # entries here are genuinely-available read-only calls.
        self._dispatch: dict[str, Callable[[Capability, dict], dict]] = {
            "system.health.read": self._exec_system_health,
            "memory.search": self._exec_memory_search,
        }

    def execute(
        self,
        intent: dict[str, Any],
        resolved: dict[str, Any],
        request_context: dict[str, Any],
        *,
        only_subsystems: Optional[set[str]] = None,
    ) -> dict[str, Any]:
        """Route ``intent`` to capabilities and execute the safe ones.

        Returns::
            {
              results: list[dict],         # one per executed/blocked capability
              approvals_required: list,    # human-readable approval requests
              executed: list[str],         # cap ids actually run
              blocked: list[str],          # cap ids gated behind approval
            }
        """
        intent = intent or {}
        resolved = resolved or {}
        ctx = dict(request_context or {})

        results: list[dict[str, Any]] = []
        approvals_required: list[dict[str, Any]] = []
        executed: list[str] = []
        blocked: list[str] = []

        mode = str(intent.get("mode", ""))
        task_type = intent.get("task_type")
        # An explicit imperative ("fix the build") lets L2 capabilities run
        # without a separate approval round-trip (the safety gate honours this).
        if intent.get("is_command"):
            ctx.setdefault("explicitly_commanded", True)

        # find_for_intent does token-overlap matching against capability
        # id/name/description/subsystem. The bare mode rarely overlaps, so route
        # on mode + the resolved (context-bound) text together — that's what
        # makes "what is the system doing?" reach system.health.read and
        # "apply the rate-limit patch" reach forge.apply_patch.
        routing_text = " ".join(
            s for s in (mode, str(resolved.get("resolved_text", "")
                                  or ctx.get("text", ""))) if s
        ).strip()
        candidates = self._registry.find_for_intent(routing_text, task_type)
        if only_subsystems is not None:
            candidates = [c for c in candidates if c.subsystem in only_subsystems]
        candidates = candidates[:_MAX_CANDIDATES]

        for cap in candidates:
            try:
                decision = self._gate.evaluate(cap, ctx)
            except Exception as exc:  # gate itself failing → block, never run
                logger.warning("safety gate raised for %s: %s", cap.id, exc)
                blocked.append(cap.id)
                results.append({"status": "blocked", "cap": cap.id,
                                "error": f"safety gate error: {exc}"})
                continue

            if decision.get("allowed") and not decision.get("requires_approval"):
                results.append(self._run(cap, intent, resolved, ctx))
                executed.append(cap.id)
            elif decision.get("requires_approval"):
                approvals_required.append(self._approval_request(cap, decision, resolved))
                blocked.append(cap.id)
            else:
                # Not allowed and not pending approval (e.g. gate declined) —
                # surface it without executing.
                blocked.append(cap.id)
                results.append({"status": "blocked", "cap": cap.id,
                                "reason": decision.get("reason", "not allowed")})

        return {
            "results": results,
            "approvals_required": approvals_required,
            "executed": executed,
            "blocked": blocked,
        }

    # ── Dispatch ────────────────────────────────────────────────────────────────

    def _run(self, cap: Capability, intent: dict, resolved: dict, ctx: dict) -> dict:
        """Invoke a cleared capability. Errors are captured, never raised."""
        fn = self._dispatch.get(cap.id)
        if fn is None:
            # Honest stub — adapter not wired yet (P6).
            return {"status": "not_implemented", "cap": cap.id,
                    "subsystem": cap.subsystem,
                    "note": "adapter not yet wired (P6)"}
        try:
            out = fn(cap, ctx)
            return {"status": "ok", "cap": cap.id, "data": out}
        except Exception as exc:  # noqa: BLE001 — broker must never crash
            logger.warning("capability %s execution failed: %s", cap.id, exc)
            return {"status": "error", "cap": cap.id, "error": str(exc)}

    # ── Real read-only executors ─────────────────────────────────────────────────

    @staticmethod
    def _exec_system_health(cap: Capability, ctx: dict) -> dict:
        """Live system health/resource snapshot (best-effort, read-only)."""
        from engine.compute.resource_manager import get_resource_manager
        return get_resource_manager().to_dict()

    @staticmethod
    def _exec_memory_search(cap: Capability, ctx: dict) -> dict:
        """Substring search across the engine memory store (read-only)."""
        from engine.api import memory_search
        query = str(ctx.get("query") or ctx.get("text") or "").strip()
        if not query:
            return {"results": [], "note": "no query provided"}
        top_k = int(ctx.get("top_k", 5) or 5)
        return {"results": memory_search(query=query, top_k=top_k)}

    # ── Approval request shaping ─────────────────────────────────────────────────

    @staticmethod
    def _approval_request(cap: Capability, decision: dict, resolved: dict) -> dict:
        """Human-readable approval card for a gated capability."""
        focus = resolved.get("focus") or {}
        affects = focus.get("label") if isinstance(focus, dict) else None
        rollback = None
        if cap.id == "forge.apply_patch":
            rollback = "git checkout -- <files> / git stash to discard the patch"
        elif "delete" in cap.id or "remove" in cap.id:
            rollback = "restore from the most recent state/ backup"
        return {
            "cap": cap.id,
            "action": cap.name,
            "summary": cap.description,
            "why": decision.get("reason", "risk level requires approval"),
            "risk": decision.get("risk_level", cap.risk_level),
            "affects": affects or cap.subsystem,
            "side_effects": list(cap.side_effects),
            "rollback": rollback,
            "needs_explicit_confirm": bool(decision.get("needs_explicit_confirm")),
            "approval": decision.get("approval"),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[ExecutionBroker] = None
_instance_lock = threading.Lock()


def get_execution_broker() -> ExecutionBroker:
    """Return the process-wide ``ExecutionBroker`` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ExecutionBroker()
    return _instance
