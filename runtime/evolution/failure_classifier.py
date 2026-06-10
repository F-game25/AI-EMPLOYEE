"""FailureClassifier — heuristic-first taxonomy classification of failed traces.

Fixed taxonomy. Heuristics inspect error phases/messages and trace shape; the LLM
path is optional and env-guarded (EVOLUTION_LLM_CLASSIFY). Offline only.
"""
from __future__ import annotations

import os
from typing import Any

TAXONOMY = (
    "missing_context", "bad_memory_retrieval", "wrong_model_route", "bad_tool_choice",
    "tool_argument_error", "planning_error", "reasoning_error", "execution_error",
    "code_error", "test_failure", "latency_failure", "hallucination",
    "unsafe_action_blocked", "user_preference_mismatch", "ambiguous_request",
    "external_dependency_failure",
)

_FIX_FOR = {
    "missing_context": "memory_update",
    "bad_memory_retrieval": "router_rule",
    "wrong_model_route": "model_route_patch",
    "bad_tool_choice": "router_rule",
    "tool_argument_error": "skill_patch",
    "planning_error": "prompt_patch",
    "reasoning_error": "prompt_patch",
    "execution_error": "skill_patch",
    "code_error": "code_patch",
    "test_failure": "code_patch",
    "latency_failure": "model_route_patch",
    "hallucination": "prompt_patch",
    "unsafe_action_blocked": "router_rule",
    "user_preference_mismatch": "memory_update",
    "ambiguous_request": "prompt_patch",
    "external_dependency_failure": "router_rule",
}

# Substring -> failure_type heuristics (checked in order).
_PHRASE_RULES: list[tuple[str, str]] = [
    ("unsafe", "unsafe_action_blocked"),
    ("blocked", "unsafe_action_blocked"),
    ("timeout", "latency_failure"),
    ("timed out", "latency_failure"),
    ("test", "test_failure"),
    ("assert", "test_failure"),
    ("traceback", "code_error"),
    ("syntaxerror", "code_error"),
    ("exception", "execution_error"),
    ("connection", "external_dependency_failure"),
    ("502", "external_dependency_failure"),
    ("503", "external_dependency_failure"),
    ("rate limit", "external_dependency_failure"),
    ("argument", "tool_argument_error"),
    ("invalid param", "tool_argument_error"),
    ("no such tool", "bad_tool_choice"),
    ("hallucin", "hallucination"),
    ("ambiguous", "ambiguous_request"),
    ("not found in context", "missing_context"),
]


class FailureClassifier:
    def __init__(self):
        self._llm = os.environ.get("EVOLUTION_LLM_CLASSIFY", "false").lower() == "true"

    def classify(self, trace: dict[str, Any]) -> dict[str, Any]:
        errors = trace.get("events_errors") or trace.get("errors") or []
        evidence: list[str] = []
        blob_parts = []
        for e in errors:
            msg = str(e.get("error", e)) if isinstance(e, dict) else str(e)
            blob_parts.append(msg)
            evidence.append(msg[:200])
        blob = " ".join(blob_parts).lower()

        ftype = "execution_error"  # safe default for a failure with no clear signal
        latency = float(trace.get("total_latency_ms") or 0.0)

        matched = False
        for needle, label in _PHRASE_RULES:
            if needle in blob:
                ftype = label
                matched = True
                break

        # latency-only failure (slow but no error text)
        if not matched and not errors and latency > 0:
            ftype = "latency_failure"

        # no models used but task needed one → routing miss
        if not matched and not (trace.get("models_used") or []) and trace.get("task_type") in ("code", "research"):
            ftype = "wrong_model_route"
            evidence.append("no model recorded for model-requiring task")

        root_cause = self._root_cause(ftype, trace)
        # learning value: failures with clear evidence + uncommon types teach more.
        lv = 0.5 + (0.2 if evidence else 0.0) + (0.2 if matched else 0.0)

        result = {
            "failure_type": ftype,
            "evidence": evidence[:6],
            "root_cause": root_cause,
            "recommended_fix_type": _FIX_FOR.get(ftype, "prompt_patch"),
            "learning_value_score": round(min(1.0, lv), 4),
        }
        if self._llm and not matched:
            result.update(self._llm_classify(trace, result))
        return result

    @staticmethod
    def _root_cause(ftype: str, trace: dict[str, Any]) -> str:
        goal = str(trace.get("user_goal", ""))[:120]
        return f"{ftype} while handling task_type={trace.get('task_type')} goal='{goal}'"

    def _llm_classify(self, trace: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
        try:
            from engine.api import generate
            resp = generate(
                prompt=(f"Failure evidence: {base['evidence']}\n"
                        f"Pick ONE failure_type from: {', '.join(TAXONOMY)}.\n"
                        "Reply with just the type."),
                system="You classify AI task failures. Reply with one taxonomy label.",
                timeout=30,
            )
            label = (resp or "").strip().split()[0].lower() if resp else ""
            if label in TAXONOMY:
                return {"failure_type": label,
                        "recommended_fix_type": _FIX_FOR.get(label, "prompt_patch")}
        except Exception:
            pass
        return {}


__all__ = ["FailureClassifier", "TAXONOMY"]
