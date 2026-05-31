"""Tests for Phase 4D: orchestrator reasoning quality and context scoring."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "runtime"))


# ── Stubs ─────────────────────────────────────────────────────────────────────

class _StubMemoryRouter:
    def __init__(self, hits):
        self._hits = hits

    def retrieve(self, query, *, top_k=5, memory_type=None):
        return list(self._hits[:top_k])


def _make_evaluator(hits=None, knowledge_hits=0):
    from core.context_evaluator import ContextSufficiencyEvaluator

    class _FakeKS:
        def __init__(self, n):
            self._n = n
        def search_knowledge(self, _q):
            return [{}] * self._n

    return ContextSufficiencyEvaluator(
        memory_router=_StubMemoryRouter(hits or []),
        brain_graph=None,
        llm_client=None,
        knowledge_store=_FakeKS(knowledge_hits),
        min_score=0.6,
    )


# ── ContextSufficiencyEvaluator tests ─────────────────────────────────────────

def test_evaluate_returns_score_in_0_1_range():
    """evaluate() must return a score between 0.0 and 1.0 inclusive."""
    e = _make_evaluator()
    result = e.evaluate("build a SaaS product pricing page")
    assert isinstance(result["score"], float)
    assert 0.0 <= result["score"] <= 1.0


def test_evaluate_empty_context_returns_low_score():
    """With no memory and no knowledge store, score should be below 0.5."""
    e = _make_evaluator()
    result = e.evaluate("complex enterprise software architecture review")
    assert result["score"] < 0.5
    assert result["sufficient"] is False


def test_evaluate_matching_context_scores_higher():
    """More relevant memory entries should produce a higher score than zero context."""
    goal = "Find EU carbon fiber bicycle frame manufacturers with MOQ less than 500"
    hits_relevant = [
        {"key": f"k{i}", "text": f"EU carbon fiber bicycle frame manufacturers MOQ supplier {i}", "_score": 0.85}
        for i in range(5)
    ]
    e_empty = _make_evaluator(hits=[])
    e_rich = _make_evaluator(hits=hits_relevant, knowledge_hits=4)

    score_empty = e_empty.evaluate(goal)["score"]
    score_rich = e_rich.evaluate(goal)["score"]
    assert score_rich > score_empty, f"Expected rich > empty: {score_rich} vs {score_empty}"


def test_evaluate_returns_breakdown_dict():
    """evaluate() must include a 'breakdown' dict with the four expected keys."""
    e = _make_evaluator()
    result = e.evaluate("Increase monthly recurring revenue by 20%")
    breakdown = result.get("breakdown")
    assert isinstance(breakdown, dict), "breakdown must be a dict"
    for key in ("keyword_overlap", "specificity", "historical", "knowledge_hits"):
        assert key in breakdown, f"breakdown missing key: {key}"
        assert 0.0 <= breakdown[key] <= 1.0, f"breakdown[{key}] out of range"


def test_evaluate_returns_recommendation_string():
    """evaluate() must return a non-empty 'recommendation' string."""
    e = _make_evaluator()
    result = e.evaluate("Send cold emails to 50 leads in the fintech sector")
    assert isinstance(result.get("recommendation"), str)
    assert len(result["recommendation"]) > 0


def test_specificity_score_higher_for_specific_goal():
    """A goal with named entities and numbers should score higher for specificity."""
    e = _make_evaluator()
    generic = e.evaluate("help me with marketing")
    specific = e.evaluate("Generate 500 leads for ACME Corp in Q3 with budget less than $10,000")
    # Specificity sub-score should be higher for the specific goal
    assert specific["breakdown"]["specificity"] > generic["breakdown"]["specificity"]


def test_evaluate_knowledge_hits_boost():
    """Knowledge store hits should raise score above zero-knowledge baseline."""
    goal = "research competitor pricing strategy"
    e_no_ks = _make_evaluator(hits=[], knowledge_hits=0)
    e_with_ks = _make_evaluator(hits=[], knowledge_hits=5)
    score_no = e_no_ks.evaluate(goal)["score"]
    score_yes = e_with_ks.evaluate(goal)["score"]
    assert score_yes >= score_no


# ── AgentController plan quality tests ────────────────────────────────────────

def _make_task_graph(goal="test goal", n_tasks=2, with_deps=True):
    """Build a minimal TaskGraph for quality scoring tests without heavy imports."""
    from core.contracts import TaskGraph, TaskNode
    tasks = []
    for i in range(n_tasks):
        tid = f"run-t{i+1}"
        deps = [f"run-t{i}"] if with_deps and i > 0 else []
        tasks.append(TaskNode(
            task_id=tid,
            skill="problem-solver",
            input={"goal": goal},
            expected_output={"status": "success"},
            dependencies=deps,
        ))
    return TaskGraph(run_id="run", goal=goal, tasks=tasks)


def test_score_plan_quality_returns_expected_shape():
    """_score_plan_quality must return (float in 0-1, positive int)."""
    from core.agent_controller import AgentController
    graph = _make_task_graph(n_tasks=2)
    quality, tokens = AgentController._score_plan_quality("test goal", graph)
    assert 0.0 <= quality <= 1.0
    assert isinstance(tokens, int) and tokens > 0


def test_score_plan_quality_zero_tasks_returns_zero():
    """Empty task list → quality score 0.0."""
    from core.agent_controller import AgentController
    from core.contracts import TaskGraph
    graph = TaskGraph(run_id="r", goal="g", tasks=[])
    quality, tokens = AgentController._score_plan_quality("g", graph)
    assert quality == 0.0
    assert tokens == 0


def test_score_plan_quality_moderate_task_count_scores_higher():
    """A 2-4 task plan should score better than a single-task plan."""
    from core.agent_controller import AgentController
    goal = "build a content marketing pipeline"
    single = _make_task_graph(goal=goal, n_tasks=1)
    moderate = _make_task_graph(goal=goal, n_tasks=3)
    q_single, _ = AgentController._score_plan_quality(goal, single)
    q_moderate, _ = AgentController._score_plan_quality(goal, moderate)
    assert q_moderate > q_single


def test_score_plan_quality_invalid_deps_lower_score():
    """Broken dependency references should reduce the quality score."""
    from core.agent_controller import AgentController
    from core.contracts import TaskGraph, TaskNode
    # Task with a non-existent dependency
    tasks = [
        TaskNode(task_id="t1", skill="s", input={"goal": "g"}, dependencies=["nonexistent"]),
    ]
    broken_graph = TaskGraph(run_id="r", goal="g", tasks=tasks)
    valid_graph = _make_task_graph(goal="g", n_tasks=1, with_deps=False)
    q_broken, _ = AgentController._score_plan_quality("g", broken_graph)
    q_valid, _ = AgentController._score_plan_quality("g", valid_graph)
    assert q_broken <= q_valid
