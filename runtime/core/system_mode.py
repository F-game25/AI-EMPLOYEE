"""System Mode — global ON / OFF / AUTO autonomy state.

Controls whether the autonomy daemon processes tasks:
  OFF  — paused, no execution, UI monitoring only.
  ON   — limited execution (high-priority / safe tasks only).
  AUTO — full autonomous execution of all queued tasks.

Thread-safe singleton with optional file persistence.

Usage::

    from core.system_mode import get_system_mode

    sm = get_system_mode()
    sm.set_mode("AUTO")
    print(sm.current_mode)   # "AUTO"
    print(sm.is_active())    # True
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Literal

SystemModeType = Literal["OFF", "ON", "AUTO"]

_VALID_MODES: set[str] = {"OFF", "ON", "AUTO"}
_DEFAULT_MODE: SystemModeType = "OFF"
_DEFAULT_PATH = Path.home() / ".ai-employee" / "system_mode.json"


class SystemMode:
    """Thread-safe singleton that tracks the global autonomy mode."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._mode: SystemModeType = _DEFAULT_MODE
        self._emergency_stopped = False
        self._changed_at: str = _now()
        self._listeners: list[Any] = []
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            mode = data.get("mode", _DEFAULT_MODE).upper()
            if mode in _VALID_MODES:
                self._mode = mode  # type: ignore[assignment]
                self._changed_at = data.get("changed_at", _now())
        except Exception:
            pass

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(
                    {"mode": self._mode, "changed_at": self._changed_at},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def current_mode(self) -> SystemModeType:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str) -> SystemModeType:
        """Set mode (case-insensitive).  Raises ``ValueError`` for unknown modes."""
        upper = mode.upper()
        if upper not in _VALID_MODES:
            raise ValueError(
                f"Unknown mode '{mode}'. Choose from {sorted(_VALID_MODES)}."
            )
        with self._lock:
            self._mode = upper  # type: ignore[assignment]
            self._emergency_stopped = False
            self._changed_at = _now()
            self._save()
            self._notify()
        return self._mode

    def emergency_stop(self) -> None:
        """Immediately halt all autonomous execution."""
        with self._lock:
            self._mode = "OFF"
            self._emergency_stopped = True
            self._changed_at = _now()
            self._save()
            self._notify()

    def is_active(self) -> bool:
        """Return True if the daemon should be processing tasks."""
        return self.current_mode in ("ON", "AUTO")

    def is_auto(self) -> bool:
        return self.current_mode == "AUTO"

    def is_on(self) -> bool:
        return self.current_mode == "ON"

    def is_off(self) -> bool:
        return self.current_mode == "OFF"

    @property
    def emergency_stopped(self) -> bool:
        with self._lock:
            return self._emergency_stopped

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self._mode,
                "active": self._mode in ("ON", "AUTO"),
                "auto": self._mode == "AUTO",
                "limited": self._mode == "ON",
                "paused": self._mode == "OFF",
                "emergency_stopped": self._emergency_stopped,
                "changed_at": self._changed_at,
            }

    # ── Listener support ──────────────────────────────────────────────────────

    def on_change(self, callback: Any) -> None:
        """Register a callback invoked on mode change."""
        self._listeners.append(callback)

    def _notify(self) -> None:
        for cb in self._listeners:
            try:
                cb(self._mode)
            except Exception:
                pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: SystemMode | None = None
_instance_lock = threading.Lock()


def get_system_mode(path: Path | None = None) -> SystemMode:
    """Return the process-wide SystemMode singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SystemMode(path)
    return _instance
