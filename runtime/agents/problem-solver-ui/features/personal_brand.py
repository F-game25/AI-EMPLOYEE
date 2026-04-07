"""Personal Brand Agent — thought leadership content, brand profile, topic ideas."""
import json
import sys
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/brand", tags=["brand"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "personal_brand.json"
_AI_ROUTER_DIR = str(Path(__file__).parent.parent.parent / "ai-router")


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"profile": {}, "content_pieces": [], "topics": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.get("/profile")
def get_profile():
    return JSONResponse(_load()["profile"])


@router.post("/profile")
async def save_profile(payload: dict):
    data = _load()
    data["profile"] = {
        "name": payload.get("name", ""),
        "title": payload.get("title", ""),
        "industry": payload.get("industry", ""),
        "expertise": payload.get("expertise", []),
        "tone": payload.get("tone", "professional"),
        "target_audience": payload.get("target_audience", ""),
        "goals": payload.get("goals", []),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _save(data)
    return JSONResponse(data["profile"])


@router.post("/generate-content")
async def generate_content(payload: dict):
    data = _load()
    profile = data.get("profile", {})
    content_type = payload.get("content_type", "linkedin_post")
    topic = payload.get("topic", "")

    prompt = (
        f"Create a {content_type} for {profile.get('name', 'a professional')} "
        f"({profile.get('title', '')}) in {profile.get('industry', 'business')}.\n"
        f"Topic: {topic}\nTone: {profile.get('tone', 'professional')}\n"
        f"Target audience: {profile.get('target_audience', 'business professionals')}\n"
        f"Make it authentic, insightful, and shareable."
    )
    fallback = f"Thought leadership content about {topic}."
    try:
        if _AI_ROUTER_DIR not in sys.path:
            sys.path.insert(0, _AI_ROUTER_DIR)
        from ai_router import query_ai_for_agent  # type: ignore[import]
        result = query_ai_for_agent("brand-strategist", prompt)
        content = result.get("content", result.get("text", fallback))
    except Exception:
        content = fallback

    piece = {
        "id": str(uuid.uuid4())[:8],
        "type": content_type,
        "topic": topic,
        "content": content,
        "status": "draft",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["content_pieces"].append(piece)
    _save(data)
    return JSONResponse(piece)


@router.get("/content")
def list_content():
    return JSONResponse(_load()["content_pieces"])


@router.delete("/content/{pid}")
async def delete_content(pid: str):
    data = _load()
    data["content_pieces"] = [p for p in data["content_pieces"] if p["id"] != pid]
    _save(data)
    return JSONResponse({"ok": True})


@router.post("/topics")
async def suggest_topics(payload: dict):
    data = _load()
    profile = data.get("profile", {})
    prompt = (
        f"Suggest 10 thought leadership content topics for "
        f"{profile.get('name', 'a professional')} in "
        f"{profile.get('industry', 'business')}. "
        f"Expertise: {', '.join(profile.get('expertise', []))}. "
        f"Format as a numbered list."
    )
    fallback_topics = [
        "Leadership lessons learned the hard way",
        "Industry trends to watch",
        "Career growth strategies",
        "Innovation mindset in practice",
        "Building high-performance teams",
    ]
    try:
        if _AI_ROUTER_DIR not in sys.path:
            sys.path.insert(0, _AI_ROUTER_DIR)
        from ai_router import query_ai_for_agent  # type: ignore[import]
        result = query_ai_for_agent("brand-strategist", prompt)
        text = result.get("content", result.get("text", ""))
        topics = [
            line.lstrip("0123456789. ").strip()
            for line in text.split("\n")
            if line.strip() and line.strip()[0].isdigit()
        ][:10]
        if not topics:
            topics = fallback_topics
    except Exception:
        topics = fallback_topics
    data["topics"] = topics
    _save(data)
    return JSONResponse({"topics": topics})


@router.get("/topics")
def get_topics():
    return JSONResponse(_load()["topics"])
