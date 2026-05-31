"""Embedded native graph store for the Neural Brain runtime.

This is the Python-side writer for the same offline SQLite graph database used
by the Node hybrid memory router. Neo4j-compatible graph capability is a core
runtime feature; an external Neo4j server may be used later, but memory graph
writes must still work offline by default.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

CURRENT_SCHEMA_VERSION = 1


def _state_dir() -> Path:
    home = Path(os.environ.get("AI_EMPLOYEE_HOME") or os.environ.get("AI_HOME") or Path.home() / ".ai-employee")
    return Path(os.environ.get("STATE_DIR") or home / "state").resolve()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _hash16(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value if isinstance(value, dict) else {"value": value}, ensure_ascii=True)
    except Exception:
        return "{}"


class NativeGraphStore:
    """Small embedded property graph on SQLite.

    The table names and columns intentionally match ``backend/core/native-memory-graph.js``.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or _state_dir() / "native_memory_graph.db").resolve()
        self._lock = threading.RLock()
        self._init_error: str | None = None
        self._ensure_schema()

    @property
    def available(self) -> bool:
        return self._init_error is None

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=2.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS graph_meta (
                      key TEXT PRIMARY KEY,
                      value TEXT NOT NULL,
                      updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS graph_nodes (
                      id TEXT PRIMARY KEY,
                      label TEXT NOT NULL,
                      type TEXT NOT NULL DEFAULT 'memory',
                      "group" TEXT NOT NULL DEFAULT 'memory',
                      source TEXT NOT NULL DEFAULT 'native_memory_graph',
                      confidence REAL NOT NULL DEFAULT 0.7,
                      metadata TEXT NOT NULL DEFAULT '{}',
                      created_at TEXT NOT NULL,
                      updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS graph_edges (
                      id TEXT PRIMARY KEY,
                      source TEXT NOT NULL,
                      target TEXT NOT NULL,
                      type TEXT NOT NULL DEFAULT 'RELATED_TO',
                      weight REAL NOT NULL DEFAULT 0.5,
                      source_system TEXT NOT NULL DEFAULT 'native_memory_graph',
                      metadata TEXT NOT NULL DEFAULT '{}',
                      created_at TEXT NOT NULL,
                      updated_at TEXT NOT NULL,
                      FOREIGN KEY(source) REFERENCES graph_nodes(id) ON DELETE CASCADE,
                      FOREIGN KEY(target) REFERENCES graph_nodes(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_graph_nodes_label ON graph_nodes(label);
                    CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(type);
                    CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source);
                    CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target);
                    CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges(type);
                    """
                )
                conn.execute(
                    """
                    INSERT INTO graph_meta (key, value, updated_at)
                    VALUES ('schema_version', ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                    """,
                    (json.dumps(CURRENT_SCHEMA_VERSION), _now()),
                )
                conn.execute(f"PRAGMA user_version={CURRENT_SCHEMA_VERSION}")
                conn.commit()
            self._init_error = None
        except Exception as exc:
            self._init_error = str(exc)

    def upsert_node(
        self,
        node_id: str,
        label: str,
        *,
        type: str = "Concept",
        group: str | None = None,
        source: str = "python_neural_brain",
        confidence: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not node_id:
            node_id = _hash16(f"{type}:{label.lower()}")
        ts = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO graph_nodes (id, label, type, "group", source, confidence, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  label=excluded.label,
                  type=excluded.type,
                  "group"=excluded."group",
                  source=excluded.source,
                  confidence=excluded.confidence,
                  metadata=excluded.metadata,
                  updated_at=excluded.updated_at
                """,
                (
                    node_id,
                    label or node_id,
                    type or "Concept",
                    group or type or "memory",
                    source,
                    float(confidence),
                    _safe_json(metadata or {}),
                    ts,
                    ts,
                ),
            )
            conn.commit()
        return node_id

    def upsert_edge(
        self,
        source: str,
        target: str,
        *,
        rel: str = "RELATES_TO",
        strength: float = 0.5,
        source_system: str = "python_neural_brain",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not source or not target:
            return ""
        self.upsert_node(source, source, type="Entity", source=source_system)
        self.upsert_node(target, target, type="Entity", source=source_system)
        edge_id = f"{source}:{rel}:{target}"
        ts = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO graph_edges (id, source, target, type, weight, source_system, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  source=excluded.source,
                  target=excluded.target,
                  type=excluded.type,
                  weight=excluded.weight,
                  source_system=excluded.source_system,
                  metadata=excluded.metadata,
                  updated_at=excluded.updated_at
                """,
                (edge_id, source, target, rel, float(strength), source_system, _safe_json(metadata or {}), ts, ts),
            )
            conn.commit()
        return edge_id

    def attach_memory(self, memory_id: str, concept_ids: list[str], *, label: str = "MENTIONS") -> None:
        if not memory_id:
            return
        self.upsert_node(memory_id, memory_id, type="Memory", group="memory", source="python_neural_brain")
        for concept_id in concept_ids:
            if concept_id:
                self.upsert_edge(memory_id, concept_id, rel=label, strength=1.0, source_system="python_neural_brain")

    def neighborhood(self, seed_ids: list[str] | None = None, *, limit: int = 50) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or 50), 500))
        with self._lock, self._connect() as conn:
            if seed_ids:
                seeds = [str(seed) for seed in seed_ids if seed]
                placeholders = ",".join("?" for _ in seeds)
                if not placeholders:
                    return {"nodes": [], "links": []}
                edge_rows = conn.execute(
                    f"""
                    SELECT * FROM graph_edges
                    WHERE source IN ({placeholders}) OR target IN ({placeholders})
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    [*seeds, *seeds, safe_limit * 2],
                ).fetchall()
                node_ids = set(seeds)
                for row in edge_rows:
                    node_ids.add(row["source"])
                    node_ids.add(row["target"])
                node_placeholders = ",".join("?" for _ in node_ids)
                node_rows = conn.execute(
                    f"SELECT * FROM graph_nodes WHERE id IN ({node_placeholders}) LIMIT ?",
                    [*node_ids, safe_limit],
                ).fetchall()
            else:
                node_rows = conn.execute(
                    "SELECT * FROM graph_nodes ORDER BY updated_at DESC LIMIT ?",
                    (safe_limit,),
                ).fetchall()
                node_ids = {row["id"] for row in node_rows}
                edge_rows = conn.execute(
                    "SELECT * FROM graph_edges ORDER BY updated_at DESC LIMIT ?",
                    (safe_limit * 2,),
                ).fetchall()

        nodes = [self._node_row(row) for row in node_rows]
        visible = {node["id"] for node in nodes}
        links = [self._edge_row(row) for row in edge_rows if row["source"] in visible and row["target"] in visible]
        return {"nodes": nodes, "links": links}

    def full_snapshot(self, *, limit: int = 200) -> dict[str, Any]:
        return self.neighborhood(None, limit=limit)

    def stats(self) -> dict[str, Any]:
        if self._init_error:
            return {"available": False, "backend": "native_sqlite_graph", "error": self._init_error}
        with self._lock, self._connect() as conn:
            nodes = conn.execute("SELECT COUNT(*) AS n FROM graph_nodes").fetchone()["n"]
            edges = conn.execute("SELECT COUNT(*) AS n FROM graph_edges").fetchone()["n"]
        return {
            "available": True,
            "backend": "native_sqlite_graph",
            "db_path": str(self.db_path),
            "schema_version": CURRENT_SCHEMA_VERSION,
            "concepts": nodes,
            "relationships": edges,
            "memories": 0,
            "skills": 0,
        }

    @staticmethod
    def _node_row(row: sqlite3.Row) -> dict[str, Any]:
        props = {
            "id": row["id"],
            "label": row["label"],
            "type": row["type"],
            "group": row["group"],
            "source": row["source"],
            "confidence": row["confidence"],
        }
        return {
            "id": row["id"],
            "label": row["label"],
            "labels": [row["type"]],
            "props": props,
            "text": row["label"],
            "score": row["confidence"],
            "type": row["type"],
        }

    @staticmethod
    def _edge_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "source": row["source"],
            "target": row["target"],
            "rel": row["type"],
            "type": row["type"],
            "strength": row["weight"],
            "props": {"source_system": row["source_system"]},
        }
