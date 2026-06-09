"""http_request — atomic tool for outbound HTTP GET/POST requests.

External network calls are consequential actions (risk level 3).
Every call goes through the HITL gate before the request is made.
The gate is non-blocking by default: it queues the approval request and
returns immediately with status="pending". The caller must poll or wait.

Input::

    {"url": "https://...", "method": "GET", "headers": {}, "body": {}}

Output (HITL pending)::

    {"status": "pending", "hitl_request_id": "hitl-xxxx", "message": "..."}

Output (after approval or if blocking=True and approved)::

    {"status": "ok", "http_status": 200, "body": "...", "url": "..."}

Output (rejected / blocked)::

    {"status": "blocked", "reason": "...", "hitl_request_id": "..."}
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from .registry import register_tool

logger = logging.getLogger(__name__)

_MAX_RESPONSE_BYTES = 50_000  # 50 KB cap to keep memory bounded


def _do_request(url: str, method: str, headers: dict, body: dict | None) -> dict[str, Any]:
    method = method.upper()
    req = urllib.request.Request(url, method=method, headers=headers)
    if body:
        req.data = json.dumps(body).encode("utf-8")
        if "Content-Type" not in headers:
            req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read(_MAX_RESPONSE_BYTES)
            return {
                "status": "ok",
                "http_status": resp.status,
                "url": url,
                "body": raw.decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        return {"status": "error", "http_status": exc.code, "url": url, "error": str(exc)}
    except urllib.error.URLError as exc:
        return {"status": "error", "url": url, "error": str(exc)}


def _call(input_data: dict[str, Any]) -> dict[str, Any]:
    url     = str(input_data.get("url") or "").strip()
    method  = str(input_data.get("method") or "GET").strip()
    headers = dict(input_data.get("headers") or {})
    body    = input_data.get("body")  # dict or None
    blocking = bool(input_data.get("blocking", False))

    if not url:
        return {"status": "error", "error": "url is required"}
    if not url.startswith(("http://", "https://")):
        return {"status": "error", "error": "url must start with http:// or https://"}

    try:
        from core.hitl_gate import get_hitl_gate
        gate = get_hitl_gate()
    except Exception as exc:
        logger.warning("http_request: HITL gate unavailable — blocking request. %s", exc)
        return {"status": "blocked", "reason": "HITL gate unavailable; external request denied"}

    hitl_payload = {"url": url, "method": method, "headers": headers}
    if body:
        hitl_payload["body_preview"] = str(body)[:200]

    result = gate.require_approval(
        agent="http_request_tool",
        action=f"HTTP {method} → {url}",
        payload=hitl_payload,
        submitted_by="http_request_tool",
        blocking=blocking,
    )

    if result["status"] == "pending":
        return {
            "status": "pending",
            "hitl_request_id": result["request_id"],
            "message": result.get("message", "Awaiting human approval before sending HTTP request."),
        }

    if result.get("status") == "approved":
        logger.info("http_request: HITL approved %s %s", method, url)
        return _do_request(url, method, headers, body)

    # rejected or timeout
    return {
        "status": "blocked",
        "reason": f"HITL decision: {result.get('status', 'rejected')}",
        "hitl_request_id": result.get("request_id", ""),
    }


register_tool(
    name="http_request",
    description=(
        "Make an outbound HTTP GET or POST request to any URL. "
        "REQUIRES human approval via HITL gate before the request is sent. "
        "Returns status=pending with a hitl_request_id until approved. "
        "Input: url (required), method ('GET'/'POST'), headers (dict), body (dict), blocking (bool)."
    ),
    call=_call,
    input_schema={
        "type": "object",
        "required": ["url"],
        "properties": {
            "url":      {"type": "string", "description": "Full URL including scheme"},
            "method":   {"type": "string", "description": "HTTP method: GET or POST", "default": "GET"},
            "headers":  {"type": "object", "description": "Optional request headers"},
            "body":     {"type": "object", "description": "Optional JSON body (POST)"},
            "blocking": {"type": "boolean", "description": "If true, wait for HITL decision (max 1h)", "default": False},
        },
    },
    output_schema={
        "type": "object",
        "properties": {
            "status":          {"type": "string", "description": "ok | pending | blocked | error"},
            "http_status":     {"type": "integer"},
            "body":            {"type": "string"},
            "url":             {"type": "string"},
            "hitl_request_id": {"type": "string"},
            "message":         {"type": "string"},
            "reason":          {"type": "string"},
            "error":           {"type": "string"},
        },
    },
    tags=["http", "network", "external", "hitl-required"],
)
