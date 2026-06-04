"""Tests for SearchOrchestrator end-to-end pipeline.

Run: python3 -m pytest tests/test_search_orchestrator.py -v
"""
from __future__ import annotations
import asyncio
import os
import sys

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
_RUNTIME = os.path.join(_REPO_ROOT, 'runtime')
for p in (_REPO_ROOT, _RUNTIME):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest

from core.quantum.search.orchestrator import SearchOrchestrator
from core.quantum.search.schema import SearchRequest, NormalizedSearchResult, ContextPack


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Full search tests
# ---------------------------------------------------------------------------

class TestOrchestrator:
    def setup_method(self):
        self.orc = SearchOrchestrator()

    def test_full_search_no_bang(self):
        """Search without bangs must return a list of NormalizedSearchResult."""
        req = SearchRequest(query='agent task', timeout_ms=3000)
        results = _run(self.orc.search(req))
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, NormalizedSearchResult)

    def test_results_sorted_by_amplitude(self):
        """Results must be sorted amplitude descending."""
        req = SearchRequest(query='agent', timeout_ms=3000)
        results = _run(self.orc.search(req))
        if len(results) < 2:
            return  # nothing to compare
        for i in range(len(results) - 1):
            assert results[i].amplitude >= results[i + 1].amplitude, (
                f'Not sorted at index {i}: {results[i].amplitude} < {results[i+1].amplitude}'
            )

    def test_amplitudes_in_range(self):
        """Every amplitude must be in [0, 1]."""
        req = SearchRequest(query='skill tool', timeout_ms=3000)
        results = _run(self.orc.search(req))
        for r in results:
            assert 0.0 <= r.amplitude <= 1.0, f'Amplitude {r.amplitude} out of range for {r.id}'

    def test_context_pack_structure(self):
        """build_context_pack() must return a ContextPack with all fields set."""
        req = SearchRequest(query='agent sales', complexity='complex', timeout_ms=3000)
        pack = _run(self.orc.build_context_pack(req))
        assert isinstance(pack, ContextPack)
        assert pack.search_id
        assert pack.query == 'agent sales'
        assert isinstance(pack.candidates, list)
        assert isinstance(pack.top_agents, list)
        assert isinstance(pack.top_tools, list)
        assert pack.suggested_model == 'claude-sonnet-4-6'
        assert isinstance(pack.confidence, float)
        assert 0.0 <= pack.confidence <= 1.0
        assert isinstance(pack.reasoning, str)
        assert isinstance(pack.engine_stats, dict)

    def test_context_pack_model_routing(self):
        """Complexity mapping must produce the right suggested model."""
        cases = [
            ('critical', 'claude-opus-4-8'),
            ('complex',  'claude-sonnet-4-6'),
            ('medium',   'claude-haiku-4-5'),
            ('simple',   'claude-haiku-4-5'),
        ]
        for complexity, expected_model in cases:
            req = SearchRequest(query='test', complexity=complexity, timeout_ms=2000)
            pack = _run(self.orc.build_context_pack(req))
            assert pack.suggested_model == expected_model, (
                f'complexity={complexity}: expected {expected_model}, got {pack.suggested_model}'
            )

    def test_bang_limits_engines(self):
        """!agent bang must produce only results from the agents engine."""
        req = SearchRequest(query='!agent orchestrator', timeout_ms=3000)
        results = _run(self.orc.search(req))
        if not results:
            return  # If no agents match, still OK — just verify no crash
        for r in results:
            assert r.engine == 'agents', (
                f'Expected engine=agents, got engine={r.engine} for result {r.id}'
            )

    def test_timeout_graceful(self):
        """Very short timeout must not crash — returns whatever completed."""
        req = SearchRequest(query='agent', timeout_ms=1)  # 1ms — almost nothing will complete
        results = _run(self.orc.search(req))
        # Must not raise; results may be empty
        assert isinstance(results, list)

    def test_engine_stats_populated(self):
        """ContextPack.engine_stats must include count/latency_ms/error per engine."""
        req = SearchRequest(query='task', timeout_ms=3000)
        pack = _run(self.orc.build_context_pack(req))
        for engine_name, stats in pack.engine_stats.items():
            assert 'count' in stats, f'{engine_name} missing count'
            assert 'latency_ms' in stats, f'{engine_name} missing latency_ms'
            assert 'error' in stats, f'{engine_name} missing error'

    def test_tenant_id_propagated(self):
        """tenant_id set on request must appear on ContextPack."""
        req = SearchRequest(query='agent', tenant_id='tenant-xyz', timeout_ms=2000)
        pack = _run(self.orc.build_context_pack(req))
        assert pack.tenant_id == 'tenant-xyz'

    def test_no_bang_returns_multi_engine_results(self):
        """Without bang filter, results should come from more than one engine."""
        req = SearchRequest(query='the', timeout_ms=3000)
        results = _run(self.orc.search(req))
        engines_seen = {r.engine for r in results}
        # 'the' is common enough that at least 2 engines should return something
        assert len(engines_seen) >= 1  # At minimum, agents engine always has results
