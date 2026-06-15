"""FinanceOps — advisory-only finance drafting with a mandatory human-review gate.

Reference: financial-services patterns (pitch/model/forecast/memo). Patterns only.

Hard rules (non-negotiable, enforced in every method):
  - ADVISORY ONLY. No transaction/trade/payment/wallet movement. No final
    tax/legal/accounting advice.
  - Every output carries ``advisory=True`` + ``requires_human_signoff=True`` and a
    disclaimer. All monetary figures are labelled estimates.
  - LLM-backed where useful (engine.api.generate), guarded; honest status when the
    LLM is unavailable (never fabricate financial numbers).
"""
from __future__ import annotations

import logging
import re
import threading

logger = logging.getLogger(__name__)

_DISCLAIMER = ("Advisory draft only — estimates, not committed figures. Not investment, "
               "tax, legal, or accounting advice. No transaction is or will be executed. "
               "Requires human review and sign-off before any use.")


def _llm(prompt: str, system: str) -> str | None:
    try:
        from engine.api import generate
        out = generate(prompt=prompt, system=system, timeout=60)
        return (out or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("financeops: LLM unavailable — %s", exc)
        return None


def _wrap(kind: str, body: dict) -> dict:
    """Stamp every FinanceOps output with the advisory/sign-off contract."""
    return {
        "ok": True,
        "kind": kind,
        "advisory": True,
        "requires_human_signoff": True,
        "executed": False,            # FinanceOps never executes anything
        "is_estimate": True,
        "disclaimer": _DISCLAIMER,
        **body,
    }


def _unavailable(kind: str) -> dict:
    return {"ok": False, "kind": kind, "advisory": True, "requires_human_signoff": True,
            "executed": False, "status": "unavailable",
            "note": "LLM engine unavailable — no figures produced (honest, not fabricated)",
            "disclaimer": _DISCLAIMER}


class FinanceOps:
    """Advisory finance drafts. Nothing here moves money or commits a number."""

    def business_model(self, idea: str, context: str = "") -> dict:
        idea = (idea or "").strip()
        if not idea:
            return {"ok": False, "kind": "business_model", "error": "idea required"}
        text = _llm(
            f"Draft a concise business model for: {idea}\n{('Context: '+context) if context else ''}\n"
            "Cover: value proposition, customer segments, revenue streams, cost structure, "
            "key risks. Mark all numbers as rough estimates.",
            "You are a finance analyst drafting an ADVISORY business model for human review. "
            "Be concrete but never present figures as committed. No investment advice.")
        if not text:
            return _unavailable("business_model")
        return _wrap("business_model", {"idea": idea, "draft": text})

    def pricing_analysis(self, product: str, comps: str = "") -> dict:
        product = (product or "").strip()
        if not product:
            return {"ok": False, "kind": "pricing_analysis", "error": "product required"}
        text = _llm(
            f"Draft a pricing analysis for: {product}\n{('Comparables: '+comps) if comps else ''}\n"
            "Cover: cost-plus vs value-based vs competitive framing, a recommended range "
            "(as an estimate), and the assumptions behind it.",
            "You are a pricing analyst producing an ADVISORY recommendation for human review. "
            "Label the range as an estimate. No commitments.")
        if not text:
            return _unavailable("pricing_analysis")
        return _wrap("pricing_analysis", {"product": product, "draft": text})

    def revenue_forecast(self, inputs: dict | None = None) -> dict:
        inputs = inputs or {}
        # Heuristic, transparent projection — clearly an estimate, not a measurement.
        try:
            price = float(inputs.get("price") or 0)
            customers = float(inputs.get("customers") or 0)
            growth = float(inputs.get("monthly_growth_pct") or 0) / 100.0
            months = int(inputs.get("months") or 12)
        except (TypeError, ValueError):
            return {"ok": False, "kind": "revenue_forecast", "error": "numeric inputs required"}
        projection = []
        c = customers
        for m in range(1, max(1, min(months, 60)) + 1):
            projection.append({"month": m, "customers_est": round(c, 1),
                               "revenue_est": round(c * price, 2)})
            c *= (1 + growth)
        return _wrap("revenue_forecast", {
            "inputs": {"price": price, "customers": customers,
                       "monthly_growth_pct": growth * 100, "months": months},
            "projection": projection,
            "method": "deterministic_compound_estimate",
        })

    def pitch_memo(self, company: str, context: str = "") -> dict:
        company = (company or "").strip()
        if not company:
            return {"ok": False, "kind": "pitch_memo", "error": "company required"}
        text = _llm(
            f"Draft a one-page investor pitch memo for: {company}\n{('Context: '+context) if context else ''}\n"
            "Cover: problem, solution, market, traction (label any numbers as estimates), "
            "team, the ask. Keep it tight.",
            "You are drafting an ADVISORY pitch memo for human review and editing. "
            "Never fabricate traction; mark estimates clearly. No investment advice.")
        if not text:
            return _unavailable("pitch_memo")
        return _wrap("pitch_memo", {"company": company, "draft": text})

    # ── Dispatcher for the companion capability ───────────────────────────────
    _KIND_RE = {
        "pricing": "pricing_analysis", "price": "pricing_analysis",
        "forecast": "revenue_forecast", "revenue": "revenue_forecast", "projection": "revenue_forecast",
        "pitch": "pitch_memo", "memo": "pitch_memo", "investor": "pitch_memo",
        "business model": "business_model", "model": "business_model",
    }

    def draft(self, request: str, context: str = "", inputs: dict | None = None) -> dict:
        """Pick the right advisory draft for a free-form finance request."""
        r = (request or "").lower()
        kind = next((v for k, v in self._KIND_RE.items() if k in r), "business_model")
        if kind == "revenue_forecast":
            return self.revenue_forecast(inputs or {})
        if kind == "pricing_analysis":
            return self.pricing_analysis(request, context)
        if kind == "pitch_memo":
            return self.pitch_memo(request, context)
        return self.business_model(request, context)


_instance: FinanceOps | None = None
_instance_lock = threading.Lock()


def get_financeops() -> FinanceOps:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = FinanceOps()
    return _instance
