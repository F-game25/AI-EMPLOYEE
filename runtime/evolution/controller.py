"""EvolutionController — thin offline orchestrator for the evolution engine.

``on_task_finalized(trace)`` is the single entry point invoked AFTER a task has
already returned to the user. It is async/offline by contract — nothing here runs
on the live request path. Pipeline:

    score → (maybe) classify + reflect → (maybe) build distillation feed
          → register candidates

``handle_evolution_op`` is the convenience surface for the Node worker boundary
(status / traces / lessons / candidates / promote / rollback).
"""
from __future__ import annotations

from typing import Any

from evolution import EVOLUTION_ENABLED
from evolution.candidate_registry import get_candidate_registry
from evolution.distillation_adapter import DistillationAdapter
from evolution.failure_classifier import FailureClassifier
from evolution.outcome_scorer import OutcomeScorer
from evolution.promotion_gate import PromotionGate
from evolution.reflection_engine import ReflectionEngine
from evolution.replay_harness import ReplayHarness
from evolution.rollback_manager import RollbackManager


class EvolutionController:
    def __init__(self):
        self._scorer = OutcomeScorer()
        self._classifier = FailureClassifier()
        self._reflector = ReflectionEngine()
        self._adapter = DistillationAdapter()
        self._registry = get_candidate_registry()
        self._gate = PromotionGate()
        self._replay = ReplayHarness()
        self._rollback = RollbackManager()

    # ── offline entry point (post-response) ──────────────────────────────────
    def on_task_finalized(self, trace: dict[str, Any]) -> dict[str, Any]:
        if not EVOLUTION_ENABLED or not trace:
            return {"skipped": True}
        out: dict[str, Any] = {"trace_id": trace.get("trace_id")}
        try:
            scores = self._scorer.score(trace)
            out["scores"] = scores

            failure = None
            if not trace.get("success", True):
                failure = self._classifier.classify(trace)
                out["failure"] = failure

            lesson = self._reflector.reflect(trace, scores, failure)
            if lesson:
                out["lesson_id"] = lesson["lesson_id"]

            # High-learning-value traces feed distillation (gated downstream).
            if scores.get("learning_value_score", 0.0) >= 0.5 or failure:
                feed = self._adapter.build_feed([trace], [scores])
                out["distillation"] = self._adapter.write_feed(feed)
        except Exception as exc:  # offline path must never surface to caller
            out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    # ── Node-worker convenience surface ──────────────────────────────────────
    def handle_evolution_op(self, op: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        try:
            if op == "status":
                return {"ok": True, "enabled": EVOLUTION_ENABLED,
                        "candidates": len(self._registry.list())}
            if op == "lessons":
                return {"ok": True, "lessons": self._reflector.list_lessons(args.get("limit", 100))}
            if op == "candidates":
                return {"ok": True, "candidates": self._registry.list(args.get("status"), args.get("limit", 100))}
            if op == "traces":
                # traces live as JSONL; surface count of registered candidates' sources
                return {"ok": True, "note": "traces persisted under ~/.ai-employee/evolution/traces/"}
            if op == "promote":
                cand = self._registry.get(args.get("candidate_id", ""))
                if not cand:
                    return {"ok": False, "error": "candidate not found"}
                evals = cand.get("eval_results") or self._replay.replay(cand)
                evals.setdefault("rollback_artifact",
                                 self._rollback.has_rollback_artifact(cand.get("target", "")))
                decision = self._gate.evaluate(cand, evals)
                if decision["promote"]:
                    self._registry.update(cand["candidate_id"], promotion_status="promoted",
                                          eval_results=evals)
                    self._rollback.promote(cand.get("target", ""), cand.get("after_version", ""))
                return {"ok": True, "decision": decision}
            if op == "rollback":
                ok = self._rollback.rollback(args.get("target", ""), args.get("trigger", "manual"))
                return {"ok": ok}
            return {"ok": False, "error": f"unknown op: {op}"}
        except Exception as exc:  # fail closed, never raise to the worker
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


_singleton: EvolutionController | None = None


def get_evolution_controller() -> EvolutionController:
    global _singleton
    if _singleton is None:
        _singleton = EvolutionController()
    return _singleton


__all__ = ["EvolutionController", "get_evolution_controller"]
