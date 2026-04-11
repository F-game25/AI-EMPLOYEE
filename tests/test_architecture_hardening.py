"""Architecture hardening tests — edge cases, contract enforcement, layer boundaries."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_RUNTIME = Path(__file__).parent.parent / "runtime"
for _p in [str(_RUNTIME)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ─────────────────────────────────────────────────────────────────────────────
# TaskGraph — circular dependency detection
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskGraphIntegrity:
    def test_validate_no_cycles_passes_for_linear_chain(self):
        from core.contracts import TaskGraph, TaskNode

        t1 = TaskNode(task_id="t1", skill="a", input={"goal": "x"})
        t2 = TaskNode(task_id="t2", skill="b", input={"goal": "x"}, dependencies=["t1"])
        graph = TaskGraph(run_id="r1", goal="x", tasks=[t1, t2])
        graph.validate_no_cycles()  # must not raise

    def test_validate_no_cycles_raises_for_self_loop(self):
        from core.contracts import TaskGraph, TaskNode

        t1 = TaskNode(task_id="t1", skill="a", input={"goal": "x"}, dependencies=["t1"])
        graph = TaskGraph(run_id="r1", goal="x", tasks=[t1])
        with pytest.raises(ValueError, match="circular"):
            graph.validate_no_cycles()

    def test_validate_no_cycles_raises_for_two_node_cycle(self):
        from core.contracts import TaskGraph, TaskNode

        t1 = TaskNode(task_id="t1", skill="a", input={"goal": "x"}, dependencies=["t2"])
        t2 = TaskNode(task_id="t2", skill="b", input={"goal": "x"}, dependencies=["t1"])
        graph = TaskGraph(run_id="r1", goal="x", tasks=[t1, t2])
        with pytest.raises(ValueError, match="circular"):
            graph.validate_no_cycles()

    def test_validate_no_cycles_raises_for_unknown_dependency(self):
        from core.contracts import TaskGraph, TaskNode

        t1 = TaskNode(task_id="t1", skill="a", input={"goal": "x"}, dependencies=["ghost"])
        graph = TaskGraph(run_id="r1", goal="x", tasks=[t1])
        with pytest.raises(ValueError, match="unknown task"):
            graph.validate_no_cycles()


# ─────────────────────────────────────────────────────────────────────────────
# Executor — fail-fast on invalid graph
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutorFailFast:
    def _make_executor(self, tmp_path: Path):
        os.environ["AI_HOME"] = str(tmp_path)
        from analytics.structured_logger import StructuredLogger
        from core.executor import Executor
        from security.policy import SecurityPolicy
        from skills.catalog import SkillCatalog

        logger = StructuredLogger(log_path=tmp_path / "ops.jsonl")
        return Executor(
            skills=SkillCatalog(),
            policy=SecurityPolicy(),
            logger=logger,
            action_emitter=lambda action, payload: {"status": "executed", "action_id": "x"},
        )

    def test_execute_graph_raises_on_cycle(self, tmp_path):
        from core.contracts import TaskGraph, TaskNode

        executor = self._make_executor(tmp_path)
        t1 = TaskNode(task_id="t1", skill="x", input={"goal": "g"}, dependencies=["t1"])
        graph = TaskGraph(run_id="r", goal="g", tasks=[t1])
        with pytest.raises(ValueError, match="circular"):
            executor.execute_graph(graph)


# ─────────────────────────────────────────────────────────────────────────────
# SecurityPolicy — input and output contract enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestSecurityPolicyContracts:
    def test_validate_task_input_raises_on_missing_required_field(self):
        from security.policy import SecurityPolicy

        policy = SecurityPolicy()
        with pytest.raises(ValueError, match="missing required input fields"):
            policy.validate_task_input({"other": "x"}, required_keys=["goal"])

    def test_validate_task_input_raises_on_non_dict(self):
        from security.policy import SecurityPolicy

        policy = SecurityPolicy()
        with pytest.raises(ValueError, match="JSON object"):
            policy.validate_task_input("not a dict", required_keys=[])

    def test_validate_output_raises_on_missing_required_key(self):
        from security.policy import SecurityPolicy

        policy = SecurityPolicy()
        with pytest.raises(ValueError, match="skill output missing required fields"):
            policy.validate_output({"action_result": {}}, required_keys=["status"])

    def test_validate_output_raises_on_non_dict(self):
        from security.policy import SecurityPolicy

        policy = SecurityPolicy()
        with pytest.raises(ValueError, match="JSON object"):
            policy.validate_output("bad", required_keys=["status"])

    def test_validate_output_passes_when_keys_present(self):
        from security.policy import SecurityPolicy

        policy = SecurityPolicy()
        policy.validate_output({"status": "ok"}, required_keys=["status"])

    def test_ensure_action_allowed_raises_for_unknown_action(self):
        from security.policy import SecurityPolicy

        policy = SecurityPolicy()
        with pytest.raises(PermissionError, match="not allowed"):
            policy.ensure_action_allowed(
                action="destroy_database",
                allowed_actions=["skill_dispatch"],
                skill_name="test-skill",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Skill system — version and capability_tags declared
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillMetadata:
    def test_all_catalog_skills_have_version(self):
        from skills.catalog import SkillCatalog

        catalog = SkillCatalog()
        for name, skill in catalog.all().items():
            assert skill.version, f"skill '{name}' missing version"

    def test_all_catalog_skills_have_capability_tags(self):
        from skills.catalog import SkillCatalog

        catalog = SkillCatalog()
        for name, skill in catalog.all().items():
            assert isinstance(skill.capability_tags, list), (
                f"skill '{name}' capability_tags must be a list"
            )
            assert len(skill.capability_tags) > 0, (
                f"skill '{name}' must declare at least one capability tag"
            )

    def test_skill_output_schema_has_required_field(self):
        from skills.catalog import SkillCatalog

        catalog = SkillCatalog()
        skill = catalog.get("problem-solver")
        assert "required" in skill.output_schema
        assert "status" in skill.output_schema["required"]

    def test_skill_is_stateless_no_shared_class_state(self):
        """Two separate catalog instances must not share skill state."""
        from skills.catalog import SkillCatalog

        c1 = SkillCatalog()
        c2 = SkillCatalog()
        s1 = c1.get("problem-solver")
        s2 = c2.get("problem-solver")
        assert s1 is not s2


# ─────────────────────────────────────────────────────────────────────────────
# Validator — structured logging
# ─────────────────────────────────────────────────────────────────────────────

class TestValidatorLogging:
    def test_validator_logs_passed_event(self, tmp_path):
        from analytics.structured_logger import StructuredLogger
        from core.contracts import TaskNode
        from core.validator import Validator

        logger = StructuredLogger(log_path=tmp_path / "ops.jsonl")
        validator = Validator(logger=logger)
        task = TaskNode(
            task_id="t1",
            skill="problem-solver",
            input={"goal": "x"},
            status="success",
            output={"status": "success"},
            attempts=1,
        )
        verdict = validator.validate(task)
        assert verdict.passed
        events = logger.recent()
        assert any(e["component"] == "validator" for e in events)
        assert any(e["result"] == "passed" for e in events)

    def test_validator_logs_failed_event(self, tmp_path):
        from analytics.structured_logger import StructuredLogger
        from core.contracts import TaskNode
        from core.validator import Validator

        logger = StructuredLogger(log_path=tmp_path / "ops.jsonl")
        validator = Validator(logger=logger)
        task = TaskNode(
            task_id="t2",
            skill="problem-solver",
            input={"goal": "x"},
            status="failed",
            error="intentional",
            attempts=3,
        )
        verdict = validator.validate(task)
        assert not verdict.passed
        assert verdict.score == 0.0
        events = logger.recent()
        assert any(e["result"] == "failed" for e in events)


# ─────────────────────────────────────────────────────────────────────────────
# Planner — logs planning and validates graph
# ─────────────────────────────────────────────────────────────────────────────

class TestPlannerLogging:
    def test_planner_logs_plan_event(self, tmp_path):
        from analytics.structured_logger import StructuredLogger
        from core.planner import Planner

        logger = StructuredLogger(log_path=tmp_path / "ops.jsonl")
        planner = Planner(logger=logger)
        planner.plan(goal="publish a post", run_id="r1")
        events = logger.recent()
        assert any(e["component"] == "planner" for e in events)

    def test_planner_classifies_analytics_goal(self):
        from core.planner import Planner

        p = Planner()
        assert p.classify_goal("Analyze the business report") == "analytics"

    def test_planner_classifies_general_goal(self):
        from core.planner import Planner

        p = Planner()
        assert p.classify_goal("Do something") == "general"


# ─────────────────────────────────────────────────────────────────────────────
# ActionBus — injected mode_checker removes upward layer dependency
# ─────────────────────────────────────────────────────────────────────────────

class TestActionBusInjection:
    def test_injected_mode_checker_governs_approval(self):
        from actions.action_bus import ActionBus

        bus = ActionBus(mode_checker=lambda: True)  # always require approval
        result = bus.emit("test_action", {"x": 1})
        assert result["status"] == "pending_approval"

    def test_injected_mode_checker_auto_executes(self):
        from actions.action_bus import ActionBus

        bus = ActionBus(mode_checker=lambda: False)  # never require approval
        result = bus.emit("test_action", {"x": 1})
        assert result["status"] == "executed"

    def test_injected_audit_func_is_called(self):
        from actions.action_bus import ActionBus

        audit_calls: list[tuple] = []

        def audit(actor, action_type, reason, before, after, outcome):
            audit_calls.append((actor, action_type, outcome))

        bus = ActionBus(mode_checker=lambda: False, audit_func=audit)
        bus.emit("audit_test", {"k": "v"}, actor="tester")
        assert len(audit_calls) == 1
        assert audit_calls[0][1] == "audit_test"

    def test_approve_calls_audit_with_injected_func(self):
        from actions.action_bus import ActionBus

        audit_calls: list[tuple] = []

        def audit(actor, action_type, reason, before, after, outcome):
            audit_calls.append((actor, action_type, outcome))

        bus = ActionBus(mode_checker=lambda: True, audit_func=audit)
        result = bus.emit("pending_action", {})
        action_id = result["action_id"]
        bus.approve(action_id)
        outcomes = [c[2] for c in audit_calls]
        assert "approved" in outcomes

    def test_reject_calls_audit_with_injected_func(self):
        from actions.action_bus import ActionBus

        audit_calls: list[tuple] = []

        def audit(actor, action_type, reason, before, after, outcome):
            audit_calls.append((actor, action_type, outcome))

        bus = ActionBus(mode_checker=lambda: True, audit_func=audit)
        result = bus.emit("reject_action", {})
        action_id = result["action_id"]
        bus.reject(action_id)
        outcomes = [c[2] for c in audit_calls]
        assert "rejected" in outcomes


# ─────────────────────────────────────────────────────────────────────────────
# AgentController — silent failures are logged not swallowed
# ─────────────────────────────────────────────────────────────────────────────

class TestControllerObservability:
    def test_controller_logs_strategy_fallback(self, tmp_path):
        """_best_strategies failures must produce a log event, not silently return []."""
        os.environ["AI_HOME"] = str(tmp_path)
        from analytics.structured_logger import StructuredLogger
        from core.agent_controller import AgentController
        from core.planner import Planner

        logger = StructuredLogger(log_path=tmp_path / "ops.jsonl")

        def bad_strategy_store():
            raise RuntimeError("store unavailable")

        planner = Planner(logger=logger)
        controller = AgentController(planner=planner, logger=logger)

        # Patch strategy store to fail
        import memory.strategy_store as ss_mod
        original = ss_mod._instance
        try:
            ss_mod._instance = None
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(ss_mod, "get_strategy_store", bad_strategy_store)
                result = controller._best_strategies("general goal")
        finally:
            ss_mod._instance = original

        assert result == []
        events = logger.recent()
        assert any(e["action"] == "best_strategies" and e["result"] == "fallback" for e in events)
