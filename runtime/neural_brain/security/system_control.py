"""System Control — Blacklight's enforcement arm.

Highest-authority module. NOT dependent on Neural Brain — can operate
even if ConsciousnessEngine is completely broken.

Actions available:
  stop_all_tasks()     — drain + cancel task queue
  pause_agents()       — set agent pool to paused state
  resume_agents()      — lift agent pause
  disable_forge()      — freeze forge (no new deployments)
  enable_forge()       — re-enable forge
  lockdown_system()    — pause agents + disable forge + rate-limit all inputs
  shutdown_system()    — full graceful shutdown (emit event, then os signal)
  get_state()          — current control state snapshot
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time

logger = logging.getLogger(__name__)


class SystemState:
    NORMAL = "NORMAL"
    ALERT = "ALERT"
    CRITICAL = "CRITICAL"
    LOCKDOWN = "LOCKDOWN"
    OFFLINE = "OFFLINE"


class SystemControl:
    """Direct system actuator. Thread-safe. No external deps at import time."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._agents_paused = False
        self._forge_disabled = False
        self._inputs_blocked = False
        self._current_mode = SystemState.NORMAL
        self._mode_history: list[dict] = []
        self._pause_reason = ""
        self._forge_reason = ""

    # ── Agent control ─────────────────────────────────────────────────────

    def pause_agents(self, reason: str = "blacklight") -> None:
        with self._lock:
            self._agents_paused = True
            self._pause_reason = reason
        logger.warning("SystemControl: agents PAUSED — %s", reason)
        self._emit("system:agents_paused", {"reason": reason})
        try:
            from neural_brain.core.task_queue import get_task_queue
            get_task_queue().cancel_all()
        except Exception:
            pass

    def resume_agents(self) -> None:
        with self._lock:
            self._agents_paused = False
            self._pause_reason = ""
        logger.info("SystemControl: agents RESUMED")
        self._emit("system:agents_resumed", {})

    def is_agents_paused(self) -> bool:
        return self._agents_paused

    # ── Task queue control ────────────────────────────────────────────────

    def stop_all_tasks(self, reason: str = "blacklight") -> int:
        cancelled = 0
        try:
            from neural_brain.core.task_queue import get_task_queue
            cancelled = get_task_queue().cancel_all()
        except Exception as e:
            logger.warning("stop_all_tasks error: %s", e)
        self._emit("system:tasks_stopped", {"cancelled": cancelled, "reason": reason})
        return cancelled

    # ── Forge control ─────────────────────────────────────────────────────

    def disable_forge(self, reason: str = "blacklight") -> None:
        with self._lock:
            self._forge_disabled = True
            self._forge_reason = reason
        logger.warning("SystemControl: forge DISABLED — %s", reason)
        # Notify via event bus — ForgeController subscribes to system:forge_disabled
        self._emit("system:forge_disabled", {"reason": reason})

    def enable_forge(self) -> None:
        with self._lock:
            self._forge_disabled = False
            self._forge_reason = ""
        logger.info("SystemControl: forge ENABLED")
        self._emit("system:forge_enabled", {})

    def is_forge_disabled(self) -> bool:
        return self._forge_disabled

    # ── System mode ───────────────────────────────────────────────────────

    def set_mode(self, mode: str, reason: str = "", threat_score: int = 0) -> None:
        with self._lock:
            previous = self._current_mode
            if mode == previous:
                return
            self._current_mode = mode
            self._mode_history.append({
                "from": previous,
                "to": mode,
                "ts": time.time(),
                "reason": reason,
                "threat_score": threat_score,
            })
            if len(self._mode_history) > 100:
                self._mode_history.pop(0)

        logger.warning("SystemControl: mode %s → %s (score=%d, reason=%s)", previous, mode, threat_score, reason)
        self._emit("blacklight:mode_change", {
            "mode": mode,
            "previous": previous,
            "reason": reason,
            "threat_score": threat_score,
        })

    def get_mode(self) -> str:
        return self._current_mode

    # ── Lockdown ──────────────────────────────────────────────────────────

    def lockdown_system(self, reason: str = "threat detected") -> None:
        self.set_mode(SystemState.LOCKDOWN, reason=reason)
        self.pause_agents(reason)
        self.disable_forge(reason)
        self.stop_all_tasks(reason)
        with self._lock:
            self._inputs_blocked = True
        self._emit("blacklight:lockdown", {"reason": reason})
        logger.critical("SystemControl: LOCKDOWN ACTIVATED — %s", reason)

    def is_input_blocked(self) -> bool:
        return self._inputs_blocked

    # ── Shutdown ──────────────────────────────────────────────────────────

    def shutdown_system(self, reason: str = "blacklight emergency") -> None:
        self.set_mode(SystemState.OFFLINE, reason=reason)
        self.stop_all_tasks(reason)
        self._emit("system:shutdown", {"reason": reason})
        logger.critical("SystemControl: SHUTDOWN — %s", reason)
        # Give event a moment to propagate before killing process
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    # ── State ─────────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        with self._lock:
            return {
                "mode": self._current_mode,
                "agents_paused": self._agents_paused,
                "forge_disabled": self._forge_disabled,
                "inputs_blocked": self._inputs_blocked,
                "pause_reason": self._pause_reason,
                "forge_reason": self._forge_reason,
                "mode_history": list(self._mode_history[-10:]),
            }

    # ── Internal ──────────────────────────────────────────────────────────

    def _emit(self, event_type: str, payload: dict) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            publish(event_type, source="blacklight", payload=payload)
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────
_ctrl: SystemControl | None = None
_ctrl_lock = threading.Lock()

def get_system_control() -> SystemControl:
    global _ctrl
    if _ctrl is None:
        with _ctrl_lock:
            if _ctrl is None:
                _ctrl = SystemControl()
    return _ctrl
