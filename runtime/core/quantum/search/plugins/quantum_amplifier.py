from __future__ import annotations
import datetime
import logging
from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

WEIGHTS = {
    'keyword':      0.30,
    'past_success': 0.25,
    'recency':      0.15,
    'source_fit':   0.20,
    'convergence':  0.10,
}

# Maps task_type hints to preferred source_types
_SOURCE_FIT: dict[str, set[str]] = {
    'research':  {'web', 'doc', 'memory', 'graph_memory'},
    'coding':    {'code_file', 'doc', 'tool'},
    'agent':     {'agent', 'skill'},
    'task':      {'task_log', 'event_log'},
    'memory':    {'memory', 'rag', 'graph_memory'},
    'testing':   {'test_log', 'code_file'},
    'artifact':  {'ui_component', 'artifact'},
}


def _recency_score(metadata: dict) -> float:
    updated = metadata.get('updated_at') or metadata.get('timestamp') or metadata.get('created_at')
    if not updated:
        return 0.5
    try:
        if isinstance(updated, (int, float)):
            dt = datetime.datetime.fromtimestamp(updated, tz=datetime.timezone.utc)
        else:
            dt = datetime.datetime.fromisoformat(str(updated).replace('Z', '+00:00'))
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        age_days = max(0, (now - dt).total_seconds() / 86400)
        # Decay: fresh (0d)=1.0, 7d=0.7, 30d=0.4, 90d+=0.1
        return max(0.1, 1.0 - age_days / 120)
    except Exception:
        return 0.5


def _source_fit_score(source_type: str, task_type: str) -> float:
    if not task_type:
        return 0.5
    for tt, types in _SOURCE_FIT.items():
        if tt in task_type.lower() and source_type in types:
            return 1.0
    return 0.2


class QuantumAmplifierPlugin:
    async def process(
        self,
        pool: list[NormalizedSearchResult],
        request: SearchRequest,
    ) -> tuple[list[NormalizedSearchResult], SearchRequest]:
        if not pool:
            return pool, request

        # Count how many engines returned each id (convergence bonus)
        id_engine_count: dict[str, int] = {}
        for r in pool:
            id_engine_count[r.id] = id_engine_count.get(r.id, 0) + 1
        max_convergence = max(id_engine_count.values()) or 1

        tokens = request.query.lower().split()

        for r in pool:
            keyword = r.score  # already computed by engine
            past_success = r.past_success_rate if r.past_success_rate > 0 else 0.5
            recency = _recency_score(r.metadata)
            source_fit = _source_fit_score(r.source_type, request.task_type)
            convergence = id_engine_count[r.id] / max_convergence

            amplitude = (
                WEIGHTS['keyword']      * keyword +
                WEIGHTS['past_success'] * past_success +
                WEIGHTS['recency']      * recency +
                WEIGHTS['source_fit']   * source_fit +
                WEIGHTS['convergence']  * convergence
            )
            r.amplitude = amplitude

        # 2 amplification rounds
        for _ in range(2):
            amplitudes = [r.amplitude for r in pool]
            amplitudes_sorted = sorted(amplitudes)
            n = len(amplitudes_sorted)
            q75 = amplitudes_sorted[int(n * 0.75)]
            q25 = amplitudes_sorted[int(n * 0.25)]
            for r in pool:
                if r.amplitude >= q75:
                    r.amplitude = min(r.amplitude * 1.15, 1.0)
                elif r.amplitude <= q25:
                    r.amplitude = max(r.amplitude * 0.85, 0.0)

        # Interference suppression
        for r in pool:
            if r.amplitude < 0.15:
                r.amplitude = 0.0

        # Normalize to [0, 1]
        max_amp = max((r.amplitude for r in pool), default=1.0)
        if max_amp > 0:
            for r in pool:
                r.amplitude = r.amplitude / max_amp

        return pool, request
