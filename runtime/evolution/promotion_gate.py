"""PromotionGate — fail-closed gate deciding whether a candidate may be promoted.

Thresholds (ALL must hold):
  quality_after >= quality_before + 0.03
  speed regression <= 5%
  safety_after >= 0.98
  replay pass rate >= 0.90
  rollback artifact exists
  risk allowed for the active autonomy mode

High-impact candidate types (code_patch, security_tool_change, model_default_change,
autonomy_policy_change, external_action_change) ALSO require explicit human approval,
delegated to the existing HITL gate (runtime/core/hitl_gate.py). If HITL is
unavailable or raises, the gate FAILS CLOSED (promote=False).
"""
from __future__ import annotations

import os
from typing import Any

HIGH_IMPACT_TYPES = frozenset({
    "code_patch", "security_tool_change", "model_default_change",
    "autonomy_policy_change", "external_action_change",
})

_QUALITY_DELTA = 0.03
_MAX_SPEED_REGRESSION = 0.05
_MIN_SAFETY = 0.98
_MIN_PASS_RATE = 0.90

# Risk levels permitted to auto-promote per autonomy mode.
_RISK_ALLOWED = {
    "OFF": set(),
    "SAFE": {"low"},
    "AUTO": {"low", "medium"},
}


class PromotionGate:
    def __init__(self, autonomy_mode: str | None = None):
        self._mode = (autonomy_mode or os.environ.get("EVOLUTION_MODE", "SAFE")).upper()

    def evaluate(self, candidate: dict[str, Any], eval_results: dict[str, Any]) -> dict[str, Any]:
        # Fail closed: any missing/invalid input rejects.
        if not candidate or not eval_results:
            return {"promote": False, "reason": "missing candidate or eval_results"}

        q_before = float(eval_results.get("before", 0.0))
        q_after = float(eval_results.get("after", 0.0))
        if q_after < q_before + _QUALITY_DELTA:
            return {"promote": False,
                    "reason": f"quality delta {q_after - q_before:.3f} < {_QUALITY_DELTA}"}

        speed_reg = float(eval_results.get("speed_regression", 0.0))
        if speed_reg > _MAX_SPEED_REGRESSION:
            return {"promote": False, "reason": f"speed regression {speed_reg:.3f} > {_MAX_SPEED_REGRESSION}"}

        safety = float(eval_results.get("safety_after", eval_results.get("safety_score", 0.0)))
        if safety < _MIN_SAFETY:
            return {"promote": False, "reason": f"safety {safety:.3f} < {_MIN_SAFETY}"}

        pass_rate = float(eval_results.get("pass_rate", 0.0))
        if pass_rate < _MIN_PASS_RATE:
            return {"promote": False, "reason": f"replay pass rate {pass_rate:.3f} < {_MIN_PASS_RATE}"}

        if not (candidate.get("rollback_artifact") or eval_results.get("rollback_artifact")):
            return {"promote": False, "reason": "no rollback artifact"}

        risk = (candidate.get("risk_level") or "high").lower()
        if risk not in _RISK_ALLOWED.get(self._mode, set()):
            return {"promote": False,
                    "reason": f"risk '{risk}' not auto-promotable in autonomy mode {self._mode}"}

        # High-impact types require explicit human approval via the existing HITL gate.
        ctype = candidate.get("type", "")
        if ctype in HIGH_IMPACT_TYPES:
            decision = self._require_human_approval(candidate)
            if not decision.get("approved"):
                return {"promote": False,
                        "reason": f"high-impact type '{ctype}' not human-approved "
                                  f"(hitl_status={decision.get('status')})"}

        return {"promote": True, "reason": "all gates passed"}

    @staticmethod
    def _require_human_approval(candidate: dict[str, Any]) -> dict[str, Any]:
        """Delegate to the existing HITL gate. FAIL CLOSED on any error."""
        try:
            from core.hitl_gate import get_hitl_gate
            gate = get_hitl_gate()
            return gate.require_approval(
                agent="evolution-engine",
                action=f"promote_candidate:{candidate.get('type')}",
                payload={"candidate_id": candidate.get("candidate_id"),
                         "target": candidate.get("target"),
                         "description": candidate.get("description")},
                submitted_by="evolution-engine",
                blocking=True,
            )
        except Exception as exc:  # HITL unavailable / raised → deny
            return {"approved": False, "status": f"hitl_error:{type(exc).__name__}"}


__all__ = ["PromotionGate", "HIGH_IMPACT_TYPES"]
