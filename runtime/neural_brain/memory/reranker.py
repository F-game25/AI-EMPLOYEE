"""Cross-encoder reranker — off by default, lazy load."""
from __future__ import annotations

import logging
from typing import Any

from neural_brain.memory.memory_schemas import RecallHit

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        enabled: bool = False,
    ) -> None:
        self._model_name = model_name
        self._enabled = enabled
        self._model: Any = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers required for reranker"
            ) from e
        self._model = CrossEncoder(self._model_name)

    def rerank(
        self,
        query: str,
        hits: list[RecallHit],
        top_k: int | None = None,
    ) -> list[RecallHit]:
        if not hits:
            return []
        if not self._enabled:
            return hits[: top_k] if top_k else hits

        try:
            self._ensure_loaded()
            pairs = [(query, h.text) for h in hits]
            scores = self._model.predict(pairs)
            scored = list(zip(hits, [float(s) for s in scores]))
            scored.sort(key=lambda x: x[1], reverse=True)
            # Normalize cross-encoder scores to a 0-1 band best-effort.
            if scored:
                lo = min(s for _, s in scored)
                hi = max(s for _, s in scored)
                rng = hi - lo if hi > lo else 1.0
            reordered: list[RecallHit] = []
            for h, s in scored:
                norm = (s - lo) / rng if rng else 0.5
                reordered.append(h.model_copy(update={"score": max(0.0, min(1.0, norm))}))
            return reordered[: top_k] if top_k else reordered
        except Exception as e:
            logger.warning("rerank failed; falling back to original order: %s", e)
            return hits[: top_k] if top_k else hits
