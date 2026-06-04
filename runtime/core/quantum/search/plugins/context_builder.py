from __future__ import annotations
import uuid
from ..schema import NormalizedSearchResult, SearchRequest, ContextPack, IntentCandidate

_MODEL_MAP = {
    'critical': 'claude-opus-4-8',
    'complex':  'claude-sonnet-4-6',
    'medium':   'claude-haiku-4-5',
    'simple':   'claude-haiku-4-5',
}


class ContextBuilderPlugin:
    """Build a ContextPack from the amplified result pool."""

    async def process(
        self,
        pool: list[NormalizedSearchResult],
        request: SearchRequest,
    ) -> tuple[list[NormalizedSearchResult], SearchRequest]:
        # ContextBuilderPlugin.process is a no-op on the pool/request;
        # actual ContextPack construction happens in build_context_pack on the orchestrator.
        return pool, request

    def build(
        self,
        pool: list[NormalizedSearchResult],
        request: SearchRequest,
        engine_stats: dict,
        search_id: str | None = None,
    ) -> ContextPack:
        sorted_pool = sorted(pool, key=lambda r: r.amplitude, reverse=True)

        top_agents = [
            r.agent_id
            for r in sorted_pool
            if r.source_type == 'agent' and r.agent_id
        ][:3]

        top_tools = [
            r.title
            for r in sorted_pool
            if r.source_type == 'tool'
        ][:3]

        complexity = request.complexity or 'medium'
        suggested_model = _MODEL_MAP.get(complexity, 'claude-haiku-4-5')

        top10 = sorted_pool[:10]
        confidence = sum(r.amplitude for r in top10) / len(top10) if top10 else 0.0

        reasoning = self._build_reasoning(sorted_pool, request)

        intent = IntentCandidate(
            text=request.query,
            amplitude=confidence,
            rationale=reasoning,
        ) if request.query else None

        sid = search_id or f"{request.tenant_id}:{uuid.uuid4().hex[:8]}"

        return ContextPack(
            search_id=sid,
            query=request.query,
            intent=intent,
            candidates=sorted_pool,
            top_agents=top_agents,
            top_tools=top_tools,
            suggested_model=suggested_model,
            confidence=round(confidence, 4),
            reasoning=reasoning,
            engine_stats=engine_stats,
            tenant_id=request.tenant_id,
        )

    def _build_reasoning(self, pool: list[NormalizedSearchResult], request: SearchRequest) -> str:
        if not pool:
            return 'No results returned by any engine.'
        top = pool[0]
        engine_counts: dict[str, int] = {}
        for r in pool:
            engine_counts[r.engine] = engine_counts.get(r.engine, 0) + 1
        top_engine = max(engine_counts, key=engine_counts.__getitem__)
        return (
            f"Top result '{top.title}' from {top.engine} (amplitude={top.amplitude:.2f}). "
            f"Most results from {top_engine} ({engine_counts[top_engine]} results). "
            f"Complexity: {request.complexity}."
        )
