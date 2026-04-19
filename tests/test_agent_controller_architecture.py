from __future__ import annotations

import os
from pathlib import Path


def test_planner_outputs_structured_task_graph():
    from core.planner import Planner

    planner = Planner()
    graph = planner.plan(goal="publish a video", run_id="run1234")
    contract = graph.to_contract()

    assert contract["run_id"] == "run1234"
    assert isinstance(contract["tasks"], list)
    assert contract["tasks"][0]["status"] == "pending"
    assert "task_id" in contract["tasks"][0]
    assert "input" in contract["tasks"][0]


def test_skill_catalog_skills_declare_contracts():
    from skills.catalog import SkillCatalog

    catalog = SkillCatalog()
    skill = catalog.get("problem-solver")
    assert skill is not None
    assert skill.name
    assert skill.description
    assert isinstance(skill.input_schema, dict)
    assert isinstance(skill.output_schema, dict)
    assert isinstance(skill.allowed_actions, list)


def test_agent_controller_produces_deterministic_summary(tmp_path):
    os.environ["AI_HOME"] = str(tmp_path)
    from core.agent_controller import AgentController
    from core.task_log_store import TaskLogStore

    store = TaskLogStore(tmp_path / "task_log.db")
    controller = AgentController()
    result = controller.run_goal(
        "Analyze business metrics",
        persist_task=store.log_task,
    )
    assert "task_graph" in result
    assert "tasks" in result
    assert "performance_score" in result
    assert 0.0 <= result["performance_score"] <= 1.0


def test_security_policy_denies_unknown_action():
    from security.policy import SecurityPolicy

    policy = SecurityPolicy()
    try:
        policy.ensure_action_allowed(
            action="filesystem_delete",
            allowed_actions=["skill_dispatch"],
            skill_name="problem-solver",
        )
    except PermissionError:
        return
    raise AssertionError("Expected permission error for disallowed action")


def test_structured_logger_writes_required_fields(tmp_path):
    from analytics.structured_logger import StructuredLogger

    log_file = tmp_path / "ops.jsonl"
    logger = StructuredLogger(log_path=log_file)
    event = logger.log_event(
        component="executor",
        action="task:problem-solver",
        result="success",
        latency_ms=12.5,
    )
    assert event["timestamp"]
    assert event["component"] == "executor"
    assert event["action"] == "task:problem-solver"
    assert event["result"] == "success"
    assert event["latency_ms"] >= 0
    assert log_file.exists()


def test_task_engine_compatibility_shape(tmp_path):
    from core.task_engine import TaskEngine

    engine = TaskEngine(db_path=tmp_path / "task_log.db")
    result = engine.run_goal("publish a video")
    assert "run_id" in result
    assert "tasks" in result
    assert "success_rate" in result
