"""Offline/local content generation (stable-diffusion.cpp) — no network.

Verifies the local catalog, the sd-cli arg construction per model type, honest
failure when the engine/model is absent, and that the content factory defaults
to the LOCAL (offline) provider.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from content import media_models as mm  # noqa: E402
from content import local_image_gen as lig  # noqa: E402


# ── Local catalog ─────────────────────────────────────────────────────────────

def test_local_catalog_loads():
    models = mm.local_models()
    assert len(models) >= 5
    ids = {m["id"] for m in models}
    assert "dreamshaper-8" in ids
    assert mm.default_local_model_id() in ids
    assert all(m["provider"] == "sdcpp" for m in models)


def test_zimage_aux_present():
    aux = mm.zimage_aux()
    assert "llm" in aux and "vae" in aux and aux["vae"]["filename"]


# ── sd-cli arg construction (faithful to the vendored engine) ─────────────────

def test_args_sd1_uses_dash_m():
    model = mm.get_local_model("dreamshaper-8")
    args = lig._build_args(model, Path("/m/ds.safetensors"), Path("/o.png"),
                           "a fox", negative=None, width=512, height=512,
                           seed=7, steps=None, cfg=None)
    assert args[0] == "-m"
    assert "--sampling-method" in args and "euler_a" in args
    assert "-p" in args and "a fox" in args and "-o" in args


def test_args_zimage_uses_diffusion_model_and_aux():
    model = mm.get_local_model("z-image-turbo")
    args = lig._build_args(model, Path("/m/z.gguf"), Path("/o.png"), "a fox",
                           negative=None, width=512, height=512, seed=1,
                           steps=None, cfg=None)
    assert args[0] == "--diffusion-model"
    assert "--llm" in args and "--vae" in args and "--scheduler" in args


def test_args_sdxl_flag():
    model = mm.get_local_model("stable-diffusion-xl-base")
    args = lig._build_args(model, Path("/m/x.safetensors"), Path("/o.png"), "a fox",
                           negative="blurry", width=1024, height=1024, seed=1,
                           steps=None, cfg=None)
    assert "--sd-version" in args and "sdxl" in args
    assert "-n" in args and "blurry" in args


# ── Honest failure (offline-only, no silent cloud fallback) ───────────────────

def test_generate_errors_when_engine_missing(monkeypatch):
    monkeypatch.setattr(lig, "find_binary", lambda: None)
    with pytest.raises(lig.LocalGenError) as e:
        lig.generate("a fox")
    assert "not installed" in str(e.value).lower()
    assert "cloud" in str(e.value).lower()  # explicitly refuses to call cloud


def test_generate_errors_when_model_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(lig, "find_binary", lambda: tmp_path / "sd-cli")
    (tmp_path / "sd-cli").write_text("#!/bin/sh\n")
    (tmp_path / "sd-cli").chmod(0o755)
    monkeypatch.setenv("SD_MODELS_DIR", str(tmp_path / "empty"))
    with pytest.raises(lig.LocalGenError) as e:
        lig.generate("a fox", model_id="dreamshaper-8")
    assert "model file missing" in str(e.value).lower()


# ── Content factory defaults to LOCAL ─────────────────────────────────────────

def test_factory_defaults_to_local_and_is_honest(monkeypatch):
    monkeypatch.setattr(lig, "find_binary", lambda: None)
    from content.content_factory import get_content_factory
    out = get_content_factory().generate_media("a fox")  # provider defaults to local
    assert out["ok"] is False and out["provider"] == "local"
    assert "scripts/setup_local_image_gen.py" in out["error"]
