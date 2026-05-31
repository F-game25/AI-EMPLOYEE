"""BM25Okapi scorer — pure Python, no external deps."""
from __future__ import annotations
import math
import re
from collections import Counter


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class BM25:
    """BM25Okapi scoring over a fixed corpus of strings."""

    k1: float = 1.5
    b: float = 0.75

    def __init__(self, corpus: list[str]) -> None:
        self._tokenized = [_tokenize(doc) for doc in corpus]
        self._n = len(self._tokenized)
        self._avgdl = (
            sum(len(d) for d in self._tokenized) / self._n if self._n else 1.0
        )
        self._df: dict[str, int] = {}
        for doc in self._tokenized:
            for term in set(doc):
                self._df[term] = self._df.get(term, 0) + 1

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log((self._n - df + 0.5) / (df + 0.5) + 1.0)

    def scores(self, query: str) -> list[float]:
        if self._n == 0:
            return []
        q_terms = _tokenize(query)
        result = [0.0] * self._n
        for term in q_terms:
            idf = self._idf(term)
            for i, doc in enumerate(self._tokenized):
                tf = doc.count(term)
                if tf == 0:
                    continue
                dl = len(doc)
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
                result[i] += idf * (tf * (self.k1 + 1)) / denom
        return result
