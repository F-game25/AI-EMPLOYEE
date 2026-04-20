"""ASCEND AI — Agents Router"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from services.agent_manager import (
    get_all_statuses,
    restart_agent,
    start_agent,
    stop_agent,
)

router = APIRouter()


@router.get("/agents")
def list_agents():
    return get_all_statuses()


@router.post("/agents/{name}/start")
def start(name: str):
    return start_agent(name)


@router.post("/agents/{name}/stop")
def stop(name: str):
    return stop_agent(name)


@router.post("/agents/{name}/restart")
def restart(name: str):
    return restart_agent(name)


@router.post("/agents/pause-all")
def pause_all():
    """Stop all currently running agents."""
    statuses = get_all_statuses()
    stopped = []
    errors = []
    for agent in statuses:
        name = agent.get("name", "")
        if agent.get("status") == "online" and name:
            result = stop_agent(name)
            if result.get("success"):
                stopped.append(name)
            else:
                errors.append(name)
    return {"success": True, "stopped": stopped, "errors": errors}
