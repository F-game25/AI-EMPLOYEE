"""Session manager — per-device session tracking with concurrent session limits."""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


MAX_SESSIONS_PER_USER = 5
SESSION_IDLE_TTL_S = 3600  # 1 hour idle → expire


@dataclass
class Session:
    session_id: str
    user_id: str
    role: str
    device_id: str
    device_fingerprint: str
    created_at: float
    last_active: float
    ip: str
    revoked: bool = False
    suspicious: bool = False
    meta: dict = field(default_factory=dict)


class SessionManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}           # session_id → Session
        self._user_sessions: dict[str, list[str]] = defaultdict(list)  # user_id → [session_ids]
        self._purge_thread = threading.Thread(target=self._purge_loop, daemon=True, name="session_purge")
        self._purge_thread.start()

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, *, user_id: str, role: str, device_id: str, ip: str, user_agent: str = "") -> Session:
        fingerprint = self._fingerprint(ip, user_agent)
        with self._lock:
            existing = self._user_sessions[user_id]
            # Enforce concurrent session limit
            if len(existing) >= MAX_SESSIONS_PER_USER:
                oldest_id = existing[0]
                self._revoke_locked(oldest_id, "max_sessions_exceeded")
                existing.pop(0)

            session_id = str(uuid.uuid4())
            now = time.time()
            s = Session(
                session_id=session_id,
                user_id=user_id,
                role=role,
                device_id=device_id,
                device_fingerprint=fingerprint,
                created_at=now,
                last_active=now,
                ip=ip,
            )
            self._sessions[session_id] = s
            self._user_sessions[user_id].append(session_id)
        return s

    # ── Validate / touch ─────────────────────────────────────────────────────

    def touch(self, session_id: str, ip: str = "", user_agent: str = "") -> Optional[Session]:
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None or s.revoked:
                return None
            if time.time() - s.last_active > SESSION_IDLE_TTL_S:
                s.revoked = True
                return None

            # Detect suspicious IP change (flag, don't block immediately)
            if ip and ip != s.ip:
                s.suspicious = True
                self._emit_suspicious(s, f"ip_change:{s.ip}->{ip}")

            s.last_active = time.time()
            return s

    # ── Revoke ────────────────────────────────────────────────────────────────

    def revoke(self, session_id: str, reason: str = "manual") -> bool:
        with self._lock:
            return self._revoke_locked(session_id, reason)

    def _revoke_locked(self, session_id: str, reason: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None:
            return False
        s.revoked = True
        return True

    def revoke_all_for_user(self, user_id: str, reason: str = "admin_action") -> int:
        with self._lock:
            ids = list(self._user_sessions.get(user_id, []))
            for sid in ids:
                self._revoke_locked(sid, reason)
            return len(ids)

    def revoke_device(self, user_id: str, device_id: str) -> int:
        with self._lock:
            count = 0
            for sid in list(self._user_sessions.get(user_id, [])):
                s = self._sessions.get(sid)
                if s and s.device_id == device_id:
                    self._revoke_locked(sid, "device_revoked")
                    count += 1
            return count

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_active_sessions(self, user_id: str) -> list[dict]:
        now = time.time()
        with self._lock:
            result = []
            for sid in self._user_sessions.get(user_id, []):
                s = self._sessions.get(sid)
                if s and not s.revoked:
                    result.append({
                        "session_id": sid,
                        "device_id": s.device_id,
                        "ip": s.ip,
                        "created_at": s.created_at,
                        "last_active": s.last_active,
                        "idle_s": int(now - s.last_active),
                        "suspicious": s.suspicious,
                    })
            return result

    def get_all_active(self) -> list[dict]:
        """Admin view — all active sessions."""
        now = time.time()
        with self._lock:
            return [
                {
                    "session_id": s.session_id,
                    "user_id": s.user_id,
                    "role": s.role,
                    "device_id": s.device_id,
                    "ip": s.ip,
                    "idle_s": int(now - s.last_active),
                    "suspicious": s.suspicious,
                }
                for s in self._sessions.values()
                if not s.revoked and now - s.last_active < SESSION_IDLE_TTL_S
            ]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _fingerprint(ip: str, user_agent: str) -> str:
        raw = f"{ip}|{user_agent}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _emit_suspicious(self, s: Session, reason: str) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish("security:suspicious_session", source="session_manager", payload={
                "user_id": s.user_id, "session_id": s.session_id,
                "device_id": s.device_id, "reason": reason,
            })
        except Exception:
            pass

    def _purge_loop(self) -> None:
        while True:
            time.sleep(300)
            now = time.time()
            with self._lock:
                expired = [sid for sid, s in self._sessions.items()
                           if s.revoked or now - s.last_active > SESSION_IDLE_TTL_S]
                for sid in expired:
                    s = self._sessions.pop(sid, None)
                    if s:
                        user_sessions = self._user_sessions.get(s.user_id, [])
                        if sid in user_sessions:
                            user_sessions.remove(sid)


# ── Singleton ─────────────────────────────────────────────────────────────────
_manager: SessionManager | None = None
_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                _manager = SessionManager()
    return _manager
