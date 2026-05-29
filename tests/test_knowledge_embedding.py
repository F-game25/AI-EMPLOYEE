"""Integration tests for KnowledgeStore.embed_entries_to_vector_store().

Verifies:
- Entries from knowledge_store.json are embedded into the vector store
- The count of newly embedded entries is returned correctly
- The method is idempotent (re-running with the same entries returns 0)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolate_stores(tmp_path, monkeypatch):
    """Redirect STATE_DIR and AI_HOME; reset singletons for store isolation."""
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AI_HOME", str(tmp_path))

    # Reset module-level singletons so each test starts fresh.
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

    # Teardown: reset again to avoid state leaking into later tests.
    for mod_name in ("core.knowledge_store", "memory.vector_store"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            mod._instance = None


@pytest.fixture()
def sample_entries():
    return [
        {
            "id": "test1",
            "title": "Test Topic",
            "content": "Test content about machine learning and AI systems.",
            "tags": ["test", "ml"],
        },
        {
            "id": "test2",
            "title": "Second Topic",
            "content": "Information about ecommerce and sales pipelines.",
            "tags": ["sales", "ecommerce"],
        },
        {
            "id": "test3",
            "title": "Third Topic",
            "content": "Details about deployment, CI/CD, and observability.",
            "tags": ["devops"],
        },
    ]


@pytest.fixture()
def knowledge_store_path(isolate_stores, sample_entries):
    """Write a knowledge_store.json with 3 entries and return its path."""
    ks_path = isolate_stores / "knowledge_store.json"
    ks_path.write_text(
        json.dumps({"entries": sample_entries}, indent=2),
        encoding="utf-8",
    )
    return ks_path


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestEmbedEntriesToVectorStore:

    def test_returns_positive_count(self, knowledge_store_path):
        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store(knowledge_store_path)
        count = ks.embed_entries_to_vector_store()
        assert isinstance(count, int)
        assert count > 0

    def test_embeds_all_three_entries(self, knowledge_store_path):
        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store(knowledge_store_path)
        count = ks.embed_entries_to_vector_store()
        assert count == 3

    def test_vector_store_count_increases(self, knowledge_store_path):
        from core.knowledge_store import get_knowledge_store
        from memory.vector_store import get_vector_store

        vs = get_vector_store()
        before = vs.count()

        ks = get_knowledge_store(knowledge_store_path)
        ks.embed_entries_to_vector_store()

        after = vs.count()
        assert after > before

    def test_idempotent_second_call_returns_zero(self, knowledge_store_path):
        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store(knowledge_store_path)

        first_count = ks.embed_entries_to_vector_store()
        assert first_count == 3

        # Second call with identical entries — all keys already indexed
        second_count = ks.embed_entries_to_vector_store()
        assert second_count == 0

    def test_idempotent_does_not_inflate_vector_store(self, knowledge_store_path):
        from core.knowledge_store import get_knowledge_store
        from memory.vector_store import get_vector_store

        ks = get_knowledge_store(knowledge_store_path)
        ks.embed_entries_to_vector_store()

        vs = get_vector_store()
        count_after_first = vs.count()

        ks.embed_entries_to_vector_store()
        count_after_second = vs.count()

        assert count_after_first == count_after_second

    def test_empty_entries_returns_zero(self, isolate_stores):
        ks_path = isolate_stores / "knowledge_store.json"
        ks_path.write_text(json.dumps({"entries": []}), encoding="utf-8")

        from core.knowledge_store import get_knowledge_store
        ks = get_knowledge_store(ks_path)
        assert ks.embed_entries_to_vector_store() == 0

    def test_entries_keyed_with_ks_prefix_in_vector_store(self, knowledge_store_path):
        """Entries are stored with 'ks:<id>' keys in the vector store."""
        from core.knowledge_store import get_knowledge_store
        from memory.vector_store import get_vector_store

        ks = get_knowledge_store(knowledge_store_path)
        ks.embed_entries_to_vector_store()

        vs = get_vector_store()
        entry = vs.retrieve("ks:test1")
        assert entry is not None
        assert "Test Topic" in entry["text"]

    def test_new_entry_added_after_first_embed(self, knowledge_store_path, isolate_stores):
        """Adding a new entry after initial embed should embed only the new one."""
        from core.knowledge_store import get_knowledge_store

        ks = get_knowledge_store(knowledge_store_path)
        first_count = ks.embed_entries_to_vector_store()
        assert first_count == 3

        # Append a 4th entry to the file
        ks_data = json.loads(knowledge_store_path.read_text())
        ks_data["entries"].append({
            "id": "test4",
            "title": "New Entry",
            "content": "Brand new content added later.",
            "tags": ["new"],
        })
        knowledge_store_path.write_text(json.dumps(ks_data), encoding="utf-8")

        second_count = ks.embed_entries_to_vector_store()
        assert second_count == 1
