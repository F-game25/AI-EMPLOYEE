"""MuAPI client — the content-creation engine from the vendored Open-Generative-AI
base. Generates images/videos via MuAPI using a submit→poll flow.

Faithful port of vendor/open-generative-ai (src/lib/muapi.js):
  - Auth: ``x-api-key`` header (NOT Bearer).
  - POST /api/v1/<endpoint> → request_id.
  - Poll /api/v1/predictions/<request_id>/result until completed/succeeded/failed.
  - Normalize: url = outputs[0] | url | output.url.

Honest by design: with no ``MUAPI_API_KEY`` it raises a clear error — it never
fabricates a media URL. Real key → real generation.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from content.media_models import endpoint_for

MUAPI_BASE = os.getenv("MUAPI_BASE", "https://api.muapi.ai")
_DONE = {"completed", "succeeded", "success", "complete"}
_FAILED = {"failed", "error", "errored", "cancelled", "canceled"}


class MuapiError(RuntimeError):
    """Raised on missing key, API error, failure, or timeout — never silent."""


def _api_key(explicit: str | None = None) -> str:
    key = explicit or os.getenv("MUAPI_API_KEY") or os.getenv("MUAPI_KEY")
    if not key:
        raise MuapiError(
            "MUAPI_API_KEY not set — cannot generate media. Get a key at "
            "https://muapi.ai/access-keys and set MUAPI_API_KEY in ~/.ai-employee/.env.")
    return key


def _request(url: str, key: str, payload: dict | None, timeout: float) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"x-api-key": key}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200] if hasattr(exc, "read") else ""
        raise MuapiError(f"MuAPI {exc.code} {exc.reason}: {body}") from exc
    except urllib.error.URLError as exc:
        raise MuapiError(f"MuAPI unreachable: {exc.reason}") from exc


def _extract_url(result: dict) -> str | None:
    outputs = result.get("outputs")
    if isinstance(outputs, list) and outputs:
        return outputs[0]
    return result.get("url") or (result.get("output") or {}).get("url")


def generate(model_id: str, prompt: str, *, api_key: str | None = None,
             inputs: dict[str, Any] | None = None, max_attempts: int = 60,
             interval: float = 2.0, timeout: float = 60.0) -> dict[str, Any]:
    """Generate media via MuAPI. Returns ``{url, model, request_id, status, raw}``.

    Raises ``MuapiError`` on missing key, API/HTTP error, generation failure, or
    timeout. ``inputs`` carries model-specific params (aspect_ratio, resolution,
    image_url, seed, ...) per the model's schema in the vendored catalog.
    """
    key = _api_key(api_key)
    payload: dict[str, Any] = {"prompt": prompt, **(inputs or {})}
    submit = _request(f"{MUAPI_BASE}/api/v1/{endpoint_for(model_id)}", key, payload, timeout)

    request_id = submit.get("request_id") or submit.get("id")
    if not request_id:  # some endpoints return the result inline
        return {"url": _extract_url(submit), "model": model_id,
                "request_id": None, "status": "completed", "raw": submit}

    poll_url = f"{MUAPI_BASE}/api/v1/predictions/{request_id}/result"
    for _ in range(max(1, max_attempts)):
        res = _request(poll_url, key, None, timeout)
        status = str(res.get("status", "")).lower()
        if status in _DONE or _extract_url(res):
            return {"url": _extract_url(res), "model": model_id,
                    "request_id": request_id, "status": status or "completed", "raw": res}
        if status in _FAILED:
            raise MuapiError(f"MuAPI generation {status}: {res.get('error') or res}")
        time.sleep(interval)
    raise MuapiError(f"MuAPI generation timed out after {max_attempts} polls "
                     f"(request_id={request_id})")
