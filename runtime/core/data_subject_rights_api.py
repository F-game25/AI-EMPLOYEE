"""GDPR Data Subject Rights — export, erase, and summarise personal data.

Endpoints
---------
GET  /data/summary  — list every data store and record counts
GET  /data/export   — full JSON export of all personal data for a user
DELETE /data/delete — irreversible erasure of all personal data for a user

Design notes
------------
* All endpoints require authentication (enforced by the caller via
  ``require_auth`` FastAPI dependency).
* Every request is recorded in the AuditEngine with actor = requesting user,
  action = "gdpr_export" / "gdpr_delete" / "gdpr_summary".
* The module is backend-agnostic: it reads files that server.py owns via
  the AI_HOME environment variable, and also queries the AuditEngine and
  memory stores via their singletons.
* Deletion is *best-effort*: if a store does not exist, the error is logged
  but the overall operation still succeeds so that one missing file does not
  block the erasure of all other stores.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("data_subject_rights")

# ── Path helpers ───────────────────────────────────────────────────────────────

def _ai_home() -> Path:
    return Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))


def _state_dir() -> Path:
    return _ai_home() / "state"


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Audit helper ───────────────────────────────────────────────────────────────

def _audit(*, actor: str, action: str, meta: dict[str, Any]) -> None:
    try:
        from core.audit_engine import get_audit_engine
        get_audit_engine().record(
            actor=actor,
            action=action,
            input_data=meta,
            output_data={},
            risk_score=0.7,  # data-subject actions are HIGH risk by default
        )
    except Exception as exc:
        logger.warning("audit record failed: %s", exc)


# ── Per-store helpers ──────────────────────────────────────────────────────────

def _read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    """Return all entries from a JSONL file, silently ignoring parse errors."""
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except OSError:
        pass
    return entries


def _read_json_file(path: Path) -> Any:
    """Return parsed JSON from a file, or None if missing/invalid."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def _delete_file(path: Path, store_name: str, deleted: list[str], errors: list[str]) -> None:
    """Remove a file, recording the outcome."""
    if not path.exists():
        return
    try:
        path.unlink()
        deleted.append(store_name)
    except OSError as exc:
        errors.append(f"{store_name}: {exc}")
        logger.warning("gdpr_delete: could not remove %s — %s", path, exc)


def _query_audit_db(user_id: str) -> list[dict[str, Any]]:
    """Return audit records whose ``actor`` field matches *user_id*."""
    db_path = _state_dir() / "audit_log.db"
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, ts, actor, action, input, output, risk_score, trace_id, meta "
            "FROM audit_log WHERE actor = ? ORDER BY ts DESC LIMIT 1000",
            (user_id,),
        ).fetchall()
        conn.close()
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "actor": r["actor"],
                "action": r["action"],
                "input": json.loads(r["input"] or "{}"),
                "output": json.loads(r["output"] or "{}"),
                "risk_score": r["risk_score"],
                "trace_id": r["trace_id"],
                "meta": json.loads(r["meta"] or "{}"),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("gdpr: audit db query failed: %s", exc)
        return []


def _count_audit_records(user_id: str) -> int:
    db_path = _state_dir() / "audit_log.db"
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE actor = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        return int(count)
    except Exception:
        return 0


def _erase_audit_records(user_id: str) -> int:
    """Delete all audit records owned by *user_id*. Returns the count erased."""
    db_path = _state_dir() / "audit_log.db"
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute("DELETE FROM audit_log WHERE actor = ?", (user_id,))
        count = cur.rowcount
        conn.commit()
        conn.close()
        return count
    except Exception as exc:
        logger.warning("gdpr_delete: could not erase audit records for %s — %s", user_id, exc)
        return 0


def _filter_chatlog_for_user(entries: list[dict[str, Any]], user_id: str) -> list[dict[str, Any]]:
    """Return chatlog entries that belong to the requesting user.

    Heuristic: if the entry contains a ``user_id`` field matching *user_id*,
    include it.  If no ``user_id`` fields exist at all (legacy log), include
    all entries so the operator can review them manually.
    """
    has_user_id = any("user_id" in e for e in entries)
    if not has_user_id:
        return entries  # legacy — return everything
    return [e for e in entries if e.get("user_id") == user_id or e.get("actor") == user_id]


# ── Public API — Summary ───────────────────────────────────────────────────────

def summary(user_id: str) -> dict[str, Any]:
    """Return a catalogue of data stores and their record counts for *user_id*.

    Safe to call; never mutates any data.
    """
    sd = _state_dir()
    chat_all = _read_jsonl_file(sd / "chatlog.jsonl")
    chat_user = _filter_chatlog_for_user(chat_all, user_id)

    memory_data = _read_json_file(sd / "memory.json") or {}
    learning_data = _read_json_file(sd / "learning_engine.json") or {}
    economy_data = _read_json_file(sd / "economy_state.json") or {}
    audit_count = _count_audit_records(user_id)

    vector_store_path = sd / "vector_memory"
    vector_files = (
        len(list(vector_store_path.glob("*.json")))
        if vector_store_path.is_dir()
        else 0
    )

    _audit(
        actor=user_id,
        action="gdpr_summary",
        meta={"user_id": user_id},
    )

    return {
        "user_id": user_id,
        "ts": _ts(),
        "stores": {
            "chatlog": {
                "path": str(sd / "chatlog.jsonl"),
                "records_for_user": len(chat_user),
                "total_records": len(chat_all),
            },
            "memory": {
                "path": str(sd / "memory.json"),
                "exists": (sd / "memory.json").exists(),
            "clients": len(
            memory_data.get("clients")
            if isinstance(memory_data, dict)
            else (memory_data if isinstance(memory_data, list) else [])
        ),
            },
            "audit_log": {
                "path": str(sd / "audit_log.db"),
                "records_for_user": audit_count,
            },
            "learning_engine": {
                "path": str(sd / "learning_engine.json"),
                "exists": (sd / "learning_engine.json").exists(),
            },
            "economy_state": {
                "path": str(sd / "economy_state.json"),
                "exists": (sd / "economy_state.json").exists(),
            },
            "vector_memory": {
                "path": str(vector_store_path),
                "files": vector_files,
            },
        },
        "legal_basis": "GDPR Article 15 — Right of access by the data subject",
    }


# ── Public API — Export ────────────────────────────────────────────────────────

def export(user_id: str) -> dict[str, Any]:
    """Return a full JSON export of all personal data associated with *user_id*.

    This satisfies GDPR Article 20 (Right to data portability).
    """
    sd = _state_dir()

    chat_all = _read_jsonl_file(sd / "chatlog.jsonl")
    chat_user = _filter_chatlog_for_user(chat_all, user_id)

    memory_raw = _read_json_file(sd / "memory.json")
    learning_raw = _read_json_file(sd / "learning_engine.json")
    audit_records = _query_audit_db(user_id)

    _audit(
        actor=user_id,
        action="gdpr_export",
        meta={"user_id": user_id, "records_exported": len(chat_user) + len(audit_records)},
    )

    return {
        "user_id": user_id,
        "exported_at": _ts(),
        "legal_basis": "GDPR Article 20 — Right to data portability",
        "data": {
            "chatlog": chat_user,
            "memory": memory_raw,
            "audit_records": audit_records,
            "learning_engine": learning_raw,
        },
        "note": (
            "This export contains data attributed to the requesting user. "
            "Some stores (e.g. economy_state, vector_memory) are system-level "
            "and are not included in the portable export."
        ),
    }


# ── Public API — Erasure ───────────────────────────────────────────────────────

def erase(user_id: str, *, erase_chatlog: bool = True,
          erase_memory: bool = True, erase_audit: bool = True) -> dict[str, Any]:
    """Erase all personal data associated with *user_id*.

    This satisfies GDPR Article 17 (Right to erasure / "right to be forgotten").

    Parameters
    ----------
    erase_chatlog : bool
        Erase chatlog entries attributed to this user (default True).
    erase_memory : bool
        Erase the full memory.json (default True — contains PII).
    erase_audit : bool
        Erase audit_log.db rows attributed to this user (default True).

    Returns
    -------
    dict with keys: ``deleted``, ``errors``, ``ts``.
    """
    sd = _state_dir()
    deleted: list[str] = []
    errors: list[str] = []

    # ── Chat log — filter and rewrite without user entries ────────────────────
    if erase_chatlog:
        chatlog_path = sd / "chatlog.jsonl"
        if chatlog_path.exists():
            try:
                all_entries = _read_jsonl_file(chatlog_path)
                has_user_id = any("user_id" in e for e in all_entries)
                if has_user_id:
                    # Remove only entries for this user
                    remaining = [
                        e for e in all_entries
                        if e.get("user_id") != user_id and e.get("actor") != user_id
                    ]
                    chatlog_path.write_text(
                        "\n".join(json.dumps(e) for e in remaining) + ("\n" if remaining else ""),
                        encoding="utf-8",
                    )
                    deleted.append(f"chatlog ({len(all_entries) - len(remaining)} entries removed)")
                else:
                    # Legacy log without user tagging — erase entire file
                    chatlog_path.unlink()
                    deleted.append("chatlog (full — no user-level tagging)")
            except OSError as exc:
                errors.append(f"chatlog: {exc}")

    # ── Memory file — full deletion (contains PII) ────────────────────────────
    if erase_memory:
        _delete_file(sd / "memory.json", "memory.json", deleted, errors)

    # ── Audit log — per-user row deletion ─────────────────────────────────────
    if erase_audit:
        erased_count = _erase_audit_records(user_id)
        if erased_count > 0:
            deleted.append(f"audit_log ({erased_count} rows)")

    # ── Learning engine state — full deletion ─────────────────────────────────
    _delete_file(sd / "learning_engine.json", "learning_engine.json", deleted, errors)

    # ── Vector memory — full deletion ─────────────────────────────────────────
    vector_dir = sd / "vector_memory"
    if vector_dir.is_dir():
        import shutil
        try:
            shutil.rmtree(str(vector_dir))
            deleted.append("vector_memory/")
        except OSError as exc:
            errors.append(f"vector_memory: {exc}")

    # ── Record the erasure itself (so it appears in any future audit) ──────────
    _audit(
        actor=user_id,
        action="gdpr_delete",
        meta={
            "user_id": user_id,
            "deleted": deleted,
            "errors": errors,
        },
    )
    logger.info("GDPR erasure complete for user=%s deleted=%s errors=%s", user_id, deleted, errors)

    return {
        "user_id": user_id,
        "ts": _ts(),
        "deleted": deleted,
        "errors": errors,
        "legal_basis": "GDPR Article 17 — Right to erasure",
    }
