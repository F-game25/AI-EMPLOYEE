"""Agent system tests.

Validates that agent controllers, orchestrators, and agent execution
pipelines work correctly.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"

# Ensure runtime is on the path
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))


# ---------------------------------------------------------------------------
# Test: Agent controller can be imported and instantiated
# ---------------------------------------------------------------------------

class TestAgentController:
    """Verify the AgentController architecture."""

    def test_agent_controller_importable(self) -> None:
        from core.agent_controller import AgentController
        assert AgentController is not None

    def test_agent_controller_has_planner(self) -> None:
        from core.agent_controller import AgentController
        ac = AgentController()
        assert hasattr(ac, "planner")

    def test_agent_controller_has_executor(self) -> None:
        from core.agent_controller import AgentController
        ac = AgentController()
        assert hasattr(ac, "executor")

    def test_agent_controller_has_validator(self) -> None:
        from core.agent_controller import AgentController
        ac = AgentController()
        assert hasattr(ac, "validator")

    def test_agent_controller_has_brain(self) -> None:
        from core.agent_controller import AgentController
        ac = AgentController()
        assert hasattr(ac, "brain")


# ---------------------------------------------------------------------------
# Test: Orchestrator intent classification
# ---------------------------------------------------------------------------

class TestOrchestrator:
    """Verify orchestrator is importable and has expected categories."""

    def test_orchestrator_importable(self) -> None:
        from core.orchestrator import INTENT_CATEGORIES
        assert isinstance(INTENT_CATEGORIES, tuple)
        assert len(INTENT_CATEGORIES) > 0

    def test_orchestrator_has_expected_intents(self) -> None:
        from core.orchestrator import INTENT_CATEGORIES
        for intent in ("lead_gen", "content", "email", "research"):
            assert intent in INTENT_CATEGORIES, f"Missing intent: {intent}"

    def test_llm_client_importable(self) -> None:
        from core.orchestrator import LLMClient
        client = LLMClient()
        assert hasattr(client, "complete")
        assert hasattr(client, "backend")


# ---------------------------------------------------------------------------
# Test: Planner, Executor, Validator modules
# ---------------------------------------------------------------------------

class TestPlannerExecutorValidator:
    """Verify the core pipeline components exist and are constructable."""

    def test_planner_importable(self) -> None:
        from core.planner import Planner
        p = Planner()
        assert p is not None

    def test_executor_importable(self) -> None:
        from core.executor import Executor
        assert Executor is not None

    def test_validator_importable(self) -> None:
        from core.validator import Validator
        v = Validator()
        assert v is not None


# ---------------------------------------------------------------------------
# Test: Task contracts and graph data structures
# ---------------------------------------------------------------------------

class TestContracts:
    """Verify task graph data structures."""

    def test_task_node_importable(self) -> None:
        from core.contracts import TaskNode
        assert TaskNode is not None

    def test_task_graph_importable(self) -> None:
        from core.contracts import TaskGraph
        assert TaskGraph is not None


# ---------------------------------------------------------------------------
# Test: Skill catalog
# ---------------------------------------------------------------------------

class TestSkillCatalog:
    """Verify the skill catalog can be loaded."""

    def test_skill_catalog_importable(self) -> None:
        from skills.catalog import SkillCatalog, get_skill_catalog
        catalog = get_skill_catalog()
        assert catalog is not None

    def test_skill_catalog_has_list(self) -> None:
        from skills.catalog import get_skill_catalog
        catalog = get_skill_catalog()
        # Should be able to list skills
        assert hasattr(catalog, "list_skills") or hasattr(catalog, "skills") or hasattr(catalog, "get")


# ---------------------------------------------------------------------------
# Test: Worker pool
# ---------------------------------------------------------------------------

class TestWorkerPool:
    """Verify the worker pool module."""

    def test_worker_pool_module_importable(self) -> None:
        import core.worker_pool
        assert hasattr(core.worker_pool, "main")


# ---------------------------------------------------------------------------
# Test: Brain registry
# ---------------------------------------------------------------------------

class TestBrainRegistry:
    """Verify the brain registry is accessible."""

    def test_brain_registry_importable(self) -> None:
        from core.brain_registry import brain
        assert brain is not None


# ---------------------------------------------------------------------------
# Test: Bus / event system
# ---------------------------------------------------------------------------

class TestMessageBus:
    """Verify the internal message bus."""

    def test_bus_importable(self) -> None:
        from core.bus import get_message_bus
        bus = get_message_bus()
        assert bus is not None

    def test_bus_has_publish(self) -> None:
        from core.bus import get_message_bus
        bus = get_message_bus()
        assert hasattr(bus, "publish") or hasattr(bus, "emit") or hasattr(bus, "send")


# ---------------------------------------------------------------------------
# Test: Research agent
# ---------------------------------------------------------------------------

class TestResearchAgent:
    """Verify the research agent module."""

    def test_research_agent_importable(self) -> None:
        from core.research_agent import ResearchAgent
        agent = ResearchAgent()
        assert agent is not None
