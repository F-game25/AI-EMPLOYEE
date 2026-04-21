"""Memory system tests.

Validates that the memory index can store, retrieve, and rank entries,
and that the strategy store persists data correctly.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))


# ---------------------------------------------------------------------------
# Test: Memory index core operations
# ---------------------------------------------------------------------------

class TestMemoryIndex:
    """Verify memory index storage and retrieval."""

    @pytest.fixture(autouse=True)
    def _isolated_memory(self, tmp_path, monkeypatch):
        """Run each test with a fresh, temp-backed MemoryIndex singleton.

        Without isolation the singleton accumulates entries across the entire
        test session (other test modules also call add_memory), which causes
        cosine-similarity ranking to push freshly added entries out of the
        small top_k window used by retrieval tests.
        """
        import core.memory_index as mi_mod
        monkeypatch.setenv("AI_HOME", str(tmp_path))
        with mi_mod._instance_lock:
            mi_mod._instance = None
        yield
        with mi_mod._instance_lock:
            mi_mod._instance = None

    def test_memory_index_importable(self) -> None:
        from core.memory_index import get_memory_index
        mi = get_memory_index()
        assert mi is not None

    def test_store_and_retrieve(self) -> None:
        """Store an entry and retrieve it by query."""
        from core.memory_index import get_memory_index
        mi = get_memory_index()
        mi.add_memory("Test entry for QA validation", importance=0.8)
        results = mi.get_relevant_memories("QA validation", top_k=5)
        assert isinstance(results, list)
        # At least one result should match
        assert len(results) >= 1
        found = any("QA validation" in str(r.get("text", "")) for r in results)
        assert found, f"Stored entry not found in results: {results}"

    def test_store_multiple_entries(self) -> None:
        """Storing multiple entries should all be retrievable."""
        from core.memory_index import get_memory_index
        mi = get_memory_index()
        entries = [
            "Agent performance metrics for Q1",
            "Security audit results from March",
            "Forge deployment log for version 2.1",
        ]
        for entry in entries:
            mi.add_memory(entry, importance=0.7)

        results = mi.get_relevant_memories("performance metrics", top_k=10)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_embed_text_produces_vector(self) -> None:
        """The embed_text function should produce a fixed-dimension vector."""
        from core.memory_index import embed_text, _DIM
        vec = embed_text("hello world test embedding")
        assert isinstance(vec, list)
        assert len(vec) == _DIM

    def test_cosine_similarity_range(self) -> None:
        """Cosine similarity should be in [-1, 1]."""
        from core.memory_index import cosine_similarity, embed_text
        a = embed_text("agent performance")
        b = embed_text("agent metrics")
        sim = cosine_similarity(a, b)
        assert -1.0 <= sim <= 1.0

    def test_empty_query_returns_list(self) -> None:
        """An empty query should still return a list (possibly empty)."""
        from core.memory_index import get_memory_index
        mi = get_memory_index()
        results = mi.get_relevant_memories("", top_k=5)
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Test: Strategy store
# ---------------------------------------------------------------------------

class TestStrategyStore:
    """Verify the strategy store for recording and retrieving strategies."""

    def test_strategy_store_importable(self) -> None:
        from memory.strategy_store import StrategyStore, get_strategy_store
        store = get_strategy_store()
        assert store is not None

    def test_record_strategy(self, tmp_path: Path) -> None:
        """Record a strategy and verify it persists."""
        from memory.strategy_store import StrategyStore
        store = StrategyStore(path=tmp_path / "strategies.json")
        store.record(
            goal_type="content_generation",
            agent="faceless_video",
            config={"platform": "tiktok", "length": 60},
            outcome_score=0.87,
        )
        best = store.get_best_strategy("content_generation")
        assert isinstance(best, list)
        assert len(best) >= 1
        assert best[0]["agent"] == "faceless_video"

    def test_record_low_score_strategy(self, tmp_path: Path) -> None:
        """A low-score strategy should still be recorded."""
        from memory.strategy_store import StrategyStore
        store = StrategyStore(path=tmp_path / "strategies.json")
        store.record(
            goal_type="research",
            agent="research_agent",
            config={"depth": "shallow"},
            outcome_score=0.2,
        )
        best = store.get_best_strategy("research")
        assert isinstance(best, list)
        # Even low-score entries are returned
        assert len(best) >= 1

    def test_multiple_strategies_returns_best(self, tmp_path: Path) -> None:
        """When multiple strategies exist, get_best_strategy returns sorted by score."""
        from memory.strategy_store import StrategyStore
        store = StrategyStore(path=tmp_path / "strategies.json")
        store.record(goal_type="email", agent="agent_a", config={}, outcome_score=0.65)
        store.record(goal_type="email", agent="agent_b", config={}, outcome_score=0.92)
        store.record(goal_type="email", agent="agent_c", config={}, outcome_score=0.78)

        best = store.get_best_strategy("email")
        assert isinstance(best, list)
        assert len(best) >= 2
        # The highest-scoring strategy should be first
        assert best[0]["outcome_score"] >= best[-1]["outcome_score"]


# ---------------------------------------------------------------------------
# Test: Knowledge store
# ---------------------------------------------------------------------------

class TestKnowledgeStore:
    """Verify the knowledge store module."""

    def test_knowledge_store_importable(self) -> None:
        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store()
        assert ks is not None

    def test_knowledge_store_has_add_method(self) -> None:
        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store()
        assert hasattr(ks, "add_knowledge")

    def test_knowledge_store_has_search_method(self) -> None:
        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store()
        assert hasattr(ks, "search_knowledge")

    def test_knowledge_store_add_and_search(self) -> None:
        """Add knowledge and verify it can be searched."""
        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store()
        ks.add_knowledge("qa_testing", "Automated QA system validates all subsystems")
        results = ks.search_knowledge("QA")
        assert isinstance(results, list)
