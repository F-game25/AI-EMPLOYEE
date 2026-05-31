"""PII redaction for logs — single import point for all log sanitization.

Usage:
    import core.log_sanitizer  # installs global filter at import time

    # FastAPI middleware (add before auth middleware so it runs outermost):
    app.add_middleware(SanitizedLoggingMiddleware)
"""

import logging
import re
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# ---------------------------------------------------------------------------
# 1. Compiled redaction patterns
# ---------------------------------------------------------------------------
# Each entry: (compiled pattern, replacement label)
REDACT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # JWT tokens  — must run before generic Bearer so the full token is caught
    (
        re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        "[REDACTED-JWT]",
    ),
    # Bearer tokens
    (
        re.compile(r"Bearer\s+\S+", re.IGNORECASE),
        "Bearer [REDACTED-TOKEN]",
    ),
    # OpenAI-style API keys
    (
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        "[REDACTED-API-KEY]",
    ),
    # xAI keys
    (
        re.compile(r"xai-[A-Za-z0-9]{20,}"),
        "[REDACTED-API-KEY]",
    ),
    # Google API keys (AIza…)
    (
        re.compile(r"AIza[A-Za-z0-9_-]{35}"),
        "[REDACTED-API-KEY]",
    ),
    # Generic api_key / api-key assignments in JSON / YAML / env
    (
        re.compile(
            r'[Aa][Pp][Ii][-_]?[Kk][Ee][Yy]["\s:=]+[A-Za-z0-9_-]{16,}',
            re.IGNORECASE,
        ),
        "[REDACTED-API-KEY]",
    ),
    # Email addresses (RFC 5322 simplified)
    (
        re.compile(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        ),
        "[REDACTED-EMAIL]",
    ),
    # AWS access key IDs
    (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "[REDACTED-AWS-KEY]",
    ),
    # AWS secret access key assignments
    (
        re.compile(
            r'[Aa][Ww][Ss][-_]?[Ss][Ee][Cc][Rr][Ee][Tt]["\s:=]+\S+',
            re.IGNORECASE,
        ),
        "[REDACTED-AWS-SECRET]",
    ),
    # Passwords in JSON payloads: "password": "..."
    (
        re.compile(r'"password"\s*:\s*"[^"]+"', re.IGNORECASE),
        '"password": "[REDACTED-PASSWORD]"',
    ),
    # Private IPs that appear near auth/token/secret keywords.
    # The lookahead keeps the pattern selective so ordinary internal IPs
    # (e.g. in health-check traces) are NOT stripped.
    (
        re.compile(
            r"(?:(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)"
            r"\.\d{1,3}\.\d{1,3})"
            r"(?=.*?(?:auth|token|secret))",
            re.IGNORECASE | re.DOTALL,
        ),
        "[REDACTED-PRIVATE-IP]",
    ),
]

# ---------------------------------------------------------------------------
# 2. Core sanitize function
# ---------------------------------------------------------------------------

def sanitize(text: str) -> str:
    """Apply all REDACT_PATTERNS to *text* and return the cleaned string."""
    for pattern, replacement in REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# 3. logging.Filter subclass
# ---------------------------------------------------------------------------

class PIIFilter(logging.Filter):
    """Logging filter that redacts PII from every LogRecord before emission."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        # Render the full message first so %-style args are applied, then
        # replace msg with the sanitized string and clear args so the handler
        # does not double-format.
        try:
            original = record.getMessage()
        except Exception:
            original = str(record.msg)

        clean = sanitize(original)
        record.msg = clean
        record.args = ()
        return True


# ---------------------------------------------------------------------------
# 4. Global filter installer
# ---------------------------------------------------------------------------

_FILTER_INSTALLED = False
_PII_FILTER = PIIFilter()

def install_global_filter() -> None:
    """Install PIIFilter on the root logger and key framework loggers.

    Safe to call multiple times — idempotent.
    """
    global _FILTER_INSTALLED
    if _FILTER_INSTALLED:
        return

    for name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        lg = logging.getLogger(name)
        # Avoid adding duplicates if called more than once
        if not any(isinstance(f, PIIFilter) for f in lg.filters):
            lg.addFilter(_PII_FILTER)

    _FILTER_INSTALLED = True


# ---------------------------------------------------------------------------
# 5. Starlette / FastAPI middleware
# ---------------------------------------------------------------------------

class SanitizedLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that:
    - Sanitizes the request path and query string before logging.
    - Never logs the request body.
    - Adds an ``X-Request-ID`` response header for correlation.
    """

    _log = logging.getLogger("sanitized.access")

    def __init__(self, app: ASGIApp, **kwargs) -> None:
        super().__init__(app, **kwargs)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = uuid.uuid4().hex[:12]

        # Sanitize path + query before any logging
        safe_path = sanitize(request.url.path)
        safe_query = sanitize(str(request.url.query)) if request.url.query else ""
        safe_url = f"{safe_path}{'?' + safe_query if safe_query else ''}"

        self._log.debug(
            "req %s %s %s",
            request_id,
            request.method,
            safe_url,
        )

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        self._log.debug(
            "res %s %s %s -> %d",
            request_id,
            request.method,
            safe_url,
            response.status_code,
        )

        return response


# ---------------------------------------------------------------------------
# 6. Auto-install on import
# ---------------------------------------------------------------------------
install_global_filter()
