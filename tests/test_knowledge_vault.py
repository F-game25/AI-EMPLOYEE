"""Tests for runtime/memory/knowledge_vault.py — KnowledgeVault."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runtime"))
from memory.knowledge_vault import (  # noqa: E402
    KnowledgeVault, STATUS_PENDING, STATUS_VERIFIED, STATUS_REJECTED, _slug
)


class TestSlugHelper(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(_slug("Hello World"), "hello-world")

    def test_strips_special_chars(self):
        self.assertNotIn("!", _slug("What is AI?!"))

    def test_max_length(self):
        self.assertLessEqual(len(_slug("x" * 200)), 120)


class TestKnowledgeVaultInstantiation(unittest.TestCase):
    def test_instantiates_with_temp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            vault = KnowledgeVault(vault_dir=d)
            self.assertTrue(os.path.isdir(d))


class TestKnowledgeVaultCRUD(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.vault = KnowledgeVault(vault_dir=self.tmpdir)

    def test_add_entry_returns_slug(self):
        slug = self.vault.add_entry("AI Basics", "AI stands for Artificial Intelligence", "test")
        self.assertIsInstance(slug, str)
        self.assertGreater(len(slug), 0)

    def test_get_entry_returns_dict(self):
        self.vault.add_entry("Machine Learning", "ML is a subset of AI", "wiki")
        entry = self.vault.get_entry("Machine Learning")
        self.assertEqual(entry["title"], "Machine Learning")
        self.assertIn("content", entry)
        self.assertIn("confidence", entry)

    def test_get_entry_missing_returns_empty(self):
        result = self.vault.get_entry("Nonexistent Topic")
        self.assertEqual(result, {})

    def test_search_finds_by_title(self):
        self.vault.add_entry("Python Language", "Python is a programming language", "docs")
        results = self.vault.search("python")
        self.assertGreater(len(results), 0)
        titles = [r["title"] for r in results]
        self.assertIn("Python Language", titles)

    def test_search_empty_query_returns_results(self):
        self.vault.add_entry("Topic A", "Some content", "src")
        # Empty query should not crash
        results = self.vault.search("")
        self.assertIsInstance(results, list)

    def test_list_all_returns_entries(self):
        self.vault.add_entry("Entry 1", "body1", "src")
        self.vault.add_entry("Entry 2", "body2", "src")
        all_entries = self.vault.list_all()
        self.assertEqual(len(all_entries), 2)

    def test_mark_verified_updates_status(self):
        self.vault.add_entry("Verified Topic", "content", "src")
        self.vault.mark_verified("Verified Topic")
        entry = self.vault.get_entry("Verified Topic")
        self.assertEqual(entry["status"], STATUS_VERIFIED)

    def test_mark_rejected_updates_status(self):
        self.vault.add_entry("Bad Topic", "content", "src")
        self.vault.mark_rejected("Bad Topic")
        entry = self.vault.get_entry("Bad Topic")
        self.assertEqual(entry["status"], STATUS_REJECTED)

    def test_list_pending_review(self):
        self.vault.add_entry("Pending Entry", "stuff", "src")
        pending = self.vault.list_pending_review()
        titles = [p["title"] for p in pending]
        self.assertIn("Pending Entry", titles)

    def test_update_confidence_increases(self):
        self.vault.add_entry("Conf Test", "body", "src", confidence=0.5)
        self.vault.update_confidence("Conf Test", 0.1)
        entry = self.vault.get_entry("Conf Test")
        self.assertAlmostEqual(entry["confidence"], 0.6, places=2)

    def test_update_confidence_clamps_to_1(self):
        self.vault.add_entry("Max Conf", "body", "src", confidence=0.95)
        self.vault.update_confidence("Max Conf", 0.5)
        entry = self.vault.get_entry("Max Conf")
        self.assertLessEqual(entry["confidence"], 1.0)

    def test_wikilinks_tracked(self):
        self.vault.add_entry("ML Guide", "See [[Python Language]] for details", "src")
        entry = self.vault.get_entry("ML Guide")
        self.assertIn("Python Language", entry.get("wikilinks", []))

    def test_backlinks_tracked(self):
        self.vault.add_entry("Source", "References [[Target Topic]]", "src")
        backlinks = self.vault.get_backlinks("Target Topic")
        self.assertIn(_slug("Source"), backlinks)

    def test_export_context_returns_string(self):
        self.vault.add_entry("Export Me", "content here", "src")
        ctx = self.vault.export_context(["Export Me"])
        self.assertIsInstance(ctx, str)
        self.assertIn("Export Me", ctx)

    def test_prune_low_confidence_removes_old_entries(self):
        # Add entry with very low confidence
        self.vault.add_entry("Stale Entry", "old stuff", "src", confidence=0.1)
        # Manually backdate the entry by forcing old timestamp in index
        import json
        from datetime import datetime, timezone, timedelta
        idx = self.vault._load_index()
        slug = _slug("Stale Entry")
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        idx["entries"][slug]["updated"] = old_ts
        self.vault._save_index(idx)
        # Also update file's updated field
        path = self.vault._entry_path(slug)
        raw = path.read_text(encoding='utf-8')
        raw = raw.replace(idx["entries"][slug].get("created", ""), old_ts)
        # Write a fresh frontmatter with old date
        from memory.knowledge_vault import _parse_frontmatter, _render_frontmatter
        meta, body = _parse_frontmatter(path.read_text(encoding='utf-8'))
        meta['updated'] = old_ts
        path.write_text(_render_frontmatter(meta) + f'\n{body}\n', encoding='utf-8')

        removed = self.vault.prune_low_confidence(threshold=0.3, older_than_days=7)
        self.assertGreaterEqual(removed, 1)


if __name__ == "__main__":
    unittest.main()
