"""Creator Agency Bot — creator/personal brand automation: content planning, DM funnels,
upsell scripts, chat simulation, captions, comment replies, and brand kits.

Generates complete content strategies, fan engagement scripts, and monetisation copy
for creators, influencers, and personal brand builders.

Commands (via chatlog):
  creator plan <username|topic>    — 30-day content calendar with daily post ideas
  creator dm-funnel <style>        — complete DM funnel (5-7 messages: opener→close)
  creator upsell <tier>            — upsell scripts for content tiers (e.g. "premium $30/mo")
  creator chat <persona>           — chat simulation scripts (flirty/friendly/professional)
  creator captions <platform> <topic> — 10 engaging captions with hooks
  creator comments <post_topic>    — 10 comment reply templates that drive engagement
  creator brand <name> <niche>     — full brand kit: bio, content pillars, tone, hashtags
  creator status                   — generated content count, DM funnels, brand kits

Config env vars:
  CREATOR_AGENCY_POLL_INTERVAL  — chatlog poll seconds (default: 5)
  CREATOR_DEFAULT_PLATFORM      — default platform: instagram|tiktok|onlyfans (default: instagram)
  CREATOR_PERSONA               — default creator persona/style
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE   = AI_HOME / "state" / "creator-agency.state.json"
CHATLOG      = AI_HOME / "state" / "chatlog.jsonl"
CONTENT_DIR  = AI_HOME / "social_content"

POLL_INTERVAL      = int(os.environ.get("CREATOR_AGENCY_POLL_INTERVAL", "5"))
DEFAULT_PLATFORM   = os.environ.get("CREATOR_DEFAULT_PLATFORM", "instagram")
DEFAULT_PERSONA    = os.environ.get("CREATOR_PERSONA", "")

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ts_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def write_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
        return [json.loads(l) for l in CHATLOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []


def append_chatlog(e: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(e) + "\n")


def _ai(prompt: str, system: str = "") -> str:
    if not _AI_AVAILABLE:
        return "[AI unavailable]"
    return (_query_ai_for_agent("creator-agency", prompt, system_prompt=system) or {}).get("answer", "")


def _save_content(name: str, data: dict) -> Path:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-z0-9_-]", "_", name.lower())
    path = CONTENT_DIR / f"creator_{safe_name}_{ts_slug()}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def _load_stats() -> dict:
    state_path = AI_HOME / "state" / "creator-agency-stats.json"
    if not state_path.exists():
        return {"plans": 0, "funnels": 0, "upsells": 0, "captions": 0,
                "comment_sets": 0, "brand_kits": 0, "chat_scripts": 0}
    try:
        return json.loads(state_path.read_text())
    except Exception:
        return {"plans": 0, "funnels": 0, "upsells": 0, "captions": 0,
                "comment_sets": 0, "brand_kits": 0, "chat_scripts": 0}


def _inc_stat(key: str) -> None:
    state_path = AI_HOME / "state" / "creator-agency-stats.json"
    stats = _load_stats()
    stats[key] = stats.get(key, 0) + 1
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(stats, indent=2))


# ── Core logic ────────────────────────────────────────────────────────────────

def content_plan(topic: str) -> str:
    """Generate a 30-day content calendar with daily post ideas."""
    result = _ai(
        f"Create a 30-day content calendar for a creator in this niche/username: '{topic}'\n"
        f"Platform: {DEFAULT_PLATFORM}\n\n"
        "Format as a table with columns: Day | Post Type | Hook/Title | Caption Angle | CTA\n"
        "Include a variety of: educational, entertaining, personal, promotional posts.\n"
        "Group by weekly themes. Days 1-7 focus on growth, 8-14 engagement, "
        "15-21 authority, 22-30 monetisation.",
        system="You are a top creator strategist who has grown accounts to 1M+ followers. "
               "Design a strategic, platform-native content calendar. Be specific with hooks "
               "and ideas, not generic. Optimise for the algorithm and audience retention.",
    )
    data = {"topic": topic, "platform": DEFAULT_PLATFORM, "calendar": result, "ts": now_iso()}
    path = _save_content(f"plan_{topic}", data)
    _inc_stat("plans")
    return f"30-Day Content Plan for '{topic}':\n\n{result}\n\n[Saved: {path.name}]"


def dm_funnel(style: str) -> str:
    """Generate a complete DM funnel sequence (opener → close)."""
    result = _ai(
        f"Create a complete DM funnel sequence in '{style}' style for a creator.\n\n"
        "Write exactly 6 messages:\n"
        "Message 1 — Opener (warm, curiosity-driven, no pitch)\n"
        "Message 2 — Rapport builder (find common ground, ask question)\n"
        "Message 3 — Value drop (share something useful/interesting)\n"
        "Message 4 — Soft offer (introduce what you offer naturally)\n"
        "Message 5 — Follow-up (handle hesitation, add social proof)\n"
        "Message 6 — Close (clear CTA, easy yes/no)\n\n"
        "For each message include: the message text, timing (e.g. 'send after 1 day'), "
        "and a note on the psychological principle used.",
        system="You are an expert DM conversion specialist for creators. Write messages that "
               "feel natural and human, not salesy. Use psychology: reciprocity, curiosity, "
               "social proof, and scarcity appropriately. Style: " + style,
    )
    data = {"style": style, "funnel": result, "ts": now_iso()}
    path = _save_content(f"dm_funnel_{style}", data)
    _inc_stat("funnels")
    return f"DM Funnel ({style} style):\n\n{result}\n\n[Saved: {path.name}]"


def upsell_script(tier: str) -> str:
    """Generate upsell scripts for a content tier."""
    result = _ai(
        f"Write upsell scripts for this content tier: '{tier}'\n\n"
        "Create 4 different upsell scripts:\n"
        "1. Story/post CTA upsell (30 words)\n"
        "2. DM upsell to existing fans (100 words)\n"
        "3. Live stream upsell pitch (60 words)\n"
        "4. Email/newsletter upsell (150 words)\n\n"
        "Also include: 3 objection-handling responses and 2 scarcity/urgency hooks.",
        system="You are an expert creator monetisation strategist. Write upsell scripts that "
               "convert without feeling pushy. Use value-first framing, social proof, and "
               "FOMO. Make it authentic to the creator voice.",
    )
    data = {"tier": tier, "scripts": result, "ts": now_iso()}
    path = _save_content(f"upsell_{tier}", data)
    _inc_stat("upsells")
    return f"Upsell Scripts — {tier}:\n\n{result}\n\n[Saved: {path.name}]"


def chat_simulation(persona: str) -> str:
    """Generate chat simulation scripts for fan engagement."""
    result = _ai(
        f"Generate chat simulation scripts for a '{persona}' creator persona.\n\n"
        "Create 10 chat scenarios with full conversation flows:\n"
        "- 3 openers from fans (how to respond to 'hey', 'love your content', compliments)\n"
        "- 3 engagement deepeners (keep conversation going, build connection)\n"
        "- 2 upsell transition scripts (natural transition to paid content)\n"
        "- 2 rejection/boundary scripts (handle rude messages professionally)\n\n"
        "For each: fan message → creator response → optional follow-up.",
        system="You are a creator engagement specialist. Write authentic-sounding chat scripts "
               "that build genuine fan relationships while protecting the creator's time. "
               f"Persona style: {persona}. Keep responses warm, brief, and engaging.",
    )
    data = {"persona": persona, "scripts": result, "ts": now_iso()}
    path = _save_content(f"chat_{persona}", data)
    _inc_stat("chat_scripts")
    return f"Chat Scripts ({persona} persona):\n\n{result}\n\n[Saved: {path.name}]"


def generate_captions(platform: str, topic: str) -> str:
    """Generate 10 engaging captions with hooks for a platform."""
    result = _ai(
        f"Write 10 high-performing {platform} captions about: {topic}\n\n"
        "For each caption provide:\n"
        "- Hook (first line — must stop the scroll)\n"
        "- Body (2-4 lines of value/story/insight)\n"
        "- CTA (platform-appropriate call to action)\n"
        "- 5 relevant hashtags\n\n"
        "Vary the formats: question, story, tip, controversial take, listicle, "
        "personal revelation, social proof, FOMO.",
        system=f"You are a viral {platform} content creator with 500K+ followers. "
               "Write captions that stop the scroll and drive engagement. "
               "Use platform-native language and formats. Every hook must be irresistible.",
    )
    data = {"platform": platform, "topic": topic, "captions": result, "ts": now_iso()}
    path = _save_content(f"captions_{platform}_{topic}", data)
    _inc_stat("captions")
    return f"Captions for {platform} — {topic}:\n\n{result}\n\n[Saved: {path.name}]"


def comment_replies(post_topic: str) -> str:
    """Generate 10 comment reply templates that drive engagement."""
    result = _ai(
        f"Generate 10 comment reply templates for a post about: {post_topic}\n\n"
        "Include replies for:\n"
        "1-2: Positive/love comments (expand and invite more)\n"
        "3-4: Question comments (answer + add value + CTA)\n"
        "5-6: Disagreement/debate comments (handle gracefully)\n"
        "7-8: 'How do I...?' comments (tease answer, drive to DM/link)\n"
        "9-10: New follower 'just found you' comments (warm welcome + hook)\n\n"
        "Each reply should feel authentic, boost engagement signal, "
        "and ideally invite another response.",
        system="You are a social media engagement expert. Write replies that feel genuine, "
               "boost algorithmic signals (replies, saves, shares), and build community. "
               "Never use generic responses.",
    )
    data = {"post_topic": post_topic, "replies": result, "ts": now_iso()}
    path = _save_content(f"comments_{post_topic}", data)
    _inc_stat("comment_sets")
    return f"Comment Replies — {post_topic}:\n\n{result}\n\n[Saved: {path.name}]"


def brand_kit(name: str, niche: str) -> str:
    """Generate a full personal brand kit."""
    result = _ai(
        f"Create a complete personal brand kit for:\n"
        f"Name/Handle: {name}\nNiche: {niche}\nPlatform: {DEFAULT_PLATFORM}\n\n"
        "Deliver:\n"
        "1. BIO (platform-optimised, 150 chars version + full 300 chars version)\n"
        "2. CONTENT PILLARS (5 pillars with description and example post idea each)\n"
        "3. TONE GUIDE (3 adjectives, what to say, what never to say, voice examples)\n"
        "4. HASHTAG STRATEGY (tier 1: 3 broad, tier 2: 7 mid, tier 3: 10 niche)\n"
        "5. MONETISATION MODEL (3 revenue streams with activation tips)\n"
        "6. POSTING SCHEDULE (optimal days/times per platform algorithm)",
        system="You are a personal brand strategist who has built 7-figure creator businesses. "
               "Create a focused, differentiated brand strategy. Be specific to the niche, "
               "not generic. Every element should serve the creator's growth goals.",
    )
    data = {"name": name, "niche": niche, "platform": DEFAULT_PLATFORM, "brand_kit": result, "ts": now_iso()}
    path = _save_content(f"brand_{name}_{niche}", data)
    _inc_stat("brand_kits")
    return f"Brand Kit — {name} ({niche}):\n\n{result}\n\n[Saved: {path.name}]"


def show_status() -> str:
    stats = _load_stats()
    return (
        f"Creator Agency Status:\n"
        f"  Content plans: {stats.get('plans', 0)}\n"
        f"  DM funnels: {stats.get('funnels', 0)}\n"
        f"  Upsell scripts: {stats.get('upsells', 0)}\n"
        f"  Caption sets: {stats.get('captions', 0)}\n"
        f"  Comment reply sets: {stats.get('comment_sets', 0)}\n"
        f"  Brand kits: {stats.get('brand_kits', 0)}\n"
        f"  Chat script sets: {stats.get('chat_scripts', 0)}\n"
        f"  Default platform: {DEFAULT_PLATFORM}"
    )


# ── Chatlog processing ────────────────────────────────────────────────────────

def process_chatlog(last_idx: int) -> int:
    chatlog = load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        if msg_lower.startswith("creator plan "):
            topic = msg[len("creator plan "):].strip()
            result = content_plan(topic) if topic else "Usage: creator plan <username|topic>"
            append_chatlog({"type": "bot", "bot": "creator-agency", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("creator dm-funnel "):
            style = msg[len("creator dm-funnel "):].strip() or "friendly"
            result = dm_funnel(style)
            append_chatlog({"type": "bot", "bot": "creator-agency", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("creator upsell "):
            tier = msg[len("creator upsell "):].strip()
            result = upsell_script(tier) if tier else "Usage: creator upsell <tier>"
            append_chatlog({"type": "bot", "bot": "creator-agency", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("creator chat "):
            persona = msg[len("creator chat "):].strip() or DEFAULT_PERSONA or "friendly"
            result = chat_simulation(persona)
            append_chatlog({"type": "bot", "bot": "creator-agency", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("creator captions "):
            rest = msg[len("creator captions "):].strip()
            parts = rest.split(maxsplit=1)
            platform = parts[0] if parts else DEFAULT_PLATFORM
            topic = parts[1] if len(parts) > 1 else "general"
            result = generate_captions(platform, topic)
            append_chatlog({"type": "bot", "bot": "creator-agency", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("creator comments "):
            post_topic = msg[len("creator comments "):].strip()
            result = comment_replies(post_topic) if post_topic else "Usage: creator comments <post_topic>"
            append_chatlog({"type": "bot", "bot": "creator-agency", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("creator brand "):
            rest = msg[len("creator brand "):].strip()
            parts = rest.split(maxsplit=1)
            name = parts[0] if parts else "creator"
            niche = parts[1] if len(parts) > 1 else "lifestyle"
            result = brand_kit(name, niche)
            append_chatlog({"type": "bot", "bot": "creator-agency", "message": result, "ts": now_iso()})

        elif msg_lower.startswith("creator status"):
            result = show_status()
            append_chatlog({"type": "bot", "bot": "creator-agency", "message": result, "ts": now_iso()})

    return new_idx


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[{now_iso()}] creator-agency started (platform={DEFAULT_PLATFORM})")
    last_idx = len(load_chatlog())
    stats = _load_stats()
    write_state({
        "bot": "creator-agency",
        "ts": now_iso(),
        "status": "starting",
        "default_platform": DEFAULT_PLATFORM,
        "total_generated": sum(stats.values()),
    })

    while True:
        try:
            last_idx = process_chatlog(last_idx)
            stats = _load_stats()
            write_state({
                "bot": "creator-agency",
                "ts": now_iso(),
                "status": "running",
                "default_platform": DEFAULT_PLATFORM,
                "stats": stats,
                "total_generated": sum(stats.values()),
            })
        except Exception as exc:
            print(f"[{now_iso()}] ERROR: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
