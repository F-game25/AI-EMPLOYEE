"""Backend-driven avatar visual-state engine for the Companion Gateway.

The avatar is NOT free-running on the frontend — the backend decides what the
avatar is doing and emits a single, well-typed event the UI consumes. This keeps
the visual state truthful: the avatar "executes" only when the broker actually
executes, "needs approval" only when the safety gate actually blocked something.

Public surface::

    from companion.avatar_state_engine import get_avatar_state_engine
    eng = get_avatar_state_engine()
    state = eng.state_for(mode="execution", phase="executing")   # -> "executing"
    payload = eng.event(state, intensity=0.8, focus="forge.apply_patch")
"""
from __future__ import annotations

import threading
from typing import Any, Optional

# ── Visual states (exact strings — the frontend switches on these) ─────────────
IDLE = "idle"
LISTENING = "listening"
THINKING = "thinking"
PLANNING = "planning"
SPEAKING = "speaking"
EXECUTING = "executing"
MONITORING = "monitoring"
LEARNING = "learning"
WARNING = "warning"
APPROVAL_NEEDED = "approval_needed"
ERROR = "error"

ALL_STATES = (
    IDLE, LISTENING, THINKING, PLANNING, SPEAKING, EXECUTING,
    MONITORING, LEARNING, WARNING, APPROVAL_NEEDED, ERROR,
)

EVENT_TYPE = "companion:avatar_state_changed"

# Runtime phases the orchestrator passes as it moves through a turn. These are the
# *what's happening right now* signals; mode is *what kind of turn this is*.
PHASE_RECEIVING = "receiving"
PHASE_RESOLVING = "resolving"
PHASE_CLASSIFYING = "classifying"
PHASE_PLANNING = "planning"
PHASE_GENERATING = "generating"
PHASE_EXECUTING = "executing"
PHASE_MONITORING = "monitoring"
PHASE_AWAITING_APPROVAL = "awaiting_approval"
PHASE_LEARNING = "learning"
PHASE_SPEAKING = "speaking"
PHASE_DONE = "done"
PHASE_ERROR = "error"

# Phase dominates (it reflects the live runtime step). Mode is the fallback when a
# phase is generic ("done"/None) so the avatar settles into a mode-appropriate rest.
_PHASE_TO_STATE: dict[str, str] = {
    PHASE_RECEIVING: LISTENING,
    PHASE_RESOLVING: THINKING,
    PHASE_CLASSIFYING: THINKING,
    PHASE_PLANNING: PLANNING,
    PHASE_GENERATING: THINKING,
    PHASE_EXECUTING: EXECUTING,
    PHASE_MONITORING: MONITORING,
    PHASE_AWAITING_APPROVAL: APPROVAL_NEEDED,
    PHASE_LEARNING: LEARNING,
    PHASE_SPEAKING: SPEAKING,
    PHASE_ERROR: ERROR,
}

# Resting state per intent mode (used when phase is done/unknown).
_MODE_REST_STATE: dict[str, str] = {
    "conversation": SPEAKING,
    "analysis": SPEAKING,
    "planning": PLANNING,
    "execution": EXECUTING,
    "monitoring": MONITORING,
    "debugging": THINKING,
    "learning": LEARNING,
    "approval": APPROVAL_NEEDED,
}


class AvatarStateEngine:
    """Maps (intent mode, runtime phase) → a single avatar visual state."""

    def state_for(self, mode: str, phase: str) -> str:
        """Resolve the avatar state for a turn.

        Phase wins when it maps to a concrete state (it is the live runtime
        signal). When the phase is terminal/unknown the avatar settles into a
        mode-appropriate resting state, defaulting to ``idle``.
        """
        ph = (phase or "").strip().lower()
        md = (mode or "").strip().lower()

        if ph in _PHASE_TO_STATE:
            return _PHASE_TO_STATE[ph]
        if ph in ("", PHASE_DONE):
            return _MODE_REST_STATE.get(md, IDLE)
        # Unknown phase string → never throw; settle on mode rest or idle.
        return _MODE_REST_STATE.get(md, IDLE)

    def event(
        self,
        state: str,
        intensity: float = 0.6,
        focus: Optional[str] = None,
        message: Optional[str] = None,
        progress: Optional[float] = None,
    ) -> dict[str, Any]:
        """Build the WS payload the frontend renders for an avatar transition."""
        st = state if state in ALL_STATES else IDLE
        try:
            inten = max(0.0, min(1.0, float(intensity)))
        except (TypeError, ValueError):
            inten = 0.6
        prog: Optional[float] = None
        if progress is not None:
            try:
                prog = max(0.0, min(1.0, float(progress)))
            except (TypeError, ValueError):
                prog = None
        return {
            "type": EVENT_TYPE,
            "state": st,
            "intensity": round(inten, 3),
            "focusTarget": focus,
            "message": message,
            "progress": prog,
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: Optional[AvatarStateEngine] = None
_instance_lock = threading.Lock()


def get_avatar_state_engine() -> AvatarStateEngine:
    """Return the process-wide ``AvatarStateEngine`` singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = AvatarStateEngine()
    return _instance
