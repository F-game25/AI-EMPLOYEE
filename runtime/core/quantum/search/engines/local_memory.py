from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))


def _state_dir() -> str:
    return os.environ.get('STATE_DIR', os.path.join(_REPO_ROOT, 'state'))


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


class LocalMemoryEngine:
    name = 'local_memory'
    source_type = 'rag'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('LocalMemoryEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        tokens = request.query.lower().split()
        results: list[NormalizedSearchResult] = []
        sd = _state_dir()

        # Knowledge store
        ks_path = os.path.join(sd, 'knowledge_store.json')
        if os.path.exists(ks_path):
            try:
                with open(ks_path) as f:
                    data = json.load(f)
                results.extend(self._search_knowledge(data, tokens, request))
            except Exception as exc:
                log.debug('knowledge_store read error: %s', exc)

        # Bus events (last 200 lines)
        bus_path = os.path.join(sd, 'bus.jsonl')
        if os.path.exists(bus_path):
            try:
                results.extend(self._search_bus(bus_path, tokens, request))
            except Exception as exc:
                log.debug('bus.jsonl read error: %s', exc)

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]

    def _search_knowledge(self, data: dict, tokens: list[str], request: SearchRequest) -> list[NormalizedSearchResult]:
        out = []
        topics = data.get('topics', {})
        for topic, entries in topics.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                # Tenant filter
                if request.tenant_id and entry.get('tenant_id', '') not in ('', request.tenant_id):
                    continue
                title = entry.get('title', topic)
                content = str(entry.get('content', entry.get('summary', '')))[:500]
                combined = f"{topic} {title} {content}"
                score = _keyword_score(tokens, combined)
                if score == 0.0:
                    continue
                uid = hashlib.md5(f"ks:{topic}:{title}".encode()).hexdigest()[:12]
                out.append(NormalizedSearchResult(
                    id=uid, title=title, content=content,
                    url=f'state/knowledge_store.json#{topic}',
                    source_type='rag', engine=self.name, score=score,
                    tenant_id=entry.get('tenant_id', ''),
                ))
        return out

    def _search_bus(self, bus_path: str, tokens: list[str], request: SearchRequest) -> list[NormalizedSearchResult]:
        out = []
        with open(bus_path) as f:
            lines = f.readlines()
        for line in lines[-200:]:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                continue
            channel = event.get('channel', '')
            msg = event.get('message', {})
            content = json.dumps(msg)[:500]
            score = _keyword_score(tokens, content)
            if score == 0.0:
                continue
            ts = event.get('timestamp', '')
            uid = hashlib.md5(f"bus:{ts}:{content[:50]}".encode()).hexdigest()[:12]
            out.append(NormalizedSearchResult(
                id=uid, title=f'[{channel}] {msg.get("event", "event")}',
                content=content, url='state/bus.jsonl',
                source_type='event_log', engine=self.name, score=score,
                metadata={'timestamp': ts},
            ))
        return out
