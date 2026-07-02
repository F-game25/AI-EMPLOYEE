"""Per-tenant process-local singleton pool.

A plain process-wide ``_instance`` shares BOTH its file path and its in-memory
cache across every tenant the process serves — a cross-tenant data leak. This pool
holds one instance per active tenant (keyed by tenant id, or ``__global__`` when no
tenant context is set), so each tenant gets an isolated instance whose state file
resolves under its own ``tenants/<id>/state`` tree via ``tenant_state_dir()``.

Behaviour-preserving for the common path: with no active tenant (local/default
mode, CLI, tests) every caller shares the single ``__global__`` instance — exactly
like the previous global singleton. Per-tenant isolation only engages when the
tenant middleware has set a request-scoped tenant.
"""
from __future__ import annotations

import threading
from typing import Callable, Generic, TypeVar

from core.state_paths import active_tenant_id

T = TypeVar("T")

_GLOBAL_KEY = "__global__"


class TenantSingletonPool(Generic[T]):
    """Lazily build and cache one instance of ``T`` per active tenant."""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._instances: dict[str, T] = {}
        self._lock = threading.Lock()

    def get(self) -> T:
        key = active_tenant_id() or _GLOBAL_KEY
        with self._lock:
            inst = self._instances.get(key)
            if inst is None:
                inst = self._factory()
                self._instances[key] = inst
            return inst

    def set(self, instance: T) -> None:
        """Pin an instance for the active tenant (used by accessors that accept an
        explicit override, e.g. tests passing a custom path)."""
        key = active_tenant_id() or _GLOBAL_KEY
        with self._lock:
            self._instances[key] = instance

    def reset(self) -> None:
        """Drop all cached instances (test isolation / reconfiguration)."""
        with self._lock:
            self._instances.clear()
