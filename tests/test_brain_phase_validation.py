from __future__ import annotations

import importlib
import sys
from pathlib import Path

_RUNTIME = Path(__file__).parent.parent / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


def _reload(module_name: str):
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_learning_cycle_improves_scoring_signal(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    _reload("core.learning_engine")
    br = _reload("core.brain_registry")
    from core.contracts import TaskNode

    registry = br.BrainRegistry()
    goal = "find qualified ecommerce leads with outreach"
    selected_scores: list[float] = []
    for i in range(3):
        strategy = registry.get_strategy(goal=goal, goal_type="lead_generation")
        selected_agent = strategy["brain"]["selected_agent"]
        selected_scores.append(float(strategy["brain"]["scores"].get(selected_agent, 0.0)))
        registry.learn_from_task(
            goal=goal,
            task=TaskNode(
                task_id=f"lead-{i}",
                skill=strategy["agent"],
                input={"goal": goal},
                status="success",
                output={"result": "usable"},
            ),
        )

    assert selected_scores[-1] >= selected_scores[0]
    metrics = _reload("core.learning_engine").get_learning_engine().metrics()
    assert metrics["best_strategies"]
    assert metrics["best_strategies"][0]["use_count"] >= 3


def test_memory_usage_adapts_outreach_context(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    ks = _reload("core.knowledge_store").get_knowledge_store()
    mi = _reload("core.memory_index").get_memory_index()
    br = _reload("core.brain_registry")

    ks.add_knowledge("outreach", {"insight": "high ticket clients prefer email over cold calls"})
    mi.add_memory("high ticket clients prefer email over cold calls", importance=0.95)

    strategy = br.BrainRegistry().get_strategy(
        goal="find high ticket leads and create outreach plan",
        goal_type="lead_generation",
    )
    memories = strategy["config"]["context_bundle"]["memories"]
    assert any("email over cold calls" in str(m.get("text", "")).lower() for m in memories)
    reasoning = strategy["brain"]["reasoning"].lower()
    assert "previous" in reasoning and "similar" in reasoning and "tasks" in reasoning


def test_research_knowledge_impacts_future_planning(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    ra = _reload("core.research_agent")
    planner_mod = _reload("core.planner")

    payload = ra.ResearchAgent().learn_topic("learn how to run an online clothing business")
    assert payload["research_tasks"]
    graph = planner_mod.Planner().plan(
        goal="build instagram influencer marketing for clothing brand",
        run_id="run-ig-1",
    )
    prompts = " ".join(str(task.input.get("context_prompt", "")).lower() for task in graph.tasks)
    assert "instagram" in prompts
    assert "influencer" in prompts


def test_brain_insights_expose_real_decision_memory_and_learning_panels(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_HOME", str(tmp_path))
    br = _reload("core.brain_registry")
    from core.contracts import TaskNode

    registry = br.BrainRegistry()
    strategy = registry.get_strategy(goal="generate qualified leads", goal_type="lead_generation")
    registry.learn_from_task(
        goal="generate qualified leads",
        task=TaskNode(
            task_id="ui-proof-1",
            skill=strategy["agent"],
            input={"goal": "generate qualified leads"},
            status="success",
            output={"result": "ok"},
        ),
    )

    insights = registry.insights()
    assert insights["last_decision"]
    assert insights["last_decision"].get("reasoning")
    assert insights["last_decision"].get("memory_used")
    assert isinstance(insights["memory_panel"]["short_term"], list)
    assert isinstance(insights["memory_panel"]["episodic"], list)
    assert isinstance(insights["memory_panel"]["long_term"], list)
    assert (
        len(insights["memory_panel"]["short_term"]) > 0
        or len(insights["memory_panel"]["episodic"]) > 0
        or len(insights["memory_panel"]["long_term"]) > 0
    )
    memory_blob = str(insights["memory_panel"]).lower()
    assert "lead" in memory_blob
    assert "best_performing_strategies" in insights["learning_panel"]
    assert "reward_trends" in insights["learning_panel"]
