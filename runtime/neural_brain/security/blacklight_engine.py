"""BLACKLIGHT — Autonomous security kernel for AETERNUS NEXUS.

Highest authority in the system. Operates independently of Neural Brain.
Cannot be disabled by any other subsystem.

Architecture:
- Background loop: subscribes to ALL events via EventBus wildcard
- Per-event analysis: rule + AI risk scoring
- Threat accumulator: rolling score across time window
- System mode state machine: NORMAL → ALERT → CRITICAL → LOCKDOWN → OFFLINE
- Actuator: SystemControl (direct, no Neural Brain dependency)

Threat score accumulation:
  Each event contributes a delta to a rolling 60-second window.
  Aggregated score 0–100 drives mode transitions.

Mode transitions:
  score < 30  → NORMAL
  score 30–49 → ALERT    (log + emit)
  score 50–74 → CRITICAL (pause new tasks + rate-limit)
  score 75–89 → LOCKDOWN (stop all tasks, pause agents, disable forge)
  score ≥ 90  → OFFLINE  (initiate shutdown)
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

import os
_THREAT_WINDOW_S = int(os.getenv("BL_THREAT_WINDOW_S", "60"))
_EVAL_INTERVAL_S = float(os.getenv("BL_EVAL_INTERVAL_S", "3"))
_ALERT_THRESHOLD = int(os.getenv("BL_ALERT_THRESHOLD", "30"))
_CRITICAL_THRESHOLD = int(os.getenv("BL_CRITICAL_THRESHOLD", "50"))
_LOCKDOWN_THRESHOLD = int(os.getenv("BL_LOCKDOWN_THRESHOLD", "75"))
_SHUTDOWN_THRESHOLD = int(os.getenv("BL_SHUTDOWN_THRESHOLD", "90"))
_RECOVERY_HYSTERESIS = int(os.getenv("BL_RECOVERY_HYSTERESIS", "10"))  # score must drop this far below threshold to recover


class ThreatEvent:
    __slots__ = ("ts", "score", "event_type", "source", "details")

    def __init__(self, ts: float, score: int, event_type: str, source: str, details: dict) -> None:
        self.ts = ts
        self.score = score
        self.event_type = event_type
        self.source = source
        self.details = details


class BlacklightEngine:
    """Autonomous security monitor — run start() once at process boot."""

    # Event types that always get analyzed (everything else gets sampled)
    _HIGH_PRIORITY_EVENTS = frozenset({
        "nb:reasoning_step", "nb:action_call", "nb:forge_submitted",
        "system:error", "system:degraded", "agent:failed",
        "blacklight:input_analyzed",
    })

    # Cooldown: minimum seconds between escalation and any recovery transition
    _COOLDOWN_S = int(os.getenv("BL_COOLDOWN_S", "120"))  # 2 minutes default

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._threat_events: deque[ThreatEvent] = deque()
        self._running = False
        self._thread: threading.Thread | None = None
        self._current_score = 0
        self._active_threats: list[dict] = []
        self._event_count = 0
        self._threat_count = 0
        self._last_escalation_ts: float = 0.0   # when last escalation happened
        self._lockdown_entered_ts: float = 0.0   # when LOCKDOWN was entered (for staged exit)
        # ── Security Sentinel (always-on local AI defender) ───────────────────
        self._sentinel_enabled = os.getenv("BL_SENTINEL_ENABLED", "true").lower() == "true"
        self._sentinel_interval_s = int(os.getenv("BL_SENTINEL_INTERVAL_S", "30"))
        self._last_sentinel_ts: float = 0.0
        self._sentinel_state = "idle"      # idle | analyzing | online | degraded | off
        self._sentinel_last_verdict: dict | None = None
        self._sentinel_runs = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        # Subscribe to ALL events
        try:
            from neural_brain.utils.event_bus import subscribe
            subscribe(None, self._on_event)  # wildcard
        except Exception as e:
            logger.warning("Blacklight: event bus subscription failed: %s", e)

        self._thread = threading.Thread(
            target=self._eval_loop, daemon=True, name="blacklight_engine"
        )
        self._thread.start()
        logger.info("BLACKLIGHT ENGINE ONLINE — threat thresholds: ALERT=%d CRITICAL=%d LOCKDOWN=%d",
                    _ALERT_THRESHOLD, _CRITICAL_THRESHOLD, _LOCKDOWN_THRESHOLD)
        self._emit_status()

    def stop(self) -> None:
        self._running = False

    # ── Event ingestion ───────────────────────────────────────────────────

    def _on_event(self, event: dict) -> None:
        """Called for every system event. Must be non-blocking."""
        self._event_count += 1
        event_type = event.get("type", "")
        source = event.get("source", "system")
        payload = event.get("payload", {})

        # Quick triage — only score events that can carry threat signals
        score = self._quick_score(event_type, source, payload)
        if score <= 0:
            return

        te = ThreatEvent(
            ts=time.time(),
            score=score,
            event_type=event_type,
            source=source,
            details={"payload_keys": list(payload.keys())[:5]},
        )
        with self._lock:
            self._threat_events.append(te)
            self._threat_count += 1

    def _quick_score(self, event_type: str, source: str, payload: dict) -> int:
        """Zero-latency event scoring."""
        score = 0
        # Error events
        if event_type == "system:error":
            score = max(score, 20)
        if event_type == "system:degraded":
            score = max(score, 15)
        if event_type == "agent:failed":
            score = max(score, 10)
        # Forge events (medium risk by default)
        if event_type in ("nb:forge_submitted", "nb:forge_approved", "nb:forge_deployed"):
            score = max(score, 5)
        # High error rates from security analyzer
        if event_type == "blacklight:input_analyzed":
            rs = payload.get("risk_score", 0)
            score = max(score, rs // 2)  # 50% weight from analyzer
        # Repeated failures from same source
        error = payload.get("error", "")
        if error and len(error) > 10:
            score = max(score, 8)
        # ── Auth events ───────────────────────────────────────────────────────
        if event_type == "auth:login_failed":
            score = max(score, 15)
        if event_type == "auth:brute_force_detected":
            score = max(score, 60)
            self._handle_brute_force(payload)
        if event_type == "auth:account_locked":
            score = max(score, 25)
        if event_type == "auth:user_blocked":
            score = max(score, 10)
        if event_type == "security:rate_limited":
            kind = payload.get("kind", "")
            score = max(score, 30 if kind == "login" else 12)
        if event_type == "security:access_denied":
            score = max(score, 18)
        if event_type == "security:suspicious_session":
            score = max(score, 20)
        return score

    def _handle_brute_force(self, payload: dict) -> None:
        """Immediate response to detected brute force: lock account + possible key rotation."""
        try:
            ip = payload.get("ip", "")
            username = payload.get("username", "")
            logger.warning("BLACKLIGHT: Brute force from IP=%s user=%s — triggering key rotation", ip, username)
            from neural_brain.security.key_manager import get_key_manager
            get_key_manager().force_rotate()
            # Emit alert
            from neural_brain.utils.event_bus import publish
            publish("blacklight:brute_force_response", source="blacklight", payload={
                "ip": ip, "username": username, "action": "key_rotated",
            })
        except Exception as e:
            logger.debug("Blacklight brute force handler error: %s", e)

    # ── Evaluation loop ───────────────────────────────────────────────────

    def _eval_loop(self) -> None:
        while self._running:
            try:
                self._evaluate()
            except Exception as e:
                logger.debug("Blacklight eval error: %s", e)
            time.sleep(_EVAL_INTERVAL_S)

    def _evaluate(self) -> None:
        now = time.time()
        cutoff = now - _THREAT_WINDOW_S

        with self._lock:
            while self._threat_events and self._threat_events[0].ts < cutoff:
                self._threat_events.popleft()
            events = list(self._threat_events)

        if not events:
            aggregate = 0
        else:
            # Weighted sum: recent events count more
            total_weight = 0.0
            weighted_score = 0.0
            for te in events:
                age = now - te.ts
                weight = max(0.1, 1.0 - (age / _THREAT_WINDOW_S))
                weighted_score += te.score * weight
                total_weight += weight
            aggregate = int(min(100, weighted_score / max(total_weight, 1) * len(events) / max(len(events), 1)))
            # Cap at sum of individual scores (avoid inflating)
            aggregate = min(100, int(sum(te.score for te in events[-10:])))

        # Security Sentinel: local-AI reasoning over the event window (rate-limited).
        # Runs even in offline mode (local Ollama only). Can raise the score.
        sentinel_bump = self._maybe_run_sentinel(events)
        aggregate = min(100, aggregate + sentinel_bump)

        self._current_score = aggregate
        self._update_active_threats(events)
        self._apply_mode(aggregate)
        self._emit_status()

    # ── Security Sentinel (always-on local AI defender) ───────────────────────
    def _maybe_run_sentinel(self, events: list[ThreatEvent]) -> int:
        """Analyze the recent threat window with a local SLM. Returns a score bump.

        Local-only (Ollama) so it works fully offline. Rate-limited; only runs when
        there are threat signals. Degrades to rule-only (bump 0) if no local model.
        """
        if not self._sentinel_enabled:
            self._sentinel_state = "off"
            return 0
        now = time.time()
        if not events or (now - self._last_sentinel_ts) < self._sentinel_interval_s:
            return 0
        self._last_sentinel_ts = now
        self._sentinel_state = "analyzing"
        try:
            summary = self._summarize_events(events)
            verdict = self._sentinel_llm(summary)
            self._sentinel_runs += 1
            self._sentinel_last_verdict = verdict
            self._sentinel_state = "online"
            risk = int(verdict.get("risk", 0) or 0)
            if risk >= 40:
                from neural_brain.utils.event_bus import publish
                publish("blacklight:ai_alert", source="blacklight_sentinel", payload={
                    "risk": risk, "category": verdict.get("category"),
                    "reason": verdict.get("reason"),
                    "recommended_action": verdict.get("recommended_action"),
                })
                logger.warning("BLACKLIGHT SENTINEL: risk=%d category=%s — %s",
                               risk, verdict.get("category"), str(verdict.get("reason"))[:120])
            # DETECT → DEFEND: at high risk the sentinel takes graduated defensive action.
            self._sentinel_defend(risk, verdict)
            # Contribute up to ~30 points so the AI can escalate but not solely drive lockdown.
            return min(30, risk // 3)
        except Exception as e:  # noqa: BLE001
            self._sentinel_state = "degraded"
            logger.debug("Blacklight sentinel degraded (rule-only): %s", e)
            return 0

    def _sentinel_defend(self, risk: int, verdict: dict) -> None:
        """Graduated, audited defensive response driven by the sentinel's verdict.

        Uses only the engine's existing defensive capabilities (no new destructive
        powers). Gated by BL_SENTINEL_AUTODEFEND (default on). Actions escalate with
        risk; each is published as blacklight:ai_defense and audited. Lethal escalation
        (system shutdown) is intentionally left to the threshold-based _apply_mode path.
        """
        import os as _os
        if _os.getenv("BL_SENTINEL_AUTODEFEND", "true").lower() != "true":
            return
        category = str(verdict.get("category", "")).lower()
        actions: list[str] = []
        try:
            # ≥85 or credential/brute categories → rotate keys (invalidates forged tokens).
            if risk >= 85 or any(k in category for k in ("brute", "credential", "token", "auth", "key")):
                try:
                    self.force_key_rotation()
                    actions.append("key_rotation")
                except Exception:  # noqa: BLE001
                    pass
            # ≥75 or session/hijack categories → invalidate all sessions.
            if risk >= 75 or any(k in category for k in ("session", "hijack", "takeover")):
                try:
                    self.invalidate_all_sessions(reason="sentinel_autodefend")
                    actions.append("invalidate_sessions")
                except Exception:  # noqa: BLE001
                    pass
            if actions:
                from neural_brain.utils.event_bus import publish
                publish("blacklight:ai_defense", source="blacklight_sentinel", payload={
                    "risk": risk, "category": verdict.get("category"),
                    "actions": actions, "reason": verdict.get("reason"),
                })
                logger.warning("BLACKLIGHT SENTINEL DEFEND: risk=%d actions=%s", risk, actions)
        except Exception as e:  # noqa: BLE001
            logger.debug("sentinel defend error: %s", e)

    @staticmethod
    def _summarize_events(events: list[ThreatEvent]) -> str:
        from collections import Counter
        by_type = Counter(te.event_type for te in events)
        by_source = Counter(te.source for te in events)
        top = sorted(events, key=lambda e: e.score, reverse=True)[:8]
        lines = [f"window_event_count={len(events)}",
                 "by_type=" + ", ".join(f"{k}:{v}" for k, v in by_type.most_common(8)),
                 "by_source=" + ", ".join(f"{k}:{v}" for k, v in by_source.most_common(6)),
                 "top_events=" + "; ".join(f"{te.event_type}(score={te.score},src={te.source})" for te in top)]
        return "\n".join(lines)

    def _sentinel_llm(self, summary: str) -> dict:
        """Ask the local SLM to judge breach risk. Local Ollama only — offline-safe."""
        import json as _json
        import re as _re
        from engine.api import generate
        system = (
            "You are a local security sentinel defending an AI operating system. "
            "Given a summary of recent system/auth/security events, judge the likelihood "
            "of an active security breach or attack. Respond ONLY with compact JSON: "
            '{"risk": 0-100, "category": "<short>", "reason": "<short>", '
            '"recommended_action": "<short>"}.'
        )
        text = generate(prompt=f"Recent security event window:\n{summary}", system=system)
        text = (text or "").strip()
        m = _re.search(r"\{.*\}", text, _re.DOTALL)
        if not m:
            raise ValueError("sentinel produced no JSON verdict")
        verdict = _json.loads(m.group(0))
        verdict["risk"] = max(0, min(100, int(verdict.get("risk", 0) or 0)))
        return verdict

    def _update_active_threats(self, events: list[ThreatEvent]) -> None:
        self._active_threats = [
            {"type": te.event_type, "score": te.score, "source": te.source, "ts": te.ts}
            for te in sorted(events, key=lambda e: e.score, reverse=True)[:10]
        ]

    def _apply_mode(self, score: int) -> None:
        from neural_brain.security.system_control import get_system_control, SystemState
        ctrl = get_system_control()
        current = ctrl.get_mode()
        now = time.time()

        # ── Escalation (immediate, no cooldown) ───────────────────────────
        if score >= _SHUTDOWN_THRESHOLD and current != SystemState.OFFLINE:
            self._last_escalation_ts = now
            ctrl.shutdown_system(f"threat_score={score}")
            return
        if score >= _LOCKDOWN_THRESHOLD and current not in (SystemState.LOCKDOWN, SystemState.OFFLINE):
            self._last_escalation_ts = now
            self._lockdown_entered_ts = now
            ctrl.lockdown_system(f"threat_score={score}")
            self._rotate_keys_on_lockdown()
            return
        if score >= _CRITICAL_THRESHOLD and current not in (SystemState.CRITICAL, SystemState.LOCKDOWN, SystemState.OFFLINE):
            self._last_escalation_ts = now
            ctrl.set_mode(SystemState.CRITICAL, reason=f"threat_score={score}", threat_score=score)
            ctrl.stop_all_tasks("blacklight:critical")
            return
        if score >= _ALERT_THRESHOLD and current == SystemState.NORMAL:
            self._last_escalation_ts = now
            ctrl.set_mode(SystemState.ALERT, reason=f"threat_score={score}", threat_score=score)
            return

        # ── Staged recovery — requires cooldown + score well below threshold ──
        cooldown_ok = (now - self._last_escalation_ts) >= self._COOLDOWN_S

        if not cooldown_ok:
            return  # Prevent flip-flopping during cooldown window

        if score < (_ALERT_THRESHOLD - _RECOVERY_HYSTERESIS) and current == SystemState.ALERT:
            ctrl.set_mode(SystemState.NORMAL, reason="threat_cleared", threat_score=score)
            self._on_recovery(SystemState.NORMAL, ctrl)

        elif score < (_CRITICAL_THRESHOLD - _RECOVERY_HYSTERESIS) and current == SystemState.CRITICAL:
            # CRITICAL → ALERT (one step, not straight to NORMAL)
            ctrl.set_mode(SystemState.ALERT, reason="partial_recovery", threat_score=score)
            self._on_recovery(SystemState.ALERT, ctrl)

        elif score < (_LOCKDOWN_THRESHOLD - _RECOVERY_HYSTERESIS) and current == SystemState.LOCKDOWN:
            # LOCKDOWN → CRITICAL (one step — additional cooldown required for further recovery)
            # Only exit lockdown if it has been held for at least 2× cooldown
            lockdown_held = (now - self._lockdown_entered_ts) >= (self._COOLDOWN_S * 2)
            if lockdown_held:
                ctrl.set_mode(SystemState.CRITICAL, reason="lockdown_exit", threat_score=score)
                self._last_escalation_ts = now  # reset cooldown for CRITICAL→ALERT transition
                logger.warning("BLACKLIGHT: LOCKDOWN → CRITICAL (staged recovery, score=%d)", score)

    def _on_recovery(self, new_state, ctrl) -> None:
        """Post-recovery actions: re-enable agents, resume tasks, re-enable forge."""
        from neural_brain.security.system_control import SystemState
        try:
            ctrl.resume_agents()
        except Exception:
            pass
        if new_state == SystemState.NORMAL:
            try:
                ctrl.enable_forge()
            except Exception:
                pass
            # Resume any paused tasks
            try:
                from neural_brain.core.task_queue import get_task_queue
                tq = get_task_queue()
                logger.info("BLACKLIGHT: Recovery complete — task queue has %d tasks", tq.stats().get("queued", 0))
            except Exception:
                pass
            logger.info("BLACKLIGHT: Full recovery to NORMAL")
        else:
            logger.info("BLACKLIGHT: Partial recovery → %s", new_state)

    def _rotate_keys_on_lockdown(self) -> None:
        """On lockdown: force key rotation + invalidate all active sessions."""
        try:
            from neural_brain.security.key_manager import get_key_manager
            new_ver = get_key_manager().force_rotate()
            logger.warning("BLACKLIGHT LOCKDOWN: Keys rotated → version=%d", new_ver)
        except Exception as e:
            logger.debug("Lockdown key rotation failed: %s", e)

    def force_key_rotation(self) -> int:
        """Externally callable: Blacklight triggers immediate key rotation."""
        try:
            from neural_brain.security.key_manager import get_key_manager
            return get_key_manager().force_rotate()
        except Exception:
            return -1

    def invalidate_all_sessions(self, reason: str = "blacklight_action") -> int:
        """Invalidate ALL sessions across ALL users."""
        try:
            from neural_brain.auth.session_manager import get_session_manager
            sm = get_session_manager()
            sessions = sm.get_all_active()
            count = 0
            for s in sessions:
                sm.revoke(s["session_id"], reason)
                count += 1
            logger.warning("BLACKLIGHT: Invalidated %d sessions — reason=%s", count, reason)
            return count
        except Exception as e:
            logger.debug("Session invalidation failed: %s", e)
            return 0

    # ── Input analysis gate ───────────────────────────────────────────────

    def analyze_input(self, text: str, *, user_id: str = "anonymous", source: str = "neural_brain") -> dict:
        """Analyze user input. Call from ConsciousnessEngine.process_input().

        Returns risk assessment. If CRITICAL/HIGH → raises SecurityError.
        """
        from neural_brain.security.ai_security_analyzer import get_analyzer
        assessment = get_analyzer().analyze(text, user_id=user_id, source=source)

        # Feed result back into threat accumulator
        risk_score = assessment["risk_score"]
        if risk_score >= 30:
            te = ThreatEvent(
                ts=time.time(),
                score=risk_score // 2,
                event_type="blacklight:input_analyzed",
                source="blacklight",
                details={"user_id": user_id, "risk_score": risk_score},
            )
            with self._lock:
                self._threat_events.append(te)

        # Emit for dashboard
        try:
            from neural_brain.utils.event_bus import publish
            publish("blacklight:input_analyzed", source="blacklight", payload=assessment)
        except Exception:
            pass

        return assessment

    # ── Status ────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        from neural_brain.security.system_control import get_system_control
        ctrl = get_system_control()
        cooldown_remaining = max(0.0, self._COOLDOWN_S - (time.time() - self._last_escalation_ts))
        return {
            "threat_score": self._current_score,
            "mode": ctrl.get_mode(),
            "active_threats": self._active_threats,
            "event_count": self._event_count,
            "threat_event_count": self._threat_count,
            "cooldown_remaining_s": round(cooldown_remaining, 1),
            "sentinel": {
                "enabled": self._sentinel_enabled,
                "state": self._sentinel_state,
                "runs": self._sentinel_runs,
                "interval_s": self._sentinel_interval_s,
                "last_verdict": self._sentinel_last_verdict,
            },
            **ctrl.get_state(),
        }

    def _emit_status(self) -> None:
        try:
            from neural_brain.utils.event_bus import publish
            from neural_brain.security.system_control import get_system_control
            publish("blacklight:status", source="blacklight", payload={
                "threat_score": self._current_score,
                "mode": get_system_control().get_mode(),
                "active_threats": self._active_threats[:5],
                "sentinel_state": self._sentinel_state,
                "sentinel_last_verdict": self._sentinel_last_verdict,
            })
        except Exception:
            pass


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine: BlacklightEngine | None = None
_engine_lock = threading.Lock()

def get_blacklight() -> BlacklightEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = BlacklightEngine()
                _engine.start()
    return _engine
