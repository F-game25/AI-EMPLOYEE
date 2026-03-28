"""PartnershipMatchmaker Bot — JV and partnership opportunity finder.

Identifies, scores, and closes strategic partnership deals:
  - Partner scoring and fit analysis
  - Partnership pitch deck outlines
  - JV partner discovery by niche
  - Partnership outreach emails
  - Deal structuring (rev-share/affiliate/JV)
  - Active partnership pipeline tracking

Commands (via chatlog / WhatsApp / Dashboard):
  partner score <company>     — score a potential partner for fit
  partner pitch <company>     — generate partnership pitch deck outline
  partner find <niche>        — find potential JV partners in a niche
  partner email <company>     — partnership outreach email
  partner deal <type>         — structure a partnership deal
  partner status              — show active partnership pipeline

State files:
  ~/.ai-employee/state/partnership-matchmaker.state.json
  ~/.ai-employee/state/partnerships.json
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
STATE_FILE = AI_HOME / "state" / "partnership-matchmaker.state.json"
PARTNERSHIPS_FILE = AI_HOME / "state" / "partnerships.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("PARTNERSHIP_MATCHMAKER_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("partnership-matchmaker")

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


def load_partnerships() -> list:
    if not PARTNERSHIPS_FILE.exists():
        return []
    try:
        return json.loads(PARTNERSHIPS_FILE.read_text())
    except Exception:
        return []


def save_partnerships(partnerships: list) -> None:
    PARTNERSHIPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PARTNERSHIPS_FILE.write_text(json.dumps(partnerships, indent=2))


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


def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "partnership-matchmaker.queue.jsonl"
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
    logger.info("partnership-matchmaker: completed subtask '%s'", subtask_id)


SYSTEM_PROMPT = (
    "You are PartnershipMatchmaker, a strategic partnerships expert who has brokered multi-million "
    "dollar JV deals, affiliate arrangements, and co-marketing campaigns. You identify synergistic "
    "partners, craft compelling pitches, structure win-win deals, and negotiate terms that create "
    "lasting value. You know how to find partners who have your audience and make them an offer "
    "they can't refuse."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_score(company: str) -> str:
    partnerships = load_partnerships()
    result = ai_query(
        f"Score this company as a potential partner: {company}\n\n"
        "## Partner Fit Score (0–100)\n"
        "| Dimension | Weight | Score | Weighted Score |\n"
        "|-----------|--------|-------|----------------|\n"
        "Audience overlap | 25% | [/10] | [calc]\n"
        "Complementary offering | 25% | [/10] | [calc]\n"
        "Revenue potential | 20% | [/10] | [calc]\n"
        "Brand alignment | 15% | [/10] | [calc]\n"
        "Reachability/access | 15% | [/10] | [calc]\n"
        "**Total Score**: [/100] — [Hot / Warm / Cold]\n\n"
        "## Synergy Analysis\n"
        "Specific reasons this partnership creates value for both sides\n\n"
        "## Revenue Potential\n"
        "Estimated revenue from this partnership over 12 months\n\n"
        "## Partnership Types to Propose\n"
        "Ranked by ease of execution and value:\n"
        "1. [type] — [rationale]\n"
        "2. [type] — [rationale]\n"
        "3. [type] — [rationale]\n\n"
        "## Decision-Maker\n"
        "Who to contact and how to reach them\n\n"
        "## Conversation Starter\n"
        "How to open the partnership conversation",
        SYSTEM_PROMPT,
    )
    partnership_entry = {
        "id": str(uuid.uuid4())[:8],
        "company": company,
        "created_at": now_iso(),
        "status": "scored",
    }
    partnerships.insert(0, partnership_entry)
    save_partnerships(partnerships[:100])
    return result


def cmd_pitch(company: str) -> str:
    return ai_query(
        f"Generate a partnership pitch deck outline for: {company}\n\n"
        "## Pitch Deck Structure (10 slides)\n\n"
        "**Slide 1 — The Opportunity**\n"
        "[what we're building together]\n\n"
        "**Slide 2 — Their Audience, Our Solution**\n"
        "[how our product serves their customers better]\n\n"
        "**Slide 3 — Mutual Revenue Upside**\n"
        "[specific numbers and projections]\n\n"
        "**Slide 4 — Partnership Model**\n"
        "[exactly how it works]\n\n"
        "**Slide 5 — Case Study / Social Proof**\n"
        "[similar partnership that worked]\n\n"
        "**Slide 6 — Revenue Share / Deal Terms**\n"
        "[proposed economics]\n\n"
        "**Slide 7 — Integration / Technical Requirements**\n"
        "[what's needed to execute]\n\n"
        "**Slide 8 — Go-to-Market Timeline**\n"
        "[launch plan]\n\n"
        "**Slide 9 — Success Metrics**\n"
        "[how we measure success together]\n\n"
        "**Slide 10 — Next Steps**\n"
        "[clear ask and proposed timeline]\n\n"
        "## Executive Summary\n"
        "One-paragraph summary for initial outreach\n\n"
        "## Anticipated Objections\n"
        "Top 5 objections and responses",
        SYSTEM_PROMPT,
    )


def cmd_find(niche: str) -> str:
    return ai_query(
        f"Find potential JV partners in niche: {niche}\n\n"
        "## Partner Categories\n"
        "5 types of companies that serve the same audience:\n"
        "1. [category] — why they're good partners\n"
        "2. [category] — why they're good partners\n"
        "...\n\n"
        "## 20 Specific Partner Candidates (Simulated)\n"
        "| Company | Audience Size | Partnership Type | Revenue Potential | Approach |\n"
        "|---------|--------------|-----------------|------------------|----------|\n"
        "[fill 20 rows with realistic companies]\n\n"
        "## Where to Find More Partners\n"
        "- Directories and marketplaces\n"
        "- Industry events and conferences\n"
        "- LinkedIn search strings\n"
        "- Podcasts and communities\n\n"
        "## Quick-Win Partners\n"
        "Top 3 easiest partnerships to close in <30 days\n\n"
        "## Big-Bet Partners\n"
        "Top 2 transformational partnerships worth pursuing\n\n"
        "## Partnership Outreach Sequence\n"
        "How to systematically approach and close 5 partners per month",
        SYSTEM_PROMPT,
    )


def cmd_email(company: str) -> str:
    return ai_query(
        f"Write partnership outreach emails for: {company}\n\n"
        "## Cold Email (Variant A — Direct)\n"
        "Subject: [subject]\n\n"
        "[Full email body — specific, personalized, value-first]\n\n"
        "---\n\n"
        "## Cold Email (Variant B — Referral Frame)\n"
        "Subject: [subject]\n\n"
        "[Full email body — positioned as being introduced]\n\n"
        "---\n\n"
        "## LinkedIn Message (300 chars)\n"
        "[Connection note or DM]\n\n"
        "## Follow-Up Email (Day 5)\n"
        "[Brief follow-up with a different angle]\n\n"
        "## Follow-Up Email (Day 12)\n"
        "[Final follow-up with social proof or urgency]\n\n"
        "## Subject Line Options (10)\n"
        "Ranked by open rate potential\n\n"
        "## Personalization Guide\n"
        "How to customize for each specific company",
        SYSTEM_PROMPT,
    )


def cmd_deal(deal_type: str) -> str:
    partnerships = load_partnerships()
    result = ai_query(
        f"Structure a {deal_type} partnership deal\n\n"
        "## Deal Structure Overview\n"
        f"Type: {deal_type}\n"
        "Standard terms for this deal type in the market\n\n"
        "## Economic Model\n"
        "- Revenue share split: [recommend % with rationale]\n"
        "- Payment trigger: [what event triggers payment]\n"
        "- Payment timing: [net 30/60, etc.]\n"
        "- Minimum guarantees: [if applicable]\n"
        "- Performance bonuses: [if applicable]\n\n"
        "## Term Sheet Template\n"
        "Key clauses to include:\n"
        "1. Definitions\n"
        "2. Revenue share formula\n"
        "3. Tracking and attribution\n"
        "4. Payment terms\n"
        "5. IP ownership\n"
        "6. Exclusivity (yes/no/limited)\n"
        "7. Term and termination\n"
        "8. Dispute resolution\n\n"
        "## Negotiation Guide\n"
        "What to concede vs. hold firm on\n\n"
        "## Red Flags\n"
        "Deal terms that indicate a bad partner\n\n"
        "## Success Metrics\n"
        "KPIs for this deal type",
        SYSTEM_PROMPT,
    )
    deal_entry = {
        "id": str(uuid.uuid4())[:8],
        "type": deal_type,
        "created_at": now_iso(),
        "status": "structuring",
    }
    partnerships.insert(0, deal_entry)
    save_partnerships(partnerships[:100])
    return result


def cmd_status() -> str:
    partnerships = load_partnerships()
    if not partnerships:
        return "No partnerships tracked yet. Try: `partner find <niche>`"
    lines = ["🤝 *PartnershipMatchmaker — Pipeline:*"]
    lines.append(f"  Total partnerships: {len(partnerships)}")
    active = sum(1 for p in partnerships if p.get("status") == "active")
    lines.append(f"  Active: {active} | In pipeline: {len(partnerships) - active}")
    lines.append("\n*Recent partnerships:*")
    for p in partnerships[:5]:
        name = p.get("company", p.get("type", p.get("niche", "?")))
        lines.append(f"  • `{p.get('id','?')}` — {str(name)[:50]} ({p.get('status','?')})")
    return "\n".join(lines)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("partner ") and msg_lower != "partner":
        return None

    rest = msg[8:].strip() if msg_lower.startswith("partner ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("score "):
        return cmd_score(rest[6:].strip())
    if rest_lower.startswith("pitch "):
        return cmd_pitch(rest[6:].strip())
    if rest_lower.startswith("find "):
        return cmd_find(rest[5:].strip())
    if rest_lower.startswith("email "):
        return cmd_email(rest[6:].strip())
    if rest_lower.startswith("deal "):
        return cmd_deal(rest[5:].strip())
    if rest_lower == "status":
        return cmd_status()
    if rest_lower == "help" or not rest_lower:
        return (
            "🤝 *PartnershipMatchmaker Commands:*\n"
            "  `partner score <company>` — partner fit score\n"
            "  `partner pitch <company>` — pitch deck outline\n"
            "  `partner find <niche>` — find JV partners\n"
            "  `partner email <company>` — partnership outreach email\n"
            "  `partner deal <type>` — structure a deal (rev-share/affiliate/jv)\n"
            "  `partner status` — active partnership pipeline"
        )

    return "Unknown partner command. Try `partner help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] partnership-matchmaker started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "partnership-matchmaker",
                    "message": response,
                })
                logger.info("partnership-matchmaker: handled command: %s", message[:60])

        partnerships = load_partnerships()
        write_state({
            "bot": "partnership-matchmaker",
            "ts": now_iso(),
            "status": "running",
            "total_partnerships": len(partnerships),
            "active_partnerships": sum(1 for p in partnerships if p.get("status") == "active"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
