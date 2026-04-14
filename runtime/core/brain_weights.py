"""Compatibility wrapper around the multi-layer brain model."""
from __future__ import annotations

import threading

from core.brain_model import (
    get_agent_model,
    load_agent_model,
    save_agent_model,
    update_agent_model,
)

_lock = threading.RLock()


def load_weights() -> dict[str, dict[str, float]]:
    with _lock:
        return load_agent_model()


def save_weights() -> dict[str, dict[str, float]]:
    with _lock:
        return save_agent_model()


def get_weights() -> dict[str, dict[str, float]]:
    with _lock:
        return get_agent_model()


def update_weight(agent: str, reward: float) -> tuple[float, float]:
    with _lock:
        return update_agent_model(agent, reward)


load_weights()
