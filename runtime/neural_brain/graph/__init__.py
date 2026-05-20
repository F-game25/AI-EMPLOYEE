"""Neural Brain graph subsystem (M3)."""
from __future__ import annotations

import threading

__all__ = ["get_brain_graph"]

_graph_instance = None
_graph_lock = threading.Lock()


def get_brain_graph():
    """Return the process-wide BrainGraph singleton (None if Neo4j unavailable)."""
    global _graph_instance
    if _graph_instance is None:
        with _graph_lock:
            if _graph_instance is None:
                try:
                    from neural_brain.config import get_settings
                    from neural_brain.graph.neo4j_adapter import Neo4jAdapter
                    from neural_brain.graph.brain_graph import BrainGraph
                    settings = get_settings()
                    adapter = Neo4jAdapter(
                        uri=settings.neo4j_uri,
                        user=settings.neo4j_user,
                        password=settings.neo4j_password,
                    )
                    _graph_instance = BrainGraph(adapter)
                except Exception:
                    _graph_instance = None  # type: ignore[assignment]
    return _graph_instance
