"""Tests for KnowledgeStore.hybrid_search() — Phase 5D semantic search.

Verifies:
- Results always contain a ``source`` field
- Results always contain a ``score`` field
- Pure vector search (alpha=1.0) returns a list
- Pure BM25/keyword search (alpha=0.0) returns a list
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AI_HOME", str(tmp_path))

    import importlib
    for mod_name in ("core.knowledge_store", "memory.vector_store"):
        try:
            mod = sys.modules.get(mod_name)
            if mod is None:
                importlib.import_module(mod_name)
                mod = sys.modules[mod_name]
            mod._instance = None
        except Exception:
            pass

    yield tmp_path

    for mod_name in ("core.knowledge_store", "memory.vector_store"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            mod._instance = None


@pytest.fixture()
def populated_store(isolate_state):
    """Knowledge store with 3 embedded entries; returns (ks, ks_path)."""
    ks_path = isolate_state / "knowledge_store.json"
    entries = [
        {
            "id": "sem1",
            "title": "Machine Learning Basics",
            "content": "Supervised learning trains models on labelled data.",
            "source": "https://example.com/ml",
            "tags": ["ml", "ai"],
        },
        {
            "id": "sem2",
            "title": "Sales Pipeline Guide",
            "content": "A sales pipeline tracks deals through qualification stages.",
            "source": "https://example.com/sales",
            "tags": ["sales"],
        },
        {
            "id": "sem3",
            "title": "CI/CD Overview",
            "content": "Continuous integration runs tests on every commit.",
            "source": "https://example.com/cicd",
            "tags": ["devops"],
        },
    ]
    ks_path.write_text(json.dumps({"entries": entries}), encoding="utf-8")

    from core.knowledge_store import get_knowledge_store
    ks = get_knowledge_store(ks_path)
    ks.embed_entries_to_vector_store()
    return ks


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHybridSearch:

    def test_results_have_source_field(self, populated_store):
        """Every result from hybrid_search() must include a 'source' field."""
        results = populated_store.hybrid_search("machine learning")
        assert isinstance(results, list)
        assert len(results) > 0
        for r in results:
            assert "source" in r, f"Missing 'source' in result: {r}"
            assert r["source"]  # non-empty

    def test_results_have_score_field(self, populated_store):
        """Every result from hybrid_search() must include a numeric 'score' field."""
        results = populated_store.hybrid_search("machine learning")
        assert len(results) > 0
        for r in results:
            assert "score" in r, f"Missing 'score' in result: {r}"
            assert isinstance(r["score"], float)
            assert 0.0 <= r["score"] <= 1.0, f"Score out of range: {r['score']}"

    def test_pure_vector_search_returns_list(self, populated_store):
        """alpha=1.0 (pure vector) must return a list."""
        results = populated_store.hybrid_search("sales pipeline", alpha=1.0)
        assert isinstance(results, list)

    def test_pure_keyword_search_returns_list(self, populated_store):
        """alpha=0.0 (pure BM25/keyword) must return a list."""
        results = populated_store.hybrid_search("sales pipeline", alpha=0.0)
        assert isinstance(results, list)

    def test_empty_query_returns_list(self, populated_store):
        """An empty query should return a list (possibly empty) without raising."""
        results = populated_store.hybrid_search("")
        assert isinstance(results, list)

    def test_results_sorted_by_score_descending(self, populated_store):
        """Results should be sorted highest score first."""
        results = populated_store.hybrid_search("continuous integration")
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limits_results(self, populated_store):
        """top_k parameter caps the number of returned results."""
        results = populated_store.hybrid_search("learning", top_k=2)
        assert len(results) <= 2

    def test_source_field_matches_original_entry(self, populated_store):
        """The source field should reflect the original entry's source URL."""
        results = populated_store.hybrid_search("machine learning", top_k=5)
        ml_results = [r for r in results if "sem1" in r.get("id", "")]
        if ml_results:
            assert ml_results[0]["source"] == "https://example.com/ml"
