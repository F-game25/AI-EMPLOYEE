from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from typing import Optional

_METRICS_LOCK = threading.Lock()
_METRICS = {
    "route_selected": 0,
    "route_selected_wavefield": 0,
    "shadow_requests": 0,
    "healthcheck_failures": 0,
    "fallbacks": 0,
    "wavefield_calls": 0,
    "wavefield_errors": 0,
}


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def wavefield_healthcheck(*, ollama_host: Optional[str] = None, model: Optional[str] = None) -> tuple[bool, str]:
    host = (ollama_host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
    model_name = model or os.environ.get("WAVEFIELD_MODEL", "").strip()
    if not model_name:
        return False, "WAVEFIELD_MODEL is not configured"
    req = urllib.request.Request(f"{host}/api/tags", headers={"User-Agent": "AI-Employee/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status != 200:
                return False, f"ollama status {resp.status}"
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return False, f"ollama unavailable: {exc}"
    names = {
        str(m.get("name", "")).split(":")[0]
        for m in (body.get("models") or [])
        if isinstance(m, dict)
    }
    if model_name.split(":")[0] not in names:
        return False, f"model '{model_name}' is not pulled in Ollama"
    return True, "ok"


def wavefield_call(
    *,
    prompt: str,
    system_prompt: str,
    history: Optional[list] = None,
    model: Optional[str] = None,
    timeout_s: int = 120,
) -> str:
    record_wavefield_event("wavefield_calls")
    model_name = (model or os.environ.get("WAVEFIELD_MODEL", "")).strip()
    if not model_name:
        raise RuntimeError("WAVEFIELD_MODEL is not configured")
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    messages: list = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model_name, "stream": False, "messages": messages}
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        record_wavefield_event("wavefield_errors")
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"wavefield HTTP {exc.code}: {details}") from exc
    return ((body.get("message") or {}).get("content") or "").strip()


def wavefield_allow_fallback() -> bool:
    return _bool_env("WAVEFIELD_ALLOW_FALLBACK", True)


def record_wavefield_event(event: str) -> None:
    with _METRICS_LOCK:
        if event in _METRICS:
            _METRICS[event] += 1


def get_wavefield_metrics() -> dict[str, int]:
    with _METRICS_LOCK:
        return dict(_METRICS)
