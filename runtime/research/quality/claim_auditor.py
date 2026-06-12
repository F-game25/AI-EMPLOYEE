"""Claim audit — unsupported-claim and fabricated-reference detection.

fabricated_refs: references cited inline in the report's sections that are
NOT present in the report's own source list — i.e. the model cited something
it never collected. Full URLs require an exact normalized match against the
source list (a deep link nobody fetched is treated as fabricated); the
engine's ``[domain.tld]`` notation is matched with subdomain tolerance to
avoid false positives like ``[python.org]`` vs ``docs.python.org``.

unsupported: claims from citation_anchor with ``anchored: False``.

Verdict: ``block`` on ANY fabricated reference or an unsupported share above
the block threshold; ``warn`` when unsupported claims exist; else ``pass``.
Deterministic — no LLM.
"""
from __future__ import annotations

import os

from research.quality.citation_anchor import (
    anchor_claims,
    domains_related,
    extract_bracket_domains,
    extract_inline_urls,
    get_source_list,
    normalize_url,
    url_domain,
)


def unsupported_block_ratio() -> float:
    """Share of unsupported claims above which the verdict is 'block'."""
    return float(os.getenv("RESEARCH_UNSUPPORTED_BLOCK_RATIO", "0.4"))


def find_fabricated_refs(report: dict) -> list[str]:
    """Inline-cited references absent from the report's source list."""
    sources = get_source_list(report)
    known_norms = {normalize_url(s["url"]) for s in sources}
    known_domains = {d for d in (url_domain(s["url"]) for s in sources) if d}

    fabricated: list[str] = []
    seen: set[str] = set()
    for section in report.get("sections") or []:
        content = section.get("content", "")
        for u in extract_inline_urls(content):
            norm = normalize_url(u)
            if norm not in known_norms and norm not in seen:
                seen.add(norm)
                fabricated.append(u)
        for d in extract_bracket_domains(content):
            if d not in seen and not any(domains_related(d, k) for k in known_domains):
                seen.add(d)
                fabricated.append(d)
    return fabricated


def audit_claims(report: dict) -> dict:
    """Audit a persisted DeepResearchReport dict.

    Returns ``{anchored, total_claims, unsupported: [claim...],
    unsupported_ratio, fabricated_refs: [ref...], verdict}`` where verdict is
    ``pass | warn | block``.
    """
    anchor = anchor_claims(report)
    unsupported = [c for c in anchor["claims"] if not c["anchored"]]
    ratio = len(unsupported) / anchor["total"] if anchor["total"] else 0.0
    fabricated = find_fabricated_refs(report)

    if fabricated or ratio > unsupported_block_ratio():
        verdict = "block"
    elif unsupported:
        verdict = "warn"
    else:
        verdict = "pass"

    return {
        "anchored": anchor["anchored"],
        "total_claims": anchor["total"],
        "unsupported": unsupported,
        "unsupported_ratio": round(ratio, 3),
        "fabricated_refs": fabricated,
        "verdict": verdict,
    }
