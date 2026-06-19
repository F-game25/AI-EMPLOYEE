"""IdeaRefiner — turn a weak idea into a buildable one.

When validation is weak, a yes-man rejects and stops. A teammate proposes concrete
pivots that fix the *specific* weaknesses. This module reads a Founder Brief + its
validation verdict and returns actionable suggestions targeting the lowest-scoring
dimensions (demand / competition_gap / monetization / feasibility), plus an
improved idea statement. LLM-backed with an honest heuristic fallback.
"""
from __future__ import annotations

import json
import re
import threading

# Heuristic playbook per weak dimension — concrete moves, not platitudes.
_PLAYBOOK = {
    "demand": [
        ("Narrow to a high-pain niche", "Pick one segment with an urgent, recurring "
         "pain and a budget — broad 'nice to have' ideas fail; a sharp 'must have' wins."),
        ("Anchor to a trigger event", "Tie the product to a moment of acute need "
         "(an audit, a launch, a deadline) where people actively look for a solution."),
    ],
    "competition_gap": [
        ("Pick an underserved wedge", "Don't fight incumbents head-on — own a sub-segment "
         "or workflow they ignore, then expand."),
        ("Differentiate on one sharp axis", "Be clearly best at ONE thing (speed, price, "
         "a deep integration, a specific compliance need) rather than broadly similar."),
    ],
    "monetization": [
        ("Sell to a higher-willingness-to-pay buyer", "Reframe for a buyer whose budget and "
         "ROI are obvious (revenue/risk owners), not a casual consumer."),
        ("Tie price to the outcome", "Charge for the result (per closed deal, per hour saved) "
         "so value is undeniable and pricing isn't a race to the bottom."),
    ],
    "feasibility": [
        ("Cut the MVP to one core workflow", "Ship the single highest-value step first; "
         "prove it works before broadening scope."),
        ("Start service-assisted", "Deliver the outcome semi-manually first to validate "
         "demand and learn, then automate what works."),
    ],
}


def _llm_json(prompt: str, system: str) -> dict | None:
    try:
        from engine.api import generate
        raw = generate(prompt=prompt, system=system, timeout=90) or ""
        m = re.search(r"\{.*\}", raw, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:  # noqa: BLE001
        return None


class IdeaRefiner:
    def refine(self, brief: dict, validation: dict | None = None) -> dict:
        """brief (+ optional validation) → {suggestions[], improved_idea, strongest_pivot}.

        suggestions = [{angle, change, why, targets: <dimension>}]. Concrete and
        tied to the weakest scored dimensions. Never fabricates demand evidence.
        """
        brief = brief or {}
        idea = str(brief.get("idea") or "").strip()
        validation = validation or {}
        scores = validation.get("scores") or {}
        objection = str(validation.get("strongest_objection") or "")

        # Which dimensions are weakest? (lowest scores, or all if no scores yet)
        if scores:
            ordered = sorted(scores.items(), key=lambda kv: kv[1])
            weak = [k for k, v in ordered if v < 6.5][:2] or [ordered[0][0]]
        else:
            weak = ["demand", "monetization"]

        # 1) LLM: idea-specific pivots that fix the named weaknesses + objection.
        parsed = _llm_json(
            "A venture scored weak on these dimensions: " + ", ".join(weak) +
            (f". Strongest objection: {objection}." if objection else "") +
            " Propose 3 concrete PIVOTS that turn it into a buildable, in-demand business. "
            "For each: a sharper target customer or angle, the specific change, and why it "
            "raises real demand/margin. Then give one improved one-sentence idea. "
            'Return JSON: {suggestions:[{angle,change,why,targets}], improved_idea:string}. '
            "Idea + brief: " + json.dumps(brief)[:1500],
            "You are a sharp founder-coach. Turn weak ideas into strong ones with concrete, "
            "specific pivots — never vague 'add AI' advice, never invent traction.")

        if parsed and isinstance(parsed.get("suggestions"), list) and parsed["suggestions"]:
            suggestions = []
            for s in parsed["suggestions"][:4]:
                if isinstance(s, dict) and (s.get("change") or s.get("angle")):
                    suggestions.append({
                        "angle": str(s.get("angle") or "").strip(),
                        "change": str(s.get("change") or "").strip(),
                        "why": str(s.get("why") or "").strip(),
                        "targets": str(s.get("targets") or (weak[0] if weak else "")).strip(),
                    })
            improved = str(parsed.get("improved_idea") or "").strip() or idea
            source = "llm"
        else:
            # Heuristic fallback — targeted templates for the weak dimensions.
            suggestions = []
            for dim in weak:
                for angle, why in _PLAYBOOK.get(dim, []):
                    suggestions.append({"angle": angle, "change": f"Apply to: {idea or 'the idea'}",
                                        "why": why, "targets": dim})
            suggestions = suggestions[:4]
            improved = (f"{idea} — refocused on a high-pain niche with outcome-based pricing"
                        if idea else "Define a sharp customer + urgent problem first.")
            source = "heuristic"

        return {
            "ok": True,
            "weak_dimensions": weak,
            "suggestions": suggestions,
            "improved_idea": improved,
            "strongest_pivot": suggestions[0] if suggestions else None,
            "source": source,
            "note": "Pivot suggestions to make the idea buildable — re-validate after applying one.",
        }


_instance: IdeaRefiner | None = None
_instance_lock = threading.Lock()


def get_idea_refiner() -> IdeaRefiner:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = IdeaRefiner()
    return _instance
