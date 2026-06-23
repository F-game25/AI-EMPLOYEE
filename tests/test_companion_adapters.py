"""Tests for the Companion Gateway execution-broker capability adapters (P6).

Exercises the real read-only/low-risk executors wired in
runtime/companion/execution_broker.py. Deterministic + fast:
  - No network, no LLM required (LLM-backed adapter is tested via its
    "unavailable" degradation path, not a live call).
  - forge.run_tests is tested via the "target required" path and a tiny no-op
    target — never the full suite.
  - Every adapter is fed bad input to prove it returns a structured result and
    never raises (the broker must stay alive).
"""
import sys
from pathlib import Path
import json

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

import pytest  # noqa: E402

import companion.execution_broker as eb  # noqa: E402
import companion.teammate_state as ts  # noqa: E402
from companion.execution_broker import ExecutionBroker, get_execution_broker  # noqa: E402


# ── system.tasks.active ─────────────────────────────────────────────────────────

def test_tasks_active_returns_list_without_crashing():
    out = ExecutionBroker._exec_system_tasks_active(None, {})
    assert isinstance(out, dict)
    assert isinstance(out["tasks"], list)  # empty ok


# ── system.logs.search ──────────────────────────────────────────────────────────

def test_logs_search_structured_when_log_absent_or_present():
    out = ExecutionBroker._exec_system_logs_search(None, {"query": "zzz-no-such-token"})
    assert isinstance(out, dict)
    assert isinstance(out["lines"], list)  # structured, never raises


def test_logs_search_no_query_is_honest():
    out = ExecutionBroker._exec_system_logs_search(None, {})
    assert out["lines"] == []
    assert "note" in out


# ── briefing.morning ───────────────────────────────────────────────────────────

def test_morning_briefing_uses_real_local_state(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "_state_dir", lambda: tmp_path)
    (tmp_path / "tasks.json").write_text(json.dumps({
        "tasks": {
            "t1": {"title": "Follow up proposals", "status": "running"},
            "t2": {"title": "Done task", "status": "completed"},
        }
    }), encoding="utf-8")
    (tmp_path / "leads-crm.json").write_text(json.dumps({
        "leads": [
            {"stage": "negotiation", "value": 1200},
            {"stage": "new_lead", "value": 300},
        ]
    }), encoding="utf-8")
    (tmp_path / "invoices.json").write_text(json.dumps({
        "invoices": [
            {"status": "paid", "total": 500},
            {"status": "overdue", "total": 250},
        ]
    }), encoding="utf-8")
    (tmp_path / "guardrails.jsonl").write_text(
        json.dumps({"status": "pending"}) + "\n",
        encoding="utf-8",
    )

    out = ExecutionBroker._exec_morning_briefing(None, {})
    assert out["status"] == "ok"
    assert out["read_only"] is True
    assert out["metrics"]["active_tasks"] == 1
    assert out["metrics"]["active_pipeline_leads"] == 2
    assert out["metrics"]["pipeline_value"] == 1500
    assert out["metrics"]["revenue_paid"] == 500
    assert out["metrics"]["invoices_overdue"] == 1
    assert out["metrics"]["guardrail_flags"] == 1
    assert out["focus"]
    assert out["spoken_summary"].startswith("Morning brief:")


def test_morning_briefing_missing_state_is_honest(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "_state_dir", lambda: tmp_path)
    out = ExecutionBroker._exec_morning_briefing(None, {})
    assert out["status"] == "ok"
    assert out["metrics"]["active_tasks"] == 0
    assert out["missing_sources"]
    assert "No revenue, guardrail, or execution risks" in out["risks"][0]


# ── teammate.* ───────────────────────────────────────────────────────────────

def test_teammate_routine_configure_persists_local_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "canonical_state_dir", lambda: tmp_path)
    out = ExecutionBroker._exec_teammate_routine_configure(
        None, {"text": "brief me every morning at 8:30", "tenant_id": "default"})
    assert out["status"] == "stored"
    assert out["stored"] is True
    assert out["config"]["enabled"] is True
    assert out["config"]["time"] == "08:30"

    status = ExecutionBroker._exec_teammate_routine_status(
        None, {"tenant_id": "default"})
    assert status["routines"]["morning_brief"]["enabled"] is True


def test_teammate_briefing_create_task_writes_local_task(tmp_path, monkeypatch):
    monkeypatch.setattr(eb, "_state_dir", lambda: tmp_path)
    briefing = {
        "date": "2026-06-21",
        "focus": ["Collect overdue invoice.", "Follow up proposal."],
        "risks": ["1 overdue invoice."],
    }
    out = ExecutionBroker._exec_teammate_briefing_create_task(
        None,
        {
            "text": "turn first focus into a task",
            "recent_tool_results": [{"cap": "briefing.morning", "data": briefing}],
        },
    )
    assert out["status"] == "created"
    assert out["stored"] is True
    assert out["task"]["status"] == "pending"
    assert out["task"]["priority"] == "high"

    saved = json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))
    tasks = saved["tasks"]
    assert out["task"]["id"] in tasks
    assert tasks[out["task"]["id"]]["source"] == "voice_morning_brief"


def test_teammate_briefing_create_task_requires_recent_brief():
    out = ExecutionBroker._exec_teammate_briefing_create_task(
        None, {"text": "turn that into a task"})
    assert out["status"] == "needs_briefing"
    assert out["stored"] is False


# ── security.score_action ───────────────────────────────────────────────────────

def test_score_action_ranks_risky_above_benign():
    risky = ExecutionBroker._exec_security_score_action(
        None, {"action": "delete all production data"})
    benign = ExecutionBroker._exec_security_score_action(
        None, {"action": "summarize this page"})
    assert risky["status"] == "ok" and benign["status"] == "ok"
    assert risky["score"] > benign["score"]
    assert risky["risk_level"] in ("medium", "high")
    assert benign["risk_level"] in ("minimal", "low")
    assert isinstance(risky["reasons"], list) and risky["reasons"]


def test_score_action_empty_is_structured():
    out = ExecutionBroker._exec_security_score_action(None, {})
    assert out["status"] == "error" and "note" in out


# ── forge.search_code ───────────────────────────────────────────────────────────

def test_search_code_finds_known_symbol():
    out = ExecutionBroker._exec_forge_search_code(
        None, {"query": "ConversationRuntime", "path": "runtime/companion"})
    assert isinstance(out["matches"], list)
    assert out["count"] >= 1
    assert any("companion" in m["file"] for m in out["matches"])


def test_search_code_no_query_is_honest():
    out = ExecutionBroker._exec_forge_search_code(None, {})
    assert out["matches"] == [] and "note" in out


def test_search_code_bad_path_does_not_crash():
    out = ExecutionBroker._exec_forge_search_code(
        None, {"query": "x", "path": "../../../etc"})
    assert isinstance(out, dict)
    assert isinstance(out.get("matches", []), list)


# ── money.analyze_idea ──────────────────────────────────────────────────────────

def test_money_analyze_idea_returns_draft_no_spend():
    out = ExecutionBroker._exec_money_analyze_idea(
        None, {"idea": "B2B SaaS subscription for automated lead research"})
    assert out["status"] == "draft"
    assert out["spent"] is False
    assert isinstance(out["score"], float)
    assert isinstance(out["breakdown"], dict)


def test_money_analyze_idea_empty_is_structured():
    out = ExecutionBroker._exec_money_analyze_idea(None, {})
    assert out["status"] == "error"


# ── research.deep.start ─────────────────────────────────────────────────────────

def test_research_deep_start_does_not_block(monkeypatch):
    """Must return started/queued immediately — never run a full research pass."""
    import core.deep_research_engine as dre

    started = {"thread": False}

    class _FakeThread:
        def __init__(self, *a, **k):
            self._target = k.get("target")

        def start(self):
            started["thread"] = True  # do NOT call target — proves non-blocking

    monkeypatch.setattr("companion.execution_broker.threading.Thread", _FakeThread)
    # Keep persistence cheap/no-op.
    monkeypatch.setattr(dre, "_save_report", lambda r: None)

    out = ExecutionBroker._exec_research_deep_start(
        None, {"topic": "competitor landscape for AI ops"})
    assert out["status"] in ("started", "queued")
    if out["status"] == "started":
        assert started["thread"] is True
        assert out.get("report_id")


def test_research_deep_start_no_topic_is_structured():
    out = ExecutionBroker._exec_research_deep_start(None, {})
    assert out["status"] == "error"


# ── forge.plan_change (LLM not required — degradation path) ──────────────────────

def test_plan_change_degrades_when_llm_unavailable(monkeypatch):
    import engine.api as eapi
    monkeypatch.setattr(
        eapi, "generate",
        lambda **k: (_ for _ in ()).throw(RuntimeError("llm down")))
    out = ExecutionBroker._exec_forge_plan_change(None, {"goal": "add rate limiting"})
    assert out["status"] in ("planning_unavailable", "draft")
    assert out["writes_files"] is False


def test_plan_change_no_goal_is_structured():
    out = ExecutionBroker._exec_forge_plan_change(None, {})
    assert out["status"] == "error"


# ── forge.run_tests (never runs the full suite here) ────────────────────────────

def test_run_tests_requires_target():
    out = ExecutionBroker._exec_forge_run_tests(None, {})
    assert out["status"] == "target_required"


def test_run_tests_missing_target_is_structured():
    out = ExecutionBroker._exec_forge_run_tests(
        None, {"selector": "tests/does_not_exist_zzz.py"})
    assert out["status"] == "error"
    assert "not found" in out["note"]


def test_run_tests_target_escaping_repo_blocked():
    out = ExecutionBroker._exec_forge_run_tests(None, {"target": "../../etc/passwd"})
    assert out["status"] in ("error",)


# ── memory.write_structured ─────────────────────────────────────────────────────

def test_memory_write_structured_no_key_is_structured():
    out = ExecutionBroker._exec_memory_write_structured(None, {"value": "x"})
    assert out["stored"] is False


def test_memory_write_structured_persists(monkeypatch):
    captured = {}
    import engine.api as eapi
    monkeypatch.setattr(eapi, "memory_store",
                        lambda **k: captured.update(k))
    out = ExecutionBroker._exec_memory_write_structured(
        None, {"key": "launch_date", "value": "Friday", "tags": ["plan"]})
    assert out["stored"] is True
    assert captured.get("key") == "launch_date"


# ── No adapter ever raises on garbage input ─────────────────────────────────────

@pytest.mark.parametrize("fn_name", [
    "_exec_system_tasks_active",
    "_exec_system_logs_search",
    "_exec_morning_briefing",
    "_exec_teammate_routine_status",
    "_exec_teammate_routine_configure",
    "_exec_teammate_briefing_create_task",
    "_exec_security_score_action",
    "_exec_forge_search_code",
    "_exec_money_analyze_idea",
    "_exec_research_deep_start",
    "_exec_forge_plan_change",
    "_exec_forge_run_tests",
    "_exec_memory_write_structured",
])
@pytest.mark.parametrize("bad_ctx", [None, {}, {"text": 123}, {"query": None}])
def test_adapters_never_raise_on_bad_input(fn_name, bad_ctx, monkeypatch, tmp_path):
    # Stop research from actually launching a thread.
    monkeypatch.setattr("companion.execution_broker.threading.Thread",
                        type("_T", (), {"__init__": lambda s, *a, **k: None,
                                        "start": lambda s: None}))
    monkeypatch.setattr(ts, "canonical_state_dir", lambda: tmp_path)
    monkeypatch.setattr(eb, "_state_dir", lambda: tmp_path)
    fn = getattr(ExecutionBroker, fn_name)
    try:
        out = fn(None, dict(bad_ctx) if isinstance(bad_ctx, dict) else (bad_ctx or {}))
    except Exception as exc:  # pragma: no cover
        raise AssertionError(f"{fn_name} raised on {bad_ctx!r}: {exc}")
    assert isinstance(out, dict)


# ── Broker integration: dispatch wires the new adapters, gate respected ─────────

def test_broker_dispatch_has_all_p6_adapters():
    broker = get_execution_broker()
    for cap_id in (
        "system.tasks.active", "system.logs.search", "memory.write_structured",
        "briefing.morning", "teammate.routine.status",
        "teammate.routine.configure", "teammate.briefing.create_task",
        "research.deep.start", "money.analyze_idea", "forge.search_code",
        "forge.plan_change", "forge.run_tests", "security.score_action",
    ):
        assert cap_id in broker._dispatch, cap_id
    # apply_patch stays gated — must NOT be auto-dispatchable.
    assert "forge.apply_patch" not in broker._dispatch
