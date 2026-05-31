"""Reasoning trace recording and persistence."""
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any


@dataclass
class ReasoningTrace:
    """Single step in a reasoning chain."""
    node: str  # e.g., "classify", "retrieve", "plan", "reason", "act", "verify", "synthesize"
    input: dict[str, Any]
    output: dict[str, Any]
    latency_ms: float
    status: str  # "success", "error", "partial"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReasoningSession:
    """Complete reasoning session with all traces."""
    thread_id: str
    user_id: str
    input: str
    intent: str
    traces: list[ReasoningTrace] = field(default_factory=list)
    output: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_latency_ms(self) -> float:
        return sum(t.latency_ms for t in self.traces)

    def save_jsonl(self, base_dir: str | Path = "state/neural_brain/traces") -> Path:
        """Persist as JSONL."""
        Path(base_dir).mkdir(parents=True, exist_ok=True)
        path = Path(base_dir) / f"{self.thread_id}.jsonl"
        with open(path, "a") as f:
            for trace in self.traces:
                f.write(json.dumps({
                    "timestamp": datetime.utcnow().isoformat(),
                    **trace.as_dict
                }) + "\n")
        return path

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "input": self.input,
            "intent": self.intent,
            "output": self.output,
            "traces": [t.as_dict for t in self.traces],
            "total_latency_ms": self.total_latency_ms,
            "created_at": self.created_at.isoformat(),
        }
