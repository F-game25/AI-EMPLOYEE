"""Model decision audit — compliance traceability without storing prompt content."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ai_employee.model_decision_audit")

_STATE_DIR = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee")) / "state"


@dataclass
class ModelDecisionRecord:
    decision_id: str       # uuid4 hex
    tenant_id_hash: str    # HMAC-SHA256 truncated
    model: str             # e.g. "claude-sonnet-4-6"
    prompt_hash: str       # SHA-256 of prompt
    response_hash: str     # SHA-256 of response
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    decision_type: str     # "chat", "task", "research", "classification"
    confidence: float      # 0.0-1.0 or -1.0 if unavailable
    outcome: str           # "success", "error", "budget_exceeded", "safety_blocked"
    safety_flags: list     # e.g. ["prompt_injection_detected", "pii_redacted"]
    ts: str                # ISO8601 UTC


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


class ModelDecisionAudit:
    def __init__(self, state_dir: Path | None = None) -> None:
        self._dir = state_dir or _STATE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "model_decisions.jsonl"
        self._cache: deque[dict] = deque(maxlen=5000)
        self._lock = threading.Lock()
        self._load_recent()

    def _load_recent(self) -> None:
        """Seed in-memory cache from tail of existing file (up to 5000 records)."""
        if not self._path.exists():
            return
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            for line in lines[-5000:]:
                line = line.strip()
                if line:
                    self._cache.append(json.loads(line))
        except Exception as exc:
            logger.warning("model_decision_audit: could not load history: %s", exc)

    def record(
        self,
        tenant_id: str,
        model: str,
        prompt: str,
        response: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: float,
        decision_type: str = "chat",
        confidence: float = -1.0,
        outcome: str = "success",
        safety_flags: list | None = None,
    ) -> str:
        from core.telemetry import hash_tenant_id

        rec = ModelDecisionRecord(
            decision_id=uuid.uuid4().hex,
            tenant_id_hash=hash_tenant_id(tenant_id),
            model=model,
            prompt_hash=_sha256(prompt),
            response_hash=_sha256(response),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            decision_type=decision_type,
            confidence=confidence,
            outcome=outcome,
            safety_flags=safety_flags or [],
            ts=datetime.now(timezone.utc).isoformat(),
        )
        row = asdict(rec)
        with self._lock:
            self._cache.append(row)
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
            except Exception as exc:
                logger.warning("model_decision_audit: write failed: %s", exc)
        return rec.decision_id

    def get_recent(self, tenant_id_hash: str | None = None, limit: int = 100) -> list[dict]:
        with self._lock:
            records = list(self._cache)
        if tenant_id_hash:
            records = [r for r in records if r.get("tenant_id_hash") == tenant_id_hash]
        return records[-limit:]

    def get_stats(self, tenant_id_hash: str | None = None, window_hours: int = 24) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
        with self._lock:
            records = list(self._cache)
        if tenant_id_hash:
            records = [r for r in records if r.get("tenant_id_hash") == tenant_id_hash]
        records = [r for r in records if r.get("ts", "") >= cutoff]

        by_model: dict[str, int] = {}
        by_outcome: dict[str, int] = {}
        total_cost = 0.0
        total_tokens = 0
        flag_count = 0

        for r in records:
            by_model[r["model"]] = by_model.get(r["model"], 0) + 1
            by_outcome[r["outcome"]] = by_outcome.get(r["outcome"], 0) + 1
            total_cost += r.get("cost_usd", 0.0)
            total_tokens += r.get("input_tokens", 0) + r.get("output_tokens", 0)
            if r.get("safety_flags"):
                flag_count += 1

        n = len(records)
        return {
            "total_decisions": n,
            "by_model": by_model,
            "by_outcome": by_outcome,
            "avg_cost_usd": round(total_cost / n, 6) if n else 0.0,
            "total_tokens": total_tokens,
            "safety_flag_rate": round(flag_count / n, 4) if n else 0.0,
        }


_instance: ModelDecisionAudit | None = None
_instance_lock = threading.Lock()


def get_model_audit() -> ModelDecisionAudit:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ModelDecisionAudit()
    return _instance
