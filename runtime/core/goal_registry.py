"""GoalRegistry — one canonical goal identity across the goal layers (coherence).

The system has three legitimate goal *layers*, each with its own store + purpose:
  * core.goal_store              — resumable run-goals (execution loop)
  * infra.planning.goal_engine   — strategic OKR objectives (DAG, key results)
  * core.roadmap_engine          — milestone decomposition (goal -> milestones)

They never shared an identity, so a goal created in one was invisible to the
others. This thin registry gives every goal ONE canonical id and cross-links its
representations across layers — without collapsing the specialised stores.

Backed by SQLite in the canonical state dir. Registration is best-effort: a layer
calls ``register_goal()`` after creating its native goal; a failure here never
breaks the layer (the registry is an index, not the source of truth).
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from core.state_paths import canonical_state_dir

# Canonical source labels for the three layers.
SOURCE_RUN_GOAL = "goal_store"
SOURCE_OBJECTIVE = "goal_engine"
SOURCE_ROADMAP = "roadmap_engine"

_lock = threading.Lock()


def _db_path() -> Path:
    # Resolved lazily so STATE_DIR / tenant overrides are honoured at call time.
    return canonical_state_dir() / "goal_registry.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    canonical_id TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT '',
    tenant_id    TEXT NOT NULL DEFAULT 'default',
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goal_links (
    canonical_id TEXT NOT NULL,
    source       TEXT NOT NULL,
    native_id    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (source, native_id)
);
CREATE INDEX IF NOT EXISTS idx_links_canonical ON goal_links(canonical_id);
"""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _conn() -> sqlite3.Connection:
    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p))
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


class GoalRegistry:
    """Cross-layer goal-identity index. Thin: stores ids + links + status only."""

    def register_goal(self, title: str, source: str, native_id: str, *,
                      tenant_id: str = "default", status: str = "active",
                      canonical_id: Optional[str] = None) -> str:
        """Register (or relink) a native goal. If ``(source, native_id)`` is
        already known, returns its existing canonical id (and refreshes status).
        Otherwise creates a canonical goal + link. Returns the canonical id."""
        native_id = str(native_id)
        with _lock, _conn() as c:
            row = c.execute(
                "SELECT canonical_id FROM goal_links WHERE source=? AND native_id=?",
                (source, native_id)).fetchone()
            if row:
                c.execute(
                    "UPDATE goal_links SET status=?, updated_at=? WHERE source=? AND native_id=?",
                    (status, _now(), source, native_id))
                return row["canonical_id"]
            cid = canonical_id or f"goal-{uuid.uuid4().hex[:12]}"
            c.execute(
                "INSERT OR IGNORE INTO goals (canonical_id, title, tenant_id, created_at) VALUES (?,?,?,?)",
                (cid, title or "", tenant_id, _now()))
            c.execute(
                "INSERT INTO goal_links (canonical_id, source, native_id, status, updated_at) VALUES (?,?,?,?,?)",
                (cid, source, native_id, status, _now()))
            return cid

    def link_goal(self, canonical_id: str, source: str, native_id: str, *,
                  status: str = "active") -> None:
        """Attach another layer's representation to an existing canonical goal."""
        with _lock, _conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO goal_links (canonical_id, source, native_id, status, updated_at) VALUES (?,?,?,?,?)",
                (canonical_id, source, str(native_id), status, _now()))

    def update_status(self, source: str, native_id: str, status: str) -> bool:
        with _lock, _conn() as c:
            cur = c.execute(
                "UPDATE goal_links SET status=?, updated_at=? WHERE source=? AND native_id=?",
                (status, _now(), source, str(native_id)))
            return cur.rowcount > 0

    def resolve(self, source: str, native_id: str) -> Optional[str]:
        with _lock, _conn() as c:
            row = c.execute(
                "SELECT canonical_id FROM goal_links WHERE source=? AND native_id=?",
                (source, str(native_id))).fetchone()
            return row["canonical_id"] if row else None

    def get_goal(self, canonical_id: str) -> Optional[dict]:
        with _lock, _conn() as c:
            g = c.execute("SELECT * FROM goals WHERE canonical_id=?", (canonical_id,)).fetchone()
            if not g:
                return None
            links = c.execute(
                "SELECT source, native_id, status, updated_at FROM goal_links WHERE canonical_id=?",
                (canonical_id,)).fetchall()
            return {**dict(g), "links": [dict(row) for row in links]}

    def list_goals(self, *, tenant_id: Optional[str] = None, limit: int = 200) -> list[dict]:
        with _lock, _conn() as c:
            if tenant_id:
                rows = c.execute(
                    "SELECT * FROM goals WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, limit)).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM goals ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            out = []
            for g in rows:
                links = c.execute(
                    "SELECT source, native_id, status FROM goal_links WHERE canonical_id=?",
                    (g["canonical_id"],)).fetchall()
                out.append({**dict(g), "links": [dict(row) for row in links]})
            return out


_singleton: Optional[GoalRegistry] = None
_singleton_lock = threading.Lock()


def get_goal_registry() -> GoalRegistry:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = GoalRegistry()
    return _singleton


def register_goal(title: str, source: str, native_id: str, **kw) -> Optional[str]:
    """Best-effort helper layers call after creating a goal — never raises."""
    try:
        return get_goal_registry().register_goal(title, source, native_id, **kw)
    except Exception:
        return None
