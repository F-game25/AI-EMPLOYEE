"""Circuit Breaker implementation for ASCEND AI.

Protects LLM providers, the memory system, and the database from cascading
failures by applying the classic CLOSED → OPEN → HALF_OPEN state machine.

────────────────────────────────────────────────────────────────
STATES
────────────────────────────────────────────────────────────────

  CLOSED    — normal operation.  Failures are counted; once
              ``failure_threshold`` is reached within the rolling
              ``window_seconds`` window the circuit trips to OPEN.

  OPEN      — fast-fail: every call immediately raises
              ``CircuitBreakerOpenError`` without touching the
              downstream system.  After ``recovery_timeout`` seconds
              the breaker moves to HALF_OPEN for a probe.

  HALF_OPEN — one call is let through.  If it succeeds the breaker
              resets to CLOSED; if it fails it returns to OPEN and
              the recovery timer restarts.

────────────────────────────────────────────────────────────────
NAMED BREAKERS
────────────────────────────────────────────────────────────────

Pre-defined names:

  llm:anthropic   llm:openai   llm:groq
  llm:ollama      llm:gemma    llm:nvidia
  memory          database

Breakers are created on first access via the global registry.

────────────────────────────────────────────────────────────────
PUBLIC API
────────────────────────────────────────────────────────────────

::

    from core.circuit_breaker import get_circuit_registry, CircuitBreakerOpenError

    registry = get_circuit_registry()

    # Protect a call
    cb = registry.get("llm:openai")
    try:
        result = cb.call(my_openai_fn, *args, **kwargs)
    except CircuitBreakerOpenError:
        # fast-fail — return fallback immediately
        result = FALLBACK

    # Report all breaker states (for the /api/circuit-breakers endpoint)
    status = registry.status_all()
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger("ai_employee.circuit_breaker")

F = TypeVar("F", bound=Callable[..., Any])

# ── Defaults (override via environment variables) ─────────────────────────────

import os as _os

def _env_int(name: str, default: int) -> int:
    try:
        return int(_os.environ[name])
    except (KeyError, ValueError):
        return default

def _env_float(name: str, default: float) -> float:
    try:
        return float(_os.environ[name])
    except (KeyError, ValueError):
        return default

DEFAULT_FAILURE_THRESHOLD: int   = _env_int("CB_FAILURE_THRESHOLD", 5)
DEFAULT_RECOVERY_TIMEOUT: float  = _env_float("CB_RECOVERY_TIMEOUT", 30.0)
DEFAULT_SUCCESS_THRESHOLD: int   = _env_int("CB_SUCCESS_THRESHOLD", 2)
DEFAULT_WINDOW_SECONDS: float    = _env_float("CB_WINDOW_SECONDS", 60.0)


# ── State ─────────────────────────────────────────────────────────────────────

class CBState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


# ── Exceptions ────────────────────────────────────────────────────────────────

class CircuitBreakerOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit is OPEN."""

    def __init__(self, name: str, reset_in: float) -> None:
        self.name = name
        self.reset_in = reset_in
        super().__init__(
            f"Circuit breaker '{name}' is OPEN — calls rejected. "
            f"Retrying in {reset_in:.1f}s."
        )


# ── CircuitBreaker ────────────────────────────────────────────────────────────

class CircuitBreaker:
    """Thread-safe CLOSED/OPEN/HALF_OPEN circuit breaker.

    Parameters
    ----------
    name:
        Human-readable identifier (e.g. "llm:openai", "memory").
    failure_threshold:
        Number of failures within *window_seconds* that trips the breaker.
    recovery_timeout:
        Seconds to wait in OPEN state before probing (HALF_OPEN).
    success_threshold:
        Consecutive successes needed in HALF_OPEN to close the breaker.
    window_seconds:
        Rolling window for failure counting.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int   = DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: float  = DEFAULT_RECOVERY_TIMEOUT,
        success_threshold: int   = DEFAULT_SUCCESS_THRESHOLD,
        window_seconds: float    = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self.name              = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout  = recovery_timeout
        self.success_threshold = success_threshold
        self.window_seconds    = window_seconds

        self._lock             = threading.RLock()
        self._state            = CBState.CLOSED
        self._failure_times: deque[float] = deque()
        self._half_open_successes: int    = 0
        self._opened_at: float            = 0.0
        self._total_calls: int            = 0
        self._total_failures: int         = 0
        self._total_rejections: int       = 0

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def state(self) -> CBState:
        with self._lock:
            self._maybe_transition()
            return self._state

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute *fn* if the circuit allows, otherwise raise CircuitBreakerOpenError.

        Records success/failure automatically.
        """
        with self._lock:
            self._maybe_transition()

            if self._state == CBState.OPEN:
                self._total_rejections += 1
                reset_in = max(0.0, self.recovery_timeout - (time.monotonic() - self._opened_at))
                raise CircuitBreakerOpenError(self.name, reset_in)

            if self._state == CBState.HALF_OPEN:
                # Only one probe call at a time
                pass  # fall through to execute

            self._total_calls += 1

        # Execute outside the lock so we don't hold it during I/O
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            self._on_failure(exc)
            raise
        else:
            self._on_success()
            return result

    def reset(self) -> None:
        """Manually force the breaker back to CLOSED."""
        with self._lock:
            self._state = CBState.CLOSED
            self._failure_times.clear()
            self._half_open_successes = 0
            self._opened_at = 0.0
        logger.info("Circuit breaker '%s' manually reset to CLOSED", self.name)

    def force_open(self, reason: str = "manual") -> None:
        """Manually trip the breaker to OPEN."""
        with self._lock:
            self._state = CBState.OPEN
            self._opened_at = time.monotonic()
        logger.warning("Circuit breaker '%s' manually forced OPEN: %s", self.name, reason)

    def status(self) -> dict[str, Any]:
        """Return a JSON-serialisable status snapshot."""
        with self._lock:
            self._maybe_transition()
            recent = self._recent_failure_count()
            reset_in = (
                max(0.0, self.recovery_timeout - (time.monotonic() - self._opened_at))
                if self._state == CBState.OPEN
                else None
            )
            return {
                "name":             self.name,
                "state":            self._state.value,
                "recent_failures":  recent,
                "failure_threshold": self.failure_threshold,
                "total_calls":      self._total_calls,
                "total_failures":   self._total_failures,
                "total_rejections": self._total_rejections,
                "reset_in_seconds": reset_in,
            }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _maybe_transition(self) -> None:
        """Check if we should move from OPEN → HALF_OPEN (called while locked)."""
        if self._state == CBState.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = CBState.HALF_OPEN
                self._half_open_successes = 0
                logger.info("Circuit breaker '%s' → HALF_OPEN (probing)", self.name)

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CBState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.success_threshold:
                    self._state = CBState.CLOSED
                    self._failure_times.clear()
                    self._half_open_successes = 0
                    logger.info("Circuit breaker '%s' → CLOSED (recovered)", self.name)

    def _on_failure(self, exc: Exception) -> None:
        with self._lock:
            now = time.monotonic()
            self._failure_times.append(now)
            self._total_failures += 1
            self._trim_old_failures(now)

            if self._state == CBState.HALF_OPEN:
                # Probe failed — back to OPEN
                self._state = CBState.OPEN
                self._opened_at = now
                logger.warning(
                    "Circuit breaker '%s' probe failed → OPEN again: %s", self.name, exc
                )
            elif self._state == CBState.CLOSED:
                if self._recent_failure_count() >= self.failure_threshold:
                    self._state = CBState.OPEN
                    self._opened_at = now
                    logger.error(
                        "Circuit breaker '%s' TRIPPED → OPEN after %d failures: %s",
                        self.name, self.failure_threshold, exc,
                    )
                    self._notify_audit()

    def _recent_failure_count(self) -> int:
        """Count failures in the rolling window (called while locked)."""
        cutoff = time.monotonic() - self.window_seconds
        while self._failure_times and self._failure_times[0] < cutoff:
            self._failure_times.popleft()
        return len(self._failure_times)

    def _trim_old_failures(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._failure_times and self._failure_times[0] < cutoff:
            self._failure_times.popleft()

    def _notify_audit(self) -> None:
        """Best-effort notification to AuditEngine (non-fatal)."""
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _rdir = _Path(__file__).resolve().parent.parent
            if str(_rdir) not in _sys.path:
                _sys.path.insert(0, str(_rdir))
            from core.audit_engine import get_audit_engine  # type: ignore
            get_audit_engine().record(
                actor="circuit_breaker",
                action="circuit_tripped",
                input_data={"breaker": self.name, "threshold": self.failure_threshold},
                output_data={"state": "open"},
                risk_score=0.60,
                meta={"xai_module": "circuit_breaker"},
            )
        except Exception:
            pass


# ── CircuitBreakerRegistry ────────────────────────────────────────────────────

#: Well-known names with domain-specific defaults.
_REGISTRY_DEFAULTS: dict[str, dict[str, Any]] = {
    # LLM providers — trip quickly (external I/O), longer recovery
    "llm:anthropic": {"failure_threshold": 3, "recovery_timeout": 45.0},
    "llm:openai":    {"failure_threshold": 3, "recovery_timeout": 45.0},
    "llm:groq":      {"failure_threshold": 3, "recovery_timeout": 30.0},
    "llm:ollama":    {"failure_threshold": 5, "recovery_timeout": 20.0},
    "llm:gemma":     {"failure_threshold": 5, "recovery_timeout": 20.0},
    "llm:nvidia":    {"failure_threshold": 3, "recovery_timeout": 45.0},
    # Internal systems — more tolerant
    "memory":        {"failure_threshold": 5, "recovery_timeout": 15.0},
    "database":      {"failure_threshold": 5, "recovery_timeout": 15.0},
}


class CircuitBreakerRegistry:
    """Thread-safe registry of named :class:`CircuitBreaker` instances."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, name: str) -> CircuitBreaker:
        """Return the named breaker, creating it on first access."""
        with self._lock:
            if name not in self._breakers:
                kwargs = _REGISTRY_DEFAULTS.get(name, {})
                self._breakers[name] = CircuitBreaker(name, **kwargs)
            return self._breakers[name]

    def status_all(self) -> list[dict[str, Any]]:
        """Return status snapshots for all registered breakers."""
        with self._lock:
            names = list(self._breakers.keys())
        return [self.get(n).status() for n in sorted(names)]

    def reset_all(self) -> None:
        """Reset every registered breaker to CLOSED."""
        with self._lock:
            names = list(self._breakers.keys())
        for name in names:
            self.get(name).reset()

    def pre_populate(self) -> None:
        """Pre-create all well-known breakers so they appear in status_all()."""
        for name in _REGISTRY_DEFAULTS:
            self.get(name)


# ── Singleton ─────────────────────────────────────────────────────────────────

_registry_instance: Optional[CircuitBreakerRegistry] = None
_registry_lock = threading.Lock()


def get_circuit_registry() -> CircuitBreakerRegistry:
    """Return the process-wide :class:`CircuitBreakerRegistry` singleton."""
    global _registry_instance
    with _registry_lock:
        if _registry_instance is None:
            _registry_instance = CircuitBreakerRegistry()
            _registry_instance.pre_populate()
    return _registry_instance
