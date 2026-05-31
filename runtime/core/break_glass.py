"""Break-glass emergency access — time-boxed admin access with full audit trail.

Flow: admin requests access → request logged → (manual) approve/deny →
      on approval a 15-min JWT is issued for the target tenant →
      access auto-expires → every step written to the audit chain.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

# ── Paths ─────────────────────────────────────────────────────────────────────

_AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_STORE_FILE = _AI_HOME / "state" / "break_glass.jsonl"

# ── Duration ──────────────────────────────────────────────────────────────────

_ACCESS_MINUTES = 15


# ── Dataclass ────────────────────────────────────────────────────────────────


@dataclass
class BreakGlassRequest:
    request_id: str
    admin_id: str
    target_tenant_id: str
    reason: str
    requested_at: str          # ISO-8601
    expires_at: str            # ISO-8601  (requested_at + 15 min)
    status: Literal["pending", "approved", "denied", "expired"]
    approved_at: Optional[str] = None
    token: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BreakGlassRequest":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})  # type: ignore[attr-defined]


# ── Token helpers (stdlib-only, mirrors the server.py fallback AuthManager) ──


def _bg_create_token(
    admin_id: str,
    target_tenant_id: str,
    request_id: str,
    secret_key: str,
    expire_minutes: int = _ACCESS_MINUTES,
) -> str:
    """Create a signed break-glass JWT-like token (HMAC-SHA256, stdlib only)."""
    exp = int(time.time()) + expire_minutes * 60
    body_data = {
        "sub": admin_id,
        "tenant_id": target_tenant_id,
        "type": "break_glass",
        "request_id": request_id,
        "role": "admin",
        "exp": exp,
        "jti": secrets.token_hex(16),
    }
    body = base64.urlsafe_b64encode(
        json.dumps(body_data, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    sig = hmac.new(secret_key.encode(), body.encode(), "sha256").hexdigest()
    return f"bg1.{body}.{sig}"


def _bg_verify_token(token: str, secret_key: str) -> Optional[dict]:
    """Verify a break-glass token. Returns payload dict or None."""
    try:
        parts = token.split(".", 2)
        if len(parts) != 3 or parts[0] != "bg1":
            return None
        _, body, sig = parts
        expected = hmac.new(secret_key.encode(), body.encode(), "sha256").hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        padding = "=" * (4 - len(body) % 4)
        data = json.loads(base64.urlsafe_b64decode(body + padding))
        if data.get("exp", 0) < int(time.time()):
            return None
        return data
    except Exception:
        return None


def _jwt_secret() -> str:
    """Return the active JWT secret from the environment."""
    return os.environ.get(
        "JWT_SECRET_KEY",
        "CHANGE_THIS_IN_SECURITY_LOCAL_YML_OR_SET_JWT_SECRET_KEY_ENV_VAR",
    )


# ── Store ─────────────────────────────────────────────────────────────────────


class BreakGlassStore:
    """In-memory store backed by an append-only JSONL file."""

    def __init__(self, store_file: Path = _STORE_FILE) -> None:
        self._file = store_file
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._requests: dict[str, BreakGlassRequest] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Replay JSONL into in-memory dict (last write per request_id wins)."""
        if not self._file.exists():
            return
        with self._file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    req = BreakGlassRequest.from_dict(d)
                    self._requests[req.request_id] = req
                except Exception:
                    pass  # corrupt line — skip

    def _append(self, req: BreakGlassRequest) -> None:
        """Append the current state of *req* to the JSONL file."""
        with self._file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(req.to_dict(), separators=(",", ":")) + "\n")

    # ── Public API ────────────────────────────────────────────────────────────

    def create_request(
        self,
        admin_id: str,
        target_tenant_id: str,
        reason: str,
    ) -> BreakGlassRequest:
        """Create a new pending break-glass request."""
        now = datetime.now(timezone.utc)
        req = BreakGlassRequest(
            request_id=secrets.token_hex(16),
            admin_id=admin_id,
            target_tenant_id=target_tenant_id,
            reason=reason,
            requested_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=_ACCESS_MINUTES)).isoformat(),
            status="pending",
        )
        with self._lock:
            self._requests[req.request_id] = req
            self._append(req)
        return req

    def approve(self, request_id: str) -> str:
        """Approve a pending request; return the short-lived break-glass token.

        Raises KeyError if request_id unknown, ValueError if not in pending state.
        """
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                raise KeyError(f"Unknown break-glass request: {request_id}")
            if req.status != "pending":
                raise ValueError(f"Request {request_id} is '{req.status}', not pending")

            token = _bg_create_token(
                admin_id=req.admin_id,
                target_tenant_id=req.target_tenant_id,
                request_id=request_id,
                secret_key=_jwt_secret(),
                expire_minutes=_ACCESS_MINUTES,
            )
            req.status = "approved"
            req.approved_at = datetime.now(timezone.utc).isoformat()
            req.token = token
            self._append(req)
        return token

    def deny(self, request_id: str) -> None:
        """Deny a pending request."""
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                raise KeyError(f"Unknown break-glass request: {request_id}")
            if req.status != "pending":
                raise ValueError(f"Request {request_id} is '{req.status}', not pending")
            req.status = "denied"
            self._append(req)

    def is_valid(self, request_id: str) -> bool:
        """Return True if request is approved and the token has not expired."""
        req = self._requests.get(request_id)
        if req is None or req.status != "approved" or req.token is None:
            return False
        payload = _bg_verify_token(req.token, _jwt_secret())
        return payload is not None

    def expire_old(self) -> int:
        """Mark pending/approved requests past their expires_at as expired.

        Returns the number of requests transitioned to 'expired'.
        """
        now = datetime.now(timezone.utc)
        count = 0
        with self._lock:
            for req in list(self._requests.values()):
                if req.status not in ("pending", "approved"):
                    continue
                try:
                    exp = datetime.fromisoformat(req.expires_at)
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if now >= exp:
                    req.status = "expired"
                    self._append(req)
                    count += 1
        return count

    def get_active(self, admin_id: Optional[str] = None) -> list[BreakGlassRequest]:
        """Return approved (non-expired) requests, optionally filtered by admin."""
        self.expire_old()
        with self._lock:
            reqs = [
                r for r in self._requests.values()
                if r.status == "approved" and self.is_valid(r.request_id)
                and (admin_id is None or r.admin_id == admin_id)
            ]
        return reqs


# ── Singleton ────────────────────────────────────────────────────────────────

_singleton: Optional[BreakGlassStore] = None
_singleton_lock = threading.Lock()


def get_break_glass_store() -> BreakGlassStore:
    """Return the module-level singleton BreakGlassStore, expiring stale records."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = BreakGlassStore()
    _singleton.expire_old()
    return _singleton
