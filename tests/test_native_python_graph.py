"""Contract test for Python native graph memory fallback."""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path


tmp_root = Path(tempfile.mkdtemp(prefix="aeternus-python-native-graph-"))
state_dir = tmp_root / "state"
state_dir.mkdir(parents=True, exist_ok=True)
os.environ["AI_HOME"] = str(tmp_root)
os.environ["AI_EMPLOYEE_HOME"] = str(tmp_root)
os.environ["STATE_DIR"] = str(state_dir)


class OfflineAdapter:
    def health(self):
        return {"connected": False, "error": "offline-test"}

    def run_write(self, *_args, **_kwargs):
        raise AssertionError("offline adapter should not receive writes")

    def run_read(self, *_args, **_kwargs):
        raise AssertionError("offline adapter should not receive reads")


try:
    from neural_brain.graph.brain_graph import BrainGraph
    from memory.memory_router import MemoryRouter

    graph = BrainGraph(OfflineAdapter())
    concept = graph.upsert_concept("Project Apollo", type="Concept", weight=0.9)
    graph.attach_memory("memory_apollo", [concept])

    stats = graph.stats()
    assert stats["available"] is True
    assert stats["backend"] == "native_sqlite_graph"
    assert stats["neo4j_connected"] is False
    assert stats["concepts"] >= 2

    snapshot = graph.full_snapshot(limit=20)
    assert any(node.get("id") == concept for node in snapshot["nodes"])
    assert any(link.get("source") == "memory_apollo" for link in snapshot["links"])

    router = MemoryRouter()
    result = router.store(
        "semantic_native_write",
        "Native Python memory writes must be visible to the embedded graph.",
        memory_type="semantic",
        source="test",
        importance=0.8,
    )
    assert result["vector_stored"] is True

    db_path = state_dir / "native_memory_graph.db"
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE id = ?",
            ("semantic_native_write",),
        ).fetchone()[0]
        assert count == 1
    finally:
        conn.close()

    print("[✓] python native graph fallback contract tests passed")
finally:
    shutil.rmtree(tmp_root, ignore_errors=True)
