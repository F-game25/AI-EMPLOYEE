from __future__ import annotations
import asyncio
import glob
import hashlib
import json
import logging
import os

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
_CODE_INDEX_DIR = os.path.join(_REPO_ROOT, 'state', 'code_index')

# Module-level cache built after first call
_INDEX_CACHE: list[dict] | None = None


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


def _build_live_index() -> list[dict]:
    """Scan repo for .py and .js files; read first 50 lines of each."""
    index = []
    patterns = ['**/*.py', '**/*.js']
    skip_dirs = {'.git', 'node_modules', '__pycache__', 'dist', '.venv', 'venv',
                 'src-tauri', '.claude'}
    for pattern in patterns:
        for path in glob.glob(os.path.join(_REPO_ROOT, pattern), recursive=True):
            # Skip unwanted dirs
            parts = path.replace(_REPO_ROOT, '').split(os.sep)
            if any(p in skip_dirs for p in parts):
                continue
            rel = os.path.relpath(path, _REPO_ROOT)
            try:
                with open(path, encoding='utf-8', errors='ignore') as f:
                    lines = [f.readline() for _ in range(50)]
                snippet = ''.join(lines)[:500]
                index.append({'path': rel, 'snippet': snippet})
            except Exception:
                continue
    return index


class CodebaseSearchEngine:
    name = 'codebase'
    source_type = 'code_file'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('CodebaseSearchEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        global _INDEX_CACHE
        tokens = request.query.lower().split()
        results: list[NormalizedSearchResult] = []

        # Try JSON index files first
        if os.path.isdir(_CODE_INDEX_DIR):
            entries = self._load_json_index()
        else:
            if _INDEX_CACHE is None:
                _INDEX_CACHE = _build_live_index()
            entries = [{'path': e['path'], 'content': e['snippet']} for e in _INDEX_CACHE]

        for entry in entries:
            path = entry.get('path', entry.get('file', ''))
            content = str(entry.get('content', entry.get('snippet', '')))[:500]
            combined = f"{path} {content}"
            score = _keyword_score(tokens, combined)
            if score == 0.0:
                continue
            uid = hashlib.md5(f"code:{path}".encode()).hexdigest()[:12]
            results.append(NormalizedSearchResult(
                id=uid, title=path, content=content, url=path,
                source_type='code_file', engine=self.name, score=score,
                metadata={'file': path},
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]

    def _load_json_index(self) -> list[dict]:
        entries = []
        for jf in glob.glob(os.path.join(_CODE_INDEX_DIR, '*.json')):
            try:
                with open(jf) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    entries.extend(data)
                elif isinstance(data, dict):
                    entries.append(data)
            except Exception:
                continue
        return entries
