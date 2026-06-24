"""Executable content skills — the quality gate, retry, artifact, and registration
that make the deepened skills *products* (not prompt templates). Hermetic: the local
model is patched per test."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from skills import executable_content as ec  # noqa: E402
from skills.executable_content import QualityGate, ExecutableContentSkill, build_executable_skills  # noqa: E402
from skills.catalog import get_skill_catalog  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    yield


# ── QualityGate ──────────────────────────────────────────────────────────────
def test_gate_flags_short_refusal_and_missing_pattern():
    g = QualityGate(min_chars=50, must_match=[r"subject\s*:"], must_match_desc=["subject"])
    ok, failed = g.check("Subject: Hi there — this is a sufficiently long marketing email body about X.")
    assert ok and not failed
    ok2, failed2 = g.check("too short")
    assert not ok2 and any("too_short" in f for f in failed2)
    ok3, failed3 = g.check("I cannot help with that as an AI language model, please provide more info now.")
    assert not ok3 and "refusal_or_input_request" in failed3
    ok4, failed4 = g.check("A long enough body of text but it is missing the required field entirely here.")
    assert not ok4 and any("missing:subject" in f for f in failed4)


# ── ExecutableContentSkill ───────────────────────────────────────────────────
def _skill():
    return ExecutableContentSkill("blog_writing", QualityGate(min_chars=30, must_match=[r"^#"], must_match_desc=["heading"]))


def test_requires_brief():
    assert _skill().execute({}, lambda a, p: {})["status"] == "error"


def test_success_validates_and_saves_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "local_chat", lambda *a, **k: "# Title\nA decent blog body that passes the gate.")
    out = _skill().execute({"brief": "remote work"}, lambda a, p: {})
    assert out["status"] == "success"
    assert out["quality"]["passed"] is True
    assert out["confidence"] == 0.85
    assert out["artifact"] and (tmp_path / "artifacts" / out["artifact"]).exists()


def test_low_quality_when_gate_fails_twice(monkeypatch):
    monkeypatch.setattr(ec, "local_chat", lambda *a, **k: "no heading here, just text but long enough to pass length")
    out = _skill().execute({"brief": "x"}, lambda a, p: {})
    assert out["status"] == "low_quality"
    assert out["quality"]["passed"] is False
    assert out["confidence"] == 0.4


def test_retry_recovers_on_second_attempt(monkeypatch):
    calls = {"n": 0}
    def fake(*a, **k):
        calls["n"] += 1
        return "bad" if calls["n"] == 1 else "# Good Heading\nNow with a heading and enough body text."
    monkeypatch.setattr(ec, "local_chat", fake)
    out = _skill().execute({"brief": "x"}, lambda a, p: {})
    assert out["status"] == "success"
    assert out["quality"]["retried"] is True
    assert calls["n"] == 2


def test_degraded_without_local_model(monkeypatch):
    monkeypatch.setattr(ec, "local_chat", lambda *a, **k: None)
    assert _skill().execute({"brief": "x"}, lambda a, p: {})["status"] == "degraded"


# ── registration ─────────────────────────────────────────────────────────────
def test_15_top_skills_built():
    assert len(build_executable_skills()) == 15


def test_deepened_skills_override_in_catalog():
    cat = get_skill_catalog()
    blog = cat.get("blog_writing")
    assert blog is not None
    # the executable (v2.0) version won over the prompt-only library entry
    assert getattr(blog, "version", None) == "2.0"
    assert "executable" in getattr(blog, "capability_tags", [])
