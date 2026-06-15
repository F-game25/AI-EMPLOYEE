"""ValidationEngine — the anti-Polsia differentiator: validate demand BEFORE build.

Scores demand / competition / monetization / feasibility for a Founder Brief and
returns a verdict that can REFUSE the build path. Polsia's #1 documented failure is
launching on unvalidated ideas (factory worker: months + $199/mo → 0 paying
customers). Here, a weak verdict blocks 'building' (overridable, but explicit).

Uses the LLM for analysis when available, with a transparent heuristic fallback —
and NEVER fabricates evidence (honest 'low confidence' when it can't research).
"""
from __future__ import annotations

import json
import re
import threading

# verdict thresholds on a 0-10 composite
_BUILD = 6.5
_PIVOT = 4.0   # below this → reject; between → pivot/need_evidence


def _llm_json(prompt: str, system: str) -> dict | None:
    try:
        from engine.api import generate
        raw = generate(prompt=prompt, system=system, timeout=90) or ""
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:  # noqa: BLE001
        return None


def _clamp(v, lo=0.0, hi=10.0):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.0


class ValidationEngine:
    def validate(self, brief: dict) -> dict:
        """brief → {verdict, scores, composite, confidence, reasons, recommendation}.

        verdict ∈ build | pivot | need_evidence | reject. 'build' is the ONLY
        verdict CompanyOS will let proceed to the build path without an override.
        """
        brief = brief or {}
        idea = str(brief.get("idea") or "").strip()
        if not idea:
            return {"verdict": "need_evidence", "composite": 0.0, "confidence": 0.0,
                    "scores": {}, "reasons": ["No idea provided."],
                    "recommendation": "Provide a concrete idea + target customer + problem."}

        parsed = _llm_json(
            "Assess this venture for REAL market demand. Be skeptical — most ideas are "
            "weak. Return JSON: {demand:0-10, competition_gap:0-10, monetization:0-10, "
            "feasibility:0-10, confidence:0-1, reasons:[3 strings], "
            "strongest_objection:string}.\n\nVenture: " + json.dumps(brief)[:2000],
            "You are a hard-nosed venture analyst. Validate demand BEFORE anyone builds. "
            "Reward evidence of real, urgent demand; penalize 'nice to have' and crowded "
            "markets. Never invent traction.")

        if parsed:
            scores = {k: _clamp(parsed.get(k)) for k in
                      ("demand", "competition_gap", "monetization", "feasibility")}
            confidence = max(0.0, min(1.0, float(parsed.get("confidence") or 0.5)))
            reasons = [str(r) for r in (parsed.get("reasons") or [])][:3]
            objection = str(parsed.get("strongest_objection") or "")
            source = "llm"
        else:
            # Heuristic fallback — transparent + low confidence (NOT fabricated demand).
            has = lambda k: bool(brief.get(k))  # noqa: E731
            scores = {
                "demand": 5.0 if has("problem") else 3.0,
                "competition_gap": 5.0 if has("differentiation") else 4.0,
                "monetization": 6.0 if has("monetization") else 3.0,
                "feasibility": 6.0,
            }
            confidence = 0.25
            reasons = ["Heuristic estimate only — live research unavailable.",
                       "Demand not independently verified.",
                       "Provide target customer + evidence to raise confidence."]
            objection = "No external demand evidence was gathered."
            source = "heuristic"

        # demand is weighted heaviest — it's the failure Polsia ignores.
        composite = round(
            0.4 * scores["demand"] + 0.2 * scores["competition_gap"]
            + 0.25 * scores["monetization"] + 0.15 * scores["feasibility"], 2)

        if composite >= _BUILD and confidence >= 0.4:
            verdict = "build"
            rec = "Demand looks real enough to build a small, testable MVP."
        elif composite >= _BUILD and confidence < 0.4:
            verdict = "need_evidence"
            rec = "Scores look ok but confidence is low — gather real demand evidence first."
        elif composite >= _PIVOT:
            verdict = "pivot"
            rec = "Weak as-is. Pivot the angle/customer before committing build budget."
        else:
            verdict = "reject"
            rec = "Insufficient demand signal — do not build yet. Validate with customers."

        return {
            "verdict": verdict,
            "scores": scores,
            "composite": composite,
            "confidence": round(confidence, 2),
            "reasons": reasons,
            "strongest_objection": objection,
            "recommendation": rec,
            "source": source,
            "blocks_build": verdict != "build",
        }


_instance: ValidationEngine | None = None
_instance_lock = threading.Lock()


def get_validation_engine() -> ValidationEngine:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ValidationEngine()
    return _instance
