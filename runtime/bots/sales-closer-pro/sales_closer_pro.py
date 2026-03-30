"""SalesCloserPro Bot — Negotiation and deal closing specialist.

Masters every stage of B2B sales to maximize close rates:
  - Objection handling with empathy and logic
  - Negotiation tactics for complex deals
  - Word-for-word closing scripts
  - Stage-specific sales scripts (discovery/demo/close)
  - Active pipeline management and recommendations
  - Won/lost deal analytics

Commands (via chatlog / WhatsApp / Dashboard):
  closer objection <objection>    — handle a specific sales objection
  closer negotiate <context>      — negotiation tactics for a deal
  closer close <deal_context>     — closing script for a deal
  closer script <stage>           — sales script for a stage
  closer pipeline                 — show active deals and recommended actions
  closer status                   — stats on deals won/lost

State files:
  ~/.ai-employee/state/sales-closer-pro.state.json
  ~/.ai-employee/state/deals.json
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
STATE_FILE = AI_HOME / "state" / "sales-closer-pro.state.json"
DEALS_FILE = AI_HOME / "state" / "deals.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("SALES_CLOSER_PRO_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("sales-closer-pro")

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


def load_deals() -> list:
    if not DEALS_FILE.exists():
        return []
    try:
        return json.loads(DEALS_FILE.read_text())
    except Exception:
        return []


def save_deals(deals: list) -> None:
    DEALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEALS_FILE.write_text(json.dumps(deals, indent=2))


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
        result = _query_ai_for_agent("sales-closer-pro", prompt, system_prompt=system_prompt)
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
    queue_file = AGENT_TASKS_DIR / "sales-closer-pro.queue.jsonl"
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
    logger.info("sales-closer-pro: completed subtask '%s'", subtask_id)


SYSTEM_PROMPT = (
    "You are SalesCloserPro, an elite sales closer with expertise in B2B SaaS, services, and "
    "high-ticket sales. You master SPIN selling, Challenger Sale, and MEDDIC frameworks. You "
    "handle every objection with empathy and logic, turn 'no' into 'yes', and create urgency "
    "without being pushy. Provide exact scripts, word-for-word, that sales reps can use immediately."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_objection(objection: str) -> str:
    return ai_query(
        f"Handle this sales objection with expert precision: \"{objection}\"\n\n"
        "## Objection Classification\n"
        "Type: [price / timing / authority / need / trust / competition]\n"
        "Real concern beneath the objection: [what they really mean]\n\n"
        "## 3 Response Frameworks\n\n"
        "**Framework 1 — Feel/Felt/Found:**\n"
        "[exact word-for-word script]\n\n"
        "**Framework 2 — Reframe:**\n"
        "[exact word-for-word script]\n\n"
        "**Framework 3 — Question back:**\n"
        "[exact word-for-word script]\n\n"
        "## Best Response (recommended)\n"
        "[exact script with tone notes]\n\n"
        "## Follow-Up Question\n"
        "The one question to ask after handling the objection\n\n"
        "## If They Repeat the Objection\n"
        "What to do when they say it again\n\n"
        "## Red Flags\n"
        "Signs this is a dealbreaker vs. a real buying signal",
        SYSTEM_PROMPT,
    )


def cmd_negotiate(context: str) -> str:
    return ai_query(
        f"Provide negotiation tactics for this deal context: {context}\n\n"
        "## Negotiation Position Assessment\n"
        "- Your leverage points: [list]\n"
        "- Their leverage points: [list]\n"
        "- Power balance: [who has more leverage and why]\n\n"
        "## BATNA Analysis\n"
        "Best Alternative To Negotiated Agreement for both sides\n\n"
        "## Opening Stance\n"
        "Where to anchor and why (specific numbers/terms)\n\n"
        "## Concession Strategy\n"
        "What to give up, in what order, and what to get in return\n"
        "- Never concede without getting something back (reciprocity)\n"
        "- Concessions to offer: [list with perceived vs. real value]\n\n"
        "## Specific Scripts\n"
        "Word-for-word for: opening, counter-offer, final offer, walkaway\n\n"
        "## Pressure Tactics to Expect\n"
        "Common buyer tactics and exactly how to respond\n\n"
        "## Deal Structure Options\n"
        "3 deal structures that protect margin while appearing flexible\n\n"
        "## Walk-Away Point\n"
        "Criteria and exact language for walking away",
        SYSTEM_PROMPT,
    )


def cmd_close(deal_context: str) -> str:
    deals = load_deals()
    result = ai_query(
        f"Write a closing script for this deal: {deal_context}\n\n"
        "## Deal Readiness Assessment\n"
        "MEDDIC score: Metrics / Economic Buyer / Decision Criteria / Decision Process / "
        "Identify Pain / Champion — score each 1-5\n\n"
        "## Closing Technique Selection\n"
        "Best technique for this deal type:\n"
        "[Assumptive / Summary / Urgency / Alternative / Trial / Puppy-dog close]\n"
        "Why this technique fits\n\n"
        "## Closing Script (word-for-word)\n"
        "[Full closing script including setup, transition, close, and silence]\n\n"
        "## Handling 'I Need to Think About It'\n"
        "[Exact response to the most common stall]\n\n"
        "## Creating Urgency (Without Pressure)\n"
        "3 legitimate urgency drivers specific to this deal\n\n"
        "## Post-Close Actions\n"
        "Immediate next steps after they say yes (prevent buyer's remorse)\n\n"
        "## If They Say No\n"
        "How to gracefully exit and set up future re-engagement",
        SYSTEM_PROMPT,
    )
    deal_entry = {
        "id": str(uuid.uuid4())[:8],
        "context": deal_context[:100],
        "created_at": now_iso(),
        "status": "closing",
    }
    deals.insert(0, deal_entry)
    save_deals(deals[:100])
    return result


def cmd_script(stage: str) -> str:
    return ai_query(
        f"Write a complete sales script for the '{stage}' stage\n\n"
        "## Script Overview\n"
        f"Stage: {stage} | Duration: [ideal call length] | Goal: [outcome]\n\n"
        "## Pre-Call Preparation\n"
        "5 things to research/know before the call\n\n"
        "## Opening (first 60 seconds)\n"
        "[exact word-for-word opener that builds rapport and sets agenda]\n\n"
        "## Main Script\n"
        "[full script with:\n"
        "- Transition phrases between sections\n"
        "- Questions to ask (SPIN/Challenger framework)\n"
        "- Active listening prompts\n"
        "- Value delivery moments\n"
        "- Mini-commitments to build momentum]\n\n"
        "## Common Derails and Recoveries\n"
        "5 scenarios where the call goes off-script + exact recoveries\n\n"
        "## Closing the Call\n"
        "How to end with a clear next step and commitment\n\n"
        "## Follow-Up Email\n"
        "Template to send within 30 minutes of the call",
        SYSTEM_PROMPT,
    )


def cmd_pipeline() -> str:
    deals = load_deals()
    if not deals:
        return "No deals in pipeline yet. Try: `closer close <deal_context>`"
    result = ai_query(
        f"Analyze this sales pipeline and recommend actions:\n"
        f"Active deals: {len(deals)}\n"
        f"Stages: {[d.get('status') for d in deals[:10]]}\n\n"
        "## Pipeline Health Assessment\n"
        "- Deals at each stage\n"
        "- Pipeline velocity (avg days per stage)\n"
        "- Biggest bottleneck stage\n\n"
        "## Priority Deals\n"
        "Top 3 deals to focus on this week with specific actions\n\n"
        "## At-Risk Deals\n"
        "Deals showing stall signals and rescue tactics\n\n"
        "## Pipeline Gap\n"
        "If current pipeline won't hit quota, what to do\n\n"
        "## Weekly Action Plan\n"
        "Day-by-day plan for maximum pipeline movement",
        SYSTEM_PROMPT,
    )
    return result


def cmd_status() -> str:
    deals = load_deals()
    if not deals:
        return "No deals tracked yet. Try: `closer close <deal_context>`"
    won = sum(1 for d in deals if d.get("status") == "won")
    lost = sum(1 for d in deals if d.get("status") == "lost")
    active = sum(1 for d in deals if d.get("status") not in ("won", "lost"))
    lines = ["💼 *SalesCloserPro — Deal Stats:*"]
    lines.append(f"  Total deals: {len(deals)} | Won: {won} | Lost: {lost} | Active: {active}")
    closed = won + lost
    if closed > 0:
        win_rate = round(won / closed * 100, 1)
        lines.append(f"  Win rate: {win_rate}% (of closed deals)")
    lines.append("\n*Recent deals:*")
    for d in deals[:5]:
        lines.append(f"  • `{d.get('id','?')}` — {d.get('context','?')[:50]} ({d.get('status','?')})")
    return "\n".join(lines)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("closer ") and msg_lower != "closer":
        return None

    rest = msg[7:].strip() if msg_lower.startswith("closer ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("objection "):
        return cmd_objection(rest[10:].strip())
    if rest_lower.startswith("negotiate "):
        return cmd_negotiate(rest[10:].strip())
    if rest_lower.startswith("close "):
        return cmd_close(rest[6:].strip())
    if rest_lower.startswith("script "):
        return cmd_script(rest[7:].strip())
    if rest_lower == "pipeline":
        return cmd_pipeline()
    if rest_lower == "status":
        return cmd_status()
    if rest_lower == "help" or not rest_lower:
        return (
            "💼 *SalesCloserPro Commands:*\n"
            "  `closer objection <objection>` — handle a sales objection\n"
            "  `closer negotiate <context>` — negotiation tactics\n"
            "  `closer close <deal_context>` — closing script\n"
            "  `closer script <stage>` — sales script (discovery/demo/close)\n"
            "  `closer pipeline` — active deals and actions\n"
            "  `closer status` — won/lost stats"
        )

    return "Unknown closer command. Try `closer help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] sales-closer-pro started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "sales-closer-pro",
                    "message": response,
                })
                logger.info("sales-closer-pro: handled command: %s", message[:60])

        deals = load_deals()
        write_state({
            "bot": "sales-closer-pro",
            "ts": now_iso(),
            "status": "running",
            "total_deals": len(deals),
            "won_deals": sum(1 for d in deals if d.get("status") == "won"),
            "lost_deals": sum(1 for d in deals if d.get("status") == "lost"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
