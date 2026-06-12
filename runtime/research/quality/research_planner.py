"""Research stage planner — staged-flow descriptor for UI display.

Thin and deterministic: mirrors the academic staged research flow so the
frontend can render progress lanes. Execution itself belongs to
``core.deep_research_engine`` (collect/synthesize) and this package
(verify/audit/review/passport) — wired by the orchestrator.
"""
from __future__ import annotations

STAGES = (
    "decompose", "collect", "verify", "synthesize", "audit", "review", "passport",
)

_STAGE_NOTES = {
    "decompose": "Break the topic into specific research sub-questions.",
    "collect": "Discover and fetch sources per sub-question (deep_research_engine).",
    "verify": "Validate source URLs; live reachability when RESEARCH_VERIFY_LIVE=1.",
    "synthesize": "Merge findings per sub-question into report sections.",
    "audit": "Anchor claims to sources; flag unsupported and fabricated references.",
    "review": "Reviewer panel scores rigor/coverage/clarity; devil's advocate objects.",
    "passport": "Attach reproducibility metadata and the content hash.",
}


def plan_stages(topic: str) -> dict:
    """Return the staged quality flow for a topic: ``{topic, stages, notes}``."""
    return {
        "topic": (topic or "").strip(),
        "stages": list(STAGES),
        "notes": dict(_STAGE_NOTES),
    }
