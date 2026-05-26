"""Unit tests for AutoResearchAgent."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "runtime"))


class _StubMemory:
    def __init__(self): self.stores = []; self.outcomes = []
    def store(self, key, text, *, memory_type="semantic", source="", importance=0.5, agent="", extra=None):
        self.stores.append({"key": key, "text": text, "extra": extra or {}, "importance": importance})
        return {"cache_key": key, "vector_stored": True, "memory_type": memory_type, "ts": "ts"}
    def record_outcome(self, *, action, success, context="", result=None, goal_type=""):
        self.outcomes.append({"action": action, "success": success, "context": context, "result": result})
        return {"ok": True}


class _StubKnowledge:
    def __init__(self): self.entries = []
    def add_knowledge(self, topic, content):
        self.entries.append({"topic": topic, "content": content}); return {"topic": topic, "entries": len(self.entries)}


class _StubGraph:
    available = False
    def upsert_concept(self, *a, **kw): return "cid"
    def link(self, *a, **kw): return None
    def attach_memory(self, *a, **kw): return None


def _fake_search(query, n=3):
    return [
        {"title": f"Result {i} for {query}", "url": f"https://example.com/r{i}",
         "snippet": f"snippet {i}", "source": "TEST"} for i in range(n)
    ]


async def _fake_fetch(url):
    return {
        "url": url, "final_url": url, "title": f"Title of {url}",
        "text": f"Body text describing the topic at {url} with details numbers 42 and facts.",
        "screenshot_b64": None,
    }


def _agent_with_stubs(memory=None, knowledge=None, graph=None):
    from core.auto_research_agent import AutoResearchAgent
    events = []
    def bc(evt, payload): events.append((evt, payload))
    a = AutoResearchAgent(
        memory_router=memory or _StubMemory(),
        brain_graph=graph or _StubGraph(),
        knowledge_store=knowledge or _StubKnowledge(),
        llm_client=None,
        search_fn=_fake_search,
        fetch_fn=_fake_fetch,
        broadcaster=bc,
        save_screenshots=False,
    )
    return a, events


def test_research_persists_to_memory_and_knowledge(monkeypatch):
    # Force auto_save decision so findings bypass the pending_review gate
    # (pending_review fires when sentence_transformers is not installed)
    import types
    stub_result = types.SimpleNamespace(decision="auto_save", confidence=0.9,
                                        to_dict=lambda: {"decision": "auto_save", "confidence": 0.9})
    stub_engine = types.SimpleNamespace(verify=lambda **kw: stub_result)
    monkeypatch.setattr("core.auto_research_agent._VERIFY_AVAILABLE", True)
    monkeypatch.setattr("core.auto_research_agent._get_verification_engine", lambda: stub_engine)
    mem = _StubMemory(); ks = _StubKnowledge()
    a, events = _agent_with_stubs(memory=mem, knowledge=ks)
    result = asyncio.run(a.research(gaps=["my gap"], goal="my goal", hop=0))
    assert result["findings_count"] >= 1
    assert len(mem.stores) == result["findings_count"]
    assert ks.entries, "knowledge_store.add_knowledge should be called"
    assert any(s.get("event") if isinstance(s, dict) else s[0] for s in events) or events
    assert mem.outcomes, "record_outcome should be called for telemetry"


def test_research_emits_lifecycle_events():
    a, events = _agent_with_stubs()
    asyncio.run(a.research(gaps=["x"], goal="g", hop=0, task_id="t1"))
    kinds = [e[0] for e in events]
    assert "task:research_started" in kinds
    assert "task:research_completed" in kinds


def test_research_empty_gaps_short_circuits():
    a, events = _agent_with_stubs()
    r = asyncio.run(a.research(gaps=[], goal="g", hop=0))
    assert r["findings_count"] == 0
    assert events == []
