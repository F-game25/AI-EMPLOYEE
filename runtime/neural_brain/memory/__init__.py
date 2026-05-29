"""Neural Brain memory subsystem (M2)."""
from __future__ import annotations

import threading

from neural_brain.memory.chroma_adapter import ChromaAdapter
from neural_brain.memory.embedding_provider import EmbeddingProvider
from neural_brain.memory.mem0_adapter import Mem0Adapter
from neural_brain.memory.memory_schemas import (
    MemoryFilter,
    MemoryItem,
    MemoryType,
    RecallHit,
    RecallResult,
)
from neural_brain.memory.neural_memory_manager import (
    GraphHook,
    NeuralMemoryManager,
)
from neural_brain.memory.reranker import CrossEncoderReranker

__all__ = [
    "ChromaAdapter",
    "CrossEncoderReranker",
    "EmbeddingProvider",
    "GraphHook",
    "Mem0Adapter",
    "MemoryFilter",
    "MemoryItem",
    "MemoryType",
    "NeuralMemoryManager",
    "RecallHit",
    "RecallResult",
    "get_memory",
]

_memory_instance: NeuralMemoryManager | None = None
_memory_lock = threading.Lock()


def get_memory() -> NeuralMemoryManager:
    """Return the process-wide NeuralMemoryManager singleton."""
    global _memory_instance
    if _memory_instance is None:
        with _memory_lock:
            if _memory_instance is None:
                from neural_brain.config import get_settings
                from neural_brain.api.node_bridge import emit
                settings = get_settings()
                embedder = EmbeddingProvider(settings.embed_model)
                chroma = ChromaAdapter(settings.chroma_dir, embedder)
                mem0 = Mem0Adapter(settings)
                _memory_instance = NeuralMemoryManager(
                    chroma=chroma,
                    mem0=mem0,
                    embedder=embedder,
                    bridge_emit=emit,
                )
    return _memory_instance
