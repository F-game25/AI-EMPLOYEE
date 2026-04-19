"""ASCEND AI — Doctor Router"""

from fastapi import APIRouter
from pydantic import BaseModel

from services.log_streamer import get_logs
from services.mock_layer import MOCK_AGENTS

router = APIRouter()
_status = {"mode": "off", "active": False, "progress": 0, "last_action": "Idle"}
_errors: list[dict] = []


class TaskRequest(BaseModel):
    task: str = ""
    mode: str = "off"


@router.post("/doctor/task")
def run_task(req: TaskRequest):
    _status["mode"] = req.mode
    _status["active"] = req.mode == "on"
    _status["last_action"] = req.task or "Mode changed"
    return {"success": True, "status": _status}


@router.get("/doctor/status")
def get_status():
    return _status


@router.post("/doctor/rollback")
def rollback():
    _status["active"] = False
    _status["last_action"] = "Rolled back"
    return {"success": True}


@router.post("/doctor/run")
def run_diagnostic():
    return {
        "success": True,
        "results": [
            {"check": "Backend connectivity", "status": "pass"},
            {"check": "Agent processes", "status": "warn", "detail": "All agents offline"},
            {"check": "Memory usage", "status": "pass"},
            {"check": "Disk space", "status": "pass"},
            {"check": "API keys", "status": "warn", "detail": "No API key configured"},
        ],
    }


@router.get("/logs/{bot_name}")
def get_bot_logs(bot_name: str, lines: int = 100):
    return {"bot": bot_name, "lines": get_logs(bot_name, lines)}


@router.get("/errors")
def get_errors():
    return _errors
