"""CandidateRegistry — persistent registry of improvement candidates.

Every proposed change (memory update, prompt patch, router rule, model-route patch,
skill patch, distillation dataset, ...) is registered here so it must pass through
the promotion gate before anything is applied. JSONL-backed, scrubbed on write.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from evolution import CANDIDATES_DIR, ensure_dirs
from evolution.scrub import scrub

CANDIDATE_TYPES = (
    "memory_update", "prompt_patch", "router_rule", "model_route_patch",
    "skill_patch", "code_patch", "distillation_dataset", "autonomy_policy_change",
    "security_tool_change", "model_default_change", "external_action_change",
)

PROMOTION_STATUSES = ("registered", "evaluating", "approved", "promoted", "rejected", "rolled_back")


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CandidateRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._store = CANDIDATES_DIR / "candidates.jsonl"

    def register(self, *, type: str, target: str, description: str,
                 created_from_trace_ids: list[str] | None = None,
                 before_version: str = "", after_version: str = "",
                 expected_gain: dict[str, Any] | None = None,
                 risk_level: str = "medium",
                 payload: dict[str, Any] | None = None) -> dict[str, Any]:
        cand = {
            "candidate_id": f"cand-{uuid.uuid4().hex[:12]}",
            "type": type if type in CANDIDATE_TYPES else "prompt_patch",
            "target": target,
            "description": description[:400],
            "created_from_trace_ids": created_from_trace_ids or [],
            "before_version": before_version,
            "after_version": after_version,
            "expected_gain": expected_gain or {},
            "risk_level": risk_level,
            "eval_results": {},
            "promotion_status": "registered",
            "payload": payload or {},
            "created_at": _iso(),
            "updated_at": _iso(),
        }
        cand = scrub(cand)
        with self._lock:
            ensure_dirs()
            with open(self._store, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(cand, ensure_ascii=False) + "\n")
        return cand

    def _read_all(self) -> list[dict[str, Any]]:
        if not self._store.exists():
            return []
        out = []
        with open(self._store, encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
        return out

    def get(self, candidate_id: str) -> Optional[dict[str, Any]]:
        # last write wins (registry is append-only with updates appended)
        found = None
        for c in self._read_all():
            if c.get("candidate_id") == candidate_id:
                found = c
        return found

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        # collapse to latest version per id
        latest: dict[str, dict[str, Any]] = {}
        for c in self._read_all():
            latest[c.get("candidate_id")] = c
        rows = list(latest.values())
        if status:
            rows = [c for c in rows if c.get("promotion_status") == status]
        return rows[-limit:]

    def update(self, candidate_id: str, **fields) -> Optional[dict[str, Any]]:
        cur = self.get(candidate_id)
        if cur is None:
            return None
        cur = {**cur, **scrub(fields), "updated_at": _iso()}
        with self._lock:
            ensure_dirs()
            with open(self._store, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(cur, ensure_ascii=False) + "\n")
        return cur


_singleton: Optional[CandidateRegistry] = None
_lock = threading.Lock()


def get_candidate_registry() -> CandidateRegistry:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = CandidateRegistry()
    return _singleton


__all__ = ["CandidateRegistry", "get_candidate_registry", "CANDIDATE_TYPES"]
