from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
_VECTOR_STORE_PATH = os.path.join(_REPO_ROOT, 'runtime', 'memory', 'vector_store.json')

# TODO: replace with cosine similarity when embeddings available


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


class Mem0MemoryEngine:
    name = 'mem0'
    source_type = 'memory'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('Mem0MemoryEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        tokens = request.query.lower().split()
        results: list[NormalizedSearchResult] = []

        if not os.path.exists(_VECTOR_STORE_PATH):
            return results

        try:
            with open(_VECTOR_STORE_PATH) as f:
                data = json.load(f)
        except Exception as exc:
            log.debug('vector_store.json read error: %s', exc)
            return results

        entries = data if isinstance(data, list) else data.get('entries', data.get('memories', []))
        if isinstance(data, dict) and not isinstance(entries, list):
            # Try top-level keys as entries
            entries = [{'id': k, 'content': str(v)} for k, v in data.items()]

        for entry in entries[:request.max_results_per_engine * 2]:
            if not isinstance(entry, dict):
                continue
            if request.tenant_id and entry.get('tenant_id', '') not in ('', request.tenant_id):
                continue
            title = entry.get('title', entry.get('id', 'memory'))
            content = str(entry.get('content', entry.get('text', '')))[:500]
            combined = f"{title} {content}"
            score = _keyword_score(tokens, combined)
            if score == 0.0:
                continue
            uid = hashlib.md5(f"mem0:{entry.get('id', title)}".encode()).hexdigest()[:12]
            results.append(NormalizedSearchResult(
                id=uid, title=str(title), content=content,
                url='runtime/memory/vector_store.json',
                source_type='memory', engine=self.name, score=score,
                tenant_id=entry.get('tenant_id', ''),
                metadata={'entry_id': entry.get('id', '')},
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]
