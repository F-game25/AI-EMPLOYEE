from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=True)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _unb64url(data: str) -> bytes:
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _secret() -> str:
    s = os.environ.get("JWT_SECRET", "").strip() or os.environ.get("JWT_SECRET_KEY", "").strip()
    if not s:
        raise RuntimeError("JWT_SECRET is not configured")
    return s


def create_token(sub: str, expires_hours: int = 24) -> tuple[str, datetime]:
    exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": sub, "exp": int(exp.timestamp())}
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    signature = hmac.new(_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    token = f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"
    return token, exp


def decode_token(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    h, p, s = parts
    signing_input = f"{h}.{p}".encode("utf-8")
    expected = hmac.new(_secret().encode("utf-8"), signing_input, hashlib.sha256).digest()
    provided = _unb64url(s)
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")
    payload = json.loads(_unb64url(p).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    return payload


def verify_token(credentials: HTTPAuthorizationCredentials = Security(_bearer)) -> dict[str, Any]:
    token = credentials.credentials
    return decode_token(token)


def verify_login(username: str, password: str) -> bool:
    env_user = os.environ.get("AI_EMPLOYEE_USER", "admin")
    env_pass = os.environ.get("AI_EMPLOYEE_PASS", "admin")
    return username == env_user and password == env_pass
