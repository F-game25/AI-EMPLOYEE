import asyncio
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DECISIONS_PER_MIN = 60
_buckets: dict[str, dict] = {}


def _get_bucket(agent_id: str) -> dict:
    if agent_id not in _buckets:
        _buckets[agent_id] = {
            "tokens": float(_DECISIONS_PER_MIN),
            "max": float(_DECISIONS_PER_MIN),
            "refill": _DECISIONS_PER_MIN / 60.0,
            "last": time.time(),
        }
    return _buckets[agent_id]


def _refill(b: dict) -> None:
    now = time.time()
    elapsed = now - b["last"]
    b["tokens"] = min(b["max"], b["tokens"] + elapsed * b["refill"])
    b["last"] = now


async def acquire_decision(agent_id: str) -> None:
    b = _get_bucket(agent_id)
    while True:
        _refill(b)
        if b["tokens"] >= 1.0:
            b["tokens"] -= 1.0
            return
        wait = (1.0 - b["tokens"]) / b["refill"]
        await asyncio.sleep(min(wait, 1.0))


def get_state() -> dict:
    return {aid: {"tokens": round(b["tokens"], 2), "max": b["max"]} for aid, b in _buckets.items()}


_instance = None


def get_rate_governor():
    global _instance
    if _instance is None:
        _instance = type("RateGovernor", (), {
            "acquire": staticmethod(acquire_decision),
            "get_state": staticmethod(get_state),
        })()
    return _instance
