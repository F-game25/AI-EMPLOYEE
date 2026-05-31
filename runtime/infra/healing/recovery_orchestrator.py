"""RecoveryOrchestrator — policy engine that drives self-healing actions."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .schema import HealingEvent, HealingEventType, RecoveryAction, RecoveryPolicy
from .circuit_breaker import get_circuit_registry
from .health_scorer import score_service
from .predictive_detector import get_predictive_detector
from .workflow_watchdog import get_workflow_watchdog

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 30     # seconds between health sweeps
_HEALTH_THRESHOLD = 40  # trigger recovery below this score
_DB = Path(os.path.expanduser("~/.ai-employee/healing.db"))
_POLICY_FILE = Path(os.path.expanduser("~/.ai-employee/healing_policies.json"))

_DEFAULT_POLICIES = {
    "system": {
        "actions": ["restart_agent", "degrade", "alert"],
        "restart_attempts": 3, "restart_backoff_s": 5.0
    }
}


def _load_policies() -> dict:
    if _POLICY_FILE.exists():
        try:
            return json.loads(_POLICY_FILE.read_text())
        except Exception:
            pass
    return _DEFAULT_POLICIES


def _conn() -> sqlite3.Connection:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB), timeout=10)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("""
        CREATE TABLE IF NOT EXISTS healing_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            service TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            ts REAL NOT NULL
        )
    """)
    c.commit()
    return c


def _log_event(evt: HealingEvent) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO healing_events (event_type,service,message,details,ts) VALUES (?,?,?,?,?)",
            (evt.event_type.value, evt.service, evt.message, json.dumps(evt.details), evt.ts)
        )


class RecoveryOrchestrator:
    def __init__(self):
        self._policies = _load_policies()
        self._in_recovery: set[str] = set()

    async def start(self) -> None:
        logger.info("RecoveryOrchestrator started (poll every %ds)", _POLL_INTERVAL)
        # Start sub-tasks
        asyncio.create_task(get_predictive_detector().start_poll_loop())
        asyncio.create_task(get_workflow_watchdog().start())
        while True:
            await asyncio.sleep(_POLL_INTERVAL)
            await self._sweep()

    async def _sweep(self) -> None:
        services = list(self._policies.keys()) + ["ai_backend", "node_backend"]
        for svc in services:
            hs = score_service(svc)
            if hs.score < _HEALTH_THRESHOLD and svc not in self._in_recovery:
                logger.warning("Service %s health=%.1f — triggering recovery", svc, hs.score)
                asyncio.create_task(self._recover(svc, hs.score))

    async def _recover(self, service: str, trigger_score: float) -> None:
        self._in_recovery.add(service)
        try:
            policy_data = self._policies.get(service, self._policies.get("system", {}))
            actions = [RecoveryAction(a) for a in policy_data.get("actions", ["degrade", "alert"])]
            max_restarts = policy_data.get("restart_attempts", 3)
            backoff = policy_data.get("restart_backoff_s", 5.0)

            _log_event(HealingEvent(
                HealingEventType.RECOVERY_ATTEMPTED, service,
                f"Score {trigger_score:.1f} triggered recovery"
            ))

            success = False
            for action in actions:
                try:
                    ok = await self._execute_action(action, service, max_restarts, backoff)
                    if ok:
                        success = True
                        break
                except Exception as e:
                    logger.error("Recovery action %s failed for %s: %s", action, service, e)

            if success:
                _log_event(HealingEvent(HealingEventType.RECOVERY_SUCCEEDED, service, "Recovery succeeded"))
            else:
                _log_event(HealingEvent(HealingEventType.RECOVERY_FAILED, service, "All recovery actions exhausted"))
                await self._send_alert(service, trigger_score)
        finally:
            self._in_recovery.discard(service)

    async def _execute_action(self, action: RecoveryAction, service: str,
                              max_restarts: int, backoff: float) -> bool:
        if action == RecoveryAction.RESTART_AGENT:
            for attempt in range(max_restarts):
                logger.info("Restart attempt %d/%d for %s", attempt + 1, max_restarts, service)
                await asyncio.sleep(backoff * (attempt + 1))
                # Signal restart via event bus so agent supervisors can act
                try:
                    from infra.events.bus import get_event_bus
                    await get_event_bus().publish("healing:restart_agent", {
                        "service": service, "attempt": attempt + 1, "max": max_restarts
                    })
                except Exception as _e:
                    logger.warning("Event bus unavailable for restart signal: %s", _e)
                hs = score_service(service)
                if hs.score >= _HEALTH_THRESHOLD:
                    return True
            return False

        if action == RecoveryAction.DEGRADE:
            logger.warning("Service %s entering degraded mode — opening circuit", service)
            # OPEN the circuit so callers get fast-fail + fallback, not force-closed
            reg = get_circuit_registry()
            cb = reg.get(service)
            from .schema import CircuitState
            if cb.state != CircuitState.OPEN:
                # Inject failures up to threshold to trigger OPEN transition
                for _ in range(cb.threshold):
                    reg.record_failure(service)
            try:
                from infra.events.bus import get_event_bus
                await get_event_bus().publish("healing:degrade", {"service": service})
            except Exception:
                pass
            return False  # degraded ≠ success, continue to alert

        if action == RecoveryAction.ALERT:
            await self._send_alert(service, 0)
            return False

        if action == RecoveryAction.SCALE_OUT:
            logger.info("Scale-out signal for %s (no k8s — skipping)", service)
            return False

        if action == RecoveryAction.ROLLBACK:
            logger.info("Rollback requested for %s — no snapshot configured", service)
            return False

        return False

    @staticmethod
    async def _send_alert(service: str, score: float) -> None:
        try:
            from infra.events.bus import get_event_bus
            await get_event_bus().publish("healing:alert", {
                "service": service, "score": score,
                "message": f"All recovery actions exhausted for {service}"
            })
        except Exception:
            pass

    def get_events(self, limit: int = 50) -> list[dict]:
        with _conn() as c:
            rows = c.execute(
                "SELECT event_type,service,message,details,ts FROM healing_events "
                "ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"event_type": r[0], "service": r[1], "message": r[2],
                 "details": json.loads(r[3]), "ts": r[4]} for r in rows]

    def inject_failure(self, service: str, count: int = 6) -> dict:
        reg = get_circuit_registry()
        for _ in range(count):
            reg.record_failure(service)
        return {"ok": True, "service": service, "failures_injected": count,
                "circuit_state": reg.get(service).state.value}


_orchestrator: Optional[RecoveryOrchestrator] = None


def get_recovery_orchestrator() -> RecoveryOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RecoveryOrchestrator()
    return _orchestrator
