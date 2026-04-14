from __future__ import annotations

import importlib
import os


def _reload(module_name: str):
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_weights_update_and_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    bw = _reload("core.brain_weights")

    before = bw.get_weights()["lead_hunter"]
    bw.update_weight("lead_hunter", 1.0)
    after = bw.get_weights()["lead_hunter"]

    assert after > before
    assert (tmp_path / "state" / "brain_weights.json").exists()


def test_same_task_selection_improves_over_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    bw = _reload("core.brain_weights")
    br = _reload("core.brain_registry")
    from core.contracts import TaskNode

    registry = br.BrainRegistry()
    confidences = []
    for i in range(5):
        strategy = registry.get_strategy(goal="find qualified sales leads", goal_type="lead_generation")
        confidences.append(float(strategy["brain"]["confidence"]))
        task = TaskNode(
            task_id=f"t{i}",
            skill=strategy["agent"],
            input={"goal": "find qualified sales leads"},
            status="success",
            output={"result": "ok"},
        )
        registry.learn_from_task(goal="find qualified sales leads", task=task)

    assert confidences[-1] >= confidences[0]
    assert bw.get_weights()["lead_hunter"] >= 0.5


def test_learn_topic_is_reused_in_planner_context(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.knowledge_store")
    ra = _reload("core.research_agent")
    from core.self_improvement.contracts import ImprovementTask
    from core.self_improvement.planner_ai import PlannerAI

    result = ra.ResearchAgent().learn_topic("learn about ecommerce")
    assert result["topic"] == "ecommerce"

    task = ImprovementTask(
        description="create marketing strategy for ecommerce",
        target_area="agents",
    )
    plan = PlannerAI().analyze_and_plan(task)
    assert "learned the following relevant knowledge" in plan.why
    assert "ecommerce" in plan.why.lower()


def test_conversation_profile_learning(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    ks = _reload("core.knowledge_store")
    store = ks.get_knowledge_store()
    profile = store.learn_from_conversation(
        "My business type is ecommerce. My goal is to grow revenue with a small budget."
    )

    assert "ecommerce" in (profile.get("business_type") or "")
    assert profile.get("goals")
