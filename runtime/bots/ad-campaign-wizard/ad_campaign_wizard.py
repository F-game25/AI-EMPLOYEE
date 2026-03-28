"""AdCampaignWizard Bot — Paid ads specialist (Meta/Google/LinkedIn).

Manages end-to-end paid advertising across major platforms:
  - Conversion-optimized ad copy generation
  - Budget allocation strategy across platforms
  - Campaign performance analysis and optimization
  - ROAS prediction modeling
  - Full campaign launch briefs
  - Creative briefs for ad visuals
  - Campaign performance reporting

Commands (via chatlog / WhatsApp / Dashboard):
  ads copy <product> <platform>     — ad copy for a product/platform
  ads budget <goal> <spend>         — budget allocation strategy
  ads analyze <campaign_data>       — performance analysis and optimization
  ads roas <product> <cpa>          — ROAS prediction model
  ads launch <product> <budget>     — full campaign launch brief
  ads creative <product>            — creative brief for ad visuals
  ads status                        — show campaign performance

State files:
  ~/.ai-employee/state/ad-campaign-wizard.state.json
  ~/.ai-employee/state/campaigns.json
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
STATE_FILE = AI_HOME / "state" / "ad-campaign-wizard.state.json"
CAMPAIGNS_FILE = AI_HOME / "state" / "campaigns.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("AD_CAMPAIGN_WIZARD_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("ad-campaign-wizard")

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


def load_campaigns() -> list:
    if not CAMPAIGNS_FILE.exists():
        return []
    try:
        return json.loads(CAMPAIGNS_FILE.read_text())
    except Exception:
        return []


def save_campaigns(campaigns: list) -> None:
    CAMPAIGNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAMPAIGNS_FILE.write_text(json.dumps(campaigns, indent=2))


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
    queue_file = AGENT_TASKS_DIR / "ad-campaign-wizard.queue.jsonl"
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
    logger.info("ad-campaign-wizard: completed subtask '%s'", subtask_id)


SYSTEM_PROMPT = (
    "You are AdCampaignWizard, a performance marketing expert who has managed $50M+ in ad spend "
    "across Meta, Google, and LinkedIn. You write conversion-optimized ad copy, design precise "
    "targeting strategies, predict ROAS, and optimize campaigns to beat benchmarks. You think in "
    "funnels, audience segments, and creative testing frameworks."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_copy(product: str, platform: str) -> str:
    campaigns = load_campaigns()
    result = ai_query(
        f"Write conversion-optimized ad copy for product: {product} on platform: {platform}\n\n"
        "## Platform Context\n"
        f"Platform: {platform} | Format: [best formats for this platform]\n\n"
        "## Primary Ad Copy (5 variants)\n"
        "For each variant:\n"
        "- **Headline**: [<30 chars for Google / <40 for Meta]\n"
        "- **Primary Text** (Meta) / **Description** (Google): [full copy]\n"
        "- **CTA**: [button text]\n"
        "- **Hook**: [what stops the scroll]\n"
        "- **Angle**: [pain / gain / fear / curiosity / social proof]\n\n"
        "## Headlines Bank (15 options)\n"
        "Ranked by predicted CTR\n\n"
        "## Body Copy Templates (5)\n"
        "Different emotional angles for split testing\n\n"
        "## Targeting Recommendations\n"
        f"Specific audience targeting for {platform}\n\n"
        "## Bidding Strategy\n"
        "Recommended bid type and starting bid\n\n"
        "## Creative Guidance\n"
        "What visual/video to pair with each copy variant",
        SYSTEM_PROMPT,
    )
    campaign_entry = {
        "id": str(uuid.uuid4())[:8],
        "product": product,
        "platform": platform,
        "created_at": now_iso(),
        "status": "draft",
    }
    campaigns.insert(0, campaign_entry)
    save_campaigns(campaigns[:100])
    return result


def cmd_budget(goal: str, spend: str) -> str:
    return ai_query(
        f"Design a budget allocation strategy for goal: {goal} with total spend: {spend}\n\n"
        "## Budget Allocation Model\n"
        "| Platform | % of Budget | Amount | Rationale |\n"
        "|----------|-------------|--------|----------|\n"
        "[fill in Meta, Google, LinkedIn, TikTok, Other]\n\n"
        "## Within-Platform Allocation\n"
        "For each platform: campaign type → ad set → creative split\n\n"
        "## Funnel Budget Distribution\n"
        "- TOFU (awareness): [%]\n"
        "- MOFU (consideration): [%]\n"
        "- BOFU (conversion): [%]\n"
        "- Retargeting: [%]\n\n"
        "## Pacing Strategy\n"
        "How to spend budget over time (front-load vs. even pacing)\n\n"
        "## Scale Triggers\n"
        "When to increase budget and by how much (specific ROAS/CPA thresholds)\n\n"
        "## Kill Switch Rules\n"
        "When to pause campaigns and reallocate\n\n"
        "## Monthly Budget Calendar\n"
        "Day-by-day spend recommendation",
        SYSTEM_PROMPT,
    )


def cmd_analyze(campaign_data: str) -> str:
    return ai_query(
        f"Analyze this campaign data and provide optimization recommendations: {campaign_data}\n\n"
        "## Performance Diagnosis\n"
        "- CTR benchmark: [actual vs. industry benchmark]\n"
        "- CPC analysis: [high/low and why]\n"
        "- CVR analysis: [conversion rate assessment]\n"
        "- ROAS assessment: [vs. target]\n\n"
        "## Root Cause Analysis\n"
        "Top 3 reasons for current performance level\n\n"
        "## Optimization Actions (prioritized)\n"
        "**Immediate (today):**\n"
        "[3 changes to make right now]\n\n"
        "**This week:**\n"
        "[5 optimizations to implement]\n\n"
        "**This month:**\n"
        "[Strategic changes for sustained improvement]\n\n"
        "## Creative Fatigue Check\n"
        "How to detect and fix ad fatigue\n\n"
        "## Audience Optimization\n"
        "Expand, narrow, or shift targeting recommendations\n\n"
        "## Projected Impact\n"
        "Expected ROAS improvement from each recommendation",
        SYSTEM_PROMPT,
    )


def cmd_roas(product: str, cpa: str) -> str:
    return ai_query(
        f"Build a ROAS prediction model for product: {product} with target CPA: {cpa}\n\n"
        "## ROAS Calculation Model\n"
        "Formula: Revenue / Ad Spend = ROAS\n"
        f"- Target CPA: {cpa}\n"
        "- Assumed AOV: [estimate based on product]\n"
        "- Expected CVR: [by platform/funnel stage]\n\n"
        "## ROAS Scenarios\n"
        "| Scenario | CVR | CPC | ROAS | Monthly Revenue at $1k spend |\n"
        "|----------|-----|-----|------|------------------------------|\n"
        "Conservative | [%] | [$] | [x] | [$]\n"
        "Base Case    | [%] | [$] | [x] | [$]\n"
        "Optimistic   | [%] | [$] | [x] | [$]\n\n"
        "## Break-Even Analysis\n"
        "Minimum ROAS to break even and how to calculate it\n\n"
        "## ROAS Improvement Levers\n"
        "Ranked by impact: what moves ROAS the most\n\n"
        "## LTV-Adjusted ROAS\n"
        "How to calculate blended ROAS including repeat purchases\n\n"
        "## Benchmarks by Industry\n"
        "ROAS targets for this product category",
        SYSTEM_PROMPT,
    )


def cmd_launch(product: str, budget: str) -> str:
    campaigns = load_campaigns()
    result = ai_query(
        f"Create a full campaign launch brief for product: {product} with budget: {budget}\n\n"
        "## Campaign Strategy\n"
        "- Objective: [awareness/consideration/conversion]\n"
        "- Primary platform: [recommendation with reason]\n"
        "- Campaign structure: campaign → ad set → ads\n\n"
        "## Audience Strategy\n"
        "- Cold audiences: [3 targeting approaches]\n"
        "- Lookalike audiences: [seed audience and % recommendations]\n"
        "- Retargeting audiences: [segments and messages]\n\n"
        "## Creative Brief\n"
        "- Ad formats: [which formats to test]\n"
        "- Creative themes: [3 angles to test]\n"
        "- Copy framework: [hook, body, CTA structure]\n\n"
        "## Launch Checklist (30 items)\n"
        "Pixel, tracking, assets, approvals, budget, scheduling\n\n"
        "## Week 1 Optimization Plan\n"
        "Daily actions in the first 7 days\n\n"
        "## Success Metrics\n"
        "KPIs, targets, and review cadence\n\n"
        "## 90-Day Scaling Roadmap\n"
        "How to grow from launch to scaled performance",
        SYSTEM_PROMPT,
    )
    launch_entry = {
        "id": str(uuid.uuid4())[:8],
        "product": product,
        "budget": budget,
        "created_at": now_iso(),
        "status": "launched",
    }
    campaigns.insert(0, launch_entry)
    save_campaigns(campaigns[:100])
    return result


def cmd_creative(product: str) -> str:
    return ai_query(
        f"Write a creative brief for ad visuals for product: {product}\n\n"
        "## Creative Strategy\n"
        "- Primary message: [one sentence]\n"
        "- Emotional trigger: [the feeling to evoke]\n"
        "- Visual metaphor: [concept]\n\n"
        "## Creative Formats to Test\n"
        "1. Static image ad brief\n"
        "2. Video ad brief (15s and 30s)\n"
        "3. Carousel ad brief\n"
        "4. Story/Reel brief\n\n"
        "## For Each Format\n"
        "- Visual description (what to show)\n"
        "- Text overlay\n"
        "- Color palette and tone\n"
        "- Talent/model direction (if applicable)\n"
        "- B-roll or asset list\n\n"
        "## Hook Frames\n"
        "First 3 seconds of video — 5 options\n\n"
        "## Creative Testing Matrix\n"
        "How to systematically test creatives\n\n"
        "## Production Notes\n"
        "Spec requirements for each platform",
        SYSTEM_PROMPT,
    )


def cmd_status() -> str:
    campaigns = load_campaigns()
    if not campaigns:
        return "No campaigns tracked yet. Try: `ads launch <product> <budget>`"
    lines = ["📊 *AdCampaignWizard — Campaign Performance:*"]
    lines.append(f"  Total campaigns: {len(campaigns)}")
    active = sum(1 for c in campaigns if c.get("status") == "launched")
    drafts = sum(1 for c in campaigns if c.get("status") == "draft")
    lines.append(f"  Active: {active} | Drafts: {drafts}")
    lines.append("\n*Recent campaigns:*")
    for c in campaigns[:5]:
        name = c.get("product", "?")
        lines.append(
            f"  • `{c.get('id','?')}` — {str(name)[:40]} "
            f"[{c.get('platform', c.get('budget','?'))}] ({c.get('status','?')})"
        )
    return "\n".join(lines)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("ads ") and msg_lower != "ads":
        return None

    rest = msg[4:].strip() if msg_lower.startswith("ads ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("copy "):
        parts = rest[5:].strip().split(None, 1)
        product = parts[0] if parts else "product"
        platform = parts[1] if len(parts) > 1 else "meta"
        return cmd_copy(product, platform)
    if rest_lower.startswith("budget "):
        parts = rest[7:].strip().split(None, 1)
        goal = parts[0] if parts else "revenue"
        spend = parts[1] if len(parts) > 1 else "1000"
        return cmd_budget(goal, spend)
    if rest_lower.startswith("analyze "):
        return cmd_analyze(rest[8:].strip())
    if rest_lower.startswith("roas "):
        parts = rest[5:].strip().split(None, 1)
        product = parts[0] if parts else "product"
        cpa = parts[1] if len(parts) > 1 else "50"
        return cmd_roas(product, cpa)
    if rest_lower.startswith("launch "):
        parts = rest[7:].strip().split(None, 1)
        product = parts[0] if parts else "product"
        budget = parts[1] if len(parts) > 1 else "1000"
        return cmd_launch(product, budget)
    if rest_lower.startswith("creative "):
        return cmd_creative(rest[9:].strip())
    if rest_lower == "status":
        return cmd_status()
    if rest_lower == "help" or not rest_lower:
        return (
            "📊 *AdCampaignWizard Commands:*\n"
            "  `ads copy <product> <platform>` — ad copy generation\n"
            "  `ads budget <goal> <spend>` — budget allocation\n"
            "  `ads analyze <campaign_data>` — performance analysis\n"
            "  `ads roas <product> <cpa>` — ROAS prediction\n"
            "  `ads launch <product> <budget>` — campaign launch brief\n"
            "  `ads creative <product>` — creative brief\n"
            "  `ads status` — campaign performance"
        )

    return "Unknown ads command. Try `ads help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] ad-campaign-wizard started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "ad-campaign-wizard",
                    "message": response,
                })
                logger.info("ad-campaign-wizard: handled command: %s", message[:60])

        campaigns = load_campaigns()
        write_state({
            "bot": "ad-campaign-wizard",
            "ts": now_iso(),
            "status": "running",
            "total_campaigns": len(campaigns),
            "active_campaigns": sum(1 for c in campaigns if c.get("status") == "launched"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
