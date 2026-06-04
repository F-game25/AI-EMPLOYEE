from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
_CAPABILITIES_PATH = os.path.join(_REPO_ROOT, 'runtime', 'config', 'agent_capabilities.json')
_FEEDBACK_PATH = os.path.join(_REPO_ROOT, 'state', 'quantum_feedback.jsonl')


def _state_dir() -> str:
    return os.environ.get('STATE_DIR', os.path.join(_REPO_ROOT, 'state'))


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


def _load_feedback() -> dict[str, float]:
    """Aggregate past_success_rate per agent_id from quantum_feedback.jsonl."""
    feedback: dict[str, list[float]] = {}
    path = os.path.join(_state_dir(), 'quantum_feedback.jsonl')
    if not os.path.exists(path):
        path = _FEEDBACK_PATH
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    agent_id = ev.get('agent_id', '')
                    success = float(ev.get('success', 0.5))
                    if agent_id:
                        feedback.setdefault(agent_id, []).append(success)
                except Exception:
                    continue
    except Exception:
        return {}
    return {aid: sum(vals) / len(vals) for aid, vals in feedback.items()}


class AgentRegistryEngine:
    name = 'agents'
    source_type = 'agent'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('AgentRegistryEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        if not os.path.exists(_CAPABILITIES_PATH):
            return []

        tokens = request.query.lower().split()
        feedback = _load_feedback()
        results: list[NormalizedSearchResult] = []

        try:
            with open(_CAPABILITIES_PATH) as f:
                data = json.load(f)
        except Exception as exc:
            log.debug('agent_capabilities.json read error: %s', exc)
            return []

        agents = data.get('agents', data)
        if not isinstance(agents, dict):
            return []

        for agent_id, info in agents.items():
            if not isinstance(info, dict):
                continue
            description = info.get('description', '')
            skills = info.get('skills', [])
            specialties = info.get('specialties', [])
            combined = f"{agent_id} {description} {' '.join(skills)} {' '.join(specialties)}"
            score = _keyword_score(tokens, combined)
            if score == 0.0:
                continue
            content = f"{description} | Skills: {', '.join(skills[:5])}"[:500]
            uid = hashlib.md5(f"agent:{agent_id}".encode()).hexdigest()[:12]
            results.append(NormalizedSearchResult(
                id=uid,
                title=agent_id,
                content=content,
                url=f'runtime/agents/{agent_id}/',
                source_type='agent',
                engine=self.name,
                score=score,
                skills=skills,
                agent_id=agent_id,
                past_success_rate=feedback.get(agent_id, 0.5),
                metadata={
                    'category': info.get('category', ''),
                    'model': info.get('model', ''),
                    'capacity_mode': info.get('capacity_mode', ''),
                },
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]
