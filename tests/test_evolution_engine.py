"""Tests for the Evolution Engine (runtime/evolution/). sys.path pattern from
tests/test_model_lanes.py."""
import importlib
import os
import sys
import time
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


def _sample_trace(success=True, errors=None, **extra):
    return {
        "trace_id": "tr-test-1",
        "tenant_id": "t1",
        "task_id": "task-1",
        "user_goal": "summarize the quarterly report",
        "task_type": "research",
        "started_at": "2026-06-10T00:00:00Z",
        "ended_at": "2026-06-10T00:00:05Z",
        "total_latency_ms": 5000.0,
        "models_used": ["llama"],
        "tools_used": ["search_web"],
        "errors": errors or [],
        "outputs": ["A concise summary."],
        "success": success,
        "events": [{"phase": "call_llm", "t_ms": 10, "payload": {}}],
        **extra,
    }


# ── trace collector: non-blocking + EVOLUTION_ENABLED=false no-op ─────────────
def test_trace_event_is_non_blocking_and_fast():
    from evolution.trace_collector import TraceCollector
    tc = TraceCollector(flush_interval_s=100)  # don't auto-flush during timing
    tid = tc.start_trace("task-x", "do a thing", "chat")
    t0 = time.perf_counter()
    for i in range(1000):
        tc.event(tid, "phase", {"i": i})
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    # Intent: prove event() does no inline disk I/O. 1000 real disk writes would take
    # seconds; in-memory appends are sub-millisecond. The bound is generous (500ms) only
    # to absorb scheduling/GC jitter on heavily contended shared CI runners — it still
    # catches an inline-I/O regression (which would be >1000ms) without flaking.
    assert elapsed_ms < 500, f"event path too slow ({elapsed_ms:.2f}ms) — likely doing I/O"
    rec = tc.finalize(tid, outputs=["done"], success=True)
    assert rec and rec["success"] is True
    tc.stop()


def test_collectors_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("EVOLUTION_ENABLED", "false")
    import evolution
    importlib.reload(evolution)
    from evolution import trace_collector as tcmod
    importlib.reload(tcmod)
    tc = tcmod.TraceCollector()
    assert tc.start_trace("a", "b", "c") == ""        # no trace id when disabled
    tc.event("", "p", {})                              # no-op, no raise
    assert tc.finalize("") is None
    monkeypatch.setenv("EVOLUTION_ENABLED", "true")
    importlib.reload(evolution)
    importlib.reload(tcmod)


# ── secret redaction before persist ──────────────────────────────────────────
def test_secret_redaction_scrubs_keys_and_passwords():
    from evolution.scrub import scrub
    dirty = {
        "user_goal": "use key sk-ant-abcdefghijklmnopqrstuvwxyz123456 now",
        "note": "password: hunter2longvalue",
        "password": "topsecretvalue",
        "email": "alice@example.com",
        "env": "API_TOKEN=supersecretvalue123456",
        "nested": ["bearer abcdefghijklmnop1234567890"],
    }
    out = scrub(dirty)
    blob = str(out)
    assert "sk-ant-abcdefghijklmnopqrstuvwxyz123456" not in blob
    assert "hunter2longvalue" not in blob
    assert "topsecretvalue" not in blob
    assert "alice@example.com" not in blob
    assert "supersecretvalue123456" not in blob
    assert out["password"] == "[REDACTED]"
    assert "[REDACTED]" in blob


def test_trace_persist_is_scrubbed(tmp_path, monkeypatch):
    import evolution
    monkeypatch.setattr(evolution, "TRACES_DIR", tmp_path)
    from evolution import trace_collector as tcmod
    monkeypatch.setattr(tcmod, "TRACES_DIR", tmp_path)
    tc = tcmod.TraceCollector(flush_interval_s=100)
    tid = tc.start_trace("t", "leak sk-ant-aaaaaaaaaaaaaaaaaaaaaaaaaaaa", "chat")
    tc.event(tid, "p", {"note": "password: hunter2longsecret"})
    tc.finalize(tid, outputs=["password: hunter2longsecret"], success=True)
    n = tc.flush_now()
    tc.stop()
    assert n >= 1
    written = "".join(p.read_text() for p in tmp_path.glob("traces-*.jsonl"))
    assert "sk-ant-aaaaaaaaaaaaaaaaaaaaaaaaaaaa" not in written
    assert "hunter2longsecret" not in written
    assert "[REDACTED]" in written


# ── outcome scorer ───────────────────────────────────────────────────────────
def test_outcome_scorer_returns_seven_scores_in_range():
    from evolution.outcome_scorer import OutcomeScorer, _AXES
    scores = OutcomeScorer().score(_sample_trace())
    assert set(scores.keys()) == set(_AXES)
    for k, v in scores.items():
        assert 0.0 <= v <= 1.0, f"{k}={v} out of range"


# ── failure classifier ───────────────────────────────────────────────────────
def test_failure_classifier_returns_valid_taxonomy_type():
    from evolution.failure_classifier import FailureClassifier, TAXONOMY
    trace = _sample_trace(success=False,
                          errors=[{"phase": "execute_tasks", "error": "AssertionError: test failed"}])
    res = FailureClassifier().classify(trace)
    assert res["failure_type"] in TAXONOMY
    assert res["recommended_fix_type"]
    assert 0.0 <= res["learning_value_score"] <= 1.0


# ── reflection only fires on triggers ────────────────────────────────────────
def test_reflection_skips_clean_high_score_trace(tmp_path, monkeypatch):
    import evolution
    monkeypatch.setattr(evolution, "LESSONS_DIR", tmp_path)
    from evolution import reflection_engine as rmod
    monkeypatch.setattr(rmod, "LESSONS_DIR", tmp_path)
    eng = rmod.ReflectionEngine()
    eng._store = tmp_path / "lessons.jsonl"
    # A clean, routine success: high quality but LOW learning value (nothing new
    # to learn). This is the genuine "no lesson" case — not a contrived all-0.95.
    clean = {k: 0.95 for k in (
        "quality_score", "speed_score", "safety_score", "cost_score",
        "completion_score", "reusability_score")}
    clean["learning_value_score"] = 0.2
    assert eng.reflect(_sample_trace(success=True), clean, None) is None


def test_reflection_fires_on_failure(tmp_path, monkeypatch):
    import evolution
    monkeypatch.setattr(evolution, "LESSONS_DIR", tmp_path)
    from evolution import reflection_engine as rmod
    monkeypatch.setattr(rmod, "LESSONS_DIR", tmp_path)
    eng = rmod.ReflectionEngine()
    eng._store = tmp_path / "lessons.jsonl"
    failure = {"failure_type": "test_failure", "root_cause": "tests failed"}
    lesson = eng.reflect(_sample_trace(success=False), {"learning_value_score": 0.9}, failure)
    assert lesson and lesson["promotion_state"] == "candidate"
    assert lesson["lesson_type"] == "failure_avoidance"


# ── promotion gate ───────────────────────────────────────────────────────────
def test_promotion_gate_rejects_below_quality_delta():
    from evolution.promotion_gate import PromotionGate
    gate = PromotionGate(autonomy_mode="AUTO")
    cand = {"type": "prompt_patch", "risk_level": "low", "rollback_artifact": True}
    evals = {"before": 0.80, "after": 0.81, "safety_after": 0.99,
             "pass_rate": 0.95, "speed_regression": 0.0}
    decision = gate.evaluate(cand, evals)
    assert decision["promote"] is False
    assert "quality delta" in decision["reason"]


def test_promotion_gate_high_impact_requires_human_approval(monkeypatch):
    from evolution import promotion_gate as pg

    class _OKGate:
        def require_approval(self, **kw):
            return {"approved": True, "status": "approved", "request_id": "r1"}

    monkeypatch.setattr("core.hitl_gate.get_hitl_gate", lambda: _OKGate(), raising=False)
    gate = pg.PromotionGate(autonomy_mode="AUTO")
    cand = {"type": "code_patch", "risk_level": "low", "rollback_artifact": True,
            "candidate_id": "c1", "target": "x"}
    evals = {"before": 0.70, "after": 0.80, "safety_after": 0.99,
             "pass_rate": 0.95, "speed_regression": 0.0}
    decision = gate.evaluate(cand, evals)
    assert decision["promote"] is True  # approved → passes


def test_promotion_gate_fails_closed_when_hitl_raises(monkeypatch):
    from evolution import promotion_gate as pg

    def _boom():
        raise RuntimeError("hitl down")

    monkeypatch.setattr("core.hitl_gate.get_hitl_gate", _boom, raising=False)
    gate = pg.PromotionGate(autonomy_mode="AUTO")
    cand = {"type": "security_tool_change", "risk_level": "low", "rollback_artifact": True,
            "candidate_id": "c2", "target": "y"}
    evals = {"before": 0.70, "after": 0.85, "safety_after": 0.99,
             "pass_rate": 0.95, "speed_regression": 0.0}
    decision = gate.evaluate(cand, evals)
    assert decision["promote"] is False  # fail closed


# ── distillation adapter: handoff, not re-implementation ─────────────────────
def test_distillation_adapter_feed_carries_handoff_and_scores():
    from evolution.distillation_adapter import DistillationAdapter, _HANDOFF
    trace = _sample_trace()
    scores = {"quality_score": 0.8, "learning_value_score": 0.6}
    feed = DistillationAdapter().build_feed([trace], [scores])
    rows = feed["reasoning_examples"]
    assert rows, "expected reasoning rows"
    row = rows[0]
    # Each row carries source_trace_id + scores and the handoff marker — proving
    # this feeds forge_learning.js rather than reimplementing scoreTrajectory.
    assert row["source_trace_id"] == "tr-test-1"
    assert row["scores"] == scores
    assert row["handoff"] == _HANDOFF == "forge_learning.js"
    assert row["approved_for_training"] is False


def test_distillation_adapter_does_not_compute_trajectory_score():
    # The adapter must NOT expose/compute a composite trajectory score (that is
    # forge_learning.js::scoreTrajectory). It only passes scores through as labels.
    from evolution import distillation_adapter as da
    src = (Path(da.__file__)).read_text()
    assert "scoreTrajectory" not in src or "owned by" in src.lower()
    assert not hasattr(da.DistillationAdapter, "scoreTrajectory")
    assert not hasattr(da.DistillationAdapter, "score_trajectory")


# ── controller end-to-end ────────────────────────────────────────────────────
def test_controller_on_task_finalized_runs_without_throwing(tmp_path, monkeypatch):
    import evolution
    for attr in ("TRACES_DIR", "LESSONS_DIR", "CANDIDATES_DIR",
                 "BENCHMARKS_DIR", "METRICS_DIR", "DISTILL_FEED_DIR"):
        monkeypatch.setattr(evolution, attr, tmp_path)
    from evolution.controller import EvolutionController
    ctrl = EvolutionController()
    out = ctrl.on_task_finalized(_sample_trace(success=False,
                                 errors=[{"phase": "exec", "error": "timeout"}]))
    assert "error" not in out, out.get("error")
    assert out["trace_id"] == "tr-test-1"
    assert "scores" in out
    status = ctrl.handle_evolution_op("status")
    assert status["ok"] is True
