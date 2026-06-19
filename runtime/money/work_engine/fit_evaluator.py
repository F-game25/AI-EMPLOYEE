"""Fit evaluation for a work opportunity.

Heuristic baseline (deterministic, offline) + optional LLM deepening (guarded).
All numeric outputs are clearly labelled estimates — nothing here is presented
as an actual. Never raises.

evaluate(opportunity) -> {
    fit_score: 0..1,
    value_estimate: {amount, currency, is_estimate, basis},
    effort_estimate: {hours, is_estimate, basis},
    risk_level: 'low'|'medium'|'high',
    rationale: str,
    recommendation: 'pursue'|'decline'|'needs_info',
    method: 'heuristic'|'heuristic+llm',
}
"""
from __future__ import annotations

import json
import re
from typing import Any

# Category → baseline effort (hours) and hourly value. These are conservative
# REFERENCE anchors for an estimate, never quoted as fact.
_CATEGORY_ANCHORS: dict[str, dict[str, float]] = {
    "content":   {"hours": 4.0,  "rate": 60.0},
    "writing":   {"hours": 4.0,  "rate": 60.0},
    "research":  {"hours": 6.0,  "rate": 75.0},
    "data":      {"hours": 8.0,  "rate": 80.0},
    "code":      {"hours": 12.0, "rate": 95.0},
    "design":    {"hours": 8.0,  "rate": 85.0},
    "outreach":  {"hours": 5.0,  "rate": 70.0},
    "general":   {"hours": 6.0,  "rate": 65.0},
}

_HIGH_RISK_SIGNALS = ("urgent", "asap", "legal", "medical", "guarantee", "refund",
                      "crypto", "investment", "no budget", "unpaid")
_GOOD_FIT_SIGNALS = ("blog", "article", "report", "summary", "research", "scrape",
                     "dataset", "landing page", "copy", "email", "analysis")


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _category(opp: dict[str, Any]) -> str:
    cat = str(opp.get("category") or "").lower()
    if cat in _CATEGORY_ANCHORS:
        return cat
    text = f"{opp.get('title', '')} {opp.get('description', '')}".lower()
    for key in _CATEGORY_ANCHORS:
        if key in text:
            return key
    return "general"


def _heuristic(opp: dict[str, Any]) -> dict[str, Any]:
    title = str(opp.get("title") or "")
    desc = str(opp.get("description") or "")
    text = f"{title} {desc}".lower()
    cat = _category(opp)
    anchor = _CATEGORY_ANCHORS[cat]

    # Fit signal: clear scope (length), known-good keywords, has a client/budget.
    fit = 0.4
    if len(desc) >= 40:
        fit += 0.15
    if any(s in text for s in _GOOD_FIT_SIGNALS):
        fit += 0.2
    if opp.get("budget_hint") not in (None, "", 0):
        fit += 0.15
    if opp.get("client"):
        fit += 0.05
    # Risk drag on fit.
    risk_hits = [s for s in _HIGH_RISK_SIGNALS if s in text]
    fit -= 0.12 * len(risk_hits)
    if not desc.strip():
        fit -= 0.2
    fit = _clamp01(round(fit, 3))

    risk_level = "high" if len(risk_hits) >= 2 else ("medium" if risk_hits else "low")

    # Effort estimate (hours) anchored by category, nudged by scope length.
    scope_factor = 1.0 + min(1.0, len(desc) / 400.0)
    hours = round(anchor["hours"] * scope_factor, 1)

    # Value estimate: prefer the client's budget hint when numeric, else
    # effort × reference rate. ALWAYS labelled an estimate.
    amount = None
    basis = "effort × reference_rate"
    bh = opp.get("budget_hint")
    bh_num = _coerce_amount(bh)
    if bh_num is not None:
        amount = round(bh_num, 2)
        basis = "client_budget_hint"
    else:
        amount = round(hours * anchor["rate"], 2)

    if not desc.strip():
        recommendation = "needs_info"
    elif fit < 0.45 or risk_level == "high":
        recommendation = "decline"
    else:
        recommendation = "pursue"

    rationale = (
        f"category={cat}; fit={fit}; risk={risk_level} "
        f"({', '.join(risk_hits) or 'none'}); "
        f"effort≈{hours}h; value≈{amount} (estimate, basis={basis})."
    )

    return {
        "fit_score": fit,
        "value_estimate": {
            "amount": amount, "currency": "USD",
            "is_estimate": True, "basis": basis,
        },
        "effort_estimate": {"hours": hours, "is_estimate": True, "basis": f"category_anchor:{cat}"},
        "risk_level": risk_level,
        "rationale": rationale,
        "recommendation": recommendation,
        "method": "heuristic",
    }


def _coerce_amount(val: Any) -> float | None:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        m = re.search(r"[-+]?\d[\d,]*\.?\d*", val.replace(",", ""))
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _llm_deepen(opp: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Optionally refine fit_score + rationale via LLM. Guarded; degrades to base."""
    try:
        from engine.api import generate
    except Exception:
        return base
    prompt = (
        "You assess freelance/work opportunities. Given the opportunity and a "
        "heuristic baseline, return STRICT JSON with keys: fit_score (0..1 float), "
        "risk_level ('low'|'medium'|'high'), recommendation "
        "('pursue'|'decline'|'needs_info'), rationale (short string). Do not invent "
        "monetary numbers.\n\n"
        f"Opportunity: {json.dumps({k: opp.get(k) for k in ('title', 'description', 'category', 'budget_hint')}, ensure_ascii=False)}\n"
        f"Heuristic baseline: {json.dumps({k: base[k] for k in ('fit_score', 'risk_level', 'recommendation')})}\n"
        "JSON:"
    )
    try:
        raw = generate(prompt=prompt, system="Return only valid JSON.", timeout=30)
    except Exception:
        return base
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict):
        return base
    out = dict(base)
    fs = parsed.get("fit_score")
    if isinstance(fs, (int, float)):
        out["fit_score"] = _clamp01(round(float(fs), 3))
    if parsed.get("risk_level") in ("low", "medium", "high"):
        out["risk_level"] = parsed["risk_level"]
    if parsed.get("recommendation") in ("pursue", "decline", "needs_info"):
        out["recommendation"] = parsed["recommendation"]
    if isinstance(parsed.get("rationale"), str) and parsed["rationale"].strip():
        out["rationale"] = parsed["rationale"].strip()[:600]
    out["method"] = "heuristic+llm"
    return out


def _extract_json(raw: str) -> Any:
    if not isinstance(raw, str):
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def evaluate(opportunity: dict[str, Any] | None, *, use_llm: bool = True) -> dict[str, Any]:
    """Evaluate an opportunity. Never raises; always returns a structured dict."""
    try:
        opp = dict(opportunity or {})
        base = _heuristic(opp)
        if use_llm:
            return _llm_deepen(opp, base)
        return base
    except Exception as exc:  # pragma: no cover — defensive
        return {
            "fit_score": 0.0,
            "value_estimate": {"amount": None, "currency": "USD", "is_estimate": True, "basis": "error"},
            "effort_estimate": {"hours": None, "is_estimate": True, "basis": "error"},
            "risk_level": "high",
            "rationale": f"evaluation_error: {exc}",
            "recommendation": "needs_info",
            "method": "error",
        }
