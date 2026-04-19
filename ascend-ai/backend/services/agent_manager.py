"""
ASCEND AI — Agent Manager
Orchestrates agent lifecycle and status queries.
Falls back to mock data when ~/.ai-employee/ is unavailable.
"""

import asyncio
import os
import time

from services.mock_layer import MOCK_AGENTS, get_mock_agents
from services.process_wrapper import get_pid, start_bot, stop_bot

AI_EMPLOYEE_DIR = os.path.expanduser("~/.ai-employee")

_start_times: dict[str, float] = {}


def _ai_employee_available() -> bool:
    return os.path.isdir(os.path.join(AI_EMPLOYEE_DIR, "bots"))


def list_agents() -> list[dict]:
    """Return status for every known agent."""
    if not _ai_employee_available():
        return get_mock_agents()

    agents = []
    for name in MOCK_AGENTS:
        pid = get_pid(name)
        uptime = None
        if pid and name in _start_times:
            uptime = round(time.time() - _start_times[name])
        agents.append(
            {
                "name": name,
                "status": "running" if pid else "offline",
                "pid": pid,
                "uptime": uptime,
                "mock": False,
            }
        )
    return agents


def launch_agent(name: str) -> dict:
    """Start a single agent."""
    result = start_bot(name)
    if result.get("success"):
        _start_times[name] = time.time()
    return result


def kill_agent(name: str) -> dict:
    """Stop a single agent."""
    result = stop_bot(name)
    if result.get("success"):
        _start_times.pop(name, None)
    return result


async def startup():
    """Called on FastAPI startup — no auto-launch, just verify availability."""
    if _ai_employee_available():
        print("[ASCEND] ~/.ai-employee/bots/ detected — agents ready to launch.")
    else:
        print("[ASCEND] ~/.ai-employee/ not found — running in mock mode.")
