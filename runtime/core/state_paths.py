"""Canonical state-directory resolver.

Single source of truth for where runtime state lives. `start.sh` exports
`STATE_DIR=<AI_HOME>/state` (default `~/.ai-employee/state`) and the Node backend
reads from there. Several modules historically used `AI_EMPLOYEE_STATE_DIR` with a
*relative* `"state"` default, so they wrote into the repo-local `./state` instead —
splitting state across two dirs (e.g. llm_calls.jsonl written repo-local but read
from ~/.ai-employee/state). Everything must resolve through here.

Two seams:

* ``canonical_state_dir()`` — the install-global tree. Use for state that is
  intentionally shared across tenants (telemetry identity, OS update metadata,
  privacy mode).
* ``tenant_state_dir()`` — the active tenant's private tree when a request-scoped
  tenant context is set, else falls back to ``canonical_state_dir()``. Use for any
  per-tenant data store (knowledge, memory, economy, learning, feedback, …) so one
  tenant can never read or overwrite another tenant's state.
"""
import os
from pathlib import Path
from typing import Optional


def canonical_state_dir() -> Path:
    explicit = os.environ.get("STATE_DIR") or os.environ.get("AI_EMPLOYEE_STATE_DIR")
    if explicit:
        return Path(explicit).resolve()
    home = Path(
        os.environ.get("AI_EMPLOYEE_HOME")
        or os.environ.get("AI_HOME")
        or Path.home() / ".ai-employee"
    )
    return (home / "state").resolve()


def _active_tenant_state_dir() -> Optional[Path]:
    """Resolve the request-scoped tenant's state dir, or ``None`` when there is no
    active tenant / the tenant manager is not initialized (CLI, tests, local mode).

    Lazy import of ``core.tenancy`` avoids an import cycle (tenancy may import this
    module) and keeps state_paths dependency-free at import time. Never raises —
    any failure degrades to the install-global tree."""
    try:
        from core.tenancy import get_tenant_manager  # lazy — avoid import cycle
        manager = get_tenant_manager()
        context = manager.get_current_tenant()
    except Exception:
        return None
    tenant_id = getattr(context, "tenant_id", None) if context else None
    if not tenant_id:
        return None
    try:
        return manager.get_tenant_state_dir(tenant_id).resolve()
    except Exception:
        return None


def tenant_state_dir() -> Path:
    """State directory for the ACTIVE tenant, falling back to the install-global
    tree when no tenant context is set.

    This is the multi-tenant isolation seam for per-tenant data stores. With an
    active tenant (set by the FastAPI/Node tenant middleware) it returns that
    tenant's private ``tenants/<id>/state`` tree; with none (local/default mode,
    CLI, tests) it returns ``canonical_state_dir()`` so existing single-tenant
    behavior is unchanged."""
    tdir = _active_tenant_state_dir()
    return tdir if tdir is not None else canonical_state_dir()


def active_tenant_id() -> Optional[str]:
    """The active request-scoped tenant id, or ``None`` in local/default mode
    (no tenant context — CLI, tests, single-tenant). Used to key per-tenant
    in-memory singletons so one tenant's cached state never serves another."""
    try:
        from core.tenancy import get_tenant_manager  # lazy — avoid import cycle
        context = get_tenant_manager().get_current_tenant()
    except Exception:
        return None
    return getattr(context, "tenant_id", None) if context else None
