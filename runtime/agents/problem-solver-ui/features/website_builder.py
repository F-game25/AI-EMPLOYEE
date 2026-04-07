"""Website / Landing Page Builder Agent — AI-generated page HTML."""
import json
import sys
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/website-builder", tags=["website"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "websites.json"
_AI_ROUTER_DIR = str(Path(__file__).parent.parent.parent / "ai-router")

PAGE_TYPES = ["landing", "sales", "portfolio", "blog", "product", "coming_soon"]


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"pages": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.get("/pages")
def list_pages():
    data = _load()
    # Return pages without full HTML to keep list responses small
    return JSONResponse([
        {k: v for k, v in p.items() if k != "html_content"} for p in data["pages"]
    ])


@router.get("/pages/{pid}")
def get_page(pid: str):
    data = _load()
    for p in data["pages"]:
        if p["id"] == pid:
            return JSONResponse(p)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/generate")
async def generate_page(payload: dict):
    business_name = payload.get("business_name", "My Business")
    page_type = payload.get("page_type", "landing")
    industry = payload.get("industry", "")
    description = payload.get("description", "")
    tone = payload.get("tone", "professional")

    prompt = (
        f"Generate a complete HTML landing page for {business_name} ({industry}).\n"
        f"Page type: {page_type}, Tone: {tone}\n"
        f"Description: {description}\n\n"
        f"Include: hero section, features/benefits, CTA, and footer. Use modern inline CSS."
    )
    fallback = (
        f"<!DOCTYPE html><html><head><title>{business_name}</title></head>"
        f"<body><h1>{business_name}</h1><p>{description}</p></body></html>"
    )
    try:
        if _AI_ROUTER_DIR not in sys.path:
            sys.path.insert(0, _AI_ROUTER_DIR)
        from ai_router import query_ai_for_agent  # type: ignore[import]
        result = query_ai_for_agent("website-builder", prompt)
        html_content = result.get("content", result.get("text", fallback))
    except Exception:
        html_content = fallback

    data = _load()
    page = {
        "id": str(uuid.uuid4())[:8],
        "name": f"{business_name} — {page_type.replace('_', ' ').title()}",
        "type": page_type,
        "business_name": business_name,
        "industry": industry,
        "html_content": html_content,
        "status": "draft",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["pages"].append(page)
    _save(data)
    return JSONResponse({k: v for k, v in page.items() if k != "html_content"} | {"preview_length": len(html_content)})


@router.patch("/pages/{pid}")
async def update_page(pid: str, payload: dict):
    data = _load()
    for p in data["pages"]:
        if p["id"] == pid:
            p.update({k: v for k, v in payload.items() if k != "id"})
            _save(data)
            return JSONResponse({k: v for k, v in p.items() if k != "html_content"})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.delete("/pages/{pid}")
async def delete_page(pid: str):
    data = _load()
    data["pages"] = [p for p in data["pages"] if p["id"] != pid]
    _save(data)
    return JSONResponse({"ok": True})
