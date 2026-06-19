"""Tests for runtime/core/orchestrator_v2.py — OrchestratorV2."""
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Add runtime to path FIRST so 'core' resolves to the real package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runtime"))

# Stub modules this test newly injects into sys.modules. Tracked so tearDownModule
# can remove them — otherwise an empty stub (e.g. core.execution_engine) leaks and
# breaks later tests that import the real module ("cannot import name ... unknown location").
_INJECTED_MODULES: list[str] = []


def _inject_stubs():
    """Inject minimal stubs so OrchestratorV2 can be imported without the full runtime."""
    # core.orchestrator — get_llm_client
    import core  # real package
    orch_mod = sys.modules.get("core.orchestrator")
    if orch_mod is None:
        orch_mod = types.ModuleType("core.orchestrator")
        sys.modules["core.orchestrator"] = orch_mod
        _INJECTED_MODULES.append("core.orchestrator")
    llm_stub = MagicMock()
    llm_stub.complete.return_value = {"output": '{"category": "ops", "urgency": 3}'}
    orch_mod.get_llm_client = MagicMock(return_value=llm_stub)
    if not hasattr(orch_mod, "INTENT_CATEGORIES"):
        orch_mod.INTENT_CATEGORIES = ("lead_gen", "content", "social", "research", "email", "support", "finance", "ops")
    if not hasattr(orch_mod, "LLMClient"):
        orch_mod.LLMClient = MagicMock

    # NOTE: core.execution_engine is intentionally NOT stubbed. OrchestratorV2
    # imports it inside a try/except (see _execute_steps), so it never needs a stub,
    # and an empty stub here leaks into sys.modules and breaks test_execution_engine_qce
    # ("cannot import name 'ExecutionEngine' ... unknown location").
    for name in ["core.knowledge_store", "core.memory_index", "core.model_routing",
                 "core.hitl_gate", "core.bus",
                 "core.observability.metrics_collector", "core.observability"]:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
            _INJECTED_MODULES.append(name)

    # core.bus — get_message_bus
    bus_mod = sys.modules["core.bus"]
    bus_stub = MagicMock()
    bus_stub.publish_sync = MagicMock()
    bus_mod.get_message_bus = MagicMock(return_value=bus_stub)

    # core.observability.metrics_collector — get_metrics_collector
    mc_mod = sys.modules["core.observability.metrics_collector"]
    mc_stub = MagicMock()
    mc_stub.increment = MagicMock()
    mc_mod.get_metrics_collector = MagicMock(return_value=mc_stub)


_inject_stubs()

from core.orchestrator_v2 import OrchestratorV2, _PipelineAbort  # noqa: E402


def tearDownModule():
    """Remove stub modules this test injected so later tests import the real ones."""
    for name in _INJECTED_MODULES:
        sys.modules.pop(name, None)
    _INJECTED_MODULES.clear()


class TestOrchestratorV2Init(unittest.TestCase):
    def test_instantiates(self):
        o = OrchestratorV2()
        self.assertIsNotNone(o)

    def test_has_llm_client(self):
        o = OrchestratorV2()
        self.assertIsNotNone(o._llm)


class TestOrchestratorV2Run(unittest.TestCase):
    def setUp(self):
        self.orch = OrchestratorV2()

    def test_run_returns_dict_with_required_keys(self):
        result = self.orch.run("test goal")
        for key in ("success", "result", "phases_completed", "errors", "task_id"):
            self.assertIn(key, result)

    def test_task_id_has_prefix(self):
        result = self.orch.run("hello")
        self.assertTrue(result["task_id"].startswith("ov2-"))

    def test_classify_intent_defaults_on_bad_llm(self):
        # LLM returns non-JSON — should gracefully default to 'ops'
        self.orch._llm.complete.return_value = {"output": "not json"}
        ctx = {"goal": "do something", "tenant_id": "default"}
        self.orch._classify_intent(ctx)
        self.assertEqual(ctx["intent"], "ops")
        self.assertEqual(ctx["urgency"], 3)

    def test_run_with_empty_goal_still_completes(self):
        result = self.orch.run("")
        self.assertIn("task_id", result)

    def test_phases_completed_is_list(self):
        result = self.orch.run("some task")
        self.assertIsInstance(result["phases_completed"], list)

    def test_pipeline_abort_returns_failure(self):
        def _bad_classify(ctx):
            raise _PipelineAbort("budget exceeded")
        self.orch._classify_intent = _bad_classify
        result = self.orch.run("goal")
        self.assertFalse(result["success"])
        self.assertIn("classify_intent", result["errors"])


if __name__ == "__main__":
    unittest.main()
