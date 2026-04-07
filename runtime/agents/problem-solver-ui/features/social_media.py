"""Social Media Manager — schedule posts, track engagement, AI generation."""
import json
import sys
import time
import uuid
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/social", tags=["social"])

_HOME = Path.home() / ".ai-employee" / "state"
_HOME.mkdir(parents=True, exist_ok=True)
_FILE = _HOME / "social_media.json"
_AI_ROUTER_DIR = str(Path(__file__).parent.parent.parent / "ai-router")

PLATFORMS = ["linkedin", "instagram", "twitter", "facebook"]


def _load() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text())
        except Exception:
            pass
    return {"posts": [], "accounts": []}


def _save(data: dict) -> None:
    _FILE.write_text(json.dumps(data, indent=2))


@router.get("/posts")
def list_posts():
    return JSONResponse(_load()["posts"])


@router.post("/posts")
async def create_post(payload: dict):
    data = _load()
    post = {
        "id": str(uuid.uuid4())[:8],
        "content": payload.get("content", ""),
        "platforms": payload.get("platforms", ["linkedin"]),
        "media_urls": payload.get("media_urls", []),
        "hashtags": payload.get("hashtags", []),
        "status": "draft",
        "scheduled_at": payload.get("scheduled_at", ""),
        "published_at": "",
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "reach": 0,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data["posts"].append(post)
    _save(data)
    return JSONResponse(post)


@router.patch("/posts/{pid}")
async def update_post(pid: str, payload: dict):
    data = _load()
    for p in data["posts"]:
        if p["id"] == pid:
            p.update({k: v for k, v in payload.items() if k != "id"})
            _save(data)
            return JSONResponse(p)
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/posts/{pid}/publish")
async def publish_post(pid: str):
    data = _load()
    for p in data["posts"]:
        if p["id"] == pid:
            p["status"] = "published"
            p["published_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            _save(data)
            return JSONResponse({"ok": True, "post": p})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/posts/{pid}/schedule")
async def schedule_post(pid: str, payload: dict):
    data = _load()
    for p in data["posts"]:
        if p["id"] == pid:
            p["status"] = "scheduled"
            p["scheduled_at"] = payload.get("scheduled_at", "")
            _save(data)
            return JSONResponse({"ok": True})
    return JSONResponse({"error": "not found"}, status_code=404)


@router.delete("/posts/{pid}")
async def delete_post(pid: str):
    data = _load()
    data["posts"] = [p for p in data["posts"] if p["id"] != pid]
    _save(data)
    return JSONResponse({"ok": True})


@router.post("/generate")
async def generate_post(payload: dict):
    topic = payload.get("topic", "")
    platform = payload.get("platform", "linkedin")
    tone = payload.get("tone", "professional")
    try:
        if _AI_ROUTER_DIR not in sys.path:
            sys.path.insert(0, _AI_ROUTER_DIR)
        from ai_router import query_ai_for_agent  # type: ignore[import]
        prompt = (
            f"Write a {tone} social media post for {platform} about: {topic}. "
            f"Include relevant hashtags. Keep it engaging and platform-appropriate."
        )
        result = query_ai_for_agent("social-media-manager", prompt)
        content = result.get("content", result.get("text", f"Post about {topic}"))
    except Exception:
        content = f"🚀 Excited to share insights about {topic}! #growth #business"
    return JSONResponse({"content": content, "platform": platform})


@router.get("/stats")
def social_stats():
    data = _load()
    posts = data["posts"]
    published = [p for p in posts if p.get("status") == "published"]
    return JSONResponse({
        "total_posts": len(posts),
        "published": len(published),
        "scheduled": len([p for p in posts if p.get("status") == "scheduled"]),
        "drafts": len([p for p in posts if p.get("status") == "draft"]),
        "total_likes": sum(p.get("likes", 0) for p in published),
        "total_reach": sum(p.get("reach", 0) for p in published),
        "platforms": PLATFORMS,
    })
