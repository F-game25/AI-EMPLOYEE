from __future__ import annotations
import asyncio
import hashlib
import logging
from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

SEARXNG_URL = 'http://localhost:8080/search'


class SearxngEngine:
    name = 'searxng'
    source_type = 'web'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.wait_for(
                self._fetch(request),
                timeout=request.timeout_ms / 1000
            )
        except Exception as exc:
            log.debug('SearxngEngine error: %s', exc)
            return []

    async def _fetch(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        params = {'q': request.query, 'format': 'json'}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=request.timeout_ms / 1000) as client:
                resp = await client.get(SEARXNG_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except ImportError:
            # Fallback: urllib in thread executor
            data = await asyncio.get_event_loop().run_in_executor(None, self._urllib_fetch, params)

        results = []
        for item in data.get('results', [])[:request.max_results_per_engine]:
            uid = hashlib.md5(item.get('url', item.get('title', '')).encode()).hexdigest()[:12]
            content = (item.get('content') or '')[:500]
            score = float(item.get('score', 0.5))
            results.append(NormalizedSearchResult(
                id=uid,
                title=item.get('title', ''),
                content=content,
                url=item.get('url', ''),
                source_type='web',
                engine=self.name,
                score=min(max(score, 0.0), 1.0),
                metadata={'engines': item.get('engines', [])},
            ))
        return results

    def _urllib_fetch(self, params: dict) -> dict:
        import urllib.request, urllib.parse, json as _json
        url = SEARXNG_URL + '?' + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=5) as r:
            return _json.loads(r.read())
