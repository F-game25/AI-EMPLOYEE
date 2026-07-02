"""Tests for runtime/tools/registry.py — ToolRegistry and module-level helpers."""
import os
import sys
import types
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Stub out sub-imports before loading registry
for _mod in ["tools.web_research_tool", "tools.context_score_tool",
             "core.orchestrator", "core.embeddings", "memory.memory_router"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runtime"))
from tools.registry import (  # noqa: E402
    ToolRegistry, register_tool, list_tools, call_tool, get_tool_registry
)


class TestModuleLevelRegistry(unittest.TestCase):
    def test_register_and_list(self):
        fn = lambda d: {"ok": True}  # noqa: E731
        register_tool(name="_test_tool", description="test", call=fn)
        names = [t["name"] for t in list_tools()]
        self.assertIn("_test_tool", names)

    def test_call_tool_known(self):
        fn = lambda d: {"value": d.get("x", 0) * 2}  # noqa: E731
        register_tool(name="_double", description="double x", call=fn)
        result = call_tool("_double", {"x": 5})
        self.assertEqual(result.get("value"), 10)

    def test_call_tool_unknown_returns_error(self):
        result = call_tool("__nonexistent__", {})
        self.assertEqual(result["status"], "error")
        self.assertIn("unknown tool", result["error"])

    def test_list_tools_excludes_call_key(self):
        fn = lambda d: {}  # noqa: E731
        register_tool(name="_no_call_exposed", description="x", call=fn)
        for t in list_tools():
            self.assertNotIn("call", t)


class TestToolRegistryClass(unittest.TestCase):
    def setUp(self):
        # Fresh instance (not singleton) for isolation
        self.reg = ToolRegistry()

    def test_instantiates(self):
        self.assertIsNotNone(self.reg)

    def test_has_default_tools(self):
        tools = self.reg.list_tools()
        names = {t["name"] for t in tools}
        self.assertIn("web_search", names)
        self.assertIn("read_file", names)
        self.assertIn("write_file", names)

    def test_list_tools_max_risk_filters(self):
        all_tools = self.reg.list_tools(max_risk=5)
        risk0_only = self.reg.list_tools(max_risk=0)
        self.assertGreaterEqual(len(all_tools), len(risk0_only))
        for t in risk0_only:
            self.assertEqual(t["risk_level"], 0)

    def test_get_returns_tool_dict(self):
        tool = self.reg.get("read_file")
        self.assertIsNotNone(tool)
        self.assertEqual(tool["name"], "read_file")
        self.assertIn("fn", tool)

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.reg.get("__does_not_exist__"))

    def test_execute_known_tool(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello")
            fname = f.name
        try:
            result = self.reg.execute("read_file", {"path": fname})
            self.assertTrue(result["ok"])
            self.assertIn("hello", result["result"].get("content", ""))
        finally:
            os.unlink(fname)

    def test_execute_missing_tool_returns_error(self):
        result = self.reg.execute("__no_such_tool__", {})
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"])

    def test_execute_read_nonexistent_file(self):
        # Regression: execute() used to report ok=True for a tool that signals
        # failure by returning {"error": ...} instead of raising — a fake
        # success masking a real failure. Fixed to fail closed.
        result = self.reg.execute("read_file", {"path": "/nonexistent/path/file.txt"})
        self.assertFalse(result["ok"])
        self.assertIn("error", result)
        self.assertIn("error", result["result"])

    def test_register_custom_tool(self):
        self.reg.register("_custom_test", lambda x=1: x * 3, 0, "custom")
        tool = self.reg.get("_custom_test")
        self.assertIsNotNone(tool)
        self.assertEqual(tool["risk_level"], 0)

    def test_singleton_get_instance(self):
        a = ToolRegistry.get_instance()
        b = ToolRegistry.get_instance()
        self.assertIs(a, b)

    def test_get_tool_registry_returns_toolregistry(self):
        reg = get_tool_registry()
        self.assertIsInstance(reg, ToolRegistry)


if __name__ == "__main__":
    unittest.main()
