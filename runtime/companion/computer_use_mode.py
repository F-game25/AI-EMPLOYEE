"""Computer-Use mode — master switch for the teammate driving a computer.

When OFF (the default), the execution broker refuses every ``browser.*`` (and
future ``desktop.*``) capability, so the companion cannot drive a browser/desktop.
When ON, those capabilities run under the existing M1 risk model: read-only
actions (open/snapshot/extract/capture) are free, side-effecting ones
(``browser.act``) are approval-gated. The toggle is the master switch; per-action
safety is unchanged.

State is a single JSON file under the canonical state dir so the choice survives
restarts. Thread-safe; never raises to callers (fails safe → OFF).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from core.file_lock import FileLock

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_FILENAME = "computer_use_mode.json"
_DEFAULT_MODE = {"enabled": False, "desktop": False, "desktop_available": False, "updated_at": None}


def _state_dir() -> Path:
    """Return the canonical state directory, falling back to repo-local state."""
    try:
        from core.state_paths import canonical_state_dir
        return canonical_state_dir()
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parents[2] / "state"


def _path() -> Path:
    """Return the persisted computer-use mode file path."""
    return _state_dir() / _FILENAME


def _normalize(data: dict | None) -> dict:
    """Normalize a possibly partial state payload to the public mode contract."""
    data = data or {}
    return {
        "enabled": bool(data.get("enabled", False)),
        "desktop": bool(data.get("desktop", False)),
        "desktop_available": False,
        "updated_at": data.get("updated_at"),
    }


def _read_unlocked(path: Path) -> dict:
    """Read mode state while the caller already owns the thread and file locks."""
    if not path.exists():
        return dict(_DEFAULT_MODE)
    return _normalize(json.loads(path.read_text(encoding="utf-8")))


def get_mode() -> dict:
    """Return ``{enabled, desktop, desktop_available, updated_at}``. Fails safe to OFF.

    ``enabled``  — master Computer-Use switch.
    ``desktop``  — desktop (screen/system) sub-switch; control needs BOTH on.
    """
    with _LOCK:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(p):
                return _read_unlocked(p)
        except FileNotFoundError:
            return dict(_DEFAULT_MODE)
        except Exception as exc:  # noqa: BLE001
            logger.warning("computer_use_mode read failed (defaulting OFF): %s", exc)
            return dict(_DEFAULT_MODE)


def _update(*, enabled: bool | None = None, desktop: bool | None = None) -> dict:
    """Atomically update one or both switches while preserving omitted values."""
    with _LOCK:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(p):
                current = _read_unlocked(p)
                payload = {
                    "enabled": bool(current["enabled"] if enabled is None else enabled),
                    "desktop": bool(current["desktop"] if desktop is None else desktop),
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                p.write_text(json.dumps(payload), encoding="utf-8")
                return {**payload, "desktop_available": False}
        except Exception as exc:  # noqa: BLE001
            logger.warning("computer_use_mode write failed: %s", exc)
    return get_mode()


def _write(enabled: bool, desktop: bool) -> dict:
    """Persist both switches after computing their values under one lock."""
    with _LOCK:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(p):
                payload = {
                    "enabled": bool(enabled),
                    "desktop": bool(desktop),
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                p.write_text(json.dumps(payload), encoding="utf-8")
                return {**payload, "desktop_available": False}
        except Exception as exc:  # noqa: BLE001
            logger.warning("computer_use_mode write failed: %s", exc)
    return get_mode()


def set_mode(enabled: bool) -> dict:
    """Persist the master switch (preserving the desktop sub-switch)."""
    return _update(enabled=enabled)


def set_desktop(enabled: bool) -> dict:
    """Persist the desktop sub-switch (preserving the master switch). Desktop
    control requires the master switch AND this sub-switch ON."""
    return _update(desktop=enabled)


def computer_use_enabled() -> bool:
    """True only when the master Computer-Use switch is ON."""
    return bool(get_mode().get("enabled"))


def desktop_enabled() -> bool:
    """True only when BOTH the master switch and the desktop sub-switch are ON."""
    m = get_mode()
    return bool(m.get("enabled")) and bool(m.get("desktop"))
