#!/usr/bin/env python3
"""
migrate_json_to_postgres.py

One-shot idempotent migration from JSON state files to PostgreSQL.

Usage:
    DATABASE_URL=postgresql://user:pass@host/db python3 scripts/migrate_json_to_postgres.py

Safe to run multiple times — uses INSERT ... ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure runtime/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "runtime"))

STATE_DIR = Path(__file__).parent.parent / "state"
DEFAULT_TENANT = "default"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(name: str) -> dict:
    path = STATE_DIR / f"{name}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as e:
        print(f"  WARNING: could not read {path}: {e}")
        return {}


def migrate_tasks(conn) -> int:
    data = _load("tasks")
    tasks_raw = data.get("tasks", {})
    # tasks.json stores tasks as a dict keyed by id, or may be empty
    if isinstance(tasks_raw, dict):
        records = list(tasks_raw.values())
    elif isinstance(tasks_raw, list):
        records = tasks_raw
    else:
        return 0

    count = 0
    with conn.cursor() as cur:
        for task in records:
            task_id = str(task.get("id") or uuid.uuid4())
            cur.execute(
                """
                INSERT INTO agent_tasks
                    (id, tenant_id, title, description, status, priority, agent_id, result, meta)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    task_id,
                    task.get("tenant_id", DEFAULT_TENANT),
                    task.get("title"),
                    task.get("description"),
                    task.get("status", "pending"),
                    task.get("priority", "medium"),
                    task.get("agent_id"),
                    json.dumps(task.get("result")) if task.get("result") is not None else None,
                    json.dumps(task.get("meta", task.get("metadata", {}))),
                ),
            )
            count += cur.rowcount
    conn.commit()
    return count


def migrate_knowledge_store(conn) -> int:
    data = _load("knowledge_store")
    entries = data.get("entries", [])
    count = 0
    with conn.cursor() as cur:
        for entry in entries:
            entry_id = str(entry.get("id") or uuid.uuid4())
            meta = {k: v for k, v in entry.items()
                    if k not in ("id", "topic", "content", "source", "confidence", "tags", "embedding_id")}
            cur.execute(
                """
                INSERT INTO knowledge_store
                    (id, tenant_id, topic, content, source, confidence, tags, embedding_id, meta)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    entry_id,
                    DEFAULT_TENANT,
                    entry.get("topic"),
                    entry.get("content", ""),
                    entry.get("source"),
                    float(entry.get("importance", entry.get("confidence", 1.0))),
                    json.dumps(entry.get("tags", [])),
                    entry.get("embedding_id"),
                    json.dumps(meta),
                ),
            )
            count += cur.rowcount
    conn.commit()
    return count


def migrate_agents(conn) -> int:
    data = _load("agents")
    # Support both flat list and _tenant_data structure
    tenant_data = data.get("_tenant_data", {})
    all_agents: list[dict] = []
    if tenant_data:
        for tid, tdata in tenant_data.items():
            for agent in tdata.get("agents", []):
                agent = dict(agent)
                agent["_tenant_id"] = tid
                all_agents.append(agent)
    else:
        for agent in data.get("agents", []):
            all_agents.append(agent)

    count = 0
    with conn.cursor() as cur:
        for agent in all_agents:
            agent_id = str(agent.get("id") or agent.get("agent_id") or uuid.uuid4())
            tenant_id = agent.get("_tenant_id", DEFAULT_TENANT)
            meta = {k: v for k, v in agent.items()
                    if k not in ("id", "agent_id", "status", "last_heartbeat", "_tenant_id")}
            cur.execute(
                """
                INSERT INTO agents_status (agent_id, tenant_id, status, last_heartbeat, meta)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (agent_id, tenant_id) DO NOTHING
                """,
                (
                    agent_id,
                    tenant_id,
                    agent.get("status", "idle"),
                    agent.get("last_heartbeat"),
                    json.dumps(meta),
                ),
            )
            count += cur.rowcount
    conn.commit()
    return count


def migrate_learning_engine(conn) -> int:
    """
    learning_engine.json holds aggregate state (strategy_weights, agent_stats,
    episodic_memory, etc.) rather than a list of discrete sessions.
    We store it as a single synthetic session record so no data is lost.
    """
    data = _load("learning_engine")
    if not data:
        return 0

    session_id = "learning_engine_snapshot"
    count = 0
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO learning_sessions (id, tenant_id, topic, status, sources_consulted, result)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                session_id,
                DEFAULT_TENANT,
                "system_snapshot",
                "completed",
                len(data.get("episodic_memory", [])),
                json.dumps(data),
            ),
        )
        count = cur.rowcount
    conn.commit()
    return count


def migrate_memory_index(conn) -> int:
    data = _load("memory_index")
    memories = data.get("memories", [])
    count = 0
    with conn.cursor() as cur:
        for mem in memories:
            mem_id = str(mem.get("id") or uuid.uuid4())
            meta = {k: v for k, v in mem.items()
                    if k not in ("id", "text", "embedding")}
            cur.execute(
                """
                INSERT INTO memory_index (id, tenant_id, text, embedding, meta)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    mem_id,
                    DEFAULT_TENANT,
                    mem.get("text", ""),
                    json.dumps(mem.get("embedding", [])),
                    json.dumps(meta),
                ),
            )
            count += cur.rowcount
    conn.commit()
    return count


def migrate_research_budget(conn) -> int:
    data = _load("research_budget")
    # Format: {"2026-05-16": 24, "2026-05-17": 6, ...}
    count = 0
    with conn.cursor() as cur:
        for date_str, pages_used in data.items():
            if not isinstance(pages_used, (int, float)):
                continue
            cur.execute(
                """
                INSERT INTO research_budget (tenant_id, date, pages_used, pages_limit)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, date) DO NOTHING
                """,
                (DEFAULT_TENANT, date_str, int(pages_used), 200),
            )
            count += cur.rowcount
    conn.commit()
    return count


def migrate_vector_store(conn) -> int:
    data = _load("vector_store")
    entries = data.get("entries", [])
    count = 0
    with conn.cursor() as cur:
        for entry in entries:
            key = str(entry.get("key") or uuid.uuid4())
            meta = {k: v for k, v in entry.items()
                    if k not in ("key", "text", "embedding")}
            cur.execute(
                """
                INSERT INTO vector_entries (key, tenant_id, text, embedding, meta)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (key, tenant_id) DO NOTHING
                """,
                (
                    key,
                    DEFAULT_TENANT,
                    entry.get("text", ""),
                    json.dumps(entry.get("embedding", [])),
                    json.dumps(meta),
                ),
            )
            count += cur.rowcount
    conn.commit()
    return count


MIGRATIONS = [
    ("tasks.json          -> agent_tasks",       migrate_tasks),
    ("knowledge_store.json -> knowledge_store",  migrate_knowledge_store),
    ("agents.json          -> agents_status",    migrate_agents),
    ("learning_engine.json -> learning_sessions", migrate_learning_engine),
    ("memory_index.json    -> memory_index",     migrate_memory_index),
    ("research_budget.json -> research_budget",  migrate_research_budget),
    ("vector_store.json    -> vector_entries",   migrate_vector_store),
]


def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print(
            "DATABASE_URL is not set.\n"
            "Set it to a PostgreSQL connection string and re-run:\n\n"
            "  DATABASE_URL=postgresql://user:pass@localhost/ai_employee "
            "python3 scripts/migrate_json_to_postgres.py\n"
        )
        sys.exit(0)

    try:
        from core.database import DatabaseClient
    except ImportError as e:
        print(f"ERROR: could not import DatabaseClient: {e}")
        sys.exit(1)

    print(f"Connecting to database...")
    client = DatabaseClient(dsn=db_url, pool_size=2)
    if not client.connect():
        print("ERROR: could not connect to database. Check DATABASE_URL and ensure Postgres is running.")
        sys.exit(1)

    print(f"Connected. Starting migration (tenant_id='{DEFAULT_TENANT}' for all legacy data).\n")

    total = 0
    with client.get_connection() as conn:
        for label, fn in MIGRATIONS:
            try:
                n = fn(conn)
                print(f"  {label}: {n} records migrated")
                total += n
            except Exception as e:
                print(f"  {label}: ERROR — {e}")

    client.disconnect()
    print(f"\nDone. {total} total records migrated.")


if __name__ == "__main__":
    main()
