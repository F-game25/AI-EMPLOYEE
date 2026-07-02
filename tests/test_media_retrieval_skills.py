"""product-video + document-qa skills (compose the video_render / pageindex tools).

Hermetic: the local-LLM step is patched per-skill-module; the pageindex retrieval
runs for real (reasoning if Ollama is up, deterministic keyword fallback in CI).
video_render stays in dry_run (no browser/render)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from skills import product_video as pv  # noqa: E402
from skills import document_qa as dq  # noqa: E402
from skills.catalog import get_skill_catalog  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.delenv("VIDEO_RENDER_ENABLED", raising=False)
    # Force pageindex's deterministic keyword path so skill tests are fast + hermetic
    # (no dependency on a running Ollama); the reasoning path is covered elsewhere.
    import tools.pageindex_tool as _pi
    monkeypatch.setattr(_pi, "_local_llm_select", lambda *a, **k: None)
    yield


# ── registration ─────────────────────────────────────────────────────────────
def test_skills_registered_in_catalog():
    cat = get_skill_catalog()
    assert cat.get("product-video") is not None
    assert cat.get("document-qa") is not None


# ── product-video ────────────────────────────────────────────────────────────
def test_product_video_requires_brief():
    assert pv.ProductVideoSkill().execute({}, lambda a, p: {})["status"] == "error"


def test_product_video_composes_html_then_dry_run_renders(monkeypatch):
    monkeypatch.setattr(pv, "local_chat", lambda *a, **k: "```html\n<!doctype html><body>Promo</body>\n```")
    out = pv.ProductVideoSkill().execute({"brief": "launch our app", "name": "launch"}, lambda a, p: {})
    assert out["status"] == "success"
    assert out["html_bytes"] > 0
    assert out["render"]["status"] == "planned"  # dry_run by default (render flag not set)


def test_product_video_degrades_without_local_model(monkeypatch):
    monkeypatch.setattr(pv, "local_chat", lambda *a, **k: None)
    out = pv.ProductVideoSkill().execute({"brief": "x"}, lambda a, p: {})
    assert out["status"] == "degraded"


# ── document-qa ──────────────────────────────────────────────────────────────
DOC = """# Pet Policy
## Domestic Animals
Dogs and cats are allowed in designated areas.
## Fees
A pet fee of $50 applies per stay.
"""


def test_document_qa_requires_inputs():
    s = dq.DocumentQASkill()
    assert s.execute({"query": "x"}, lambda a, p: {})["status"] == "error"
    assert s.execute({"document": "x"}, lambda a, p: {})["status"] == "error"


def test_document_qa_answers_with_citations(monkeypatch):
    monkeypatch.setattr(dq, "local_chat", lambda *a, **k: "A $50 pet fee applies (see Fees).")
    out = dq.DocumentQASkill().execute({"document": DOC, "query": "what is the pet fee?"}, lambda a, p: {})
    assert out["status"] == "success"
    assert "50" in out["answer"]
    assert out["citations"]  # at least one cited section
    assert out["retrieval_method"] in ("reasoning", "keyword")


def test_document_qa_partial_without_local_model(monkeypatch):
    monkeypatch.setattr(dq, "local_chat", lambda *a, **k: None)
    out = dq.DocumentQASkill().execute({"document": DOC, "query": "fee?"}, lambda a, p: {})
    assert out["status"] == "partial"
    assert out["citations"]  # evidence still returned
