"""Tests for QCE Core Engine (Phases 4-5)."""
from __future__ import annotations
import asyncio
import json
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure runtime is on sys.path
_RUNTIME = Path(__file__).parent.parent / 'runtime'
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_result(
    id='r1', title='', content='', source_type='agent',
    amplitude=0.5, past_success_rate=0.5,
    graph_neighbors=None, tenant_id='', metadata=None,
):
    from core.quantum.search.schema import NormalizedSearchResult
    return NormalizedSearchResult(
        id=id, title=title, content=content,
        source_type=source_type, amplitude=amplitude,
        past_success_rate=past_success_rate,
        graph_neighbors=graph_neighbors or [],
        tenant_id=tenant_id,
        metadata=metadata or {},
    )


def _make_candidate(oracle_score=0.5, amplitude=0.5, **kwargs):
    from core.quantum.candidate import Candidate
    return Candidate(result=_make_result(**kwargs), oracle_score=oracle_score, amplitude=amplitude)


def _make_context_pack(candidates=None, confidence=0.7):
    from core.quantum.search.schema import ContextPack
    return ContextPack(
        search_id='test-sid',
        query='test query',
        candidates=candidates or [],
        confidence=confidence,
        top_agents=['agent-alpha', 'agent-beta'],
        top_tools=['tool-x'],
        suggested_model='claude-sonnet-4-6',
    )


# ── complexity ───────────────────────────────────────────────────────────────

def test_complexity_simple():
    from core.quantum.complexity import classify
    assert classify('fix bug now') == 'simple'


def test_complexity_critical():
    from core.quantum.complexity import classify
    assert classify('delete all user data immediately') == 'critical'


def test_complexity_complex():
    from core.quantum.complexity import classify
    long_goal = (
        'First analyze the codebase, then identify bottlenecks, after that refactor '
        'the database layer, and also update the API contracts, additionally write tests, '
        'furthermore update the documentation, and then deploy to staging'
    )
    assert classify(long_goal) == 'complex'


# ── oracle ───────────────────────────────────────────────────────────────────

def test_oracle_weights_sum_to_1():
    from core.quantum.oracle import WEIGHTS
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_oracle_scores_candidate():
    from core.quantum.oracle import OracleScorer
    scorer = OracleScorer()
    c = _make_candidate(content='fix the login bug', title='auth fix')
    score = scorer.score(c, query='login bug fix', task_type='coding')
    assert 0.0 <= score <= 1.0
    assert c.oracle_score == score
    assert c.why != ''


# ── amplifier ────────────────────────────────────────────────────────────────

def test_amplifier_convergence():
    from core.quantum.amplifier import AmplitudeAmplifier
    candidates = [
        _make_candidate(amplitude=0.9, id='top'),
        _make_candidate(amplitude=0.5, id='mid'),
        _make_candidate(amplitude=0.1, id='bot'),
    ]
    amp = AmplitudeAmplifier()
    result = amp.amplify(candidates, rounds=4)
    top = next(c for c in result if c.result.id == 'top')
    bot = next(c for c in result if c.result.id == 'bot')
    assert top.amplitude > bot.amplitude


def test_amplifier_clamps_to_1():
    from core.quantum.amplifier import AmplitudeAmplifier
    candidates = [_make_candidate(amplitude=0.99, id=f'c{i}') for i in range(10)]
    amp = AmplitudeAmplifier()
    result = amp.amplify(candidates, rounds=6)
    assert all(0.0 <= c.amplitude <= 1.0 for c in result)


# ── interference ─────────────────────────────────────────────────────────────

def test_interference_constructive():
    from core.quantum.interference import apply
    c = _make_candidate(
        amplitude=0.5, oracle_score=0.8, past_success_rate=0.9,
        source_type='agent',
    )
    # past_success > 0.7 AND oracle_score > 0.7 → constructive
    result = apply([c], query='plan launch', task_type='planning')
    assert result[0].interference == 'constructive'
    assert result[0].amplitude > 0.5


def test_interference_destructive_deprecated():
    from core.quantum.interference import apply
    c = _make_candidate(amplitude=0.8, metadata={'deprecated': True})
    result = apply([c], query='test')
    assert result[0].interference == 'destructive'
    assert result[0].amplitude < 0.2


def test_interference_permission_blocked():
    from core.quantum.interference import apply
    c = _make_candidate(amplitude=0.9, metadata={'permission_ok': 0})
    result = apply([c], query='do something')
    assert result[0].amplitude == 0.0
    assert result[0].interference == 'destructive'


# ── strategy_superposer ───────────────────────────────────────────────────────

def test_strategy_fastest_single_step():
    from core.quantum.strategy_superposer import StrategySuperposer
    ss = StrategySuperposer()
    cp = _make_context_pack()
    strategies = ss.generate('run tests', cp, complexity='simple')
    assert len(strategies) == 1
    assert strategies[0].name == 'fastest'


def test_strategy_medium_three_strategies():
    from core.quantum.strategy_superposer import StrategySuperposer
    ss = StrategySuperposer()
    cp = _make_context_pack()
    strategies = ss.generate(
        'analyze logs then create a report and update dashboard',
        cp, complexity='medium',
    )
    assert len(strategies) == 3
    names = {s.name for s in strategies}
    assert {'fastest', 'safest', 'highest_quality'} == names


# ── router ────────────────────────────────────────────────────────────────────

def test_router_preferred_agent():
    from core.quantum.router import AmplitudeRouter
    router = AmplitudeRouter()
    candidates = [
        _make_candidate(id='agent-alpha', source_type='agent', amplitude=0.9),
        _make_candidate(id='agent-beta',  source_type='agent', amplitude=0.6),
        _make_candidate(id='agent-gamma', source_type='agent', amplitude=0.3),
    ]
    cp = _make_context_pack(candidates=candidates)
    # Force no epsilon swap for deterministic test
    import core.quantum.router as r_mod
    orig = r_mod.EXPLORATION_EPSILON
    r_mod.EXPLORATION_EPSILON = 0.0
    try:
        result = router.route_agents(cp, preferred_agent_id='agent-gamma')
    finally:
        r_mod.EXPLORATION_EPSILON = orig
    assert result[0] == 'agent-gamma'


def test_router_model_simple():
    from core.quantum.router import AmplitudeRouter, MODEL_COMPLEXITY_MAP
    router = AmplitudeRouter()
    model = router.route_model('simple')
    assert model == MODEL_COMPLEXITY_MAP['simple']
    assert 'haiku' in model.lower()


def test_router_model_critical():
    from core.quantum.router import AmplitudeRouter, MODEL_COMPLEXITY_MAP
    router = AmplitudeRouter()
    model = router.route_model('critical')
    assert model == MODEL_COMPLEXITY_MAP['critical']
    assert 'opus' in model.lower()


# ── step_score ───────────────────────────────────────────────────────────────

def test_step_score_direct():
    from core.quantum.step_score import score_step
    # Put a high-trust agent candidate in the pool so agent_trust_score lookup succeeds
    agent_c = _make_candidate(id='agent-alpha', source_type='agent',
                              amplitude=1.0, past_success_rate=1.0)
    tool_c  = _make_candidate(id='tool-read',  source_type='tool',
                              amplitude=1.0, past_success_rate=1.0)
    cp = _make_context_pack(candidates=[agent_c, tool_c], confidence=1.0)
    # Low-risk read action, high trust
    ss = score_step(
        {'action': 'read_file', 'agent_id': 'agent-alpha', 'tool_id': 'tool-read'},
        cp, prior_success=1.0, sandbox_available=True, tenant_permission=1.0,
    )
    assert ss.gate == 'direct'
    assert ss.confidence > 0.85


def test_step_score_hitl():
    from core.quantum.step_score import score_step
    cp = _make_context_pack(confidence=0.3)
    # High-risk action, low context
    ss = score_step(
        {'action': 'transfer_funds', 'agent_id': 'agent-alpha'},
        cp, prior_success=0.2, sandbox_available=False, tenant_permission=0.5,
    )
    assert ss.gate in ('hitl', 'sandbox', 'reject')


def test_step_score_reject():
    from core.quantum.step_score import score_step
    cp = _make_context_pack(confidence=0.0)
    ss = score_step(
        {'action': 'rm_rf'},
        cp, prior_success=0.0, sandbox_available=False, tenant_permission=0.0,
    )
    assert ss.gate == 'reject'


# ── reflection ────────────────────────────────────────────────────────────────

def test_reflection_writes_file(tmp_path):
    from core.quantum.reflection import ReflectionEngine
    engine = ReflectionEngine(state_dir=str(tmp_path))
    cp = _make_context_pack()
    engine.reflect('task-001', 'success', cp, agent_id='agent-alpha')

    lines = (tmp_path / 'quantum_feedback.jsonl').read_text().strip().split('\n')
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec['task_id'] == 'task-001'
    assert rec['outcome'] == 'success'
    assert rec['agent_id'] == 'agent-alpha'


# ── persistence ───────────────────────────────────────────────────────────────

def test_persistence_update_success(tmp_path):
    from core.quantum.persistence import AmplitudePersistence
    p = AmplitudePersistence(state_dir=str(tmp_path))
    initial = p.load_success_rate('cand-1')
    assert initial == 0.5
    p.update('cand-1', 'success')
    after = p.load_success_rate('cand-1')
    assert after > initial


# ── metrics ───────────────────────────────────────────────────────────────────

def test_metrics_gate_counter():
    from core.quantum.metrics import QCEMetricsCollector
    # Use a fresh instance to avoid cross-test bleed
    m = QCEMetricsCollector()
    m.record_gate('direct')
    m.record_gate('direct')
    m.record_gate('hitl')
    text = m.prometheus_text()
    assert 'qce_gate_total{gate="direct"} 2' in text
    assert 'qce_gate_total{gate="hitl"} 1' in text


# ── engine integration ────────────────────────────────────────────────────────

def test_engine_process_returns_context_pack():
    from core.quantum.engine import QuantumCognitiveEngine
    from core.quantum.search.schema import ContextPack, NormalizedSearchResult

    mock_pack = ContextPack(
        search_id='mock-sid',
        query='fix the login bug',
        candidates=[],
        confidence=0.6,
    )

    async def _run():
        engine = QuantumCognitiveEngine()
        with patch.object(engine._orchestrator, 'build_context_pack', new=AsyncMock(return_value=mock_pack)):
            result = await engine.process('fix the login bug', tenant_id='t1', task_type='coding')
        return result

    result = asyncio.run(_run())
    assert isinstance(result, ContextPack)
    assert result.search_id == 'mock-sid'
    assert result.complexity in ('simple', 'medium', 'complex', 'critical')
