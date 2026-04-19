"""
ASCEND AI — Agent Manager
Orchestrates agent lifecycle and status queries.
Falls back to mock data when ~/.ai-employee/ is unavailable.
"""

import asyncio
import os

from services.mock_layer import get_mock_agents
from services.process_wrapper import get_pid, start_bot, stop_bot

AI_EMPLOYEE_DIR = os.path.expanduser("~/.ai-employee")

_agent_statuses: dict[str, dict] = {}

ALL_BOTS = [
    "task-orchestrator", "company-builder", "hr-manager", "finance-wizard",
    "brand-strategist", "growth-hacker", "project-manager", "lead-hunter",
    "content-master", "social-guru", "intel-agent", "email-ninja",
    "support-bot", "data-analyst", "creative-studio", "web-sales",
    "skills-manager", "polymarket-trader", "mirofish-researcher", "discovery",
    "problem-solver", "problem-solver-ui",
]


async def startup():
    """Called on FastAPI startup — initialises agent statuses."""
    if not os.path.exists(AI_EMPLOYEE_DIR):
        # No ~/.ai-employee — full mock mode
        for name in ALL_BOTS:
            _agent_statuses[name] = {
                "name": name, "status": "offline", "pid": None, "mock": True,
            }
        return

    # Try starting watchdog first
    try:
        result = start_bot("problem-solver")
        _agent_statuses["problem-solver"] = {
            "name": "problem-solver",
            "status": "starting" if result["success"] else "error",
            "pid": result.get("pid"),
        }
    except Exception:
        pass

    # Start remaining bots
    for name in ALL_BOTS:
        if name == "problem-solver":
            continue
        try:
            result = start_bot(name)
            _agent_statuses[name] = {
                "name": name,
                "status": "starting" if result["success"] else "offline",
                "pid": result.get("pid"),
            }
        except Exception:
            _agent_statuses[name] = {"name": name, "status": "offline", "pid": None}

    # Start background health loop
    asyncio.create_task(health_check_loop())


async def health_check_loop():
    """Periodically checks whether each bot process is still alive."""
    while True:
        await asyncio.sleep(10)
        for name in ALL_BOTS:
            pid = get_pid(name)
            if pid:
                _agent_statuses[name]["status"] = "online"
                _agent_statuses[name]["pid"] = pid
            else:
                if _agent_statuses.get(name, {}).get("status") == "online":
                    _agent_statuses[name]["status"] = "offline"


def get_all_statuses() -> list[dict]:
    """Return status list for every known agent."""
    if not _agent_statuses:
        return get_mock_agents()
    return list(_agent_statuses.values())


def start_agent(name: str) -> dict:
    """Start a single agent by name."""
    try:
        result = start_bot(name)
        if result["success"]:
            _agent_statuses[name] = {
                "name": name, "status": "starting", "pid": result["pid"],
            }
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def stop_agent(name: str) -> dict:
    """Stop a single agent by name."""
    try:
        result = stop_bot(name)
        if result["success"]:
            _agent_statuses[name]["status"] = "offline"
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def restart_agent(name: str) -> dict:
    """Stop then start an agent."""
    stop_agent(name)
    return start_agent(name)
