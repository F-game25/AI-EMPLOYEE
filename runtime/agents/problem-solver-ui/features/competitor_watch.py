"""Competitor Watch Agent — monitor competitors, AI analysis, change alerts."""
import json
import sys
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/competitors", tags=["competitors"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "competitors.json"
_AI_ROUTER_DIR = str(Path(__file__).parent.parent.parent / "ai-router")


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"competitors": [], "alerts": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.get("/")
def list_competitors():
    return JSONResponse(_load()["competitors"])


@router.post("/")
async def add_competitor(payload: dict):
    data = _load()
    comp = {
        "id": str(uuid.uuid4())[:8],
        "name": payload.get("name", ""),
        "website": payload.get("website", ""),
        "description": payload.get("description", ""),
        "strengths": payload.get("strengths", []),
        "weaknesses": payload.get("weaknesses", []),
        "pricing": payload.get("pricing", ""),
        "social_handles": payload.get("social_handles", {}),
        "analysis": "",
        "last_checked": "",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["competitors"].append(comp)
    _save(data)
    return JSONResponse(comp)


@router.patch("/{cid}")
async def update_competitor(cid: str, payload: dict):
    data = _load()
    for c in data["competitors"]:
        if c["id"] == cid:
            c.update({k: v for k, v in payload.items() if k != "id"})
            _save(data)
            return JSONResponse(c)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/{cid}/analyze")
async def analyze_competitor(cid: str):
    data = _load()
    for c in data["competitors"]:
        if c["id"] == cid:
            prompt = (
                f"Analyze competitor: {c['name']} ({c.get('website', '')})\n"
                f"Description: {c.get('description', '')}\n\n"
                f"Provide: 1) Key strengths 2) Weaknesses/opportunities "
                f"3) Recommended counter-strategies"
            )
            fallback = (
                f"Analysis for {c['name']}: Review their website and social media "
                f"for latest updates and positioning."
            )
            try:
                if _AI_ROUTER_DIR not in sys.path:
                    sys.path.insert(0, _AI_ROUTER_DIR)
                from ai_router import query_ai_for_agent  # type: ignore[import]
                result = query_ai_for_agent("competitor-watch", prompt)
                analysis = result.get("content", result.get("text", fallback))
            except Exception:
                analysis = fallback
            c["analysis"] = analysis
            c["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse({"analysis": analysis, "competitor": c})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.delete("/{cid}")
async def delete_competitor(cid: str):
    data = _load()
    data["competitors"] = [c for c in data["competitors"] if c["id"] != cid]
    _save(data)
    return JSONResponse({"ok": True})


@router.get("/alerts")
def get_alerts():
    return JSONResponse(_load()["alerts"])
