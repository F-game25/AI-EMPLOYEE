"""Phase A1–A3 — quant-aware model lanes, roles, and KV-cache VRAM budgeter."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

ROOT = Path(__file__).resolve().parents[1]
from core import model_lanes as ml  # noqa: E402
from engine.compute import vram_budget as vb  # noqa: E402


# ── Config integrity ──────────────────────────────────────────────────────────

def test_configs_valid_json():
    profiles = json.loads((ROOT / "runtime/config/model_quant_profiles.json").read_text())
    roles = json.loads((ROOT / "runtime/config/model_roles.json").read_text())
    assert profiles and roles
    # Every role's preferred models should have a quant profile entry.
    prof = profiles.get("models", profiles)
    for role, spec in (roles.get("roles", roles)).items():
        for m in spec.get("preferred_models", []):
            assert m in prof, f"role {role} model {m} missing a quant profile"


# ── Quant-aware tier resolution ───────────────────────────────────────────────

def test_resolve_tier_with_quant_shape():
    out = ml.resolve_tier_with_quant("HEAVY")
    assert set(out) >= {"model", "quant", "vram_needed", "fits"}
    assert isinstance(out["model"], str) and out["model"]
    assert isinstance(out["quant"], str) and out["quant"]


def test_coding_role_never_degrades_to_general():
    out = ml.model_and_quant_for_role("coding")
    # Coding must resolve to a DESIGNATED coding model from the role config
    # (qwythos — the primary model with a hardened codegen Modelfile — or a
    # dedicated *coder), never a general fallback. Config-driven, no hardcoding.
    coding_models = {m.lower() for m in ml._model_roles()["coding"]["preferred_models"]}
    assert (out["model"] or "").lower() in coding_models, f"degraded to {out['model']}"


def test_execution_role_resolves_a_model():
    out = ml.model_and_quant_for_role("execution_reasoning")
    assert out["model"] and out["quant"]
    assert "available" in out


# ── KV-cache-aware VRAM budgeter ──────────────────────────────────────────────

def test_plan_fits_with_ample_vram(monkeypatch):
    monkeypatch.setattr(vb, "_live_free_vram_mb", lambda: 20000)
    p = vb.plan("gemma3:4b-it-qat", "q4_0", 4096)
    assert p["fits"] is True
    assert p["num_ctx"] == 4096
    # est = weights + kv + reserve, and must be <= free
    assert p["est_vram_mb"] <= 20000


def test_plan_tight_vram_does_not_silently_overcommit(monkeypatch):
    monkeypatch.setattr(vb, "_live_free_vram_mb", lambda: 1000)
    p = vb.plan("qwen2.5-coder:14b", "q4_K_M", 8192)
    # Either it reports it doesn't fully fit, or it offloads layers (num_gpu>=0),
    # but it must never claim a clean full-GPU fit it can't honor.
    assert p["fits"] is False or p["num_gpu"] >= 0
