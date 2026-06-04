from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))

_DOC_SOURCES = [
    ('runtime/config/agent_capabilities.json', 'json'),
    ('runtime/config/agent_behavior_templates.json', 'json'),
    ('runtime/config/skills_library.json', 'json'),
    ('CLAUDE.md', 'text'),
]


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


class DocsSearchEngine:
    name = 'docs'
    source_type = 'doc'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('DocsSearchEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        tokens = request.query.lower().split()
        results: list[NormalizedSearchResult] = []

        for rel_path, fmt in _DOC_SOURCES:
            abs_path = os.path.join(_REPO_ROOT, rel_path)
            if not os.path.exists(abs_path):
                continue
            try:
                with open(abs_path, encoding='utf-8', errors='ignore') as f:
                    raw = f.read()
            except Exception as exc:
                log.debug('DocsSearchEngine read error %s: %s', rel_path, exc)
                continue

            if fmt == 'json':
                results.extend(self._search_json(raw, rel_path, tokens, request))
            else:
                results.extend(self._search_text(raw, rel_path, tokens))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]

    def _search_json(self, raw: str, path: str, tokens: list[str], request: SearchRequest) -> list[NormalizedSearchResult]:
        out = []
        try:
            data = json.loads(raw)
        except Exception:
            return self._search_text(raw, path, tokens)

        # Flatten top-level dict entries
        items = data if isinstance(data, list) else (
            list(data.get('agents', data).items()) if isinstance(data, dict) else []
        )
        if isinstance(data, dict) and 'agents' not in data:
            items = list(data.items())

        for item in items[:request.max_results_per_engine * 2]:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                key, val = item
                title = str(key)
                content = json.dumps(val)[:500] if not isinstance(val, str) else val[:500]
            elif isinstance(item, dict):
                title = str(item.get('name', item.get('id', path)))
                content = json.dumps(item)[:500]
            else:
                continue

            score = _keyword_score(tokens, f"{title} {content}")
            if score == 0.0:
                continue
            uid = hashlib.md5(f"doc:{path}:{title}".encode()).hexdigest()[:12]
            out.append(NormalizedSearchResult(
                id=uid, title=title, content=content, url=path,
                source_type='doc', engine=self.name, score=score,
                metadata={'source': path},
            ))
        return out

    def _search_text(self, raw: str, path: str, tokens: list[str]) -> list[NormalizedSearchResult]:
        # Split into 500-char chunks, keyword-search each
        out = []
        chunks = [raw[i:i+500] for i in range(0, len(raw), 500)]
        for i, chunk in enumerate(chunks):
            score = _keyword_score(tokens, chunk)
            if score == 0.0:
                continue
            uid = hashlib.md5(f"doc:{path}:chunk{i}".encode()).hexdigest()[:12]
            out.append(NormalizedSearchResult(
                id=uid, title=f'{os.path.basename(path)} §{i+1}',
                content=chunk, url=path,
                source_type='doc', engine=self.name, score=score,
                metadata={'source': path, 'chunk': i},
            ))
        return out
