from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import AgentListResponse, AgentStatusResponse, GenericMessage
from app.state import store

router = APIRouter(prefix="/agents", tags=["agents"])

_DEFAULT_AGENTS = [
    "lead_hunter",
    "content_master",
    "social_guru",
    "intel_agent",
    "email_ninja",
    "support_bot",
    "data_analyst",
    "task_orchestrator",
]


def _load() -> dict:
    data = store.read("agents", {})
    if not data:
        data = {a: "stopped" for a in _DEFAULT_AGENTS}
        store.write("agents", data)
    return data


@router.get("", response_model=AgentListResponse)
def list_agents() -> AgentListResponse:
    data = _load()
    return AgentListResponse(agents=[AgentStatusResponse(id=k, status=v) for k, v in data.items()])


@router.get("/{agent_id}/status", response_model=AgentStatusResponse)
def agent_status(agent_id: str) -> AgentStatusResponse:
    data = _load()
    if agent_id not in data:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentStatusResponse(id=agent_id, status=data[agent_id])


@router.post("/{agent_id}/start", response_model=AgentStatusResponse)
def start_agent(agent_id: str) -> AgentStatusResponse:
    data = _load()
    if agent_id not in data:
        raise HTTPException(status_code=404, detail="Agent not found")
    data[agent_id] = "running"
    store.write("agents", data)
    return AgentStatusResponse(id=agent_id, status="running")


@router.post("/{agent_id}/stop", response_model=AgentStatusResponse)
def stop_agent(agent_id: str) -> AgentStatusResponse:
    data = _load()
    if agent_id not in data:
        raise HTTPException(status_code=404, detail="Agent not found")
    data[agent_id] = "stopped"
    store.write("agents", data)
    return AgentStatusResponse(id=agent_id, status="stopped")
