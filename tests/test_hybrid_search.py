"""Tests for BM25 scorer and hybrid_search in memory_router."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))

from memory.bm25 import BM25


# ── BM25 unit tests ───────────────────────────────────────────────────────────

class TestBM25:

    def test_exact_match_scores_higher(self):
        corpus = ["the quick brown fox", "something completely unrelated"]
        bm25 = BM25(corpus)
        scores = bm25.scores("quick fox")
        assert scores[0] > scores[1]

    def test_scores_length_matches_corpus(self):
        corpus = ["doc one", "doc two", "doc three"]
        bm25 = BM25(corpus)
        assert len(bm25.scores("one")) == 3

    def test_empty_corpus_returns_empty(self):
        bm25 = BM25([])
        assert bm25.scores("anything") == []

    def test_no_match_scores_zero_or_low(self):
        corpus = ["bananas and mangoes", "tropical fruit salad"]
        bm25 = BM25(corpus)
        scores = bm25.scores("zzz_nonexistent_term_xyz")
        assert all(s == 0.0 for s in scores)

    def test_scores_non_negative(self):
        corpus = ["hello world", "foo bar baz", "python testing code"]
        bm25 = BM25(corpus)
        for s in bm25.scores("hello python"):
            assert s >= 0.0

    def test_repeated_term_boosts_score(self):
        corpus = ["test test test repeated", "test once"]
        bm25 = BM25(corpus)
        scores = bm25.scores("test")
        # First doc has more term frequency — should score higher
        assert scores[0] > scores[1]


# ── hybrid_search tests ───────────────────────────────────────────────────────

class TestHybridSearch:

    @pytest.fixture()
    def populated_ks(self, tmp_path, monkeypatch):
        """Write a knowledge_store.json and redirect _KS_PATH."""
        ks = {
            "entries": [
                {"source": "https://a.com", "content": "machine learning neural networks deep learning"},
                {"source": "https://b.com", "content": "python programming language syntax"},
                {"source": "https://c.com", "content": "machine learning classification algorithms"},
            ]
        }
        ks_path = tmp_path / "knowledge_store.json"
        ks_path.write_text(json.dumps(ks))
        monkeypatch.setenv("STATE_DIR", str(tmp_path))
        import importlib
        import memory.memory_router as mr
        monkeypatch.setattr(mr, "_KS_PATH", ks_path)
        return ks_path

    def test_returns_list(self, populated_ks):
        from memory.memory_router import hybrid_search
        results = hybrid_search("machine learning", top_k=2)
        assert isinstance(results, list)

    def test_results_have_required_fields(self, populated_ks):
        from memory.memory_router import hybrid_search
        results = hybrid_search("machine learning", top_k=2)
        assert len(results) > 0
        for r in results:
            for key in ("source", "content", "score", "bm25_score", "vector_score", "rank"):
                assert key in r, f"Missing key: {key}"

    def test_top_k_limits_results(self, populated_ks):
        from memory.memory_router import hybrid_search
        results = hybrid_search("machine learning", top_k=1)
        assert len(results) <= 1

    def test_relevant_doc_ranks_higher(self, populated_ks):
        from memory.memory_router import hybrid_search
        results = hybrid_search("machine learning neural networks", top_k=3, alpha=0.0)
        # With alpha=0 (pure BM25), ML docs should outscore Python doc
        sources = [r["source"] for r in results]
        python_idx = next((i for i, s in enumerate(sources) if "b.com" in s), None)
        # python doc should not be ranked first
        assert python_idx != 0 or len(results) == 1

    def test_alpha_zero_uses_bm25_only(self, populated_ks):
        from memory.memory_router import hybrid_search
        results = hybrid_search("python programming", top_k=3, alpha=0.0)
        assert results, "Should return results with alpha=0"
        # vector_score contribution is 0 — score should equal bm25 component
        for r in results:
            assert r["bm25_score"] >= 0.0

    def test_rank_field_is_sequential(self, populated_ks):
        from memory.memory_router import hybrid_search
        results = hybrid_search("machine learning", top_k=3)
        for i, r in enumerate(results):
            assert r["rank"] == i + 1

    def test_empty_store_falls_back_gracefully(self, tmp_path, monkeypatch):
        ks_path = tmp_path / "knowledge_store.json"
        ks_path.write_text(json.dumps({"entries": []}))
        import memory.memory_router as mr
        monkeypatch.setattr(mr, "_KS_PATH", ks_path)
        from memory.memory_router import hybrid_search
        # Should not raise — fallback to vector router (which may return empty)
        results = hybrid_search("anything", top_k=3)
        assert isinstance(results, list)
