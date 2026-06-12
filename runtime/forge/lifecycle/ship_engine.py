"""The ship gate: pure boolean checklist, no overrides, no rationalization.

ship_ready is True ONLY when: spec is ready, a non-empty plan exists, tests
passed, every review approves, and no P0/P1 finding exists anywhere. There is
deliberately no force/override parameter.
"""
from __future__ import annotations

from forge.lifecycle.review_engine import BLOCKING_SEVERITIES


def ship_checklist(spec: dict, plan: dict, test_result: dict, review: dict | list) -> dict:
    """-> {items: [{id, label, passed}], ship_ready: bool}

    ``spec`` is the build_spec envelope (or any dict with a 'status' field);
    ``review`` accepts a single review dict or a list of them.
    """
    spec = spec or {}
    plan = plan or {}
    test_result = test_result or {}
    reviews = review if isinstance(review, list) else [review or {}]
    findings = [f for r in reviews for f in (r.get("findings") or [])]

    items = [
        {"id": "spec_ready", "label": "Spec is ready (no open clarification questions)",
         "passed": spec.get("status") == "ready"},
        {"id": "plan_ready", "label": "Plan exists with at least one slice",
         "passed": plan.get("status") == "planned" and bool(plan.get("slices"))},
        {"id": "tests_passed", "label": "Named test target ran and passed",
         "passed": test_result.get("status") == "passed"},
        {"id": "reviews_approved", "label": "Every review verdict is 'approve'",
         "passed": bool(reviews) and all(r.get("verdict") == "approve" for r in reviews)},
        {"id": "no_blocking_findings", "label": "No P0/P1 findings in any review",
         "passed": not any(f.get("severity") in BLOCKING_SEVERITIES for f in findings)},
    ]
    return {"items": items, "ship_ready": all(i["passed"] for i in items)}
