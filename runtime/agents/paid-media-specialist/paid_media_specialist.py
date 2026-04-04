"""Paid Media Specialist Bot — PPC, paid social, and performance media strategy.

Provides comprehensive paid media management capabilities:
  - Google Ads account architecture and campaign design
  - Meta (Facebook/Instagram) Ads strategy and creative guidance
  - PPC campaign audits and performance diagnosis
  - Budget allocation across platforms
  - Bidding strategy selection and transitions
  - Keyword strategy (match types, negatives, search term analysis)
  - Ad copy creation (RSAs, ETA, Meta ad creative)
  - Audience strategy (first-party data, lookalikes, in-market)
  - Conversion tracking setup and measurement
  - Monthly performance reporting and optimization plans

Commands (via chatlog / WhatsApp / Dashboard):
  ppc build <business/goal>        — design new account structure from scratch
  ppc audit <account/description>  — diagnose performance issues
  ppc budget <goal> <spend>        — budget allocation framework
  ppc keywords <product/service>   — keyword strategy and match types
  ppc adcopy <product/audience>    — write ad copy variants (RSA, Meta)
  ppc audiences <business>         — audience strategy and targeting plan
  ppc tracking <platform/goal>     — conversion tracking setup guide
  ppc report <metrics>             — performance analysis and action plan
  ppc forecast <budget/goal>       — forecast expected results
  ppc diagnose <issue>             — diagnose specific performance problem
  ppc status                       — current campaigns and performance

State files:
  ~/.ai-employee/state/paid-media-specialist.state.json
  ~/.ai-employee/state/ppc-campaigns.json
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
STATE_FILE = AI_HOME / "state" / "paid-media-specialist.state.json"
CAMPAIGNS_FILE = AI_HOME / "state" / "ppc-campaigns.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("PPC_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("paid-media-specialist")

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
        result = _query_ai_for_agent("paid-media-specialist", prompt, system_prompt=system_prompt)
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


SYSTEM_PPC = (
    "You are a senior paid media strategist with deep expertise in Google Ads, Meta Ads, "
    "Microsoft Advertising, and performance marketing. "
    "You've managed accounts from $10K to $1M+ monthly spend. "
    "You think in account structure as strategy — how the entire system of campaigns, "
    "ad groups, audiences, and signals work together to drive business outcomes. "
    "You're data-driven and ROI-obsessed. You diagnose performance problems systematically. "
    "You know when to use each campaign type, bidding strategy, and audience approach. "
    "Always provide specific, actionable recommendations with expected impact."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_build(business_goal: str) -> str:
    return ai_query(
        f"Design a paid media account structure for: {business_goal}\n\n"
        "## Account Architecture\n"
        "Campaign structure with campaign names, types, and purposes:\n"
        "- Brand campaigns (exact + phrase)\n"
        "- Non-brand campaigns by category/intent\n"
        "- Competitor/conquest campaigns\n"
        "- Remarketing campaigns\n"
        "- Performance Max campaigns (if applicable)\n\n"
        "## Budget Allocation\n"
        "Recommended split across campaigns with rationale\n\n"
        "## Bidding Strategy\n"
        "Starting bid strategy for each campaign with transition plan as data accrues\n\n"
        "## Keyword Strategy\n"
        "Core keyword themes with match type guidance\n\n"
        "## Audience Setup\n"
        "Audiences to build and apply (observation vs. targeting)\n\n"
        "## 30-Day Launch Plan\n"
        "Week-by-week actions for the first month\n\n"
        "## KPIs and Targets\n"
        "Primary KPIs with target ranges",
        SYSTEM_PPC,
    )


def cmd_audit(account_description: str) -> str:
    return ai_query(
        f"Audit paid media account and diagnose issues: {account_description}\n\n"
        "## Performance Diagnosis Framework\n"
        "Check in this order:\n"
        "1. **Auction-level**: Impression share trends, competitor activity\n"
        "2. **Budget**: Impression share lost to budget, pacing\n"
        "3. **Bid**: Strategy changes, learning period issues\n"
        "4. **Quality**: Ad relevance, landing page experience\n"
        "5. **Match-type**: Search term quality, irrelevant queries\n"
        "6. **Tracking**: Conversion recording correctly?\n\n"
        "## Issues Found (by priority)\n"
        "**Critical (immediate action)**: [List]\n"
        "**High (fix this week)**: [List]\n"
        "**Medium (fix this month)**: [List]\n"
        "**Quick Wins**: [Low effort, high impact]\n\n"
        "## Optimization Action Plan\n"
        "Prioritized list of changes with expected impact\n\n"
        "## Structural Improvements\n"
        "Long-term account restructuring recommendations",
        SYSTEM_PPC,
    )


def cmd_budget(goal_and_spend: str) -> str:
    return ai_query(
        f"Budget allocation framework for: {goal_and_spend}\n\n"
        "## Platform Allocation\n"
        "Recommended split across Google/Meta/Microsoft/other with rationale\n\n"
        "## Campaign-Level Allocation\n"
        "Budget breakdown by campaign type:\n"
        "| Campaign | Budget | % of Total | Goal | Expected CPA/ROAS |\n\n"
        "## Pacing Strategy\n"
        "Daily budget settings vs. monthly caps approach\n\n"
        "## Scaling Logic\n"
        "When and how to increase budget (performance thresholds to hit first)\n\n"
        "## Diminishing Returns Analysis\n"
        "At what spend level does efficiency start declining?\n\n"
        "## Seasonal Adjustments\n"
        "Budget flex recommendations for peak vs. off-peak periods\n\n"
        "## Expected Outcomes\n"
        "Projected clicks, conversions, and revenue at this budget",
        SYSTEM_PPC,
    )


def cmd_keywords(product_service: str) -> str:
    return ai_query(
        f"Keyword strategy for: {product_service}\n\n"
        "## Core Keyword Themes\n"
        "5-8 keyword themes with description and search intent\n\n"
        "## Keyword Examples per Theme\n"
        "10 example keywords per theme (high value ones)\n\n"
        "## Match Type Strategy\n"
        "Which match types to use for which keyword types and why\n\n"
        "## Negative Keyword List\n"
        "50+ negative keywords organized by category (irrelevant, competitor brand, low-intent)\n\n"
        "## Long-Tail Opportunities\n"
        "High-intent, lower-competition long-tail variations\n\n"
        "## Competitor Keyword Strategy\n"
        "How to approach competitor terms (bid on them? exclude them?)\n\n"
        "## Search Term Monitoring\n"
        "Process for reviewing search terms weekly and adding negatives",
        SYSTEM_PPC,
    )


def cmd_adcopy(product_audience: str) -> str:
    return ai_query(
        f"Write ad copy variants for: {product_audience}\n\n"
        "## Google Responsive Search Ads (RSA)\n"
        "For 2 ad groups:\n"
        "- 15 headlines (30 chars max) with [PIN] notation for must-show\n"
        "- 4 descriptions (90 chars max)\n"
        "- Testing rationale for each variant\n\n"
        "## Meta (Facebook/Instagram) Ad Copy\n"
        "3 complete ad variants with:\n"
        "- Primary text (125 chars for feed preview)\n"
        "- Headline (27 chars)\n"
        "- Description (27 chars)\n"
        "- Image/video concept\n"
        "- Target audience for each variant\n\n"
        "## Call-to-Action Strategy\n"
        "Which CTAs to test and for which funnel stage\n\n"
        "## A/B Testing Plan\n"
        "What hypothesis each variant is testing",
        SYSTEM_PPC,
    )


def cmd_audiences(business: str) -> str:
    return ai_query(
        f"Audience strategy for paid media: {business}\n\n"
        "## First-Party Audiences\n"
        "Customer lists to build and how to use them:\n"
        "- Customer Match (email lists)\n"
        "- Website visitors (segmented)\n"
        "- App users (if applicable)\n"
        "- CRM segments\n\n"
        "## Lookalike / Similar Audiences\n"
        "Which first-party lists to use as seeds and expansion strategy\n\n"
        "## In-Market and Affinity Audiences\n"
        "Top 10 relevant audiences with rationale\n\n"
        "## Retargeting Strategy\n"
        "Segmentation by recency and behavior with different messaging\n\n"
        "## Exclusions\n"
        "Who to exclude and why\n\n"
        "## Observation vs. Targeting\n"
        "Which audiences to observe first before targeting\n\n"
        "## Audience Hierarchy\n"
        "Priority order for audience targeting when budgets are limited",
        SYSTEM_PPC,
    )


def cmd_tracking(platform_goal: str) -> str:
    return ai_query(
        f"Conversion tracking setup guide for: {platform_goal}\n\n"
        "## Conversion Action Hierarchy\n"
        "Primary vs. secondary conversions and why this matters for bidding\n\n"
        "## Google Ads Tracking Setup\n"
        "- Tag implementation (Google Tag Manager recommended)\n"
        "- Conversion action settings (counting, attribution model, lookback)\n"
        "- Enhanced conversions setup (if applicable)\n\n"
        "## Meta Pixel Setup\n"
        "- Standard events to implement\n"
        "- Custom conversions setup\n"
        "- Conversions API (CAPI) setup for iOS 14+ impact\n\n"
        "## Verification Steps\n"
        "How to verify tracking is working correctly\n\n"
        "## Attribution Model Guidance\n"
        "Which attribution model to use and cross-platform considerations\n\n"
        "## Reporting Setup\n"
        "Dashboards and alerts to monitor tracking health",
        SYSTEM_PPC,
    )


def cmd_report(metrics: str) -> str:
    return ai_query(
        f"Performance analysis and action plan for: {metrics}\n\n"
        "## Performance Summary\n"
        "Key metrics assessment vs. targets and benchmarks\n\n"
        "## What's Working\n"
        "Top performing campaigns/ad groups/keywords to scale\n\n"
        "## What's Not Working\n"
        "Underperformers to fix or pause with specific diagnostics\n\n"
        "## Trend Analysis\n"
        "Week-over-week and month-over-month performance trends\n\n"
        "## Optimization Priorities\n"
        "Top 5 changes to make this week ranked by expected impact\n\n"
        "## Opportunities Identified\n"
        "New campaigns, keywords, or audiences to test\n\n"
        "## Next Month Goals\n"
        "Revised targets and strategy adjustments",
        SYSTEM_PPC,
    )


def cmd_forecast(budget_goal: str) -> str:
    return ai_query(
        f"Forecast expected paid media results for: {budget_goal}\n\n"
        "## Forecast Methodology\n"
        "Assumptions used (avg CPC, CVR, CTR benchmarks for this industry)\n\n"
        "## Conservative / Base / Optimistic Scenarios\n"
        "| Metric | Conservative | Base Case | Optimistic |\n"
        "| Monthly Spend | | | |\n"
        "| Impressions | | | |\n"
        "| Clicks | | | |\n"
        "| Conversions | | | |\n"
        "| CPA | | | |\n"
        "| ROAS | | | |\n\n"
        "## Key Assumptions\n"
        "Industry benchmarks used and data sources\n\n"
        "## Confidence Level\n"
        "How reliable this forecast is and what would change it\n\n"
        "## Milestones to Hit\n"
        "Leading indicators to track in first 30/60/90 days",
        SYSTEM_PPC,
    )


def cmd_diagnose(issue: str) -> str:
    return ai_query(
        f"Diagnose this paid media performance issue: {issue}\n\n"
        "## Root Cause Analysis\n"
        "Most likely causes ranked by probability\n\n"
        "## Diagnostic Steps\n"
        "Step-by-step investigation: what to check and in what order\n\n"
        "## Data to Collect\n"
        "Specific reports and metrics to pull to confirm the diagnosis\n\n"
        "## Fix Options\n"
        "Solutions ranked by impact and ease of implementation\n\n"
        "## Prevention\n"
        "How to prevent this issue recurring with monitoring alerts\n\n"
        "## Timeline\n"
        "How quickly should this be addressed? (immediate / this week / this month)",
        SYSTEM_PPC,
    )


def cmd_status() -> str:
    campaigns = load_campaigns()
    if not campaigns:
        return "No paid media campaigns recorded yet."
    lines = ["## Paid Media Campaigns\n"]
    for c in campaigns[:10]:
        lines.append(f"- [{c.get('type', 'ppc')}] {c.get('description', '')[:80]} — {c.get('created_at', '')[:10]}")
    return "\n".join(lines)


# ── Message Routing ────────────────────────────────────────────────────────────

COMMANDS = {
    "ppc build": (cmd_build, 1),
    "ppc audit": (cmd_audit, 1),
    "ppc budget": (cmd_budget, 1),
    "ppc keywords": (cmd_keywords, 1),
    "ppc adcopy": (cmd_adcopy, 1),
    "ppc audiences": (cmd_audiences, 1),
    "ppc tracking": (cmd_tracking, 1),
    "ppc report": (cmd_report, 1),
    "ppc forecast": (cmd_forecast, 1),
    "ppc diagnose": (cmd_diagnose, 1),
    "ppc status": (lambda: cmd_status(), 0),
}


def process_message(text: str) -> str | None:
    text_lower = text.strip().lower()
    for prefix, (handler, needs_arg) in COMMANDS.items():
        if text_lower.startswith(prefix):
            arg = text[len(prefix):].strip() if needs_arg else ""
            campaigns = load_campaigns()
            campaigns.insert(0, {
                "id": str(uuid.uuid4())[:8],
                "type": prefix.replace("ppc ", ""),
                "description": arg[:200],
                "created_at": now_iso(),
            })
            save_campaigns(campaigns[:50])
            if needs_arg:
                return handler(arg)
            return handler()
    return None


def process_queue() -> None:
    queue_file = AGENT_TASKS_DIR / "paid-media-specialist.queue.jsonl"
    if not queue_file.exists():
        return
    lines = queue_file.read_text().splitlines()
    remaining = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            task = json.loads(line)
        except Exception:
            continue
        if task.get("status") == "pending":
            result = process_message(task.get("input", ""))
            if result:
                write_orchestrator_result(task["subtask_id"], result)
                task["status"] = "done"
            else:
                task["status"] = "unhandled"
                write_orchestrator_result(
                    task["subtask_id"],
                    f"Paid Media Specialist could not process: {task.get('input', '')}",
                    status="unhandled",
                )
        remaining.append(json.dumps(task))
    queue_file.write_text("\n".join(remaining) + "\n" if remaining else "")


# ── Main Loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    state = {
        "agent": "paid-media-specialist",
        "started_at": now_iso(),
        "status": "running",
        "last_poll": now_iso(),
    }
    write_state(state)
    logger.info("Paid Media Specialist started.")
    processed: set = set()

    while True:
        try:
            process_queue()
            entries = load_chatlog()
            for entry in entries:
                eid = entry.get("id") or entry.get("ts") or str(entry)
                if eid in processed:
                    continue
                role = entry.get("role", "")
                text = entry.get("text", "") or entry.get("content", "")
                if role == "user" and text.strip().lower().startswith("ppc "):
                    result = process_message(text)
                    if result:
                        append_chatlog({
                            "id": str(uuid.uuid4()),
                            "role": "assistant",
                            "agent": "paid-media-specialist",
                            "text": result,
                            "ts": now_iso(),
                        })
                processed.add(eid)

            state["last_poll"] = now_iso()
            write_state(state)
        except Exception as exc:
            logger.error("Paid Media Specialist error: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
