"""Tests for Module 3 Skill Lifecycle OS (runtime/forge/lifecycle + ui_quality).

Deterministic — no live LLM: enrichment is opt-in via FORGE_LIFECYCLE_LLM and
force-disabled here.
"""
import json
import sys
from pathlib import Path

import pytest

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from forge.lifecycle.lifecycle import run_lifecycle  # noqa: E402
from forge.lifecycle.planning_engine import build_plan  # noqa: E402
from forge.lifecycle.review_engine import review  # noqa: E402
from forge.lifecycle.ship_engine import ship_checklist  # noqa: E402
from forge.lifecycle.skill_selector import select_skills  # noqa: E402
from forge.lifecycle.spec_engine import build_spec  # noqa: E402
from forge.lifecycle.test_engine import run_tests  # noqa: E402
from forge.ui_quality.design_language_inferer import infer  # noqa: E402
from forge.ui_quality.frontend_preflight import preflight  # noqa: E402
from forge.ui_quality.ui_auditor import audit  # noqa: E402

CLEAR_GOAL = ("Add a health check endpoint to the backend that returns JSON status "
              "and log each request to the audit trail")
VAGUE_GOAL = "fix it"
_LIBRARY = Path(__file__).resolve().parents[1] / "runtime" / "config" / "skills_library.json"


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.delenv("FORGE_LIFECYCLE_LLM", raising=False)


# ---------------------------------------------------------------- spec

def test_spec_clear_goal_is_ready_with_criteria():
    res = build_spec(CLEAR_GOAL)
    assert res["status"] == "ready"
    assert res["open_questions"] == []
    criteria = res["spec"]["acceptance_criteria"]
    assert len(criteria) >= 2
    for c in criteria:
        assert c["id"].startswith("AC-")
        assert c["checkable_via"] in ("test", "build", "manual")
        assert c["statement"].startswith("System must ")


def test_spec_vague_goal_needs_clarification():
    res = build_spec(VAGUE_GOAL)
    assert res["status"] == "needs_clarification"
    assert res["open_questions"]


# ---------------------------------------------------------------- plan

def test_plan_blocked_on_unclarified_spec():
    plan = build_plan(build_spec(VAGUE_GOAL))
    assert plan["status"] == "blocked"
    assert plan["slices"] == []
    assert plan["reason"]


def test_plan_slices_carry_acceptance_ids():
    spec = build_spec(CLEAR_GOAL)
    plan = build_plan(spec)
    assert plan["status"] == "planned"
    valid_ids = {c["id"] for c in spec["spec"]["acceptance_criteria"]}
    assert plan["slices"]
    for s in plan["slices"]:
        assert s["acceptance_ids"]
        assert set(s["acceptance_ids"]) <= valid_ids
        assert s["files_hint"]


# ---------------------------------------------------------------- ship gate

def _green_inputs():
    spec = {"status": "ready",
            "spec": {"goal": "g", "acceptance_criteria": [
                {"id": "AC-1", "checkable_via": "test"}]}}
    plan = {"status": "planned", "slices": [{"id": "S1", "acceptance_ids": ["AC-1"]}]}
    tests = {"status": "passed", "summary": "1 passed"}
    rev = {"findings": [], "verdict": "approve"}
    return spec, plan, tests, rev


def test_ship_gate_all_green():
    out = ship_checklist(*_green_inputs())
    assert out["ship_ready"] is True
    assert all(i["passed"] for i in out["items"])


def test_ship_gate_blocks_on_failed_tests():
    spec, plan, _, rev = _green_inputs()
    out = ship_checklist(spec, plan, {"status": "failed", "summary": "1 failed"}, rev)
    assert out["ship_ready"] is False
    assert not next(i for i in out["items"] if i["id"] == "tests_passed")["passed"]


def test_ship_gate_blocks_on_p0_even_if_verdict_approves():
    """Anti-rationalization: a P0 finding blocks ship regardless of prose verdict."""
    spec, plan, tests, _ = _green_inputs()
    sneaky = {"findings": [{"severity": "P0", "issue": "scope creep", "where": "x"}],
              "verdict": "approve"}
    out = ship_checklist(spec, plan, tests, sneaky)
    assert out["ship_ready"] is False
    assert not next(i for i in out["items"] if i["id"] == "no_blocking_findings")["passed"]


# ---------------------------------------------------------------- review

def test_review_flags_uncovered_criteria_as_blocking():
    spec = {"status": "ready", "spec": {"goal": "g", "acceptance_criteria": [
        {"id": "AC-1", "checkable_via": "test"}, {"id": "AC-2", "checkable_via": "test"}]}}
    plan = {"files": ["tests/test_x.py"], "acceptance_ids": ["AC-1"],
            "approach": "implements AC-1 only, with a long enough description here"}
    out = review(plan, spec)
    assert out["verdict"] == "needs_work"
    assert any("AC-2" in f["issue"] for f in out["findings"])


def test_review_flags_out_of_scope_files_as_p0():
    spec = {"status": "ready", "spec": {"goal": "g", "out_of_scope": ["billing module"],
                                        "acceptance_criteria": [{"id": "AC-1", "checkable_via": "manual"}]}}
    plan = {"files": ["backend/routes/billing.js"], "acceptance_ids": ["AC-1"],
            "approach": "long enough approach description to not be flagged thin"}
    out = review(plan, spec)
    assert any(f["severity"] == "P0" for f in out["findings"])
    assert out["verdict"] == "needs_work"


# ---------------------------------------------------------------- test engine

def test_test_engine_requires_target():
    out = run_tests()
    assert out["status"] == "target_required"
    assert "target" in out["summary"]


def test_test_engine_rejects_escaping_target():
    assert run_tests("../../etc/passwd")["status"] == "error"


# ---------------------------------------------------------------- skill selector

def test_skill_selector_uses_real_library():
    skills = select_skills("research competitor market trends", "research")
    assert len(skills) >= 1
    library_ids = {s["id"] for s in json.loads(_LIBRARY.read_text())["skills"]}
    for s in skills:
        assert s["id"] in library_ids
        assert s["match_score"] > 0


def test_skill_selector_respects_max():
    assert len(select_skills("research market analysis data", "research", max_skills=2)) <= 2


# ---------------------------------------------------------------- ui quality

_BAD_JSX = """
export default function Page({ items }) {
  // TODO placeholder
  return <ul>{items.map(i => <li key={i.id}>{i.name}</li>)}</ul>;
}
"""

_CLEAN_JSX = """
import { EmptyState } from '../nexus-ui/EmptyState';
export default function Page({ items }) {
  if (!items.length) return <EmptyState label="No items yet" />;
  return (
    <section>
      <h2>Items</h2>
      <ul>{items.map(i => <li key={i.id}>{i.name}</li>)}</ul>
    </section>
  );
}
"""


def test_preflight_catches_placeholder_and_missing_empty_state(tmp_path):
    f = tmp_path / "Bad.jsx"
    f.write_text(_BAD_JSX)
    out = preflight([str(f)])
    assert out["passed"] is False
    rules = {v["rule"] for v in out["violations"]}
    assert "placeholder_text" in rules
    assert "missing_empty_state" in rules


def test_preflight_passes_clean_component(tmp_path):
    f = tmp_path / "Clean.jsx"
    f.write_text(_CLEAN_JSX)
    out = preflight([str(f)])
    assert out["passed"] is True
    assert out["violations"] == []


def test_ui_auditor_grades_clean_above_bad(tmp_path):
    bad, clean = tmp_path / "Bad.jsx", tmp_path / "Clean.jsx"
    bad.write_text(_BAD_JSX)
    clean.write_text(_CLEAN_JSX)
    bad_audit, clean_audit = audit(str(bad)), audit(str(clean))
    assert set(bad_audit["scores"]) == {"hierarchy", "consistency", "density"}
    assert clean_audit["grade"] <= bad_audit["grade"]  # 'A' < 'F' lexically


def test_design_inferer_scans_only_what_exists(tmp_path):
    css = tmp_path / "theme.css"
    css.write_text(":root { --accent: #ff6600; } .btn { padding: 8px; font-family: Inter; }")
    out = infer([str(css), str(tmp_path / "missing.css")])
    assert out["source"] == "scanned"
    assert out["files_scanned"] == 1
    assert out["tokens"]["variables"].get("accent") == "#ff6600"
    assert any(t["value"] == "8px" for t in out["tokens"]["spacing"])


# ---------------------------------------------------------------- lifecycle

def test_lifecycle_blocks_early_on_vague_goal():
    out = run_lifecycle(VAGUE_GOAL)
    assert out["status"] == "blocked"
    assert out["reason"] == "spec_needs_clarification"
    assert out["open_questions"]
    assert out["plan"] is None and out["ship"] is None


def test_lifecycle_clear_goal_pends_without_test_target():
    out = run_lifecycle(CLEAR_GOAL)
    assert out["status"] == "pending_gates"  # no test target named -> tests gate not green
    assert out["plan"]["status"] == "planned"
    assert out["stage_results"]["tests"]["status"] == "target_required"
    assert out["stage_results"]["review"]["verdict"] == "approve"
    assert out["ship"]["ship_ready"] is False


def test_lifecycle_blocks_on_out_of_scope_p0():
    out = run_lifecycle("Add a billing endpoint to the backend that returns invoice JSON",
                        context={"out_of_scope": ["backend routes"]})
    assert out["status"] == "blocked"
    assert out["reason"] == "review_found_p0"
