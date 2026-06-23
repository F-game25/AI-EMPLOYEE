"""Durable local teammate preferences and routines for the companion.

This is intentionally small and local-state only. It records how the companion
should behave as a teammate (for example a morning briefing routine), but it
does not schedule background jobs or touch external channels by itself.
"""
from __future__ import annotations

import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.file_lock import read_json_safe, write_json_safe
from core.state_paths import canonical_state_dir

_STATE_FILE = "teammate_state.json"
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)?\b", re.I)


def teammate_state_path() -> Path:
    return canonical_state_dir() / _STATE_FILE


def default_teammate_state() -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 1,
        "preferences": {
            "briefing_style": "conversational",
            "default_channel": "voice",
        },
        "routines": {
            "morning_brief": {
                "enabled": False,
                "time": "08:00",
                "timezone": time.tzname[0] if time.tzname else "local",
                "channel": "voice",
                "last_delivered_date": None,
                "auto_start": False,
            },
        },
        "created_at": now,
        "updated_at": now,
    }


def load_teammate_state(tenant_id: str = "default") -> dict[str, Any]:
    raw = read_json_safe(teammate_state_path(), default={}, tenant_id=tenant_id)
    state = default_teammate_state()
    if isinstance(raw, dict):
        state = _deep_merge(state, raw)
    return state


def save_teammate_state(state: dict[str, Any], tenant_id: str = "default") -> bool:
    clean = _deep_merge(default_teammate_state(), state if isinstance(state, dict) else {})
    clean["updated_at"] = _now_iso()
    return write_json_safe(teammate_state_path(), clean, tenant_id=tenant_id)


def configure_morning_brief(
    *,
    enabled: bool,
    briefing_time: str | None = None,
    channel: str | None = None,
    tenant_id: str = "default",
) -> dict[str, Any]:
    state = load_teammate_state(tenant_id)
    routine = state.setdefault("routines", {}).setdefault(
        "morning_brief",
        default_teammate_state()["routines"]["morning_brief"],
    )
    routine["enabled"] = bool(enabled)
    if briefing_time:
        routine["time"] = normalize_time(briefing_time) or routine.get("time") or "08:00"
    if channel:
        routine["channel"] = str(channel).strip().lower() or "voice"
    save_teammate_state(state, tenant_id)
    return load_teammate_state(tenant_id)["routines"]["morning_brief"]


def mark_morning_brief_delivered(
    *,
    delivery_date: str,
    summary: str = "",
    tenant_id: str = "default",
) -> dict[str, Any]:
    """Record that today's local morning brief was delivered."""
    state = load_teammate_state(tenant_id)
    routine = state.setdefault("routines", {}).setdefault(
        "morning_brief",
        default_teammate_state()["routines"]["morning_brief"],
    )
    now = _now_iso()
    routine["last_delivered_date"] = str(delivery_date or "")
    routine["last_delivered_at"] = now
    if summary:
        routine["last_delivery_summary"] = str(summary)[:500]
    deliveries = routine.setdefault("deliveries", [])
    if isinstance(deliveries, list):
        deliveries.append({
            "date": routine["last_delivered_date"],
            "delivered_at": now,
            "summary": str(summary or "")[:240],
        })
        routine["deliveries"] = deliveries[-14:]
    save_teammate_state(state, tenant_id)
    return load_teammate_state(tenant_id)["routines"]["morning_brief"]


def normalize_time(text: str) -> str | None:
    """Extract a simple local HH:MM time from user text."""
    m = _TIME_RE.search(str(text or ""))
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    suffix = (m.group(3) or "").lower()
    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")
