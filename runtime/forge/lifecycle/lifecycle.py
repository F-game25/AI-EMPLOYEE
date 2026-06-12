"""Lifecycle orchestrator: spec -> plan -> implement -> review -> simplify
-> test -> ship, stopping early with status='blocked' at any gate failure.

Final statuses:
    'blocked'       — a hard gate failed (vague spec, unplannable, P0, failed tests)
    'pending_gates' — pipeline ran but the ship checklist is not all green
                      (e.g. no test target named yet)
    'ship_ready'    — every gate green; apply/merge still stays L3 approval-gated
"""
from __future__ import annotations

import os

from forge.lifecycle.implementation_engine import implement_slice
from forge.lifecycle.planning_engine import build_plan
from forge.lifecycle.review_engine import review
from forge.lifecycle.ship_engine import ship_checklist
from forge.lifecycle.simplify_engine import simplify_suggestions
from forge.lifecycle.skill_selector import select_skills
from forge.lifecycle.spec_engine import build_spec
from forge.lifecycle.test_engine import run_tests

_MAX_MERGED_APPROACH_CHARS = int(os.environ.get("FORGE_LIFECYCLE_APPROACH_CAP", "1200"))


def _blocked(spec_res: dict, plan: dict | None, stages: dict, reason: str, **extra) -> dict:
    return {"spec": spec_res, "plan": plan, "stage_results": stages,
            "ship": None, "status": "blocked", "reason": reason, **extra}


def run_lifecycle(goal: str, context: dict | None = None) -> dict:
    """-> {spec, plan, stage_results, ship, status[, reason, open_questions]}"""
    context = context or {}
    stages: dict = {}

    spec_res = build_spec(goal, context)
    stages["spec"] = spec_res
    if spec_res["status"] != "ready":
        return _blocked(spec_res, None, stages, "spec_needs_clarification",
                        open_questions=spec_res["open_questions"])

    stages["skills"] = select_skills(goal, str(context.get("task_type", "general")))

    plan = build_plan(spec_res)
    stages["plan"] = plan
    if plan["status"] != "planned":
        return _blocked(spec_res, plan, stages, plan.get("reason", "plan_blocked"))

    drafts = [implement_slice(s, spec_res) for s in plan["slices"]]
    stages["implementation"] = drafts

    # Whole-plan review: merge the slice patch plans so coverage is judged globally.
    patch_plans = [d["patch_plan"] for d in drafts]
    merged = {
        "slice_id": "merged",
        "files": list(dict.fromkeys(f for p in patch_plans for f in p["files"])),
        "acceptance_ids": list(dict.fromkeys(a for p in patch_plans for a in p["acceptance_ids"])),
        "approach": " | ".join(p["approach"] for p in patch_plans)[:_MAX_MERGED_APPROACH_CHARS],
    }
    rev = review(merged, spec_res)
    stages["review"] = rev
    if any(f.get("severity") == "P0" for f in rev["findings"]):
        return _blocked(spec_res, plan, stages, "review_found_p0")

    stages["simplify"] = simplify_suggestions(patch_plans)

    tests = run_tests(context.get("test_target"))
    stages["tests"] = tests
    if tests["status"] == "failed":
        return _blocked(spec_res, plan, stages, "tests_failed")

    ship = ship_checklist(spec_res, plan, tests, rev)
    stages["ship"] = ship
    return {"spec": spec_res, "plan": plan, "stage_results": stages, "ship": ship,
            "status": "ship_ready" if ship["ship_ready"] else "pending_gates"}
