"""ASCEND AI — Doctor Router"""

import os
import time

import psutil
from fastapi import APIRouter
from pydantic import BaseModel

from services.error_collector import get_errors as _collect_errors
from services.log_streamer import get_logs

router = APIRouter()
_status = {"mode": "off", "active": False, "progress": 0, "last_action": "Idle"}


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
    results = []

    # Backend connectivity — if we respond, it passes
    results.append({"check": "Backend connectivity", "status": "pass"})

    # CPU usage — use a short interval (0.1s) to avoid blocking the request thread
    cpu = psutil.cpu_percent(interval=0.1)
    cpu_status = "warn" if cpu > 85 else "pass"
    results.append({
        "check": "CPU usage",
        "status": cpu_status,
        "detail": f"{cpu:.1f}%",
    })

    # RAM usage
    ram = psutil.virtual_memory()
    ram_pct = ram.percent
    ram_status = "warn" if ram_pct > 85 else "pass"
    results.append({
        "check": "Memory usage",
        "status": ram_status,
        "detail": f"{ram.used // (1024 ** 2)} MB / {ram.total // (1024 ** 2)} MB ({ram_pct:.1f}%)",
    })

    # Disk space
    disk = psutil.disk_usage("/")
    disk_free_gb = disk.free / (1024 ** 3)
    disk_status = "warn" if disk_free_gb < 2 else "pass"
    results.append({
        "check": "Disk space",
        "status": disk_status,
        "detail": f"{disk_free_gb:.1f} GB free",
    })

    # Check running processes count
    proc_count = len(psutil.pids())
    results.append({
        "check": "Running processes",
        "status": "pass",
        "detail": f"{proc_count} processes",
    })

    # API key presence
    env_path = os.path.expanduser("~/.ai-employee/.env")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.path.exists(env_path))
    results.append({
        "check": "API key configured",
        "status": "pass" if has_key else "warn",
        "detail": "Key found" if has_key else "No ANTHROPIC_API_KEY configured",
    })

    # Agent processes
    from services.agent_manager import get_all_statuses
    statuses = get_all_statuses()
    online = [a for a in statuses if a.get("status") == "online"]
    agent_status = "pass" if online else "warn"
    results.append({
        "check": "Agent processes",
        "status": agent_status,
        "detail": f"{len(online)} of {len(statuses)} agents online",
    })

    # Recent errors
    errors = _collect_errors(limit=10)
    err_status = "warn" if errors else "pass"
    results.append({
        "check": "Recent error log",
        "status": err_status,
        "detail": f"{len(errors)} recent error(s)",
    })

    return {"success": True, "results": results, "ts": time.time()}


@router.get("/logs/{bot_name}")
def get_bot_logs(bot_name: str, lines: int = 100):
    return {"bot": bot_name, "lines": get_logs(bot_name, lines)}


@router.get("/errors")
def get_errors_endpoint(limit: int = 50):
    return _collect_errors(limit=limit)


@router.get("/logs/export")
def export_logs():
    """Export all buffered logs as a concatenated response."""
    from services.log_streamer import _buffers
    lines = []
    for bot_name, buf in _buffers.items():
        for line in buf:
            lines.append(f"[{bot_name}] {line}")
    return {"lines": lines, "count": len(lines)}
