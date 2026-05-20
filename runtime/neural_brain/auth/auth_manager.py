"""Auth manager — user registry, login, registration, brute-force tracking."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from neural_brain.auth.jwt_handler import create_access_token, create_refresh_token, revoke_all_for_user
from neural_brain.auth.rbac import Role, parse_role
from neural_brain.auth.session_manager import get_session_manager

_SALT_BYTES = 32
_HASH_ITERS = 200_000
_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_S = 900  # 15 min
_PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*[0-9])(?=.*[!@#$%^&*]).{12,}$")


@dataclass
class User:
    user_id: str
    username: str
    email: str
    role: str
    password_hash: str
    salt: str
    created_at: float
    active: bool = True
    blocked: bool = False
    block_reason: str = ""
    last_login: Optional[float] = None
    failed_attempts: int = 0
    locked_until: Optional[float] = None
    meta: dict = field(default_factory=dict)


class AuthManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: dict[str, User] = {}           # user_id → User
        self._by_username: dict[str, str] = {}       # username → user_id
        self._by_email: dict[str, str] = {}          # email → user_id
        self._login_attempts: dict[str, list[float]] = defaultdict(list)  # ip → timestamps
        self._create_admin()

    # ── Bootstrap admin ───────────────────────────────────────────────────────

    def _create_admin(self) -> None:
        username = os.getenv("ADMIN_USERNAME", "admin")
        password = os.getenv("ADMIN_PASSWORD", "")
        email = os.getenv("ADMIN_EMAIL", "admin@nexus.local")
        if not password:
            return  # skip — no admin password set
        try:
            self.register(username=username, password=password, email=email, role="admin")
        except ValueError:
            pass  # already exists

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, *, username: str, password: str, email: str = "", role: str = "user") -> User:
        if not _PASSWORD_PATTERN.match(password):
            raise ValueError(
                "Password must be ≥12 chars with uppercase, digit, and special char (!@#$%^&*)"
            )
        with self._lock:
            if username in self._by_username:
                raise ValueError(f"Username '{username}' already taken")
            if email and email in self._by_email:
                raise ValueError(f"Email already registered")

            salt = os.urandom(_SALT_BYTES).hex()
            pw_hash = self._hash(password, salt)
            user = User(
                user_id=str(uuid.uuid4()),
                username=username,
                email=email,
                role=role,
                password_hash=pw_hash,
                salt=salt,
                created_at=time.time(),
            )
            self._users[user.user_id] = user
            self._by_username[username] = user.user_id
            if email:
                self._by_email[email] = user.user_id

        self._emit("auth:user_registered", {"user_id": user.user_id, "username": username, "role": role})
        return user

    # ── Login ─────────────────────────────────────────────────────────────────

    def login(self, *, username: str, password: str, ip: str = "0.0.0.0",
              device_id: str = "", user_agent: str = "") -> dict:
        self._check_brute_force(ip)

        with self._lock:
            user_id = self._by_username.get(username)
            if user_id is None:
                self._record_failure(ip, username)
                raise ValueError("Invalid credentials")
            user = self._users[user_id]

        if user.blocked:
            self._emit("auth:login_blocked", {"user_id": user.user_id, "ip": ip, "reason": user.block_reason})
            raise PermissionError(f"Account blocked: {user.block_reason}")

        locked_until = user.locked_until
        if locked_until and time.time() < locked_until:
            wait = int(locked_until - time.time())
            raise PermissionError(f"Account locked — try again in {wait}s")

        if not self._verify(password, user.password_hash, user.salt):
            self._record_failure(ip, username)
            with self._lock:
                user.failed_attempts += 1
                if user.failed_attempts >= _MAX_LOGIN_ATTEMPTS:
                    user.locked_until = time.time() + _LOCKOUT_S
                    user.failed_attempts = 0
                    self._emit("auth:account_locked", {
                        "user_id": user.user_id, "username": username, "ip": ip,
                    })
            raise ValueError("Invalid credentials")

        # Success
        with self._lock:
            user.failed_attempts = 0
            user.locked_until = None
            user.last_login = time.time()

        device_id = device_id or str(uuid.uuid4())
        session = get_session_manager().create(
            user_id=user.user_id, role=user.role,
            device_id=device_id, ip=ip, user_agent=user_agent,
        )
        access = create_access_token(user.user_id, user.role, device_id)
        refresh = create_refresh_token(user.user_id, user.role, device_id)

        self._emit("auth:login_success", {"user_id": user.user_id, "ip": ip, "role": user.role})
        return {
            "user_id": user.user_id,
            "username": username,
            "role": user.role,
            "access_token": access,
            "refresh_token": refresh,
            "session_id": session.session_id,
            "device_id": device_id,
        }

    # ── Admin actions ─────────────────────────────────────────────────────────

    def block_user(self, user_id: str, reason: str = "admin_action") -> None:
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                raise ValueError("User not found")
            user.blocked = True
            user.block_reason = reason
        revoke_all_for_user(user_id)
        get_session_manager().revoke_all_for_user(user_id, reason)
        self._emit("auth:user_blocked", {"user_id": user_id, "reason": reason})

    def unblock_user(self, user_id: str) -> None:
        with self._lock:
            user = self._users.get(user_id)
            if user:
                user.blocked = False
                user.block_reason = ""
        self._emit("auth:user_unblocked", {"user_id": user_id})

    def set_role(self, user_id: str, role: str) -> None:
        role_obj = parse_role(role)
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                raise ValueError("User not found")
            old = user.role
            user.role = role_obj.name.lower()
        self._emit("auth:role_changed", {"user_id": user_id, "from": old, "to": role})

    def list_users(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "user_id": u.user_id,
                    "username": u.username,
                    "email": u.email,
                    "role": u.role,
                    "active": u.active,
                    "blocked": u.blocked,
                    "block_reason": u.block_reason,
                    "last_login": u.last_login,
                    "created_at": u.created_at,
                }
                for u in self._users.values()
            ]

    def get_user(self, user_id: str) -> Optional[dict]:
        with self._lock:
            u = self._users.get(user_id)
            return {
                "user_id": u.user_id, "username": u.username,
                "email": u.email, "role": u.role,
                "active": u.active, "blocked": u.blocked,
                "last_login": u.last_login,
            } if u else None

    def force_logout(self, user_id: str) -> int:
        """Admin: revoke all sessions for user."""
        revoke_all_for_user(user_id)
        return get_session_manager().revoke_all_for_user(user_id, "admin_force_logout")

    # ── Brute force ───────────────────────────────────────────────────────────

    def _check_brute_force(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            attempts = self._login_attempts[ip]
            recent = [t for t in attempts if now - t < 300]  # last 5 min
            self._login_attempts[ip] = recent
            if len(recent) >= _MAX_LOGIN_ATTEMPTS:
                self._emit("auth:brute_force_detected", {"ip": ip, "attempts": len(recent)})
                raise PermissionError(f"Too many login attempts from {ip} — wait 5 minutes")

    def _record_failure(self, ip: str, username: str) -> None:
        with self._lock:
            self._login_attempts[ip].append(time.time())
        self._emit("auth:login_failed", {"ip": ip, "username": username})

    # ── Crypto ────────────────────────────────────────────────────────────────

    @staticmethod
    def _hash(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), _HASH_ITERS
        ).hex()

    @staticmethod
    def _verify(password: str, pw_hash: str, salt: str) -> bool:
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), _HASH_ITERS
        ).hex()
        return hmac.compare_digest(candidate, pw_hash)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _emit(self, event_type: str, payload: dict) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish(event_type, source="auth_manager", payload=payload)
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────
_manager: AuthManager | None = None
_lock = threading.Lock()


def get_auth_manager() -> AuthManager:
    global _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                _manager = AuthManager()
    return _manager
