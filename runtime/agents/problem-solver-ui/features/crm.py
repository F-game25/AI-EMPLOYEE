"""CRM feature — lead pipeline, deal stages, lead scoring, follow-up sequences."""
import json
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/crm", tags=["crm"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_CRM_FILE = _HOME / "crm.json"

DEAL_STAGES = ["lead", "contacted", "qualified", "proposal", "negotiation", "won", "lost"]


def _load() -> dict:
    if _CRM_FILE.exists():
        try:
            return json.loads(_CRM_FILE.read_text())
        except Exception:
            pass
    return {"leads": [], "sequences": []}


def _save(data: dict) -> None:
    _CRM_FILE.write_text(json.dumps(data, indent=2))


@router.get("/leads")
def list_leads():
    return JSONResponse(_load()["leads"])


@router.post("/leads")
async def create_lead(payload: dict):
    data = _load()
    lead = {
        "id": str(uuid.uuid4())[:8],
        "name": payload.get("name", ""),
        "company": payload.get("company", ""),
        "email": payload.get("email", ""),
        "phone": payload.get("phone", ""),
        "score": 0,
        "stage": payload.get("stage", "lead"),
        "notes": payload.get("notes", ""),
        "tags": payload.get("tags", []),
        "value": payload.get("value", 0),
        "follow_up_date": payload.get("follow_up_date", ""),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Auto-score on creation
    score = 0
    if lead["email"]:
        score += 20
    if lead["phone"]:
        score += 10
    if lead["company"]:
        score += 15
    if lead["value"] > 1000:
        score += 25
    lead["score"] = min(score, 100)
    data["leads"].append(lead)
    _save(data)
    return JSONResponse(lead)


@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: dict):
    data = _load()
    for lead in data["leads"]:
        if lead["id"] == lead_id:
            lead.update({k: v for k, v in payload.items() if k != "id"})
            lead["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse(lead)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str):
    data = _load()
    data["leads"] = [l for l in data["leads"] if l["id"] != lead_id]
    _save(data)
    return JSONResponse({"ok": True})


@router.get("/pipeline")
def get_pipeline():
    data = _load()
    pipeline = {stage: [] for stage in DEAL_STAGES}
    for lead in data["leads"]:
        stage = lead.get("stage", "lead")
        if stage in pipeline:
            pipeline[stage].append(lead)
    total_value = sum(l.get("value", 0) for l in data["leads"])
    won_value = sum(l.get("value", 0) for l in data["leads"] if l.get("stage") == "won")
    pipeline_value = sum(
        l.get("value", 0) for l in data["leads"] if l.get("stage") not in ("won", "lost")
    )
    return JSONResponse({
        "pipeline": pipeline,
        "stages": DEAL_STAGES,
        "total": len(data["leads"]),
        "total_value": total_value,
        "won_value": won_value,
        "pipeline_value": pipeline_value,
    })


@router.post("/leads/{lead_id}/score")
async def score_lead(lead_id: str, payload: dict):
    data = _load()
    for lead in data["leads"]:
        if lead["id"] == lead_id:
            score = 0
            if lead.get("email"):
                score += 20
            if lead.get("phone"):
                score += 10
            if lead.get("company"):
                score += 15
            if lead.get("value", 0) > 1000:
                score += 25
            stage_scores = {
                "lead": 0, "contacted": 10, "qualified": 20,
                "proposal": 30, "negotiation": 40, "won": 50,
            }
            score += stage_scores.get(lead.get("stage", "lead"), 0)
            lead["score"] = min(score + payload.get("manual_boost", 0), 100)
            lead["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse({"score": lead["score"], "lead_id": lead_id})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.get("/sequences")
def list_sequences():
    return JSONResponse(_load()["sequences"])


@router.post("/sequences")
async def create_sequence(payload: dict):
    data = _load()
    seq = {
        "id": str(uuid.uuid4())[:8],
        "name": payload.get("name", "New Sequence"),
        "steps": payload.get("steps", []),
        "trigger": payload.get("trigger", "manual"),
        "active": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["sequences"].append(seq)
    _save(data)
    return JSONResponse(seq)


@router.get("/stats")
def crm_stats():
    data = _load()
    leads = data["leads"]
    by_stage = {s: len([l for l in leads if l.get("stage") == s]) for s in DEAL_STAGES}
    won_leads = [l for l in leads if l.get("stage") == "won"]
    return JSONResponse({
        "total_leads": len(leads),
        "by_stage": by_stage,
        "avg_score": round(
            sum(l.get("score", 0) for l in leads) / max(len(leads), 1), 1
        ),
        "pipeline_value": sum(
            l.get("value", 0) for l in leads if l.get("stage") not in ("won", "lost")
        ),
        "won_value": sum(l.get("value", 0) for l in won_leads),
        "conversion_rate": round(len(won_leads) / max(len(leads), 1) * 100, 1),
    })
