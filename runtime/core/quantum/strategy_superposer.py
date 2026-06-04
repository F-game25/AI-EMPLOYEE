"""Strategy superposition — heuristic execution strategy generation."""
from __future__ import annotations
from dataclasses import dataclass, field
from core.quantum.search.schema import ContextPack


@dataclass
class Strategy:
    name: str
    steps: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    estimated_cost: float = 0.0
    risk_level: float = 0.0
    rationale: str = ''


def _top_agent(context_pack: ContextPack, idx: int = 0) -> str:
    if context_pack.top_agents and len(context_pack.top_agents) > idx:
        return context_pack.top_agents[idx]
    return f'agent_{idx}'


class StrategySuperposer:
    def generate(self, goal: str, context_pack: ContextPack, complexity: str) -> list[Strategy]:
        agent0 = _top_agent(context_pack, 0)
        agent1 = _top_agent(context_pack, 1)

        if complexity == 'simple':
            return [Strategy(
                name='fastest',
                steps=[{'action': 'agent_task', 'agent_id': agent0, 'description': goal}],
                confidence=0.7, estimated_cost=0.1, risk_level=0.2,
                rationale='Single agent, minimal overhead.',
            )]

        fastest = Strategy(
            name='fastest',
            steps=[{'action': 'agent_task', 'agent_id': agent0, 'description': goal}],
            confidence=0.7, estimated_cost=0.2, risk_level=0.3,
            rationale='Single agent, low latency.',
        )
        safest = Strategy(
            name='safest',
            steps=[
                {'action': 'sandbox_check', 'agent_id': agent0, 'description': 'Validate in sandbox'},
                {'action': 'agent_task',    'agent_id': agent0, 'description': goal},
            ],
            confidence=0.85, estimated_cost=0.4, risk_level=0.1,
            rationale='Sandbox validation before execution.',
        )
        highest_quality = Strategy(
            name='highest_quality',
            steps=[
                {'action': 'agent_task',   'agent_id': agent0, 'description': goal},
                {'action': 'agent_task',   'agent_id': agent1, 'description': f'Review: {goal}'},
                {'action': 'validation',   'agent_id': agent0, 'description': 'Validate outputs'},
            ],
            confidence=0.9, estimated_cost=0.7, risk_level=0.15,
            rationale='Dual agent + validation for maximum quality.',
        )

        strategies = [fastest, safest, highest_quality]

        if complexity == 'critical':
            cheapest = Strategy(
                name='cheapest',
                steps=[{'action': 'agent_task', 'agent_id': agent0, 'description': goal}],
                confidence=0.6, estimated_cost=0.05, risk_level=0.35,
                rationale='Haiku model + local tools for minimum cost.',
            )
            cheapest.steps[0]['suggested_model'] = 'claude-haiku-4-5'
            strategies.append(cheapest)

        return strategies

    def select(self, strategies: list[Strategy]) -> Strategy:
        def _score(s: Strategy) -> float:
            return s.confidence * (1 - s.risk_level) * (1 - s.estimated_cost * 0.3)
        return max(strategies, key=_score)

    def merge_compatible(self, strategies: list[Strategy]) -> Strategy | None:
        if not strategies:
            return None
        first_steps = [s.steps[0] if s.steps else None for s in strategies]
        if not all(s is not None for s in first_steps):
            return None
        # Check identical first step across all strategies
        ref = first_steps[0]
        if not all(s.get('action') == ref.get('action') and s.get('agent_id') == ref.get('agent_id')
                   for s in first_steps[1:]):
            return None
        merged_step = dict(ref)
        merged_step['confidence'] = 1.0
        return Strategy(
            name='merged',
            steps=[merged_step],
            confidence=1.0,
            rationale='All strategies agree on first step.',
        )
