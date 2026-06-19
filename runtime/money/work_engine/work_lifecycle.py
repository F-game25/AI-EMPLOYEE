"""Work lifecycle state machine + the two HARD HITL gates.

State path:
    ingest → evaluate → quote(GATE 1) → accepted → execute → deliver(GATE 2)
           → feedback → study

Two non-negotiable HITL gates:
  * GATE 1 (quote): before a quote/message could be sent to a client, a HITL
    request is opened (blocking=False) and the opportunity is parked in
    ``quote_pending``. No message is sent here — we only stage + request approval.
  * GATE 2 (deliver): before a deliverable is submitted/released, a second HITL
    request is opened and the opportunity is parked in ``delivery_pending``.

The actual approve/release transitions are driven by the HITL gate's
approve()/reject() (operator action) — this module only opens the gate and,
when told the gate cleared, advances the state. Nothing here auto-sends.

Every function is try/except wrapped → structured status; never raises.
"""
from __future__ import annotations

from typing import Any

from . import opportunity_store as store
from . import fit_evaluator, pricing_estimator, deliverable_builder, feedback_store

_AGENT = "work-engine"


def _gate():
    """Return the HITL gate, or None if unavailable (degrade honestly)."""
    try:
        from core.hitl_gate import get_hitl_gate
        return get_hitl_gate()
    except Exception:
        return None


def _gate_status(gate_id: str | None) -> str | None:
    if not gate_id:
        return None
    gate = _gate()
    if gate is None:
        return None
    try:
        req = gate.get_request(gate_id)
        return req.get("status") if req else None
    except Exception:
        return None


# ── ingest ─────────────────────────────────────────────────────────────────────

def ingest(opportunity: dict[str, Any] | None) -> dict[str, Any]:
    try:
        rec = store.create(opportunity)
        return {"ok": True, "stage": "ingested", "opportunity": rec}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc), "stage": "ingest"}


# ── evaluate ───────────────────────────────────────────────────────────────────

def evaluate(opp_id: str, *, use_llm: bool = True) -> dict[str, Any]:
    try:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found", "stage": "evaluate"}
        result = fit_evaluator.evaluate(rec, use_llm=use_llm)
        store.attach(opp_id, "evaluation", result)
        store.set_status(opp_id, "evaluated")
        return {"ok": True, "stage": "evaluated", "evaluation": result,
                "opportunity": store.get(opp_id)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc), "stage": "evaluate"}


# ── quote → HARD HITL GATE 1 ────────────────────────────────────────────────────

def quote(opp_id: str, *, submitted_by: str = "work-engine") -> dict[str, Any]:
    """Draft a price estimate and open HITL GATE 1. Never auto-sends."""
    try:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found", "stage": "quote"}
        evaluation = rec.get("evaluation")
        if not evaluation:
            evaluation = fit_evaluator.evaluate(rec)
            store.attach(opp_id, "evaluation", evaluation)
            store.set_status(opp_id, "evaluated")

        estimate = pricing_estimator.quote(rec, evaluation)

        gate = _gate()
        gate_result = None
        gate_id = None
        if gate is not None:
            gate_result = gate.require_approval(
                agent=_AGENT,
                action="send_quote",
                payload={
                    "opportunity_id": opp_id,
                    "title": rec.get("title"),
                    "amount_estimate": estimate.get("amount_estimate"),
                    "currency": estimate.get("currency"),
                    "is_estimate": True,
                    "disclaimer": estimate.get("disclaimer"),
                },
                submitted_by=submitted_by,
                blocking=False,
            )
            gate_id = gate_result.get("request_id")

        quote_doc = {
            "estimate": estimate,
            "gate_id": gate_id,
            "approval_status": "pending_approval",
        }
        store.attach(opp_id, "quote", quote_doc)
        store.record_gate(opp_id, "quote", {"gate_id": gate_id, "status": "pending_approval"})
        store.set_status(opp_id, "quote_pending")

        return {
            "ok": True,
            "stage": "quote_pending",
            "status": "pending_approval",   # explicit: NOT sent
            "gate_id": gate_id,
            "requires_human_approval": True,
            "quote": quote_doc,
            "opportunity": store.get(opp_id),
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc), "stage": "quote"}


def confirm_quote_sent(opp_id: str) -> dict[str, Any]:
    """Advance quote_pending → quoted, only if GATE 1 was approved by a human."""
    try:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found"}
        gate_id = (rec.get("quote") or {}).get("gate_id")
        status = _gate_status(gate_id)
        if status != "approved":
            return {
                "ok": False, "stage": "quote_pending",
                "status": status or "pending_approval",
                "error": "quote not approved — cannot mark as sent",
                "requires_human_approval": True,
            }
        q = dict(rec.get("quote") or {})
        q["approval_status"] = "approved"
        store.attach(opp_id, "quote", q)
        store.set_status(opp_id, "quoted")
        return {"ok": True, "stage": "quoted", "opportunity": store.get(opp_id)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


# ── accept ─────────────────────────────────────────────────────────────────────

def accept(opp_id: str) -> dict[str, Any]:
    try:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found", "stage": "accept"}
        res = store.set_status(opp_id, "accepted")
        if not res.get("ok"):
            return {"ok": False, "stage": rec.get("status"), **res}
        return {"ok": True, "stage": "accepted", "opportunity": store.get(opp_id)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc), "stage": "accept"}


# ── execute ────────────────────────────────────────────────────────────────────

def execute(opp_id: str) -> dict[str, Any]:
    """Build the deliverable artifact. Staging only — does NOT deliver."""
    try:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found", "stage": "execute"}
        trans = store.set_status(opp_id, "executing")
        if not trans.get("ok"):
            # Refuse to build out-of-order — execute only after 'accepted'.
            return {"ok": False, "stage": rec.get("status"),
                    "error": trans.get("error", "cannot execute from current state")}
        built = deliverable_builder.build(rec)
        store.attach(opp_id, "deliverable", built)
        if not built.get("ok"):
            store.set_status(opp_id, "failed", force=True)
            return {"ok": False, "stage": "failed", "deliverable": built,
                    "opportunity": store.get(opp_id)}
        return {"ok": True, "stage": "executing", "deliverable": built,
                "opportunity": store.get(opp_id)}
    except Exception as exc:  # pragma: no cover
        store.set_status(opp_id, "failed", force=True)
        return {"ok": False, "error": str(exc), "stage": "execute"}


# ── deliver → HARD HITL GATE 2 ──────────────────────────────────────────────────

def deliver(opp_id: str, *, submitted_by: str = "work-engine") -> dict[str, Any]:
    """Stage the deliverable and open HITL GATE 2. Never auto-submits."""
    try:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found", "stage": "deliver"}
        if not store.can_transition(rec.get("status", ""), "delivery_pending"):
            return {"ok": False, "stage": rec.get("status"),
                    "error": "cannot deliver from current state — accept the work first"}
        deliverable = rec.get("deliverable")
        if not deliverable or not deliverable.get("ok"):
            # Build it now if execution hasn't produced an artifact yet.
            built = deliverable_builder.build(rec)
            store.attach(opp_id, "deliverable", built)
            deliverable = built
            if not built.get("ok"):
                store.set_status(opp_id, "failed", force=True)
                return {"ok": False, "stage": "failed", "deliverable": built}

        gate = _gate()
        gate_id = None
        if gate is not None:
            gate_result = gate.require_approval(
                agent=_AGENT,
                action="submit_deliverable",
                payload={
                    "opportunity_id": opp_id,
                    "title": rec.get("title"),
                    "artifact_path": deliverable.get("artifact_path"),
                    "summary": deliverable.get("summary"),
                },
                submitted_by=submitted_by,
                blocking=False,
            )
            gate_id = gate_result.get("request_id")

        store.record_gate(opp_id, "deliver", {"gate_id": gate_id, "status": "pending_approval"})
        store.set_status(opp_id, "delivery_pending")
        return {
            "ok": True,
            "stage": "delivery_pending",
            "status": "pending_approval",   # explicit: NOT submitted
            "gate_id": gate_id,
            "requires_human_approval": True,
            "deliverable": deliverable,
            "opportunity": store.get(opp_id),
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc), "stage": "deliver"}


def confirm_delivered(opp_id: str) -> dict[str, Any]:
    """Advance delivery_pending → delivered, only if GATE 2 was human-approved."""
    try:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found"}
        gate_id = (rec.get("gates") or {}).get("deliver", {}).get("gate_id")
        status = _gate_status(gate_id)
        if status != "approved":
            return {
                "ok": False, "stage": "delivery_pending",
                "status": status or "pending_approval",
                "error": "delivery not approved — cannot mark as delivered",
                "requires_human_approval": True,
            }
        store.set_status(opp_id, "delivered")
        return {"ok": True, "stage": "delivered", "opportunity": store.get(opp_id)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}


# ── feedback + study ────────────────────────────────────────────────────────────

def record_feedback(opp_id: str, outcome: dict[str, Any] | None) -> dict[str, Any]:
    try:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found", "stage": "feedback"}
        fb = feedback_store.record(opp_id, outcome)
        if fb.get("ok"):
            store.attach(opp_id, "feedback", fb["feedback"])
            store.set_status(opp_id, "feedback_recorded", force=True)
        return {"ok": fb.get("ok", False), "stage": "feedback_recorded",
                "feedback": fb.get("feedback"), "opportunity": store.get(opp_id)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc), "stage": "feedback"}


def study(opp_id: str | None = None, *, use_llm: bool = True) -> dict[str, Any]:
    """Run the offline study session (non-blocking). Optionally tag an opp."""
    try:
        summary = feedback_store.study_session(use_llm=use_llm)
        if opp_id:
            rec = store.get(opp_id)
            if rec is not None:
                store.attach(opp_id, "study", summary)
                store.set_status(opp_id, "studied", force=True)
        return {"ok": summary.get("ok", True), "stage": "studied", "study": summary}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc), "stage": "study"}


def decline(opp_id: str, reason: str = "") -> dict[str, Any]:
    try:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found"}
        store.attach(opp_id, "decline_reason", reason)
        store.set_status(opp_id, "declined", force=True)
        return {"ok": True, "stage": "declined", "opportunity": store.get(opp_id)}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)}
