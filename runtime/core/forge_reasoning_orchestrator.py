"""Forge V5 reasoning adapter around the Quantum Cognitive Engine."""
from __future__ import annotations

import dataclasses
from typing import Any


def _strategy_to_dict(strategy: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(strategy):
        return dataclasses.asdict(strategy)
    if isinstance(strategy, dict):
        return dict(strategy)
    return {
        "name": getattr(strategy, "name", "unknown"),
        "steps": list(getattr(strategy, "steps", []) or []),
        "confidence": float(getattr(strategy, "confidence", 0.0) or 0.0),
        "estimated_cost": float(getattr(strategy, "estimated_cost", 0.0) or 0.0),
        "risk_level": float(getattr(strategy, "risk_level", 0.0) or 0.0),
        "rationale": getattr(strategy, "rationale", ""),
    }


class ForgeReasoningOrchestrator:
    async def reason(
        self,
        *,
        phase: str,
        goal: str,
        context: dict[str, Any] | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        selected_mode = mode or self._select_mode(goal, context)
        try:
            from core.quantum.engine import get_qce

            qce = get_qce()
            pack = await qce.process(goal=goal, task_type=phase or "planning")
            strategies = await qce.plan(goal, pack, getattr(pack, "complexity", "medium"))
            paths = [_strategy_to_dict(item) for item in strategies]
            chosen = paths[0] if paths else None
            return {
                "ok": True,
                "phase": phase,
                "selected_mode": selected_mode,
                "goal": goal,
                "confidence": float(getattr(pack, "confidence", 0.0) or 0.0),
                "complexity": getattr(pack, "complexity", "medium"),
                "model_used": getattr(pack, "suggested_model", None),
                "agents": list(getattr(pack, "top_agents", []) or []),
                "tools": list(getattr(pack, "top_tools", []) or []),
                "paths_considered": paths,
                "chosen_path": chosen,
                "rejected_paths": paths[1:],
                "search_id": getattr(pack, "search_id", None),
            }
        except Exception as exc:
            return {
                "ok": False,
                "phase": phase,
                "selected_mode": selected_mode,
                "goal": goal,
                "confidence": 0.0,
                "complexity": "unknown",
                "model_used": None,
                "agents": [],
                "tools": [],
                "paths_considered": [],
                "chosen_path": None,
                "rejected_paths": [],
                "error": str(exc),
                "fallback": True,
            }

    async def explore_paths(self, goal: str, context: dict[str, Any] | None = None, n: int = 3) -> list[dict[str, Any]]:
        result = await self.reason(phase="planning", goal=goal, context=context or {}, mode="quantum_exploration")
        return list(result.get("paths_considered") or [])[:n]

    def select_model(self, task_type: str, quality: str = "balanced", privacy: str = "local_ok") -> dict[str, Any]:
        complexity = "critical" if quality == "high" else "medium"
        try:
            from core.quantum.router import AmplitudeRouter

            return {
                "model": AmplitudeRouter().route_model(complexity),
                "task_type": task_type,
                "quality": quality,
                "privacy": privacy,
                "source": "qce_amplitude_router",
            }
        except Exception as exc:
            return {
                "model": None,
                "task_type": task_type,
                "quality": quality,
                "privacy": privacy,
                "source": "unavailable",
                "error": str(exc),
            }

    def _select_mode(self, goal: str, context: dict[str, Any]) -> str:
        text = f"{goal} {context}".lower()
        if any(word in text for word in ("research", "unknown", "investigate", "audit")):
            return "research_first"
        if any(word in text for word in ("security", "payment", "wallet", "deploy", "delete")):
            return "high_quality"
        if len(goal or "") > 300:
            return "quantum_exploration"
        return "stepwise"


def get_forge_reasoning_orchestrator() -> ForgeReasoningOrchestrator:
    return ForgeReasoningOrchestrator()
