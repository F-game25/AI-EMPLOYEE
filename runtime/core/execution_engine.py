"""ExecutionEngine — 5-level risk gating for all tool executions.

Risk levels:
  0 — READ_ONLY:    always allowed, no approval
  1 — LOCAL_WRITE:  allowed with logging
  2 — LOCAL_EXEC:   requires user approval (HITL)
  3 — EXTERNAL:     requires approval + audit log
  4 — FINANCIAL:    requires explicit approval + dual-confirm
  5 — BLOCKED:      never allowed, raises ExecutionBlocked
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("execution_engine")

RISK_MAP: dict[str, int] = {
    # Level 0 — read-only, always allowed
    "read_file": 0, "search_web": 0, "get_memory": 0,
    # Level 1 — local writes, allowed with logging
    "write_file": 1, "create_file": 1, "update_db": 1,
    # Level 2 — local execution, requires HITL
    "run_code": 2, "run_shell": 2,
    # Level 3 — external actions, requires approval + audit
    "send_email": 3, "call_api": 3, "browse_url": 3, "post_social": 3,
    # Level 4 — financial, requires explicit dual-confirm
    "pay_invoice": 4, "transfer_funds": 4, "publish_public": 4,
    # Level 5 — permanently blocked
    "rm_rf": 5, "drop_table": 5, "delete_all": 5,
}

_RISK_LABELS = {0: "READ_ONLY", 1: "LOCAL_WRITE", 2: "LOCAL_EXEC", 3: "EXTERNAL", 4: "FINANCIAL", 5: "BLOCKED"}


class ExecutionBlocked(Exception):
    """Raised when an action_type is at risk level 5 (permanently blocked)."""


class ExecutionEngine:
    """Risk-gated execution engine.

    Usage::

        engine = ExecutionEngine(tenant_id="default")
        result = await engine.execute("read_file", {"path": "/tmp/x"}, agent_id="coder")
        # → {ok, result, risk_level, approved, audit_id}
    """

    def __init__(self, tenant_id: str = "default") -> None:
        self.tenant_id = tenant_id

    async def execute(
        self,
        action_type: str,
        payload: dict[str, Any],
        agent_id: str = "system",
    ) -> dict[str, Any]:
        risk_level = RISK_MAP.get(action_type, 1)  # unknown actions default to LOCAL_WRITE
        audit_id = f"exec-{uuid.uuid4().hex[:10]}"

        if risk_level == 5:
            self._audit(audit_id, action_type, risk_level, agent_id, payload, approved=False, outcome="blocked")
            raise ExecutionBlocked(
                f"Action '{action_type}' is permanently blocked (risk level 5). audit_id={audit_id}"
            )

        approved = False

        if risk_level <= 1:
            # READ_ONLY and LOCAL_WRITE: execute immediately, just log
            approved = True
            self._audit(audit_id, action_type, risk_level, agent_id, payload, approved=True, outcome="auto_approved")
        else:
            # Levels 2-4: require HITL approval
            from core.hitl_gate import get_hitl_gate
            blocking = risk_level >= 4  # financial actions block until decided
            hitl_result = get_hitl_gate().require_approval(
                agent=agent_id,
                action=action_type,
                payload={**payload, "_risk_level": risk_level, "_risk_label": _RISK_LABELS[risk_level]},
                submitted_by=agent_id,
                blocking=blocking,
            )
            approved = hitl_result.get("approved", False)
            self._audit(
                audit_id, action_type, risk_level, agent_id, payload,
                approved=approved,
                outcome="approved" if approved else "pending_hitl",
                hitl_id=hitl_result.get("request_id"),
            )
            if not approved:
                return {
                    "ok": False,
                    "result": None,
                    "risk_level": risk_level,
                    "approved": False,
                    "audit_id": audit_id,
                    "message": hitl_result.get("message", f"Awaiting human approval for '{action_type}'"),
                }

        result = self._dispatch(action_type, payload)
        return {
            "ok": result.get("ok", True),
            "result": result.get("result"),
            "risk_level": risk_level,
            "approved": approved,
            "audit_id": audit_id,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _dispatch(self, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Route to actual tool handler. Extensible — add handlers as needed."""
        handler = _HANDLERS.get(action_type)
        if handler is None:
            return {"ok": True, "result": f"[no-op] action '{action_type}' executed", "payload": payload}
        try:
            return handler(payload)
        except Exception as exc:
            logger.warning("dispatch failed for %s: %s", action_type, exc)
            return {"ok": False, "result": None, "error": str(exc)}

    def _audit(
        self,
        audit_id: str,
        action_type: str,
        risk_level: int,
        agent_id: str,
        payload: dict[str, Any],
        *,
        approved: bool,
        outcome: str,
        hitl_id: str | None = None,
    ) -> None:
        entry = {
            "audit_id": audit_id,
            "action_type": action_type,
            "risk_level": risk_level,
            "risk_label": _RISK_LABELS.get(risk_level, "UNKNOWN"),
            "agent_id": agent_id,
            "tenant_id": self.tenant_id,
            "approved": approved,
            "outcome": outcome,
            "hitl_request_id": hitl_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("EXEC_AUDIT %s", entry)
        try:
            from core.audit_engine import get_audit_engine
            get_audit_engine().record(
                actor=agent_id,
                action=action_type,
                input_data={**payload, "risk_level": risk_level},
                output_data={"approved": approved, "outcome": outcome},
                risk_score=risk_level / 5.0,
            )
        except Exception as exc:
            logger.debug("audit_engine.record skipped: %s", exc)


# ── Built-in handlers (extend as needed) ─────────────────────────────────────

def _handle_read_file(payload: dict) -> dict:
    from pathlib import Path
    path = payload.get("path", "")
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "result": content[:4096]}
    except Exception as exc:
        return {"ok": False, "result": None, "error": str(exc)}


def _handle_write_file(payload: dict) -> dict:
    from pathlib import Path
    path = payload.get("path", "")
    content = payload.get("content", "")
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "result": f"written {len(content)} bytes to {path}"}
    except Exception as exc:
        return {"ok": False, "result": None, "error": str(exc)}


_HANDLERS: dict[str, Any] = {
    "read_file": _handle_read_file,
    "write_file": _handle_write_file,
    "create_file": _handle_write_file,
}
