"""LinkedInGrowthHacker Bot — LinkedIn profile optimizer and growth specialist.

Drives LinkedIn audience growth and B2B pipeline through systematic strategies:
  - Profile optimization for search and conversion
  - Viral content creation and scheduling
  - Targeted connection campaigns
  - Viral hook ideation for posts
  - Personalized DM templates by niche
  - Full profile audits
  - Connection campaign stats tracking

Commands (via chatlog / WhatsApp / Dashboard):
  linkedin optimize <profile_url>      — profile optimization recommendations
  linkedin content <topic>             — viral content post for LinkedIn
  linkedin campaign <target_audience>  — connection campaign strategy
  linkedin hook <topic>                — viral hook ideas for posts
  linkedin dms <niche>                 — connection message templates
  linkedin audit <profile_url>         — full profile audit
  linkedin status                      — show connection campaign stats

State files:
  ~/.ai-employee/state/linkedin-growth-hacker.state.json
  ~/.ai-employee/state/linkedin-content.json
"""
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "linkedin-growth-hacker.state.json"
CONTENT_FILE = AI_HOME / "state" / "linkedin-content.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("LINKEDIN_GROWTH_HACKER_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("linkedin-growth-hacker")

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_content() -> list:
    if not CONTENT_FILE.exists():
        return []
    try:
        return json.loads(CONTENT_FILE.read_text())
    except Exception:
        return []


def save_content(content: list) -> None:
    CONTENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTENT_FILE.write_text(json.dumps(content, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    entries = []
    try:
        for line in CHATLOG.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except Exception:
        pass
    return entries


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def ai_query(prompt: str, system_prompt: str = "") -> str:
    if not _AI_AVAILABLE:
        return "AI router not available."
    try:
        result = _query_ai_for_agent("linkedin-growth-hacker", prompt, system_prompt=system_prompt)
        return result.get("answer", "No response generated.")
    except Exception as exc:
        return f"AI query failed: {exc}"


def write_orchestrator_result(subtask_id: str, result_text: str, status: str = "done") -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"{subtask_id}.json"
    result_file.write_text(json.dumps({
        "subtask_id": subtask_id,
        "status": status,
        "result": result_text,
        "completed_at": now_iso(),
    }))


def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "linkedin-growth-hacker.queue.jsonl"
    if not queue_file.exists():
        return []
    lines = queue_file.read_text().splitlines()
    pending = []
    for line in lines:
        if line.strip():
            try:
                pending.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if pending:
        queue_file.write_text("")
    return pending


def process_subtask(subtask: dict) -> None:
    subtask_id = subtask.get("subtask_id", "")
    instructions = subtask.get("instructions", "")
    result = ai_query(instructions, SYSTEM_PROMPT)
    write_orchestrator_result(subtask_id, result)
    logger.info("linkedin-growth-hacker: completed subtask '%s'", subtask_id)


SYSTEM_PROMPT = (
    "You are LinkedInGrowthHacker, a LinkedIn growth expert who has helped hundreds of B2B founders "
    "and consultants go from 0 to 10,000+ followers and generate qualified pipeline from LinkedIn. "
    "You know the algorithm, write viral posts, optimize profiles for search, and run systematic "
    "connection campaigns that convert."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_optimize(profile_url: str) -> str:
    return ai_query(
        f"Provide LinkedIn profile optimization recommendations for: {profile_url}\n\n"
        "## Profile Completeness Score\n"
        "Score each section 1-10 and overall score\n\n"
        "## Headline Optimization\n"
        "Current vs. optimized headline (3 variants)\n"
        "Formula: [Role] who helps [ICP] achieve [outcome] without [pain]\n\n"
        "## About Section Rewrite\n"
        "Full rewrite using storytelling framework:\n"
        "Hook → Problem → Journey → Solution → Social Proof → CTA\n\n"
        "## Featured Section\n"
        "What to feature and how to structure for maximum conversions\n\n"
        "## Experience Section\n"
        "How to rewrite each role for keywords and impact\n\n"
        "## Keywords to Add\n"
        "20 high-search keywords to weave into the profile\n\n"
        "## Profile Photo and Banner\n"
        "Recommendations for visual elements\n\n"
        "## Creator Mode Settings\n"
        "Which topics to select and why\n\n"
        "## Expected Results\n"
        "Projected increase in profile views and connection requests",
        SYSTEM_PROMPT,
    )


def cmd_content(topic: str) -> str:
    content = load_content()
    result = ai_query(
        f"Write a viral LinkedIn post about: {topic}\n\n"
        "## Post #1 — Story Format\n"
        "[Hook line — stops the scroll]\n\n"
        "[3-5 short paragraphs with line breaks]\n\n"
        "[Insight or lesson]\n\n"
        "[CTA question to drive comments]\n\n"
        "---\n\n"
        "## Post #2 — List Format\n"
        "[Counterintuitive hook]\n\n"
        "Here's what actually works:\n\n"
        "1. [Point]\n"
        "2. [Point]\n"
        "...\n\n"
        "[Closing insight]\n\n"
        "[CTA]\n\n"
        "---\n\n"
        "## Post #3 — Hot Take Format\n"
        "[Controversial opener]\n\n"
        "[Argument]\n\n"
        "[Proof]\n\n"
        "[CTA]\n\n"
        "## Best Posting Time\n"
        "When to post for maximum reach\n\n"
        "## Hashtags\n"
        "5 hashtags per post\n\n"
        "## Comment Strategy\n"
        "How to respond to comments to boost the algorithm",
        SYSTEM_PROMPT,
    )
    content_entry = {
        "id": str(uuid.uuid4())[:8],
        "topic": topic,
        "created_at": now_iso(),
        "status": "draft",
    }
    content.insert(0, content_entry)
    save_content(content[:100])
    return result


def cmd_campaign(target_audience: str) -> str:
    return ai_query(
        f"Design a LinkedIn connection campaign strategy for: {target_audience}\n\n"
        "## Target Audience Profile\n"
        "- Job titles to target\n"
        "- Industries and company sizes\n"
        "- LinkedIn search filters to use\n"
        "- Boolean search strings\n\n"
        "## Daily Connection Plan\n"
        "- Connections per day (safe limits)\n"
        "- Best time to send requests\n"
        "- Profile warm-up sequence\n\n"
        "## Connection Request Notes\n"
        "5 templates for connection requests (300 chars max)\n\n"
        "## Welcome Message Sequence\n"
        "Message 1 (day 0): [after connect]\n"
        "Message 2 (day 3): [value add]\n"
        "Message 3 (day 7): [soft CTA]\n\n"
        "## Content Strategy During Campaign\n"
        "Post topics that resonate with target audience\n\n"
        "## 30-Day Growth Target\n"
        "Projected connections, followers, and leads\n\n"
        "## Safety Guidelines\n"
        "How to avoid LinkedIn restrictions and account flags",
        SYSTEM_PROMPT,
    )


def cmd_hook(topic: str) -> str:
    return ai_query(
        f"Generate 20 viral hook ideas for LinkedIn posts about: {topic}\n\n"
        "## Hook Categories\n\n"
        "**Curiosity Hooks (5):**\n"
        "[hooks that create an open loop]\n\n"
        "**Contrarian Hooks (5):**\n"
        "[hooks that challenge conventional wisdom]\n\n"
        "**Story Hooks (5):**\n"
        "[hooks that start mid-story]\n\n"
        "**Number Hooks (5):**\n"
        "[hooks with specific numbers/data]\n\n"
        "## Hook Formulas That Work\n"
        "10 fill-in-the-blank hook templates\n\n"
        "## Top 3 Highest-Potential Hooks\n"
        "Why each will perform well for this topic\n\n"
        "## Hook Testing Strategy\n"
        "How to A/B test hooks across posts",
        SYSTEM_PROMPT,
    )


def cmd_dms(niche: str) -> str:
    return ai_query(
        f"Create LinkedIn connection message and DM templates for niche: {niche}\n\n"
        "## Connection Request Notes (10 templates)\n"
        "Under 300 characters, personalized, no pitch\n\n"
        "## Welcome DM Sequence (5 templates)\n"
        "For each:\n"
        "- When to send (trigger)\n"
        "- Personalization hook\n"
        "- Value-first message\n"
        "- Soft conversation starter\n\n"
        "## Nurture Messages (5 templates)\n"
        "After initial connection, over 7-14 days\n\n"
        "## Soft CTA Message\n"
        "How to transition from conversation to meeting (3 variants)\n\n"
        "## Voice Note Script\n"
        "30-second voice note template for premium prospects\n\n"
        "## Personalization Guide\n"
        "How to customize each template at scale\n\n"
        "## What NOT to Do\n"
        "10 DM mistakes that kill reply rates",
        SYSTEM_PROMPT,
    )


def cmd_audit(profile_url: str) -> str:
    return ai_query(
        f"Conduct a full LinkedIn profile audit for: {profile_url}\n\n"
        "## Audit Score (0–100)\n"
        "Category breakdown:\n"
        "- SEO/Discoverability (0–20)\n"
        "- Profile Completeness (0–20)\n"
        "- Conversion Optimization (0–20)\n"
        "- Content Strategy (0–20)\n"
        "- Network Quality (0–20)\n"
        "**Total**: [score] — Grade: [A/B/C/D/F]\n\n"
        "## Critical Issues (fix immediately)\n"
        "Top 3 problems costing the most opportunities\n\n"
        "## Quick Wins (fix this week)\n"
        "5 changes that take <30 minutes each\n\n"
        "## Strategic Improvements (30-day plan)\n"
        "Deeper changes requiring more effort\n\n"
        "## Competitive Benchmark\n"
        "How this profile compares to top performers in the niche\n\n"
        "## 90-Day Growth Projection\n"
        "Expected results if all recommendations are implemented",
        SYSTEM_PROMPT,
    )


def cmd_status() -> str:
    content = load_content()
    if not content:
        return "No LinkedIn content created yet. Try: `linkedin content <topic>`"
    lines = ["💼 *LinkedInGrowthHacker — Stats:*"]
    lines.append(f"  Content pieces created: {len(content)}")
    published = sum(1 for c in content if c.get("status") == "published")
    lines.append(f"  Published: {published} | Drafts: {len(content) - published}")
    lines.append("\n*Recent content:*")
    for c in content[:5]:
        lines.append(f"  • `{c.get('id','?')}` — {c.get('topic','?')[:50]} ({c.get('status','?')})")
    return "\n".join(lines)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("linkedin ") and msg_lower != "linkedin":
        return None

    rest = msg[9:].strip() if msg_lower.startswith("linkedin ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("optimize "):
        return cmd_optimize(rest[9:].strip())
    if rest_lower.startswith("content "):
        return cmd_content(rest[8:].strip())
    if rest_lower.startswith("campaign "):
        return cmd_campaign(rest[9:].strip())
    if rest_lower.startswith("hook "):
        return cmd_hook(rest[5:].strip())
    if rest_lower.startswith("dms "):
        return cmd_dms(rest[4:].strip())
    if rest_lower.startswith("audit "):
        return cmd_audit(rest[6:].strip())
    if rest_lower == "status":
        return cmd_status()
    if rest_lower == "help" or not rest_lower:
        return (
            "💼 *LinkedInGrowthHacker Commands:*\n"
            "  `linkedin optimize <profile_url>` — profile optimization\n"
            "  `linkedin content <topic>` — viral content post\n"
            "  `linkedin campaign <target_audience>` — connection campaign\n"
            "  `linkedin hook <topic>` — viral hook ideas\n"
            "  `linkedin dms <niche>` — connection message templates\n"
            "  `linkedin audit <profile_url>` — full profile audit\n"
            "  `linkedin status` — connection campaign stats"
        )

    return "Unknown linkedin command. Try `linkedin help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] linkedin-growth-hacker started; poll_interval={POLL_INTERVAL}s; {ai_status}")

    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)

    last_processed_idx = len(load_chatlog())

    while True:
        for subtask in check_agent_queue():
            process_subtask(subtask)

        chatlog = load_chatlog()
        new_entries = chatlog[last_processed_idx:]
        last_processed_idx = len(chatlog)

        for entry in new_entries:
            if entry.get("type") != "user":
                continue
            message = entry.get("message", "").strip()
            if not message:
                continue
            response = handle_command(message)
            if response:
                append_chatlog({
                    "ts": now_iso(),
                    "type": "bot",
                    "bot": "linkedin-growth-hacker",
                    "message": response,
                })
                logger.info("linkedin-growth-hacker: handled command: %s", message[:60])

        content = load_content()
        write_state({
            "bot": "linkedin-growth-hacker",
            "ts": now_iso(),
            "status": "running",
            "total_content": len(content),
            "published_content": sum(1 for c in content if c.get("status") == "published"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
