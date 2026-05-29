"""Concept extraction.

Heuristic-only by default; an optional LLM hook re-ranks candidates when
the heuristic stage produces more than ``max_concepts``. The LLM call is
optional so M2 can wire this up before M5's model router exists.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import OrderedDict
from typing import Callable

logger = logging.getLogger(__name__)

# Capture order matters: TitleCase phrases first, then hyphenated tech words,
# then short ALL-CAPS acronyms.
_TITLECASE_PHRASE = re.compile(r"\b[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*\b")
_HYPHENATED = re.compile(r"\b[a-zA-Z]+(?:-[a-zA-Z]+)+\b")
_ACRONYM = re.compile(r"\b[A-Z]{2,6}\b")

# Common stopwords / glue words that show up as TitleCase or ALL-CAPS but
# carry no semantic value as a concept.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "and", "or", "but", "if", "then", "else", "for",
        "to", "of", "in", "on", "at", "by", "with", "from", "into", "as",
        "is", "was", "are", "were", "be", "been", "being", "do", "does",
        "did", "have", "has", "had", "this", "that", "these", "those",
        "it", "its", "we", "us", "our", "you", "your", "they", "their",
        "i", "me", "my", "he", "she", "him", "her",
        # Common ALL-CAPS noise.
        "OK", "URL", "API", "TBD", "TODO", "FAQ", "AKA", "ETC",
        "AM", "PM", "ID", "OS", "UI", "UX", "IT",
    }
)

_CACHE_CAP = 1024


class ConceptExtractor:
    def __init__(self, llm_call: Callable[[str], str] | None = None) -> None:
        self._llm = llm_call
        # OrderedDict gives O(1) LRU eviction.
        self._cache: OrderedDict[str, list[str]] = OrderedDict()

    # ── public ────────────────────────────────────────────────────────────
    def extract(self, text: str, *, max_concepts: int = 5) -> list[str]:
        if not text or not isinstance(text, str):
            return []

        key = hashlib.sha256(f"{max_concepts}|{text}".encode("utf-8")).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return list(self._cache[key])

        candidates = self._heuristic_candidates(text, cap=max_concepts * 2)

        if self._llm is not None and len(candidates) > max_concepts:
            ranked = self._llm_rerank(candidates, max_concepts)
            chosen = ranked if ranked else candidates[:max_concepts]
        else:
            chosen = candidates[:max_concepts]

        self._cache_put(key, chosen)
        return list(chosen)

    # ── internal ──────────────────────────────────────────────────────────
    def _heuristic_candidates(self, text: str, *, cap: int) -> list[str]:
        seen_lower: set[str] = set()
        out: list[str] = []

        def _add(token: str) -> None:
            t = token.strip()
            if len(t) < 3:
                return
            if t.lower() in _STOPWORDS or t in _STOPWORDS:
                return
            low = t.lower()
            if low in seen_lower:
                return
            seen_lower.add(low)
            out.append(t)

        for m in _TITLECASE_PHRASE.finditer(text):
            _add(m.group(0))
        for m in _HYPHENATED.finditer(text):
            _add(m.group(0))
        for m in _ACRONYM.finditer(text):
            _add(m.group(0))

        return out[:cap]

    def _llm_rerank(self, candidates: list[str], max_concepts: int) -> list[str]:
        prompt = (
            f"Return a JSON list of the {max_concepts} most semantically "
            f"meaningful concepts from this set: {candidates}. "
            "Just the JSON array, no commentary."
        )
        try:
            raw = self._llm(prompt)  # type: ignore[misc]
        except Exception as e:
            logger.warning("LLM rerank failed: %s", e)
            return []

        return _safe_parse_json_list(raw, max_concepts)

    def _cache_put(self, key: str, value: list[str]) -> None:
        self._cache[key] = list(value)
        self._cache.move_to_end(key)
        while len(self._cache) > _CACHE_CAP:
            self._cache.popitem(last=False)


def _safe_parse_json_list(raw: str, max_concepts: int) -> list[str]:
    if not raw:
        return []
    # Tolerate fences / trailing prose.
    s = raw.strip()
    # Slice from first `[` to last `]` to survive minor LLM noise.
    a, b = s.find("["), s.rfind("]")
    if a == -1 or b == -1 or b <= a:
        return []
    try:
        parsed = json.loads(s[a : b + 1])
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out = [str(x).strip() for x in parsed if isinstance(x, (str, int, float)) and str(x).strip()]
    return out[:max_concepts]
