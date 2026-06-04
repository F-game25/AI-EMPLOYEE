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


class ExecutionLogEngine:
    name = 'logs'
    source_type = 'event_log'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('ExecutionLogEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        tokens = request.query.lower().split()
        results: list[NormalizedSearchResult] = []
        sd = _state_dir()
        bus_path = os.path.join(sd, 'bus.jsonl')

        if not os.path.exists(bus_path):
            return results

        try:
            with open(bus_path) as f:
                lines = f.readlines()
        except Exception as exc:
            log.debug('ExecutionLogEngine bus read error: %s', exc)
            return results

        for line in lines[-500:]:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue

            channel = ev.get('channel', '')
            msg = ev.get('message', {})
            ts = ev.get('timestamp', '')
            content = json.dumps(msg)[:500]
            score = _keyword_score(tokens, content)
            if score == 0.0:
                continue

            uid = hashlib.md5(f"log:{ts}:{content[:40]}".encode()).hexdigest()[:12]
            event_name = msg.get('event', channel) if isinstance(msg, dict) else channel
            results.append(NormalizedSearchResult(
                id=uid,
                title=f'[{channel}] {event_name}',
                content=content,
                url='state/bus.jsonl',
                source_type='event_log',
                engine=self.name,
                score=score,
                metadata={'timestamp': ts, 'channel': channel},
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]
