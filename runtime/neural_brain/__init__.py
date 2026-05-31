"""Neural Brain — LangGraph + Mem0 + Neo4j cognitive subsystem.

Public surface (renamed per project convention; underlying libs are an
implementation detail callers should not depend on):

    ConsciousnessEngine     — top-level orchestrator (think / recall / remember)
    NeuralMemoryManager     — unified vector + facts + graph memory
    BrainGraph              — Neo4j-backed knowledge graph
    ModelArchitectureRouter — routes across LLM/SLM/MoE/VLM/MLM/LAM/LCM/SAM

Lazy-import to avoid pulling heavy deps when the package is referenced from
non-Neural-Brain code paths.
"""
from __future__ import annotations

__all__ = [
    "ConsciousnessEngine",
    "NeuralMemoryManager",
    "BrainGraph",
    "ModelArchitectureRouter",
    "get_settings",
]


def __getattr__(name: str):  # PEP 562 lazy attribute access
    if name == "ConsciousnessEngine":
        from neural_brain.core.consciousness_engine import ConsciousnessEngine
        return ConsciousnessEngine
    if name == "NeuralMemoryManager":
        from neural_brain.memory.neural_memory_manager import NeuralMemoryManager
        return NeuralMemoryManager
    if name == "BrainGraph":
        from neural_brain.graph.brain_graph import BrainGraph
        return BrainGraph
    if name == "ModelArchitectureRouter":
        from neural_brain.models.model_architecture_router import ModelArchitectureRouter
        return ModelArchitectureRouter
    if name == "get_settings":
        from neural_brain.config import get_settings
        return get_settings
    raise AttributeError(f"module 'runtime.neural_brain' has no attribute {name!r}")
