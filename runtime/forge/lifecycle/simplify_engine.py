"""Suggest simplifications for one or more patch plans.

Heuristics: the same file targeted by multiple slices (merge candidates) and
duplicate file entries inside a single plan. token_estimate_delta is a rough
negative token saving — explicit estimate, not fabricated measurement.
"""
from __future__ import annotations

import os

_TOKENS_PER_DUPLICATE = int(os.environ.get("FORGE_SIMPLIFY_TOKENS_PER_DUP", "80"))


def simplify_suggestions(patch_plan: dict | list) -> dict:
    """-> {suggestions: [...], token_estimate_delta: int (<=0)}"""
    plans = patch_plan if isinstance(patch_plan, list) else [patch_plan or {}]
    plans = [p if isinstance(p, dict) else {} for p in plans]
    suggestions: list[str] = []
    delta = 0

    # Cross-plan: same file owned by multiple slices.
    owners: dict[str, list[str]] = {}
    for p in plans:
        sid = str(p.get("slice_id") or "patch")
        for f in dict.fromkeys(p.get("files") or []):
            owners.setdefault(str(f), []).append(sid)
    for f, sids in sorted(owners.items()):
        if len(sids) > 1:
            suggestions.append(
                f"file '{f}' is targeted by {len(sids)} slices ({', '.join(sids)}) — "
                "merge into one slice to avoid duplicate edits")
            delta -= _TOKENS_PER_DUPLICATE * (len(sids) - 1)

    # In-plan: literal duplicate file entries.
    for p in plans:
        files = [str(f) for f in p.get("files") or []]
        for f in sorted({f for f in files if files.count(f) > 1}):
            suggestions.append(
                f"slice '{p.get('slice_id') or 'patch'}' lists '{f}' more than once — deduplicate")
            delta -= _TOKENS_PER_DUPLICATE * (files.count(f) - 1)

    return {"suggestions": suggestions, "token_estimate_delta": delta}
