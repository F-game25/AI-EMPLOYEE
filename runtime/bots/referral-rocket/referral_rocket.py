"""ReferralRocket Bot — Automated referral program builder.

Designs and launches viral referral programs that drive acquisition:
  - Referral program structure design
  - Optimal incentive model calculation
  - Referral email and message copy templates
  - Program tracking metrics
  - Full referral program launch plans
  - Referral program stats reporting

Commands (via chatlog / WhatsApp / Dashboard):
  referral design <product>              — design referral program structure
  referral incentive <product> <budget>  — calculate optimal incentive model
  referral copy <product>                — referral email/message templates
  referral track <program_id>            — tracking metrics for a program
  referral launch <product>              — full referral program launch plan
  referral status                        — show referral program stats

State files:
  ~/.ai-employee/state/referral-rocket.state.json
  ~/.ai-employee/state/referral-programs.json
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
STATE_FILE = AI_HOME / "state" / "referral-rocket.state.json"
PROGRAMS_FILE = AI_HOME / "state" / "referral-programs.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("REFERRAL_ROCKET_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("referral-rocket")

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


def load_programs() -> list:
    if not PROGRAMS_FILE.exists():
        return []
    try:
        return json.loads(PROGRAMS_FILE.read_text())
    except Exception:
        return []


def save_programs(programs: list) -> None:
    PROGRAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRAMS_FILE.write_text(json.dumps(programs, indent=2))


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
    queue_file = AGENT_TASKS_DIR / "referral-rocket.queue.jsonl"
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
    logger.info("referral-rocket: completed subtask '%s'", subtask_id)


SYSTEM_PROMPT = (
    "You are ReferralRocket, a viral growth and referral marketing expert who has designed referral "
    "programs generating 40%+ of new revenue for SaaS companies. You understand psychology of "
    "sharing, optimal incentive structures, fraud prevention, and how to make referral the most "
    "cost-effective acquisition channel."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_design(product: str) -> str:
    programs = load_programs()
    result = ai_query(
        f"Design a referral program structure for: {product}\n\n"
        "## Program Type Comparison\n"
        "| Type | Structure | Best For | Pros | Cons |\n"
        "|------|-----------|---------|------|------|\n"
        "One-sided | [desc] | [use case] | [pros] | [cons]\n"
        "Two-sided | [desc] | [use case] | [pros] | [cons]\n"
        "Multi-tier | [desc] | [use case] | [pros] | [cons]\n\n"
        "## Recommended Structure\n"
        "Which type and why for this specific product\n\n"
        "## Program Mechanics\n"
        "- How participants join\n"
        "- How the referral link/code works\n"
        "- Attribution model and window\n"
        "- How rewards are triggered and delivered\n\n"
        "## Sharing Triggers\n"
        "3 in-product moments that naturally prompt sharing\n\n"
        "## Fraud Prevention\n"
        "Rules and technical measures to prevent abuse\n\n"
        "## Program Name and Branding\n"
        "5 name ideas and visual identity concept\n\n"
        "## Technology Requirements\n"
        "Recommended tools and implementation complexity",
        SYSTEM_PROMPT,
    )
    program_entry = {
        "id": str(uuid.uuid4())[:8],
        "product": product,
        "created_at": now_iso(),
        "status": "designed",
    }
    programs.insert(0, program_entry)
    save_programs(programs[:100])
    return result


def cmd_incentive(product: str, budget: str) -> str:
    return ai_query(
        f"Calculate the optimal incentive model for product: {product} with budget: {budget}\n\n"
        "## Incentive Economics\n"
        f"- Monthly budget: {budget}\n"
        "- Target CAC via referral: [calculate]\n"
        "- Break-even referral volume: [calculate]\n\n"
        "## Incentive Options Analysis\n"
        "| Incentive Type | Amount | Cost Per Referral | Motivation Score | Fraud Risk |\n"
        "|----------------|--------|------------------|------------------|------------|\n"
        "Cash reward      | [$]    | [$]              | [1-10]           | [low/med/high]\n"
        "Product credit   | [$]    | [$]              | [1-10]           | [low/med/high]\n"
        "Discount         | [%]    | [$]              | [1-10]           | [low/med/high]\n"
        "Feature unlock   | [desc] | [$]              | [1-10]           | [low/med/high]\n"
        "Merchandise      | [desc] | [$]              | [1-10]           | [low/med/high]\n\n"
        "## Recommended Incentive\n"
        "Exact structure with amounts for both referrer and referee\n\n"
        "## Tiered Incentive Model\n"
        "Bonus rewards for top referrers (gamification)\n\n"
        "## ROI Projection\n"
        f"Expected new customers per month at {budget} budget\n\n"
        "## Incentive Psychology\n"
        "Why this incentive motivates sharing",
        SYSTEM_PROMPT,
    )


def cmd_copy(product: str) -> str:
    return ai_query(
        f"Write referral email and message templates for product: {product}\n\n"
        "## Referral Invite Email (5 variants)\n"
        "For each:\n"
        "- Subject line\n"
        "- Full email body (personal tone, not corporate)\n"
        "- P.S. line\n\n"
        "## In-App Share Message\n"
        "Pre-filled message for social/email sharing\n\n"
        "## WhatsApp/SMS Template\n"
        "Short, casual message under 160 characters\n\n"
        "## Social Post Templates\n"
        "LinkedIn, Twitter/X, Facebook — 1 template each\n\n"
        "## Referral Landing Page Copy\n"
        "Headline, subheadline, and CTA for referee landing page\n\n"
        "## Reward Notification Emails\n"
        "- Reward earned notification\n"
        "- Reward delivered notification\n"
        "- Milestone reward notification\n\n"
        "## Copy Principles\n"
        "What makes referral copy convert",
        SYSTEM_PROMPT,
    )


def cmd_track(program_id: str) -> str:
    return ai_query(
        f"Define tracking metrics and dashboard for referral program ID: {program_id}\n\n"
        "## Core Referral Metrics\n"
        "| Metric | Definition | Formula | Target Benchmark |\n"
        "|--------|-----------|---------|------------------|\n"
        "Referral Rate | [def] | [formula] | [benchmark]\n"
        "K-Factor | [def] | [formula] | [benchmark]\n"
        "Viral Coefficient | [def] | [formula] | [benchmark]\n"
        "Invite-to-Signup Rate | [def] | [formula] | [benchmark]\n"
        "Referral CAC | [def] | [formula] | [benchmark]\n\n"
        "## Dashboard Setup\n"
        "Which charts and reports to build\n\n"
        "## Weekly Review Template\n"
        "What to check every week and how to interpret it\n\n"
        "## Cohort Analysis\n"
        "How to track referral program cohorts over time\n\n"
        "## Fraud Detection Signals\n"
        "Metrics that indicate abuse\n\n"
        "## Program Health Score\n"
        "Composite score to assess overall program performance",
        SYSTEM_PROMPT,
    )


def cmd_launch(product: str) -> str:
    programs = load_programs()
    result = ai_query(
        f"Create a full referral program launch plan for: {product}\n\n"
        "## Pre-Launch (Week -2 to 0)\n"
        "- Technical setup checklist\n"
        "- Copy and creative assets needed\n"
        "- Tracking and analytics setup\n"
        "- Legal/compliance review\n\n"
        "## Seed Strategy\n"
        "How to get first 100 referrals from existing users\n\n"
        "## Launch Announcement\n"
        "- Email to existing customers\n"
        "- In-app announcement\n"
        "- Social media post\n\n"
        "## Growth Loops\n"
        "How new referrers become referrers themselves\n\n"
        "## 30-60-90 Day Milestones\n"
        "Targets and actions for each phase\n\n"
        "## Optimization Schedule\n"
        "When and how to test incentive changes\n\n"
        "## Launch Checklist (25 items)\n"
        "Everything to verify before going live",
        SYSTEM_PROMPT,
    )
    launch_entry = {
        "id": str(uuid.uuid4())[:8],
        "product": product,
        "created_at": now_iso(),
        "status": "launched",
    }
    programs.insert(0, launch_entry)
    save_programs(programs[:100])
    return result


def cmd_status() -> str:
    programs = load_programs()
    if not programs:
        return "No referral programs yet. Try: `referral launch <product>`"
    lines = ["🚀 *ReferralRocket — Program Stats:*"]
    lines.append(f"  Total programs: {len(programs)}")
    launched = sum(1 for p in programs if p.get("status") == "launched")
    lines.append(f"  Live programs: {launched} | In design: {len(programs) - launched}")
    lines.append("\n*Recent programs:*")
    for p in programs[:5]:
        lines.append(f"  • `{p.get('id','?')}` — {p.get('product','?')[:50]} ({p.get('status','?')})")
    return "\n".join(lines)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("referral ") and msg_lower != "referral":
        return None

    rest = msg[9:].strip() if msg_lower.startswith("referral ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("design "):
        return cmd_design(rest[7:].strip())
    if rest_lower.startswith("incentive "):
        parts = rest[10:].strip().split(None, 1)
        product = parts[0] if parts else "product"
        budget = parts[1] if len(parts) > 1 else "1000"
        return cmd_incentive(product, budget)
    if rest_lower.startswith("copy "):
        return cmd_copy(rest[5:].strip())
    if rest_lower.startswith("track "):
        return cmd_track(rest[6:].strip())
    if rest_lower.startswith("launch "):
        return cmd_launch(rest[7:].strip())
    if rest_lower == "status":
        return cmd_status()
    if rest_lower == "help" or not rest_lower:
        return (
            "🚀 *ReferralRocket Commands:*\n"
            "  `referral design <product>` — referral program structure\n"
            "  `referral incentive <product> <budget>` — optimal incentive model\n"
            "  `referral copy <product>` — email/message templates\n"
            "  `referral track <program_id>` — tracking metrics\n"
            "  `referral launch <product>` — full launch plan\n"
            "  `referral status` — program stats"
        )

    return "Unknown referral command. Try `referral help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] referral-rocket started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "referral-rocket",
                    "message": response,
                })
                logger.info("referral-rocket: handled command: %s", message[:60])

        programs = load_programs()
        write_state({
            "bot": "referral-rocket",
            "ts": now_iso(),
            "status": "running",
            "total_programs": len(programs),
            "live_programs": sum(1 for p in programs if p.get("status") == "launched"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
