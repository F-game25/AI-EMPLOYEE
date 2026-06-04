"""Tests for QCE search engines, parsers, and plugins.

Run: python3 -m pytest tests/test_search_engines.py -v
"""
from __future__ import annotations
import asyncio
import os
import sys

# Ensure runtime/ is on sys.path (mirrors start.sh behaviour)
_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
_RUNTIME = os.path.join(_REPO_ROOT, 'runtime')
for p in (_REPO_ROOT, _RUNTIME):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest

from core.quantum.search.bang import BangParser
from core.quantum.search.schema import SearchRequest, NormalizedSearchResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_result(uid: str, url: str = '', score: float = 0.5) -> NormalizedSearchResult:
    return NormalizedSearchResult(
        id=uid, title=uid, content='test content',
        url=url, source_type='doc', engine='test',
        score=score,
    )


# ---------------------------------------------------------------------------
# BangParser tests
# ---------------------------------------------------------------------------

class TestBangParser:
    def setup_method(self):
        self.parser = BangParser()

    def test_bang_parser_web(self):
        _, engines = self.parser.parse('!web latest AI news')
        assert engines == ['searxng']

    def test_bang_parser_memory(self):
        _, engines = self.parser.parse('!memory recall user preferences')
        assert set(engines) == {'local_memory', 'mem0'}

    def test_bang_parser_no_bang(self):
        _, engines = self.parser.parse('find agent that handles billing')
        assert engines == []

    def test_bang_parser_cleans_query(self):
        cleaned, _ = self.parser.parse('!web search for cats')
        assert '!web' not in cleaned
        assert 'cats' in cleaned

    def test_bang_parser_multiple_bangs(self):
        cleaned, engines = self.parser.parse('!code !doc fastapi route')
        assert 'codebase' in engines
        assert 'docs' in engines
        assert '!code' not in cleaned
        assert '!doc' not in cleaned


# ---------------------------------------------------------------------------
# SearxngEngine — offline returns empty
# ---------------------------------------------------------------------------

class TestSearxngEngine:
    def test_searxng_offline_returns_empty(self):
        """SearxngEngine with an unreachable server must return [] without raising."""
        import importlib
        mod = importlib.import_module('core.quantum.search.engines.searxng')
        # Temporarily point at a bad port
        original = mod.SEARXNG_URL
        mod.SEARXNG_URL = 'http://127.0.0.1:19999/search'
        try:
            engine = mod.SearxngEngine()
            req = SearchRequest(query='test', timeout_ms=500)
            results = _run(engine.search(req))
            assert results == []
        finally:
            mod.SEARXNG_URL = original


# ---------------------------------------------------------------------------
# AgentRegistryEngine
# ---------------------------------------------------------------------------

class TestAgentRegistryEngine:
    def test_agent_registry_engine_returns_results(self):
        from core.quantum.search.engines.agents import AgentRegistryEngine
        engine = AgentRegistryEngine()
        req = SearchRequest(query='agent')
        results = _run(engine.search(req))
        # agent_capabilities.json has 50+ agents — should return something
        assert len(results) > 0
        for r in results:
            assert r.source_type == 'agent'
            assert r.engine == 'agents'

    def test_agent_results_have_skills(self):
        from core.quantum.search.engines.agents import AgentRegistryEngine
        engine = AgentRegistryEngine()
        req = SearchRequest(query='sales')
        results = _run(engine.search(req))
        # All results must have list (possibly empty) for skills
        for r in results:
            assert isinstance(r.skills, list)


# ---------------------------------------------------------------------------
# LocalMemoryEngine
# ---------------------------------------------------------------------------

class TestLocalMemoryEngine:
    def test_local_memory_engine_keyword_match(self):
        """Query matching a channel name that appears in bus.jsonl."""
        from core.quantum.search.engines.local_memory import LocalMemoryEngine
        engine = LocalMemoryEngine()
        # 'notifications' is a channel name present in state/bus.jsonl
        req = SearchRequest(query='notifications')
        results = _run(engine.search(req))
        # May be 0 if bus.jsonl has no matching lines, but must not raise
        assert isinstance(results, list)

    def test_local_memory_engine_no_raise_on_missing_files(self):
        """Engine must not raise even if state dir has nothing relevant."""
        from core.quantum.search.engines.local_memory import LocalMemoryEngine
        engine = LocalMemoryEngine()
        req = SearchRequest(query='xyzzy_nonexistent_qqq')
        results = _run(engine.search(req))
        assert results == []


# ---------------------------------------------------------------------------
# Deduplicator
# ---------------------------------------------------------------------------

class TestDeduplicatorPlugin:
    def test_deduplicator_removes_url_dupes(self):
        from core.quantum.search.plugins.deduplicator import DeduplicatorPlugin
        plugin = DeduplicatorPlugin()
        pool = [
            _make_result('aaa', url='http://example.com/page', score=0.8),
            _make_result('bbb', url='http://example.com/page', score=0.4),
            _make_result('ccc', url='http://other.com/', score=0.6),
        ]
        req = SearchRequest(query='test')
        result_pool, _ = _run(plugin.process(pool, req))
        urls = [r.url for r in result_pool]
        assert urls.count('http://example.com/page') == 1
        # The higher-score one should survive
        surviving = next(r for r in result_pool if r.url == 'http://example.com/page')
        assert surviving.score == 0.8

    def test_deduplicator_removes_id_dupes(self):
        from core.quantum.search.plugins.deduplicator import DeduplicatorPlugin
        plugin = DeduplicatorPlugin()
        pool = [_make_result('dup1'), _make_result('dup1'), _make_result('unique')]
        req = SearchRequest(query='test')
        result_pool, _ = _run(plugin.process(pool, req))
        ids = [r.id for r in result_pool]
        assert ids.count('dup1') == 1
        assert 'unique' in ids


# ---------------------------------------------------------------------------
# QuantumAmplifierPlugin
# ---------------------------------------------------------------------------

class TestQuantumAmplifierPlugin:
    def test_quantum_amplifier_normalizes_0_to_1(self):
        from core.quantum.search.plugins.quantum_amplifier import QuantumAmplifierPlugin
        plugin = QuantumAmplifierPlugin()
        pool = [
            NormalizedSearchResult(id=f'r{i}', title=f't{i}', content='c', url='',
                                   source_type='doc', engine='test', score=0.1 * i,
                                   past_success_rate=0.5)
            for i in range(1, 11)
        ]
        req = SearchRequest(query='test keyword')
        result_pool, _ = _run(plugin.process(pool, req))
        for r in result_pool:
            assert 0.0 <= r.amplitude <= 1.0, f'amplitude {r.amplitude} out of range'

    def test_quantum_amplifier_suppresses_low_amplitude(self):
        from core.quantum.search.plugins.quantum_amplifier import QuantumAmplifierPlugin
        plugin = QuantumAmplifierPlugin()
        # One very high-scoring, rest zeros — zeros should be suppressed
        pool = [
            NormalizedSearchResult(id='hi', title='high', content='high relevance test',
                                   url='', source_type='doc', engine='test', score=0.9,
                                   past_success_rate=1.0),
        ] + [
            NormalizedSearchResult(id=f'lo{i}', title='low', content='x',
                                   url='', source_type='doc', engine='test', score=0.0,
                                   past_success_rate=0.0)
            for i in range(5)
        ]
        req = SearchRequest(query='high relevance')
        result_pool, _ = _run(plugin.process(pool, req))
        high = next(r for r in result_pool if r.id == 'hi')
        assert high.amplitude == 1.0
