"""Report finalizer — attach the quality block, never touch the findings.

``finalize`` runs gate → reviewer panel → passport over a persisted
DeepResearchReport dict and returns a NEW dict with a ``quality`` block
attached. The input dict and the original findings are never mutated.
If the gate blocked, ``quality.publishable`` is False with the blocker
reasons — verified-source integrity always wins over review scores.
"""
from __future__ import annotations

import copy

from research.quality.integrity_gate import gate
from research.quality.material_passport import build_passport
from research.quality.reviewer_panel import review


def finalize(report: dict, n_reviewers: int = 3) -> dict:
    """Returns ``{report: <original + quality block>, quality: {...}}``."""
    working = copy.deepcopy(report)  # analyzers never see the caller's dict

    gate_result = gate(working)
    panel = review(working, n_reviewers=n_reviewers)
    passport = build_passport(working, verification=gate_result["audit"]["sources"])

    claims = gate_result["audit"]["claims"]
    anchored_ratio = (
        round(claims["anchored"] / claims["total_claims"], 3)
        if claims["total_claims"] else 0.0
    )

    quality = {
        "gate": gate_result,
        "reviews": panel,
        "passport": passport,
        "anchored_ratio": anchored_ratio,
        "publishable": gate_result["passed"],
    }
    if not gate_result["passed"]:
        quality["reasons"] = list(gate_result["blockers"])

    out_report = copy.deepcopy(report)
    out_report["quality"] = quality
    return {"report": out_report, "quality": quality}
