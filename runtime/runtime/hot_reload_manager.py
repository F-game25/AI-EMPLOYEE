"""Hot Reload Manager — apply module updates without restarting the system.

Usage::

    from runtime.hot_reload_manager import get_hot_reload_manager

    mgr = get_hot_reload_manager()
    result = mgr.reload(
        module="core/research_agent.py",
        new_code="def run(): ...",
        snapshot_id="abc123",
    )
    if not result["success"]:
        print(result["error"])     # automatically rolled back

Design
------
For each reload request the manager:

1. Reads the current content of the target file as the rollback payload.
2. Writes the new code to disk.
3. Invalidates and reimports the module via ``importlib``.
4. If import fails → writes the rollback payload back and marks the
   snapshot as ``rolled_back``.
5. Notifies the version_control of deployment or rollback status.

Thread safety: a single RLock serialises all reload calls so that two
concurrent forge submissions cannot race on the same file.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("runtime.hot_reload_manager")

_LOCK = threading.RLock()

# Modules that must never be live-reloaded (require full restart)
_NO_RELOAD_MODULES: frozenset[str] = frozenset({
    "main",
    "engine.api",
    "runtime.hot_reload_manager",
    "runtime.sandbox_executor",
    "runtime.version_control",
    "core.orchestrator",
})


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _module_path(module: str) -> Path:
    """Resolve a repo-relative module string to an absolute Path."""
    repo = _repo_root()
    candidates = [
        _runtime_root() / module,
        repo / module,
    ]
    for c in candidates:
        if c.exists():
            return c
    # New module — default to runtime/
    p = _runtime_root() / module
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _python_module_name(module: str) -> str:
    """Convert a file path like ``core/research_agent.py`` to ``core.research_agent``."""
    return module.replace("/", ".").replace("\\", ".").removesuffix(".py")


class HotReloadManager:
    """Live module updater with automatic rollback on failure."""

    def __init__(self) -> None:
        self._reload_history: list[dict[str, Any]] = []
        logger.info("HotReloadManager initialised")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reload(
        self,
        module: str,
        new_code: str,
        *,
        snapshot_id: str = "",
    ) -> dict[str, Any]:
        """Apply *new_code* to *module* and live-reload it.

        Args:
            module:      Repo-relative path, e.g. ``"core/research_agent.py"``.
            new_code:    Replacement Python source.
            snapshot_id: Optional VersionControl ID (used for status updates).

        Returns:
            ``{"success": bool, "module": str, "snapshot_id": str, ...}``
        """
        mod_name = _python_module_name(module)

        if mod_name in _NO_RELOAD_MODULES:
            return {
                "success": False,
                "module": module,
                "error": f"'{mod_name}' is in the no-reload list and requires a full restart.",
                "snapshot_id": snapshot_id,
                "ts": _ts(),
            }

        with _LOCK:
            target = _module_path(module)

            # 1. Read current content as rollback payload
            rollback_code = ""
            if target.exists():
                try:
                    rollback_code = target.read_text(encoding="utf-8")
                except OSError:
                    pass

            # 2. Write new code
            try:
                target.write_text(new_code, encoding="utf-8")
            except OSError:
                logger.exception("Failed to write module '%s' during reload", module)
                return self._record(
                    success=False,
                    module=module,
                    snapshot_id=snapshot_id,
                    error="Cannot write module.",
                )

            # 3. Attempt importlib reload
            reload_error = self._try_reload(mod_name)

            if reload_error:
                # 4. Rollback to previous content
                logger.warning(
                    "Reload of '%s' failed (%s) — rolling back", module, reload_error
                )
                try:
                    if rollback_code:
                        target.write_text(rollback_code, encoding="utf-8")
                    self._try_reload(mod_name)  # best-effort re-import of old code
                except Exception:  # noqa: BLE001
                    pass

                self._notify_vc(snapshot_id, "rolled_back")
                return self._record(
                    success=False,
                    module=module,
                    snapshot_id=snapshot_id,
                    error=reload_error,
                    rolled_back=True,
                )

            # 5. Success
            self._notify_vc(snapshot_id, "deployed")
            return self._record(
                success=True,
                module=module,
                snapshot_id=snapshot_id,
                error="",
            )

    def reload_history(self, *, limit: int = 30) -> list[dict[str, Any]]:
        """Return the most recent reload attempts."""
        with _LOCK:
            return list(self._reload_history[-limit:])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_reload(self, mod_name: str) -> str:
        """Attempt to reload *mod_name*.  Returns error string or empty string."""
        # Ensure runtime/ is on sys.path
        rt = str(_runtime_root())
        if rt not in sys.path:
            sys.path.insert(0, rt)

        try:
            if mod_name in sys.modules:
                importlib.reload(sys.modules[mod_name])
            else:
                spec = importlib.util.find_spec(mod_name)
                if spec:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return ""
        except Exception:  # noqa: BLE001
            logger.exception("Module reload failed for '%s'", mod_name)
            return "Module reload failed."

    def _notify_vc(self, snapshot_id: str, status: str) -> None:
        """Update VersionControl status for *snapshot_id* (best-effort)."""
        if not snapshot_id:
            return
        try:
            from runtime.version_control import get_version_control
            get_version_control().set_status(snapshot_id, status)
        except Exception:  # noqa: BLE001
            pass

    def _record(
        self,
        *,
        success: bool,
        module: str,
        snapshot_id: str,
        error: str,
        rolled_back: bool = False,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "ts": _ts(),
            "success": success,
            "module": module,
            "snapshot_id": snapshot_id,
            "error": error,
            "rolled_back": rolled_back,
        }
        with _LOCK:
            self._reload_history.append(entry)
            if len(self._reload_history) > 200:
                self._reload_history = self._reload_history[-200:]
        if success:
            logger.info("Reloaded '%s' successfully (snapshot=%s)", module, snapshot_id)
        else:
            logger.warning(
                "Reload of '%s' failed — %s (rolled_back=%s)", module, error, rolled_back
            )
        return entry


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: HotReloadManager | None = None
_instance_lock = threading.Lock()


def get_hot_reload_manager() -> HotReloadManager:
    """Return the process-wide HotReloadManager singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = HotReloadManager()
    return _instance
