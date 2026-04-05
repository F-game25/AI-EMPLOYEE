"""LeadHunterElite Bot — B2B lead generation specialist.

Drives top-of-funnel pipeline through precision prospecting and enrichment:
  - B2B lead scraping from public sources
  - ICP-based qualification scoring
  - CRM enrichment for decision-makers
  - Outreach script generation per niche
  - Full lead hunt pipelines
  - Lead statistics and CRM reporting

Commands (via chatlog / WhatsApp / Dashboard):
  leadelite scrape <niche> <location>   — scrape B2B leads from public sources
  leadelite qualify <company>           — qualification scoring for a company
  leadelite enrich <lead_id>            — CRM enrichment for a lead
  leadelite outreach <niche>            — generate outreach script for a niche
  leadelite hunt <goal>                 — full lead hunt pipeline
  leadelite status                      — show lead hunt stats

State files:
  ~/.ai-employee/state/lead-hunter-elite.state.json
  ~/.ai-employee/state/leads-elite-crm.json
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
STATE_FILE = AI_HOME / "state" / "lead-hunter-elite.state.json"
CRM_FILE = AI_HOME / "state" / "leads-elite-crm.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("LEAD_HUNTER_ELITE_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("lead-hunter-elite")

_ai_router_path = AI_HOME / "agents" / "ai-router"
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


def load_crm() -> list:
    if not CRM_FILE.exists():
        return []
    try:
        return json.loads(CRM_FILE.read_text())
    except Exception:
        return []


def save_crm(leads: list) -> None:
    CRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRM_FILE.write_text(json.dumps(leads, indent=2))


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
        result = _query_ai_for_agent("lead-hunter-elite", prompt, system_prompt=system_prompt)
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
    queue_file = AGENT_TASKS_DIR / "lead-hunter-elite.queue.jsonl"
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
    logger.info("lead-hunter-elite: completed subtask '%s'", subtask_id)


def notify_agent(agent_id: str, instructions: str) -> None:
    """Write a subtask to another agent's queue file."""
    queue_file = AGENT_TASKS_DIR / f"{agent_id}.queue.jsonl"
    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(queue_file, "a") as f:
        f.write(json.dumps({
            "subtask_id": str(uuid.uuid4())[:8],
            "from": "lead-hunter-elite",
            "instructions": instructions,
        }) + "\n")



SYSTEM_PROMPT = (
    "You are LeadHunterElite, a world-class B2B lead generation specialist with 10+ years of "
    "experience in prospecting, qualification, and CRM enrichment. You excel at finding "
    "decision-makers, scoring leads by ICP match, and crafting compelling outreach that opens "
    "doors. Be precise, data-driven, and always provide actionable lead intel."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_scrape(niche: str, location: str) -> str:
    return ai_query(
        f"Generate a B2B lead scraping strategy for niche: {niche} in location: {location}\n\n"
        "## Target Profile (ICP)\n"
        "Define ideal company size, revenue range, industry sub-verticals, tech stack signals\n\n"
        "## Public Data Sources\n"
        "List 10 free/public sources to find leads (LinkedIn, Crunchbase, Product Hunt, G2, etc.)\n"
        "For each: URL pattern, data available, how to extract\n\n"
        "## Decision-Maker Titles\n"
        "Top 8 job titles to target with LinkedIn search strings\n\n"
        "## 25 Sample Leads (Simulated)\n"
        "| Company | Size | Location | Decision-Maker Title | Signal | Score |\n"
        "|---------|------|----------|---------------------|--------|-------|\n"
        "[fill 25 rows with realistic data]\n\n"
        "## Scraping Workflow\n"
        "Step-by-step process to build a list of 500 leads in 48 hours\n\n"
        "## Tools Recommended\n"
        "Free and paid tools with specific use cases",
        SYSTEM_PROMPT,
    )


def cmd_qualify(company: str) -> str:
    return ai_query(
        f"Score and qualify this company as a B2B lead: {company}\n\n"
        "## ICP Match Score (0–100)\n"
        "Breakdown by dimension:\n"
        "- Company size fit (0–20): [score + reasoning]\n"
        "- Industry fit (0–20): [score + reasoning]\n"
        "- Tech stack fit (0–20): [score + reasoning]\n"
        "- Budget signals (0–20): [score + reasoning]\n"
        "- Timing/trigger signals (0–20): [score + reasoning]\n"
        "**Total Score**: [sum] — [Hot / Warm / Cold]\n\n"
        "## Decision-Maker Map\n"
        "Who to contact, their likely pain points, and how to reach them\n\n"
        "## Buying Signals\n"
        "Recent signals that suggest they are in-market\n\n"
        "## Recommended Approach\n"
        "Personalized first touch message for this specific company\n\n"
        "## Disqualifiers\n"
        "Reasons this lead might NOT be a good fit",
        SYSTEM_PROMPT,
    )


def cmd_enrich(lead_id: str) -> str:
    crm = load_crm()
    result = ai_query(
        f"Enrich this B2B lead for CRM entry. Lead ID: {lead_id}\n\n"
        "## Data Enrichment Checklist\n"
        "Fields to research and populate:\n"
        "- Company: legal name, DBA, website, LinkedIn URL\n"
        "- Firmographics: founded, HQ, employee count, revenue estimate\n"
        "- Tech stack: top 10 tools detected (BuiltWith/Wappalyzer signals)\n"
        "- Funding: latest round, total raised, investors\n"
        "- Decision-Makers: name, title, LinkedIn, email pattern, phone\n"
        "- Recent News: last 3 press mentions or announcements\n\n"
        "## CRM Record (JSON format)\n"
        "Provide a complete JSON object ready to import\n\n"
        "## Personalization Intel\n"
        "3 highly specific talking points for outreach based on enriched data\n\n"
        "## Next Actions\n"
        "Recommended sequence of touches with timing",
        SYSTEM_PROMPT,
    )
    enriched = {
        "id": lead_id,
        "enriched_at": now_iso(),
        "status": "enriched",
    }
    crm = [e for e in crm if e.get("id") != lead_id]
    crm.insert(0, enriched)
    save_crm(crm[:200])
    # Notify email-ninja agent about the enriched lead
    notify_agent("email-ninja", f"Enriched lead {lead_id} is ready. Draft a personalized cold email.")
    return result


def cmd_outreach(niche: str) -> str:
    result = ai_query(
        f"Generate a cold outreach script for niche: {niche}\n\n"
        "## Subject Lines (10 options)\n"
        "A/B testable, curiosity-driven, <50 chars each\n\n"
        "## Email Body (3 variants)\n"
        "For each:\n"
        "- Hook (1 sentence, hyper-personalized)\n"
        "- Problem statement (1-2 sentences)\n"
        "- Value proposition (1-2 sentences)\n"
        "- Proof point (1 sentence)\n"
        "- CTA (1 sentence, low friction)\n"
        "- P.S. line\n\n"
        "## LinkedIn Message (150 chars)\n"
        "Connection request note for {niche} decision-makers\n\n"
        "## Follow-Up Sequence\n"
        "Days 3, 7, 14 follow-up messages (email + LinkedIn)\n\n"
        "## Personalization Variables\n"
        "{{first_name}}, {{company}}, {{trigger}} — how to fill each at scale\n\n"
        "## Response Rate Benchmarks\n"
        "Expected open rates, reply rates, and meeting conversion",
        SYSTEM_PROMPT,
    )
    # Notify lead-generator agent
    notify_agent("lead-generator", f"Outreach script ready for niche: {niche}. Generate additional leads.")
    return result


def cmd_hunt(goal: str) -> str:
    crm = load_crm()
    result = ai_query(
        f"Execute a full lead hunt pipeline for goal: {goal}\n\n"
        "## Phase 1 — ICP Definition\n"
        "Define exact ICP with 10 qualifying criteria\n\n"
        "## Phase 2 — Lead Sourcing\n"
        "Sources, search strings, and expected yield (aim for 200+ leads)\n\n"
        "## Phase 3 — Qualification\n"
        "Scoring matrix and threshold for 'hot' vs 'warm' vs 'cold'\n\n"
        "## Phase 4 — Enrichment\n"
        "Which fields to enrich and tools to use\n\n"
        "## Phase 5 — Outreach Sequencing\n"
        "Multi-channel sequence: email → LinkedIn → call\n"
        "Day-by-day touchpoint plan for 30 days\n\n"
        "## Phase 6 — Tracking\n"
        "CRM fields, pipeline stages, and reporting cadence\n\n"
        "## Expected Outcomes\n"
        "Conversion funnel estimates: leads → replies → demos → deals\n\n"
        "## 7-Day Action Plan\n"
        "Daily tasks to launch this hunt immediately",
        SYSTEM_PROMPT,
    )
    hunt_entry = {
        "id": str(uuid.uuid4())[:8],
        "goal": goal,
        "created_at": now_iso(),
        "status": "active",
    }
    crm.insert(0, hunt_entry)
    save_crm(crm[:200])
    return result


def cmd_status() -> str:
    crm = load_crm()
    if not crm:
        return "No leads in CRM yet. Try: `leadelite hunt <goal>`"
    lines = ["🎯 *LeadHunterElite — CRM Status:*"]
    lines.append(f"  Total records: {len(crm)}")
    enriched = sum(1 for e in crm if e.get("status") == "enriched")
    active = sum(1 for e in crm if e.get("status") == "active")
    lines.append(f"  Enriched: {enriched} | Active hunts: {active}")
    lines.append("\n*Recent entries:*")
    for e in crm[:5]:
        lines.append(f"  • `{e.get('id','?')}` — {str(e.get('goal', e.get('id', '?')))[:50]} ({e.get('status','?')})")
    return "\n".join(lines)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("leadelite ") and msg_lower != "leadelite":
        return None

    rest = msg[10:].strip() if msg_lower.startswith("leadelite ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("scrape "):
        parts = rest[7:].strip().split(None, 1)
        niche = parts[0] if parts else "general"
        location = parts[1] if len(parts) > 1 else "global"
        return cmd_scrape(niche, location)
    if rest_lower.startswith("qualify "):
        return cmd_qualify(rest[8:].strip())
    if rest_lower.startswith("enrich "):
        return cmd_enrich(rest[7:].strip())
    if rest_lower.startswith("outreach "):
        return cmd_outreach(rest[9:].strip())
    if rest_lower.startswith("hunt "):
        return cmd_hunt(rest[5:].strip())
    if rest_lower == "status":
        return cmd_status()
    if rest_lower == "help" or not rest_lower:
        return (
            "🎯 *LeadHunterElite Commands:*\n"
            "  `leadelite scrape <niche> <location>` — scrape B2B leads\n"
            "  `leadelite qualify <company>` — qualification scoring\n"
            "  `leadelite enrich <lead_id>` — CRM enrichment\n"
            "  `leadelite outreach <niche>` — outreach script\n"
            "  `leadelite hunt <goal>` — full lead hunt pipeline\n"
            "  `leadelite status` — lead hunt stats"
        )

    return "Unknown leadelite command. Try `leadelite help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] lead-hunter-elite started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "lead-hunter-elite",
                    "message": response,
                })
                logger.info("lead-hunter-elite: handled command: %s", message[:60])

        crm = load_crm()
        write_state({
            "bot": "lead-hunter-elite",
            "ts": now_iso(),
            "status": "running",
            "total_leads": len(crm),
            "enriched_leads": sum(1 for e in crm if e.get("status") == "enriched"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
