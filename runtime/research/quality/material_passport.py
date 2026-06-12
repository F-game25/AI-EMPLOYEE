"""Material passport — reproducibility metadata + deterministic content hash.

The passport records what the report is made of (sources, sub-questions,
budget actually used) and a sha256 over the normalized research CONTENT, so
any post-hoc edit to findings is detectable. Volatile fields (id, timestamps,
status, duration) are excluded from the hash by design.
"""
from __future__ import annotations

import hashlib
import json

from research.quality.citation_anchor import get_source_list, normalize_url
from research.quality.source_verifier import verify_sources


def content_hash(report: dict) -> str:
    """sha256 over normalized report content (order-stable, volatile-free)."""
    normalized = {
        "topic": report.get("topic", ""),
        "sub_questions": list(report.get("sub_questions") or []),
        "sections": [
            {"title": s.get("title", ""), "content": s.get("content", "")}
            for s in (report.get("sections") or [])
        ],
        "executive_summary": report.get("executive_summary", ""),
        "key_findings": list(report.get("key_findings") or []),
        "source_urls": sorted(normalize_url(s["url"]) for s in get_source_list(report)),
    }
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_passport(report: dict, verification: dict | None = None) -> dict:
    """Build the material passport for a persisted DeepResearchReport dict.

    ``verification`` may be a precomputed ``verify_sources`` result to avoid
    re-running checks; otherwise it is computed here (offline-deterministic
    unless RESEARCH_VERIFY_LIVE=1).
    """
    if verification is None:
        verification = verify_sources(report)
    summary = verification.get("summary", {})

    return {
        "topic": report.get("topic", ""),
        "created_at": report.get("created_at"),
        "source_count": len(get_source_list(report)),
        "verified_sources": summary.get("verified", 0),
        "unchecked_sources": summary.get("unchecked", 0),
        "tool_versions": {"engine": "deep_research_engine"},
        "reproducibility": {
            "sub_questions": list(report.get("sub_questions") or []),
            "depth": report.get("depth"),
            "budget_used": {
                "sources_found": report.get("sources_found", 0),
                "sources_fetched": report.get("sources_fetched", 0),
                "duration_s": report.get("duration_s", 0.0),
            },
        },
        "hash": content_hash(report),
    }
