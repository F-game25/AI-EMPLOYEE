"""Reviewer panel — multi-role report review with guarded LLM + fallback.

Roles: methodologist, domain skeptic, devil's advocate. Each review is ONE
guarded LLM call (``engine.api.generate``) with a tight JSON prompt. When the
LLM is unavailable, errors, or returns unparseable output, a deterministic
heuristic scores the report from its own stats (source count, section depth,
gaps) — clearly labeled ``method: 'heuristic'``. Reviews never invent facts;
they only score and raise concerns.

Env: ``RESEARCH_REVIEW_LLM=0`` forces heuristic mode (offline/CI);
``RESEARCH_REVIEW_TIMEOUT_S`` caps each LLM call.
"""
from __future__ import annotations

import json
import logging
import os
import re

from research.quality.citation_anchor import get_source_list

logger = logging.getLogger(__name__)

ROLES = ("methodologist", "domain_skeptic", "devils_advocate")

_ROLE_FOCUS = {
    "methodologist": "research method rigor, source diversity, and traceability",
    "domain_skeptic": "factual plausibility, missing counter-evidence, and overclaiming",
    "devils_advocate": "the strongest objection to the report's central conclusions",
}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _llm_enabled() -> bool:
    return os.getenv("RESEARCH_REVIEW_LLM", "1").strip() != "0"


def _llm_timeout_s() -> int:
    return int(os.getenv("RESEARCH_REVIEW_TIMEOUT_S", "45"))


def _llm_generate(prompt: str, timeout: int) -> str:
    """Single guarded LLM call. Lazy import so the package loads without the
    engine and so tests can monkeypatch either this or engine.api.generate."""
    from engine.api import generate
    return generate(
        prompt,
        system="You are a strict research reviewer. Reply with JSON only.",
        timeout=timeout,
    )


# ── Report stats (shared by prompt + heuristic) ──────────────────────────────

def _report_stats(report: dict) -> dict:
    sections = report.get("sections") or []
    filled = [s for s in sections if len((s.get("content") or "").strip()) >= 80]
    return {
        "source_count": len(get_source_list(report)),
        "sections_total": len(sections),
        "sections_filled": len(filled),
        "sub_questions": len(report.get("sub_questions") or []),
        "gaps": list(report.get("gaps_identified") or []),
        "key_findings": len(report.get("key_findings") or []),
        "has_exec_summary": len((report.get("executive_summary") or "").strip()) >= 100,
    }


def _clamp(v: float) -> float:
    return round(min(10.0, max(0.0, v)), 1)


def _heuristic_review(role: str, stats: dict) -> dict:
    """Deterministic scoring from report stats — no model involved."""
    coverage_ratio = stats["sections_filled"] / max(1, stats["sections_total"])
    rigor = _clamp(2.0 + stats["source_count"] * 0.8 - len(stats["gaps"]) * 0.5)
    coverage = _clamp(10.0 * coverage_ratio - len(stats["gaps"]) * 0.5)
    clarity = _clamp(
        4.0 + (3.0 if stats["has_exec_summary"] else 0.0)
        + min(3.0, stats["key_findings"] * 0.4)
    )
    if role == "domain_skeptic":  # skeptic discounts rigor further per open gap
        rigor = _clamp(rigor - len(stats["gaps"]) * 0.5)

    concerns = []
    if stats["source_count"] < 5:
        concerns.append(f"only {stats['source_count']} source(s) underpin the report")
    if stats["gaps"]:
        concerns.append(f"{len(stats['gaps'])} knowledge gap(s) remain unresolved")
    if stats["sections_filled"] < stats["sections_total"]:
        concerns.append(
            f"{stats['sections_total'] - stats['sections_filled']} section(s) are thin or empty"
        )
    if not stats["has_exec_summary"]:
        concerns.append("executive summary missing or too short")

    return {
        "role": role,
        "scores": {"rigor": rigor, "coverage": coverage, "clarity": clarity},
        "concerns": concerns,
        "method": "heuristic",
    }


# ── LLM path ─────────────────────────────────────────────────────────────────

def _build_prompt(role: str, report: dict, stats: dict) -> str:
    return (
        f"Review this research report as a {role.replace('_', ' ')} focused on "
        f"{_ROLE_FOCUS[role]}.\n"
        f"Topic: {report.get('topic', '')}\n"
        f"Stats: {stats['source_count']} sources, {stats['sections_filled']}/"
        f"{stats['sections_total']} sections substantive, "
        f"{len(stats['gaps'])} open gaps.\n"
        f"Executive summary: {(report.get('executive_summary') or '')[:1200]}\n\n"
        'Return ONLY this JSON, scores are 0-10 numbers:\n'
        '{"scores": {"rigor": 0, "coverage": 0, "clarity": 0}, '
        '"concerns": ["..."], "strongest_objection": "..."}'
    )


def _parse_review(raw: str, role: str) -> dict | None:
    m = _JSON_BLOCK_RE.search(raw or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        scores = data.get("scores") or {}
        parsed = {k: _clamp(float(scores[k])) for k in ("rigor", "coverage", "clarity")}
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
    concerns = [str(c) for c in (data.get("concerns") or []) if str(c).strip()][:5]
    review = {"role": role, "scores": parsed, "concerns": concerns, "method": "llm"}
    objection = str(data.get("strongest_objection") or "").strip()
    if objection:
        review["strongest_objection"] = objection
    return review


# ── Public API ───────────────────────────────────────────────────────────────

def review(report: dict, n_reviewers: int = 3) -> dict:
    """Run the reviewer panel.

    Returns ``{reviews: [{role, scores, concerns, method}],
    devils_advocate: {strongest_objection}, composite: float}``.
    """
    stats = _report_stats(report)
    roles = [ROLES[i % len(ROLES)] for i in range(max(1, n_reviewers))]
    use_llm, timeout = _llm_enabled(), _llm_timeout_s()

    reviews: list[dict] = []
    for role in roles:
        result = None
        if use_llm:
            try:
                result = _parse_review(_llm_generate(_build_prompt(role, report, stats), timeout), role)
            except Exception as e:
                logger.debug("reviewer LLM call failed (%s): %s — falling back", role, e)
        reviews.append(result or _heuristic_review(role, stats))

    # Devil's advocate: strongest objection from its review, else deterministic.
    da = next((r for r in reviews if r["role"] == "devils_advocate"), None)
    objection = (da or {}).get("strongest_objection") or next(
        iter((da or {}).get("concerns") or []), ""
    )
    if not objection:
        objection = (
            f"open gap remains unaddressed: {stats['gaps'][0]}" if stats["gaps"]
            else f"conclusions rest on only {stats['source_count']} source(s) "
                 "without independent corroboration"
        )

    all_scores = [v for r in reviews for v in r["scores"].values()]
    composite = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0

    return {
        "reviews": reviews,
        "devils_advocate": {"strongest_objection": objection},
        "composite": composite,
    }
