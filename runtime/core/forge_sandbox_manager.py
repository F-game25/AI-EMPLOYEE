"""Forge V5 quality gate mapper.

The actual sandbox and verification execution stays in the Node Forge runtime.
This module converts existing Forge verification/run payloads into the V5
quality gate shape.
"""
from __future__ import annotations

import time
import uuid
from typing import Any


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ForgeSandboxManager:
    DIMENSIONS = (
        "functional_correctness",
        "safety",
        "efficiency",
        "usability",
        "reliability",
        "integration_quality",
        "maintainability",
    )

    def run_validation(self, run_id: str, goal: dict[str, Any], dimensions: list[str] | None = None) -> dict[str, Any]:
        selected = dimensions or list(self.DIMENSIONS)
        return {
            "run_id": run_id,
            "goal_id": goal.get("goal_id"),
            "type": "existing_forge_verify",
            "available": False,
            "status": "unavailable",
            "dimensions": {
                key: {"status": "unavailable", "evidence": [], "reason": "Node Forge verify endpoint must execute this check"}
                for key in selected
            },
            "created_at": _now(),
        }

    def build_quality_gate(
        self,
        *,
        goal_id: str,
        run_result: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
        reasoning: dict[str, Any] | None = None,
        compute: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_result = run_result or {}
        verification = verification or {}
        test_results = verification.get("results") or verification.get("test_results") or run_result.get("test_results") or []
        all_passed = verification.get("all_passed")
        if all_passed is None and test_results:
            all_passed = all(bool(item.get("pass")) for item in test_results if isinstance(item, dict))

        functional = "passed" if all_passed else "failed" if all_passed is False else "skipped"
        integration = functional
        safety = "skipped"
        if run_result.get("blocked") or run_result.get("security_blocked"):
            safety = "failed"
        elif verification.get("security") or run_result.get("security"):
            safety = "passed"

        dimensions = {
            "functional_correctness": {"status": functional, "evidence": test_results, "source": "forge_verify"},
            "safety": {"status": safety, "evidence": verification.get("security") or [], "source": "doctor_or_policy"},
            "efficiency": {"status": "skipped", "evidence": [], "reason": "no efficiency check configured"},
            "usability": {"status": "skipped", "evidence": [], "reason": "not a UI-specific configured gate"},
            "reliability": {"status": "skipped", "evidence": [], "reason": "no reliability check configured"},
            "integration_quality": {"status": integration, "evidence": test_results, "source": "forge_verify"},
            "maintainability": {"status": "skipped", "evidence": [], "reason": "no maintainability check configured"},
        }
        return {
            "quality_gate_id": f"qg-{uuid.uuid4().hex[:12]}",
            "goal_id": goal_id,
            "run_id": run_result.get("run_id") or run_result.get("id"),
            "status": "passed" if functional == "passed" and safety != "failed" else "failed" if functional == "failed" or safety == "failed" else "partial",
            **dimensions,
            "summary": {key: value.get("status") for key, value in dimensions.items()},
            "model_used": (reasoning or {}).get("model_used"),
            "compute_backend": (compute or {}).get("backend"),
            "sandbox_used": "forge_verify",
            "created_at": _now(),
        }


def get_forge_sandbox_manager() -> ForgeSandboxManager:
    return ForgeSandboxManager()
