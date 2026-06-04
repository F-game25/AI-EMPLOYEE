from __future__ import annotations
import asyncio
import logging
import time
import uuid

from .schema import SearchRequest, NormalizedSearchResult, ContextPack
from .registry import EngineRegistry
from .bang import BangParser

log = logging.getLogger(__name__)


def _default_plugins() -> list:
    from .plugins.query_cleaner import QueryCleanerPlugin
    from .plugins.bang_parser import BangParserPlugin
    from .plugins.deduplicator import DeduplicatorPlugin
    from .plugins.quantum_amplifier import QuantumAmplifierPlugin
    from .plugins.context_builder import ContextBuilderPlugin
    # BangParser MUST run before QueryCleaner so bangs are extracted before
    # the cleaner strips leading punctuation like '!'
    return [
        BangParserPlugin(),
        QueryCleanerPlugin(),
        DeduplicatorPlugin(),
        QuantumAmplifierPlugin(),
        ContextBuilderPlugin(),
    ]


class SearchOrchestrator:
    def __init__(self, registry: EngineRegistry | None = None, plugins: list | None = None) -> None:
        self._registry = registry or EngineRegistry()
        self._plugins = plugins or _default_plugins()
        self._bang = BangParser()

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        """Run full search pipeline. Returns results sorted by amplitude descending."""
        pool: list[NormalizedSearchResult] = []
        engine_stats: dict[str, dict] = {}

        # --- Pre-pipeline: QueryCleaner + BangParser ---
        pre_plugins = [p for p in self._plugins if hasattr(p, 'process') and
                       type(p).__name__ in ('QueryCleanerPlugin', 'BangParserPlugin')]
        for plugin in pre_plugins:
            pool, request = await plugin.process(pool, request)

        # --- Fan-out to engines ---
        engines = self._registry.get_engines(request.bangs or [])
        if request.engine_filter:
            engines = {k: v for k, v in engines.items() if k in request.engine_filter}

        async def _run_engine(name: str, engine) -> tuple[str, list[NormalizedSearchResult], float, str | None]:
            t0 = time.monotonic()
            error = None
            try:
                results = await asyncio.wait_for(
                    engine.search(request),
                    timeout=request.timeout_ms / 1000
                )
            except asyncio.TimeoutError:
                results = []
                error = 'timeout'
            except Exception as exc:
                results = []
                error = str(exc)
                log.debug('Engine %s raised: %s', name, exc)
            latency_ms = (time.monotonic() - t0) * 1000
            return name, results, latency_ms, error

        tasks = [_run_engine(name, eng) for name, eng in engines.items()]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        for item in gathered:
            if isinstance(item, Exception):
                log.debug('Engine task raised: %s', item)
                continue
            name, results, latency_ms, error = item
            engine_stats[name] = {
                'count': len(results),
                'latency_ms': round(latency_ms, 1),
                'error': error,
            }
            pool.extend(results)

        # --- Post-pipeline: Deduplicator, QuantumAmplifier, ContextBuilder (pass-through) ---
        post_plugins = [p for p in self._plugins if hasattr(p, 'process') and
                        type(p).__name__ in ('DeduplicatorPlugin', 'QuantumAmplifierPlugin', 'ContextBuilderPlugin')]
        for plugin in post_plugins:
            pool, request = await plugin.process(pool, request)

        pool.sort(key=lambda r: r.amplitude, reverse=True)
        return pool

    async def build_context_pack(self, request: SearchRequest) -> ContextPack:
        """Run search then build ContextPack."""
        search_id = f"{request.tenant_id}:{uuid.uuid4().hex[:8]}"

        pool: list[NormalizedSearchResult] = []
        engine_stats: dict[str, dict] = {}

        # Pre-pipeline
        pre_plugins = [p for p in self._plugins if hasattr(p, 'process') and
                       type(p).__name__ in ('QueryCleanerPlugin', 'BangParserPlugin')]
        for plugin in pre_plugins:
            pool, request = await plugin.process(pool, request)

        # Fan-out
        engines = self._registry.get_engines(request.bangs or [])
        if request.engine_filter:
            engines = {k: v for k, v in engines.items() if k in request.engine_filter}

        async def _run_engine(name: str, engine) -> tuple[str, list[NormalizedSearchResult], float, str | None]:
            t0 = time.monotonic()
            error = None
            try:
                results = await asyncio.wait_for(
                    engine.search(request),
                    timeout=request.timeout_ms / 1000
                )
            except asyncio.TimeoutError:
                results = []
                error = 'timeout'
            except Exception as exc:
                results = []
                error = str(exc)
            latency_ms = (time.monotonic() - t0) * 1000
            return name, results, latency_ms, error

        tasks = [_run_engine(name, eng) for name, eng in engines.items()]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        for item in gathered:
            if isinstance(item, Exception):
                continue
            name, results, latency_ms, error = item
            engine_stats[name] = {
                'count': len(results),
                'latency_ms': round(latency_ms, 1),
                'error': error,
            }
            pool.extend(results)

        # Post-pipeline
        post_plugins = [p for p in self._plugins if hasattr(p, 'process') and
                        type(p).__name__ in ('DeduplicatorPlugin', 'QuantumAmplifierPlugin')]
        for plugin in post_plugins:
            pool, request = await plugin.process(pool, request)

        pool.sort(key=lambda r: r.amplitude, reverse=True)

        # Build ContextPack via ContextBuilderPlugin
        builder = next(
            (p for p in self._plugins if type(p).__name__ == 'ContextBuilderPlugin'),
            None
        )
        if builder is None:
            from .plugins.context_builder import ContextBuilderPlugin
            builder = ContextBuilderPlugin()

        return builder.build(pool, request, engine_stats, search_id)
