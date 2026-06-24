"""video_render (HyperFrames) + pageindex (vectorless RAG) atomic tools.

Hermetic: no Ollama, no headless browser, no network. video_render uses dry_run/
disabled paths; pageindex uses force_keyword (deterministic). Both must NEVER raise
and must register in the tool registry."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from tools import video_render_tool as vr  # noqa: E402
from tools import pageindex_tool as pi  # noqa: E402
from tools.registry import call_tool, list_tools  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.delenv("VIDEO_RENDER_ENABLED", raising=False)  # default off
    yield


# ── registration ─────────────────────────────────────────────────────────────
def test_both_tools_registered():
    names = {t["name"] for t in list_tools()}
    assert "video_render" in names
    assert "pageindex" in names


# ── video_render ─────────────────────────────────────────────────────────────
def test_video_render_requires_html():
    assert vr._call({})["status"] == "error"


def test_video_render_oversize_html():
    big = "x" * (vr._MAX_HTML_BYTES + 1)
    assert vr._call({"html": big})["status"] == "error"


def test_video_render_dry_run_validates_without_rendering(tmp_path):
    out = vr._call({"html": "<!doctype html><body>hi</body>", "name": "promo!!", "dry_run": True})
    assert out["status"] == "planned"
    assert out["plan"]["render_id"].startswith("promo")  # name sanitized
    # nothing left behind
    assert not list((tmp_path / "artifacts").glob("hyperframes-*"))


def test_video_render_disabled_by_default():
    out = vr._call({"html": "<!doctype html><body>hi</body>"})
    assert out["status"] == "disabled"  # VIDEO_RENDER_ENABLED != 1


def test_video_render_never_raises():
    assert call_tool("video_render", {"html": 123})["status"] == "error"
    assert call_tool("video_render", {})["status"] == "error"


# ── pageindex ────────────────────────────────────────────────────────────────
DOC = """# Pet Policy
Intro about pets.

## Domestic Animals
Dogs and cats are allowed in designated areas.

## Fees
A pet fee of $50 applies per stay.

# Parking
Garage details here.
"""


def test_pageindex_requires_inputs():
    assert pi._call({"query": "x"})["status"] == "error"
    assert pi._call({"document": "x"})["status"] == "error"


def test_pageindex_builds_hierarchical_tree():
    sections = pi._build_tree(DOC)
    titles = [s["title"] for s in sections]
    assert "Domestic Animals" in titles
    # nested heading carries its parent path
    dom = next(s for s in sections if s["title"] == "Domestic Animals")
    assert dom["path"] == "Pet Policy > Domestic Animals"


def test_pageindex_keyword_retrieval_finds_relevant_section():
    out = pi._call({"document": DOC, "query": "can I bring my dog?", "force_keyword": True})
    assert out["status"] == "success"
    assert out["method"] == "keyword"
    assert out["traceable"] is True
    # the dog answer lives under Domestic Animals
    assert any("Domestic Animals" in s["title"] for s in out["sections"])


def test_pageindex_local_only_guard(monkeypatch):
    # A non-loopback OLLAMA_HOST must disable the LLM path (no data egress).
    monkeypatch.setattr(pi, "_OLLAMA_HOST", "http://203.0.113.9:11434")
    assert pi._local_llm_select("q", pi._build_tree(DOC), 2) is None


def test_pageindex_never_raises():
    assert call_tool("pageindex", {"document": 5, "query": "x"})["status"] == "error"
