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

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_FILENAME = "computer_use_mode.json"


def _state_dir() -> Path:
    try:
        from core.state_paths import canonical_state_dir
        return canonical_state_dir()
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parents[2] / "state"


def _path() -> Path:
    return _state_dir() / _FILENAME


def get_mode() -> dict:
    """Return ``{enabled, desktop, desktop_available, updated_at}``. Fails safe to OFF.

    ``enabled``  — master Computer-Use switch.
    ``desktop``  — desktop (screen/system) sub-switch; control needs BOTH on.
    """
    with _LOCK:
        try:
            data = json.loads(_path().read_text(encoding="utf-8"))
            return {
                "enabled": bool(data.get("enabled", False)),
                "desktop": bool(data.get("desktop", False)),
                "desktop_available": False,  # kept for back-compat (driver check lives in desktop_control)
                "updated_at": data.get("updated_at"),
            }
        except FileNotFoundError:
            return {"enabled": False, "desktop": False, "desktop_available": False, "updated_at": None}
        except Exception as exc:  # noqa: BLE001
            logger.warning("computer_use_mode read failed (defaulting OFF): %s", exc)
            return {"enabled": False, "desktop": False, "desktop_available": False, "updated_at": None}


def _write(enabled: bool, desktop: bool) -> dict:
    payload = {
        "enabled": bool(enabled),
        "desktop": bool(desktop),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with _LOCK:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("computer_use_mode write failed: %s", exc)
    return {**payload, "desktop_available": False}


def set_mode(enabled: bool) -> dict:
    """Persist the master switch (preserving the desktop sub-switch)."""
    return _write(enabled, get_mode().get("desktop", False))


def set_desktop(enabled: bool) -> dict:
    """Persist the desktop sub-switch (preserving the master switch). Desktop
    control requires the master switch AND this sub-switch ON."""
    return _write(get_mode().get("enabled", False), enabled)


def computer_use_enabled() -> bool:
    """True only when the master Computer-Use switch is ON."""
    return bool(get_mode().get("enabled"))


def desktop_enabled() -> bool:
    """True only when BOTH the master switch and the desktop sub-switch are ON."""
    m = get_mode()
    return bool(m.get("enabled")) and bool(m.get("desktop"))
