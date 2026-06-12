"""Integrity gate — pure boolean pass/block over claim audit + source check.

BLOCKS on: any fabricated reference; unsupported-claim share above the block
threshold. WARNS (does not block) on: remaining unsupported claims,
unreachable/malformed sources, and unchecked sources when live verification
is off. No LLM is consulted and nothing can override a blocker.
"""
from __future__ import annotations

from research.quality.claim_auditor import audit_claims, unsupported_block_ratio
from research.quality.source_verifier import verify_sources


def gate(report: dict) -> dict:
    """Run the integrity gate.

    Returns ``{passed: bool, blockers: [...], warnings: [...],
    audit: {claims: <audit_claims>, sources: <verify_sources>}}``.
    ``passed`` is strictly ``len(blockers) == 0``.
    """
    claims_audit = audit_claims(report)
    source_check = verify_sources(report)

    blockers: list[str] = []
    warnings: list[str] = []

    for ref in claims_audit["fabricated_refs"]:
        blockers.append(f"fabricated reference not in source list: {ref}")

    ratio = claims_audit["unsupported_ratio"]
    n_unsupported = len(claims_audit["unsupported"])
    if ratio > unsupported_block_ratio():
        blockers.append(
            f"{n_unsupported}/{claims_audit['total_claims']} claims unsupported "
            f"({ratio:.0%}) — exceeds block threshold"
        )
    elif n_unsupported:
        warnings.append(f"{n_unsupported} claim(s) lack a plausible source anchor")

    summary = source_check["summary"]
    if summary.get("malformed"):
        warnings.append(f"{summary['malformed']} source URL(s) malformed")
    if summary.get("unreachable"):
        warnings.append(f"{summary['unreachable']} source(s) unreachable on live check")
    if summary.get("unchecked"):
        warnings.append(
            f"{summary['unchecked']} source(s) unchecked (live verification off)"
        )

    return {
        "passed": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "audit": {"claims": claims_audit, "sources": source_check},
    }
