"""HTTP fetch tool — implements the browser_fetch stub.

Risk level 2. GET/POST with configurable headers, 15s timeout,
response body capped at 50 KB.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger("tools.web_fetch")

_MAX_BODY = 50_000


def web_fetch(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: dict | None = None,
    timeout: int = 15,
    **_,
) -> dict:
    """Fetch a URL via HTTP.

    Args:
        url:     Target URL (must be http or https).
        method:  HTTP method (default GET).
        headers: Optional dict of request headers.
        body:    Optional dict to JSON-encode as request body.
        timeout: Seconds (capped at 30).

    Returns:
        {"status_code": int, "body": str, "ok": bool, "url": str}
    """
    if not url.startswith(("http://", "https://")):
        return {"status_code": 0, "body": "", "ok": False, "error": "URL must start with http:// or https://"}

    timeout = min(int(timeout), 30)
    hdrs = {"User-Agent": "AI-Employee/1.0", "Accept": "text/html,application/json"}
    if headers:
        hdrs.update(headers)

    data = None
    if body:
        data = json.dumps(body).encode()
        hdrs["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(_MAX_BODY)
            body_text = raw.decode("utf-8", errors="replace")
            return {"status_code": resp.status, "body": body_text, "ok": resp.status < 400, "url": url}
    except urllib.error.HTTPError as exc:
        body_text = exc.read(_MAX_BODY).decode("utf-8", errors="replace") if exc.fp else ""
        return {"status_code": exc.code, "body": body_text, "ok": False, "url": url, "error": str(exc)}
    except Exception as exc:
        logger.warning("web_fetch error for %s: %s", url, exc)
        return {"status_code": 0, "body": "", "ok": False, "url": url, "error": str(exc)}
