"""Singleton sentence-transformers wrapper with lazy load + thread-safe init."""
from __future__ import annotations

import logging
import threading
from typing import Any

from neural_brain.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    _instance: "EmbeddingProvider | None" = None
    _lock = threading.Lock()

    def __init__(self, model_name: str) -> None:
        # Use get() — direct construction is allowed but discouraged.
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover - import guard
            raise RuntimeError(
                "sentence-transformers not installed; "
                "pip install -r runtime/requirements-extras.txt"
            ) from e

        self._model_name = model_name
        self._model: Any = SentenceTransformer(model_name)
        try:
            self._dim = int(self._model.get_sentence_embedding_dimension())
        except Exception:
            # Fallback: encode a probe vector to determine dimension.
            probe = self._model.encode(["_"], convert_to_numpy=True)
            self._dim = int(probe.shape[-1])

    @classmethod
    def get(cls) -> "EmbeddingProvider":
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                model_name = get_settings().embed_model
                cls._instance = cls(model_name)
        return cls._instance

    def encode(
        self,
        texts: list[str] | str,
        *,
        normalize: bool = True,
    ) -> list[list[float]]:
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return []
        arr = self._model.encode(
            texts,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
        )
        return arr.tolist()

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name
