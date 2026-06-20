from __future__ import annotations

import sys
from pathlib import Path

_RUNTIME = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from core.memory_index import MemoryIndex


def test_memory_ranking_and_feedback(tmp_path):
    idx = MemoryIndex(path=tmp_path / "memory_index.json")
    idx.add_memory("ecommerce strategy for growth", importance=0.6)
    idx.add_memory("generic note", importance=0.2)

    relevant = idx.get_relevant_memories("ecommerce marketing", top_k=1)
    assert len(relevant) == 1
    top = relevant[0]
    assert "ecommerce" in top["text"]
    before = top["importance"]

    idx.apply_feedback(relevant, 1.0)
    refreshed = idx.get_relevant_memories("ecommerce marketing", top_k=1)[0]
    assert refreshed["importance"] >= before
    assert refreshed["usage_count"] >= 1


def test_memory_decay_reduces_importance(tmp_path):
    idx = MemoryIndex(path=tmp_path / "memory_index.json")
    idx.add_memory("old memory", importance=1.0)
    snapshot = idx.snapshot()
    snapshot[0]["last_used"] = "2000-01-01T00:00:00Z"
    idx._memories = snapshot  # controlled test fixture state
    idx.apply_decay()
    decayed = idx.snapshot()[0]
    assert decayed["importance"] < 1.0


def test_memory_index_writes_unified_store(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    idx = MemoryIndex(path=tmp_path / "state" / "memory_index.json")

    stored = idx.add_memory("premium command center status memory", importance=0.8)

    from memory.unified_store import UnifiedMemoryStore

    unified = UnifiedMemoryStore(path=tmp_path / "state" / "memory" / "unified_memory.json")
    record = unified.get(stored["id"])
    assert record is not None
    assert record.memory_type == "long_term"
    assert record.source == "memory_index"

    results = idx.get_relevant_memories("command center status", top_k=3)
    assert any(row["id"] == stored["id"] for row in results)

    before = record.importance
    idx.apply_feedback([stored], 1.0)
    refreshed = unified.get(stored["id"])
    assert refreshed is not None
    assert refreshed.importance >= before
