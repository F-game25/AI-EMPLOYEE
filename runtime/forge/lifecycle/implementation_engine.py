"""Draft a patch PLAN for one slice — planning only, never writes product files.

Actual file writes belong to the Forge sandbox/apply path, which stays L3
approval-gated. This engine only describes WHAT would change and WHY.
"""
from __future__ import annotations


def implement_slice(slice_: dict, spec: dict) -> dict:
    """-> {patch_plan: {files, approach, slice_id, acceptance_ids}, status: 'drafted'}"""
    slice_ = slice_ or {}
    body = (spec or {}).get("spec", spec) or {}
    files = list(dict.fromkeys(slice_.get("files_hint") or []))
    acceptance_ids = list(slice_.get("acceptance_ids") or [])
    approach = (
        f"Implement '{slice_.get('title', '')}' as a thin vertical slice toward goal "
        f"'{body.get('goal', '')}'. Touch only: {', '.join(files) or '(no file hints)'}. "
        f"Satisfies acceptance criteria: {', '.join(acceptance_ids) or '(none mapped)'}. "
        "No product files are written by this engine — Forge sandbox/apply "
        "(approval-gated) owns all writes."
    )
    return {
        "patch_plan": {
            "files": files,
            "approach": approach,
            "slice_id": slice_.get("id"),
            "acceptance_ids": acceptance_ids,
        },
        "status": "drafted",
    }
