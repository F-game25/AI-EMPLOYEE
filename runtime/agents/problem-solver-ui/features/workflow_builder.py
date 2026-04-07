"""Workflow Builder — no-code custom workflow editor with trigger/action steps."""
import json
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "workflows.json"

TRIGGER_TYPES = [
    "manual", "schedule", "new_lead", "email_opened",
    "deal_stage_change", "invoice_paid", "webhook",
]
ACTION_TYPES = [
    "send_email", "create_task", "update_lead", "send_notification",
    "run_agent", "wait", "condition",
]


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"workflows": [], "runs": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.get("/")
def list_workflows():
    return JSONResponse(_load()["workflows"])


@router.post("/")
async def create_workflow(payload: dict):
    data = _load()
    wf = {
        "id": str(uuid.uuid4())[:8],
        "name": payload.get("name", "New Workflow"),
        "description": payload.get("description", ""),
        "trigger": payload.get("trigger", {"type": "manual"}),
        "steps": payload.get("steps", []),
        "active": payload.get("active", False),
        "runs": 0,
        "last_run": "",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["workflows"].append(wf)
    _save(data)
    return JSONResponse(wf)


@router.patch("/{wf_id}")
async def update_workflow(wf_id: str, payload: dict):
    data = _load()
    for wf in data["workflows"]:
        if wf["id"] == wf_id:
            wf.update({k: v for k, v in payload.items() if k != "id"})
            wf["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse(wf)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.delete("/{wf_id}")
async def delete_workflow(wf_id: str):
    data = _load()
    data["workflows"] = [w for w in data["workflows"] if w["id"] != wf_id]
    _save(data)
    return JSONResponse({"ok": True})


@router.post("/{wf_id}/run")
async def run_workflow(wf_id: str):
    data = _load()
    for wf in data["workflows"]:
        if wf["id"] == wf_id:
            run = {
                "id": str(uuid.uuid4())[:8],
                "workflow_id": wf_id,
                "workflow_name": wf["name"],
                "status": "completed",
                "steps_completed": len(wf.get("steps", [])),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "trigger": "manual",
            }
            data["runs"].append(run)
            wf["runs"] = wf.get("runs", 0) + 1
            wf["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            data["runs"] = data["runs"][-500:]
            _save(data)
            return JSONResponse({"ok": True, "run": run})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.get("/triggers")
def list_triggers():
    return JSONResponse({"triggers": TRIGGER_TYPES, "actions": ACTION_TYPES})


@router.get("/runs")
def list_runs():
    return JSONResponse(_load()["runs"][-50:])
