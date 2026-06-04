"""AmplitudeRouter — agent, tool, model, research source selection."""
from __future__ import annotations
import random
from core.quantum.search.schema import ContextPack
from core.quantum.candidate import Candidate
from core.quantum.oracle import TASK_TYPE_AFFINITY

MODEL_COMPLEXITY_MAP = {
    'simple':   'claude-haiku-4-5',
    'medium':   'claude-sonnet-4-6',
    'complex':  'claude-sonnet-4-6',
    'critical': 'claude-opus-4-8',
}

EXPLORATION_EPSILON = 0.10


def _candidates(context_pack: ContextPack) -> list[Candidate]:
    return [c for c in context_pack.candidates if isinstance(c, Candidate)]


class AmplitudeRouter:
    def route_agents(self, context_pack: ContextPack, n: int = 3,
                     preferred_agent_id: str | None = None) -> list[str]:
        pool = [c for c in _candidates(context_pack) if c.result.source_type == 'agent']
        pool.sort(key=lambda c: c.amplitude, reverse=True)
        ids = [c.result.id for c in pool]

        if preferred_agent_id and preferred_agent_id in ids:
            ids.remove(preferred_agent_id)
            ids.insert(0, preferred_agent_id)
        elif preferred_agent_id:
            ids.insert(0, preferred_agent_id)

        if len(ids) >= 2 and random.random() < EXPLORATION_EPSILON:
            ids[0], ids[1] = ids[1], ids[0]

        return ids[:n]

    def route_tools(self, context_pack: ContextPack, action_hint: str = '') -> list[str]:
        pool = [c for c in _candidates(context_pack) if c.result.source_type == 'tool']
        if action_hint:
            pool = [c for c in pool if action_hint.lower() in (c.result.title + c.result.content).lower()] or pool
        pool.sort(key=lambda c: c.amplitude, reverse=True)
        return [c.result.id for c in pool[:3]]

    def route_model(self, complexity: str, context_pack: ContextPack | None = None,
                    provider_health: dict | None = None) -> str:
        model = MODEL_COMPLEXITY_MAP.get(complexity, 'claude-sonnet-4-6')
        if provider_health:
            # Try to find a healthy model for the given complexity
            for cplx in ['simple', 'medium', 'complex', 'critical']:
                candidate = MODEL_COMPLEXITY_MAP.get(cplx, model)
                provider = candidate.split('-')[0] if '-' in candidate else candidate
                if not provider_health.get(provider, {}).get('circuit_open', False):
                    if cplx == complexity or model == candidate:
                        return candidate
        return model

    def route_research_sources(self, context_pack: ContextPack) -> list[str]:
        if not context_pack.candidates:
            return ['!web', '!rag']
        # Find lowest-amplitude source types
        by_type: dict[str, float] = {}
        for c in _candidates(context_pack):
            st = c.result.source_type
            by_type[st] = min(by_type.get(st, 1.0), c.amplitude)
        sorted_types = sorted(by_type, key=by_type.get)  # type: ignore
        return [f'!{t}' for t in sorted_types[:3]]

    def route_swarm(self, context_pack: ContextPack, n: int = 3) -> list[str]:
        pool = [c for c in _candidates(context_pack) if c.result.source_type == 'agent']
        pool.sort(key=lambda c: c.amplitude, reverse=True)

        selected: list[str] = []
        seen_categories: set[str] = set()

        for c in pool:
            cat = c.result.metadata.get('category', c.result.id)
            if cat not in seen_categories:
                selected.append(c.result.id)
                seen_categories.add(cat)
            if len(selected) >= n:
                break

        return selected
