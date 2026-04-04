"""Faceless Video Bot — YouTube/TikTok faceless video production pipeline.

Given a topic, produces a complete content package: video script with hook and
scenes, voiceover text ready for ElevenLabs, visual descriptions ready for
Runway ML / Midjourney, B-roll suggestions, YouTube SEO (title A/B, description,
tags), thumbnail concept, and a 30-day posting schedule.  All artefacts are
persisted as a JSON package so downstream tools (or humans) can act immediately.

Commands:
  video <topic>                — full pipeline: research → script → scenes → voiceover → SEO → save
  video script <topic>         — hook + 5-7 scenes + CTA only
  video seo <topic>            — YouTube title (A/B), description, tags, thumbnail concept
  video tiktok <topic>         — 60-second short-form script with TikTok hooks + captions
  video schedule <channel>     — 30-day upload schedule for a channel theme
  video voiceover <script>     — clean voiceover text (no stage directions, natural speech)
  video status                 — total videos produced, channel topics, revenue tips
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "faceless-video.state.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
POLL_INTERVAL = int(os.environ.get("FACELESS_VIDEO_POLL_INTERVAL", "5"))
DEFAULT_PLATFORM = os.environ.get("VIDEO_DEFAULT_PLATFORM", "youtube")
VIDEO_STYLE = os.environ.get("VIDEO_STYLE", "educational")
VIDEO_LENGTH_SECONDS = int(os.environ.get("VIDEO_LENGTH_SECONDS", "600"))

_ai_router_path = AI_HOME / "agents" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent, search_web as _search_web  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def load_chatlog():
    if not CHATLOG.exists():
        return []
    try:
        return [json.loads(l) for l in CHATLOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []


def append_chatlog(e):
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(e) + "\n")


def _ai(prompt, system=""):
    if not _AI_AVAILABLE:
        return "[AI unavailable]"
    return (_query_ai_for_agent("faceless-video", prompt, system_prompt=system) or {}).get("answer", "")


def _search(query):
    if not _AI_AVAILABLE:
        return "[search unavailable]"
    try:
        return (_search_web(query) or {}).get("results", "[no results]")
    except Exception:
        return "[search error]"


def _safe_topic(topic: str) -> str:
    return re.sub(r"[^\w-]", "_", topic.strip().lower())[:60]


def _video_dir() -> Path:
    d = AI_HOME / "social_content"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_index() -> list:
    idx_file = AI_HOME / "state" / "video-index.json"
    if not idx_file.exists():
        return []
    try:
        return json.loads(idx_file.read_text())
    except Exception:
        return []


def _save_index(index: list):
    idx_file = AI_HOME / "state" / "video-index.json"
    idx_file.parent.mkdir(parents=True, exist_ok=True)
    idx_file.write_text(json.dumps(index, indent=2))


def _save_package(pkg: dict) -> Path:
    ts = now_iso().replace(":", "-")
    safe = _safe_topic(pkg.get("topic", "unknown"))
    path = _video_dir() / f"video_{safe}_{ts}.json"
    path.write_text(json.dumps(pkg, indent=2))
    index = _load_index()
    index.append({"file": str(path), "topic": pkg.get("topic"), "platform": pkg.get("platform"), "created_at": pkg.get("created_at")})
    _save_index(index)
    return path


# ── generation helpers ────────────────────────────────────────────────────────

def _gen_script(topic: str, platform: str = "youtube") -> str:
    length_note = f"{VIDEO_LENGTH_SECONDS // 60} minutes" if platform == "youtube" else "60 seconds"
    system = (
        f"You are an expert {VIDEO_STYLE} faceless video scriptwriter for {platform}. "
        "Write engaging, hook-driven content."
    )
    prompt = (
        f"Write a complete faceless {platform} video script about: '{topic}'.\n"
        f"Target length: {length_note}.\n"
        "Structure:\n"
        "1. HOOK (first 15 seconds — bold attention-grabbing opener)\n"
        "2. INTRO (problem/promise statement)\n"
        "3. SCENES (5-7 numbered scenes with title + narration + visual cue)\n"
        "4. CTA (subscribe, comment, follow-up video tease)\n"
        "Use plain narration language. No on-camera references."
    )
    return _ai(prompt, system)


def _gen_scenes(script: str) -> list:
    prompt = (
        "Extract each numbered scene from the script below and return a JSON array.\n"
        "Each element: {\"scene\": N, \"title\": \"...\", \"narration\": \"...\", \"visual_cue\": \"...\"}\n"
        "Return ONLY the JSON array.\n\n"
        f"SCRIPT:\n{script}"
    )
    raw = _ai(prompt)
    try:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        return json.loads(m.group()) if m else []
    except Exception:
        return []


def _gen_voiceover(script: str) -> str:
    system = "You are a professional voiceover editor. Output clean, natural speech text only."
    prompt = (
        "Convert the following video script into clean voiceover text.\n"
        "Rules:\n"
        "- Remove all stage directions, scene labels, visual cues, brackets\n"
        "- Keep only words that will be spoken aloud\n"
        "- Natural sentence flow, no bullet points\n"
        "- Add '...' for natural pauses\n\n"
        f"SCRIPT:\n{script}"
    )
    return _ai(prompt, system)


def _gen_visual_prompts(scenes: list, topic: str) -> list:
    if not scenes:
        prompt = (
            f"Generate 6 detailed Midjourney/Runway ML visual prompts for a faceless video about '{topic}'.\n"
            "Each prompt: cinematic style, specify lighting, mood, camera angle. No people faces.\n"
            "Return as a JSON array of strings."
        )
        raw = _ai(prompt)
        try:
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            return json.loads(m.group()) if m else []
        except Exception:
            return []
    prompts = []
    for scene in scenes[:7]:
        cue = scene.get("visual_cue", scene.get("title", ""))
        prompt = (
            f"Write a detailed Midjourney image prompt for this video scene visual cue:\n'{cue}'\n"
            "Style: cinematic, 4K, no human faces, specify lighting and mood. One sentence."
        )
        prompts.append(_ai(prompt))
    return prompts


def _gen_seo(topic: str, script: str = "") -> dict:
    system = "You are a YouTube SEO expert. Maximize click-through rate and searchability."
    prompt = (
        f"Generate YouTube SEO package for a video about: '{topic}'.\n"
        "Return JSON with keys:\n"
        "  title_a: primary title (max 60 chars, power word + number + keyword)\n"
        "  title_b: A/B variant title (curiosity gap style)\n"
        "  description: 250-word description (keyword-rich, first 125 chars hook, timestamps, links section)\n"
        "  tags: array of 15 tags (mix short-tail and long-tail)\n"
        "  thumbnail: thumbnail concept description (text overlay + visual element)\n"
        "Return ONLY valid JSON."
    )
    raw = _ai(prompt, system)
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group()) if m else {}
    except Exception:
        data = {}
    return {
        "title": data.get("title_a", f"How {topic} Changes Everything"),
        "title_b": data.get("title_b", ""),
        "description": data.get("description", ""),
        "tags": data.get("tags", [topic]),
        "thumbnail": data.get("thumbnail", ""),
    }


def _gen_tiktok(topic: str) -> str:
    system = "You are a viral TikTok scriptwriter. Short, punchy, addictive content."
    prompt = (
        f"Write a 60-second TikTok faceless video script about: '{topic}'.\n"
        "Structure:\n"
        "1. HOOK (0-3s): Bold visual text hook\n"
        "2. BODY (3-50s): 5 quick punchy points with on-screen captions\n"
        "3. CTA (50-60s): Follow + comment prompt\n"
        "Include [CAPTION: ...] markers for on-screen text overlays.\n"
        "High energy, fast cuts implied."
    )
    return _ai(prompt, system)


def _gen_schedule(channel_topic: str) -> str:
    system = "You are a YouTube channel growth strategist."
    prompt = (
        f"Generate a 30-day content upload schedule for a '{channel_topic}' faceless YouTube channel.\n"
        "Format: Day N | Title | Hook Concept | Best Upload Time\n"
        "Mix: 2 videos/week, alternate educational and listicle formats.\n"
        "Include trending angles and SEO-friendly titles."
    )
    return _ai(prompt, system)


def _full_pipeline(topic: str, platform: str = None) -> dict:
    platform = platform or DEFAULT_PLATFORM
    print(f"[{now_iso()}] faceless-video: running full pipeline for '{topic}' on {platform}")
    script = _gen_script(topic, platform)
    scenes = _gen_scenes(script)
    voiceover = _gen_voiceover(script)
    visual_prompts = _gen_visual_prompts(scenes, topic)
    seo = _gen_seo(topic, script)
    pkg = {
        "topic": topic,
        "platform": platform,
        "script": script,
        "scenes": scenes,
        "voiceover": voiceover,
        "visual_prompts": visual_prompts,
        "seo": {
            "title": seo.get("title", ""),
            "title_b": seo.get("title_b", ""),
            "description": seo.get("description", ""),
            "tags": seo.get("tags", []),
        },
        "thumbnail": seo.get("thumbnail", ""),
        "created_at": now_iso(),
    }
    return pkg


def _bot_reply(message: str):
    append_chatlog({"type": "bot", "bot": "faceless-video", "message": message, "ts": now_iso()})
    print(f"[{now_iso()}] faceless-video reply: {message[:120]}")


# ── command processing ────────────────────────────────────────────────────────

def process_chatlog(last_idx: int) -> int:
    chatlog = load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        if not msg_lower.startswith("video"):
            continue

        # video status
        if msg_lower in ("video status", "video stats"):
            index = _load_index()
            topics = list({v.get("topic", "") for v in index})
            tip = (
                "Monetize via: AdSense (1M views = $1K-5K), "
                "affiliate links in description, "
                "sponsorships ($500-5K/video at 100K subs)"
            )
            reply = (
                f"📹 Faceless Video Bot Status\n"
                f"  Total packages produced : {len(index)}\n"
                f"  Unique topics           : {len(topics)}\n"
                f"  Default platform        : {DEFAULT_PLATFORM}\n"
                f"  Style / target length   : {VIDEO_STYLE} / {VIDEO_LENGTH_SECONDS}s\n"
                f"  💰 Revenue tip: {tip}"
            )
            _bot_reply(reply)
            continue

        # video voiceover <script>
        if msg_lower.startswith("video voiceover "):
            raw_script = msg[len("video voiceover "):].strip()
            if not raw_script:
                _bot_reply("Usage: video voiceover <your script text>")
                continue
            vo = _gen_voiceover(raw_script)
            _bot_reply(f"🎙️ Voiceover text:\n\n{vo}")
            continue

        # video schedule <channel_topic>
        if msg_lower.startswith("video schedule "):
            channel = msg[len("video schedule "):].strip()
            if not channel:
                _bot_reply("Usage: video schedule <channel topic>")
                continue
            schedule = _gen_schedule(channel)
            _bot_reply(f"📅 30-Day Upload Schedule — {channel}:\n\n{schedule}")
            continue

        # video tiktok <topic>
        if msg_lower.startswith("video tiktok "):
            topic = msg[len("video tiktok "):].strip()
            if not topic:
                _bot_reply("Usage: video tiktok <topic>")
                continue
            script = _gen_tiktok(topic)
            _bot_reply(f"🎵 TikTok 60s Script — {topic}:\n\n{script}")
            continue

        # video seo <topic>
        if msg_lower.startswith("video seo "):
            topic = msg[len("video seo "):].strip()
            if not topic:
                _bot_reply("Usage: video seo <topic>")
                continue
            seo = _gen_seo(topic)
            reply = (
                f"🔍 YouTube SEO — {topic}\n"
                f"  Title A  : {seo.get('title')}\n"
                f"  Title B  : {seo.get('title_b')}\n"
                f"  Tags     : {', '.join(seo.get('tags', []))}\n"
                f"  Thumbnail: {seo.get('thumbnail')}\n\n"
                f"Description:\n{seo.get('description')}"
            )
            _bot_reply(reply)
            continue

        # video script <topic>
        if msg_lower.startswith("video script "):
            topic = msg[len("video script "):].strip()
            if not topic:
                _bot_reply("Usage: video script <topic>")
                continue
            script = _gen_script(topic)
            _bot_reply(f"📝 Script — {topic}:\n\n{script}")
            continue

        # video <topic>  — full pipeline
        if msg_lower.startswith("video "):
            topic = msg[len("video "):].strip()
            if not topic:
                _bot_reply("Usage: video <topic>")
                continue
            _bot_reply(f"⚙️ Starting full video pipeline for: '{topic}' — this may take a moment…")
            try:
                pkg = _full_pipeline(topic)
                path = _save_package(pkg)
                seo = pkg.get("seo", {})
                reply = (
                    f"✅ Video package ready — {topic}\n"
                    f"  Platform  : {pkg['platform']}\n"
                    f"  Scenes    : {len(pkg.get('scenes', []))}\n"
                    f"  Title A   : {seo.get('title')}\n"
                    f"  Tags      : {', '.join((seo.get('tags') or [])[:5])}…\n"
                    f"  Thumbnail : {pkg.get('thumbnail', '')[:80]}\n"
                    f"  📦 Saved  : {path}"
                )
            except Exception as exc:
                reply = f"❌ Pipeline error: {exc}"
            _bot_reply(reply)
            continue

    return new_idx


def main():
    print(f"[{now_iso()}] faceless-video started")
    last_idx = len(load_chatlog())
    write_state({"bot": "faceless-video", "ts": now_iso(), "status": "starting"})
    while True:
        try:
            new_idx = process_chatlog(last_idx)
            last_idx = new_idx
        except Exception as exc:
            print(f"[{now_iso()}] faceless-video error: {exc}")
        write_state({"bot": "faceless-video", "ts": now_iso(), "status": "running"})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
