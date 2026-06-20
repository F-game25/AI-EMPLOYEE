"""Tests for NeuralMemoryManager — runs without docker/Neo4j/Ollama."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Hard-skip the module if real embedding/vector libs are missing.
pytest.importorskip("sentence_transformers")
pytest.importorskip("chromadb")

from neural_brain.memory.chroma_adapter import ChromaAdapter
from neural_brain.memory.embedding_provider import EmbeddingProvider
from neural_brain.memory.mem0_adapter import Mem0Adapter
from neural_brain.memory.neural_memory_manager import NeuralMemoryManager


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def embedder():
    return EmbeddingProvider.get()


@pytest.fixture
def chroma(tmp_path: Path, embedder):
    return ChromaAdapter(tmp_path / "chroma", embedder)


@pytest.fixture
def mem0_disabled():
    m = Mem0Adapter.__new__(Mem0Adapter)
    m.memory = None
    m.enabled = False
    m._reason = "disabled-for-tests"
    return m


@pytest.fixture
def unified_store(tmp_path: Path):
    from memory.unified_store import UnifiedMemoryStore
    return UnifiedMemoryStore(path=tmp_path / "state" / "memory" / "unified_memory.json")


@pytest.fixture
def manager(chroma, mem0_disabled, embedder, unified_store):
    return NeuralMemoryManager(
        chroma=chroma,
        mem0=mem0_disabled,
        embedder=embedder,
        graph=None,
        bridge_emit=None,
        reranker=None,
        proxy_legacy=False,
        unified_store=unified_store,
    )


def test_remember_then_recall_roundtrip(manager):
    _run(manager.remember(
        "The Great Pyramid of Giza was built around 2560 BC as a tomb for Pharaoh Khufu.",
        type="semantic",
    ))
    _run(manager.remember(
        "Quantum entanglement allows particles to share state instantaneously across distance.",
        type="semantic",
    ))
    _run(manager.remember(
        "Sourdough bread relies on wild yeast captured from the environment for fermentation.",
        type="semantic",
    ))

    res = _run(manager.recall("Who was the pharaoh buried in the giant pyramid?", k=3))
    assert res.hits, "expected at least one hit"
    top = res.hits[0]
    assert top.score > 0.4, f"top score too low: {top.score}"
    assert "pyramid" in top.text.lower() or "khufu" in top.text.lower()


def test_recall_unrelated_low_score(manager):
    _run(manager.remember(
        "The Great Pyramid of Giza was built around 2560 BC as a tomb for Pharaoh Khufu.",
        type="semantic",
    ))
    res = _run(manager.recall("the price of tea in china", k=3))
    if res.hits:
        assert res.hits[0].score < 0.5, f"unrelated hit score too high: {res.hits[0].score}"


def test_type_filter(manager):
    _run(manager.remember("I had coffee at 8am Tuesday.", type="episodic"))
    _run(manager.remember("Photosynthesis converts light into chemical energy.", type="semantic"))

    res = _run(manager.recall("morning coffee", k=5, types=["episodic"]))
    if res.hits:
        for h in res.hits:
            assert h.type == "episodic" or h.source_store != "chroma"


def test_forget_removes_from_chroma(manager):
    mid = _run(manager.remember("Ephemeral fact about a forgettable widget.", type="semantic"))
    ok = _run(manager.forget(mid))
    assert ok is True
    res = _run(manager.recall("forgettable widget ephemeral", k=5))
    assert all(h.id != mid for h in res.hits)


def test_remember_recall_and_forget_use_unified_store(manager, unified_store):
    mid = _run(manager.remember(
        "Canonical neural memory about premium dashboard orbit status.",
        type="semantic",
        user_id="user-a",
        importance=0.9,
        source="pytest",
    ))

    record = unified_store.get(mid)
    assert record is not None
    assert record.source == "pytest"
    assert record.user_id == "user-a"

    res = _run(manager.recall("premium dashboard orbit", k=5, user_id="user-a"))
    assert any(h.id == mid and h.source_store == "unified" for h in res.hits)

    assert _run(manager.forget(mid)) is True
    assert unified_store.get(mid) is None


def test_stats_health(manager):
    s = manager.stats()
    assert "chroma" in s
    assert "mem0" in s
    assert "embed_dim" in s
    assert s["embed_dim"] > 0
    h = manager.health()
    assert h["chroma"]["ok"] is True
    assert "embedder" in h


def test_emit_called(chroma, mem0_disabled, embedder, unified_store):
    emit = MagicMock()
    mgr = NeuralMemoryManager(
        chroma=chroma,
        mem0=mem0_disabled,
        embedder=embedder,
        graph=None,
        bridge_emit=emit,
        reranker=None,
        proxy_legacy=False,
        unified_store=unified_store,
    )
    _run(mgr.remember("Bridge emit smoke test.", type="semantic"))
    channels = [c.args[0] for c in emit.call_args_list]
    assert "nb:memory_write" in channels
