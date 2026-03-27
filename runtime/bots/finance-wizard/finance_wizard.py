"""Finance Wizard Bot — Financial modeling, projections, and investor prep.

Handles all financial aspects of running and growing a business:
  - P&L projections and financial modeling
  - Investor pitch financial slides
  - Revenue model design
  - Burn rate calculation and runway analysis
  - Funding round preparation
  - Unit economics analysis
  - Break-even analysis
  - Cash flow forecasting
  - Cap table modeling
  - Pricing strategy

Commands (via chatlog / WhatsApp / Dashboard):
  finance model <business>         — complete financial model
  finance pl <revenue> <costs>     — P&L projection
  finance runway <burn> <cash>     — runway & burn rate analysis
  finance raise <stage> <amount>   — fundraising round prep
  finance unit <product> <price>   — unit economics analysis
  finance pricing <product>        — pricing strategy
  finance capex <business>         — CAPEX/OPEX breakdown
  finance kpis <business_type>     — key financial KPIs
  finance pitch <company>          — investor financial narrative
  finance valuation <company>      — valuation methodology
  finance status                   — current financial models

State files:
  ~/.ai-employee/state/finance-wizard.state.json
  ~/.ai-employee/state/finance-models.json
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
STATE_FILE = AI_HOME / "state" / "finance-wizard.state.json"
MODELS_FILE = AI_HOME / "state" / "finance-models.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("FINANCE_WIZARD_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("finance-wizard")

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


def load_models() -> list:
    if not MODELS_FILE.exists():
        return []
    try:
        return json.loads(MODELS_FILE.read_text())
    except Exception:
        return []


def save_models(models: list) -> None:
    MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODELS_FILE.write_text(json.dumps(models, indent=2))


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


SYSTEM_FINANCE = (
    "You are a CFO and financial modeling expert with experience at top investment banks "
    "and venture-backed startups. You create precise, investor-grade financial models "
    "and analyses. Use realistic numbers, industry benchmarks, and clear assumptions. "
    "Always show your work and state your assumptions."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_model(business: str) -> str:
    result = ai_query(
        f"Create a complete 3-year financial model for: {business}\n\n"
        "## Assumptions\n"
        "List all key assumptions (market size, growth rate, pricing, margins)\n\n"
        "## Year 1 Monthly P&L\n"
        "Table: Month | Revenue | COGS | Gross Profit | OpEx | EBITDA | Net Income\n\n"
        "## Annual Summary (Year 1, 2, 3)\n"
        "| Metric | Year 1 | Year 2 | Year 3 |\n"
        "| Revenue | $X | $X | $X |\n"
        "| Gross Margin | X% | X% | X% |\n"
        "| EBITDA | $X | $X | $X |\n"
        "| Net Income | $X | $X | $X |\n"
        "| Headcount | X | X | X |\n\n"
        "## Unit Economics\n"
        "CAC, LTV, LTV:CAC ratio, payback period\n\n"
        "## Cash Flow Projection\n"
        "Monthly cash position with burn rate\n\n"
        "## Break-Even Analysis\n"
        "When does the business break even and why\n\n"
        "## Funding Requirements\n"
        "How much capital needed and when\n\n"
        "## Key Financial Risks\n"
        "Top 3 risks and sensitivity analysis",
        SYSTEM_FINANCE,
    )
    models = load_models()
    models.insert(0, {"id": str(uuid.uuid4())[:8], "business": business, "created_at": now_iso(), "type": "model"})
    save_models(models[:20])
    return result


def cmd_pl(revenue: str, costs: str) -> str:
    return ai_query(
        f"Create a detailed P&L projection.\n"
        f"Revenue context: {revenue}\n"
        f"Cost structure: {costs}\n\n"
        "Provide:\n"
        "## P&L Statement (12-month monthly)\n"
        "| Month | Revenue | COGS | Gross Profit | GM% | S&M | R&D | G&A | Total OpEx | EBITDA | EBITDA% |\n"
        "Fill in realistic numbers based on the revenue and cost inputs.\n\n"
        "## Revenue Breakdown\n"
        "How revenue grows month by month with growth rate assumptions\n\n"
        "## Cost Breakdown\n"
        "Variable vs fixed costs, scaling assumptions\n\n"
        "## Key Metrics\n"
        "- Gross margin trend\n"
        "- Operating leverage (as revenue grows, margins improve by X%)\n"
        "- Path to profitability\n\n"
        "## Sensitivity Table\n"
        "Best/Base/Worst case scenarios",
        SYSTEM_FINANCE,
    )


def cmd_runway(burn: str, cash: str) -> str:
    return ai_query(
        f"Analyze runway and burn rate.\n"
        f"Monthly burn: {burn}\n"
        f"Cash on hand: {cash}\n\n"
        "Provide:\n"
        "## Runway Analysis\n"
        "- Current runway in months\n"
        "- Runway under 3 scenarios (optimistic/base/pessimistic growth)\n"
        "- When to raise next round (ideal timing)\n\n"
        "## Burn Breakdown\n"
        "How to categorize and analyze the burn by function\n\n"
        "## Burn Reduction Options\n"
        "5 specific ways to extend runway without killing growth\n\n"
        "## Fundraising Timeline\n"
        "If raising: when to start, process timeline, amount to raise\n\n"
        "## Monthly Milestones\n"
        "What metrics to hit each month to maintain investor confidence\n\n"
        "## Red Flags to Monitor\n"
        "Warning signs the burn is unsustainable",
        SYSTEM_FINANCE,
    )


def cmd_raise(stage: str, amount: str) -> str:
    return ai_query(
        f"Prepare a funding round: {stage} for {amount}\n\n"
        "## Round Overview\n"
        "- Stage definition and typical characteristics\n"
        "- Valuation range expectation\n"
        "- Dilution impact\n\n"
        "## Pre-Money Valuation\n"
        "How to justify valuation at this stage\n"
        "- Revenue multiples (if applicable)\n"
        "- Comparables analysis\n"
        "- Milestone-based valuation\n\n"
        "## Use of Funds\n"
        "Specific allocation of the {amount} raised:\n"
        "- Headcount: X% ($X)\n"
        "- Product/Tech: X% ($X)\n"
        "- Marketing: X% ($X)\n"
        "- Operations: X% ($X)\n"
        "- Reserve: X% ($X)\n\n"
        "## Investor Targeting\n"
        "- Types of investors to target\n"
        "- Tier 1 VCs to approach (by stage)\n"
        "- Angels vs. institutional\n\n"
        "## Term Sheet Key Terms\n"
        "What to expect and what to negotiate\n\n"
        "## Due Diligence Checklist\n"
        "What investors will ask for — be prepared\n\n"
        "## Timeline\n"
        "Realistic fundraising process: outreach → close",
        SYSTEM_FINANCE,
    )


def cmd_unit_economics(product: str, price: str) -> str:
    return ai_query(
        f"Analyze unit economics for: {product} at {price}\n\n"
        "Calculate and explain:\n"
        "## Revenue Metrics\n"
        "- Average Revenue Per User (ARPU)\n"
        "- Monthly Recurring Revenue (MRR) potential\n"
        "- Annual Contract Value (ACV)\n\n"
        "## Cost Metrics\n"
        "- Cost of Goods Sold (COGS) per unit\n"
        "- Gross Margin per unit\n"
        "- Customer Acquisition Cost (CAC) estimate\n\n"
        "## Customer Lifetime Value\n"
        "- LTV calculation with assumptions\n"
        "- Churn rate assumption and impact\n"
        "- LTV:CAC ratio (target: >3x)\n"
        "- CAC payback period (target: <12 months)\n\n"
        "## Margin Expansion Path\n"
        "How margins improve at scale\n\n"
        "## Pricing Sensitivity\n"
        "How a 10%/25%/50% price change affects metrics\n\n"
        "## Benchmark Comparison\n"
        "How these metrics compare to industry standards",
        SYSTEM_FINANCE,
    )


def cmd_pricing(product: str) -> str:
    return ai_query(
        f"Design an optimal pricing strategy for: {product}\n\n"
        "## Pricing Model Options\n"
        "Analyze 3 pricing models:\n"
        "1. [Model 1]: pros, cons, best for when\n"
        "2. [Model 2]: pros, cons, best for when\n"
        "3. [Model 3]: pros, cons, best for when\n\n"
        "## Recommended Pricing\n"
        "- Price point recommendation with justification\n"
        "- Psychological pricing tactics\n"
        "- Tiered pricing structure (if applicable)\n\n"
        "## Competitive Pricing Analysis\n"
        "How to price vs competitors (premium/parity/discount)\n\n"
        "## Freemium / Free Trial Analysis\n"
        "Should you offer free tier? What features?\n\n"
        "## Price Increase Strategy\n"
        "When and how to raise prices over time\n\n"
        "## Revenue Optimization\n"
        "Upsell/cross-sell opportunities",
        SYSTEM_FINANCE,
    )


def cmd_kpis(business_type: str) -> str:
    return ai_query(
        f"Define the key financial KPIs for a {business_type} business.\n\n"
        "## North Star Metric\n"
        "The single most important metric and why\n\n"
        "## Revenue KPIs (5-7)\n"
        "Each with: definition, target benchmark, how to calculate\n\n"
        "## Cost KPIs (4-5)\n"
        "Each with: definition, target benchmark, danger zones\n\n"
        "## Growth KPIs (4-5)\n"
        "Each with: definition, industry benchmark\n\n"
        "## Efficiency KPIs (3-4)\n"
        "Productivity and capital efficiency metrics\n\n"
        "## Dashboard Template\n"
        "Weekly / Monthly / Quarterly review cadence\n"
        "Which metrics to review when\n\n"
        "## Leading vs Lagging Indicators\n"
        "Which metrics predict future performance",
        SYSTEM_FINANCE,
    )


def cmd_pitch_financials(company: str) -> str:
    return ai_query(
        f"Create investor-grade financial narrative for: {company}\n\n"
        "## Financial Story\n"
        "The narrative arc: where we are, how we got here, where we're going\n\n"
        "## Key Financial Highlights (for pitch deck)\n"
        "5-7 most impressive metrics in bullet format\n\n"
        "## 3-Year Forecast Slides\n"
        "How to present Year 1/2/3 numbers compellingly\n\n"
        "## Unit Economics Slide\n"
        "How to visualize LTV:CAC and payback period\n\n"
        "## Market Opportunity Slide (financial lens)\n"
        "TAM/SAM/SOM with bottom-up math\n\n"
        "## Funding Ask Slide\n"
        "Use of funds with milestone-based narrative\n\n"
        "## Investor Questions to Prepare For\n"
        "Top 10 tough financial questions and strong answers\n\n"
        "## Financial Red Flags to Preempt\n"
        "Address before investors ask",
        SYSTEM_FINANCE,
    )


def cmd_valuation(company: str) -> str:
    return ai_query(
        f"Analyze valuation methodology for: {company}\n\n"
        "## Valuation Methods\n"
        "Apply 3 methods:\n"
        "1. **Comparable Companies** — revenue/EBITDA multiples\n"
        "2. **DCF Analysis** — discounted cash flow (with assumptions)\n"
        "3. **Venture Method** — expected exit value × ownership\n\n"
        "## Valuation Range\n"
        "Low / Mid / High scenarios with reasoning\n\n"
        "## Key Value Drivers\n"
        "What factors most affect valuation (positive)\n\n"
        "## Value Destroyers\n"
        "What will suppress valuation (risks)\n\n"
        "## How to Increase Valuation\n"
        "5 specific actions in next 6 months to justify higher valuation\n\n"
        "## Investor Perspective\n"
        "What return does this represent for a $Xm check at this valuation?\n\n"
        "## Comparable Exits\n"
        "3-5 relevant acquisitions/IPOs in the space",
        SYSTEM_FINANCE,
    )


def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "finance-wizard.queue.jsonl"
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
    result = ai_query(instructions, SYSTEM_FINANCE)
    write_orchestrator_result(subtask_id, result)
    logger.info("finance-wizard: completed subtask '%s'", subtask_id)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("finance ") and msg_lower != "finance":
        return None

    rest = msg[8:].strip() if msg_lower.startswith("finance ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("model "):
        return cmd_model(rest[6:].strip())
    if rest_lower.startswith("pl "):
        parts = rest[3:].strip().split(" costs:", 1)
        revenue = parts[0].strip()
        costs = parts[1].strip() if len(parts) > 1 else "typical startup costs"
        return cmd_pl(revenue, costs)
    if rest_lower.startswith("runway "):
        parts = rest[7:].strip().split(" cash:", 1)
        burn = parts[0].strip()
        cash = parts[1].strip() if len(parts) > 1 else "unknown"
        return cmd_runway(burn, cash)
    if rest_lower.startswith("raise "):
        parts = rest[6:].strip().split(" for ", 1)
        stage = parts[0].strip()
        amount = parts[1].strip() if len(parts) > 1 else "to be determined"
        return cmd_raise(stage, amount)
    if rest_lower.startswith("unit "):
        parts = rest[5:].strip().split(" at ", 1)
        product = parts[0].strip()
        price = parts[1].strip() if len(parts) > 1 else "market rate"
        return cmd_unit_economics(product, price)
    if rest_lower.startswith("pricing "):
        return cmd_pricing(rest[8:].strip())
    if rest_lower.startswith("kpis "):
        return cmd_kpis(rest[5:].strip())
    if rest_lower.startswith("pitch "):
        return cmd_pitch_financials(rest[6:].strip())
    if rest_lower.startswith("valuation "):
        return cmd_valuation(rest[10:].strip())
    if rest_lower == "status":
        models = load_models()
        if not models:
            return "No financial models yet. Try: `finance model <business>`"
        lines = ["💰 *Finance Models:*"]
        for m in models[:5]:
            lines.append(f"  • `{m['id']}` — {m.get('business','?')[:50]} ({m.get('type','?')})")
        return "\n".join(lines)
    if rest_lower == "help" or not rest_lower:
        return (
            "💰 *Finance Wizard Commands:*\n"
            "  `finance model <business>` — complete financial model\n"
            "  `finance pl <revenue> costs:<costs>` — P&L projection\n"
            "  `finance runway <burn> cash:<amount>` — runway analysis\n"
            "  `finance raise <stage> for <amount>` — fundraising prep\n"
            "  `finance unit <product> at <price>` — unit economics\n"
            "  `finance pricing <product>` — pricing strategy\n"
            "  `finance kpis <business_type>` — key financial KPIs\n"
            "  `finance pitch <company>` — investor financials\n"
            "  `finance valuation <company>` — valuation analysis"
        )

    return "Unknown finance command. Try `finance help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] finance-wizard started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "finance-wizard",
                    "message": response,
                })
                logger.info("finance-wizard: handled command: %s", message[:60])

        models = load_models()
        write_state({
            "bot": "finance-wizard",
            "ts": now_iso(),
            "status": "running",
            "total_models": len(models),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
