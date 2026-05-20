"""JWT handler — short-lived access tokens + long-lived refresh tokens.

Access tokens:  10 min
Refresh tokens: 7 days, stored server-side + rotated on use
"""
from __future__ import annotations

import os
import time
import threading
import uuid
from typing import Any

_JWT_SECRET = os.getenv("JWT_SECRET_KEY", "")
_ACCESS_TTL = int(os.getenv("JWT_ACCESS_TTL_S", "600"))     # 10 min
_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL_S", "604800"))  # 7 days

try:
    import jwt as _pyjwt

    def _encode(payload: dict) -> str:
        return _pyjwt.encode(payload, _JWT_SECRET, algorithm="HS256")

    def _decode(token: str) -> dict:
        return _pyjwt.decode(token, _JWT_SECRET, algorithms=["HS256"])

except ImportError:
    # Fallback: base64 + HMAC (no PyJWT required)
    import base64, hashlib, hmac, json

    def _encode(payload: dict) -> str:
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        sig = hmac.new(_JWT_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def _decode(token: str) -> dict:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError("invalid token")
        body, sig = parts
        expected = hmac.new(_JWT_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=="))
        if payload.get("exp", 0) < time.time():
            raise ValueError("token expired")
        return payload


# ── Token storage (refresh tokens must be server-side) ─────────────────────────
_refresh_store: dict[str, dict] = {}  # jti → {user_id, role, exp, device_id}
_store_lock = threading.Lock()


def create_access_token(user_id: str, role: str, device_id: str = "") -> str:
    now = time.time()
    payload = {
        "sub": user_id,
        "role": role,
        "device": device_id,
        "iat": int(now),
        "exp": int(now + _ACCESS_TTL),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return _encode(payload)


def create_refresh_token(user_id: str, role: str, device_id: str = "") -> str:
    jti = str(uuid.uuid4())
    now = time.time()
    exp = int(now + _REFRESH_TTL)
    payload = {
        "sub": user_id,
        "role": role,
        "device": device_id,
        "iat": int(now),
        "exp": exp,
        "jti": jti,
        "type": "refresh",
    }
    token = _encode(payload)
    with _store_lock:
        _refresh_store[jti] = {"user_id": user_id, "role": role, "exp": exp, "device_id": device_id, "revoked": False}
    return token


def verify_access_token(token: str) -> dict:
    """Returns payload or raises ValueError."""
    payload = _decode(token)
    if payload.get("type") != "access":
        raise ValueError("not an access token")
    return payload


def rotate_refresh_token(token: str) -> tuple[str, str]:
    """Verify + revoke old refresh token; issue new pair. Returns (access, refresh)."""
    payload = _decode(token)
    if payload.get("type") != "refresh":
        raise ValueError("not a refresh token")
    jti = payload["jti"]
    with _store_lock:
        record = _refresh_store.get(jti)
        if record is None or record.get("revoked"):
            raise ValueError("token revoked or unknown")
        record["revoked"] = True  # rotate

    user_id = payload["sub"]
    role = payload["role"]
    device_id = payload.get("device", "")
    access = create_access_token(user_id, role, device_id)
    refresh = create_refresh_token(user_id, role, device_id)
    return access, refresh


def revoke_all_for_user(user_id: str) -> int:
    """Revoke ALL refresh tokens for a user (session kill). Returns count."""
    count = 0
    with _store_lock:
        for rec in _refresh_store.values():
            if rec["user_id"] == user_id and not rec.get("revoked"):
                rec["revoked"] = True
                count += 1
    return count


def revoke_device(user_id: str, device_id: str) -> int:
    count = 0
    with _store_lock:
        for rec in _refresh_store.values():
            if rec["user_id"] == user_id and rec["device_id"] == device_id and not rec.get("revoked"):
                rec["revoked"] = True
                count += 1
    return count


def _purge_expired() -> None:
    now = time.time()
    with _store_lock:
        expired = [k for k, v in _refresh_store.items() if v["exp"] < now]
        for k in expired:
            del _refresh_store[k]
