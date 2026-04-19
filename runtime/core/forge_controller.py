"""Forge Controller — critical safety layer for Ascend Forge submissions.

This is the *only* path through which code changes may enter the live system.
It enforces:

- Security validation via sandbox_executor
- Protected-module enforcement
- Snapshot creation in version_control
- Forwarding to hot_reload_manager
- Learning signal forwarding to self_learning_brain / memory_router

Usage::

    from core.forge_controller import get_forge_controller

    fc = get_forge_controller()
    result = fc.submit_change(
        module="agents/my_new_agent.py",
        code=source_code,
        description="New lead-generation agent",
        auto_deploy=False,   # wait for manual approval
    )
    if result["status"] == "awaiting_approval":
        fc.approve(result["snapshot_id"])

Decision flow::

    submit_change()
        → sandbox_executor.run()       # validate + dry-run
        → version_control.create_snapshot()
        → if auto_deploy (and safe):
              hot_reload_manager.reload()
              self_learning_brain.record_outcome()
              memory_router.store()

Stability rule: ``Stability > intelligence growth``
Critical-core modules are never auto-deployed; they require manual approval.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("core.forge_controller")

_LOCK = threading.RLock()

# Modules where auto_deploy is **always** forced False regardless of caller flag
_AUTO_DEPLOY_BLOCKED: frozenset[str] = frozenset({
    "core/orchestrator.py",
    "core/forge_controller.py",
    "engine/api.py",
    "main.py",
    "runtime/hot_reload_manager.py",
    "runtime/sandbox_executor.py",
    "runtime/version_control.py",
})

# Modules that are entirely write-protected through forge
_WRITE_PROTECTED: frozenset[str] = frozenset({
    "main.py",
    "engine/api.py",
    "runtime/sandbox_executor.py",
})


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ForgeController:
    """Central safety layer for all Ascend Forge code submissions.

    Responsibilities
    ----------------
    - Validate code before any disk write
    - Enforce write-protection on core modules
    - Route safe changes to hot_reload_manager
    - Record every change in version_control
    - Feed learning signal to self_learning_brain
    - Prevent unsafe evolution paths

    Rule: Stability > intelligence growth
    """

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}  # snapshot_id → record
        logger.info("ForgeController initialised")

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def submit_change(
        self,
        *,
        module: str,
        code: str,
        description: str = "",
        tag: str = "",
        author: str = "forge",
        auto_deploy: bool = False,
    ) -> dict[str, Any]:
        """Submit a code change for validation and (optional) deployment.

        Args:
            module:      Repo-relative module path, e.g. ``"agents/my_agent.py"``.
            code:        New Python source code.
            description: Human-readable description of the change.
            tag:         Optional version tag (e.g. ``"v1.3"``).
            author:      Submitter name / system component.
            auto_deploy: When True and module is not in the auto-deploy blocklist,
                         the change is applied immediately after validation.

        Returns:
            A dict with ``status``, ``snapshot_id``, ``validation``, and ``ts``.
        """
        # 0. Write-protection
        if module in _WRITE_PROTECTED:
            return {
                "status": "rejected",
                "reason": f"'{module}' is write-protected and cannot be modified via Forge.",
                "snapshot_id": None,
                "ts": _ts(),
            }

        # 1. Sandbox validation
        sandbox = self._get_sandbox()
        validation = sandbox.run(code, module_name=module, target_module=module)
        if not validation["safe"]:
            logger.warning(
                "Forge submission REJECTED for '%s': %s",
                module,
                validation["errors"],
            )
            return {
                "status": "rejected",
                "reason": "Sandbox validation failed",
                "validation": validation,
                "snapshot_id": None,
                "ts": _ts(),
            }

        # 2. Create snapshot (reads current content for rollback)
        current_code = self._read_current(module)
        vc = self._get_vc()
        snapshot_id = vc.create_snapshot(
            module=module,
            code=code,
            description=description,
            tag=tag,
            author=author,
            previous_code=current_code,
        )

        # 3. Block auto-deploy for critical-core modules
        effective_auto = auto_deploy and module not in _AUTO_DEPLOY_BLOCKED

        if not effective_auto:
            with _LOCK:
                self._pending[snapshot_id] = {
                    "module": module,
                    "code": code,
                    "snapshot_id": snapshot_id,
                    "description": description,
                    "submitted_at": _ts(),
                    "validation": validation,
                }
            reason = (
                f"Module '{module}' requires manual approval before deployment."
                if module in _AUTO_DEPLOY_BLOCKED
                else "auto_deploy=False — awaiting manual approval."
            )
            return {
                "status": "awaiting_approval",
                "reason": reason,
                "snapshot_id": snapshot_id,
                "validation": validation,
                "ts": _ts(),
            }

        # 4. Deploy immediately
        return self._deploy(snapshot_id, module, code, validation)

    # ------------------------------------------------------------------
    # Approve / reject pending changes
    # ------------------------------------------------------------------

    def approve(self, snapshot_id: str) -> dict[str, Any]:
        """Approve and deploy a pending submission.

        Args:
            snapshot_id: The ID returned by ``submit_change()``.

        Returns:
            Deployment result dict.
        """
        with _LOCK:
            pending = self._pending.pop(snapshot_id, None)
        if pending is None:
            return {
                "status": "error",
                "error": f"No pending submission with ID '{snapshot_id}'",
                "ts": _ts(),
            }
        return self._deploy(
            snapshot_id,
            pending["module"],
            pending["code"],
            pending["validation"],
        )

    def reject(self, snapshot_id: str, reason: str = "") -> dict[str, Any]:
        """Reject a pending submission without deployment."""
        with _LOCK:
            pending = self._pending.pop(snapshot_id, None)
        if pending is None:
            return {"status": "error", "error": f"No pending submission '{snapshot_id}'"}
        self._get_vc().set_status(snapshot_id, "rolled_back")
        logger.info("Forge submission %s rejected: %s", snapshot_id, reason or "no reason given")
        return {"status": "rejected", "snapshot_id": snapshot_id, "reason": reason, "ts": _ts()}

    def list_pending(self) -> list[dict[str, Any]]:
        """Return all currently pending (awaiting approval) submissions."""
        with _LOCK:
            return [
                {k: v for k, v in rec.items() if k != "code"}
                for rec in self._pending.values()
            ]

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def rollback(self, snapshot_id: str) -> dict[str, Any]:
        """Roll back a previously deployed snapshot.

        The rollback itself is also sandboxed (previous code is re-validated).
        """
        vc = self._get_vc()
        snap = vc.get(snapshot_id)
        if snap is None:
            return {"success": False, "error": f"Snapshot '{snapshot_id}' not found"}

        rollback_code = snap.get("rollback_code", "")
        module = snap.get("module", "")

        if not rollback_code:
            return {"success": False, "error": "No rollback code stored for this snapshot"}

        # Validate rollback code through sandbox
        sandbox = self._get_sandbox()
        val = sandbox.run(rollback_code, module_name=f"rollback:{module}", target_module=module)
        if not val["safe"]:
            return {
                "success": False,
                "error": "Rollback code failed sandbox validation",
                "validation": val,
            }

        result = self._get_hrm().reload(module, rollback_code, snapshot_id=f"rollback:{snapshot_id}")
        self._feed_learning(
            action=f"forge.rollback:{module}",
            success=result.get("success", False),
            context=f"rollback snapshot {snapshot_id} in {module}",
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _deploy(
        self,
        snapshot_id: str,
        module: str,
        code: str,
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        hrm = self._get_hrm()
        result = hrm.reload(module, code, snapshot_id=snapshot_id)

        success = result.get("success", False)
        self._feed_learning(
            action=f"forge.deploy:{module}",
            success=success,
            context=f"forge deployment snapshot={snapshot_id}",
        )
        self._store_memory(module=module, success=success, snapshot_id=snapshot_id)

        return {
            "status": "deployed" if success else "failed",
            "snapshot_id": snapshot_id,
            "reload_result": result,
            "validation_warnings": validation.get("warnings", []),
            "ts": _ts(),
        }

    def _read_current(self, module: str) -> str:
        """Read current on-disk content of *module* for rollback storage."""
        try:
            from runtime.version_control import _resolve_module_path
            path = _resolve_module_path(module)
            if path and path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _get_sandbox(self):  # type: ignore[return]
        from runtime.sandbox_executor import get_sandbox_executor
        return get_sandbox_executor()

    def _get_vc(self):  # type: ignore[return]
        from runtime.version_control import get_version_control
        return get_version_control()

    def _get_hrm(self):  # type: ignore[return]
        from runtime.hot_reload_manager import get_hot_reload_manager
        return get_hot_reload_manager()

    def _feed_learning(self, *, action: str, success: bool, context: str) -> None:
        try:
            from core.self_learning_brain import get_self_learning_brain
            get_self_learning_brain().record_outcome(
                action=action,
                success=success,
                context=context,
                strategy="forge",
            )
        except Exception:  # noqa: BLE001
            pass

    def _store_memory(self, *, module: str, success: bool, snapshot_id: str) -> None:
        try:
            from memory.memory_router import get_memory_router
            text = (
                f"Forge {'deployed' if success else 'failed to deploy'} '{module}' "
                f"(snapshot={snapshot_id})"
            )
            get_memory_router().store(
                f"forge:{snapshot_id}",
                text,
                memory_type="episodic",
                source="forge_controller",
                importance=0.6 if success else 0.3,
            )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # V4: Profit Impact Analysis + ROI-ranked suggestion queue
    # ------------------------------------------------------------------

    def profit_impact_analysis(
        self,
        *,
        module: str,
        description: str = "",
        change_type: str = "optimization",
    ) -> dict[str, Any]:
        """Estimate the ROI impact of a proposed Forge change.

        Args:
            module:       Module being changed.
            description:  What the change does.
            change_type:  One of: optimization, new_agent, memory, ui, tool.

        Returns:
            Dict with expected_revenue_increase, efficiency_gain,
            stability_risk, roi_score, priority.
        """
        eco = self._get_eco()

        # Base estimates from economy state
        base_roi = 0.0
        if eco:
            try:
                summary = eco.system_summary()
                base_roi = summary.get("global_roi", 0.0)
            except Exception:  # noqa: BLE001
                pass

        # Heuristic impact matrix by change_type
        _impact: dict[str, dict[str, float]] = {
            "optimization":  {"revenue": 0.10, "efficiency": 0.20, "risk": 0.10},
            "new_agent":     {"revenue": 0.25, "efficiency": 0.05, "risk": 0.25},
            "memory":        {"revenue": 0.05, "efficiency": 0.30, "risk": 0.15},
            "ui":            {"revenue": 0.02, "efficiency": 0.05, "risk": 0.05},
            "tool":          {"revenue": 0.35, "efficiency": 0.10, "risk": 0.20},
        }
        impact = _impact.get(change_type, _impact["optimization"])

        # Penalise core-module changes with higher risk
        if module in _AUTO_DEPLOY_BLOCKED:
            impact = {**impact, "risk": min(impact["risk"] + 0.25, 0.95)}

        # ROI score: (revenue + efficiency) / risk
        roi_score = round(
            (impact["revenue"] + impact["efficiency"]) / max(impact["risk"], 0.01), 3
        )

        # Priority
        if roi_score >= 3.0:
            priority = "critical"
        elif roi_score >= 1.5:
            priority = "high"
        elif roi_score >= 0.8:
            priority = "medium"
        else:
            priority = "low"

        analysis = {
            "module": module,
            "change_type": change_type,
            "description": description,
            "expected_revenue_increase": round(impact["revenue"] * 100, 1),  # %
            "efficiency_gain": round(impact["efficiency"] * 100, 1),         # %
            "stability_risk": round(impact["risk"] * 100, 1),                # %
            "roi_score": roi_score,
            "priority": priority,
            "base_system_roi": round(base_roi, 4),
            "auto_deploy_eligible": priority in ("critical", "high") and module not in _AUTO_DEPLOY_BLOCKED,
            "ts": _ts(),
        }
        logger.info(
            "Profit impact analysis: %s | roi=%.3f | priority=%s",
            module, roi_score, priority,
        )
        return analysis

    def roi_suggestions(self, *, limit: int = 5) -> list[dict[str, Any]]:
        """Return ROI-ranked improvement suggestions from the economy engine.

        Combines economy engine suggestions with forge-specific analysis.
        Always sorted highest ROI first.  Low ROI suggestions are excluded.
        """
        eco = self._get_eco()
        suggestions: list[dict[str, Any]] = []

        if eco:
            try:
                eco_suggestions = eco.suggest_improvements(limit=limit * 2)
                for s in eco_suggestions:
                    # Enrich with forge ROI analysis
                    analysis = self.profit_impact_analysis(
                        module=f"agents/{s.get('agent', 'unknown')}.py",
                        description=s.get("reason", ""),
                        change_type="optimization" if s.get("type") == "optimize" else "new_agent",
                    )
                    suggestions.append({**s, "roi_analysis": analysis})
            except Exception:  # noqa: BLE001
                pass

        # Add competition engine proposals
        try:
            from core.agent_competition_engine import get_competition_engine
            rewrites = get_competition_engine().propose_rewrites(limit=3)
            for rw in rewrites:
                analysis = self.profit_impact_analysis(
                    module=f"agents/{rw.get('agent', 'unknown')}.py",
                    description=rw.get("description", "Competition engine rewrite proposal"),
                    change_type="optimization",
                )
                suggestions.append({
                    "type": "rewrite",
                    "agent": rw.get("agent"),
                    "reason": rw.get("description", ""),
                    "roi_impact": analysis["roi_score"],
                    "priority": analysis["priority"],
                    "roi_analysis": analysis,
                })
        except Exception:  # noqa: BLE001
            pass

        # Filter out low-ROI, sort by roi_score desc
        suggestions = [s for s in suggestions if s.get("roi_impact", 0) >= 0.5]
        suggestions.sort(
            key=lambda s: s.get("roi_analysis", {}).get("roi_score", 0),
            reverse=True,
        )
        return suggestions[:limit]

    @staticmethod
    def _get_eco():  # type: ignore[return]
        try:
            from core.economy_engine import get_economy_engine
            return get_economy_engine()
        except Exception:  # noqa: BLE001
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ForgeController | None = None
_instance_lock = threading.Lock()


def get_forge_controller() -> ForgeController:
    """Return the process-wide ForgeController singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ForgeController()
    return _instance
