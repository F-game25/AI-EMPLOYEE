"""Memecoin Creator Bot — Full memecoin & token launch from concept to community.

Generates everything needed to ideate, design, and launch a memecoin or crypto token:
  - Token concept and name generation
  - Tokenomics design with distribution model
  - Whitepaper drafting
  - Community strategy and viral launch plan
  - Social media content and hashtag sets
  - Roadmap generation
  - Smart contract parameters
  - Marketing campaign briefs

Commands (via chatlog / WhatsApp / Dashboard):
  memecoin create <concept>        — full memecoin launch package
  memecoin name <theme>            — generate token name ideas
  memecoin tokenomics <name>       — design tokenomics model
  memecoin whitepaper <name>       — draft whitepaper
  memecoin community <name>        — community growth strategy
  memecoin roadmap <name>          — project roadmap
  memecoin social <name>           — social media content pack
  memecoin viral <name>            — viral launch campaign
  memecoin contract <name>         — smart contract parameters
  memecoin status                  — current projects

State files:
  ~/.ai-employee/state/memecoin-creator.state.json
  ~/.ai-employee/state/memecoin-projects.json
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
STATE_FILE = AI_HOME / "state" / "memecoin-creator.state.json"
PROJECTS_FILE = AI_HOME / "state" / "memecoin-projects.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("MEMECOIN_CREATOR_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("memecoin-creator")

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai as _query_ai  # type: ignore
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
        result = _query_ai(prompt, system_prompt=system_prompt)
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


# ── Command Handlers ──────────────────────────────────────────────────────────

SYSTEM_CRYPTO = (
    "You are a crypto and Web3 expert with deep experience in tokenomics, DeFi, "
    "meme culture, and viral marketing. You understand both technical blockchain mechanics "
    "and the cultural dynamics that drive meme coin success. "
    "Be creative, specific, and realistic about both potential and risks."
)


def cmd_name(theme: str) -> str:
    return ai_query(
        f"Generate 10 creative memecoin/token names for the theme: {theme}\n\n"
        "For each name provide:\n"
        "- Token name and ticker symbol (3-5 letters)\n"
        "- Concept explanation (1-2 sentences)\n"
        "- Viral potential (why would people share this?)\n"
        "- Domain availability likely? (.com, .io)\n"
        "- Meme angle — what's the hook?\n\n"
        "Rank them 1-10 from most to least viral potential.",
        SYSTEM_CRYPTO,
    )


def cmd_tokenomics(name: str) -> str:
    return ai_query(
        f"Design a complete tokenomics model for: {name}\n\n"
        "Include:\n"
        "## Token Basics\n"
        "- Total supply (with justification)\n"
        "- Token standard (ERC-20, BEP-20, SPL, etc.)\n"
        "- Decimals\n\n"
        "## Distribution Model\n"
        "- Liquidity pool: X%\n"
        "- Community/airdrop: X%\n"
        "- Team/dev (vested): X%\n"
        "- Marketing: X%\n"
        "- CEX listings reserve: X%\n"
        "- Burn mechanism: describe\n\n"
        "## Launch Mechanics\n"
        "- Initial price and market cap target\n"
        "- Liquidity lock duration\n"
        "- Anti-whale measures\n"
        "- Tax structure (buy/sell tax if any)\n\n"
        "## Vesting Schedule\n"
        "- Team tokens vesting cliff and schedule\n\n"
        "## Deflationary Mechanics\n"
        "- Burn events, buybacks, or staking rewards\n\n"
        "Make it attractive to investors while being sustainable.",
        SYSTEM_CRYPTO,
    )


def cmd_whitepaper(name: str) -> str:
    return ai_query(
        f"Write a comprehensive whitepaper draft for the token/coin: {name}\n\n"
        "Structure:\n"
        "# {name} Whitepaper\n\n"
        "## Abstract (200 words)\n"
        "## 1. Introduction — Problem & Vision\n"
        "## 2. The {name} Ecosystem\n"
        "## 3. Tokenomics\n"
        "## 4. Technical Architecture\n"
        "## 5. Use Cases & Utility\n"
        "## 6. Roadmap\n"
        "## 7. Team & Advisors\n"
        "## 8. Community & Governance\n"
        "## 9. Marketing Strategy\n"
        "## 10. Legal Disclaimer\n\n"
        "Write in a professional yet accessible tone. "
        "Include realistic technical details and viral narrative hooks.",
        SYSTEM_CRYPTO,
    )


def cmd_community(name: str) -> str:
    return ai_query(
        f"Design a complete community growth strategy for {name} token/coin.\n\n"
        "Include:\n"
        "## Platform Strategy\n"
        "- Telegram: setup guide, bot commands, community rules\n"
        "- Discord: server structure, roles, channels\n"
        "- Twitter/X: content strategy, engagement tactics\n"
        "- TikTok: viral video concepts\n"
        "- Reddit: subreddit strategy\n\n"
        "## Community Roles\n"
        "- Roles hierarchy (mods, shillers, holders tiers)\n"
        "- Incentive structures for active members\n\n"
        "## Launch Events\n"
        "- Pre-launch hype building (2 weeks before)\n"
        "- Launch day activities\n"
        "- Post-launch retention\n\n"
        "## Influencer Strategy\n"
        "- Types of influencers to target\n"
        "- Approach and compensation models\n\n"
        "## Meme Strategy\n"
        "- Core meme concepts and formats\n"
        "- Meme creation incentives for community\n"
        "- Viral loop mechanics",
        SYSTEM_CRYPTO,
    )


def cmd_roadmap(name: str) -> str:
    return ai_query(
        f"Create a realistic 12-month roadmap for {name} token/coin.\n\n"
        "Format by quarters:\n\n"
        "**Q1 — Launch & Foundation**\n"
        "- Week 1-2: Pre-launch\n"
        "- Week 3-4: Launch\n"
        "- Month 2-3: Growth\n"
        "Key milestones: [list specific, measurable milestones]\n\n"
        "**Q2 — Traction & Listings**\n"
        "[milestones, listing targets, partnerships]\n\n"
        "**Q3 — Ecosystem Expansion**\n"
        "[utility additions, cross-chain, major partnerships]\n\n"
        "**Q4 — Scale & Sustainability**\n"
        "[CEX listings, ecosystem maturity, DAO governance]\n\n"
        "For each milestone: success metric and responsible party.\n"
        "Be realistic about timelines and what's achievable.",
        SYSTEM_CRYPTO,
    )


def cmd_social(name: str) -> str:
    return ai_query(
        f"Create a complete social media content pack for {name} token.\n\n"
        "Deliver:\n"
        "## Twitter/X Content (20 tweets)\n"
        "- 5 announcement-style tweets\n"
        "- 5 community engagement tweets\n"
        "- 5 educational/utility tweets\n"
        "- 5 hype/viral tweets\n\n"
        "## Telegram Announcements (5)\n"
        "- Launch announcement\n"
        "- Milestone celebration\n"
        "- Community update\n"
        "- Listing announcement\n"
        "- AMA promotion\n\n"
        "## Hashtag Sets\n"
        "- Primary hashtags (10)\n"
        "- Secondary hashtags (15)\n"
        "- Niche hashtags (10)\n\n"
        "## TikTok Video Concepts (5)\n"
        "- Script hooks and main message\n\n"
        "Make content viral, engaging, and authentic to meme culture.",
        SYSTEM_CRYPTO,
    )


def cmd_viral(name: str) -> str:
    return ai_query(
        f"Design a viral launch campaign for {name} token.\n\n"
        "Include:\n"
        "## Pre-Launch Hype (14 days before)\n"
        "- Mystery teaser campaign\n"
        "- Whitelist/early access mechanics\n"
        "- Countdown activities\n\n"
        "## Launch Day Blitz\n"
        "- Hour-by-hour action plan\n"
        "- Coordinated posting schedule\n"
        "- Community activation tactics\n\n"
        "## Viral Mechanics\n"
        "- Referral/airdrop programs\n"
        "- Share-to-earn mechanics\n"
        "- Meme contests with prizes\n\n"
        "## Influencer Activation Plan\n"
        "- Micro (1K-10K): how many, what to ask\n"
        "- Mid-tier (10K-100K): approach\n"
        "- Macro (100K+): strategy\n\n"
        "## Viral Content Formats\n"
        "- Top 5 meme templates to create\n"
        "- Video formats that go viral in crypto\n"
        "- Twitter Spaces / AMA topics\n\n"
        "## Growth Metrics\n"
        "- Day 1, Week 1, Month 1 targets\n"
        "- Holder milestones and celebrations\n",
        SYSTEM_CRYPTO,
    )


def cmd_contract(name: str) -> str:
    return ai_query(
        f"Provide smart contract parameters and security checklist for {name} token.\n\n"
        "Include:\n"
        "## Recommended Contract Parameters\n"
        "- Token standard recommendation with reasons\n"
        "- Ownership: renounce vs multisig (recommendation + why)\n"
        "- Mint function: include or not\n"
        "- Pause function: include or not\n"
        "- Max wallet size: recommended %\n"
        "- Max transaction size: recommended %\n"
        "- Liquidity lock: platform + duration recommendation\n\n"
        "## Security Checklist\n"
        "- Audit: what to audit, top audit firms\n"
        "- KYC: should team doxx? pros/cons\n"
        "- Rug-pull prevention measures\n"
        "- Anti-bot measures on launch\n\n"
        "## Deployment Steps\n"
        "- Step-by-step on Ethereum / BSC / Solana\n"
        "- Gas optimization tips\n"
        "- Verification on Etherscan/BSCScan\n\n"
        "## Red Flags to Avoid\n"
        "- Common contract vulnerabilities\n"
        "- Legal risks to be aware of\n\n"
        "Note: This is educational information only, not financial or legal advice.",
        SYSTEM_CRYPTO,
    )


def cmd_create(concept: str) -> str:
    """Full memecoin creation package."""
    system = (
        "You are a veteran crypto launcher who has successfully launched multiple tokens. "
        "Create a comprehensive, launch-ready memecoin package with everything needed "
        "to go from idea to community launch."
    )
    result = ai_query(
        f"Create a complete memecoin launch package for the concept: {concept}\n\n"
        "Deliver a full package:\n\n"
        "## 1. TOKEN IDENTITY\n"
        "- 3 name options with tickers\n"
        "- Recommended choice with rationale\n"
        "- Logo concept description\n"
        "- Color palette and visual identity\n\n"
        "## 2. TOKENOMICS SUMMARY\n"
        "- Total supply recommendation\n"
        "- Distribution breakdown\n"
        "- Launch price target\n"
        "- Market cap trajectory\n\n"
        "## 3. NARRATIVE & MEME HOOK\n"
        "- Core story (why does this exist?)\n"
        "- Meme angle that will go viral\n"
        "- Tagline and battle cry\n\n"
        "## 4. LAUNCH STRATEGY (30 days)\n"
        "- Week 1-2: build\n"
        "- Week 3: launch\n"
        "- Week 4: grow\n\n"
        "## 5. COMMUNITY PLAN\n"
        "- Platform priorities\n"
        "- First 1000 holder strategy\n"
        "- Viral mechanics\n\n"
        "## 6. QUICK-WIN TACTICS\n"
        "- 5 specific actions to take in the first 48 hours after launch\n\n"
        "Be creative, specific, and viral-minded.",
        system,
    )

    projects = load_projects()
    project = {
        "id": str(uuid.uuid4())[:8],
        "concept": concept,
        "created_at": now_iso(),
        "status": "created",
    }
    projects.insert(0, project)
    projects = projects[:20]
    save_projects(projects)

    return result


# ── Orchestrator subtask handler ──────────────────────────────────────────────

def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "memecoin-creator.queue.jsonl"
    if not queue_file.exists():
        return []
    lines = queue_file.read_text().splitlines()
    pending = [json.loads(l) for l in lines if l.strip()]
    if pending:
        queue_file.write_text("")
    return pending


def process_subtask(subtask: dict) -> None:
    subtask_id = subtask.get("subtask_id", "")
    instructions = subtask.get("instructions", "")
    result = ai_query(instructions, SYSTEM_CRYPTO)
    write_orchestrator_result(subtask_id, result)
    logger.info("memecoin-creator: completed subtask '%s'", subtask_id)


# ── Main command dispatch ─────────────────────────────────────────────────────

def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("memecoin ") and msg_lower != "memecoin":
        return None

    rest = msg[9:].strip() if msg_lower.startswith("memecoin ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("create "):
        return cmd_create(rest[7:].strip())
    if rest_lower.startswith("name "):
        return cmd_name(rest[5:].strip())
    if rest_lower.startswith("tokenomics "):
        return cmd_tokenomics(rest[11:].strip())
    if rest_lower.startswith("whitepaper "):
        return cmd_whitepaper(rest[11:].strip())
    if rest_lower.startswith("community "):
        return cmd_community(rest[10:].strip())
    if rest_lower.startswith("roadmap "):
        return cmd_roadmap(rest[8:].strip())
    if rest_lower.startswith("social "):
        return cmd_social(rest[7:].strip())
    if rest_lower.startswith("viral "):
        return cmd_viral(rest[6:].strip())
    if rest_lower.startswith("contract "):
        return cmd_contract(rest[9:].strip())
    if rest_lower == "status":
        projects = load_projects()
        if not projects:
            return "No memecoin projects yet. Try: `memecoin create <concept>`"
        lines = ["🪙 *Memecoin Projects:*"]
        for p in projects[:5]:
            lines.append(f"  • `{p['id']}` — {p.get('concept','?')[:50]}")
        return "\n".join(lines)
    if rest_lower == "help" or not rest_lower:
        return (
            "🪙 *Memecoin Creator Commands:*\n"
            "  `memecoin create <concept>` — full launch package\n"
            "  `memecoin name <theme>` — generate name ideas\n"
            "  `memecoin tokenomics <name>` — design tokenomics\n"
            "  `memecoin whitepaper <name>` — draft whitepaper\n"
            "  `memecoin community <name>` — community strategy\n"
            "  `memecoin roadmap <name>` — project roadmap\n"
            "  `memecoin social <name>` — social media pack\n"
            "  `memecoin viral <name>` — viral campaign\n"
            "  `memecoin contract <name>` — smart contract guide"
        )

    return "Unknown memecoin command. Try `memecoin help`"


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] memecoin-creator started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "memecoin-creator",
                    "message": response,
                })
                logger.info("memecoin-creator: handled command: %s", message[:60])

        projects = load_projects()
        write_state({
            "bot": "memecoin-creator",
            "ts": now_iso(),
            "status": "running",
            "total_projects": len(projects),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
