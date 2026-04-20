"""ASCEND AI — Memory Router (SQLite-backed)"""

import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_DB_PATH = Path(__file__).parent.parent / "state" / "memory.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def _init_db():
    with _conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                key   TEXT NOT NULL,
                value TEXT NOT NULL,
                tags  TEXT DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        con.commit()


_init_db()


class MemoryCreate(BaseModel):
    key: str
    value: str
    tags: str = ""


class MemoryUpdate(BaseModel):
    key: str | None = None
    value: str | None = None
    tags: str | None = None


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "key": row["key"],
        "value": row["value"],
        "tags": row["tags"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.get("/memory")
def list_memory(search: str = ""):
    with _conn() as con:
        if search:
            rows = con.execute(
                "SELECT * FROM memory WHERE key LIKE ? OR value LIKE ? OR tags LIKE ? ORDER BY updated_at DESC",
                (f"%{search}%", f"%{search}%", f"%{search}%"),
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM memory ORDER BY updated_at DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("/memory", status_code=201)
def create_memory(body: MemoryCreate):
    now = time.time()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO memory (key, value, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (body.key, body.value, body.tags, now, now),
        )
        con.commit()
        row = con.execute("SELECT * FROM memory WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row_to_dict(row)


@router.put("/memory/{memory_id}")
def update_memory(memory_id: int, body: MemoryUpdate):
    with _conn() as con:
        row = con.execute("SELECT * FROM memory WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Memory entry not found")
        key = body.key if body.key is not None else row["key"]
        value = body.value if body.value is not None else row["value"]
        tags = body.tags if body.tags is not None else row["tags"]
        now = time.time()
        con.execute(
            "UPDATE memory SET key=?, value=?, tags=?, updated_at=? WHERE id=?",
            (key, value, tags, now, memory_id),
        )
        con.commit()
        row = con.execute("SELECT * FROM memory WHERE id = ?", (memory_id,)).fetchone()
    return _row_to_dict(row)


@router.delete("/memory/{memory_id}")
def delete_memory(memory_id: int):
    with _conn() as con:
        row = con.execute("SELECT id FROM memory WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Memory entry not found")
        con.execute("DELETE FROM memory WHERE id = ?", (memory_id,))
        con.commit()
    return {"success": True, "deleted_id": memory_id}
