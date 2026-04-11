"""Mode Manager — global AUTO / MANUAL / BLACKLIGHT state.

Persists the current operating mode to ~/.ai-employee/mode.json so it
survives restarts.

Modes:
  AUTO       — task engine runs jobs from the scheduler without human gating.
  MANUAL     — every side-effecting action waits for explicit human approval.
  BLACKLIGHT — AUTO + DecisionEngine applies aggressive profit weighting (0.8).

Usage::

    from core.mode_manager import get_mode_manager

    mgr = get_mode_manager()
    mgr.set_mode("BLACKLIGHT")
    print(mgr.current_mode)   # "BLACKLIGHT"
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Literal

ModeType = Literal["AUTO", "MANUAL", "BLACKLIGHT"]

_VALID_MODES: set[str] = {"AUTO", "MANUAL", "BLACKLIGHT"}
_DEFAULT_MODE: ModeType = "MANUAL"
_DEFAULT_PATH = Path.home() / ".ai-employee" / "mode.json"
_MODE_PROFILES: dict[str, dict[str, float | str]] = {
    "MANUAL": {
        "decision_threshold": 0.75,
        "execution_frequency": "low",
        "risk_tolerance": "low",
    },
    "AUTO": {
        "decision_threshold": 0.6,
        "execution_frequency": "medium",
        "risk_tolerance": "medium",
    },
    "BLACKLIGHT": {
        "decision_threshold": 0.45,
        "execution_frequency": "high",
        "risk_tolerance": "high",
    },
}


class ModeManager:
    """Singleton that tracks and persists the active operating mode."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._mode: ModeType = _DEFAULT_MODE
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            mode = data.get("mode", _DEFAULT_MODE).upper()
            if mode in _VALID_MODES:
                self._mode = mode  # type: ignore[assignment]
        except Exception:
            pass

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"mode": self._mode}, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_mode(self) -> ModeType:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str) -> ModeType:
        """Set *mode* (case-insensitive). Raises ``ValueError`` for unknown modes."""
        upper = mode.upper()
        if upper not in _VALID_MODES:
            raise ValueError(f"Unknown mode '{mode}'. Choose from {sorted(_VALID_MODES)}.")
        with self._lock:
            self._mode = upper  # type: ignore[assignment]
            self._save()

            # Propagate to DecisionEngine if available
            try:
                from core.decision_engine import get_decision_engine
                get_decision_engine().set_blacklight_mode(upper == "BLACKLIGHT")
            except Exception:
                pass

        return self._mode

    def is_auto(self) -> bool:
        return self.current_mode in ("AUTO", "BLACKLIGHT")

    def is_manual(self) -> bool:
        return self.current_mode == "MANUAL"

    def is_blacklight(self) -> bool:
        return self.current_mode == "BLACKLIGHT"

    def status(self) -> dict:
        mode = self.current_mode
        profile = _MODE_PROFILES.get(mode, _MODE_PROFILES["MANUAL"])
        return {
            "mode": mode,
            "auto_execution": mode in ("AUTO", "BLACKLIGHT"),
            "requires_approval": mode == "MANUAL",
            "aggressive_profit": mode == "BLACKLIGHT",
            "decision_threshold": profile["decision_threshold"],
            "execution_frequency": profile["execution_frequency"],
            "risk_tolerance": profile["risk_tolerance"],
            "description": {
                "AUTO": "Task engine runs jobs autonomously from the scheduler.",
                "MANUAL": "Every side-effecting action requires human approval.",
                "BLACKLIGHT": "AUTO + aggressive profit-maximising decision weights.",
            }[mode],
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ModeManager | None = None
_instance_lock = threading.Lock()


def get_mode_manager(path: Path | None = None) -> ModeManager:
    """Return the process-wide ModeManager singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ModeManager(path)
    return _instance
