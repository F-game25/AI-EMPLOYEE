"""ASCEND AI — Blacklight Router"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
_status = {"mode": "off", "active": False, "progress": 0, "last_action": "Idle"}


class TaskRequest(BaseModel):
    task: str = ""
    mode: str = "off"


@router.post("/blacklight/task")
def run_task(req: TaskRequest):
    _status["mode"] = req.mode
    _status["active"] = req.mode == "on"
    _status["last_action"] = req.task or "Mode changed"
    return {"success": True, "status": _status}


@router.get("/blacklight/status")
def get_status():
    return _status


@router.post("/blacklight/rollback")
def rollback():
    _status["active"] = False
    _status["last_action"] = "Rolled back"
    return {"success": True}
