from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Any, Literal

from core.self_evolution.code_analyzer import CodeAnalyzer
from core.self_evolution.evolution_memory import EvolutionMemory, get_evolution_memory
from core.self_evolution.patch_generator import PatchGenerator
from core.self_evolution.patch_validator import PatchValidator
from core.self_evolution.safe_deployer import SafeDeployer

EvolutionMode = Literal["OFF", "SAFE", "AUTO"]


class EvolutionController:
    """Continuous self-evolution loop with validation and safe deploy."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or self._detect_repo_root()
        self._analyzer = CodeAnalyzer(self._repo_root)
        self._generator = PatchGenerator(self._repo_root)
        self._validator = PatchValidator(self._repo_root)
        self._deployer = SafeDeployer(self._repo_root)
        self._memory: EvolutionMemory = get_evolution_memory()
        self._mode: EvolutionMode = "OFF"
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._cycle_interval_s = 10.0
        self._last_cycle_at: str | None = None
        self._last_result: dict[str, Any] | None = None

    @staticmethod
    def _detect_repo_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "package.json").exists():
                return parent
        return current.parents[3]

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def set_mode(self, mode: str) -> str:
        normalized = (mode or "").upper().strip()
        if normalized not in {"OFF", "SAFE", "AUTO"}:
            raise ValueError("Unknown evolution mode. Use OFF, SAFE, or AUTO.")
        with self._lock:
            self._mode = normalized  # type: ignore[assignment]
        return self._mode

    def get_mode(self) -> str:
        with self._lock:
            return self._mode

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._loop, name="evolution-controller", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def run_once(self, *, manual_approved: bool = False) -> dict[str, Any]:
        mode = self.get_mode()
        self._last_cycle_at = self._ts()
        if mode == "OFF":
            result = {"status": "skipped", "reason": "mode_off"}
            self._last_result = result
            return result

        issues = self._analyzer.scan_full_repo()
        if not issues:
            result = {"status": "ok", "reason": "no_issues_detected"}
            self._last_result = result
            return result

        issue = self._pick_issue(issues)
        generated = self._generator.generate(issue)
        self._memory.record_patch(issue=issue, patch_meta=generated.to_dict())

        if not generated.diff:
            result = {
                "status": "rejected",
                "reason": "no_valid_diff",
                "issue": issue,
                "generator": generated.to_dict(),
            }
            self._memory.record_outcome(issue=issue, status="rejected", reward=0, detail=result)
            self._last_result = result
            return result

        validation = self._validator.validate(generated.diff)
        if not validation.get("passed"):
            result = {
                "status": "rejected",
                "reason": "validation_failed",
                "issue": issue,
                "validation": validation,
            }
            self._memory.record_outcome(issue=issue, status="validation_failed", reward=-1, detail=result)
            self._last_result = result
            return result

        deploy = self._deployer.deploy(
            diff_text=generated.diff,
            risk_level=generated.risk_level,
            evolution_mode=mode,
            tester_gate_passed=True,
            manual_approved=manual_approved,
        )
        if deploy.get("deployed"):
            result = {
                "status": "deployed",
                "issue": issue,
                "deploy": deploy,
                "validation": validation,
                "generator": generated.to_dict(),
            }
            self._memory.record_outcome(issue=issue, status="deployed", reward=1, detail=result)
            self._last_result = result
            return result

        reward = -1 if deploy.get("reason") not in {"manual_approval_required", "evolution_mode_off"} else 0
        result = {
            "status": "rejected",
            "issue": issue,
            "deploy": deploy,
            "validation": validation,
            "generator": generated.to_dict(),
        }
        self._memory.record_outcome(issue=issue, status="deploy_rejected", reward=reward, detail=result)
        self._last_result = result
        return result

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "mode": self.get_mode(),
            "last_cycle_at": self._last_cycle_at,
            "last_result": self._last_result,
            "memory": self._memory.summary(),
        }

    def rollback(self, backup_id: str) -> dict[str, Any]:
        return self._deployer.rollback(backup_id)

    def _loop(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    return
            try:
                self.run_once(manual_approved=False)
            except Exception as exc:
                self._last_result = {
                    "status": "error",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "at": self._ts(),
                }
            time.sleep(self._cycle_interval_s)

    @staticmethod
    def _pick_issue(issues: list[dict[str, str]]) -> dict[str, str]:
        rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(issues, key=lambda item: rank.get((item.get("severity") or "medium").lower(), 4))[0]


_instance: EvolutionController | None = None
_instance_lock = threading.Lock()


def get_evolution_controller() -> EvolutionController:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = EvolutionController()
    return _instance
