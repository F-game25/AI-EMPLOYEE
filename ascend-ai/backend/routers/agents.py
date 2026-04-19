"""ASCEND AI — Agents Router"""

from fastapi import APIRouter

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
