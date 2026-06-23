"""Per-run model/provider hint set by the cost-first planner (request-scoped).

The compute planner (``engine.compute.compute_planner``) + escalation policy
(``core.model_escalation``) decide the cheapest model - and, when explicitly allowed,
the provider - that should handle a goal. That decision has to reach the actual inference
call without threading parameters through every layer of planner -> executor -> LLM client.

These ``contextvar``s hold the decision request-scoped (like the tenancy context). The LLM
surfaces read them as the DEFAULT when the caller did not pass an explicit value; they
NEVER override an explicit choice, and are set/reset per run via ``preferred_model_scope``
so they can't leak across requests.
"""
from __future__ import annotations

import contextlib
import contextvars

_preferred_model: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ai_employee_preferred_model", default=None
)
_preferred_provider: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ai_employee_preferred_provider", default=None
)


def set_preferred_model(model: str | None) -> contextvars.Token:
    """Set the per-run preferred model. Returns a token for ``reset_preferred_model``."""
    return _preferred_model.set((model or "").strip() or None)


def get_preferred_model() -> str | None:
    """The per-run preferred model, or ``None`` when unset."""
    return _preferred_model.get()


def reset_preferred_model(token: contextvars.Token) -> None:
    """Restore the previous model value - call in a ``finally`` block."""
    try:
        _preferred_model.reset(token)
    except (ValueError, LookupError):
        pass  # token from a different context - ignore


def set_preferred_provider(provider: str | None) -> contextvars.Token:
    """Set the per-run preferred provider (e.g. ``'openrouter'``). ``None`` = local."""
    return _preferred_provider.set((provider or "").strip().lower() or None)


def get_preferred_provider() -> str | None:
    """The per-run preferred provider, or ``None`` (local)."""
    return _preferred_provider.get()


def reset_preferred_provider(token: contextvars.Token) -> None:
    try:
        _preferred_provider.reset(token)
    except (ValueError, LookupError):
        pass


@contextlib.contextmanager
def preferred_model_scope(model: str | None, provider: str | None = None):
    """Set model+provider for the duration of a run, always resetting on exit."""
    mt = set_preferred_model(model)
    pt = set_preferred_provider(provider)
    try:
        yield
    finally:
        reset_preferred_provider(pt)
        reset_preferred_model(mt)
