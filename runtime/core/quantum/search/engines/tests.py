from __future__ import annotations
import asyncio
import glob
import hashlib
import logging
import os

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
_TESTS_DIR = os.path.join(_REPO_ROOT, 'tests')


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


class TestLogEngine:
    name = 'tests'
    source_type = 'test_log'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('TestLogEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        tokens = request.query.lower().split()
        results: list[NormalizedSearchResult] = []

        if not os.path.isdir(_TESTS_DIR):
            return results

        for fpath in glob.glob(os.path.join(_TESTS_DIR, '**/*.py'), recursive=True):
            rel = os.path.relpath(fpath, _REPO_ROOT)
            try:
                with open(fpath, encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue

            # Score based on filename + content
            combined = f"{rel} {content}"
            score = _keyword_score(tokens, combined)
            if score == 0.0:
                continue

            # Extract test function names for title
            import re
            test_names = re.findall(r'def (test_\w+)', content)
            title = rel
            if test_names:
                title = f"{rel} ({', '.join(test_names[:3])}{'...' if len(test_names) > 3 else ''})"

            uid = hashlib.md5(f"test:{rel}".encode()).hexdigest()[:12]
            snippet = content[:500]
            results.append(NormalizedSearchResult(
                id=uid,
                title=title,
                content=snippet,
                url=rel,
                source_type='test_log',
                engine=self.name,
                score=score,
                metadata={'file': rel, 'test_count': len(test_names)},
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]
