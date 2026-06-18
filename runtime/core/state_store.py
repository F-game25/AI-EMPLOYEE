"""
state_store.py

Postgres-first, JSON-file fallback state store.

If DATABASE_URL is set and psycopg3 is available, reads/writes go to
Postgres. Otherwise the store transparently falls back to the JSON files
in the state/ directory so development works without a running database.

Usage:
    from core.state_store import get_state_store

    store = get_state_store()
    tasks = store.get_tasks("my-tenant")
    store.upsert_task({"id": "t1", "title": "Do thing", "status": "pending"}, "my-tenant")
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from core.state_paths import canonical_state_dir
from core.file_lock import read_json_safe, write_json_safe


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _state_path(name: str) -> Path:
    # Canonical state dir (honours STATE_DIR / AI_HOME), resolved per-call so an
    # env override set after import is respected. Was repo-local parents[3]/state
    # which split state across two trees — see docs/SYSTEM_COHERENCE_PLAN.md C0.
    return canonical_state_dir() / f"{name}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(name: str) -> dict:
    # Lock-protected read (blocking-with-timeout) — no more raw read races.
    return read_json_safe(_state_path(name), default={})


def _save_json(name: str, data: dict) -> None:
    # Lock-protected write — stops silent last-writer-wins on concurrent agents.
    write_json_safe(_state_path(name), data)


# ─────────────────────────────────────────────────────────────────────────────
# StateStore
# ─────────────────────────────────────────────────────────────────────────────

class StateStore:
    """Postgres-first, JSON-file fallback state store."""

    def __init__(self) -> None:
        self._db = None
        self._use_pg = False
        self._init_backend()

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_backend(self) -> None:
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            logger.info("state_store: DATABASE_URL not set — using JSON fallback")
            return

        try:
            from core.database import DatabaseClient
            client = DatabaseClient(dsn=db_url, pool_size=3)
            if client.connect():
                self._db = client
                self._use_pg = True
                logger.info("state_store: connected to Postgres")
            else:
                logger.warning("state_store: Postgres connect failed — falling back to JSON")
        except Exception as e:
            logger.warning("state_store: could not init Postgres (%s) — using JSON fallback", e)

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def get_tasks(self, tenant_id: str) -> list[dict]:
        if self._use_pg:
            try:
                with self._db.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT * FROM agent_tasks WHERE tenant_id = %s ORDER BY created_at DESC",
                            (tenant_id,),
                        )
                        cols = [d.name for d in cur.description]
                        return [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception as e:
                logger.error("state_store.get_tasks PG error: %s", e)

        # JSON fallback
        data = _load_json("tasks")
        raw = data.get("tasks", {})
        tasks = list(raw.values()) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        return [t for t in tasks if t.get("tenant_id", "default") == tenant_id]

    def upsert_task(self, task: dict, tenant_id: str) -> dict:
        task = {**task, "tenant_id": tenant_id}
        if "id" not in task:
            task["id"] = str(uuid.uuid4())
        task.setdefault("status", "pending")
        task.setdefault("priority", "medium")
        task["updated_at"] = _now_iso()

        if self._use_pg:
            try:
                with self._db.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO agent_tasks
                                (id, tenant_id, title, description, status, priority, agent_id, result, meta, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (id) DO UPDATE SET
                                title        = EXCLUDED.title,
                                description  = EXCLUDED.description,
                                status       = EXCLUDED.status,
                                priority     = EXCLUDED.priority,
                                agent_id     = EXCLUDED.agent_id,
                                result       = EXCLUDED.result,
                                meta         = EXCLUDED.meta,
                                updated_at   = NOW()
                            RETURNING *
                            """,
                            (
                                task["id"], tenant_id,
                                task.get("title"), task.get("description"),
                                task["status"], task["priority"],
                                task.get("agent_id"),
                                json.dumps(task["result"]) if task.get("result") is not None else None,
                                json.dumps(task.get("meta", {})),
                            ),
                        )
                        conn.commit()
                        cols = [d.name for d in cur.description]
                        row = cur.fetchone()
                        return dict(zip(cols, row)) if row else task
            except Exception as e:
                logger.error("state_store.upsert_task PG error: %s", e)

        # JSON fallback
        data = _load_json("tasks")
        tasks = data.setdefault("tasks", {})
        tasks[task["id"]] = task
        _save_json("tasks", data)
        return task

    # ── Knowledge ─────────────────────────────────────────────────────────────

    def get_knowledge(self, tenant_id: str, topic: Optional[str] = None) -> list[dict]:
        if self._use_pg:
            try:
                with self._db.get_connection() as conn:
                    with conn.cursor() as cur:
                        if topic:
                            cur.execute(
                                "SELECT * FROM knowledge_store WHERE tenant_id = %s AND topic = %s ORDER BY created_at DESC",
                                (tenant_id, topic),
                            )
                        else:
                            cur.execute(
                                "SELECT * FROM knowledge_store WHERE tenant_id = %s ORDER BY created_at DESC",
                                (tenant_id,),
                            )
                        cols = [d.name for d in cur.description]
                        return [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception as e:
                logger.error("state_store.get_knowledge PG error: %s", e)

        # JSON fallback
        entries = _load_json("knowledge_store").get("entries", [])
        if topic:
            entries = [e for e in entries if e.get("topic") == topic]
        return entries

    def upsert_knowledge(self, entry: dict, tenant_id: str) -> dict:
        entry = {**entry, "tenant_id": tenant_id}
        if "id" not in entry:
            entry["id"] = str(uuid.uuid4())
        entry["updated_at"] = _now_iso()

        if self._use_pg:
            try:
                with self._db.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO knowledge_store
                                (id, tenant_id, topic, content, source, confidence, tags, embedding_id, meta, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (id) DO UPDATE SET
                                topic        = EXCLUDED.topic,
                                content      = EXCLUDED.content,
                                source       = EXCLUDED.source,
                                confidence   = EXCLUDED.confidence,
                                tags         = EXCLUDED.tags,
                                embedding_id = EXCLUDED.embedding_id,
                                meta         = EXCLUDED.meta,
                                updated_at   = NOW()
                            RETURNING *
                            """,
                            (
                                entry["id"], tenant_id,
                                entry.get("topic"), entry.get("content", ""),
                                entry.get("source"),
                                float(entry.get("confidence", entry.get("importance", 1.0))),
                                json.dumps(entry.get("tags", [])),
                                entry.get("embedding_id"),
                                json.dumps({k: v for k, v in entry.items()
                                            if k not in ("id", "tenant_id", "topic", "content",
                                                         "source", "confidence", "tags",
                                                         "embedding_id", "updated_at")}),
                            ),
                        )
                        conn.commit()
                        cols = [d.name for d in cur.description]
                        row = cur.fetchone()
                        return dict(zip(cols, row)) if row else entry
            except Exception as e:
                logger.error("state_store.upsert_knowledge PG error: %s", e)

        # JSON fallback
        data = _load_json("knowledge_store")
        entries = data.setdefault("entries", [])
        for i, e in enumerate(entries):
            if e.get("id") == entry["id"]:
                entries[i] = entry
                break
        else:
            entries.append(entry)
        _save_json("knowledge_store", data)
        return entry

    # ── Research Budget ───────────────────────────────────────────────────────

    def get_research_budget(self, tenant_id: str, date: str) -> dict:
        """Return budget row for tenant + date. Creates row if missing."""
        if self._use_pg:
            try:
                with self._db.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT * FROM research_budget WHERE tenant_id = %s AND date = %s",
                            (tenant_id, date),
                        )
                        row = cur.fetchone()
                        if row:
                            cols = [d.name for d in cur.description]
                            return dict(zip(cols, row))
                        # Row doesn't exist yet — return default without inserting
                        return {"tenant_id": tenant_id, "date": date, "pages_used": 0, "pages_limit": 200}
            except Exception as e:
                logger.error("state_store.get_research_budget PG error: %s", e)

        # JSON fallback
        data = _load_json("research_budget")
        pages_used = data.get(date, 0)
        return {"tenant_id": tenant_id, "date": date, "pages_used": pages_used, "pages_limit": 200}

    def increment_research_budget(self, tenant_id: str, date: str, pages: int) -> dict:
        """Atomically increment pages_used for tenant + date, respecting pages_limit."""
        if self._use_pg:
            try:
                with self._db.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO research_budget (tenant_id, date, pages_used, pages_limit)
                            VALUES (%s, %s, %s, 200)
                            ON CONFLICT (tenant_id, date) DO UPDATE
                                SET pages_used = research_budget.pages_used + EXCLUDED.pages_used
                            RETURNING *
                            """,
                            (tenant_id, date, pages),
                        )
                        conn.commit()
                        cols = [d.name for d in cur.description]
                        row = cur.fetchone()
                        return dict(zip(cols, row)) if row else {}
            except Exception as e:
                logger.error("state_store.increment_research_budget PG error: %s", e)

        # JSON fallback
        data = _load_json("research_budget")
        data[date] = data.get(date, 0) + pages
        _save_json("research_budget", data)
        return {"tenant_id": tenant_id, "date": date, "pages_used": data[date], "pages_limit": 200}


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_store: Optional[StateStore] = None


def get_state_store() -> StateStore:
    """Return the process-wide StateStore singleton, initializing it on first call."""
    global _store
    if _store is None:
        _store = StateStore()
    return _store
