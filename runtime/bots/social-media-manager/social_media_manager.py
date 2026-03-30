"""Social Media Manager Bot — full-pipeline content creation and marketing.

Give it a brief and it handles everything:
  1. Brief intake — parse platform targets, tone, goals from guidelines
  2. Research phase — web-research trending topics/hashtags (via web-researcher)
  3. Content strategy — multi-platform content plan
  4. Script writing — long-form video/reel scripts where applicable
  5. Per-platform content — tailored captions, threads, posts, hooks
  6. Visual prompts — AI image/video generation prompts for each piece
  7. Hashtag strategy — researched, platform-specific hashtag sets
  8. Content package — all output saved to ~/.ai-employee/social_content/

Commands (via chat or WhatsApp):
  social <brief>            — full content creation pipeline
  content <brief>           — same as social
  create content <brief>    — same as social
  social plan <brief>       — strategy plan only (no full content)
  social status             — show recent jobs
  social history            — list saved content packages

Configuration (~/.ai-employee/config/social-media-manager.env):
  SOCIAL_MANAGER_POLL_INTERVAL  — chatlog poll seconds (default: 5)
  SOCIAL_PLATFORMS              — comma-sep target platforms (default: all)
  SOCIAL_DEFAULT_TONE           — default content tone (default: engaging)
  SOCIAL_CONTENT_DIR            — output directory (default: ~/.ai-employee/social_content)
  SOCIAL_MAX_CONTENT_JOBS       — max saved jobs (default: 50)
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "social-media-manager.state.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
RESEARCH_REQUESTS = AI_HOME / "state" / "research_requests.json"
RESEARCH_RESULTS = AI_HOME / "state" / "research_results.jsonl"

CONTENT_DIR = Path(os.environ.get("SOCIAL_CONTENT_DIR", str(AI_HOME / "social_content")))
POLL_INTERVAL = int(os.environ.get("SOCIAL_MANAGER_POLL_INTERVAL", "5"))
DEFAULT_TONE = os.environ.get("SOCIAL_DEFAULT_TONE", "engaging")
MAX_JOBS = int(os.environ.get("SOCIAL_MAX_CONTENT_JOBS", "50"))

_ALL_PLATFORMS = ["twitter", "instagram", "linkedin", "tiktok", "facebook", "youtube"]
_PLATFORM_ENV = os.environ.get("SOCIAL_PLATFORMS", "")
DEFAULT_PLATFORMS = [p.strip() for p in _PLATFORM_ENV.split(",") if p.strip()] or _ALL_PLATFORMS

# ── AI router ────────────────────────────────────────────────────────────────

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent, search_web as _search_web  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Chat log helpers ──────────────────────────────────────────────────────────

def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
        return [json.loads(l) for l in CHATLOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Research integration ──────────────────────────────────────────────────────

def request_research(query: str, context: str = "", requester: str = "social-media-manager") -> str:
    """Post a research request and return request ID."""
    req_id = f"social_{now_iso().replace(':', '-').replace('T', '_')}"
    requests = []
    if RESEARCH_REQUESTS.exists():
        try:
            requests = json.loads(RESEARCH_REQUESTS.read_text())
        except Exception:
            pass
    requests.append({
        "id": req_id,
        "query": query,
        "context": context,
        "requester": requester,
        "include_news": True,
        "status": "pending",
        "created_at": now_iso(),
    })
    RESEARCH_REQUESTS.parent.mkdir(parents=True, exist_ok=True)
    RESEARCH_REQUESTS.write_text(json.dumps(requests, indent=2))
    return req_id


def wait_for_research(req_id: str, timeout: int = 30) -> str:
    """Wait for a research request to complete and return the answer."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if RESEARCH_REQUESTS.exists():
            try:
                reqs = json.loads(RESEARCH_REQUESTS.read_text())
                for r in reqs:
                    if r.get("id") == req_id and r.get("status") == "done":
                        return r.get("result", {}).get("answer", "")
            except Exception:
                pass
        time.sleep(1)
    return ""


def quick_research(query: str, context: str = "") -> str:
    """Inline research: web search + AI synthesis without cross-bot round-trip."""
    if not _AI_AVAILABLE:
        return ""
    try:
        hits = _search_web(query, max_results=4, include_news=True)
        if not hits:
            return ""
        snippets = "\n\n".join(
            f"[{i+1}] {h.get('title','')}: {h.get('snippet','')[:250]}"
            for i, h in enumerate(hits[:4])
        )
        result = _query_ai_for_agent(
            "social-media-manager",
            f"Research topic: {query}\n\nWeb results:\n{snippets}\n\n"
            f"Summarize the key facts, trends, and insights relevant to {context or query} "
            f"for social media content creation.",
            system_prompt="You are a social media research analyst. Be concise and actionable.",
        )
        return result.get("answer", "")
    except Exception:
        return ""


# ── Brief parsing ─────────────────────────────────────────────────────────────

_PLATFORM_ALIASES = {
    "x": "twitter", "tweet": "twitter", "tweets": "twitter",
    "ig": "instagram", "insta": "instagram", "reel": "instagram", "reels": "instagram",
    "li": "linkedin",
    "tt": "tiktok", "tik tok": "tiktok",
    "fb": "facebook",
    "yt": "youtube", "shorts": "youtube",
}

_TONE_WORDS = {
    "professional", "casual", "funny", "humorous", "inspirational", "motivational",
    "educational", "informative", "entertaining", "promotional", "conversational",
    "engaging", "authoritative", "friendly", "bold", "witty", "serious",
}


def parse_brief(text: str) -> dict:
    """Extract platform targets, tone, goals, and topic from a content brief."""
    lower = text.lower()

    # Detect mentioned platforms
    platforms = []
    for alias, canonical in _PLATFORM_ALIASES.items():
        if alias in lower and canonical not in platforms:
            platforms.append(canonical)
    for p in _ALL_PLATFORMS:
        if p in lower and p not in platforms:
            platforms.append(p)
    if not platforms:
        platforms = list(DEFAULT_PLATFORMS)

    # Detect tone
    tone = DEFAULT_TONE
    for tw in _TONE_WORDS:
        if tw in lower:
            tone = tw
            break

    # Detect post count hint
    count_match = re.search(r"\b(\d+)\s+(?:posts?|pieces?|contents?|items?)", lower)
    post_count = int(count_match.group(1)) if count_match else 3

    # Topic extraction: strip command words
    topic = re.sub(
        r"^(social|content|create content|post|make|generate|write)\s+", "",
        text.strip(), flags=re.IGNORECASE,
    ).strip()
    if topic.lower().startswith("plan "):
        topic = topic[5:].strip()

    return {
        "raw_brief": text,
        "topic": topic,
        "platforms": platforms,
        "tone": tone,
        "post_count": min(max(1, post_count), 10),
    }


# ── Content generation pipeline ───────────────────────────────────────────────

def _ai(prompt: str, system: str = "") -> str:
    """Call AI router, return answer string."""
    if not _AI_AVAILABLE:
        return "[AI not available — install dependencies]"
    result = _query_ai_for_agent("social-media-manager", prompt, system_prompt=system)
    return result.get("answer", "")


def step_research(brief: dict) -> str:
    """Phase 1: Research trending topics, audience insights, competitor content."""
    topic = brief["topic"]
    print(f"[{now_iso()}] social-media-manager: researching '{topic[:50]}'")
    return quick_research(
        f"trending {topic} social media content 2025 2026",
        context=f"creating {brief['tone']} {', '.join(brief['platforms'])} content about {topic}",
    )


def step_strategy(brief: dict, research_summary: str) -> dict:
    """Phase 2: Create a multi-platform content strategy."""
    platforms_str = ", ".join(brief["platforms"])
    prompt = (
        f"Create a concise content strategy for: {brief['topic']}\n"
        f"Platforms: {platforms_str}\n"
        f"Tone: {brief['tone']}\n"
        f"Posts per platform: {brief['post_count']}\n"
        f"Research insights: {research_summary[:600] if research_summary else 'N/A'}\n\n"
        "Output a JSON object with keys:\n"
        "  content_pillars: list of 3 content pillars/themes\n"
        "  hook_strategy: one-sentence hook approach\n"
        "  cta_strategy: call-to-action approach\n"
        "  posting_cadence: recommended posting frequency\n"
        "  key_messages: list of 3 key messages to communicate\n"
        "Output ONLY valid JSON, no markdown."
    )
    raw = _ai(prompt, "You are a social media strategist. Output only valid JSON.")
    try:
        # Extract JSON from response
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else {
            "content_pillars": ["Awareness", "Engagement", "Conversion"],
            "hook_strategy": f"Start with a surprising fact about {brief['topic']}",
            "cta_strategy": "Always end with a question or clear next step",
            "posting_cadence": "3-5 posts per week",
            "key_messages": [brief["topic"], "Value", "Action"],
        }
    except (json.JSONDecodeError, AttributeError):
        return {
            "content_pillars": ["Awareness", "Engagement", "Conversion"],
            "hook_strategy": raw[:200] if raw else "",
            "key_messages": [brief["topic"]],
        }


_PLATFORM_SPECS = {
    "twitter":   {"name": "Twitter/X",   "max_chars": 280,  "format": "thread (5-7 tweets) or single tweet"},
    "instagram": {"name": "Instagram",   "max_chars": 2200, "format": "caption with line breaks + story/reel hook"},
    "linkedin":  {"name": "LinkedIn",    "max_chars": 3000, "format": "professional post with insight + call to action"},
    "tiktok":    {"name": "TikTok",      "max_chars": 2200, "format": "video hook + caption + trending sounds note"},
    "facebook":  {"name": "Facebook",    "max_chars": 63206,"format": "conversational post with question"},
    "youtube":   {"name": "YouTube",     "max_chars": 5000, "format": "video title + description + timestamps"},
}


def step_scripts(brief: dict, strategy: dict) -> dict:
    """Phase 3: Write content scripts for video-first platforms."""
    scripts = {}
    video_platforms = [p for p in brief["platforms"] if p in ("tiktok", "instagram", "youtube")]

    for platform in video_platforms:
        spec = _PLATFORM_SPECS.get(platform, {})
        prompt = (
            f"Write a {spec.get('format', 'video script')} for {spec.get('name', platform)}.\n"
            f"Topic: {brief['topic']}\n"
            f"Tone: {brief['tone']}\n"
            f"Hook strategy: {strategy.get('hook_strategy', '')}\n"
            f"Key messages: {', '.join(strategy.get('key_messages', []))}\n\n"
            f"Include: opening hook (first 3 seconds), main content, call to action.\n"
            f"Format with HOOK:, CONTENT:, CTA: labels."
        )
        scripts[platform] = _ai(
            prompt,
            f"You are an expert {spec.get('name', platform)} content creator. "
            f"Write engaging, {brief['tone']} scripts optimized for the platform algorithm."
        )

    return scripts


def step_platform_content(brief: dict, strategy: dict, scripts: dict) -> dict:
    """Phase 4: Generate final per-platform post content."""
    content = {}

    for platform in brief["platforms"]:
        spec = _PLATFORM_SPECS.get(platform, _PLATFORM_SPECS["instagram"])
        script_hint = scripts.get(platform, "")
        posts = []

        for i in range(brief["post_count"]):
            pillar = strategy.get("content_pillars", ["Awareness", "Engagement", "Conversion"])[
                i % len(strategy.get("content_pillars", ["Awareness"]))
            ]
            prompt = (
                f"Write {spec['format']} for {spec['name']}.\n"
                f"Topic: {brief['topic']}\n"
                f"Content pillar: {pillar}\n"
                f"Tone: {brief['tone']}\n"
                f"Max chars: {spec['max_chars']}\n"
                f"CTA: {strategy.get('cta_strategy', 'Engage with audience')}\n"
                + (f"Script reference:\n{script_hint[:400]}\n" if script_hint and i == 0 else "")
                + "\nWrite the complete post text only, ready to copy-paste."
            )
            post_text = _ai(
                prompt,
                f"You are an expert {spec['name']} copywriter. "
                f"Write {brief['tone']} content that maximizes engagement."
            )
            posts.append({"pillar": pillar, "text": post_text})

        content[platform] = posts

    return content


def step_hashtags(brief: dict, research_summary: str) -> dict:
    """Phase 5: Generate platform-specific hashtag sets."""
    prompt = (
        f"Generate hashtag sets for this content: {brief['topic']}\n"
        f"Tone/niche: {brief['tone']}\n"
        f"Platforms: {', '.join(brief['platforms'])}\n"
        f"Research context: {research_summary[:400] if research_summary else 'N/A'}\n\n"
        "Output a JSON object where each key is a platform name and the value is an array "
        "of 10-20 hashtags (without # prefix) sorted from most niche to broadest. "
        "Include a mix of small niche, medium, and large hashtags. "
        "Output ONLY valid JSON."
    )
    raw = _ai(prompt, "You are a hashtag research specialist. Output only valid JSON.")
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else {}
    except (json.JSONDecodeError, AttributeError):
        # Fallback: generic hashtags
        return {p: [brief["topic"].replace(" ", ""), "contentcreator", "socialmedia"]
                for p in brief["platforms"]}


def step_visual_prompts(brief: dict, content: dict) -> dict:
    """Phase 6: Generate AI image/video prompts for visual content."""
    prompts = {}
    visual_platforms = [p for p in brief["platforms"] if p in ("instagram", "tiktok", "facebook", "twitter")]

    for platform in visual_platforms:
        platform_posts = content.get(platform, [])
        post_sample = platform_posts[0]["text"][:300] if platform_posts else brief["topic"]
        prompt = (
            f"Create 3 AI image generation prompts for {platform} content about: {brief['topic']}\n"
            f"Content sample: {post_sample}\n"
            f"Tone: {brief['tone']}\n\n"
            "Each prompt should be detailed (style, lighting, composition, colors). "
            "Format as numbered list: 1. [prompt], 2. [prompt], 3. [prompt]"
        )
        prompts[platform] = _ai(
            prompt,
            "You are a visual content director specializing in social media aesthetics."
        )

    return prompts


# ── Package saving ────────────────────────────────────────────────────────────

def save_content_package(brief: dict, strategy: dict, scripts: dict,
                         content: dict, hashtags: dict, visuals: dict) -> Path:
    """Save the complete content package to a JSON file."""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    safe_topic = re.sub(r"[^a-z0-9_-]", "_", brief["topic"].lower())[:40]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = CONTENT_DIR / f"content_{safe_topic}_{ts}.json"

    package = {
        "created_at": now_iso(),
        "brief": brief,
        "strategy": strategy,
        "scripts": scripts,
        "content": content,
        "hashtags": hashtags,
        "visual_prompts": visuals,
    }
    filename.write_text(json.dumps(package, indent=2, ensure_ascii=False))
    return filename


def _format_summary(brief: dict, strategy: dict, content: dict,
                    hashtags: dict, filename: Path) -> str:
    """Format a concise chat summary of the generated content package."""
    lines = [
        "🎨 *Social Media Content Package Created!*",
        f"Topic: {brief['topic']}",
        f"Platforms: {', '.join(brief['platforms'])}",
        f"Tone: {brief['tone']}\n",
        "📋 *Strategy:*",
    ]
    for pillar in strategy.get("content_pillars", [])[:3]:
        lines.append(f"  • {pillar}")

    lines.append("\n📝 *Content Generated:*")
    total_posts = sum(len(v) for v in content.values())
    lines.append(f"  {total_posts} posts across {len(content)} platforms")

    for platform, posts in content.items():
        lines.append(f"\n*{_PLATFORM_SPECS.get(platform, {}).get('name', platform)}:*")
        if posts:
            preview = posts[0]["text"][:200].replace("\n", " ")
            lines.append(f"  Preview: {preview}...")

    if hashtags:
        lines.append(f"\n#️⃣ *Hashtags:* Generated for {', '.join(hashtags.keys())}")

    lines.append(f"\n💾 Saved to: {filename.name}")
    lines.append(f"📁 Full package: {filename}")
    return "\n".join(lines)


# ── Full pipeline ─────────────────────────────────────────────────────────────

def run_content_pipeline(brief_text: str, plan_only: bool = False) -> str:
    """Execute the full social media content creation pipeline."""
    if not _AI_AVAILABLE:
        return "❌ AI not available. Install dependencies: pip3 install requests anthropic"

    brief = parse_brief(brief_text)
    print(f"[{now_iso()}] social-media-manager: starting pipeline for '{brief['topic'][:50]}'")
    print(f"[{now_iso()}] social-media-manager: platforms={brief['platforms']}, tone={brief['tone']}")

    # Phase 1: Research
    research_summary = step_research(brief)

    # Phase 2: Strategy
    strategy = step_strategy(brief, research_summary)
    print(f"[{now_iso()}] social-media-manager: strategy done — pillars: {strategy.get('content_pillars')}")

    if plan_only:
        lines = [
            f"📋 *Content Strategy Plan: {brief['topic']}*\n",
            f"Platforms: {', '.join(brief['platforms'])}",
            f"Tone: {brief['tone']}",
            f"Posting cadence: {strategy.get('posting_cadence', '3-5x/week')}\n",
            "*Content Pillars:*",
        ]
        for p in strategy.get("content_pillars", []):
            lines.append(f"  • {p}")
        lines.append(f"\n*Hook Strategy:* {strategy.get('hook_strategy', '')}")
        lines.append(f"*CTA Strategy:* {strategy.get('cta_strategy', '')}")
        lines.append("\n*Key Messages:*")
        for m in strategy.get("key_messages", []):
            lines.append(f"  • {m}")
        if research_summary:
            lines.append(f"\n*Research Insights:*\n{research_summary[:400]}...")
        return "\n".join(lines)

    # Phase 3: Scripts (video platforms)
    scripts = step_scripts(brief, strategy)
    print(f"[{now_iso()}] social-media-manager: scripts done — {list(scripts.keys())}")

    # Phase 4: Platform content
    content = step_platform_content(brief, strategy, scripts)
    print(f"[{now_iso()}] social-media-manager: content done — {sum(len(v) for v in content.values())} posts")

    # Phase 5: Hashtags
    hashtags = step_hashtags(brief, research_summary)

    # Phase 6: Visual prompts
    visuals = step_visual_prompts(brief, content)
    print(f"[{now_iso()}] social-media-manager: visuals done — {list(visuals.keys())}")

    # Save package
    output_file = save_content_package(brief, strategy, scripts, content, hashtags, visuals)
    print(f"[{now_iso()}] social-media-manager: saved to {output_file}")

    return _format_summary(brief, strategy, content, hashtags, output_file)


# ── Process chatlog commands ──────────────────────────────────────────────────

def process_chatlog(last_idx: int) -> int:
    chatlog = load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        brief_text = None
        plan_only = False

        if msg_lower.startswith("social plan "):
            brief_text = msg[12:].strip()
            plan_only = True
        elif msg_lower.startswith("social "):
            brief_text = msg[7:].strip()
        elif msg_lower.startswith("content "):
            brief_text = msg[8:].strip()
        elif msg_lower.startswith("create content "):
            brief_text = msg[15:].strip()
        elif msg_lower.startswith("create social "):
            brief_text = msg[14:].strip()
        elif msg_lower == "social status":
            _report_status()
            continue
        elif msg_lower == "social history":
            _report_history()
            continue

        if not brief_text:
            continue

        # Acknowledge immediately
        append_chatlog({
            "ts": now_iso(), "type": "bot",
            "message": (
                f"🎨 Starting {'content strategy' if plan_only else 'full content creation'} "
                f"for: *{brief_text[:80]}*\n"
                f"This may take 30-90 seconds... I'll post the results when done."
            ),
        })

        print(f"[{now_iso()}] social-media-manager: brief='{brief_text[:60]}'")
        response = run_content_pipeline(brief_text, plan_only=plan_only)
        append_chatlog({"ts": now_iso(), "type": "bot", "message": response})
        print(f"[{now_iso()}] social-media-manager: pipeline complete")

    return new_idx


def _report_status() -> None:
    jobs = sorted(CONTENT_DIR.glob("content_*.json")) if CONTENT_DIR.exists() else []
    msg = (
        f"🎨 *Social Media Manager Status*\n"
        f"  Status: running\n"
        f"  Saved content packages: {len(jobs)}\n"
        f"  Content directory: {CONTENT_DIR}\n"
        f"  Commands:\n"
        f"    social <brief>          — full content creation\n"
        f"    social plan <brief>     — strategy plan only\n"
        f"    content <brief>         — same as social\n"
        f"    create content <brief>  — same as social\n"
        f"    social history          — list saved packages"
    )
    append_chatlog({"ts": now_iso(), "type": "bot", "message": msg})


def _report_history() -> None:
    jobs = sorted(CONTENT_DIR.glob("content_*.json"))[-10:] if CONTENT_DIR.exists() else []
    if not jobs:
        append_chatlog({"ts": now_iso(), "type": "bot",
                        "message": "No saved content packages yet. Try: social <brief>"})
        return
    lines = ["📂 *Recent Content Packages:*"]
    for j in reversed(jobs[-10:]):
        try:
            data = json.loads(j.read_text())
            brief = data.get("brief", {})
            ts = data.get("created_at", "")[:10]
            lines.append(f"  • [{ts}] {brief.get('topic', j.stem)[:50]} "
                         f"({', '.join(brief.get('platforms', []))})")
        except Exception:
            lines.append(f"  • {j.stem}")
    append_chatlog({"ts": now_iso(), "type": "bot", "message": "\n".join(lines)})


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    ai_status = "AI router active" if _AI_AVAILABLE else "AI router unavailable"
    print(
        f"[{now_iso()}] social-media-manager started; poll={POLL_INTERVAL}s; "
        f"platforms={DEFAULT_PLATFORMS}; {ai_status}"
    )
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    last_idx = len(load_chatlog())
    jobs_done = 0

    write_state({
        "bot": "social-media-manager",
        "ts": now_iso(),
        "status": "starting",
        "default_platforms": DEFAULT_PLATFORMS,
        "ai_available": _AI_AVAILABLE,
        "jobs_done": jobs_done,
    })

    while True:
        new_idx = process_chatlog(last_idx)
        if new_idx != last_idx:
            jobs_done += 1
        last_idx = new_idx

        saved_packages = len(list(CONTENT_DIR.glob("content_*.json"))) if CONTENT_DIR.exists() else 0
        write_state({
            "bot": "social-media-manager",
            "ts": now_iso(),
            "status": "running",
            "default_platforms": DEFAULT_PLATFORMS,
            "ai_available": _AI_AVAILABLE,
            "jobs_done": jobs_done,
            "saved_packages": saved_packages,
            "content_dir": str(CONTENT_DIR),
            "note": (
                "Commands: social <brief> | content <brief> | "
                "social plan <brief> | social status | social history"
            ),
        })
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
