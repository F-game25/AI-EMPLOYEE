import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_TENANT = 50
_MAX_AGENT  = 10
_spawns: dict[str, int] = {}
_agent_spawns: dict[str, int] = {}
_lock = asyncio.Lock()


async def acquire(tenant_id: str, agent_id: str) -> dict:
    async with _lock:
        tenant_count = _spawns.get(tenant_id, 0)
        agent_key = f"{tenant_id}:{agent_id}"
        agent_count = _agent_spawns.get(agent_key, 0)
        if tenant_count >= _MAX_TENANT:
            return {"blocked": True, "reason": "tenant_spawn_limit", "current": tenant_count, "max": _MAX_TENANT}
        if agent_count >= _MAX_AGENT:
            return {"blocked": True, "reason": "agent_spawn_limit", "current": agent_count, "max": _MAX_AGENT}
        _spawns[tenant_id] = tenant_count + 1
        _agent_spawns[agent_key] = agent_count + 1
        return {"blocked": False}


async def release(tenant_id: str, agent_id: str) -> None:
    async with _lock:
        if _spawns.get(tenant_id, 0) > 0:
            _spawns[tenant_id] -= 1
        agent_key = f"{tenant_id}:{agent_id}"
        if _agent_spawns.get(agent_key, 0) > 0:
            _agent_spawns[agent_key] -= 1


async def reset_agent(tenant_id: str, agent_id: str) -> None:
    async with _lock:
        agent_key = f"{tenant_id}:{agent_id}"
        _agent_spawns.pop(agent_key, None)


def get_state() -> dict:
    return {"tenant_counts": dict(_spawns), "agent_counts": dict(_agent_spawns)}


_instance = None


def get_spawn_limiter():
    global _instance
    if _instance is None:
        _instance = type("SpawnLimiter", (), {
            "acquire": staticmethod(acquire),
            "release": staticmethod(release),
            "reset_agent": staticmethod(reset_agent),
            "get_state": staticmethod(get_state),
        })()
    return _instance
