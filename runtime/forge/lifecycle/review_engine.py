"""Review a patch plan against its spec. Verdict is computed from findings,
never from prose — the anti-rationalization rule.

Heuristic checks: acceptance coverage (P1), missing tests for test-checkable
criteria (P1), scope creep vs spec.out_of_scope (P0), thin approach (P3).
Optional guarded LLM critique may only ADD P3 advisory findings, so prose can
neither block nor unblock a verdict.
"""
from __future__ import annotations

import re

from forge.lifecycle._llm import try_generate

BLOCKING_SEVERITIES = ("P0", "P1")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "no", "not", "any", "for"}
_MIN_APPROACH_CHARS = 40


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", str(text).lower()) if len(w) > 2 and w not in _STOP}


def _llm_advisory(patch_plan: dict, goal: str) -> list[dict]:
    raw = try_generate(
        f"One-line critique (or 'none') of this patch plan for goal '{goal}': "
        f"{patch_plan.get('approach', '')[:500]}")
    if raw and raw.strip().lower() not in ("none", "none."):
        return [{"severity": "P3", "issue": f"LLM advisory: {raw.strip()[:300]}",
                 "where": "patch_plan", "source": "llm"}]
    return []


def review(patch_plan: dict, spec: dict) -> dict:
    """-> {findings: [{severity, issue, where}], verdict: 'approve'|'needs_work'}"""
    plan = patch_plan or {}
    body = (spec or {}).get("spec", spec) or {}
    criteria = body.get("acceptance_criteria") or []
    files = [str(f) for f in plan.get("files") or []]
    covered = set(plan.get("acceptance_ids") or [])
    findings: list[dict] = []

    missing = sorted({c.get("id") for c in criteria if c.get("id")} - covered)
    if missing:
        findings.append({"severity": "P1",
                         "issue": f"acceptance criteria not covered: {', '.join(missing)}",
                         "where": "patch_plan.acceptance_ids"})

    needs_tests = any(c.get("checkable_via") == "test" and c.get("id") in covered for c in criteria)
    if needs_tests and not any("test" in f.lower() for f in files):
        findings.append({"severity": "P1",
                         "issue": "covers test-checkable criteria but plans no test files",
                         "where": "patch_plan.files"})

    for oos in body.get("out_of_scope") or []:
        toks = _tokens(oos)
        hit = [f for f in files if toks & _tokens(f)]
        if hit:
            findings.append({"severity": "P0",
                             "issue": f"scope creep: plan touches out-of-scope item '{oos}'",
                             "where": ", ".join(hit)})

    if len(str(plan.get("approach", ""))) < _MIN_APPROACH_CHARS:
        findings.append({"severity": "P3",
                         "issue": "approach description too thin to review meaningfully",
                         "where": "patch_plan.approach"})

    findings.extend(_llm_advisory(plan, str(body.get("goal", ""))))

    # Anti-rationalization: verdict is pure boolean logic over severities.
    verdict = "needs_work" if any(f["severity"] in BLOCKING_SEVERITIES for f in findings) else "approve"
    return {"findings": findings, "verdict": verdict}
