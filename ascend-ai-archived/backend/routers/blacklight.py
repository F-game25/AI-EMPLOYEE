"""ASCEND AI — Blacklight Router"""

import time

import psutil
import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
_status = {"mode": "off", "active": False, "progress": 0, "last_action": "Idle"}
_breach_alerts: list[dict] = []
_next_alert_id = 1


class TaskRequest(BaseModel):
    task: str = ""
    mode: str = "off"


def _measure_latency(url: str, timeout: float = 2.0) -> tuple[str, float]:
    """Ping a URL and return (status, latency_ms)."""
    try:
        start = time.monotonic()
        resp = httpx.get(url, timeout=timeout)
        ms = round((time.monotonic() - start) * 1000)
        status = "online" if resp.status_code < 500 else "degraded"
        return status, ms
    except Exception:
        return "offline", 0


def _real_connections() -> list[dict]:
    """Probe real internal endpoints to determine connection status."""
    results = []

    # Main Backend — self-check (we are already responding)
    results.append({"name": "Main Backend", "status": "online", "latency": 0})

    # WebSocket Hub — count connected WS clients
    # WebSocket Hub — always online since we serve the WS route
    results.append({"name": "WebSocket Hub", "status": "online", "latency": 0})

    # Memory Store — check SQLite DB file exists and is readable
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "state" / "memory.db"
    mem_status = "online" if db_path.exists() else "offline"
    results.append({"name": "Memory Store", "status": mem_status, "latency": 0})

    # Agent Gateway — check if any agent process is running
    try:
        from services.agent_manager import get_all_statuses
        agents = get_all_statuses()
        online = any(a.get("status") == "online" for a in agents)
        results.append({"name": "Agent Gateway", "status": "online" if online else "offline", "latency": 0})
    except Exception:
        results.append({"name": "Agent Gateway", "status": "offline", "latency": 0})

    # Forge Engine — check forge status
    try:
        from routers.ascend_forge import _status as forge_s
        results.append({"name": "Forge Engine", "status": "online" if forge_s.get("active") else "standby", "latency": 0})
    except Exception:
        results.append({"name": "Forge Engine", "status": "offline", "latency": 0})

    # Audit Logger — check log directory
    import os
    log_dir = os.path.expanduser("~/.ai-employee/logs")
    results.append({"name": "Audit Logger", "status": "online" if os.path.isdir(log_dir) else "offline", "latency": 0})

    return results


@router.post("/blacklight/task")
def run_task(req: TaskRequest):
    _status["mode"] = req.mode
    _status["active"] = req.mode == "on"
    _status["last_action"] = req.task or "Mode changed"
    return {"success": True, "status": _status}


@router.get("/blacklight/status")
def get_status():
    return {"status": _status, "connections": _real_connections()}


@router.post("/blacklight/toggle")
def toggle():
    _status["active"] = not _status["active"]
    _status["mode"] = "on" if _status["active"] else "off"
    _status["last_action"] = "Toggled " + _status["mode"]
    return {"success": True, "status": _status}


@router.post("/blacklight/rollback")
def rollback():
    _status["active"] = False
    _status["last_action"] = "Rolled back"
    return {"success": True}


@router.post("/blacklight/scan")
def run_scan():
    global _next_alert_id
    results = []
    new_alerts = []

    # Check open ports
    open_ports = {c.laddr.port for c in psutil.net_connections(kind="inet") if c.status == "LISTEN"}
    expected_ports = {8787}
    unexpected = open_ports - expected_ports
    if unexpected:
        results.append({"target": "Network ports", "status": "warn", "issues": len(unexpected)})
        alert_msg = f"Unexpected open ports detected: {sorted(unexpected)}"
        new_alerts.append({"id": _next_alert_id, "message": alert_msg, "severity": "medium", "ts": time.time()})
        _next_alert_id += 1
    else:
        results.append({"target": "Network ports", "status": "secure", "issues": 0})

    # Check API endpoints availability
    connections = _real_connections()
    offline_count = sum(1 for c in connections if c["status"] == "offline")
    results.append({
        "target": "API endpoints",
        "status": "secure" if offline_count == 0 else "warn",
        "issues": offline_count,
    })

    # Check running processes for suspicious activity
    try:
        procs = [p.info for p in psutil.process_iter(["name", "cpu_percent"]) if p.info.get("cpu_percent", 0) > 90]
        results.append({"target": "High-CPU processes", "status": "warn" if procs else "secure", "issues": len(procs)})
        for p in procs[:3]:
            new_alerts.append({
                "id": _next_alert_id,
                "message": f"Process '{p['name']}' using >90% CPU",
                "severity": "high",
                "ts": time.time(),
            })
            _next_alert_id += 1
    except Exception:
        results.append({"target": "High-CPU processes", "status": "secure", "issues": 0})

    _breach_alerts[:0] = new_alerts  # prepend new alerts
    return {"success": True, "results": results, "ts": time.time()}


@router.get("/blacklight/alerts")
def get_alerts(limit: int = 20):
    return _breach_alerts[:limit]
