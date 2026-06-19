"""WorkEngine facade — the single public surface for Module 4.

Ties the store + evaluator + pricing + lifecycle + feedback together behind one
singleton. Every method delegates to the try/except-wrapped lifecycle, so the
facade never raises and always returns a structured status.

Governance carried through every method:
  * quote() and deliver() are HARD HITL gates → return ``pending_approval`` with
    a gate id; nothing is auto-sent / auto-submitted.
  * All monetary figures are labelled estimates (``is_estimate: True``).
"""
from __future__ import annotations

import threading
from typing import Any

from . import opportunity_store as store
from . import work_lifecycle as lifecycle


class WorkEngine:
    """Facade over the work-acquisition + delivery lifecycle."""

    # ── ingest / list / get ────────────────────────────────────────────────────

    def ingest_opportunity(self, opportunity: dict[str, Any] | None) -> dict[str, Any]:
        return lifecycle.ingest(opportunity)

    def list_opportunities(self, status: str | None = None) -> dict[str, Any]:
        try:
            return {"ok": True, "opportunities": store.list_all(status)}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": str(exc), "opportunities": []}

    def get_opportunity(self, opp_id: str) -> dict[str, Any]:
        rec = store.get(opp_id)
        if rec is None:
            return {"ok": False, "error": "opportunity not found"}
        return {"ok": True, "opportunity": rec}

    # ── lifecycle ───────────────────────────────────────────────────────────────

    def evaluate(self, opp_id: str, *, use_llm: bool = True) -> dict[str, Any]:
        return lifecycle.evaluate(opp_id, use_llm=use_llm)

    def quote(self, opp_id: str, *, submitted_by: str = "work-engine") -> dict[str, Any]:
        """HARD HITL GATE 1 — drafts an estimate + requests approval, never sends."""
        return lifecycle.quote(opp_id, submitted_by=submitted_by)

    def confirm_quote_sent(self, opp_id: str) -> dict[str, Any]:
        return lifecycle.confirm_quote_sent(opp_id)

    def accept(self, opp_id: str) -> dict[str, Any]:
        return lifecycle.accept(opp_id)

    def execute(self, opp_id: str) -> dict[str, Any]:
        return lifecycle.execute(opp_id)

    def deliver(self, opp_id: str, *, submitted_by: str = "work-engine") -> dict[str, Any]:
        """HARD HITL GATE 2 — stages the deliverable + requests approval, never submits."""
        return lifecycle.deliver(opp_id, submitted_by=submitted_by)

    def confirm_delivered(self, opp_id: str) -> dict[str, Any]:
        return lifecycle.confirm_delivered(opp_id)

    def decline(self, opp_id: str, reason: str = "") -> dict[str, Any]:
        return lifecycle.decline(opp_id, reason)

    # ── feedback + study ────────────────────────────────────────────────────────

    def record_feedback(self, opp_id: str, outcome: dict[str, Any] | None) -> dict[str, Any]:
        return lifecycle.record_feedback(opp_id, outcome)

    def run_study_session(self, opp_id: str | None = None, *, use_llm: bool = True) -> dict[str, Any]:
        """Offline, non-blocking study loop. Safe to call any time."""
        return lifecycle.study(opp_id, use_llm=use_llm)


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: WorkEngine | None = None
_lock = threading.Lock()


def get_work_engine() -> WorkEngine:
    """Return the process-wide WorkEngine singleton."""
    global _instance
    with _lock:
        if _instance is None:
            _instance = WorkEngine()
    return _instance
