"""Company Builder Bot — Build a company from scratch with AI simulations.

Guides users through every phase of starting and running a business:
  - Business idea validation and market fit analysis
  - Full business plan generation with financial projections
  - Organizational structure and team design
  - Market entry simulation with competitive landscape
  - Go-to-market strategy and milestone roadmap
  - Operational workflows and SOP creation
  - Investor pitch deck preparation
  - Company simulation with scenario modeling

Commands (via chatlog / WhatsApp / Dashboard):
  company build <idea>             — full company launch package
  company validate <idea>          — validate business idea viability
  company plan <idea>              — detailed business plan
  company org <size> <industry>    — org chart and team structure
  company simulate <scenario>      — run company growth simulation
  company gtm <product> <market>   — go-to-market strategy
  company milestones <goal>        — 12-month milestone roadmap
  company pitch <company_name>     — investor pitch deck outline
  company status                   — current project status
  company swot <business>          — SWOT analysis

State files:
  ~/.ai-employee/state/company-builder.state.json
  ~/.ai-employee/state/company-builder-projects.json
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
STATE_FILE = AI_HOME / "state" / "company-builder.state.json"
PROJECTS_FILE = AI_HOME / "state" / "company-builder-projects.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("COMPANY_BUILDER_POLL_INTERVAL", "5"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("company-builder")

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
        return "AI router not available. Please ensure ai-router is configured."
    try:
        result = _query_ai(prompt, system_prompt=system_prompt)
        return result.get("answer", "No response generated.")
    except Exception as exc:
        logger.warning("company-builder: AI query failed — %s", exc)
        return f"AI query failed: {exc}"


def write_orchestrator_result(subtask_id: str, result_text: str, status: str = "done") -> None:
    """Write result so task-orchestrator can pick it up."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"{subtask_id}.json"
    result_file.write_text(json.dumps({
        "subtask_id": subtask_id,
        "status": status,
        "result": result_text,
        "completed_at": now_iso(),
    }))


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_validate(idea: str) -> str:
    system = (
        "You are an expert business analyst and startup advisor. "
        "Evaluate the viability of business ideas with real market data. "
        "Be honest, practical, and data-driven."
    )
    prompt = (
        f"Validate this business idea: {idea}\n\n"
        "Provide:\n"
        "1. **Market Opportunity** — size, growth rate, target segments\n"
        "2. **Problem-Solution Fit** — does it solve a real pain point?\n"
        "3. **Competitive Landscape** — who else is doing this?\n"
        "4. **Unique Value Proposition** — what makes this different?\n"
        "5. **Revenue Potential** — realistic TAM/SAM/SOM estimates\n"
        "6. **Key Risks** — what could go wrong?\n"
        "7. **Viability Score** — 1-10 with explanation\n"
        "8. **Recommendation** — proceed / pivot / abandon\n\n"
        "Be specific with numbers and examples."
    )
    return ai_query(prompt, system)


def cmd_plan(idea: str) -> str:
    system = (
        "You are a McKinsey-level business strategist and startup founder. "
        "Create comprehensive, actionable business plans that actually work. "
        "Include real financial projections and specific action steps."
    )
    prompt = (
        f"Create a full business plan for: {idea}\n\n"
        "Structure:\n"
        "## Executive Summary\n"
        "## Company Description & Mission\n"
        "## Products/Services\n"
        "## Market Analysis (with data)\n"
        "## Competitive Analysis\n"
        "## Marketing & Sales Strategy\n"
        "## Operations Plan\n"
        "## Team & Organization\n"
        "## Financial Projections (Year 1-3: Revenue, Costs, Profit)\n"
        "## Funding Requirements\n"
        "## Key Milestones (90-day, 6-month, 12-month)\n"
        "## Risk Mitigation\n\n"
        "Be specific with numbers, timelines, and actionable steps."
    )
    return ai_query(prompt, system)


def cmd_org(size: str, industry: str) -> str:
    system = (
        "You are an organizational design expert with experience at top companies. "
        "Design practical org structures optimized for growth and efficiency."
    )
    prompt = (
        f"Design an optimal organizational structure for a {size}-person {industry} company.\n\n"
        "Include:\n"
        "1. **Org Chart** — departments and reporting lines (text-based diagram)\n"
        "2. **Key Roles** — title, responsibilities, required skills for each position\n"
        "3. **Hiring Priority** — first 5 hires in order of importance\n"
        "4. **Compensation Ranges** — realistic salary/equity ranges\n"
        "5. **Team Collaboration** — how departments work together\n"
        "6. **Scaling Plan** — how org evolves from current size to 2x and 5x\n"
        "7. **Culture Guidelines** — core values and working principles\n"
    )
    return ai_query(prompt, system)


def cmd_simulate(scenario: str) -> str:
    system = (
        "You are a business simulation expert. Run detailed what-if scenarios "
        "with realistic financial modeling and strategic implications."
    )
    prompt = (
        f"Run a business simulation for this scenario: {scenario}\n\n"
        "Simulate over 12 months. Include:\n"
        "1. **Baseline Assumptions** — starting metrics and market conditions\n"
        "2. **Month-by-Month Projection** — revenue, customers, burn rate, team size\n"
        "3. **Key Decision Points** — critical choices at each phase\n"
        "4. **Best Case Scenario** — if everything goes right\n"
        "5. **Base Case Scenario** — realistic outcome\n"
        "6. **Worst Case Scenario** — major risks materializing\n"
        "7. **Pivot Options** — if base case underperforms\n"
        "8. **Success Metrics** — KPIs to track progress\n"
        "Use specific numbers and percentages."
    )
    return ai_query(prompt, system)


def cmd_gtm(product: str, market: str) -> str:
    system = (
        "You are a go-to-market strategy expert who has launched dozens of products. "
        "Create actionable, channel-specific GTM strategies with real tactics."
    )
    prompt = (
        f"Create a go-to-market strategy for: {product} targeting {market}\n\n"
        "Include:\n"
        "1. **Target Customer Profile** — detailed ICP with demographics and psychographics\n"
        "2. **Positioning Statement** — how to position vs competitors\n"
        "3. **Pricing Strategy** — pricing tiers with rationale\n"
        "4. **Distribution Channels** — primary and secondary channels ranked by ROI\n"
        "5. **Launch Sequence** — week-by-week launch plan\n"
        "6. **Content & Messaging** — key messages for each customer segment\n"
        "7. **Acquisition Tactics** — specific tactics for first 100 customers\n"
        "8. **Budget Allocation** — recommended spend breakdown\n"
        "9. **Success Metrics** — 30/60/90 day KPIs\n"
    )
    return ai_query(prompt, system)


def cmd_milestones(goal: str) -> str:
    system = (
        "You are an expert startup advisor and OKR coach. "
        "Create realistic, measurable milestone roadmaps."
    )
    prompt = (
        f"Create a 12-month milestone roadmap for: {goal}\n\n"
        "Format as:\n"
        "**Month 1-2: Foundation Phase**\n"
        "- Milestone 1: [specific, measurable]\n"
        "- Milestone 2: ...\n"
        "- Key metrics to hit: ...\n\n"
        "Continue for each 2-month phase (Foundation, MVP, Traction, Growth, Scale, Optimization).\n"
        "For each milestone: include success criteria, owner role, and dependencies.\n"
        "End with: 12-month success definition and critical success factors."
    )
    return ai_query(prompt, system)


def cmd_pitch(company_name: str) -> str:
    system = (
        "You are a pitch deck expert who has helped raise $500M+ for startups. "
        "Create compelling investor narratives that win deals."
    )
    prompt = (
        f"Create an investor pitch deck outline for: {company_name}\n\n"
        "Cover all 12 essential slides:\n"
        "1. **Cover** — company name, tagline, date\n"
        "2. **Problem** — the pain point (with data)\n"
        "3. **Solution** — your product/service\n"
        "4. **Market Size** — TAM/SAM/SOM with sources\n"
        "5. **Business Model** — how you make money\n"
        "6. **Traction** — current metrics and growth\n"
        "7. **Competitive Advantage** — why you win\n"
        "8. **Go-to-Market** — customer acquisition strategy\n"
        "9. **Team** — founder backgrounds and key hires\n"
        "10. **Financials** — 3-year projections + unit economics\n"
        "11. **Ask** — funding amount and use of funds\n"
        "12. **Vision** — big picture in 5-10 years\n\n"
        "For each slide: key message, data points, and talking points."
    )
    return ai_query(prompt, system)


def cmd_swot(business: str) -> str:
    system = (
        "You are a strategic business analyst. Create actionable SWOT analyses "
        "with specific recommendations, not generic platitudes."
    )
    prompt = (
        f"Perform a comprehensive SWOT analysis for: {business}\n\n"
        "**Strengths** (internal positives):\n- List 5-7 specific strengths\n\n"
        "**Weaknesses** (internal negatives):\n- List 5-7 specific weaknesses\n\n"
        "**Opportunities** (external positives):\n- List 5-7 specific opportunities with market data\n\n"
        "**Threats** (external negatives):\n- List 5-7 specific threats with likelihood/impact\n\n"
        "**Strategic Recommendations**:\n"
        "- SO strategies (use strengths to capture opportunities)\n"
        "- WO strategies (overcome weaknesses to capture opportunities)\n"
        "- ST strategies (use strengths to counter threats)\n"
        "- WT strategies (minimize weaknesses and avoid threats)\n\n"
        "End with: top 3 priority actions for the next 90 days."
    )
    return ai_query(prompt, system)


def cmd_build(idea: str) -> str:
    """Full company launch package — combines validation + plan + GTM + milestones."""
    system = (
        "You are a world-class startup builder and serial entrepreneur. "
        "Create comprehensive company launch packages that cover everything needed to start."
    )
    prompt = (
        f"Build a complete company launch package for: {idea}\n\n"
        "Create a comprehensive package covering:\n\n"
        "## 1. VALIDATION\nMarket size, problem validation, 3 target customer segments\n\n"
        "## 2. BUSINESS MODEL\nRevenue streams, pricing, unit economics, break-even\n\n"
        "## 3. PRODUCT/SERVICE\nCore offering, MVP features, roadmap phases\n\n"
        "## 4. BRAND & POSITIONING\n3 company name options, tagline, positioning statement\n\n"
        "## 5. GO-TO-MARKET\nLaunch channels, first 100 customers strategy, content plan\n\n"
        "## 6. TEAM\nFounder role, first 3 hires, required skills\n\n"
        "## 7. FINANCIALS\nStartup costs, monthly burn, path to profitability\n\n"
        "## 8. 90-DAY ACTION PLAN\nWeek-by-week specific actions\n\n"
        "Be specific with numbers, names, and actionable next steps."
    )
    result = ai_query(prompt, system)

    # Save as a project
    projects = load_projects()
    project = {
        "id": str(uuid.uuid4())[:8],
        "idea": idea,
        "created_at": now_iso(),
        "status": "active",
        "package": result[:2000],  # preview
    }
    projects.insert(0, project)
    projects = projects[:20]
    save_projects(projects)

    return result


# ── Orchestrator subtask handler ──────────────────────────────────────────────

def process_subtask(subtask: dict) -> None:
    """Handle a subtask dispatched by the task-orchestrator."""
    subtask_id = subtask.get("subtask_id", "")
    instructions = subtask.get("instructions", "")

    system = (
        "You are the Company Builder AI agent. You specialise in business strategy, "
        "company creation, financial modeling, and startup advisory. "
        "Complete the following subtask thoroughly and practically."
    )
    result = ai_query(instructions, system)
    write_orchestrator_result(subtask_id, result)
    logger.info("company-builder: completed subtask '%s'", subtask_id)


def check_agent_queue() -> list:
    """Read and consume pending subtasks from the agent queue file."""
    queue_file = AGENT_TASKS_DIR / "company-builder.queue.jsonl"
    if not queue_file.exists():
        return []
    lines = queue_file.read_text().splitlines()
    pending = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            task = json.loads(line)
            if task.get("status") != "processed":
                pending.append(task)
        except Exception:
            pass
    # Clear the queue
    if pending:
        queue_file.write_text("")
    return pending


# ── Main command dispatch ─────────────────────────────────────────────────────

def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("company "):
        return None

    rest = msg[8:].strip()
    rest_lower = rest.lower()

    if rest_lower.startswith("build "):
        return cmd_build(rest[6:].strip())
    if rest_lower.startswith("validate "):
        return cmd_validate(rest[9:].strip())
    if rest_lower.startswith("plan "):
        return cmd_plan(rest[5:].strip())
    if rest_lower.startswith("simulate "):
        return cmd_simulate(rest[9:].strip())
    if rest_lower.startswith("gtm "):
        parts = rest[4:].strip().split(" for ", 1)
        product = parts[0].strip()
        market = parts[1].strip() if len(parts) > 1 else "general market"
        return cmd_gtm(product, market)
    if rest_lower.startswith("milestones "):
        return cmd_milestones(rest[11:].strip())
    if rest_lower.startswith("pitch "):
        return cmd_pitch(rest[6:].strip())
    if rest_lower.startswith("swot "):
        return cmd_swot(rest[5:].strip())
    if rest_lower.startswith("org "):
        parts = rest[4:].strip().split(" ", 1)
        size = parts[0]
        industry = parts[1] if len(parts) > 1 else "startup"
        return cmd_org(size, industry)
    if rest_lower == "status":
        projects = load_projects()
        if not projects:
            return "No company projects yet. Try: `company build <your idea>`"
        lines = ["🏢 *Company Builder Projects:*"]
        for p in projects[:5]:
            lines.append(f"  • `{p['id']}` — {p.get('idea','?')[:50]} ({p.get('status','?')})")
        return "\n".join(lines)
    if rest_lower == "help":
        return (
            "🏢 *Company Builder Commands:*\n"
            "  `company build <idea>` — full launch package\n"
            "  `company validate <idea>` — viability check\n"
            "  `company plan <idea>` — detailed business plan\n"
            "  `company org <size> <industry>` — org structure\n"
            "  `company simulate <scenario>` — growth simulation\n"
            "  `company gtm <product> for <market>` — go-to-market\n"
            "  `company milestones <goal>` — 12-month roadmap\n"
            "  `company pitch <name>` — investor pitch deck\n"
            "  `company swot <business>` — SWOT analysis\n"
            "  `company status` — your projects"
        )

    return (
        "Unknown company command. Try:\n"
        "`company build <idea>` — full company launch package\n"
        "`company help` — all commands"
    )


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] company-builder started; poll_interval={POLL_INTERVAL}s; {ai_status}")

    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)

    last_processed_idx = len(load_chatlog())

    while True:
        # Process orchestrator subtasks
        for subtask in check_agent_queue():
            process_subtask(subtask)

        # Process chatlog commands
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
                    "bot": "company-builder",
                    "message": response,
                })
                logger.info("company-builder: handled command: %s", message[:60])

        projects = load_projects()
        write_state({
            "bot": "company-builder",
            "ts": now_iso(),
            "status": "running",
            "total_projects": len(projects),
            "active_projects": sum(1 for p in projects if p.get("status") == "active"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
