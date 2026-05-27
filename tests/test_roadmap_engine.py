"""Tests for runtime/core/roadmap_engine.py — RoadmapEngine."""
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

# Stub heavy deps before import
for _mod in ["engine.api", "engine", "core.agent_controller"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runtime"))
from core.roadmap_engine import RoadmapEngine, Roadmap, Milestone, Task, get_roadmap_engine  # noqa: E402


class TestRoadmapEngineInstantiation(unittest.TestCase):
    def test_instantiates(self):
        self.assertIsNotNone(RoadmapEngine())

    def test_singleton_returns_same_instance(self):
        a = get_roadmap_engine()
        b = get_roadmap_engine()
        self.assertIs(a, b)


class TestCreateRoadmap(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["STATE_DIR"] = self.tmpdir
        self.engine = RoadmapEngine()

    def tearDown(self):
        os.environ.pop("STATE_DIR", None)

    def test_create_returns_roadmap(self):
        rm = self.engine.create_roadmap("Launch a product", "tenant1")
        self.assertIsInstance(rm, Roadmap)
        self.assertEqual(rm.tenant_id, "tenant1")
        self.assertEqual(rm.status, "draft")

    def test_create_persists_to_disk(self):
        rm = self.engine.create_roadmap("Grow revenue", "t1")
        path = self.engine._path(rm.id)
        self.assertTrue(path.exists())

    def test_get_roadmap_returns_saved(self):
        rm = self.engine.create_roadmap("Build team", "t1")
        loaded = self.engine.get_roadmap(rm.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.goal, "Build team")

    def test_get_roadmap_missing_returns_none(self):
        self.assertIsNone(self.engine.get_roadmap("nonexistent-id"))

    def test_list_roadmaps_filters_by_tenant(self):
        self.engine.create_roadmap("Goal A", "tenantA")
        self.engine.create_roadmap("Goal B", "tenantB")
        results = self.engine.list_roadmaps("tenantA")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].goal, "Goal A")

    def test_roadmap_status_ok(self):
        rm = self.engine.create_roadmap("Check status", "t1")
        status = self.engine.roadmap_status(rm.id)
        self.assertTrue(status["ok"])
        self.assertEqual(status["id"], rm.id)

    def test_roadmap_status_not_found(self):
        status = self.engine.roadmap_status("bad-id")
        self.assertFalse(status["ok"])

    def test_stub_milestones_returns_list(self):
        stubs = RoadmapEngine._stub_milestones("test goal")
        self.assertIsInstance(stubs, list)
        self.assertGreater(len(stubs), 0)
        self.assertIsInstance(stubs[0], Milestone)

    def test_generate_milestones_falls_back_on_no_llm(self):
        rm = self.engine.create_roadmap("Fallback goal", "t1")
        with patch.object(RoadmapEngine, "_llm_generate", return_value=None):
            rm = self.engine.generate_milestones(rm)
        self.assertIsInstance(rm.milestones, list)
        self.assertEqual(rm.status, "active")


if __name__ == "__main__":
    unittest.main()
