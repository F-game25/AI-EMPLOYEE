from __future__ import annotations
import re

BANG_MAP: dict[str, list[str]] = {
    '!web':      ['searxng'],
    '!news':     ['searxng'],
    '!memory':   ['local_memory', 'mem0'],
    '!rag':      ['local_memory'],
    '!graph':    ['neo4j'],
    '!code':     ['codebase'],
    '!doc':      ['docs'],
    '!task':     ['tasks'],
    '!agent':    ['agents'],
    '!tool':     ['tools'],
    '!log':      ['logs'],
    '!test':     ['tests'],
    '!artifact': ['artifacts'],
}


class BangParser:
    """Extract !bang tokens from a query and map them to engine names."""

    _BANG_RE = re.compile(r'!(?:web|news|memory|rag|graph|code|doc|task|agent|tool|log|test|artifact)\b')

    def parse(self, query: str) -> tuple[str, list[str]]:
        """Return (cleaned_query, list_of_engine_names). Empty list = all engines."""
        found_bangs = self._BANG_RE.findall(query)
        cleaned = self._BANG_RE.sub('', query).strip()
        # Collapse multiple spaces
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)

        if not found_bangs:
            return cleaned, []

        engines: list[str] = []
        seen: set[str] = set()
        for bang in found_bangs:
            for eng in BANG_MAP.get(bang, []):
                if eng not in seen:
                    engines.append(eng)
                    seen.add(eng)

        return cleaned, engines
