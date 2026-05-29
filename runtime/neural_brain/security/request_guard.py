"""Zero-Trust Request Guard — FastAPI middleware.

Every request must pass:
  1. Auth check (valid JWT access token or exempted path)
  2. Permission check (role ≥ required for endpoint)
  3. Rate limit check (per-user + per-IP sliding window)
  4. Blacklight input screening (for POST body with 'input' field)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ── Rate limit config ─────────────────────────────────────────────────────────
_RATE_LIMIT_WINDOW_S = 60
_RATE_LIMIT_USER    = int(os.environ.get("RATE_LIMIT_USER",    "120"))   # per user/min
_RATE_LIMIT_IP      = int(os.environ.get("RATE_LIMIT_IP",      "200"))   # per IP/min (external)
_RATE_LIMIT_LOGIN   = int(os.environ.get("RATE_LIMIT_LOGIN",   "10"))    # login attempts/min
_RATE_LIMIT_LOOPBACK = int(os.environ.get("RATE_LIMIT_LOOPBACK", "2000")) # per loopback IP/min

_LOOPBACK_IPS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})

# Paths that don't require authentication
_PUBLIC_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/auto-token",
    "/api/identity/public",
    "/api/health",
    "/api/readiness",
    "/health",
    "/health/detail",
    "/events",
    "/metrics",
    # OIDC discovery is public by spec — clients need it before they have tokens
    "/auth/oidc/providers",
    "/api/auth/oidc/providers",
    # Telemetry and billing summary are read-only, non-sensitive observability
    "/api/telemetry/summary",
    "/api/billing/summary",
})

# NOTE: previous `_PUBLIC_PREFIXES` removed (2026-05-18 security audit CRITICAL).
# Internal Node→Python routes must now present a valid JWT (Node forwards Authorization header).
# This restores both auth + tenant isolation for vault/memory/learning/topics/research endpoints.
_PUBLIC_PREFIXES: tuple[str, ...] = ()

# Paths requiring specific minimum role
_ROLE_REQUIREMENTS: dict[str, str] = {
    "/api/admin": "admin",
    "/api/dev": "dev",
    "/api/neural-brain/forge/approve": "dev",
    "/api/neural-brain/forge/reject": "dev",
    "/api/security": "admin",
}


class SlidingWindowCounter:
    """Thread-safe per-key sliding window rate limiter."""

    def __init__(self, window_s: int, limit: int) -> None:
        self._window = window_s
        self._limit = limit
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Returns True if request is allowed, False if rate-limited."""
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            times = self._buckets[key]
            # Evict old entries
            while times and times[0] < cutoff:
                times.pop(0)
            if len(times) >= self._limit:
                return False
            times.append(now)
            return True

    def get_count(self, key: str) -> int:
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            times = self._buckets[key]
            return sum(1 for t in times if t >= cutoff)


class RequestGuard(BaseHTTPMiddleware):
    """Zero-trust middleware — applied to all routes."""

    def __init__(self, app, *, skip_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self._user_limiter    = SlidingWindowCounter(_RATE_LIMIT_WINDOW_S, _RATE_LIMIT_USER)
        self._ip_limiter      = SlidingWindowCounter(_RATE_LIMIT_WINDOW_S, _RATE_LIMIT_IP)
        self._loopback_limiter = SlidingWindowCounter(_RATE_LIMIT_WINDOW_S, _RATE_LIMIT_LOOPBACK)
        self._login_limiter   = SlidingWindowCounter(_RATE_LIMIT_WINDOW_S, _RATE_LIMIT_LOGIN)
        self._extra_skip = skip_paths or set()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        ip = self._get_ip(request)

        # ── 1. Rate limit (IP-level, always) ─────────────────────────────────
        # Loopback/testclient gets a higher limit so automated tests and internal
        # service calls don't hit the external-facing cap. External IPs use the
        # tighter _RATE_LIMIT_IP budget.
        limiter = self._loopback_limiter if ip in _LOOPBACK_IPS else self._ip_limiter
        if not limiter.check(ip):
            self._emit_rate_limit(ip, "ip", path)
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)

        # ── 2. Extra throttle on login paths ─────────────────────────────────
        if path in ("/api/auth/login", "/api/auth/register"):
            if not self._login_limiter.check(ip):
                self._emit_rate_limit(ip, "login", path)
                return JSONResponse({"detail": "Too many login attempts"}, status_code=429)

        # ── 3. Public paths skip auth ─────────────────────────────────────────
        if path in _PUBLIC_PATHS or path in self._extra_skip:
            return await call_next(request)
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        # ── 4. JWT verification ───────────────────────────────────────────────
        payload = self._verify_token(request)
        if payload is None:
            return JSONResponse({"detail": "Unauthorized — invalid or missing token"}, status_code=401)

        user_id = payload.get("sub", "anonymous")
        role = payload.get("role", "user")
        request.state.user_id = user_id
        request.state.role = role
        request.state.jwt_payload = payload

        # ── 5. Rate limit (per-user) ──────────────────────────────────────────
        if not self._user_limiter.check(user_id):
            self._emit_rate_limit(ip, "user", path, user_id=user_id)
            return JSONResponse({"detail": "User rate limit exceeded"}, status_code=429)

        # ── 6. Role check ─────────────────────────────────────────────────────
        required_role = self._required_role(path)
        if required_role:
            from neural_brain.auth.rbac import require_role, parse_role, Role
            req_role_obj = {"admin": Role.ADMIN, "dev": Role.DEV, "user": Role.USER}.get(required_role, Role.USER)
            if not require_role(role, req_role_obj):
                self._emit_forbidden(user_id, path, role, required_role)
                return JSONResponse({"detail": f"Forbidden — requires role '{required_role}'"}, status_code=403)

        # ── 7. Blacklight input screening (POST with body) ────────────────────
        if request.method == "POST" and self._should_screen(path):
            body_bytes = await request.body()
            if body_bytes:
                try:
                    import json
                    body = json.loads(body_bytes)
                    text = body.get("input") or body.get("message") or ""
                    if text and len(text) > 5:
                        from neural_brain.security.blacklight_engine import get_blacklight
                        from neural_brain.security.system_control import SystemState
                        ctrl_mode = self._get_system_mode()
                        if ctrl_mode == SystemState.LOCKDOWN:
                            return JSONResponse({"detail": "System in lockdown — inputs blocked"}, status_code=503)
                        assessment = get_blacklight().analyze_input(text, user_id=user_id, source="request_guard")
                        if assessment.get("risk_score", 0) >= 85:
                            return JSONResponse({
                                "detail": "Input rejected by security analysis",
                                "threat_level": assessment.get("threat_level"),
                            }, status_code=400)
                except Exception:
                    pass  # non-JSON or other error — pass through

        return await call_next(request)

    @staticmethod
    def _verify_token(request: Request) -> dict | None:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header[7:]
        try:
            from neural_brain.auth.jwt_handler import verify_access_token
            return verify_access_token(token)
        except Exception:
            return None

    @staticmethod
    def _required_role(path: str) -> str | None:
        for prefix, role in _ROLE_REQUIREMENTS.items():
            if path.startswith(prefix):
                return role
        return None

    @staticmethod
    def _should_screen(path: str) -> bool:
        return path in ("/api/neural-brain/think", "/api/chat")

    @staticmethod
    def _get_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "")
        return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "0.0.0.0")

    @staticmethod
    def _get_system_mode():
        try:
            from neural_brain.security.system_control import get_system_control, SystemState
            return get_system_control().get_mode()
        except Exception:
            return None

    @staticmethod
    def _emit_rate_limit(ip: str, kind: str, path: str, user_id: str = "") -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish("security:rate_limited", source="request_guard", payload={
                "ip": ip, "kind": kind, "path": path, "user_id": user_id,
            })
        except Exception:
            pass

    @staticmethod
    def _emit_forbidden(user_id: str, path: str, role: str, required: str) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish("security:access_denied", source="request_guard", payload={
                "user_id": user_id, "path": path, "role": role, "required_role": required,
            })
        except Exception:
            pass
