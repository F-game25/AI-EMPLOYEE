"""Real semantic embeddings using sentence-transformers."""
import logging
import numpy as np
from typing import List, Optional

logger = logging.getLogger(__name__)

# Try to load sentence-transformers, fallback to hash-based if unavailable
try:
    from sentence_transformers import SentenceTransformer
    _EMBEDDINGS_AVAILABLE = True
    _model = SentenceTransformer("all-MiniLM-L6-v2")
except ImportError:
    _EMBEDDINGS_AVAILABLE = False
    _model = None
    logger.warning("sentence-transformers not installed; using hash-based embeddings (degraded mode)")


class EmbeddingsManager:
    """Generate and manage semantic embeddings."""

    def __init__(self):
        self.model = _model
        self.embeddings_available = _EMBEDDINGS_AVAILABLE

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a text string."""
        if not text:
            return [0.0] * 384  # Default dimension for all-MiniLM-L6-v2

        if self.embeddings_available and self.model:
            try:
                embedding = self.model.encode(text, convert_to_tensor=False)
                return embedding.tolist()
            except Exception as e:
                logger.error(f"Failed to embed text: {e}")
                return self._hash_based_embedding(text)
        else:
            return self._hash_based_embedding(text)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        if self.embeddings_available and self.model:
            try:
                embeddings = self.model.encode(texts, convert_to_tensor=False)
                return embeddings.tolist()
            except Exception as e:
                logger.error(f"Failed to embed texts: {e}")
                return [self._hash_based_embedding(text) for text in texts]
        else:
            return [self._hash_based_embedding(text) for text in texts]

    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Calculate cosine similarity between two embeddings."""
        try:
            arr1 = np.array(embedding1)
            arr2 = np.array(embedding2)

            # Cosine similarity
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

        # Generate hash-based "embedding" (not semantic, but deterministic)
        hash_obj = hashlib.sha256(text.encode())
        hash_hex = hash_obj.hexdigest()

        # Convert hex to 384-dim vector (matching all-MiniLM-L6-v2 output)
        embedding = []
        for i in range(0, 384 * 2, 2):  # 2 chars per byte, 384 bytes needed
            idx = i % len(hash_hex)
            byte_val = int(hash_hex[idx:idx+2], 16) if idx + 2 <= len(hash_hex) else 0
            embedding.append((byte_val / 255.0) * 2.0 - 1.0)  # Normalize to [-1, 1]

        return embedding[:384]

    def get_mode(self) -> str:
        """Get current embedding mode."""
        return "semantic" if self.embeddings_available else "hash-based (degraded)"


def get_embeddings_manager() -> EmbeddingsManager:
    """Get global embeddings manager instance."""
    return EmbeddingsManager()
