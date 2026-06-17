"""Phase A4/A6 — quant-aware resolution, honest availability, KV-aware options, and
one-heavy-at-a-time lifecycle wired into the inference path (runtime/engine/inference/llm.py)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from core import model_lanes as ml  # noqa: E402
from engine.compute import vram_budget as vb  # noqa: E402
import engine.inference.llm as L  # noqa: E402


# ── A2 helper: best_quant_for_model (used by A4 _resolve_quant_model) ──────────

def test_best_quant_picks_top_fitting_quant(monkeypatch):
    monkeypatch.setattr(ml, "_live_free_vram_mb", lambda: 20000)
    out = ml.best_quant_for_model("gemma3:4b-it-qat")
    assert out["model"] == "gemma3:4b-it-qat"
    assert out["quant"] and out["fits"] is True
    assert out["offload_layers"] == 0


def test_best_quant_offloads_when_constrained(monkeypatch):
    monkeypatch.setattr(ml, "_live_free_vram_mb", lambda: 4000)
    out = ml.best_quant_for_model("qwen2.5-coder:14b")
    assert out["fits"] is False
    assert out["offload_layers"] > 0  # honest partial offload, never None/OOM


def test_best_quant_unknown_model_returns_none_quant(monkeypatch):
    monkeypatch.setattr(ml, "_live_free_vram_mb", lambda: 8000)
    out = ml.best_quant_for_model("totally-unknown:9b")
    assert out["model"] == "totally-unknown:9b"
    assert out["quant"] is None  # caller keeps current behaviour, Ollama decides


def test_resolve_quant_model_keeps_identity(monkeypatch):
    monkeypatch.setattr(ml, "_live_free_vram_mb", lambda: 20000)
    model, quant = L._resolve_quant_model("gemma3:4b-it-qat")
    assert model == "gemma3:4b-it-qat"  # identity never changes
    assert quant


# ── A4: honest availability — never a silent OOM/downgrade ────────────────────

def test_ensure_model_available_installed(monkeypatch):
    monkeypatch.setattr(L, "_installed_tags", lambda ttl=30.0: {"gemma3:4b-it-qat", "gemma3"})
    out = L.ensure_model_available("gemma3:4b-it-qat")
    assert out["available"] is True


def test_ensure_model_available_missing_blocks_with_suggestion(monkeypatch):
    monkeypatch.setattr(L, "_installed_tags", lambda ttl=30.0: {"llama3.2"})
    monkeypatch.delenv("OLLAMA_AUTO_PULL", raising=False)
    out = L.ensure_model_available("gemma3:12b-it-qat")
    assert out["available"] is False
    assert out["install_suggestion"] == "gemma3:12b-it-qat"  # honest install hint


def test_ensure_model_available_unknown_taglist_does_not_block(monkeypatch):
    monkeypatch.setattr(L, "_installed_tags", lambda ttl=30.0: None)
    out = L.ensure_model_available("anything:latest")
    assert out["available"] is True  # can't prove absence → proceed (Ollama errors if missing)


# ── A4: KV-aware Ollama options + legacy fallback ─────────────────────────────

def test_build_options_uses_budgeter_for_profiled_model(monkeypatch):
    monkeypatch.setattr(vb, "_live_free_vram_mb", lambda: 20000)
    opts, meta = L._build_ollama_options("gemma3:4b-it-qat", "q4_0")
    assert meta["source"] == "vram_budget"
    assert opts["num_ctx"] == meta["num_ctx"]
    assert "num_gpu" not in opts  # full GPU fit → omit num_gpu, let Ollama use all layers
    assert meta["est_vram_mb"] is not None


def test_build_options_partial_offload_when_tight(monkeypatch):
    monkeypatch.setattr(vb, "_live_free_vram_mb", lambda: 4000)
    opts, meta = L._build_ollama_options("qwen2.5-coder:14b", "q4_K_M")
    assert meta["source"] == "vram_budget"
    assert opts.get("num_gpu", -1) >= 0  # explicit partial offload set (not OOM)
    assert meta["fits"] is False


def test_build_options_legacy_for_unprofiled_model(monkeypatch):
    monkeypatch.setattr(vb, "_live_free_vram_mb", lambda: 8000)
    opts, meta = L._build_ollama_options("totally-unknown:9b", None)
    assert meta["source"] == "legacy"
    assert isinstance(opts, dict)


# ── A4: inference logging to state/turbo_quant.log.jsonl ──────────────────────

def test_log_inference_writes_jsonl(monkeypatch, tmp_path):
    import core.state_paths as sp
    monkeypatch.setattr(sp, "canonical_state_dir", lambda: tmp_path)
    meta = {"est_vram_mb": 4222, "free_vram_mb": 6000, "num_gpu": -1,
            "num_ctx": 4096, "fits": True, "source": "vram_budget"}
    L._log_inference("gemma3:4b-it-qat", "q4_0", meta, 812.4, "short")
    line = (tmp_path / "turbo_quant.log.jsonl").read_text().strip()
    rec = json.loads(line)
    assert rec["model"] == "gemma3:4b-it-qat" and rec["quant"] == "q4_0"
    assert rec["est_vram_mb"] == 4222 and rec["latency_ms"] == 812.4


# ── A6: one-heavy-at-a-time lifecycle ─────────────────────────────────────────

def test_ensure_model_ready_empty_model_returns_false():
    assert L.ensure_model_ready("") is False


def test_ensure_model_ready_accepts_live_estimate(monkeypatch):
    calls = {"warm": None}
    monkeypatch.setattr(L, "_ollama_post",
                        lambda ep, payload, t: calls.__setitem__("warm", payload) or {})
    # Live estimate is honoured (no crash) and the warm call fires with the right model.
    assert L.ensure_model_ready("gemma3:4b-it-qat", needed_mb=4222) is True
    assert calls["warm"]["model"] == "gemma3:4b-it-qat"


def test_ensure_model_ready_evicts_when_estimate_exceeds_free(monkeypatch):
    import importlib
    try:
        lcm = importlib.import_module("neural_brain.models.lifecycle_manager")
    except Exception:
        import pytest
        pytest.skip("lifecycle_manager unavailable")
    monkeypatch.setattr(lcm, "_free_vram_mb", lambda: 3000)
    evicted = {"called": False, "keep": None}
    monkeypatch.setattr(L, "_evict_idle_models",
                        lambda keep=None: evicted.update(called=True, keep=keep))
    monkeypatch.setattr(L, "_ollama_post", lambda ep, payload, t: {})
    # A heavy model (needs 8000 > 3000*0.85) must trigger eviction of idle heavies,
    # while keeping the permanent set + this model resident.
    L.ensure_model_ready("qwen2.5-coder:14b", needed_mb=8000)
    assert evicted["called"] is True
    assert "qwen2.5-coder:14b" in evicted["keep"]
    assert L.DEFAULT_MODEL in evicted["keep"]  # llama3.2 stays hot (one-heavy-at-a-time)
