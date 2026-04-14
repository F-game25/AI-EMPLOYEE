"""Multi-layer reinforcement model for agent selection."""
from __future__ import annotations

import copy
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_DEFAULT_AGENT_MODEL: dict[str, dict[str, float]] = {
    "lead_hunter": {
        "task_match": 0.6,
        "success_history": 0.5,
        "speed": 0.4,
        "complexity_fit": 0.5,
    },
    "email_ninja": {
        "task_match": 0.55,
        "success_history": 0.5,
        "speed": 0.5,
        "complexity_fit": 0.45,
    },
    "intel_agent": {
        "task_match": 0.5,
        "success_history": 0.55,
        "speed": 0.35,
        "complexity_fit": 0.7,
    },
    "social_guru": {
        "task_match": 0.55,
        "success_history": 0.5,
        "speed": 0.55,
        "complexity_fit": 0.45,
    },
    "data_analyst": {
        "task_match": 0.5,
        "success_history": 0.55,
        "speed": 0.35,
        "complexity_fit": 0.65,
    },
    "task_orchestrator": {
        "task_match": 0.45,
        "success_history": 0.5,
        "speed": 0.45,
        "complexity_fit": 0.55,
    },
}

feature_impact: dict[str, float] = {
    "task_match": 1.0,
    "success_history": 0.8,
    "speed": 0.3,
    "complexity_fit": 0.6,
}

learning_rate = 0.05
_CONFIDENCE_FALLBACK = 0.4
_MODEL_VERSION = 2
_lock = threading.RLock()
_last_learning_update: str | None = None


def _state_path() -> Path:
    home = os.getenv("AI_HOME")
    base = Path(home) if home else Path(__file__).resolve().parents[2]
    path = base / "state" / "brain_weights.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


agent_model: dict[str, dict[str, float]] = copy.deepcopy(_DEFAULT_AGENT_MODEL)


def _normalize_payload(payload: Any) -> dict[str, dict[str, float]]:
    if not isinstance(payload, dict):
        return copy.deepcopy(_DEFAULT_AGENT_MODEL)
    candidate = payload.get("agent_model", payload)
    if not isinstance(candidate, dict):
        return copy.deepcopy(_DEFAULT_AGENT_MODEL)

    normalized = copy.deepcopy(_DEFAULT_AGENT_MODEL)
    for agent, base in normalized.items():
        row = candidate.get(agent)
        if not isinstance(row, dict):
            continue
        base["task_match"] = clamp(row.get("task_match", base["task_match"]))
        base["success_history"] = clamp(row.get("success_history", base["success_history"]))
        base["speed"] = clamp(row.get("speed", base["speed"]))
        base["complexity_fit"] = clamp(row.get("complexity_fit", base["complexity_fit"]))
    return normalized


def _write_payload() -> None:
    payload = {
        "version": _MODEL_VERSION,
        "updated_at": _ts(),
        "agent_model": agent_model,
        "feature_impact": feature_impact,
    }
    _state_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_agent_model() -> dict[str, dict[str, float]]:
    global agent_model
    path = _state_path()
    with _lock:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            agent_model = _normalize_payload(payload)
        except Exception:
            agent_model = copy.deepcopy(_DEFAULT_AGENT_MODEL)
            _write_payload()
        return copy.deepcopy(agent_model)


def save_agent_model() -> dict[str, dict[str, float]]:
    with _lock:
        _write_payload()
        return copy.deepcopy(agent_model)


def get_agent_model() -> dict[str, dict[str, float]]:
    with _lock:
        return copy.deepcopy(agent_model)


def score_agent(agent: str, features: dict[str, float]) -> float:
    model = get_agent_model().get(agent)
    if model is None:
        return 0.0
    return (
        float(features.get("task_match", 0.0)) * model["task_match"]
        + float(features.get("success_rate", 0.0)) * model["success_history"]
        + float(features.get("speed", 0.0)) * model["speed"]
        + float(features.get("complexity", 0.0)) * model["complexity_fit"]
    )


def select_agent(
    task_features: dict[str, dict[str, float]] | dict[str, float],
    *,
    score_boosts: dict[str, float] | None = None,
) -> tuple[str, float, dict[str, float]]:
    scores: dict[str, float] = {}
    model = get_agent_model()
    boosts = score_boosts or {}

    for agent in model:
        if isinstance(task_features.get(agent), dict):  # type: ignore[arg-type]
            features = task_features.get(agent, {})  # type: ignore[assignment]
        else:
            features = task_features  # type: ignore[assignment]
        scores[agent] = score_agent(agent, features) + float(boosts.get(agent, 0.0))

    best = max(scores, key=scores.get) if scores else "task_orchestrator"
    confidence = scores.get(best, 0.0) / (sum(scores.values()) + 1e-6)
    if confidence < _CONFIDENCE_FALLBACK:
        return "task_orchestrator", float(confidence), scores
    return best, float(confidence), scores


def update_agent_model(agent: str, reward: float) -> tuple[float, float]:
    global _last_learning_update
    with _lock:
        if agent not in agent_model:
            raise ValueError(f"Unknown brain model agent: {agent}")
        row = agent_model[agent]
        before = sum(row.values()) / max(len(row), 1)
        for feature in row:
            impact = feature_impact.get(feature, 0.5)
            row[feature] = clamp(row[feature] + (learning_rate * float(reward) * impact))
        after = sum(row.values()) / max(len(row), 1)
        _last_learning_update = _ts()
        _write_payload()
        return before, after


def get_last_learning_update() -> str | None:
    with _lock:
        return _last_learning_update


load_agent_model()
