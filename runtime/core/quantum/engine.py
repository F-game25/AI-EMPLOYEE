"""Quantum Cognitive Engine — main coordinator."""
from __future__ import annotations
import logging
import uuid
from typing import Any

from core.quantum.search.schema import SearchRequest, ContextPack
from core.quantum.search.orchestrator import SearchOrchestrator
from core.quantum.complexity import classify, POOL_CAP, ROUNDS
from core.quantum.candidate import Candidate, from_results
from core.quantum.oracle import OracleScorer
from core.quantum.amplifier import AmplitudeAmplifier
from core.quantum.interference import apply as apply_interference
from core.quantum.intent_superposer import IntentSuperposer
from core.quantum.strategy_superposer import StrategySuperposer, Strategy
from core.quantum.router import AmplitudeRouter, MODEL_COMPLEXITY_MAP
from core.quantum.step_score import score_step as _score_step, StepScore
from core.quantum.reflection import ReflectionEngine
from core.quantum.persistence import AmplitudePersistence
from core.quantum.metrics import QCEMetricsCollector

log = logging.getLogger(__name__)


class QuantumCognitiveEngine:
    def __init__(self):
        self._orchestrator = SearchOrchestrator()
        self._oracle       = OracleScorer()
        self._amplifier    = AmplitudeAmplifier()
        self._intent       = IntentSuperposer()
        self._strategy     = StrategySuperposer()
        self._router       = AmplitudeRouter()
        self._reflection   = ReflectionEngine()
        self._persistence  = AmplitudePersistence()
        self._metrics      = QCEMetricsCollector.get()
        self._drift: dict[str, float] = {}

    async def process(self, goal: str, tenant_id: str = '',
                      preferred_agent_id: str | None = None,
                      task_type: str = '') -> ContextPack:
        complexity = classify(goal)
        rounds = ROUNDS[complexity]
        cap = POOL_CAP[complexity]

        # Intent superposition
        intent_candidates = self._intent.generate(goal)
        winning_intent = self._intent.select(intent_candidates)
        query = winning_intent.text

        # Search
        req = SearchRequest(
            query=query,
            task_type=task_type,
            tenant_id=tenant_id,
            max_results_per_engine=cap,
        )
        context_pack = await self._orchestrator.build_context_pack(req)
        context_pack.complexity = complexity

        # Convert raw results to Candidates
        raw = getattr(context_pack, '_raw_results', context_pack.candidates)
        if raw and not isinstance(raw[0], Candidate):
            candidates = from_results(raw)
        else:
            candidates = list(context_pack.candidates)

        # Apply persisted success rates
        for c in candidates:
            stored = self._persistence.load_success_rate(c.result.id)
            if stored != 0.5:
                c.result.past_success_rate = stored

        # Oracle scoring
        for c in candidates:
            self._oracle.score(c, query, task_type=task_type,
                               intent_text=winning_intent.text, tenant_id=tenant_id)
            c.amplitude = (c.amplitude + c.oracle_score) / 2.0

        # Amplification
        candidates = self._amplifier.amplify(candidates, rounds)

        # Interference
        candidates = apply_interference(candidates, query, task_type, tenant_id)

        # Count interference events
        for c in candidates:
            if c.interference != 'none':
                self._metrics.record_interference(c.interference)

        # Rebuild context pack with enriched candidates
        context_pack.candidates = candidates
        context_pack.confidence = (
            sum(c.amplitude for c in candidates) / len(candidates)
            if candidates else 0.0
        )

        # Routing
        agent_ids = self._router.route_agents(context_pack, preferred_agent_id=preferred_agent_id)
        tool_ids  = self._router.route_tools(context_pack)
        model     = self._router.route_model(complexity)

        context_pack.top_agents    = agent_ids
        context_pack.top_tools     = tool_ids
        context_pack.suggested_model = model

        self._metrics.record_context_pack(context_pack.confidence, len(candidates), rounds)

        return context_pack

    async def plan(self, goal: str, context_pack: ContextPack,
                   complexity: str = 'medium') -> list[Strategy]:
        strategies = self._strategy.generate(goal, context_pack, complexity)
        strategies.sort(key=lambda s: s.confidence * (1 - s.risk_level), reverse=True)
        return strategies

    async def route(self, context_pack: ContextPack, complexity: str = 'medium',
                    preferred_agent_id: str | None = None) -> dict:
        return {
            'agents': self._router.route_agents(context_pack, preferred_agent_id=preferred_agent_id),
            'tools':  self._router.route_tools(context_pack),
            'model':  self._router.route_model(complexity),
        }

    def score_step(self, step: dict, context_pack: ContextPack,
                   prior_success: float = 0.5,
                   sandbox_available: bool = True) -> StepScore:
        ss = _score_step(step, context_pack, prior_success, sandbox_available)
        self._metrics.record_gate(ss.gate)
        return ss

    def reflect(self, task_id: str, outcome: str, context_pack: ContextPack,
                **kwargs) -> None:
        self._reflection.reflect(task_id, outcome, context_pack, **kwargs)
        self._metrics.record_reflection(outcome)

        candidates = [c for c in context_pack.candidates if isinstance(c, Candidate)]
        ids = [c.result.id for c in candidates[:10]]
        if ids:
            self._persistence.bulk_update(ids, outcome)

    def rank_queued_tasks(self, tasks: list[dict]) -> list[dict]:
        def _score(t: dict) -> float:
            urgency  = float(t.get('urgency', 0.5))
            value    = float(t.get('expected_value', 0.5))
            cost     = float(t.get('resource_cost', 0.5)) or 0.01
            return (urgency * value) / cost

        return sorted(tasks, key=_score, reverse=True)

    def update_model_signal(self, model_id: str, drift_score: float) -> None:
        self._drift[model_id] = drift_score

    def prometheus_text(self) -> str:
        return self._metrics.prometheus_text()


_engine: QuantumCognitiveEngine | None = None


def get_qce() -> QuantumCognitiveEngine:
    global _engine
    if _engine is None:
        _engine = QuantumCognitiveEngine()
    return _engine
