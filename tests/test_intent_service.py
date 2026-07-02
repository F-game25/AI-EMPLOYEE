"""Tests for the unified intent seam (system coherence).

Covers: registry-backed agent scoring, the composed classify() across all three
axes, graceful degradation (never raises), and the result contract.
"""
from unittest.mock import patch

from core.intent_service import (
    IntentResult,
    classify,
    get_intent_service,
    score_agents,
)


def test_intent_result_defaults():
    r = IntentResult(text="hi")
    assert r.business_intent == "ops"
    assert r.conversation_mode == "conversation"
    assert r.task_type == "general"
    assert r.entities == [] and r.candidate_agents == []
    assert r.is_command is False
    assert set(r.to_dict()) == {
        "text", "business_intent", "conversation_mode", "task_type",
        "entities", "is_command", "confidence", "reason",
        "candidate_agents", "sources",
    }


def test_business_intent_optout_skips_llm_axis():
    """Companion conversational turns pass business_intent=False — the only LLM
    axis (TaskOrchestrator.classify_intent) must not be touched (C1/R2 perf)."""
    with patch("core.orchestrator.TaskOrchestrator") as mock_to:
        res = classify("what's the system status", business_intent=False)
        mock_to.assert_not_called()
    assert res.business_intent == "ops"            # untouched default
    assert "business_intent" not in res.sources     # axis skipped
    assert res.sources.get("conversation_mode")     # heuristic axes still ran


def test_companion_intent_parity_with_classifier():
    """to_companion_intent() must preserve the companion classifier's contract:
    mode/task_type/confidence/is_command identical to calling it directly."""
    from companion.intent_classifier import get_intent_classifier
    text = "deploy the build to staging now"
    direct = get_intent_classifier().classify(text, {})
    seam = classify(text, {}, business_intent=False).to_companion_intent()
    for key in ("mode", "task_type", "is_command", "confidence", "reason"):
        assert seam[key] == direct[key], f"{key} diverged: {seam[key]} != {direct[key]}"
    # superset: seam adds these for downstream routing (inert for current consumers)
    assert "business_intent" in seam and "candidate_agents" in seam


def test_to_companion_intent_shape():
    r = IntentResult(text="hi", conversation_mode="monitoring", task_type="briefing.morning",
                     is_command=False, confidence=0.93, reason="briefing cue")
    ci = r.to_companion_intent()
    assert ci["mode"] == "monitoring"
    assert ci["task_type"] == "briefing.morning"
    assert ci["confidence"] == 0.93
    assert ci["reason"] == "briefing cue"


def test_score_agents_matches_registry():
    ranked = score_agents("orchestrate and route tasks across agents")
    assert ranked, "a domain query must match at least one registered agent"
    assert all(score > 0 for _, score in ranked)
    assert [s for _, s in ranked] == sorted((s for _, s in ranked), reverse=True)


def test_score_agents_gibberish_returns_empty():
    assert score_agents("zzqq xxyy plplpl") == []


def test_score_agents_respects_top_k():
    assert len(score_agents("automate sales leads research content email", top_k=2)) <= 2


def test_classify_empty_returns_default():
    r = classify("   ")
    assert r.text == "" and r.business_intent == "ops"


def test_classify_uses_business_intent_from_orchestrator():
    with patch("core.orchestrator.TaskOrchestrator") as mock_orch:
        mock_orch.return_value.classify_intent.return_value = "finance"
        r = classify("build me a three-year financial model")
    assert r.business_intent == "finance"
    assert r.sources.get("business_intent") is True


def test_classify_never_raises_on_orchestrator_failure():
    with patch("core.orchestrator.TaskOrchestrator", side_effect=RuntimeError("down")):
        r = classify("do something useful")
    assert isinstance(r, IntentResult)
    assert r.business_intent == "ops"


def test_classify_populates_registry_candidates():
    with patch("core.orchestrator.TaskOrchestrator") as mock_orch:
        mock_orch.return_value.classify_intent.return_value = "ops"
        r = classify("orchestrate and route tasks across agents")
    assert isinstance(r.candidate_agents, list)
    assert r.candidate_agents, "domain query should yield registry candidates"


def test_get_intent_service_singleton():
    assert get_intent_service() is get_intent_service()
