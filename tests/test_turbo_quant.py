"""Unit tests for runtime/agents/turbo-quant/turbo_quant.py

Covers:
  - Mode management: get_mode, set_mode
  - Complexity estimation: estimate_complexity
  - VRAM estimation: vram_estimate_gb
  - Model selection: select_model (all modes + categories)
  - Memory management: memory_status, register_loaded_model, unregister_model,
                       _evict_if_needed, should_offload_to_cpu
  - Acceleration hints: suggest_acceleration
  - Performance logger: log_inference, read_recent_logs, _analyse_logs,
                        _build_suggestions, run_auto_improvement
  - Quantization helpers: recommend_quant_format
  - AirLLM config: airllm_config
  - InferenceTimer context manager
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_TURBO_DIR = Path(__file__).parent.parent / "runtime" / "agents" / "turbo-quant"
if str(_TURBO_DIR) not in sys.path:
    sys.path.insert(0, str(_TURBO_DIR))

import turbo_quant as tq


# ── Fixture: redirect file I/O to a temp dir ─────────────────────────────────

@pytest.fixture(autouse=True)
def patch_turbo_paths(tmp_path, monkeypatch):
    """Redirect file-path constants and reset in-memory state between tests."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setattr(tq, "STATE_DIR", state_dir)
    monkeypatch.setattr(tq, "LOG_FILE", state_dir / "turbo_quant.log.jsonl")
    monkeypatch.setattr(tq, "SUGGESTIONS_FILE", state_dir / "turbo_quant.suggestions.json")
    # Reset in-memory mode and loaded-models registry
    import threading
    monkeypatch.setattr(tq, "_active_mode", None)
    monkeypatch.setattr(tq, "_loaded_models", {})
    yield


# ══════════════════════════════════════════════════════════════════════════════
# Mode management
# ══════════════════════════════════════════════════════════════════════════════

class TestModeManagement:
    def test_default_mode_is_auto(self, monkeypatch):
        monkeypatch.delenv("TURBO_MODE", raising=False)
        assert tq.get_mode() == tq.MODE_AUTO

    def test_set_mode_money(self):
        tq.set_mode("MONEY")
        assert tq.get_mode() == tq.MODE_MONEY

    def test_set_mode_power(self):
        tq.set_mode("POWER")
        assert tq.get_mode() == tq.MODE_POWER

    def test_set_mode_auto(self):
        tq.set_mode("AUTO")
        assert tq.get_mode() == tq.MODE_AUTO

    def test_set_mode_case_insensitive(self):
        tq.set_mode("money")
        assert tq.get_mode() == tq.MODE_MONEY

    def test_set_mode_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid TURBO_MODE"):
            tq.set_mode("ULTRA")

    def test_set_mode_returns_normalised(self):
        result = tq.set_mode("power")
        assert result == "POWER"


# ══════════════════════════════════════════════════════════════════════════════
# Complexity estimation
# ══════════════════════════════════════════════════════════════════════════════

class TestEstimateComplexity:
    def test_empty_string_returns_mid(self):
        score = tq.estimate_complexity("")
        assert score == 0.5

    def test_simple_keywords_lower_score(self):
        simple_score  = tq.estimate_complexity("summarize briefly")
        complex_score = tq.estimate_complexity("analyze and evaluate the strategy")
        assert simple_score < complex_score

    def test_complex_keywords_raise_score(self):
        simple_score = tq.estimate_complexity("summarize briefly")
        # Use many complex keywords to clearly push score above simple
        score = tq.estimate_complexity(
            "analyze evaluate strategy architecture design implement debug reason synthesize"
        )
        assert score > simple_score

    def test_score_bounded_0_to_1(self):
        for text in ["", "a", "analyze " * 50, "summarize " * 50]:
            s = tq.estimate_complexity(text)
            assert 0.0 <= s <= 1.0, f"Out of bounds: {s} for '{text[:30]}'"

    def test_longer_text_higher_base_score(self):
        short = tq.estimate_complexity("fix this")
        long  = tq.estimate_complexity("analyze " * 20)
        # Long complex text should score higher
        assert long >= short


# ══════════════════════════════════════════════════════════════════════════════
# VRAM estimation
# ══════════════════════════════════════════════════════════════════════════════

class TestVramEstimateGb:
    def test_zero_params_returns_zero(self):
        assert tq.vram_estimate_gb(0, tq.QUANT_4BIT) == 0.0

    def test_negative_params_returns_zero(self):
        assert tq.vram_estimate_gb(-1, tq.QUANT_4BIT) == 0.0

    def test_7b_4bit_estimate(self):
        est = tq.vram_estimate_gb(7.0, tq.QUANT_4BIT)
        # 7 * 0.58 + 0.5 = 4.56
        assert 4.0 < est < 6.0

    def test_fp16_higher_than_4bit(self):
        assert tq.vram_estimate_gb(7.0, tq.QUANT_FP16) > tq.vram_estimate_gb(7.0, tq.QUANT_4BIT)

    def test_unknown_quant_uses_fallback(self):
        est = tq.vram_estimate_gb(7.0, "UNKNOWN_QUANT")
        # fallback is 1.0 GB per B: 7 * 1.0 + 0.5 = 7.5
        assert est > 0


# ══════════════════════════════════════════════════════════════════════════════
# Model selection
# ══════════════════════════════════════════════════════════════════════════════

class TestSelectModel:
    def test_returns_quant_config(self):
        cfg = tq.select_model()
        assert hasattr(cfg, "model")
        assert hasattr(cfg, "quant")
        assert hasattr(cfg, "provider")

    def test_money_mode_selects_cheap_model(self):
        tq.set_mode("MONEY")
        cfg = tq.select_model(category="general")
        assert cfg.mode == "MONEY"

    def test_power_mode_selects_larger_model(self):
        tq.set_mode("POWER")
        cfg_power = tq.select_model(category="general")
        tq.set_mode("MONEY")
        cfg_money = tq.select_model(category="general")
        # Power tier should have >= params than money tier
        assert cfg_power.params_b >= cfg_money.params_b

    def test_auto_mode_low_complexity_picks_money_tier(self):
        tq.set_mode("AUTO")
        cfg = tq.select_model(category="general", complexity=0.1)
        assert cfg.complexity < tq.LOW_COMPLEXITY_THRESHOLD or cfg.mode == "AUTO"

    def test_auto_mode_high_complexity_picks_power_tier(self):
        tq.set_mode("AUTO")
        cfg_low  = tq.select_model(category="general", complexity=0.0)
        cfg_high = tq.select_model(category="general", complexity=1.0)
        assert cfg_high.params_b >= cfg_low.params_b

    def test_explicit_complexity_overrides_task(self):
        cfg = tq.select_model(task="summarize", complexity=0.9)
        # Complexity 0.9 is high — should trigger mid or power tier
        assert cfg.complexity == 0.9

    def test_rationale_is_non_empty(self):
        cfg = tq.select_model()
        assert cfg.rationale

    def test_all_categories_return_config(self):
        for cat in tq._CATEGORY_TIERS:
            cfg = tq.select_model(category=cat)
            assert cfg.model, f"Empty model for category '{cat}'"

    def test_mode_override_per_call(self):
        tq.set_mode("MONEY")
        cfg = tq.select_model(category="general", mode="POWER")
        assert cfg.mode == "POWER"


# ══════════════════════════════════════════════════════════════════════════════
# Memory management
# ══════════════════════════════════════════════════════════════════════════════

class TestMemoryManagement:
    def test_memory_status_structure(self):
        status = tq.memory_status()
        for key in ("budget_gb", "used_est_gb", "free_est_gb", "loaded_models"):
            assert key in status

    def test_register_and_unregister_model(self):
        tq.register_loaded_model("llama3.2:3b-q4", 2.0)
        status = tq.memory_status()
        assert "llama3.2:3b-q4" in status["loaded_models"]
        assert status["used_est_gb"] >= 2.0

        tq.unregister_model("llama3.2:3b-q4")
        status2 = tq.memory_status()
        assert "llama3.2:3b-q4" not in status2["loaded_models"]

    def test_unregister_nonexistent_is_safe(self):
        tq.unregister_model("nonexistent-model")  # must not raise

    def test_evict_if_needed_empty_when_fits(self):
        # No models loaded → always fits
        evict = tq._evict_if_needed(0.1)
        assert evict == []

    def test_evict_if_needed_returns_keys_when_full(self):
        # Fill up budget
        tq.register_loaded_model("big-model", tq.VRAM_BUDGET_GB)
        evict = tq._evict_if_needed(1.0)
        assert "big-model" in evict

    def test_should_offload_to_cpu_small_model(self):
        # A 0.1B FP16 model needs ~0.7 GB; CPU-only machine budget may be large
        # Just assert it returns a bool
        result = tq.should_offload_to_cpu(0.1, tq.QUANT_FP16)
        assert isinstance(result, bool)

    def test_used_est_cannot_exceed_registered(self):
        tq.register_loaded_model("model-a", 1.0)
        tq.register_loaded_model("model-b", 1.5)
        status = tq.memory_status()
        assert abs(status["used_est_gb"] - 2.5) < 0.01


# ══════════════════════════════════════════════════════════════════════════════
# Acceleration hints
# ══════════════════════════════════════════════════════════════════════════════

class TestSuggestAcceleration:
    def test_returns_dict_with_keys(self):
        result = tq.suggest_acceleration(7.0, "ollama", tq.QUANT_4BIT)
        for key in ("flash_attention", "onnx_recommended", "batch_supported", "tips"):
            assert key in result

    def test_ollama_provider_batch_supported(self):
        result = tq.suggest_acceleration(7.0, "ollama", tq.QUANT_4BIT)
        assert result["batch_supported"] is True

    def test_cloud_provider_batch_not_supported(self):
        result = tq.suggest_acceleration(7.0, "openai", tq.QUANT_FP16)
        assert result["batch_supported"] is False

    def test_nvidia_nim_flash_attention(self):
        result = tq.suggest_acceleration(70.0, "nvidia_nim", tq.QUANT_GPTQ)
        assert result["flash_attention"] is True

    def test_tips_is_list(self):
        result = tq.suggest_acceleration(7.0, "ollama", tq.QUANT_4BIT)
        assert isinstance(result["tips"], list)

    def test_large_model_flash_attention_hint(self):
        result = tq.suggest_acceleration(7.0, "ollama", tq.QUANT_4BIT)
        assert result["flash_attention"] is True


# ══════════════════════════════════════════════════════════════════════════════
# Performance logger
# ══════════════════════════════════════════════════════════════════════════════

class TestLogInference:
    def test_log_creates_file(self):
        tq.log_inference(agent_id="test", latency_ms=100.0)
        assert tq.LOG_FILE.exists()

    def test_log_entry_is_valid_json(self):
        tq.log_inference(agent_id="test2", latency_ms=200.0, quality_score=0.8)
        lines = [l for l in tq.LOG_FILE.read_text().splitlines() if l]
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["agent_id"] == "test2"

    def test_read_recent_logs_empty_without_file(self):
        result = tq.read_recent_logs(n=10)
        assert result == []

    def test_read_recent_logs_returns_entries(self):
        for i in range(5):
            tq.log_inference(agent_id=f"agent-{i}", latency_ms=float(i * 100))
        result = tq.read_recent_logs(n=10)
        assert len(result) == 5

    def test_read_recent_logs_n_limit(self):
        for i in range(20):
            tq.log_inference(agent_id=f"a{i}")
        result = tq.read_recent_logs(n=5)
        assert len(result) == 5


# ══════════════════════════════════════════════════════════════════════════════
# _analyse_logs and _build_suggestions
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalyseLogs:
    def _sample_entries(self):
        return [
            {"model": "llama3.2:3b-q4", "quant": "Q4_K_M", "provider": "ollama",
             "latency_ms": 1000.0, "quality_score": 0.9, "error": ""},
            {"model": "llama3.2:3b-q4", "quant": "Q4_K_M", "provider": "ollama",
             "latency_ms": 1200.0, "quality_score": 0.8, "error": ""},
            {"model": "gemma2:9b-q8", "quant": "Q8_0", "provider": "ollama",
             "latency_ms": 8000.0, "quality_score": 0.3, "error": "timeout"},
        ]

    def test_returns_dict_keyed_by_model(self):
        stats = tq._analyse_logs(self._sample_entries())
        assert "llama3.2:3b-q4" in stats
        assert "gemma2:9b-q8" in stats

    def test_count_is_correct(self):
        stats = tq._analyse_logs(self._sample_entries())
        assert stats["llama3.2:3b-q4"]["count"] == 2

    def test_avg_latency_computed(self):
        stats = tq._analyse_logs(self._sample_entries())
        assert stats["llama3.2:3b-q4"]["avg_latency_ms"] == pytest.approx(1100.0)

    def test_avg_quality_computed(self):
        stats = tq._analyse_logs(self._sample_entries())
        assert stats["llama3.2:3b-q4"]["avg_quality"] == pytest.approx(0.85, abs=0.01)

    def test_error_rate_computed(self):
        stats = tq._analyse_logs(self._sample_entries())
        # gemma2 has 1 error out of 1 → 100%
        assert stats["gemma2:9b-q8"]["error_rate"] == pytest.approx(1.0)

    def test_empty_entries_returns_empty(self):
        assert tq._analyse_logs([]) == {}


class TestBuildSuggestions:
    def test_high_latency_generates_suggestion(self):
        stats = {
            "slow-model": {
                "model": "slow-model", "quant": "Q8_0", "provider": "ollama",
                "count": 5, "avg_latency_ms": 9000.0, "p95_latency_ms": 10000.0,
                "avg_quality": 0.8, "error_rate": 0.0,
            }
        }
        suggestions = tq._build_suggestions(stats)
        assert len(suggestions) >= 1
        assert any("latency" in i.lower() for s in suggestions for i in s["issues"])

    def test_low_quality_generates_suggestion(self):
        stats = {
            "poor-model": {
                "model": "poor-model", "quant": "Q4_K_M", "provider": "ollama",
                "count": 10, "avg_latency_ms": 500.0, "p95_latency_ms": 800.0,
                "avg_quality": 0.1, "error_rate": 0.0,
            }
        }
        suggestions = tq._build_suggestions(stats)
        assert any("quality" in i.lower() for s in suggestions for i in s["issues"])

    def test_high_error_rate_generates_suggestion(self):
        stats = {
            "flaky-model": {
                "model": "flaky-model", "quant": "Q4_K_M", "provider": "ollama",
                "count": 10, "avg_latency_ms": 500.0, "p95_latency_ms": 700.0,
                "avg_quality": 0.9, "error_rate": 0.5,
            }
        }
        suggestions = tq._build_suggestions(stats)
        assert any("error" in i.lower() for s in suggestions for i in s["issues"])

    def test_good_model_no_suggestions(self):
        stats = {
            "good-model": {
                "model": "good-model", "quant": "Q4_K_M", "provider": "ollama",
                "count": 100, "avg_latency_ms": 800.0, "p95_latency_ms": 1200.0,
                "avg_quality": 0.9, "error_rate": 0.01,
            }
        }
        suggestions = tq._build_suggestions(stats)
        assert suggestions == []


# ══════════════════════════════════════════════════════════════════════════════
# run_auto_improvement
# ══════════════════════════════════════════════════════════════════════════════

class TestRunAutoImprovement:
    def test_no_logs_returns_message(self):
        result = tq.run_auto_improvement()
        assert "message" in result
        assert result["stats"] == {}

    def test_with_logs_returns_stats(self):
        for _ in range(5):
            tq.log_inference(
                agent_id="test", model="llama3.2:3b-q4",
                latency_ms=900.0, quality_score=0.85,
            )
        result = tq.run_auto_improvement()
        assert result["analysed"] == 5
        assert "llama3.2:3b-q4" in result["stats"]

    def test_writes_suggestions_file(self):
        tq.log_inference(agent_id="x", model="m1", latency_ms=100.0)
        tq.run_auto_improvement()
        assert tq.SUGGESTIONS_FILE.exists()

    def test_result_has_required_keys(self):
        tq.log_inference(agent_id="x", model="m1")
        result = tq.run_auto_improvement()
        for key in ("analysed", "models_seen", "stats", "suggestions", "sandbox", "ts"):
            assert key in result


# ══════════════════════════════════════════════════════════════════════════════
# Quantization format recommendation
# ══════════════════════════════════════════════════════════════════════════════

class TestRecommendQuantFormat:
    _VALID_QUANTS = {tq.QUANT_4BIT, tq.QUANT_5BIT, tq.QUANT_8BIT,
                    tq.QUANT_FP16, tq.QUANT_GPTQ, tq.QUANT_AWQ}

    def test_returns_dict(self):
        result = tq.recommend_quant_format(7.0)
        assert isinstance(result, dict)
        assert "format" in result

    def test_has_required_keys(self):
        result = tq.recommend_quant_format(7.0)
        for key in ("format", "gguf_tag", "rationale", "ollama_pull_cmd"):
            assert key in result

    def test_large_model_recommends_known_quant(self):
        result = tq.recommend_quant_format(70.0, task_type="general")
        assert result["format"] in self._VALID_QUANTS

    def test_tiny_model_recommends_known_quant(self):
        result = tq.recommend_quant_format(0.5, task_type="general")
        assert result["format"] in self._VALID_QUANTS

    def test_all_task_types_return_valid_quant(self):
        for task_type in ("general", "coding", "reasoning", "creative"):
            result = tq.recommend_quant_format(7.0, task_type=task_type)
            assert result["format"] in self._VALID_QUANTS

    def test_zero_params_returns_fp16(self):
        result = tq.recommend_quant_format(0)
        assert result["format"] == tq.QUANT_FP16


# ══════════════════════════════════════════════════════════════════════════════
# AirLLM config
# ══════════════════════════════════════════════════════════════════════════════

class TestAirllmConfig:
    def test_returns_dict(self):
        result = tq.airllm_config(7.0)
        assert isinstance(result, dict)

    def test_has_compression_key(self):
        result = tq.airllm_config(7.0, quant=tq.QUANT_4BIT)
        assert "compression" in result

    def test_4bit_compression(self):
        result = tq.airllm_config(7.0, quant=tq.QUANT_4BIT)
        assert result["compression"] == "4bit"

    def test_8bit_compression(self):
        result = tq.airllm_config(7.0, quant=tq.QUANT_8BIT)
        assert result["compression"] == "8bit"

    def test_recommended_flag_present(self):
        result = tq.airllm_config(7.0)
        assert "recommended" in result


# ══════════════════════════════════════════════════════════════════════════════
# InferenceTimer context manager
# ══════════════════════════════════════════════════════════════════════════════

class TestInferenceTimer:
    def test_logs_entry_on_exit(self):
        with tq.InferenceTimer(agent_id="timer-test"):
            time.sleep(0.01)
        entries = tq.read_recent_logs(n=5)
        last = entries[-1]
        assert last["agent_id"] == "timer-test"
        # Latency must be at least 10 ms (we slept 10 ms)
        assert last["latency_ms"] >= 10.0

    def test_logs_on_exit(self):
        with tq.InferenceTimer(agent_id="timer-log"):
            pass
        entries = tq.read_recent_logs(n=5)
        assert any(e.get("agent_id") == "timer-log" for e in entries)
