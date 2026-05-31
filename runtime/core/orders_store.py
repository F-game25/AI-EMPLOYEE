"""Orders store — SQLite-backed persistence for the website-sales pipeline.

Uses the same audit.db that AuditEngine already owns.  The `orders` table is
created on first import via `_init_table()`.

Status flow:
  gevonden → demo_klaar → ter_review → goedgekeurd → gepitcht → akkoord → betaald → live
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_VALID_STATUSES = (
    "gevonden",
    "demo_klaar",
    "ter_review",
    "goedgekeurd",
    "gepitcht",
    "akkoord",
    "betaald",
    "live",
)


def _db_path() -> Path:
    ai_home = os.environ.get("AI_HOME")
    base = Path(ai_home) if ai_home else Path.home() / ".ai-employee"
    return base / "state" / "audit.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _init_table() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id           TEXT PRIMARY KEY,
                bedrijfsnaam TEXT NOT NULL,
                plaats       TEXT NOT NULL,
                branche      TEXT NOT NULL,
                contact      TEXT DEFAULT '',
                status       TEXT NOT NULL DEFAULT 'gevonden',
                demo_pad     TEXT DEFAULT '',
                prijs        REAL DEFAULT 0.0,
                aangemaakt_op  TEXT NOT NULL,
                pitch_tekst    TEXT DEFAULT '',
                vervolg_tekst  TEXT DEFAULT '',
                live_url       TEXT DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status)")
        # Idempotent migrations for columns added after initial schema
        for col, definition in (
            ("pitch_tekst",      "TEXT DEFAULT ''"),
            ("vervolg_tekst",    "TEXT DEFAULT ''"),
            ("live_url",         "TEXT DEFAULT ''"),
            ("research_data",    "TEXT DEFAULT ''"),
            ("betaal_referentie","TEXT DEFAULT ''"),
        ):
            try:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {definition}")
            except Exception:
                pass  # column already exists


_init_table()


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def order_aanmaken(
    *,
    bedrijfsnaam: str,
    plaats: str,
    branche: str,
    contact: str = "",
    prijs: float = 0.0,
) -> dict[str, Any]:
    """Create a new order with status=gevonden. Returns the order dict."""
    order_id = f"order-{uuid.uuid4().hex[:10]}"
    now = _ts()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO orders (id, bedrijfsnaam, plaats, branche, contact, status, prijs, aangemaakt_op) "
            "VALUES (?, ?, ?, ?, ?, 'gevonden', ?, ?)",
            (order_id, bedrijfsnaam, plaats, branche, contact, prijs, now),
        )
    return order_ophalen(order_id)


def status_bijwerken(order_id: str, nieuwe_status: str, demo_pad: str = "") -> dict[str, Any]:
    """Update an order's status (and optionally demo_pad). Returns updated order."""
    if nieuwe_status not in _VALID_STATUSES:
        raise ValueError(f"Ongeldige status: {nieuwe_status!r}. Kies uit {_VALID_STATUSES}")
    with _conn() as conn:
        if demo_pad:
            conn.execute(
                "UPDATE orders SET status=?, demo_pad=? WHERE id=?",
                (nieuwe_status, demo_pad, order_id),
            )
        else:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (nieuwe_status, order_id))
    return order_ophalen(order_id)


def order_ophalen(order_id: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    return dict(row) if row else None


def orders_ophalen(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM orders WHERE status=? ORDER BY aangemaakt_op DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY aangemaakt_op DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def order_verwijderen(order_id: str) -> dict[str, Any]:
    """Delete an order by ID. Returns ok/error."""
    with _conn() as conn:
        row = conn.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Order {order_id} niet gevonden"}
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
    return {"ok": True, "deleted": order_id}


def betaalreferentie_opslaan(order_id: str, referentie: str) -> dict[str, Any]:
    """Sla een PayPal-transactiereferentie op en zet status → betaald."""
    with _conn() as conn:
        row = conn.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Order {order_id} niet gevonden"}
        conn.execute(
            "UPDATE orders SET betaal_referentie=?, status='betaald' WHERE id=?",
            (referentie.strip(), order_id),
        )
    return {"ok": True, "order": order_ophalen(order_id)}


def pitch_bijwerken(order_id: str, pitch_tekst: str) -> dict[str, Any]:
    """Update the pitch_tekst of an existing order. Returns updated order."""
    with _conn() as conn:
        row = conn.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Order {order_id} niet gevonden"}
        conn.execute("UPDATE orders SET pitch_tekst=? WHERE id=?", (pitch_tekst, order_id))
    return {"ok": True, "order": order_ophalen(order_id)}
