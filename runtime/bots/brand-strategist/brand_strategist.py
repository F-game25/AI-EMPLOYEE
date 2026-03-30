"""Brand Strategist Bot — Brand naming, identity, positioning, and messaging.

Creates complete brand identities and strategic positioning:
  - Brand naming and domain research
  - Brand positioning strategy
  - Visual identity brief (colors, fonts, logo direction)
  - Brand voice and tone guidelines
  - Messaging frameworks and taglines
  - Competitive brand analysis
  - Rebranding strategy
  - Brand architecture for multi-product companies
  - Brand story and narrative

Commands (via chatlog / WhatsApp / Dashboard):
  brand name <industry> <keywords>  — generate brand name ideas
  brand identity <company>          — full brand identity system
  brand position <company> <market> — positioning strategy
  brand voice <company>             — brand voice & tone guide
  brand messaging <company>         — messaging framework
  brand story <company> <mission>   — brand story and narrative
  brand audit <company>             — brand audit and gaps
  brand compete <company>           — competitive brand analysis
  brand launch <company>            — brand launch plan
  brand refresh <company>           — rebranding strategy
  brand status                      — current brand projects

State files:
  ~/.ai-employee/state/brand-strategist.state.json
  ~/.ai-employee/state/brand-projects.json
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
STATE_FILE = AI_HOME / "state" / "brand-strategist.state.json"
PROJECTS_FILE = AI_HOME / "state" / "brand-projects.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("BRAND_STRATEGIST_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("brand-strategist")

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


def load_projects() -> list:
    if not PROJECTS_FILE.exists():
        return []
    try:
        return json.loads(PROJECTS_FILE.read_text())
    except Exception:
        return []


def save_projects(projects: list) -> None:
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2))


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
        result = _query_ai_for_agent("brand-strategist", prompt, system_prompt=system_prompt)
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


SYSTEM_BRAND = (
    "You are a world-class Brand Strategist who has built iconic brands at top agencies "
    "and as an in-house CMO. You create brand identities that are distinctive, memorable, "
    "and commercially effective. You balance creativity with strategic rigor. "
    "Your work is specific, actionable, and immediately useful."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_name(industry: str, keywords: str = "") -> str:
    kw_text = f" with keywords/themes: {keywords}" if keywords else ""
    return ai_query(
        f"Generate 15 brand name ideas for a {industry} company{kw_text}.\n\n"
        "For each name provide:\n"
        "- **Name**: [name]\n"
        "- **Pronunciation**: [phonetic]\n"
        "- **Meaning/Etymology**: what it means or where it comes from\n"
        "- **Brand Story**: 1-sentence story behind the name\n"
        "- **Domain Check**: likely availability as .com, .io, .co\n"
        "- **Trademark Risk**: high/medium/low with reason\n"
        "- **Strengths**: why this name works\n"
        "- **Weaknesses**: potential issues\n\n"
        "Categories to cover:\n"
        "- 3 invented/portmanteau words (unique, ownable)\n"
        "- 3 metaphor-based names (evocative)\n"
        "- 3 descriptor-based names (clear, direct)\n"
        "- 3 founder/place names (authentic)\n"
        "- 3 abstract/emotive names (feeling-based)\n\n"
        "End with TOP 3 recommendations with full rationale.",
        SYSTEM_BRAND,
    )


def cmd_identity(company: str) -> str:
    result = ai_query(
        f"Create a complete brand identity system for: {company}\n\n"
        "## Brand Foundation\n"
        "- Mission statement (1 sentence)\n"
        "- Vision statement (1 sentence)\n"
        "- Core values (5, each with 1-line description)\n"
        "- Brand personality (5 adjectives + explanation)\n\n"
        "## Visual Identity Brief\n"
        "**Logo Direction**:\n"
        "- Logo concept (3 options with descriptions)\n"
        "- Logo usage rules (minimum size, clear space)\n\n"
        "**Color Palette**:\n"
        "- Primary color: [name, hex code, why this color]\n"
        "- Secondary color: [name, hex code, purpose]\n"
        "- Accent color: [name, hex code, usage]\n"
        "- Neutral colors: [list]\n"
        "- Color psychology explanation\n\n"
        "**Typography**:\n"
        "- Display font: [name, where to get it]\n"
        "- Body font: [name, where to get it]\n"
        "- When to use each\n\n"
        "**Photography Style**: description of visual aesthetic\n"
        "**Iconography Style**: line icons vs filled, style guide\n\n"
        "## Brand Application\n"
        "How the identity applies to: website, social media, business cards, packaging\n\n"
        "## Brand Don'ts\n"
        "5 things never to do with the brand",
        SYSTEM_BRAND,
    )
    projects = load_projects()
    projects.insert(0, {"id": str(uuid.uuid4())[:8], "company": company, "created_at": now_iso(), "type": "identity"})
    save_projects(projects[:20])
    return result


def cmd_position(company: str, market: str) -> str:
    return ai_query(
        f"Develop brand positioning strategy for {company} in the {market} market.\n\n"
        "## Market Analysis\n"
        "- Market positioning map (describe key players on 2 axes)\n"
        "- White space opportunities\n"
        "- Target segment definition\n\n"
        "## Positioning Statement\n"
        "Format: 'For [target], [company] is the [category] that [benefit] because [reason to believe]'\n"
        "3 positioning options ranked by strength\n\n"
        "## Competitive Differentiation\n"
        "- Points of Difference (what you own)\n"
        "- Points of Parity (table stakes)\n"
        "- Points to Avoid (competitor traps)\n\n"
        "## Positioning in Practice\n"
        "How positioning shows up in: messaging, product, pricing, channels\n\n"
        "## Proof Points\n"
        "Evidence that makes the positioning credible\n\n"
        "## Perceptual Map\n"
        "Text description of where the brand sits vs competitors on key dimensions",
        SYSTEM_BRAND,
    )


def cmd_voice(company: str) -> str:
    return ai_query(
        f"Create a brand voice and tone guide for: {company}\n\n"
        "## Brand Voice\n"
        "The brand's character in communication — who is it?\n\n"
        "## Voice Dimensions (4 key traits)\n"
        "For each trait:\n"
        "- We are [trait] / We are not [opposite]\n"
        "- In practice: [example phrases]\n"
        "- In practice NOT: [phrases to avoid]\n\n"
        "## Tone Variations\n"
        "How tone shifts in different contexts:\n"
        "- Customer support: [guidance]\n"
        "- Social media: [guidance]\n"
        "- Marketing copy: [guidance]\n"
        "- Press releases: [guidance]\n"
        "- Error messages: [guidance]\n\n"
        "## Writing Principles\n"
        "5 rules for all brand writing\n\n"
        "## Word List\n"
        "- Words we love and use\n"
        "- Words we never use\n"
        "- Industry jargon to avoid\n\n"
        "## Before/After Examples\n"
        "5 examples: weak version → brand-right version",
        SYSTEM_BRAND,
    )


def cmd_messaging(company: str) -> str:
    return ai_query(
        f"Create a messaging framework for: {company}\n\n"
        "## Core Message Architecture\n"
        "**Brand Tagline** (3 options):\n"
        "**Brand Promise** (1 sentence):\n"
        "**Elevator Pitch** (30 seconds):\n"
        "**One-liner** (tweet length):\n\n"
        "## Audience-Specific Messages\n"
        "For each key audience (3 audiences):\n"
        "- Primary pain point addressed\n"
        "- Key benefit message\n"
        "- Proof point\n"
        "- Call to action\n\n"
        "## Feature → Benefit → Emotional Payoff\n"
        "For top 5 features/offerings:\n"
        "[Feature] → [Functional Benefit] → [Emotional Payoff]\n\n"
        "## Objection Responses\n"
        "Top 5 objections + brand-right responses\n\n"
        "## Message Hierarchy\n"
        "Primary → Secondary → Supporting messages\n\n"
        "## Channel-Specific Adaptations\n"
        "How to adapt the message for: website hero, LinkedIn, email subject lines, paid ads",
        SYSTEM_BRAND,
    )


def cmd_story(company: str, mission: str = "") -> str:
    mission_text = f" Mission: {mission}" if mission else ""
    return ai_query(
        f"Create the brand story for: {company}{mission_text}\n\n"
        "## The Origin Story\n"
        "Why does this company exist? What problem sparked it? "
        "The authentic human story behind the brand.\n\n"
        "## The Hero's Journey\n"
        "Who is the customer? What's their struggle?\n"
        "How does the brand help them win?\n\n"
        "## The Villain\n"
        "What are you fighting against? (The status quo, an industry problem)\n\n"
        "## The Vision\n"
        "What world are you trying to create?\n\n"
        "## About Us Page Copy\n"
        "400-word version ready to publish\n\n"
        "## Short Brand Story (100 words)\n"
        "For social media bio / pitch decks\n\n"
        "## Brand Narrative for Investors\n"
        "150-word version for fundraising contexts",
        SYSTEM_BRAND,
    )


def cmd_compete(company: str) -> str:
    return ai_query(
        f"Conduct a competitive brand analysis for: {company}\n\n"
        "## Competitive Brand Landscape\n"
        "Map 5-7 main brand competitors:\n"
        "- Positioning\n"
        "- Visual identity style\n"
        "- Voice and tone\n"
        "- Key messages\n"
        "- Perceived strengths\n\n"
        "## Brand Differentiation Opportunities\n"
        "Where can {company} stand out?\n\n"
        "## Competitive Brand Threats\n"
        "Which competitor brands could steal perception?\n\n"
        "## Category Clichés to Avoid\n"
        "Overused visual/messaging patterns in this category\n\n"
        "## Distinctive Asset Analysis\n"
        "Which category distinctive assets are taken vs available\n"
        "(colors, shapes, characters, sounds, words)\n\n"
        "## Strategic Recommendation\n"
        "How to build a brand that wins in this competitive landscape",
        SYSTEM_BRAND,
    )


def cmd_launch(company: str) -> str:
    return ai_query(
        f"Create a brand launch plan for: {company}\n\n"
        "## Pre-Launch (8 weeks before)\n"
        "- Brand system finalization checklist\n"
        "- Internal brand rollout\n"
        "- Asset production list\n\n"
        "## Soft Launch (4 weeks before)\n"
        "- Social media account setup\n"
        "- Website brand application\n"
        "- Teaser campaign\n\n"
        "## Launch Day\n"
        "- Hour-by-hour PR and social plan\n"
        "- Press release template\n"
        "- Influencer activation\n\n"
        "## Post-Launch (first 90 days)\n"
        "- Brand building content calendar\n"
        "- PR and media strategy\n"
        "- Community building tactics\n\n"
        "## Brand Tracking\n"
        "- Metrics to measure brand awareness and perception\n"
        "- Monthly brand review process",
        SYSTEM_BRAND,
    )


def cmd_audit(company: str) -> str:
    return ai_query(
        f"Conduct a brand audit for: {company}\n\n"
        "## Brand Audit Framework\n"
        "Evaluate across 6 dimensions (score 1-10):\n\n"
        "1. **Brand Clarity** — is the brand easily understood?\n"
        "2. **Brand Consistency** — applied consistently across touchpoints?\n"
        "3. **Brand Distinctiveness** — stands out from competitors?\n"
        "4. **Brand Relevance** — relevant to target audience today?\n"
        "5. **Brand Trust** — credible and trustworthy signals?\n"
        "6. **Brand Experience** — do customers feel the brand promise?\n\n"
        "## Touchpoint Audit\n"
        "Rate each touchpoint: website, social, email, packaging, ads, customer service\n\n"
        "## Top 3 Brand Strengths\n\n"
        "## Top 3 Brand Gaps\n\n"
        "## Priority Actions\n"
        "5 specific improvements in order of impact vs effort\n\n"
        "## Overall Brand Health Score\n"
        "0-100 with breakdown",
        SYSTEM_BRAND,
    )


def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "brand-strategist.queue.jsonl"
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
    result = ai_query(instructions, SYSTEM_BRAND)
    write_orchestrator_result(subtask_id, result)
    logger.info("brand-strategist: completed subtask '%s'", subtask_id)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("brand ") and msg_lower != "brand":
        return None

    rest = msg[6:].strip() if msg_lower.startswith("brand ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("name "):
        parts = rest[5:].strip().split(" keywords:", 1)
        industry = parts[0].strip()
        keywords = parts[1].strip() if len(parts) > 1 else ""
        return cmd_name(industry, keywords)
    if rest_lower.startswith("identity "):
        return cmd_identity(rest[9:].strip())
    if rest_lower.startswith("position "):
        parts = rest[9:].strip().split(" in ", 1)
        company = parts[0].strip()
        market = parts[1].strip() if len(parts) > 1 else "general market"
        return cmd_position(company, market)
    if rest_lower.startswith("voice "):
        return cmd_voice(rest[6:].strip())
    if rest_lower.startswith("messaging "):
        return cmd_messaging(rest[10:].strip())
    if rest_lower.startswith("story "):
        parts = rest[6:].strip().split(" mission:", 1)
        company = parts[0].strip()
        mission = parts[1].strip() if len(parts) > 1 else ""
        return cmd_story(company, mission)
    if rest_lower.startswith("audit "):
        return cmd_audit(rest[6:].strip())
    if rest_lower.startswith("compete "):
        return cmd_compete(rest[8:].strip())
    if rest_lower.startswith("launch "):
        return cmd_launch(rest[7:].strip())
    if rest_lower.startswith("refresh "):
        return ai_query(
            f"Create a rebranding strategy for: {rest[8:].strip()}\n\n"
            "When to rebrand, what to keep, what to change, rollout plan.",
            SYSTEM_BRAND,
        )
    if rest_lower == "status":
        projects = load_projects()
        if not projects:
            return "No brand projects yet. Try: `brand identity <company>`"
        lines = ["🎨 *Brand Projects:*"]
        for p in projects[:5]:
            lines.append(f"  • `{p['id']}` — {p.get('company','?')[:50]} ({p.get('type','?')})")
        return "\n".join(lines)
    if rest_lower == "help" or not rest_lower:
        return (
            "🎨 *Brand Strategist Commands:*\n"
            "  `brand name <industry>` — generate name ideas\n"
            "  `brand identity <company>` — full brand identity\n"
            "  `brand position <company> in <market>` — positioning\n"
            "  `brand voice <company>` — voice & tone guide\n"
            "  `brand messaging <company>` — messaging framework\n"
            "  `brand story <company>` — brand narrative\n"
            "  `brand audit <company>` — brand health audit\n"
            "  `brand compete <company>` — competitive analysis\n"
            "  `brand launch <company>` — brand launch plan\n"
            "  `brand refresh <company>` — rebranding strategy"
        )

    return "Unknown brand command. Try `brand help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] brand-strategist started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "brand-strategist",
                    "message": response,
                })
                logger.info("brand-strategist: handled command: %s", message[:60])

        projects = load_projects()
        write_state({
            "bot": "brand-strategist",
            "ts": now_iso(),
            "status": "running",
            "total_projects": len(projects),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
