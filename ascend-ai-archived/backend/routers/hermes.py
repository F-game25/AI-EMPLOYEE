"""ASCEND AI — Hermes Coordination Agent Router"""

import time

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_status = {"mode": "off", "active": False, "last_action": "Idle"}
_routed_tasks: list[dict] = []
_next_task_id = 1
_notification_settings = {
    "whatsapp": False,
    "telegram": False,
    "triggers": {"task_complete": True, "lead_generated": True, "error_occurred": True},
}


class TaskRequest(BaseModel):
    task: str = ""
    mode: str = "off"


class BroadcastRequest(BaseModel):
    message: str


class NotificationSettings(BaseModel):
    whatsapp: bool | None = None
    telegram: bool | None = None
    triggers: dict | None = None


@router.post("/hermes/task")
def run_task(req: TaskRequest):
    global _next_task_id
    _status["mode"] = req.mode
    _status["active"] = req.mode == "on"
    _status["last_action"] = req.task or "Mode changed"

    if req.task:
        # Route task to appropriate agent based on keywords
        agent = _route_task(req.task)
        entry = {
            "id": _next_task_id,
            "task": req.task,
            "agent": agent,
            "status": "routed",
            "result": "",
            "ts": time.time(),
        }
        _routed_tasks.insert(0, entry)
        _next_task_id += 1
        # Keep only last 50 routed tasks
        del _routed_tasks[50:]

    return {"success": True, "status": _status}


@router.get("/hermes/status")
def get_status():
    return {"status": _status, "routed_tasks": _routed_tasks[:20]}


@router.post("/hermes/broadcast")
def broadcast(req: BroadcastRequest):
    global _next_task_id
    agents = ["Forge", "MoneyMode", "Blacklight", "Doctor"]
    entries = []
    for agent in agents:
        entry = {
            "id": _next_task_id,
            "task": f"[BROADCAST] {req.message}",
            "agent": agent,
            "status": "broadcast",
            "result": "",
            "ts": time.time(),
        }
        _routed_tasks.insert(0, entry)
        entries.append(entry)
        _next_task_id += 1
    del _routed_tasks[50:]
    return {"success": True, "broadcast_to": agents, "message": req.message}


@router.get("/hermes/notifications")
def get_notifications():
    return _notification_settings


@router.post("/hermes/notifications")
def update_notifications(req: NotificationSettings):
    if req.whatsapp is not None:
        _notification_settings["whatsapp"] = req.whatsapp
    if req.telegram is not None:
        _notification_settings["telegram"] = req.telegram
    if req.triggers is not None:
        _notification_settings["triggers"].update(req.triggers)
    return {"success": True, "settings": _notification_settings}


def _route_task(task: str) -> str:
    """Simple keyword-based task routing."""
    task_lower = task.lower()
    if any(w in task_lower for w in ["code", "optimize", "forge", "improve", "sandbox"]):
        return "AscendForge"
    if any(w in task_lower for w in ["lead", "revenue", "money", "sale", "email", "campaign"]):
        return "MoneyMode"
    if any(w in task_lower for w in ["security", "scan", "threat", "breach", "safe"]):
        return "Blacklight"
    if any(w in task_lower for w in ["health", "diagnose", "error", "log", "metric"]):
        return "Doctor"
    return "TaskOrchestrator"
