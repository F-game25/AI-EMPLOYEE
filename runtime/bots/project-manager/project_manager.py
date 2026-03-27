"""Project Manager Bot — Sprint planning, milestones, risk tracking, and Gantt output.

Provides complete project management capabilities:
  - Task breakdown and work estimation
  - Sprint planning and backlog management
  - Milestone and roadmap creation
  - Risk register and mitigation plans
  - Team coordination and RACI matrices
  - Status reporting and stakeholder updates
  - Blocker identification and escalation
  - Retrospective facilitation
  - Gantt chart generation (text-based)
  - Project health scoring

Commands (via chatlog / WhatsApp / Dashboard):
  pm start <project>               — kick off a new project
  pm breakdown <goal>              — work breakdown structure
  pm sprint <goal> <duration>      — sprint plan
  pm roadmap <project> <timeline>  — project roadmap
  pm risks <project>               — risk register
  pm raci <project> <team>         — RACI matrix
  pm status <project>              — project status report
  pm retro <sprint>                — sprint retrospective
  pm gantt <project>               — Gantt chart
  pm standup <updates>             — daily standup format
  pm blockers <issue>              — blocker resolution
  pm estimate <task>               — task estimation
  pm list                          — all current projects

State files:
  ~/.ai-employee/state/project-manager.state.json
  ~/.ai-employee/state/pm-projects.json
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
STATE_FILE = AI_HOME / "state" / "project-manager.state.json"
PROJECTS_FILE = AI_HOME / "state" / "pm-projects.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("PM_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("project-manager")

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


SYSTEM_PM = (
    "You are a Senior Project Manager and Scrum Master with PMP and CSM certifications. "
    "You have managed complex multi-team projects at Fortune 500 companies and fast-growing startups. "
    "You create clear, actionable project plans that teams can actually follow. "
    "You balance agility with structure. Be specific with timelines, owners, and success criteria."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_start(project: str) -> str:
    result = ai_query(
        f"Create a project kickoff plan for: {project}\n\n"
        "## Project Charter\n"
        "- Project name and ID\n"
        "- Business objective (what business problem does this solve?)\n"
        "- Success criteria (how will we know it's done?)\n"
        "- Scope: IN scope vs OUT of scope\n"
        "- Constraints (budget, timeline, resources)\n"
        "- Assumptions\n\n"
        "## Stakeholder Register\n"
        "| Stakeholder | Role | Interest | Influence | Engagement Strategy |\n\n"
        "## Project Timeline\n"
        "- Start date, major milestones, end date\n"
        "- Phase breakdown\n\n"
        "## Team Structure\n"
        "- Roles needed and responsibilities\n"
        "- RACI summary for key decisions\n\n"
        "## Kickoff Meeting Agenda\n"
        "60-minute kickoff meeting structure\n\n"
        "## First Sprint Goals\n"
        "Top 5 deliverables for first 2 weeks\n\n"
        "## Communication Plan\n"
        "Cadence and format for status updates",
        SYSTEM_PM,
    )
    projects = load_projects()
    projects.insert(0, {
        "id": str(uuid.uuid4())[:8],
        "name": project,
        "created_at": now_iso(),
        "status": "active",
        "phase": "kickoff",
    })
    save_projects(projects[:30])
    return result


def cmd_breakdown(goal: str) -> str:
    return ai_query(
        f"Create a Work Breakdown Structure (WBS) for: {goal}\n\n"
        "## Level 1: Project Phases\n"
        "Major phases with % of total work\n\n"
        "## Level 2: Deliverables per Phase\n"
        "For each phase, 3-5 key deliverables\n\n"
        "## Level 3: Work Packages\n"
        "For each deliverable, specific tasks with:\n"
        "- Task name\n"
        "- Description\n"
        "- Estimated hours (optimistic/realistic/pessimistic)\n"
        "- Dependencies\n"
        "- Required skills/role\n"
        "- Priority (P1/P2/P3)\n\n"
        "## Critical Path\n"
        "Which tasks must finish on time for project not to slip?\n\n"
        "## Total Effort Estimate\n"
        "Hours by phase and overall, with confidence range\n\n"
        "## Resource Requirements\n"
        "How many people of what type for how long",
        SYSTEM_PM,
    )


def cmd_sprint(goal: str, duration: str = "2 weeks") -> str:
    return ai_query(
        f"Create a sprint plan for goal: {goal}\n"
        f"Sprint duration: {duration}\n\n"
        "## Sprint Goal\n"
        "One clear sentence describing what 'done' looks like\n\n"
        "## Sprint Backlog\n"
        "User stories (with acceptance criteria):\n"
        "| ID | Story | Story Points | Priority | Assignee | Status |\n\n"
        "Format each story as:\n"
        "'As a [user type], I want to [action] so that [benefit]'\n"
        "Acceptance Criteria:\n"
        "- Given [context], when [action], then [result]\n\n"
        "## Capacity Planning\n"
        "For a 2-week sprint:\n"
        "- Available days per person (subtract meetings, PTO)\n"
        "- Story points per developer\n"
        "- Total team velocity\n\n"
        "## Definition of Done\n"
        "5-7 criteria that every story must meet\n\n"
        "## Sprint Ceremonies\n"
        "Schedule: planning, daily standup, review, retro\n\n"
        "## Risk Flags\n"
        "What might prevent sprint goal completion?",
        SYSTEM_PM,
    )


def cmd_roadmap(project: str, timeline: str = "6 months") -> str:
    return ai_query(
        f"Create a project roadmap for: {project}\n"
        f"Timeline: {timeline}\n\n"
        "## Vision and Goals\n"
        "Where are we going and why\n\n"
        "## Roadmap (visual timeline)\n"
        "```\n"
        "Month 1-2: [Phase Name]\n"
        "  ████████ Feature/Initiative 1\n"
        "  ████ Feature/Initiative 2\n"
        "Month 3-4: [Phase Name]\n"
        "  ...\n"
        "```\n\n"
        "## Milestones\n"
        "| Date | Milestone | Success Metric | Owner |\n\n"
        "## Dependencies Map\n"
        "What must happen before what\n\n"
        "## Resource Plan\n"
        "When do you need which roles\n\n"
        "## Go/No-Go Decisions\n"
        "Key decision points and criteria\n\n"
        "## Roadmap Assumptions\n"
        "What must be true for this roadmap to work\n\n"
        "## Contingency Plans\n"
        "If milestone A slips, what's the recovery plan?",
        SYSTEM_PM,
    )


def cmd_risks(project: str) -> str:
    return ai_query(
        f"Create a risk register for project: {project}\n\n"
        "## Risk Register\n"
        "| ID | Risk | Category | Probability | Impact | Score | Owner | Mitigation | Contingency |\n"
        "Categories: Technical, Resource, Timeline, Scope, External, Financial\n"
        "Probability: 1-5 | Impact: 1-5 | Score = Probability × Impact\n\n"
        "Generate 15 realistic risks specific to this project.\n\n"
        "## Top 5 Critical Risks (detailed)\n"
        "For each:\n"
        "- Risk description\n"
        "- Early warning signals\n"
        "- Prevention strategy\n"
        "- Response plan if it occurs\n"
        "- Owner and review frequency\n\n"
        "## Risk Monitoring Plan\n"
        "How and when to review risks\n\n"
        "## Risk Escalation Process\n"
        "When to escalate and to whom",
        SYSTEM_PM,
    )


def cmd_raci(project: str, team: str = "standard startup team") -> str:
    return ai_query(
        f"Create a RACI matrix for project: {project}\n"
        f"Team: {team}\n\n"
        "## RACI Matrix\n"
        "R = Responsible (does the work)\n"
        "A = Accountable (owns the outcome)\n"
        "C = Consulted (gives input)\n"
        "I = Informed (kept in the loop)\n\n"
        "| Activity/Decision | Role 1 | Role 2 | Role 3 | Role 4 | Role 5 |\n"
        "List 20 key activities/decisions for this project type\n\n"
        "## RACI Pitfalls\n"
        "Common issues to avoid (too many R's, no clear A, etc.)\n\n"
        "## Decision Rights\n"
        "Who has final say on: budget, scope, timeline, quality, team changes\n\n"
        "## Escalation Path\n"
        "When to escalate and the chain of command",
        SYSTEM_PM,
    )


def cmd_status(project: str) -> str:
    return ai_query(
        f"Create a project status report template for: {project}\n\n"
        "## Executive Summary\n"
        "[3 sentences: overall health, key achievement, main risk]\n\n"
        "## Traffic Light Status\n"
        "| Dimension | Status | Notes |\n"
        "| Schedule | 🟢/🟡/🔴 | [explanation] |\n"
        "| Budget | 🟢/🟡/🔴 | [explanation] |\n"
        "| Scope | 🟢/🟡/🔴 | [explanation] |\n"
        "| Quality | 🟢/🟡/🔴 | [explanation] |\n"
        "| Team | 🟢/🟡/🔴 | [explanation] |\n\n"
        "## Accomplishments This Period\n"
        "- [list]\n\n"
        "## Planned for Next Period\n"
        "- [list]\n\n"
        "## Issues and Blockers\n"
        "| Issue | Impact | Owner | Due Date | Status |\n\n"
        "## Key Metrics\n"
        "Progress against KPIs\n\n"
        "## Decisions Needed\n"
        "What does leadership need to decide?\n\n"
        "Fill this template with realistic example content for {project}.",
        SYSTEM_PM,
    )


def cmd_retro(sprint: str) -> str:
    return ai_query(
        f"Facilitate a sprint retrospective for: {sprint}\n\n"
        "## Retrospective Structure (90 minutes)\n\n"
        "### What Went Well (20 min)\n"
        "5-7 positive items to celebrate\n\n"
        "### What Didn't Go Well (20 min)\n"
        "5-7 challenges or problems\n\n"
        "### Root Cause Analysis\n"
        "For top 3 problems: '5 Whys' analysis\n\n"
        "### Action Items (30 min)\n"
        "| Action | Owner | Due Date | Expected Impact |\n"
        "Generate 5-7 specific, measurable improvements\n\n"
        "### Process Improvements\n"
        "2-3 changes to implement next sprint\n\n"
        "### Team Morale Check\n"
        "Questions to gauge team health\n\n"
        "### Sprint Metrics Review\n"
        "Velocity, cycle time, bug rate trends and what they mean",
        SYSTEM_PM,
    )


def cmd_gantt(project: str) -> str:
    return ai_query(
        f"Create a text-based Gantt chart for: {project}\n\n"
        "Use this format:\n"
        "```\n"
        "GANTT CHART: {project}\n"
        "Week:         1  2  3  4  5  6  7  8  9  10 11 12\n"
        "─────────────────────────────────────────────────────\n"
        "Phase 1: Setup\n"
        "  Task 1.1    ██\n"
        "  Task 1.2    ████\n"
        "Phase 2: Build\n"
        "  Task 2.1       ████████\n"
        "  Task 2.2          ██████\n"
        "Milestone 1:          ◆\n"
        "Phase 3: Launch\n"
        "  ...\n"
        "```\n\n"
        "Create a realistic Gantt chart with:\n"
        "- 3-4 phases with 3-5 tasks each\n"
        "- Dependencies shown\n"
        "- Milestones marked with ◆\n"
        "- Critical path tasks marked with *\n\n"
        "Also provide:\n"
        "## Key Dates\n"
        "## Critical Path Explanation\n"
        "## Slack Time Analysis\n"
        "Where is float in the schedule?",
        SYSTEM_PM,
    )


def cmd_standup(updates: str) -> str:
    return ai_query(
        f"Format and analyze this standup update: {updates}\n\n"
        "## Formatted Standup\n"
        "**Yesterday**: [what was completed]\n"
        "**Today**: [what will be done]\n"
        "**Blockers**: [impediments]\n\n"
        "## PM Analysis\n"
        "- Are any tasks at risk?\n"
        "- Are there cross-team dependencies?\n"
        "- What needs immediate attention?\n\n"
        "## Recommended Actions\n"
        "Specific follow-ups for the PM\n\n"
        "## Standup Best Practices Template\n"
        "15-minute standup agenda and facilitation guide",
        SYSTEM_PM,
    )


def cmd_blockers(issue: str) -> str:
    return ai_query(
        f"Help resolve this project blocker: {issue}\n\n"
        "## Blocker Analysis\n"
        "- Type: Technical / Resource / Process / External / Decision\n"
        "- Impact: High/Medium/Low\n"
        "- Time sensitivity: Must resolve by [when]\n\n"
        "## Root Cause\n"
        "Why did this blocker occur?\n\n"
        "## Resolution Options\n"
        "3 ways to resolve the blocker (ranked by speed):\n"
        "1. Fastest (may have tradeoffs): ...\n"
        "2. Best long-term: ...\n"
        "3. Workaround: ...\n\n"
        "## Escalation Recommendation\n"
        "Should this be escalated? To whom? With what ask?\n\n"
        "## Communication Template\n"
        "Message to send to stakeholders about this blocker\n\n"
        "## Prevention\n"
        "How to prevent this type of blocker in future",
        SYSTEM_PM,
    )


def cmd_estimate(task: str) -> str:
    return ai_query(
        f"Estimate effort and complexity for task: {task}\n\n"
        "## Effort Estimation\n"
        "Using 3-point estimation:\n"
        "- Optimistic: X hours (best case)\n"
        "- Most Likely: X hours (normal case)\n"
        "- Pessimistic: X hours (things go wrong)\n"
        "- PERT Estimate: (O + 4M + P) / 6 = X hours\n\n"
        "## Story Points\n"
        "Fibonacci scale (1, 2, 3, 5, 8, 13, 21): [points]\n"
        "Rationale for score\n\n"
        "## Complexity Assessment\n"
        "- Technical complexity: Low/Medium/High\n"
        "- Ambiguity: Low/Medium/High\n"
        "- Dependencies: [list]\n"
        "- Required skills: [list]\n\n"
        "## Risk Factors\n"
        "What could make this take longer than estimated?\n\n"
        "## Breakdown\n"
        "Sub-tasks with individual estimates",
        SYSTEM_PM,
    )


def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "project-manager.queue.jsonl"
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
    result = ai_query(instructions, SYSTEM_PM)
    write_orchestrator_result(subtask_id, result)
    logger.info("project-manager: completed subtask '%s'", subtask_id)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("pm ") and msg_lower != "pm":
        return None

    rest = msg[3:].strip() if msg_lower.startswith("pm ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("start "):
        return cmd_start(rest[6:].strip())
    if rest_lower.startswith("breakdown "):
        return cmd_breakdown(rest[10:].strip())
    if rest_lower.startswith("sprint "):
        parts = rest[7:].strip().split(" duration:", 1)
        goal = parts[0].strip()
        duration = parts[1].strip() if len(parts) > 1 else "2 weeks"
        return cmd_sprint(goal, duration)
    if rest_lower.startswith("roadmap "):
        parts = rest[8:].strip().split(" timeline:", 1)
        project = parts[0].strip()
        timeline = parts[1].strip() if len(parts) > 1 else "6 months"
        return cmd_roadmap(project, timeline)
    if rest_lower.startswith("risks "):
        return cmd_risks(rest[6:].strip())
    if rest_lower.startswith("raci "):
        parts = rest[5:].strip().split(" team:", 1)
        project = parts[0].strip()
        team = parts[1].strip() if len(parts) > 1 else "standard startup team"
        return cmd_raci(project, team)
    if rest_lower.startswith("status "):
        return cmd_status(rest[7:].strip())
    if rest_lower.startswith("retro "):
        return cmd_retro(rest[6:].strip())
    if rest_lower.startswith("gantt "):
        return cmd_gantt(rest[6:].strip())
    if rest_lower.startswith("standup "):
        return cmd_standup(rest[8:].strip())
    if rest_lower.startswith("blockers ") or rest_lower.startswith("blocker "):
        arg = rest[9:].strip() if rest_lower.startswith("blockers ") else rest[8:].strip()
        return cmd_blockers(arg)
    if rest_lower.startswith("estimate "):
        return cmd_estimate(rest[9:].strip())
    if rest_lower == "list" or rest_lower == "projects":
        projects = load_projects()
        if not projects:
            return "No projects yet. Try: `pm start <project>`"
        lines = ["📋 *Projects:*"]
        for p in projects[:8]:
            emoji = {"active": "🟢", "completed": "✅", "paused": "⏸️"}.get(p.get("status", ""), "⚪")
            lines.append(f"  {emoji} `{p['id']}` — {p.get('name','?')[:50]} ({p.get('phase','?')})")
        return "\n".join(lines)
    if rest_lower == "help" or not rest_lower:
        return (
            "📋 *Project Manager Commands:*\n"
            "  `pm start <project>` — kick off project\n"
            "  `pm breakdown <goal>` — work breakdown structure\n"
            "  `pm sprint <goal>` — sprint planning\n"
            "  `pm roadmap <project>` — project roadmap\n"
            "  `pm risks <project>` — risk register\n"
            "  `pm raci <project>` — RACI matrix\n"
            "  `pm status <project>` — status report\n"
            "  `pm retro <sprint>` — retrospective\n"
            "  `pm gantt <project>` — Gantt chart\n"
            "  `pm standup <updates>` — format standup\n"
            "  `pm blockers <issue>` — blocker resolution\n"
            "  `pm estimate <task>` — effort estimation\n"
            "  `pm list` — all projects"
        )

    return "Unknown PM command. Try `pm help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] project-manager started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "project-manager",
                    "message": response,
                })
                logger.info("project-manager: handled command: %s", message[:60])

        projects = load_projects()
        write_state({
            "bot": "project-manager",
            "ts": now_iso(),
            "status": "running",
            "total_projects": len(projects),
            "active_projects": sum(1 for p in projects if p.get("status") == "active"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
