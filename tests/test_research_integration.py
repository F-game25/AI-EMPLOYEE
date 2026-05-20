"""Integration test: AgentController.run_goal honors the research loop."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "runtime"))


def test_run_goal_invokes_context_loop(monkeypatch):
    monkeypatch.setenv("AUTO_RESEARCH_MODE", "auto")

    from core.agent_controller import AgentController

    # Sentinel to capture that the loop ran
    called = {"evaluate": 0, "research": 0}

    class _StubEval:
        def evaluate(self, goal, **kw):
            called["evaluate"] += 1
            # First call insufficient, second sufficient — proves loop continues
            sufficient = called["evaluate"] >= 2
            return {
                "score": 0.85 if sufficient else 0.2,
                "sufficient": sufficient,
                "gaps": [] if sufficient else ["sample gap"],
                "memory_hits": 5 if sufficient else 0,
                "graph_hits": 0,
            }

    class _StubResearcher:
        async def research(self, gaps, goal, *, hop=0, task_id=""):
            called["research"] += 1
            return {"hop": hop, "gaps_researched": gaps, "findings_count": 3, "sources": ["u1"]}
        _broadcast = staticmethod(lambda _e, _p: None)

    controller = AgentController()
    controller._context_evaluator = _StubEval()
    controller._auto_researcher = _StubResearcher()
    # Skip the actual planner/executor — return an empty graph
    monkeypatch.setattr(controller, "build_task_graph", lambda *, goal, run_id: _DummyGraph())
    # Bypass the real executor (it expects a populated TaskGraph)
    monkeypatch.setattr(controller._executor, "execute_graph", lambda g: [])

    out = controller.run_goal("totally unfamiliar topic xyzzy")
    assert called["evaluate"] >= 2
    assert called["research"] >= 1
    assert out["goal"] == "totally unfamiliar topic xyzzy"


class _DummyGraph:
    def __init__(self):
        self.run_id = "r1"
        self.goal = "g"
        self.tasks = []

    def validate_no_cycles(self):
        return None

    def to_contract(self):
        return {"run_id": self.run_id, "goal": self.goal, "tasks": []}
