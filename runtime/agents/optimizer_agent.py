"""Optimizer Agent — system-wide bottleneck detector and improvement proposer (V4).

The Optimizer Agent runs continuously in the background, scanning the economy
engine and competition rankings for underperforming modules and agents, then
proposing targeted improvements via ForgeController.

Responsibilities:
- Monitor economy metrics (ROI, efficiency, budget depletion)
- Detect performance bottlenecks (agents with low scores, slow task paths)
- Generate ROI-ranked improvement proposals
- Submit proposals to ForgeController for human review

Usage::

    from agents.optimizer_agent import get_optimizer_agent

    opt = get_optimizer_agent()

    # Run a single analysis cycle
    findings = opt.analyze()

    # Submit the top proposals to forge
    opt.submit_proposals(auto_deploy=False, limit=3)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("agents.optimizer_agent")

_SCAN_INTERVAL_S = float(__import__("os").environ.get("AI_EMPLOYEE_OPTIMIZER_INTERVAL", "300"))
_MIN_TASKS_BEFORE_SCAN = 3


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class OptimizerAgent:
    """Economy-driven improvement proposer.

    Runs a background scan loop and exposes on-demand analysis methods.
    All proposals are submitted through ForgeController — no direct modifications.
    """

    def __init__(self) -> None:
        self._proposals: list[dict[str, Any]] = []
        self._scan_count: int = 0
        self._last_scan: str = ""
        self._running = False
        self._thread: threading.Thread | None = None
        logger.info("OptimizerAgent initialised (scan_interval=%.0fs)", _SCAN_INTERVAL_S)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_background_loop(self) -> None:
        """Start the background scan loop (daemon thread)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="optimizer-agent",
            daemon=True,
        )
        self._thread.start()
        logger.info("OptimizerAgent background loop started")

    def stop(self) -> None:
        """Stop the background loop."""
        self._running = False

    def analyze(self) -> dict[str, Any]:
        """Run a full optimization analysis cycle.

        Returns:
            Dict with bottlenecks, suggestions, and economy summary.
        """
        self._scan_count += 1
        self._last_scan = _ts()

        economy_summary = self._get_economy_summary()
        bottlenecks = self._detect_bottlenecks()
        competition_proposals = self._get_competition_proposals()
        forge_suggestions = self._get_forge_suggestions()

        findings = {
            "scan_id": self._scan_count,
            "ts": self._last_scan,
            "economy_summary": economy_summary,
            "bottlenecks": bottlenecks,
            "competition_proposals": competition_proposals,
            "forge_suggestions": forge_suggestions,
            "total_proposals": len(bottlenecks) + len(competition_proposals),
        }
        logger.info(
            "OptimizerAgent scan #%d — %d bottlenecks, %d forge suggestions",
            self._scan_count, len(bottlenecks), len(forge_suggestions),
        )
        return findings

    def submit_proposals(
        self,
        *,
        auto_deploy: bool = False,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Submit the top ROI-ranked proposals to ForgeController.

        Args:
            auto_deploy: Pass through to ForgeController.
            limit:       Maximum proposals to submit per cycle.

        Returns:
            List of ForgeController submission results.
        """
        findings = self.analyze()
        suggestions = findings.get("forge_suggestions", [])[:limit]

        results: list[dict[str, Any]] = []
        for sug in suggestions:
            result = self._submit_suggestion(sug, auto_deploy=auto_deploy)
            if result:
                results.append(result)
        return results

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "scan_count": self._scan_count,
            "last_scan": self._last_scan,
            "pending_proposals": len(self._proposals),
            "ts": _ts(),
        }

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    def _detect_bottlenecks(self) -> list[dict[str, Any]]:
        """Identify agents / modules with poor economy metrics."""
        bottlenecks: list[dict[str, Any]] = []
        try:
            from core.economy_engine import get_economy_engine
            eco = get_economy_engine()
            bottom = eco.bottom_agents(limit=5)
            for a in bottom:
                total = a.get("tasks_completed", 0) + a.get("tasks_failed", 0)
                if total < _MIN_TASKS_BEFORE_SCAN:
                    continue
                if a.get("roi", 1.0) < 0.2:
                    bottlenecks.append({
                        "type": "low_roi_agent",
                        "agent": a["name"],
                        "roi": a["roi"],
                        "performance_score": a["performance_score"],
                        "recommendation": "Rewrite core logic to improve output value",
                    })
                elif a.get("avg_duration_ms", 0) > 5000:
                    bottlenecks.append({
                        "type": "slow_agent",
                        "agent": a["name"],
                        "avg_duration_ms": a["avg_duration_ms"],
                        "recommendation": "Optimise execution path or parallelise sub-tasks",
                    })
        except Exception:  # noqa: BLE001
            pass
        return bottlenecks

    def _get_competition_proposals(self) -> list[dict[str, Any]]:
        try:
            from core.agent_competition_engine import get_competition_engine
            return get_competition_engine().propose_rewrites(limit=3)
        except Exception:  # noqa: BLE001
            return []

    def _get_forge_suggestions(self) -> list[dict[str, Any]]:
        try:
            from core.forge_controller import get_forge_controller
            return get_forge_controller().roi_suggestions(limit=5)
        except Exception:  # noqa: BLE001
            return []

    def _get_economy_summary(self) -> dict[str, Any]:
        try:
            from core.economy_engine import get_economy_engine
            return get_economy_engine().system_summary()
        except Exception:  # noqa: BLE001
            return {}

    def _submit_suggestion(
        self,
        suggestion: dict[str, Any],
        *,
        auto_deploy: bool,
    ) -> dict[str, Any] | None:
        """Submit a single suggestion to ForgeController."""
        agent = suggestion.get("agent", "")
        if not agent or agent == "all":
            return None
        module = f"agents/{agent}.py"
        description = suggestion.get("reason", suggestion.get("description", "Optimizer proposal"))
        roi_analysis = suggestion.get("roi_analysis", {})
        roi_score = roi_analysis.get("roi_score", 0)

        # Only submit if ROI is worth it
        if roi_score < 0.5:
            return None

        try:
            from core.forge_controller import get_forge_controller
            # We only submit a description-level marker (no code rewrite from here)
            # A full code submission requires BuilderAgent or human input
            result = get_forge_controller().profit_impact_analysis(
                module=module,
                description=description,
                change_type="optimization",
            )
            self._proposals.append({
                "module": module,
                "description": description,
                "roi_analysis": result,
                "submitted_at": _ts(),
            })
            if len(self._proposals) > 200:
                self._proposals = self._proposals[-200:]
            return {"module": module, "roi_analysis": result, "ts": _ts()}
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            try:
                self.analyze()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Optimizer scan error (non-fatal): %s", exc)
            time.sleep(_SCAN_INTERVAL_S)


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: OptimizerAgent | None = None
_instance_lock = __import__("threading").Lock()


def get_optimizer_agent() -> OptimizerAgent:
    """Return the process-wide OptimizerAgent singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = OptimizerAgent()
    return _instance
