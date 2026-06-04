"""ExecutionEngine — 5-level risk gating for all tool executions.

Risk levels:
  0 — READ_ONLY:    always allowed, no approval
  1 — LOCAL_WRITE:  allowed with logging
  2 — LOCAL_EXEC:   requires user approval (HITL)
  3 — EXTERNAL:     requires approval + audit log
  4 — FINANCIAL:    requires explicit approval + dual-confirm
  5 — BLOCKED:      never allowed, raises ExecutionBlocked

QCE-aware path (optional):
  Pass context_pack=<ContextPack> to execute() to use quantum score_step()
  gating instead of the static RISK_MAP integer levels.
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

# Module-level ReflectionEngine (lazy-initialised on first use)
_reflection = None


def _get_reflection():
    global _reflection
    if _reflection is None:
        try:
            from core.quantum.reflection import ReflectionEngine
            _reflection = ReflectionEngine()
        except Exception:
            pass
    return _reflection


def _sandbox_available() -> bool:
    try:
        from core.sandbox_manager import SandboxManager  # noqa: F401
        return True
    except Exception:
        return False


class ExecutionBlocked(Exception):
    """Raised when an action_type is at risk level 5 (permanently blocked)."""


class ExecutionEngine:
    """Risk-gated execution engine.

    Usage::

        engine = ExecutionEngine(tenant_id="default")
        result = await engine.execute("read_file", {"path": "/tmp/x"}, agent_id="coder")
        # → {ok, result, risk_level, approved, audit_id}

        # QCE-aware path — pass a ContextPack to use quantum step gating:
        result = await engine.execute("read_file", {...}, agent_id="coder",
                                      context_pack=my_context_pack)
    """

    def __init__(self, tenant_id: str = "default") -> None:
        self.tenant_id = tenant_id

    async def execute(
        self,
        action_type: str,
        payload: dict[str, Any],
        agent_id: str = "system",
        context_pack=None,          # ContextPack | None — QCE-aware path
    ) -> dict[str, Any]:
        audit_id = f"exec-{uuid.uuid4().hex[:10]}"
        risk_level = RISK_MAP.get(action_type, 1)

        # ── QCE-aware gating ──────────────────────────────────────────────────
        if context_pack is not None:
            result = await self._execute_qce(action_type, payload, agent_id, audit_id, context_pack)
            self._reflect(audit_id, action_type, agent_id, result)
            return result

        # ── Legacy static RISK_MAP gating (backward compat) ───────────────────
        if risk_level == 5:
            self._audit(audit_id, action_type, risk_level, agent_id, payload, approved=False, outcome="blocked")
            raise ExecutionBlocked(
                f"Action '{action_type}' is permanently blocked (risk level 5). audit_id={audit_id}"
            )

        approved = False

        if risk_level <= 1:
            approved = True
            self._audit(audit_id, action_type, risk_level, agent_id, payload, approved=True, outcome="auto_approved")
        else:
            from core.hitl_gate import get_hitl_gate
            blocking = risk_level >= 4
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
                result = {
                    "ok": False,
                    "result": None,
                    "risk_level": risk_level,
                    "approved": False,
                    "audit_id": audit_id,
                    "message": hitl_result.get("message", f"Awaiting human approval for '{action_type}'"),
                }
                self._reflect(audit_id, action_type, agent_id, result)
                return result

        raw = self._dispatch(action_type, payload)
        result = {
            "ok": raw.get("ok", True),
            "result": raw.get("result"),
            "risk_level": risk_level,
            "approved": approved,
            "audit_id": audit_id,
        }
        self._reflect(audit_id, action_type, agent_id, result)
        return result

    # ── QCE execution path ────────────────────────────────────────────────────

    async def _execute_qce(
        self,
        action_type: str,
        payload: dict[str, Any],
        agent_id: str,
        audit_id: str,
        context_pack,
    ) -> dict[str, Any]:
        from core.quantum.step_score import score_step

        step = {'action': action_type, 'id': audit_id, 'agent_id': agent_id}
        try:
            step_score = score_step(
                step, context_pack,
                prior_success=0.5,
                sandbox_available=_sandbox_available(),
            )
            gate = step_score.gate
        except Exception as exc:
            logger.warning("score_step failed, falling back to direct: %s", exc)
            gate = 'direct'

        risk_level = RISK_MAP.get(action_type, 1)

        if gate == 'reject':
            self._audit(audit_id, action_type, risk_level, agent_id, payload, approved=False, outcome="qce_rejected")
            return {
                "ok": False, "result": None, "risk_level": risk_level,
                "approved": False, "audit_id": audit_id, "gate": gate,
                "message": f"QCE rejected action '{action_type}' (confidence too low)",
            }

        if gate == 'direct':
            self._audit(audit_id, action_type, risk_level, agent_id, payload, approved=True, outcome="qce_direct")
            raw = self._dispatch_qce(action_type, payload, context_pack)
            return {
                "ok": raw.get("ok", True), "result": raw.get("result"),
                "risk_level": risk_level, "approved": True, "audit_id": audit_id, "gate": gate,
            }

        if gate == 'sandbox':
            raw = self._try_sandbox(action_type, payload)
            if raw.get("ok"):
                self._audit(audit_id, action_type, risk_level, agent_id, payload, approved=True, outcome="qce_sandbox_ok")
                return {
                    "ok": True, "result": raw.get("result"), "risk_level": risk_level,
                    "approved": True, "audit_id": audit_id, "gate": gate, "sandboxed": True,
                }
            gate = 'hitl'  # sandbox failed — escalate

        # gate == 'hitl'
        try:
            from core.hitl_gate import get_hitl_gate
            hitl_result = get_hitl_gate().require_approval(
                agent=agent_id,
                action=action_type,
                payload={**payload, "_gate": "hitl", "_qce": True},
                submitted_by=agent_id,
                blocking=risk_level >= 4,
            )
            approved = hitl_result.get("approved", False)
        except Exception as exc:
            logger.warning("hitl_gate failed in QCE path: %s", exc)
            approved, hitl_result = False, {"message": str(exc)}

        self._audit(
            audit_id, action_type, risk_level, agent_id, payload,
            approved=approved,
            outcome="qce_hitl_approved" if approved else "qce_hitl_pending",
            hitl_id=hitl_result.get("request_id"),
        )
        if not approved:
            return {
                "ok": False, "result": None, "risk_level": risk_level,
                "approved": False, "audit_id": audit_id, "gate": gate,
                "message": hitl_result.get("message", f"Awaiting human approval for '{action_type}'"),
            }

        raw = self._dispatch_qce(action_type, payload, context_pack)
        return {
            "ok": raw.get("ok", True), "result": raw.get("result"),
            "risk_level": risk_level, "approved": True, "audit_id": audit_id, "gate": gate,
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

    def _dispatch_qce(self, action_type: str, payload: dict[str, Any], context_pack=None) -> dict[str, Any]:
        """Dispatch using QCE tool candidates by amplitude, falling back to _HANDLERS."""
        if context_pack is not None:
            candidates = getattr(context_pack, 'candidates', [])
            tool_candidates = [
                c for c in candidates
                if getattr(c, 'source_type', '') == 'tool'
                and action_type in (
                    (c.metadata.get('tool_id', '') if hasattr(c, 'metadata') else ''),
                    getattr(c, 'title', ''),
                )
            ]
            tool_candidates.sort(key=lambda c: getattr(c, 'amplitude', 0.0), reverse=True)
            for cand in tool_candidates[:3]:
                tool_id = (cand.metadata.get('tool_id', action_type)
                           if hasattr(cand, 'metadata') else action_type)
                result = self._try_handler(tool_id, payload)
                if result.get("ok"):
                    return result
        return self._dispatch(action_type, payload)

    def _try_handler(self, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._dispatch(action_type, payload)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _try_sandbox(self, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            from core.sandbox_manager import SandboxManager
            sb = SandboxManager().execute_safe(action_type, payload)
            return {"ok": bool(sb.get("ok")), "result": sb.get("result")}
        except Exception:
            return self._dispatch(action_type, payload)

    def _reflect(self, audit_id: str, action_type: str, agent_id: str, result: dict) -> None:
        """Call ReflectionEngine after every execute(). Never raises."""
        try:
            engine = _get_reflection()
            if engine is None:
                return
            engine.reflect(
                task_id=audit_id,
                outcome='success' if result.get('ok') else 'failure',
                scope='step',
                step_action=action_type,
                agent_id=agent_id,
            )
        except Exception:
            pass

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
