"""DistillationAdapter — THE handoff to the existing distillation pipeline.

╔══════════════════════════════════════════════════════════════════════════════╗
║  DISTILLATION EXECUTION IS OWNED BY:                                          ║
║    backend/services/forge_learning.js   (scoreTrajectory, extractLessons,     ║
║      createPreferencePairs, createSkillUpdateProposals,                       ║
║      createEvaluationCases, buildDistillationRecord, scrubSecrets...)         ║
║    backend/services/forge_training.js + backend/forge_train.py               ║
║                                                                              ║
║  THIS MODULE DOES NOT re-implement any of that. It only:                      ║
║    1. Produces CLEAN, secret-scrubbed, labeled feed rows from evolution       ║
║       traces+scores (each row carries source_trace_id + scores).             ║
║    2. Writes them to ~/.ai-employee/evolution/distillation_feeds/*.jsonl —    ║
║       the JSONL feed files the existing pipeline consumes.                    ║
║    3. Registers the produced dataset as a candidate so it passes through      ║
║       promotion_gate before any training is acted on.                         ║
║                                                                              ║
║  HANDOFF BOUNDARY (where the Node side picks this up):                        ║
║    Node worker calls forge_learning.buildDistillationRecord(run, project)     ║
║    / exportLearningDataset(...) on the feed files written here. The Python    ║
║    side stops at "feed written + candidate registered". It NEVER scores a     ║
║    full trajectory or builds a distillation record itself — those belong to   ║
║    forge_learning.js. Each feed row sets handoff="forge_learning.js".         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from evolution import DISTILL_FEED_DIR, ensure_dirs
from evolution.candidate_registry import get_candidate_registry
from evolution.scrub import scrub

# Marker stamped on every feed row: distillation execution belongs to forge_learning.js.
_HANDOFF = "forge_learning.js"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DistillationAdapter:
    def __init__(self):
        self._lock = threading.Lock()

    def build_feed(self, traces: list[dict[str, Any]],
                   scores: list[dict[str, float]] | None = None) -> dict[str, list[dict]]:
        """Produce labeled, scrubbed feed rows grouped by example kind.

        NOTE: ``scores`` are the OutcomeScorer's per-axis scores — they are passed
        through as labels only. This adapter does NOT compute a trajectory score;
        that is forge_learning.js::scoreTrajectory's job on the Node side.
        """
        scores = scores or [{} for _ in traces]
        feed: dict[str, list[dict]] = {
            "reasoning_examples": [],
            "tool_use_examples": [],
            "router_examples": [],
        }
        for trace, sc in zip(traces, scores):
            tid = trace.get("trace_id")
            row_base = {
                "source_trace_id": tid,           # handoff label
                "scores": sc,                     # handoff label (NOT recomputed here)
                "handoff": _HANDOFF,              # marks: distillation owned by forge_learning.js
                "task_type": trace.get("task_type"),
                "approved_for_training": False,   # mirror forge_learning.js default
            }
            # reasoning example — goal → produced output
            feed["reasoning_examples"].append(scrub({
                **row_base,
                "input": {"goal": trace.get("user_goal")},
                "output": (trace.get("outputs") or [None])[0],
            }))
            # tool-use examples — one per recorded tool
            for tool in (trace.get("tools_used") or []):
                feed["tool_use_examples"].append(scrub({
                    **row_base, "tool": tool, "goal": trace.get("user_goal"),
                }))
            # router example — which model(s) handled this task_type
            if trace.get("models_used"):
                feed["router_examples"].append(scrub({
                    **row_base, "models": trace.get("models_used"),
                }))
        return feed

    def write_feed(self, feed: dict[str, list[dict]]) -> dict[str, Any]:
        """Write feed rows to the JSONL files the existing pipeline consumes,
        then register the dataset as a candidate (so promotion_gate governs it)."""
        ensure_dirs()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        written: dict[str, str] = {}
        total = 0
        with self._lock:
            for kind, rows in feed.items():
                if not rows:
                    continue
                path = DISTILL_FEED_DIR / f"{kind}-{stamp}.jsonl"
                with open(path, "a", encoding="utf-8") as fh:
                    for r in rows:
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                        total += 1
                written[kind] = str(path)

        trace_ids = sorted({r.get("source_trace_id")
                            for rows in feed.values() for r in rows if r.get("source_trace_id")})
        # Register as a candidate — distillation training is gated, never auto-run.
        cand = get_candidate_registry().register(
            type="distillation_dataset",
            target="distillation",
            description=f"Evolution distillation feed ({total} rows) -> {_HANDOFF}",
            created_from_trace_ids=trace_ids,
            risk_level="low",
            payload={"feed_files": written, "row_count": total, "handoff": _HANDOFF,
                     "consumed_by": "backend/services/forge_learning.js"},
        )
        return {"feed_files": written, "row_count": total,
                "candidate_id": cand["candidate_id"], "handoff": _HANDOFF}


__all__ = ["DistillationAdapter"]
