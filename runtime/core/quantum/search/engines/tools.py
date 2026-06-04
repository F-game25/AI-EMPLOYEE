from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import re

from ..schema import NormalizedSearchResult, SearchRequest

log = logging.getLogger(__name__)

_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
_CATALOG_PATH = os.path.join(_REPO_ROOT, 'runtime', 'skills', 'catalog.py')


def _keyword_score(tokens: list[str], text: str) -> float:
    if not tokens:
        return 0.0
    text_lower = text.lower()
    hits = sum(1 for t in tokens if t in text_lower)
    return hits / len(tokens)


def _extract_tools_from_catalog(path: str) -> list[dict]:
    """Extract tool names and descriptions from catalog.py via regex."""
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            src = f.read()
    except Exception:
        return []
    tools = []
    # Match function defs or class defs that look like tools
    for m in re.finditer(
        r'(?:def|class)\s+(\w+Tool|\w+_tool|\w+_action|\w+Engine)\s*[\(:]',
        src, re.IGNORECASE
    ):
        name = m.group(1)
        # Try to find a docstring right after
        pos = m.end()
        doc_match = re.search(r'"""(.*?)"""', src[pos:pos+300], re.DOTALL)
        desc = doc_match.group(1).strip()[:200] if doc_match else ''
        tools.append({'name': name, 'description': desc, 'source': path})
    # Also match dict-style registrations
    for m in re.finditer(r'"(\w+)"\s*:\s*\{[^}]*"description"\s*:\s*"([^"]{0,200})"', src):
        tools.append({'name': m.group(1), 'description': m.group(2), 'source': path})
    return tools


class ToolRegistryEngine:
    name = 'tools'
    source_type = 'tool'

    async def search(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        try:
            return await asyncio.get_event_loop().run_in_executor(None, self._search_sync, request)
        except Exception as exc:
            log.debug('ToolRegistryEngine error: %s', exc)
            return []

    def _search_sync(self, request: SearchRequest) -> list[NormalizedSearchResult]:
        tokens = request.query.lower().split()
        tool_dicts = self._load_tools()
        results: list[NormalizedSearchResult] = []

        for tool in tool_dicts:
            name = tool.get('name', '')
            desc = tool.get('description', '')
            combined = f"{name} {desc}"
            score = _keyword_score(tokens, combined)
            if score == 0.0:
                continue
            uid = hashlib.md5(f"tool:{name}".encode()).hexdigest()[:12]
            results.append(NormalizedSearchResult(
                id=uid, title=name, content=desc[:500],
                url=tool.get('source', 'runtime/skills/catalog.py'),
                source_type='tool', engine=self.name, score=score,
                metadata={'tool_name': name},
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:request.max_results_per_engine]

    def _load_tools(self) -> list[dict]:
        # Try live import first
        try:
            import sys
            sys.path.insert(0, os.path.join(_REPO_ROOT, 'runtime'))
            from core.tool_registry import list_tools  # type: ignore
            return [{'name': t.get('name', ''), 'description': t.get('description', '')}
                    for t in list_tools()]
        except Exception:
            pass

        # Fallback: parse catalog.py
        if os.path.exists(_CATALOG_PATH):
            return _extract_tools_from_catalog(_CATALOG_PATH)

        # Last resort: scan skills definitions directory
        tools = []
        defs_dir = os.path.join(_REPO_ROOT, 'runtime', 'skills', 'definitions')
        if os.path.isdir(defs_dir):
            for fname in os.listdir(defs_dir):
                name = os.path.splitext(fname)[0]
                tools.append({'name': name, 'description': '', 'source': f'runtime/skills/definitions/{fname}'})
        return tools
