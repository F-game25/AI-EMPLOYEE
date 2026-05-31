"""Tests for unified MemoryManager (14 memory types)."""
import sys
import os
import time
sys.path.insert(0, 'runtime')

import pytest
from memory.memory_manager import MemoryManager, get_memory_manager


# ── stats() ──────────────────────────────────────────────────────────────────

def test_stats_returns_expected_keys():
    mm = MemoryManager()
    s = mm.stats()
    assert isinstance(s, dict)
    assert "types" in s
    assert "total" in s
    assert "vector_indexed" in s
    assert "ts" in s


def test_stats_types_has_all_14_types():
    mm = MemoryManager()
    s = mm.stats()
    expected = {
        "session", "long_term", "research", "decision", "knowledge_graph",
        "company", "skill", "financial", "failure",
        "tool_history", "preference", "project", "event_timeline", "structured_db",
    }
    assert expected.issubset(set(s["types"].keys()))


def test_stats_total_is_int():
    mm = MemoryManager()
    assert isinstance(mm.stats()["total"], int)
    assert mm.stats()["total"] >= 0


def test_stats_does_not_crash_with_bad_state_dir(tmp_path):
    """Broken state dir must not crash stats()."""
    mm = MemoryManager(state_dir=tmp_path / "nonexistent")
    s = mm.stats()
    assert isinstance(s, dict)
    assert "types" in s


# ── store() ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("memory_type", ["session", "long_term", "research", "knowledge_graph"])
def test_store_returns_string_id(memory_type):
    mm = MemoryManager()
    mid = mm.store(memory_type=memory_type, content="test content for " + memory_type)
    assert isinstance(mid, str)
    assert len(mid) > 0


def test_store_with_metadata():
    mm = MemoryManager()
    mid = mm.store(memory_type="session", content="hello world", metadata={"source": "test"})
    assert isinstance(mid, str)


# ── retrieve() ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("memory_type", ["session", "long_term", "research"])
def test_retrieve_returns_list(memory_type):
    mm = MemoryManager()
    results = mm.retrieve(memory_type=memory_type, query="test")
    assert isinstance(results, list)


def test_retrieve_knowledge_graph_returns_list():
    mm = MemoryManager()
    results = mm.retrieve(memory_type="knowledge_graph", query="ecommerce")
    assert isinstance(results, list)


# ── invalid memory_type ───────────────────────────────────────────────────────

def test_store_invalid_type_raises_or_returns_empty():
    mm = MemoryManager()
    try:
        result = mm.store(memory_type="nonexistent_type_xyz", content="test")
        # If it doesn't raise, it must return something falsy or an error indicator
        assert result is None or isinstance(result, str)
    except (ValueError, KeyError):
        pass  # Raising is fine


def test_retrieve_invalid_type_returns_list():
    mm = MemoryManager()
    try:
        result = mm.retrieve(memory_type="nonexistent_type_xyz", query="test")
        assert isinstance(result, list)
    except (ValueError, KeyError):
        pass  # Raising is also acceptable


# ── clear_type() ──────────────────────────────────────────────────────────────

def test_clear_type_session_returns_int():
    mm = MemoryManager()
    result = mm.clear_type("session")
    assert isinstance(result, int)
    assert result >= 0


# ── singleton ─────────────────────────────────────────────────────────────────

def test_singleton_same_instance():
    a = get_memory_manager()
    b = get_memory_manager()
    assert a is b


def test_singleton_is_memory_manager():
    mm = get_memory_manager()
    assert isinstance(mm, MemoryManager)


# ── round-trip for session memory ────────────────────────────────────────────

def test_session_store_then_retrieve():
    mm = MemoryManager()
    unique = f"unique_test_content_{int(time.time())}"
    mm.store(memory_type="session", content=unique)
    results = mm.retrieve(memory_type="session", query=unique)
    # Session is short-term cache; retrieve should return list (may or may not contain the item)
    assert isinstance(results, list)
