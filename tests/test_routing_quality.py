"""C3 — model-routing quality: difficulty estimation, capability guard, output
scoring, redacted ledger, and the compute_planner integration."""
from __future__ import annotations

import json
import sys
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))


# ── difficulty estimation ─────────────────────────────────────────────────────

def test_simple_task_is_low_difficulty():
    from core.routing_quality import estimate_difficulty

    d = estimate_difficulty("what is the capital of France", 0)
    assert d["level"] == "low"
    assert d["score"] < 0.25


def test_hard_multidomain_task_is_high_or_critical():
    from core.routing_quality import estimate_difficulty

    d = estimate_difficulty(
        "Redesign the distributed payment authorization architecture so tenant "
        "secrets stay isolated and analyze the security trade-offs", 0)
    assert d["level"] in ("high", "critical")
    assert {"security", "architecture", "financial"} <= set(d["signals"])


def test_large_context_raises_difficulty():
    from core.routing_quality import estimate_difficulty

    low = estimate_difficulty("summarize this", 0)["score"]
    high = estimate_difficulty("summarize this", 20000)["score"]
    assert high > low


# ── capability-vs-difficulty guard ────────────────────────────────────────────

def test_guard_escalates_weak_tier_on_hard_task():
    from core.routing_quality import guard_tier

    g = guard_tier("NORMAL",
                   "Redesign the distributed payment authorization architecture so "
                   "tenant secrets stay isolated", 0)
    assert g["escalated"] is True
    assert g["tier"] == "HEAVY"
    assert g["enabled"] is True


def test_guard_does_not_downgrade_or_touch_easy_task():
    from core.routing_quality import guard_tier

    g = guard_tier("HEAVY", "what is 2 + 2", 0)
    assert g["escalated"] is False
    assert g["tier"] == "HEAVY"


def test_guard_preserves_code_lane():
    from core.routing_quality import guard_tier

    g = guard_tier("CODE",
                   "implement a secure distributed payment service with tenant isolation", 0)
    assert g["escalated"] is False
    assert g["tier"] == "CODE"
    assert "code lane" in g["reason"]


def test_guard_can_be_disabled(monkeypatch):
    from core.routing_quality import guard_tier

    monkeypatch.setenv("ROUTING_QUALITY_GUARD", "0")
    g = guard_tier("FAST",
                   "Redesign the distributed payment authorization architecture so "
                   "tenant secrets stay isolated", 0)
    assert g["enabled"] is False
    assert g["escalated"] is False
    assert g["tier"] == "FAST"


# ── output quality scoring ────────────────────────────────────────────────────

def test_score_empty_output_fails():
    from core.routing_quality import score_output

    r = score_output("explain X", "")
    assert r["score"] == 0.0
    assert r["passed"] is False
    assert "empty_output" in r["reasons"]


def test_score_refusal_is_low():
    from core.routing_quality import score_output

    r = score_output("write a function", "I cannot help with that request as an AI.")
    assert r["passed"] is False
    assert "refusal_or_disclaimer" in r["reasons"]


def test_score_good_answer_passes():
    from core.routing_quality import score_output

    good = ("To configure tenant isolation, scope every query by tenant_id, enforce "
            "it in middleware, and add a permission check close to the database action. "
            "This keeps each tenant's data separated and auditable across requests.")
    r = score_output("how do I configure tenant isolation", good)
    assert r["passed"] is True
    assert r["score"] >= 0.8


def test_score_off_topic_penalized():
    from core.routing_quality import score_output

    r = score_output("explain quantum entanglement physics",
                     "Bananas grow on tall tropical plants in warm humid regions worldwide.")
    assert "off_topic" in r["reasons"]


# ── redacted ledger + stats ───────────────────────────────────────────────────

def test_record_and_stats_are_redacted(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ROUTING_QUALITY_LOG", "1")
    from core.routing_quality import record_quality, quality_stats, _ledger_path

    assert record_quality("qwen2.5:7b-instruct", score=0.9, passed=True,
                          task_type="NORMAL", difficulty="medium",
                          goal="how do I configure tenant isolation") is True
    assert record_quality("qwen2.5:7b-instruct", score=0.4, passed=False,
                          task_type="NORMAL", difficulty="high",
                          goal="another goal") is True

    # Ledger must NOT contain the raw goal text — only a hash.
    raw = _ledger_path().read_text(encoding="utf-8")
    assert "tenant isolation" not in raw
    assert "goal_hash" in raw

    stats = quality_stats("qwen2.5:7b-instruct")
    assert stats["samples"] == 2
    m = stats["by_model"]["qwen2.5:7b-instruct"]
    assert m["n"] == 2
    assert abs(m["avg_score"] - 0.65) < 1e-6
    assert m["pass_rate"] == 0.5


def test_logging_can_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ROUTING_QUALITY_LOG", "0")
    from core.routing_quality import record_quality

    assert record_quality("m", score=1.0, passed=True) is False


# ── compute_planner integration ───────────────────────────────────────────────

def test_planner_escalates_hard_task(monkeypatch):
    monkeypatch.setenv("ROUTING_QUALITY_GUARD", "1")
    from engine.compute.compute_planner import assess_compute_needs

    plan = assess_compute_needs(
        "Redesign the distributed payment authorization architecture so tenant "
        "secrets stay isolated", 0)
    assert plan.difficulty in ("high", "critical")
    assert plan.guard_escalated is True
    assert plan.tier == "HEAVY"
    # strategy is downstream VRAM policy (may escalate the rung to free cloud /
    # rent on a small-VRAM box) — the C3 guarantee is that it is NOT a weak rung.
    assert plan.strategy in ("local_reasoning", "openrouter_free", "rent_gpu")


def test_planner_leaves_simple_task_alone():
    from engine.compute.compute_planner import assess_compute_needs

    plan = assess_compute_needs("what is the capital of France", 0)
    assert plan.guard_escalated is False
    assert plan.difficulty == "low"


def test_config_file_is_valid_json():
    cfg = json.loads((RUNTIME / "config" / "routing_quality.json").read_text())
    assert "capability_floor" in cfg
    assert cfg["capability_floor"]["high"] == "HEAVY"
