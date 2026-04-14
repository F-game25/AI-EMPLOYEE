"""Persistent reinforcement-style agent weights for brain routing."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path


weights: dict[str, float] = {
    "lead_hunter": 0.5,
    "email_ninja": 0.5,
    "intel_agent": 0.5,
    "social_guru": 0.5,
    "data_analyst": 0.5,
    "task_orchestrator": 0.5,
}

learning_rate = 0.05

_lock = threading.RLock()


def _state_path() -> Path:
    home = os.getenv("AI_HOME")
    if home:
        base = Path(home)
    else:
        base = Path(__file__).resolve().parents[2]
    path = base / "state" / "brain_weights.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def load_weights() -> dict[str, float]:
    path = _state_path()
    with _lock:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return dict(weights)
            for key, default in list(weights.items()):
                weights[key] = clamp(payload.get(key, default))
        except Exception:
            save_weights()
        return dict(weights)


def save_weights() -> dict[str, float]:
    path = _state_path()
    with _lock:
        path.write_text(json.dumps(weights, indent=2), encoding="utf-8")
        return dict(weights)


def get_weights() -> dict[str, float]:
    with _lock:
        return dict(weights)


def update_weight(agent: str, reward: float) -> tuple[float, float]:
    with _lock:
        if agent not in weights:
            return (0.0, 0.0)
        before = weights[agent]
        weights[agent] = clamp(before + (learning_rate * float(reward)))
        save_weights()
        return before, weights[agent]


load_weights()
