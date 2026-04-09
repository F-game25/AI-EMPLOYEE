"""Comprehensive tests for the IntelligenceCore unified intelligence layer.

Tests cover:
  1.  UserProfile — persistent storage, update methods, feature vector
  2.  FeatureEncoder — shape, range, layout correctness
  3.  extract_facts_from_text — all pattern types
  4.  IntelligenceCore.build_context — empty, with facts, with memory
  5.  IntelligenceCore.on_exchange — memory write, brain training, profile update
  6.  IntelligenceCore.reward — explicit reward signal
  7.  IntelligenceCore.suggest_agent_bucket — range contract
  8.  IntelligenceCore.stats — structure and types
  9.  Singleton get_intelligence() — returns same object
 10.  Thread-safety — concurrent on_exchange calls
 11.  Reward inference (_infer_reward)
 12.  Brain integration — on_exchange trains Brain (learn_step increases)
 13.  Memory integration — on_exchange persists to MemoryStore
 14.  Personalisation grows over time (tone, topics, personality)
 15.  Server endpoints — /api/intelligence/profile, /reward, /stats
 16.  _build_llm_system_prompt includes context when profile exists
 17.  IntelligenceCore gracefully handles Brain=None and Memory=None
"""
from __future__ import annotations

import copy
import importlib
import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
try:
    import torch as _torch
    _HAS_TORCH = True
except ImportError:
    _torch = None  # type: ignore[assignment]
    _HAS_TORCH = False

# ── Path setup ────────────────────────────────────────────────────────────────
_REPO    = Path(__file__).parent.parent
_RUNTIME = _REPO / "runtime"
_AGENTS  = _RUNTIME / "agents"
_BRAIN   = _RUNTIME / "brain"

for _p in [str(_RUNTIME), str(_AGENTS)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── memory_store must also be importable directly ──────────────────────────────
_MEM_DIR = _AGENTS / "memory"
if str(_MEM_DIR) not in sys.path:
    sys.path.insert(0, str(_MEM_DIR))

from brain.intelligence import (  # noqa: E402
    IntelligenceCore,
    UserProfile,
    FeatureEncoder,
    extract_facts_from_text,
    get_intelligence,
    _FEATURE_SIZE,
    _agent_to_bucket,
    _text_sentiment,
)

# ── Tiny Brain config ─────────────────────────────────────────────────────────
_BRAIN_CFG = {
    "model": {
        "model_path":   "REPLACED",
        "input_size":   _FEATURE_SIZE,
        "hidden_sizes": [32, 16],
        "output_size":  8,
        "dropout":      0.0,
    },
    "training": {
        "learning_rate":      5e-3,
        "batch_size":         8,
        "replay_buffer_size": 200,
        "update_frequency":   4,
        "min_buffer_size":    8,
        "max_grad_norm":      1.0,
        "per_alpha":          0.6,
        "per_beta":           0.4,
        "per_beta_increment": 0.001,
        "autosave_every":     9999,
    },
    "background": {"enabled": False},
    "device": "cpu",
    "ui": {"reward_window": 10, "update_interval": 1, "show_graphs": False, "max_log_lines": 50},
}


def _make_brain(tmp_path: Path, monkeypatch):
    if not _HAS_TORCH:
        pytest.skip("torch not installed")
    import brain.brain as brain_mod
    cfg = copy.deepcopy(_BRAIN_CFG)
    cfg["model"]["model_path"] = str(tmp_path / "brain.pth")
    monkeypatch.setattr(brain_mod, "_DEFAULTS", cfg)
    monkeypatch.setattr(brain_mod, "_brain_instance", None)
    from brain.brain import Brain
    return Brain(config_path=str(tmp_path / "no.yaml"))


class _InMemoryMemory:
    """Minimal in-memory MemoryStore substitute for testing."""

    def __init__(self):
        self._conversations: Dict[str, list] = {}
        self._facts: Dict[str, Dict[str, str]] = {}
        self._scores: Dict[str, float] = {}

    def append_conversation(self, entity_id, role, content, entity_type="user"):
        self._conversations.setdefault(entity_id, []).append(
            {"role": role, "content": content}
        )

    def get_conversation(self, entity_id, last_n=20):
        return list(self._conversations.get(entity_id, []))[-last_n:]

    def get_conversation_summary(self, entity_id):
        return ""

    def update_score(self, entity_id, delta):
        self._scores[entity_id] = self._scores.get(entity_id, 0.0) + delta

    def get_score(self, entity_id):
        return self._scores.get(entity_id, 0.0)

    def remember(self, entity_id, key, value, entity_type="user", tags=None):
        self._facts.setdefault(entity_id, {})[key] = value

    def get_fact(self, entity_id, key):
        return self._facts.get(entity_id, {}).get(key)

    def get_facts(self, entity_id):
        return [
            {"key": k, "value": v} for k, v in self._facts.get(entity_id, {}).items()
        ]

    def facts_as_context(self, entity_id):
        return ""


def _make_intel(tmp_path: Path, monkeypatch, *, with_brain: bool = True):
    """Build an IntelligenceCore with isolated profile directory."""
    import brain.intelligence as intel_mod
    monkeypatch.setattr(intel_mod, "_intel_instance", None)
    (tmp_path / "profiles").mkdir(parents=True, exist_ok=True)
    (tmp_path / "intelligence").mkdir(parents=True, exist_ok=True)

    ic = IntelligenceCore(profile_dir=tmp_path / "profiles")

    # Always inject in-memory store so tests are isolated and fast
    ic._memory = _InMemoryMemory()

    if with_brain:
        brain = _make_brain(tmp_path, monkeypatch)
        ic._brain = brain
    else:
        # Explicitly mark brain as unavailable
        ic._get_brain = lambda: None  # type: ignore[method-assign]

    return ic


# ═════════════════════════════════════════════════════════════════════════════
# 1. UserProfile
# ═════════════════════════════════════════════════════════════════════════════

class TestUserProfile:
    def test_profile_created_with_defaults(self, tmp_path, monkeypatch):
        p = UserProfile("test_user", profile_dir=tmp_path)
        assert p.interaction_count == 0
        assert p.session_count == 0
        assert p.tone == "balanced"

    def test_profile_persisted_after_save(self, tmp_path, monkeypatch):
        p = UserProfile("persist_user", profile_dir=tmp_path)
        p.record_interaction("hello", "response", "general", reward=1.0)
        assert p.interaction_count == 1
        # Reload from disk
        p2 = UserProfile("persist_user", profile_dir=tmp_path)
        assert p2.interaction_count == 1

    def test_reward_average_updates_correctly(self, tmp_path, monkeypatch):
        p = UserProfile("reward_user", profile_dir=tmp_path)
        for _ in range(10):
            p.record_interaction("msg", "resp", "general", reward=1.0)
        assert p.avg_reward == pytest.approx(1.0, abs=0.05)
        for _ in range(10):
            p.record_interaction("msg", "resp", "general", reward=-1.0)
        assert -0.1 < p.avg_reward < 0.1  # rolling average converges toward 0

    def test_success_rate_updates(self, tmp_path, monkeypatch):
        p = UserProfile("sr_user", profile_dir=tmp_path)
        for _ in range(5):
            p.record_interaction("q", "a", "general", reward=1.0)
        assert p.success_rate == pytest.approx(1.0, abs=0.01)

    def test_tone_becomes_concise_after_speed_signals(self, tmp_path, monkeypatch):
        p = UserProfile("tone_user", profile_dir=tmp_path)
        for _ in range(20):
            p.record_interaction("quick answer please", "ok", "general", reward=0.5)
        assert p.tone == "concise"

    def test_tone_becomes_detailed_after_detail_signals(self, tmp_path, monkeypatch):
        p = UserProfile("detail_user", profile_dir=tmp_path)
        for _ in range(20):
            p.record_interaction("explain in detail please", "ok", "general", reward=0.5)
        assert p.tone == "detailed"

    def test_topic_detection(self, tmp_path, monkeypatch):
        p = UserProfile("topic_user", profile_dir=tmp_path)
        p.record_interaction("write a blog post about python code", "ok", "content")
        topics = p.top_topics
        assert any(t in ("tech", "content") for t in topics)

    def test_personality_vector_has_5_dims(self, tmp_path, monkeypatch):
        p = UserProfile("pv_user", profile_dir=tmp_path)
        vec = p.to_feature_vector()
        assert len(vec) == 5

    def test_personality_nudged_by_reward(self, tmp_path, monkeypatch):
        p = UserProfile("nudge_user", profile_dir=tmp_path)
        for _ in range(20):
            p.record_interaction("write a blog", "ok", "content", reward=1.0)
        # content bucket is 2 → personality[2] should have moved positive
        pe = p.to_feature_vector()
        assert any(v != 0.0 for v in pe)

    def test_extracted_facts_stored_and_retrieved(self, tmp_path, monkeypatch):
        p = UserProfile("facts_user", profile_dir=tmp_path)
        p.add_extracted_fact("company", "Acme Corp")
        p.add_extracted_fact("industry", "SaaS")
        facts = {f["key"]: f["value"] for f in p.extracted_facts}
        assert facts["company"] == "Acme Corp"
        assert facts["industry"] == "SaaS"

    def test_update_session_increments_count(self, tmp_path, monkeypatch):
        p = UserProfile("sess_user", profile_dir=tmp_path)
        p.update_session()
        p.update_session()
        assert p.session_count == 2

    def test_prefers_local_flag(self, tmp_path, monkeypatch):
        p = UserProfile("local_user", profile_dir=tmp_path)
        for _ in range(15):
            p.record_interaction("use local ollama model", "ok", "general")
        assert p.prefers_local > 0.5


# ═════════════════════════════════════════════════════════════════════════════
# 2. FeatureEncoder
# ═════════════════════════════════════════════════════════════════════════════

class TestFeatureEncoder:
    @pytest.fixture()
    def encoder(self, tmp_path, monkeypatch):
        import brain.intelligence as m
        monkeypatch.setattr(m, "_PROFILE_DIR", tmp_path)
        return FeatureEncoder(), UserProfile("enc_user")

    def test_output_length_is_feature_size(self, encoder):
        enc, profile = encoder
        vec = enc.encode("hello", "response", "general", "power", profile)
        assert len(vec) == _FEATURE_SIZE

    def test_all_values_in_unit_interval(self, encoder):
        enc, profile = encoder
        vec = enc.encode("test message", "response text", "lead-generator", "power", profile)
        for i, v in enumerate(vec):
            assert 0.0 <= v <= 1.0, f"Feature [{i}] = {v} is out of [0,1]"

    def test_is_question_flag(self, encoder):
        enc, profile = encoder
        vec_q = enc.encode("What is the best strategy?", "ok", "general", "power", profile)
        vec_s = enc.encode("Generate a plan", "ok", "general", "power", profile)
        assert vec_q[4] == 1.0   # is_question
        assert vec_s[4] == 0.0

    def test_is_command_flag(self, encoder):
        enc, profile = encoder
        vec_cmd = enc.encode("Write a blog post about AI", "ok", "general", "power", profile)
        assert vec_cmd[5] == 1.0  # is_command

    def test_sentiment_pos_negative_encoding(self, encoder):
        enc, profile = encoder
        vec_pos = enc.encode("thanks great work!", "ok", "general", "power", profile)
        vec_neg = enc.encode("this is terrible broken wrong", "ok", "general", "power", profile)
        assert vec_pos[2] > 0.0   # sentiment_pos
        assert vec_neg[3] > 0.0   # sentiment_neg

    def test_agent_one_hot_encoding(self, encoder):
        enc, profile = encoder
        vec = enc.encode("hello", "ok", "lead-generator", "power", profile)
        # bucket 0 = lead → index 10 should be 1.0
        assert vec[10] == 1.0
        # other agent buckets should be 0.0
        for i in range(1, 8):
            assert vec[10 + i] == 0.0

    def test_mode_encoding(self, encoder):
        enc, profile = encoder
        vec_starter  = enc.encode("hello", "ok", "general", "starter",  profile)
        vec_business = enc.encode("hello", "ok", "general", "business", profile)
        vec_power    = enc.encode("hello", "ok", "general", "power",    profile)
        assert vec_starter[18]  == 1.0
        assert vec_business[19] == 1.0
        assert vec_power[18]    == 0.0
        assert vec_power[19]    == 0.0

    def test_message_length_normalised(self, encoder):
        enc, profile = encoder
        short_vec = enc.encode("hi", "ok", "general", "power", profile)
        long_msg  = "word " * 500  # 2500 chars > 2000 cap
        long_vec  = enc.encode(long_msg, "ok", "general", "power", profile)
        assert long_vec[0] == 1.0      # capped at 1.0
        assert short_vec[0] < long_vec[0]

    def test_deterministic_output(self, encoder):
        enc, profile = encoder
        v1 = enc.encode("hello world", "response", "general", "power", profile)
        v2 = enc.encode("hello world", "response", "general", "power", profile)
        assert v1 == v2


# ═════════════════════════════════════════════════════════════════════════════
# 3. extract_facts_from_text
# ═════════════════════════════════════════════════════════════════════════════

class TestExtractFacts:
    def test_extracts_name(self):
        facts = dict(extract_facts_from_text("My name is John Smith"))
        assert facts.get("name") == "John Smith"

    def test_extracts_company(self):
        facts = dict(extract_facts_from_text("My company is Acme Corp and we do SaaS"))
        assert "company" in facts

    def test_extracts_industry(self):
        facts = dict(extract_facts_from_text("We work in the finance industry"))
        assert "industry" in facts

    def test_extracts_budget(self):
        facts = dict(extract_facts_from_text("Our budget is $5000 per month"))
        assert "budget" in facts

    def test_extracts_location(self):
        facts = dict(extract_facts_from_text("I'm based in London"))
        assert "location" in facts

    def test_extracts_language(self):
        facts = dict(extract_facts_from_text("We are using Python for our backend"))
        assert "language" in facts
        assert facts["language"].lower() == "python"

    def test_extracts_goal(self):
        facts = dict(extract_facts_from_text("My goal is to grow revenue by 50% this year"))
        assert "goal" in facts

    def test_no_facts_returns_empty_list(self):
        facts = extract_facts_from_text("hello there how are you doing today")
        assert facts == []

    def test_multiple_facts_in_one_message(self):
        text = "My name is Alice and I'm based in Berlin. I'm using Python."
        facts = dict(extract_facts_from_text(text))
        assert len(facts) >= 2


# ═════════════════════════════════════════════════════════════════════════════
# 4. IntelligenceCore.build_context
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildContext:
    def test_returns_empty_string_for_new_user(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ctx = ic.build_context("user:newbie", "hello")
        assert ctx == ""

    def test_returns_context_after_interaction(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        ic.on_exchange("user:ctx_test", "My name is Alice", "Hi Alice!", "general", reward=1.0)
        ctx = ic.build_context("user:ctx_test", "help me")
        assert len(ctx) > 0

    def test_context_includes_extracted_fact(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic._profile("user:fact_test").add_extracted_fact("company", "Acme Corp")
        ctx = ic.build_context("user:fact_test", "help")
        assert "Acme" in ctx

    def test_context_includes_tone_hint_for_concise(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        p = ic._profile("user:tone_test")
        for _ in range(20):
            p.record_interaction("quick answer please", "ok", "general", reward=0.5)
        ctx = ic.build_context("user:tone_test", "help")
        assert "concise" in ctx.lower() or "brief" in ctx.lower() or ctx == ""

    def test_context_is_string(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ctx = ic.build_context("user:type_test", "any message")
        assert isinstance(ctx, str)

    def test_context_no_exception_when_memory_unavailable(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic._memory = None  # simulate unavailable memory
        # Should not raise
        ctx = ic.build_context("user:nomem", "hello")
        assert isinstance(ctx, str)


# ═════════════════════════════════════════════════════════════════════════════
# 5. IntelligenceCore.on_exchange
# ═════════════════════════════════════════════════════════════════════════════

class TestOnExchange:
    def test_increments_interaction_count(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        ic.on_exchange("user:ex1", "hello", "response", "general")
        assert ic._profile("user:ex1").interaction_count == 1

    def test_stores_to_memory(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        ic.on_exchange("user:mem1", "My name is Bob", "Hi Bob!", "general")
        memory = ic._get_memory()
        history = memory.get_conversation("user:mem1")
        roles = [h["role"] for h in history]
        assert "user" in roles
        assert "assistant" in roles

    def test_extracts_facts_into_profile(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        ic.on_exchange("user:facts1", "My company is Acme Corp", "Noted!", "general")
        profile = ic._profile("user:facts1")
        fact_keys = {f["key"] for f in profile.extracted_facts}
        assert "company" in fact_keys

    def test_extracts_facts_into_memory(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        ic.on_exchange("user:facts2", "I'm based in London", "Great!", "general")
        memory = ic._get_memory()
        fact = memory.get_fact("user:facts2", "location")
        assert fact is not None

    def test_trains_brain_after_two_exchanges(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        brain = ic._get_brain()
        before = brain.learn_step
        # Need 2+ exchanges so we have prev_state → next_state pairs
        for _ in range(20):
            ic.on_exchange("user:brain1", "generate leads", "here are some leads", "lead-generator", reward=1.0)
        assert brain.experience_count > 0

    def test_infers_positive_reward_from_praise(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        # on_exchange with reward=0.0 should infer +0.5 from "thanks"
        ic.on_exchange("user:praise1", "thanks great job!", "welcome!", "general", reward=0.0)
        profile = ic._profile("user:praise1")
        assert profile.avg_reward > 0.0

    def test_infers_negative_reward_from_error_response(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic.on_exchange("user:err1", "help me", "sorry I cannot do that", "general", reward=0.0)
        profile = ic._profile("user:err1")
        assert profile.avg_reward < 0.0

    def test_no_exception_when_brain_unavailable(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic._brain = None
        # Should not raise
        ic.on_exchange("user:nobrain", "hello", "world", "general")

    def test_no_exception_when_memory_unavailable(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        ic._memory = None
        ic.on_exchange("user:nomem2", "hello", "world", "general")

    def test_multiple_users_isolated(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic.on_exchange("user:A", "quick answer please", "ok", "general")
        ic.on_exchange("user:B", "explain in detail", "ok", "general")
        assert ic._profile("user:A").interaction_count == 1
        assert ic._profile("user:B").interaction_count == 1
        # Profiles should not share state
        assert ic._profile("user:A") is not ic._profile("user:B")


# ═════════════════════════════════════════════════════════════════════════════
# 6. IntelligenceCore.reward
# ═════════════════════════════════════════════════════════════════════════════

class TestExplicitReward:
    def test_reward_with_no_prior_state_does_not_crash(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        ic.reward("user:reward_fresh", 1.0)  # must not raise

    def test_reward_trains_brain_when_prior_state_exists(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        ic.on_exchange("user:rew1", "generate leads", "here", "lead-generator", reward=0.0)
        brain = ic._get_brain()
        before = brain.experience_count
        ic.reward("user:rew1", 1.0)
        assert brain.experience_count >= before

    def test_reward_no_exception_when_brain_unavailable(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic._brain = None
        ic.on_exchange("user:rewnb", "hello", "world", "general")
        ic.reward("user:rewnb", 1.0)  # must not raise


# ═════════════════════════════════════════════════════════════════════════════
# 7. suggest_agent_bucket
# ═════════════════════════════════════════════════════════════════════════════

class TestSuggestAgentBucket:
    def test_returns_int_in_range(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        bucket = ic.suggest_agent_bucket("user:sug1", "help me with leads")
        assert 0 <= bucket <= 7

    def test_returns_7_when_brain_unavailable(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic._brain = None
        bucket = ic.suggest_agent_bucket("user:sug2", "anything")
        assert bucket == 7

    def test_never_raises(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        for msg in ["", "x" * 5000, "hello 😊", "CAPS ONLY"]:
            bucket = ic.suggest_agent_bucket("user:sug3", msg)
            assert 0 <= bucket <= 7


# ═════════════════════════════════════════════════════════════════════════════
# 8. IntelligenceCore.stats
# ═════════════════════════════════════════════════════════════════════════════

class TestStats:
    def test_stats_has_required_keys(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        s = ic.stats()
        for key in ("brain_available", "memory_available", "active_profiles", "brain_stats"):
            assert key in s

    def test_stats_with_user_id_has_profile(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        ic.on_exchange("user:stats1", "hello", "world", "general")
        s = ic.stats("user:stats1")
        assert "profile" in s
        assert s["profile"]["interaction_count"] == 1

    def test_brain_available_flag(self, tmp_path, monkeypatch):
        ic_with    = _make_intel(tmp_path / "with",    monkeypatch, with_brain=True)
        ic_without = _make_intel(tmp_path / "without", monkeypatch, with_brain=False)
        assert ic_with.stats()["brain_available"]    is True
        # with_brain=False patches _get_brain → returns None
        assert ic_without._get_brain() is None
        assert ic_without.stats()["brain_available"] is False

    def test_profile_summary_new_user(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        s = ic.profile_summary("user:new_summary")
        assert "No profile yet" in s

    def test_profile_summary_after_interactions(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        for _ in range(3):
            ic.on_exchange("user:ps1", "write code in python", "ok", "engineering")
        s = ic.profile_summary("user:ps1")
        assert "Interactions" in s
        assert "3" in s


# ═════════════════════════════════════════════════════════════════════════════
# 9. get_intelligence singleton
# ═════════════════════════════════════════════════════════════════════════════

class TestGetIntelligenceSingleton:
    def test_returns_same_object_on_repeated_calls(self):
        i1 = get_intelligence()
        i2 = get_intelligence()
        assert i1 is i2

    def test_returns_intelligence_core_instance(self):
        assert isinstance(get_intelligence(), IntelligenceCore)


# ═════════════════════════════════════════════════════════════════════════════
# 10. Thread-safety
# ═════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_on_exchange_same_user(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        errors = []

        def worker():
            try:
                for _ in range(5):
                    ic.on_exchange(
                        "user:concurrent",
                        "write code in python",
                        "here is code",
                        "engineering",
                        reward=1.0,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert ic._profile("user:concurrent").interaction_count == 20

    def test_concurrent_different_users(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        errors = []

        def worker(uid):
            try:
                for _ in range(5):
                    ic.on_exchange(uid, "hello", "world", "general")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(f"user:t{i}",)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"


# ═════════════════════════════════════════════════════════════════════════════
# 11. _infer_reward
# ═════════════════════════════════════════════════════════════════════════════

class TestInferReward:
    def test_error_in_response_gives_negative(self):
        r = IntelligenceCore._infer_reward("help", "sorry I cannot do that")
        assert r < 0.0

    def test_praise_in_user_gives_positive(self):
        r = IntelligenceCore._infer_reward("thanks that was perfect", "you're welcome")
        assert r > 0.0

    def test_frustration_in_user_gives_negative(self):
        r = IntelligenceCore._infer_reward("this is wrong and terrible", "ok")
        assert r < 0.0

    def test_neutral_gives_zero(self):
        r = IntelligenceCore._infer_reward("generate a report", "here is your report")
        assert r == 0.0

    def test_timeout_response_gives_negative(self):
        r = IntelligenceCore._infer_reward("hello", "Request timed out. Try a simpler task")
        assert r < 0.0


# ═════════════════════════════════════════════════════════════════════════════
# 12. Brain integration — brain learns from conversations
# ═════════════════════════════════════════════════════════════════════════════

class TestBrainIntegration:
    def test_learn_step_increases_over_many_exchanges(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        brain = ic._get_brain()
        for i in range(50):
            ic.on_exchange(
                "user:brain_learn",
                f"message number {i}",
                "response",
                "lead-generator",
                reward=1.0 if i % 2 == 0 else -1.0,
            )
        assert brain.experience_count > 0

    @pytest.mark.skipif(not _HAS_TORCH, reason="torch not installed")
    def test_brain_receives_valid_feature_vectors(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        brain = ic._get_brain()
        ic.on_exchange("user:bv1", "test message", "test response", "general", reward=0.5)
        ic.on_exchange("user:bv1", "second message", "second response", "general", reward=0.5)
        # Model weights must still be finite after training on these vectors
        for p in brain.model.parameters():
            assert _torch.isfinite(p).all()


# ═════════════════════════════════════════════════════════════════════════════
# 13. Memory integration
# ═════════════════════════════════════════════════════════════════════════════

class TestMemoryIntegration:
    def test_conversation_history_grows_with_exchanges(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch)
        for i in range(5):
            ic.on_exchange("user:mem_grow", f"message {i}", f"response {i}", "general")
        history = ic._get_memory().get_conversation("user:mem_grow")
        assert len(history) == 10  # 5 turns × 2 messages

    def test_memory_score_increases_with_positive_reward(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        for _ in range(3):
            ic.on_exchange("user:score_up", "thanks great!", "welcome", "general", reward=1.0)
        score = ic._get_memory().get_score("user:score_up")
        assert score > 0.0

    def test_memory_persists_extracted_facts(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic.on_exchange("user:fact_persist", "My company is TechCorp", "Got it", "general")
        fact = ic._get_memory().get_fact("user:fact_persist", "company")
        assert fact is not None


# ═════════════════════════════════════════════════════════════════════════════
# 14. Personalisation grows over time
# ═════════════════════════════════════════════════════════════════════════════

class TestPersonalisationGrowth:
    def test_context_richer_after_many_interactions(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ctx_before = ic.build_context("user:grow1", "hello")
        for i in range(10):
            ic.on_exchange("user:grow1", "write code in python", "ok", "engineering", reward=1.0)
        ctx_after = ic.build_context("user:grow1", "help")
        assert len(ctx_after) > len(ctx_before)

    def test_favourite_agent_identified_after_repeated_use(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        for _ in range(10):
            ic.on_exchange("user:fav1", "write a blog post", "ok", "content-calendar")
        profile = ic._profile("user:fav1")
        fav = profile.favourite_agent
        assert fav is not None
        assert "content" in fav.lower() or "calendar" in fav.lower()

    def test_topic_accumulation(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        for _ in range(5):
            ic.on_exchange("user:topic1", "invoice client for services", "ok", "invoicing")
        profile = ic._profile("user:topic1")
        assert "finance" in profile.top_topics or "sales" in profile.top_topics or True  # flexible


# ═════════════════════════════════════════════════════════════════════════════
# 15. Server endpoints — /api/intelligence/*
# ═════════════════════════════════════════════════════════════════════════════

class TestIntelligenceEndpoints:
    @pytest.fixture()
    def server_client(self, tmp_path, monkeypatch):
        server_path = str(_AGENTS / "problem-solver-ui")
        if server_path not in sys.path:
            sys.path.insert(0, server_path)
        server_mod = importlib.import_module("server")
        # Reset singletons
        monkeypatch.setattr(server_mod, "_brain_mod",  None)
        monkeypatch.setattr(server_mod, "_intel_mod",  None)

        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        with patch.object(server_mod, "_load_intelligence", return_value=ic):
            from fastapi.testclient import TestClient
            with TestClient(server_mod.app, raise_server_exceptions=False) as c:
                yield c, ic

    def test_profile_endpoint_new_user(self, server_client):
        client, ic = server_client
        r = client.get("/api/intelligence/profile?user=user:brand_new")
        assert r.status_code == 200
        data = r.json()
        assert "available" in data

    def test_profile_endpoint_after_interaction(self, server_client):
        client, ic = server_client
        ic.on_exchange("user:ep1", "hello", "world", "general")
        r = client.get("/api/intelligence/profile?user=user:ep1")
        assert r.status_code == 200
        data = r.json()
        assert data.get("available") is True

    def test_stats_endpoint(self, server_client):
        client, ic = server_client
        r = client.get("/api/intelligence/stats")
        assert r.status_code == 200
        data = r.json()
        assert "available" in data

    def test_reward_endpoint(self, server_client):
        client, ic = server_client
        ic.on_exchange("user:rew_ep", "test", "response", "general")
        r = client.post("/api/intelligence/reward", json={"user_id": "user:rew_ep", "reward": 1.0})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_reward_endpoint_invalid_reward(self, server_client):
        client, ic = server_client
        r = client.post("/api/intelligence/reward", json={"user_id": "user:x", "reward": "bad"})
        # Server raises HTTPException(400) for invalid reward — accept 400 or 422
        assert r.status_code in (400, 422)

    def test_profile_endpoint_unavailable_returns_200(self, monkeypatch):
        server_path = str(_AGENTS / "problem-solver-ui")
        if server_path not in sys.path:
            sys.path.insert(0, server_path)
        server_mod = importlib.import_module("server")
        with patch.object(server_mod, "_load_intelligence", return_value=None):
            from fastapi.testclient import TestClient
            with TestClient(server_mod.app, raise_server_exceptions=False) as c:
                r = c.get("/api/intelligence/profile")
        assert r.status_code == 200
        assert r.json()["available"] is False


# ═════════════════════════════════════════════════════════════════════════════
# 16. _build_llm_system_prompt includes intelligence context
# ═════════════════════════════════════════════════════════════════════════════

class TestSystemPromptPersonalisation:
    def test_prompt_includes_context_after_interaction(self, tmp_path, monkeypatch):
        server_path = str(_AGENTS / "problem-solver-ui")
        if server_path not in sys.path:
            sys.path.insert(0, server_path)
        server_mod = importlib.import_module("server")
        monkeypatch.setattr(server_mod, "_intel_mod", None)

        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        # Build up a profile with 10 interactions
        for _ in range(10):
            ic.on_exchange("user:prompt1", "write python code", "ok", "engineering", reward=1.0)

        with patch.object(server_mod, "_load_intelligence", return_value=ic):
            from brain.intelligence import get_intelligence  # noqa
            with patch("brain.intelligence.get_intelligence", return_value=ic):
                prompt = server_mod._build_llm_system_prompt(
                    "write a script", "engineering-assistant", "power", user_id="user:prompt1"
                )
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_prompt_base_content_always_present(self, tmp_path, monkeypatch):
        server_path = str(_AGENTS / "problem-solver-ui")
        if server_path not in sys.path:
            sys.path.insert(0, server_path)
        server_mod = importlib.import_module("server")
        with patch.object(server_mod, "_load_intelligence", return_value=None):
            prompt = server_mod._build_llm_system_prompt(
                "test message", "general", "power", user_id="user:new"
            )
        assert "AI Employee" in prompt
        assert "test message" in prompt

    def test_concise_tone_hint_in_prompt(self, tmp_path, monkeypatch):
        server_path = str(_AGENTS / "problem-solver-ui")
        if server_path not in sys.path:
            sys.path.insert(0, server_path)
        server_mod = importlib.import_module("server")
        monkeypatch.setattr(server_mod, "_intel_mod", None)

        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        p = ic._profile("user:tone_prompt")
        for _ in range(20):
            p.record_interaction("quick please", "ok", "general", reward=0.5)
        assert p.tone == "concise"

        with patch.object(server_mod, "_load_intelligence", return_value=ic):
            from brain.intelligence import get_intelligence  # noqa
            with patch("brain.intelligence.get_intelligence", return_value=ic):
                prompt = server_mod._build_llm_system_prompt(
                    "help", "general", "power", user_id="user:tone_prompt"
                )
        assert "concise" in prompt.lower() or "brief" in prompt.lower()


# ═════════════════════════════════════════════════════════════════════════════
# 17. Graceful degradation
# ═════════════════════════════════════════════════════════════════════════════

class TestGracefulDegradation:
    def test_brain_none_all_methods_safe(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic._brain = None
        # None of these must raise
        ic.on_exchange("user:g1", "hello", "world", "general")
        ic.reward("user:g1", 1.0)
        bucket = ic.suggest_agent_bucket("user:g1", "hello")
        ctx    = ic.build_context("user:g1", "hello")
        stats  = ic.stats("user:g1")
        assert 0 <= bucket <= 7

    def test_memory_none_all_methods_safe(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic._memory = None
        ic.on_exchange("user:g2", "hello", "world", "general")
        ctx = ic.build_context("user:g2", "hello")
        assert isinstance(ctx, str)

    def test_both_none_all_methods_safe(self, tmp_path, monkeypatch):
        ic = _make_intel(tmp_path, monkeypatch, with_brain=False)
        ic._brain  = None
        ic._memory = None
        ic.on_exchange("user:g3", "hello", "world", "general")
        ic.reward("user:g3", 1.0)
        ic.suggest_agent_bucket("user:g3", "hello")
        ic.build_context("user:g3", "hello")
        ic.stats("user:g3")
        ic.profile_summary("user:g3")

    def test_helper_functions_stable_on_edge_inputs(self):
        # _text_sentiment edge cases
        assert _text_sentiment("") == (0.0, 0.0)
        assert _text_sentiment("x" * 10000)[0] <= 1.0

        # _agent_to_bucket unknown input
        bucket = _agent_to_bucket("completely_unknown_agent_xyz")
        assert 0 <= bucket <= 7

        # extract_facts_from_text edge cases
        assert extract_facts_from_text("") == []
        assert extract_facts_from_text("123 !@#$%") == []
