"""Growth Hacker Bot — Viral loops, funnel optimization, and retention tactics.

Drives exponential business growth through data-driven growth hacking:
  - Viral growth loop design
  - Acquisition funnel optimization
  - A/B test framework generation
  - Retention and churn reduction strategies
  - Referral program design
  - Product-led growth (PLG) strategy
  - Growth experiment prioritization (ICE scoring)
  - User activation optimization
  - Revenue expansion (upsell/cross-sell)
  - Growth metrics and OKR setting

Commands (via chatlog / WhatsApp / Dashboard):
  growth loop <product>            — design viral growth loop
  growth funnel <product>          — conversion funnel analysis
  growth abtests <feature>         — A/B test ideas and framework
  growth retention <product>       — retention improvement strategy
  growth referral <product>        — referral program design
  growth plg <product>             — product-led growth strategy
  growth experiments <goal>        — ICE-scored experiment backlog
  growth activate <product>        — user activation optimization
  growth expand <product>          — revenue expansion tactics
  growth okrs <quarter>            — growth OKRs and metrics
  growth audit <product>           — full growth audit
  growth status                    — current growth projects

State files:
  ~/.ai-employee/state/growth-hacker.state.json
  ~/.ai-employee/state/growth-experiments.json
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
STATE_FILE = AI_HOME / "state" / "growth-hacker.state.json"
EXPERIMENTS_FILE = AI_HOME / "state" / "growth-experiments.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("GROWTH_HACKER_POLL_INTERVAL", "5"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("growth-hacker")

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


def load_experiments() -> list:
    if not EXPERIMENTS_FILE.exists():
        return []
    try:
        return json.loads(EXPERIMENTS_FILE.read_text())
    except Exception:
        return []


def save_experiments(experiments: list) -> None:
    EXPERIMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXPERIMENTS_FILE.write_text(json.dumps(experiments, indent=2))


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


SYSTEM_GROWTH = (
    "You are a world-class Growth Hacker and VP of Growth with experience scaling "
    "multiple startups from 0 to millions of users. You combine product sense, "
    "data analysis, and creative experimentation to drive sustainable growth. "
    "You think in loops, funnels, and flywheel effects. Be specific, numbers-driven, "
    "and immediately actionable."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_loop(product: str) -> str:
    return ai_query(
        f"Design viral growth loops for: {product}\n\n"
        "## Primary Viral Loop\n"
        "Step-by-step mechanics:\n"
        "1. User performs [action]\n"
        "2. System triggers [mechanism]\n"
        "3. New user is exposed\n"
        "4. New user converts\n"
        "5. Loop repeats\n\n"
        "**Viral Coefficient (K-factor)** estimate and what affects it\n\n"
        "## Secondary Growth Loops\n"
        "2-3 additional loops (content loop, data loop, network effect loop)\n\n"
        "## Flywheel Design\n"
        "How loops compound and reinforce each other\n\n"
        "## Viral Feature Ideas\n"
        "5 specific product features that create virality\n\n"
        "## Mechanics to Implement\n"
        "Rank by impact × effort:\n"
        "- Quick wins (low effort, high impact)\n"
        "- Big bets (high effort, high impact)\n\n"
        "## Success Metrics\n"
        "How to measure viral performance",
        SYSTEM_GROWTH,
    )


def cmd_funnel(product: str) -> str:
    return ai_query(
        f"Analyze and optimize the conversion funnel for: {product}\n\n"
        "## Funnel Stages\n"
        "Map the full funnel: Awareness → Acquisition → Activation → Revenue → Retention → Referral\n\n"
        "## Benchmark Conversion Rates\n"
        "Industry benchmarks for each funnel stage\n\n"
        "## Biggest Leak Points\n"
        "Where most users typically drop off and why\n\n"
        "## Optimization Tactics (per stage)\n\n"
        "**Awareness:**\n"
        "- Top 3 channels ranked by CAC efficiency\n"
        "- Content types that convert best\n\n"
        "**Acquisition:**\n"
        "- Landing page optimization checklist (10 items)\n"
        "- CTA improvement tactics\n\n"
        "**Activation:**\n"
        "- 'Aha moment' definition and timeline\n"
        "- Onboarding flow optimization\n\n"
        "**Retention:**\n"
        "- Engagement triggers to implement\n"
        "- Re-engagement sequences\n\n"
        "## Priority Actions\n"
        "Top 5 funnel improvements ranked by ROI potential",
        SYSTEM_GROWTH,
    )


def cmd_abtests(feature: str) -> str:
    return ai_query(
        f"Create A/B test ideas and framework for: {feature}\n\n"
        "## 15 A/B Test Ideas (ICE scored)\n"
        "For each test:\n"
        "- **Hypothesis**: If we [change X], then [metric Y] will [improve by Z%] because [reason]\n"
        "- **Control**: current state\n"
        "- **Variant**: what to test\n"
        "- **Primary Metric**: what we're optimizing\n"
        "- **Secondary Metrics**: guardrail metrics\n"
        "- **ICE Score**: Impact (1-10), Confidence (1-10), Ease (1-10)\n"
        "- **Sample Size**: required for statistical significance\n"
        "- **Duration**: estimated test run time\n\n"
        "## Testing Prioritization Framework\n"
        "How to prioritize the backlog\n\n"
        "## A/B Testing Best Practices\n"
        "10 rules to avoid common mistakes\n\n"
        "## Statistical Significance Guide\n"
        "When to call a test and how to interpret results",
        SYSTEM_GROWTH,
    )


def cmd_retention(product: str) -> str:
    return ai_query(
        f"Design a comprehensive retention strategy for: {product}\n\n"
        "## Retention Analysis Framework\n"
        "- Day 1, Day 7, Day 30 retention benchmarks\n"
        "- How to calculate cohort retention\n"
        "- Warning signs of churn\n\n"
        "## Activation Improvements\n"
        "5 ways to improve first-session success\n\n"
        "## Engagement Loop Design\n"
        "Daily/weekly habit-forming mechanics\n\n"
        "## Email/Push Re-engagement\n"
        "- Trigger-based sequences (what actions trigger what emails)\n"
        "- Subject line formulas that work\n"
        "- Re-engagement campaign for dormant users\n\n"
        "## Churn Prediction\n"
        "- Early warning signals (behavioral)\n"
        "- Churn prevention interventions\n\n"
        "## Power User Program\n"
        "How to identify, nurture, and leverage power users\n\n"
        "## Retention Metrics Dashboard\n"
        "Which metrics to track daily/weekly/monthly",
        SYSTEM_GROWTH,
    )


def cmd_referral(product: str) -> str:
    return ai_query(
        f"Design a high-converting referral program for: {product}\n\n"
        "## Referral Program Design Options\n"
        "3 program structures with pros/cons:\n"
        "1. One-sided (reward the referrer only)\n"
        "2. Two-sided (reward both parties)\n"
        "3. Multi-tier (reward for multiple levels)\n\n"
        "**Recommended Structure** with justification\n\n"
        "## Reward Options\n"
        "- Cash rewards: amount, trigger, cap\n"
        "- Product credits: mechanics\n"
        "- Feature unlocks: what features\n"
        "- Status/recognition: program tiers\n\n"
        "## Referral Mechanics\n"
        "- How the referral link works\n"
        "- Attribution window\n"
        "- Fraud prevention\n\n"
        "## Launch Strategy\n"
        "How to seed and launch the referral program\n\n"
        "## Referral Copy Templates\n"
        "5 email templates for referral asks\n\n"
        "## Success Metrics\n"
        "How to measure program ROI",
        SYSTEM_GROWTH,
    )


def cmd_plg(product: str) -> str:
    return ai_query(
        f"Design a Product-Led Growth (PLG) strategy for: {product}\n\n"
        "## PLG Readiness Assessment\n"
        "Is the product ready for PLG? What needs to change?\n\n"
        "## Free Tier / Freemium Design\n"
        "- What features to include in free tier\n"
        "- What to gate for paid (upgrade triggers)\n"
        "- Usage limits vs feature limits (which is better here?)\n\n"
        "## Self-Serve Activation\n"
        "How users go from signup to value without sales\n\n"
        "## Product Qualified Leads (PQLs)\n"
        "- How to identify PQLs from usage data\n"
        "- Scoring model for PQLs\n"
        "- Sales handoff triggers\n\n"
        "## In-Product Growth Mechanics\n"
        "- Upgrade prompts: where, when, how\n"
        "- Collaborative features that expand usage\n"
        "- Viral sharing moments\n\n"
        "## PLG Metrics\n"
        "Key PLG metrics and benchmarks\n\n"
        "## 90-Day PLG Implementation Roadmap\n"
        "What to build first",
        SYSTEM_GROWTH,
    )


def cmd_experiments(goal: str) -> str:
    experiments = load_experiments()
    result = ai_query(
        f"Generate a growth experiment backlog for goal: {goal}\n\n"
        "Create 20 experiments with ICE scoring:\n\n"
        "| # | Experiment | Impact (1-10) | Confidence (1-10) | Ease (1-10) | ICE Score | Stage |\n"
        "|---|-----------|---------------|-------------------|-------------|-----------|-------|\n"
        "[fill in 20 rows]\n\n"
        "For top 5 experiments (by ICE score), provide full brief:\n"
        "- Hypothesis\n"
        "- Test design\n"
        "- Success criteria\n"
        "- Resources needed\n"
        "- Expected timeline\n\n"
        "## Experiment Prioritization Logic\n"
        "How to choose which experiment to run next",
        SYSTEM_GROWTH,
    )
    # Save experiments to state
    new_exp = {
        "id": str(uuid.uuid4())[:8],
        "goal": goal,
        "created_at": now_iso(),
        "status": "backlog",
    }
    experiments.insert(0, new_exp)
    save_experiments(experiments[:50])
    return result


def cmd_activate(product: str) -> str:
    return ai_query(
        f"Optimize user activation for: {product}\n\n"
        "## Define the 'Aha Moment'\n"
        "What action/outcome makes users realize the value?\n"
        "How quickly do they need to reach it?\n\n"
        "## Activation Funnel Map\n"
        "Step-by-step from signup to first 'aha moment'\n"
        "Drop-off rates at each step (estimated)\n\n"
        "## Onboarding Optimization\n"
        "- Welcome email sequence (5 emails with subject lines and content)\n"
        "- In-app onboarding checklist design\n"
        "- Tooltips and contextual help strategy\n"
        "- Empty state design principles\n\n"
        "## Time-to-Value Reduction\n"
        "5 ways to get users to value faster\n\n"
        "## Activation Experiment Ideas\n"
        "10 tests ranked by ICE score\n\n"
        "## Success Metrics\n"
        "Activation rate benchmarks and targets",
        SYSTEM_GROWTH,
    )


def cmd_expand(product: str) -> str:
    return ai_query(
        f"Design revenue expansion strategy for: {product}\n\n"
        "## Expansion Revenue Levers\n"
        "1. **Upsell**: move customers to higher tier\n"
        "2. **Cross-sell**: sell additional products/features\n"
        "3. **Seat expansion**: grow within accounts\n"
        "4. **Usage expansion**: grow consumption-based revenue\n\n"
        "## Upsell Playbook\n"
        "- Triggers for upgrade conversations\n"
        "- In-product upgrade prompts (5 examples)\n"
        "- Email sequences for upgrade\n\n"
        "## Cross-Sell Strategy\n"
        "- What to cross-sell and when\n"
        "- Bundling options\n\n"
        "## NRR Optimization\n"
        "How to improve Net Revenue Retention above 100%\n\n"
        "## Customer Success Expansion Plays\n"
        "Proactive expansion tactics for CSM team\n\n"
        "## Expansion Metrics\n"
        "MRR expansion rate, NRR, upsell conversion benchmarks",
        SYSTEM_GROWTH,
    )


def cmd_okrs(quarter: str) -> str:
    return ai_query(
        f"Create growth OKRs and metrics for: {quarter}\n\n"
        "## Growth OKRs (3-5 Objectives)\n"
        "For each Objective, 3-4 Key Results:\n"
        "- **Objective**: [aspirational goal]\n"
        "  - KR1: [measurable outcome with number]\n"
        "  - KR2: [measurable outcome]\n"
        "  - KR3: [measurable outcome]\n\n"
        "## Growth Metrics Dashboard\n"
        "**North Star Metric**: [the one that matters most]\n\n"
        "**Weekly Metrics to Track**:\n"
        "- Acquisition: [3 metrics]\n"
        "- Activation: [2 metrics]\n"
        "- Retention: [3 metrics]\n"
        "- Revenue: [3 metrics]\n"
        "- Referral: [2 metrics]\n\n"
        "## Growth Team Rhythm\n"
        "Daily standup format, weekly review, monthly retrospective\n\n"
        "## Targets and Benchmarks\n"
        "Industry benchmarks for each metric",
        SYSTEM_GROWTH,
    )


def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "growth-hacker.queue.jsonl"
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
    result = ai_query(instructions, SYSTEM_GROWTH)
    write_orchestrator_result(subtask_id, result)
    logger.info("growth-hacker: completed subtask '%s'", subtask_id)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("growth ") and msg_lower != "growth":
        return None

    rest = msg[7:].strip() if msg_lower.startswith("growth ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("loop "):
        return cmd_loop(rest[5:].strip())
    if rest_lower.startswith("funnel "):
        return cmd_funnel(rest[7:].strip())
    if rest_lower.startswith("abtests ") or rest_lower.startswith("ab "):
        arg = rest[8:].strip() if rest_lower.startswith("abtests ") else rest[3:].strip()
        return cmd_abtests(arg)
    if rest_lower.startswith("retention "):
        return cmd_retention(rest[10:].strip())
    if rest_lower.startswith("referral "):
        return cmd_referral(rest[9:].strip())
    if rest_lower.startswith("plg "):
        return cmd_plg(rest[4:].strip())
    if rest_lower.startswith("experiments "):
        return cmd_experiments(rest[12:].strip())
    if rest_lower.startswith("activate "):
        return cmd_activate(rest[9:].strip())
    if rest_lower.startswith("expand "):
        return cmd_expand(rest[7:].strip())
    if rest_lower.startswith("okrs "):
        return cmd_okrs(rest[5:].strip())
    if rest_lower.startswith("audit "):
        return ai_query(
            f"Conduct a full growth audit for: {rest[6:].strip()}\n\n"
            "Score 1-10 on: Acquisition, Activation, Retention, Revenue, Referral. "
            "Give top 3 quick wins and top 3 strategic initiatives.",
            SYSTEM_GROWTH,
        )
    if rest_lower == "status":
        experiments = load_experiments()
        if not experiments:
            return "No growth experiments yet. Try: `growth experiments <goal>`"
        lines = ["🚀 *Growth Experiments:*"]
        for e in experiments[:5]:
            lines.append(f"  • `{e['id']}` — {e.get('goal','?')[:50]} ({e.get('status','?')})")
        return "\n".join(lines)
    if rest_lower == "help" or not rest_lower:
        return (
            "🚀 *Growth Hacker Commands:*\n"
            "  `growth loop <product>` — viral growth loop design\n"
            "  `growth funnel <product>` — funnel optimization\n"
            "  `growth abtests <feature>` — A/B test framework\n"
            "  `growth retention <product>` — retention strategy\n"
            "  `growth referral <product>` — referral program\n"
            "  `growth plg <product>` — product-led growth\n"
            "  `growth experiments <goal>` — ICE experiment backlog\n"
            "  `growth activate <product>` — activation optimization\n"
            "  `growth expand <product>` — revenue expansion\n"
            "  `growth okrs <quarter>` — growth OKRs & metrics"
        )

    return "Unknown growth command. Try `growth help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] growth-hacker started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "growth-hacker",
                    "message": response,
                })
                logger.info("growth-hacker: handled command: %s", message[:60])

        experiments = load_experiments()
        write_state({
            "bot": "growth-hacker",
            "ts": now_iso(),
            "status": "running",
            "total_experiments": len(experiments),
            "active_experiments": sum(1 for e in experiments if e.get("status") == "running"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
