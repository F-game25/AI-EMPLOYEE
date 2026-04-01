"""Conversation Manager — per-call state tracking for the AI call agent.

Maintains an in-memory store of active call sessions indexed by Twilio CallSid.
Each session holds:
  - caller phone number
  - conversation history (role/content pairs)
  - detected user intent
  - goal progress flags (appointment_booked, contact_captured)
  - timestamps

Config env vars:
    CALL_SESSION_TTL_SECONDS  — seconds before idle sessions are expired (default: 3600)
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("call-agent.memory")

SESSION_TTL = int(os.environ.get("CALL_SESSION_TTL_SECONDS", "3600"))

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
LEADS_FILE = AI_HOME / "state" / "call-agent-leads.json"
CALLS_FILE = AI_HOME / "state" / "call-agent-calls.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


class ConversationManager:
    """Thread-safe in-memory conversation state store with optional lead logging."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()

    def get_or_create(self, call_sid: str, caller: str = "") -> dict:
        """Return existing session or create a new one."""
        with self._lock:
            self._maybe_cleanup()
            if call_sid not in self._sessions:
                self._sessions[call_sid] = {
                    "call_sid": call_sid,
                    "caller": caller,
                    "history": [],
                    "intent": "unknown",
                    "appointment_booked": False,
                    "contact_captured": bool(caller),
                    "turn": 0,
                    "created_at": _now_iso(),
                    "last_active": time.monotonic(),
                }
                logger.info("New call session: %s caller=%s", call_sid, caller or "unknown")
            return self._sessions[call_sid]

    def add_message(self, call_sid: str, role: str, content: str) -> None:
        """Append a message to the call history."""
        with self._lock:
            session = self._sessions.get(call_sid)
            if not session:
                return
            session["history"].append({"role": role, "content": content, "ts": _now_iso()})
            session["turn"] += 1
            session["last_active"] = time.monotonic()

    def update(self, call_sid: str, **kwargs) -> None:
        """Update arbitrary session fields."""
        with self._lock:
            session = self._sessions.get(call_sid)
            if not session:
                return
            session.update(kwargs)
            session["last_active"] = time.monotonic()

    def get(self, call_sid: str) -> Optional[dict]:
        with self._lock:
            return self._sessions.get(call_sid)

    def get_history(self, call_sid: str) -> list:
        with self._lock:
            session = self._sessions.get(call_sid)
            return list(session["history"]) if session else []

    def close_call(self, call_sid: str) -> None:
        """Persist lead data and remove session."""
        with self._lock:
            session = self._sessions.pop(call_sid, None)
        if not session:
            return
        self._persist_call(session)
        self._maybe_persist_lead(session)

    def _persist_call(self, session: dict) -> None:
        data = _load_json(CALLS_FILE, {"calls": []})
        record = {
            "call_sid": session["call_sid"],
            "caller": session["caller"],
            "intent": session["intent"],
            "appointment_booked": session["appointment_booked"],
            "contact_captured": session["contact_captured"],
            "turns": session["turn"],
            "created_at": session["created_at"],
            "closed_at": _now_iso(),
            "history": session["history"],
        }
        data["calls"].append(record)
        try:
            _save_json(CALLS_FILE, data)
        except Exception as exc:
            logger.warning("Could not persist call record: %s", exc)

    def _maybe_persist_lead(self, session: dict) -> None:
        caller = session.get("caller", "")
        if not caller:
            return
        data = _load_json(LEADS_FILE, {"leads": []})
        existing = next((l for l in data["leads"] if l.get("phone") == caller), None)
        if existing:
            existing["last_call"] = session["created_at"]
            existing["intent"] = session["intent"]
            if session["appointment_booked"]:
                existing["appointment_booked"] = True
        else:
            data["leads"].append({
                "phone": caller,
                "intent": session["intent"],
                "appointment_booked": session["appointment_booked"],
                "first_call": session["created_at"],
                "last_call": session["created_at"],
            })
        try:
            _save_json(LEADS_FILE, data)
        except Exception as exc:
            logger.warning("Could not persist lead: %s", exc)

    def _maybe_cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s["last_active"] > SESSION_TTL
        ]
        for sid in expired:
            session = self._sessions.pop(sid)
            logger.info("Session expired: %s", sid)
            try:
                self._persist_call(session)
                self._maybe_persist_lead(session)
            except Exception as exc:
                logger.warning("Error persisting expired session %s: %s", sid, exc)


_manager: Optional[ConversationManager] = None


def get_manager() -> ConversationManager:
    global _manager
    if _manager is None:
        _manager = ConversationManager()
    return _manager
