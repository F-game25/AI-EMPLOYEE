"""Pricing estimator — turns a fit evaluation into a labelled price estimate.

quote(opportunity, fit) -> {
    amount_estimate: float|None,
    currency: str,
    basis: str,
    confidence: 0..1,
    is_estimate: True,        # ALWAYS — never an actual price
    breakdown: {...},
    disclaimer: str,
}

Deterministic + offline. Never raises. No external send — producing a quote
estimate is not the same as sending it (sending is HITL-gated upstream).
"""
from __future__ import annotations

from typing import Any

_DISCLAIMER = (
    "Estimate only — not a committed price. Subject to scope confirmation and "
    "human approval before being sent to any client."
)


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) else None


def quote(opportunity: dict[str, Any] | None, fit: dict[str, Any] | None) -> dict[str, Any]:
    """Produce a labelled price estimate from the fit evaluation. Never raises."""
    try:
        fit = dict(fit or {})
        value = dict(fit.get("value_estimate") or {})
        effort = dict(fit.get("effort_estimate") or {})
        fit_score = _num(fit.get("fit_score")) or 0.0
        risk = str(fit.get("risk_level") or "medium")

        base_amount = _num(value.get("amount"))
        basis = value.get("basis") or "fit_value_estimate"

        # Risk premium: higher risk → wider margin baked into the estimate.
        risk_multiplier = {"low": 1.0, "medium": 1.1, "high": 1.25}.get(risk, 1.1)
        amount = round(base_amount * risk_multiplier, 2) if base_amount is not None else None

        # Confidence: high when we have a concrete client budget + good fit,
        # low when we are extrapolating from category anchors or missing data.
        confidence = 0.35
        if basis == "client_budget_hint":
            confidence += 0.3
        confidence += 0.25 * fit_score
        if amount is None:
            confidence = 0.1
        confidence = max(0.0, min(1.0, round(confidence, 3)))

        return {
            "amount_estimate": amount,
            "currency": value.get("currency", "USD"),
            "basis": f"{basis} × risk_multiplier({risk}={risk_multiplier})",
            "confidence": confidence,
            "is_estimate": True,
            "breakdown": {
                "base_amount": base_amount,
                "risk_multiplier": risk_multiplier,
                "effort_hours": effort.get("hours"),
                "fit_score": fit_score,
            },
            "disclaimer": _DISCLAIMER,
        }
    except Exception as exc:  # pragma: no cover — defensive
        return {
            "amount_estimate": None,
            "currency": "USD",
            "basis": "error",
            "confidence": 0.0,
            "is_estimate": True,
            "breakdown": {},
            "disclaimer": _DISCLAIMER,
            "error": str(exc),
        }
