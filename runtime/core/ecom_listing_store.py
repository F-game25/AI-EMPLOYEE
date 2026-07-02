"""Ecom listing store — SQLite-backed persistence for the e-commerce agent pipeline.

Tables: listings, ecom_email_flows, ecom_ads.
All public functions return dicts and never raise — errors come back as {"ok": False, "error": "..."}.

Status flow for listings: concept → goedgekeurd → gepubliceerd
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_VALID_STATUSES = ("concept", "goedgekeurd", "gepubliceerd")


def _db_path() -> Path:
    from core.state_paths import canonical_state_dir
    return canonical_state_dir() / "ecom.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _init_tables() -> None:
    db = _db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id            TEXT PRIMARY KEY,
                product_naam  TEXT NOT NULL,
                platform      TEXT NOT NULL DEFAULT 'shopify',
                titel         TEXT DEFAULT '',
                beschrijving  TEXT DEFAULT '',
                bullets       TEXT DEFAULT '[]',
                tags          TEXT DEFAULT '[]',
                prijs         REAL DEFAULT 0.0,
                aankoopprijs  REAL DEFAULT 0.0,
                status        TEXT NOT NULL DEFAULT 'concept',
                fotos         TEXT DEFAULT '[]',
                export_tekst  TEXT DEFAULT '',
                aangemaakt_op TEXT NOT NULL,
                bijgewerkt_op TEXT DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_status ON listings (status)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ecom_email_flows (
                id            TEXT PRIMARY KEY,
                listing_id    TEXT NOT NULL,
                type          TEXT NOT NULL,
                onderwerp     TEXT DEFAULT '',
                body          TEXT DEFAULT '',
                status        TEXT DEFAULT 'concept',
                aangemaakt_op TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ecom_ads (
                id            TEXT PRIMARY KEY,
                listing_id    TEXT NOT NULL,
                platform      TEXT NOT NULL DEFAULT 'facebook',
                copy_text     TEXT DEFAULT '',
                status        TEXT DEFAULT 'concept',
                aangemaakt_op TEXT NOT NULL
            )
        """)


_init_tables()


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for field in ("bullets", "tags", "fotos"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                d[field] = []
    return d


# ── Listings ──────────────────────────────────────────────────────────────────

def listing_aanmaken(
    product_naam: str,
    platform: str = "shopify",
    titel: str = "",
    beschrijving: str = "",
    bullets: list | None = None,
    tags: list | None = None,
    prijs: float = 0.0,
    aankoopprijs: float = 0.0,
) -> dict[str, Any]:
    try:
        listing_id = f"lst-{uuid.uuid4().hex[:10]}"
        now = _ts()
        bullets_json = json.dumps(bullets or [], ensure_ascii=False)
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        with _conn() as conn:
            conn.execute(
                "INSERT INTO listings "
                "(id, product_naam, platform, titel, beschrijving, bullets, tags, "
                "prijs, aankoopprijs, status, aangemaakt_op) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'concept', ?)",
                (listing_id, product_naam, platform, titel, beschrijving,
                 bullets_json, tags_json, float(prijs), float(aankoopprijs), now),
            )
        return listing_ophalen(listing_id) or {"ok": False, "error": "Insert failed"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def listing_ophalen(listing_id: str) -> dict[str, Any] | None:
    try:
        with _conn() as conn:
            row = conn.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone()
        return _row_to_dict(row) if row else None
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def listings_ophalen(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    try:
        with _conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM listings WHERE status=? ORDER BY aangemaakt_op DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM listings ORDER BY aangemaakt_op DESC LIMIT ?", (limit,)
                ).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        return []


_EDITABLE_VELDEN = (
    "product_naam", "platform", "titel", "beschrijving",
    "bullets", "tags", "prijs", "aankoopprijs", "fotos", "export_tekst",
)


def listing_bijwerken(listing_id: str, **velden) -> dict[str, Any]:
    try:
        updates = {k: v for k, v in velden.items() if k in _EDITABLE_VELDEN}
        if not updates:
            return {"ok": False, "error": "Geen geldige velden om bij te werken"}
        # Serialize list fields to JSON
        for field in ("bullets", "tags", "fotos"):
            if field in updates and isinstance(updates[field], list):
                updates[field] = json.dumps(updates[field], ensure_ascii=False)
        for field in ("prijs", "aankoopprijs"):
            if field in updates:
                try:
                    updates[field] = float(updates[field])
                except (TypeError, ValueError):
                    del updates[field]
        updates["bijgewerkt_op"] = _ts()
        with _conn() as conn:
            row = conn.execute("SELECT id FROM listings WHERE id=?", (listing_id,)).fetchone()
            if not row:
                return {"ok": False, "error": f"Listing {listing_id} niet gevonden"}
            sets = ", ".join(f"{k}=?" for k in updates)
            conn.execute(
                f"UPDATE listings SET {sets} WHERE id=?",  # nosec B608 — keys whitelisted
                (*updates.values(), listing_id),
            )
        return {"ok": True, "listing": listing_ophalen(listing_id)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def listing_status_bijwerken(listing_id: str, nieuwe_status: str) -> dict[str, Any]:
    try:
        if nieuwe_status not in _VALID_STATUSES:
            return {"ok": False, "error": f"Ongeldige status: {nieuwe_status!r}. Kies uit {_VALID_STATUSES}"}
        with _conn() as conn:
            row = conn.execute("SELECT id FROM listings WHERE id=?", (listing_id,)).fetchone()
            if not row:
                return {"ok": False, "error": f"Listing {listing_id} niet gevonden"}
            conn.execute(
                "UPDATE listings SET status=?, bijgewerkt_op=? WHERE id=?",
                (nieuwe_status, _ts(), listing_id),
            )
        return {"ok": True, "listing": listing_ophalen(listing_id)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def listing_verwijderen(listing_id: str) -> dict[str, Any]:
    try:
        with _conn() as conn:
            row = conn.execute("SELECT id FROM listings WHERE id=?", (listing_id,)).fetchone()
            if not row:
                return {"ok": False, "error": f"Listing {listing_id} niet gevonden"}
            conn.execute("DELETE FROM listings WHERE id=?", (listing_id,))
        return {"ok": True, "deleted": listing_id}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Email flows ───────────────────────────────────────────────────────────────

def email_aanmaken(
    listing_id: str,
    type: str,
    onderwerp: str = "",
    body: str = "",
) -> dict[str, Any]:
    try:
        email_id = f"email-{uuid.uuid4().hex[:10]}"
        now = _ts()
        with _conn() as conn:
            conn.execute(
                "INSERT INTO ecom_email_flows (id, listing_id, type, onderwerp, body, aangemaakt_op) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (email_id, listing_id, type, onderwerp, body, now),
            )
        with _conn() as conn:
            row = conn.execute("SELECT * FROM ecom_email_flows WHERE id=?", (email_id,)).fetchone()
        return dict(row) if row else {"ok": False, "error": "Insert failed"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def emails_ophalen(listing_id: str) -> list[dict[str, Any]]:
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ecom_email_flows WHERE listing_id=? ORDER BY aangemaakt_op DESC",
                (listing_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ── Ads ───────────────────────────────────────────────────────────────────────

def ad_aanmaken(
    listing_id: str,
    platform: str = "facebook",
    copy_text: str = "",
) -> dict[str, Any]:
    try:
        ad_id = f"ad-{uuid.uuid4().hex[:10]}"
        now = _ts()
        with _conn() as conn:
            conn.execute(
                "INSERT INTO ecom_ads (id, listing_id, platform, copy_text, aangemaakt_op) "
                "VALUES (?, ?, ?, ?, ?)",
                (ad_id, listing_id, platform, copy_text, now),
            )
        with _conn() as conn:
            row = conn.execute("SELECT * FROM ecom_ads WHERE id=?", (ad_id,)).fetchone()
        return dict(row) if row else {"ok": False, "error": "Insert failed"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def ads_ophalen(listing_id: str) -> list[dict[str, Any]]:
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ecom_ads WHERE listing_id=? ORDER BY aangemaakt_op DESC",
                (listing_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
