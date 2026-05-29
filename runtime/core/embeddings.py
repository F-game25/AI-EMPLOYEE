"""Real semantic embeddings using sentence-transformers."""
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Phase 7B: defer heavy model load to first embed call, not import time.
# sentence-transformers loads an ~80 MB model; numpy import is also deferred
# so that importing this module at startup costs nothing.
_EMBEDDINGS_AVAILABLE: Optional[bool] = None  # None = not yet checked
_model = None


def _ensure_model():
    """Load sentence-transformers model on first use (lazy init)."""
    global _EMBEDDINGS_AVAILABLE, _model
    if _EMBEDDINGS_AVAILABLE is not None:
        return
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        _EMBEDDINGS_AVAILABLE = True
    except (ImportError, Exception) as e:
        _EMBEDDINGS_AVAILABLE = False
        _model = None
        logger.warning("sentence-transformers unavailable; using hash-based embeddings (degraded mode): %s", e)


class EmbeddingsManager:
    """Generate and manage semantic embeddings."""

    def __init__(self):
        pass  # model loaded lazily on first embed call

    @property
    def model(self):
        _ensure_model()
        return _model

    @property
    def embeddings_available(self):
        _ensure_model()
        return bool(_EMBEDDINGS_AVAILABLE)

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a text string."""
        if not text:
            return [0.0] * 384  # Default dimension for all-MiniLM-L6-v2

        _ensure_model()
        if _EMBEDDINGS_AVAILABLE and _model:
            try:
                embedding = _model.encode(text, convert_to_tensor=False)
                return embedding.tolist()
            except Exception as e:
                logger.error(f"Failed to embed text: {e}")
                return self._hash_based_embedding(text)
        return self._hash_based_embedding(text)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        _ensure_model()
        if _EMBEDDINGS_AVAILABLE and _model:
            try:
                embeddings = _model.encode(texts, convert_to_tensor=False)
                return embeddings.tolist()
            except Exception as e:
                logger.error(f"Failed to embed texts: {e}")
                return [self._hash_based_embedding(text) for text in texts]
        return [self._hash_based_embedding(text) for text in texts]

    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Calculate cosine similarity between two embeddings."""
        try:
            import numpy as np
            arr1 = np.array(embedding1)
            arr2 = np.array(embedding2)
            dot_product = np.dot(arr1, arr2)
            norm1 = np.linalg.norm(arr1)
            norm2 = np.linalg.norm(arr2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(dot_product / (norm1 * norm2))
        except Exception as e:
            logger.error(f"Failed to calculate similarity: {e}")
            return 0.0

    def find_most_similar(self, query_embedding: List[float], candidates: List[dict]) -> Optional[dict]:
        """Find the most similar candidate to a query embedding."""
        if not candidates:
            return None
        best_match = None
        best_score = -1.0
        for candidate in candidates:
            if "embedding" not in candidate:
                continue
            score = self.similarity(query_embedding, candidate["embedding"])
            if score > best_score:
                best_score = score
                best_match = candidate
        return best_match if best_score > 0.5 else None

    def _hash_based_embedding(self, text: str) -> List[float]:
        """Fallback: hash-based embedding for text (degraded mode)."""
        import hashlib
        hash_obj = hashlib.sha256(text.encode())
        hash_hex = hash_obj.hexdigest()
        embedding = []
        for i in range(0, 384 * 2, 2):
            idx = i % len(hash_hex)
            byte_val = int(hash_hex[idx:idx+2], 16) if idx + 2 <= len(hash_hex) else 0
            embedding.append((byte_val / 255.0) * 2.0 - 1.0)
        return embedding[:384]

    def get_mode(self) -> str:
        """Get current embedding mode."""
        return "semantic" if self.embeddings_available else "hash-based (degraded)"


def get_embeddings_manager() -> EmbeddingsManager:
    """Get global embeddings manager instance."""
    return EmbeddingsManager()
