"""Neural Brain graph subsystem (M3)."""
from __future__ import annotations

import threading

__all__ = ["get_brain_graph", "get_native_graph_store"]

_graph_instance = None
_graph_lock = threading.Lock()

_native_store_instance = None
_native_store_lock = threading.Lock()


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


def get_native_graph_store():
    """Return the process-wide NativeGraphStore singleton (SQLite fallback)."""
    global _native_store_instance
    if _native_store_instance is None:
        with _native_store_lock:
            if _native_store_instance is None:
                import os
                from pathlib import Path
                from neural_brain.graph.native_graph_store import NativeGraphStore
                db_path = (
                    Path(os.environ.get("STATE_DIR") or
                         Path(os.environ.get("AI_EMPLOYEE_HOME") or
                              Path.home() / ".ai-employee") / "state")
                    / "native_memory_graph.db"
                )
                _native_store_instance = NativeGraphStore(db_path=db_path)
    return _native_store_instance
