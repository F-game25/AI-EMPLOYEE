"""HR Manager Bot — Full HR pipeline: hiring, onboarding, and org design.

Automates the complete HR lifecycle:
  - Job description writing
  - Candidate sourcing strategy
  - CV/resume screening with AI scoring
  - Interview question generation
  - Onboarding plan creation
  - Performance review templates
  - Org chart design
  - Compensation benchmarking
  - Culture documents (values, handbooks)
  - Employment contract templates

Commands (via chatlog / WhatsApp / Dashboard):
  hr hire <role>                   — full hiring package for a role
  hr jd <role> <requirements>      — write job description
  hr screen <cv_text>              — AI CV screening and score
  hr interview <role>              — interview questions pack
  hr onboard <role>                — 90-day onboarding plan
  hr review <role>                 — performance review template
  hr org <company_type> <size>     — org chart design
  hr compensation <role> <location> — salary benchmarking
  hr handbook <company_name>       — employee handbook outline
  hr culture <company_name>        — company values and culture doc
  hr status                        — HR pipeline overview

State files:
  ~/.ai-employee/state/hr-manager.state.json
  ~/.ai-employee/state/hr-pipeline.json
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
STATE_FILE = AI_HOME / "state" / "hr-manager.state.json"
PIPELINE_FILE = AI_HOME / "state" / "hr-pipeline.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("HR_MANAGER_POLL_INTERVAL", "5"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("hr-manager")

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


def load_pipeline() -> list:
    if not PIPELINE_FILE.exists():
        return []
    try:
        return json.loads(PIPELINE_FILE.read_text())
    except Exception:
        return []


def save_pipeline(pipeline: list) -> None:
    PIPELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_FILE.write_text(json.dumps(pipeline, indent=2))


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


SYSTEM_HR = (
    "You are a senior HR Director with 15+ years of experience at top companies. "
    "You create practical, professional HR documents and processes that attract talent "
    "and build great company cultures. Be specific, actionable, and modern."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_jd(role: str, requirements: str = "") -> str:
    req_text = f"\nRequirements: {requirements}" if requirements else ""
    return ai_query(
        f"Write a compelling job description for: {role}{req_text}\n\n"
        "Include:\n"
        "**Job Title:** [exact title]\n"
        "**Location:** [Remote/Hybrid/On-site]\n"
        "**Employment Type:** [Full-time/Part-time/Contract]\n\n"
        "**About the Role** (3-4 sentences describing the opportunity)\n\n"
        "**What You'll Do** (8-10 bullet points of key responsibilities)\n\n"
        "**What We're Looking For** (7-8 bullet points of requirements)\n\n"
        "**Nice to Have** (4-5 bonus skills)\n\n"
        "**What We Offer** (benefits, growth, culture — 6-8 points)\n\n"
        "**How to Apply** (process and expected timeline)\n\n"
        "Write in an engaging, modern tone that attracts top talent. "
        "Avoid jargon and focus on impact.",
        SYSTEM_HR,
    )


def cmd_screen(cv_text: str) -> str:
    return ai_query(
        f"Screen and score this CV/resume:\n\n{cv_text}\n\n"
        "Evaluate on:\n"
        "1. **Overall Score** (0-100): [score] — [one-line summary]\n\n"
        "2. **Experience Match** (0-25): [score]\n"
        "   - Strengths: ...\n"
        "   - Gaps: ...\n\n"
        "3. **Skills Match** (0-25): [score]\n"
        "   - Matching skills: ...\n"
        "   - Missing skills: ...\n\n"
        "4. **Career Progression** (0-25): [score]\n"
        "   - Assessment: ...\n\n"
        "5. **Cultural Fit Indicators** (0-25): [score]\n"
        "   - Positive signals: ...\n"
        "   - Concerns: ...\n\n"
        "6. **Red Flags**: [list any]\n\n"
        "7. **Top 3 Strengths**\n\n"
        "8. **Top 3 Questions to Ask in Interview**\n\n"
        "9. **Recommendation**: Advance / Hold / Reject\n"
        "   **Rationale**: [2-3 sentences]",
        SYSTEM_HR,
    )


def cmd_interview(role: str) -> str:
    return ai_query(
        f"Create a complete interview question pack for: {role}\n\n"
        "## Round 1: Phone Screen (15-20 min)\n"
        "5 questions to quickly qualify candidates\n\n"
        "## Round 2: Technical/Skills Assessment\n"
        "8-10 role-specific questions with what good answers look like\n\n"
        "## Round 3: In-Depth Interview\n"
        "**Behavioral Questions** (STAR format, 5 questions):\n"
        "**Situational Questions** (5 questions):\n"
        "**Role-Specific Questions** (5 questions):\n\n"
        "## Culture Fit Questions (5)\n\n"
        "## Questions Candidate May Ask\n"
        "- 5 great questions a strong candidate might ask\n"
        "- How to answer each one impressively\n\n"
        "## Scoring Rubric\n"
        "- 3 dimensions to score (1-5 scale)\n"
        "- What score thresholds mean\n\n"
        "For each question: what you're really evaluating.",
        SYSTEM_HR,
    )


def cmd_onboard(role: str) -> str:
    return ai_query(
        f"Create a 90-day onboarding plan for a new {role}.\n\n"
        "## Week 1: Orientation & Setup\n"
        "Day-by-day plan:\n"
        "- Day 1: [specific activities]\n"
        "- Day 2-5: [activities]\n"
        "Key deliverables by end of week 1\n\n"
        "## Month 1 (Days 1-30): Learning & Observation\n"
        "- Goals and learning objectives\n"
        "- Key people to meet\n"
        "- Systems and tools to master\n"
        "- 30-day check-in questions\n\n"
        "## Month 2 (Days 31-60): Contributing\n"
        "- First independent deliverables\n"
        "- Ownership areas\n"
        "- 60-day check-in template\n\n"
        "## Month 3 (Days 61-90): Impact\n"
        "- Full performance expectations\n"
        "- First mini-projects\n"
        "- 90-day review template\n\n"
        "## Resources Checklist\n"
        "- Tools to set up\n"
        "- Documents to read\n"
        "- Training to complete\n\n"
        "## Success Metrics\n"
        "How to measure if onboarding was successful",
        SYSTEM_HR,
    )


def cmd_review(role: str) -> str:
    return ai_query(
        f"Create a performance review template for: {role}\n\n"
        "## Self-Assessment Section\n"
        "5 questions for the employee to answer\n\n"
        "## Manager Assessment Section\n"
        "**Performance Dimensions** (rate 1-5 with comments):\n"
        "1. Quality of Work\n"
        "2. Productivity & Output\n"
        "3. Communication\n"
        "4. Teamwork & Collaboration\n"
        "5. Initiative & Problem-Solving\n"
        "6. Role-Specific Skills\n"
        "7. Culture & Values Alignment\n\n"
        "**Achievements This Period** (3-5 specific accomplishments)\n\n"
        "**Areas for Development** (2-3 with action plans)\n\n"
        "**Goals for Next Period** (3-5 SMART goals)\n\n"
        "## Rating Scale\n"
        "1 = Needs Improvement, 5 = Exceptional\n"
        "Descriptions for each level\n\n"
        "## Compensation Review\n"
        "Criteria for raises/bonuses based on scores\n\n"
        "## Development Plan\n"
        "Training, mentoring, and growth opportunities",
        SYSTEM_HR,
    )


def cmd_org(company_type: str, size: str) -> str:
    return ai_query(
        f"Design an org chart for a {size}-person {company_type} company.\n\n"
        "Provide:\n"
        "## Org Chart (ASCII/text diagram)\n"
        "Show reporting lines and department structure\n\n"
        "## Departments & Functions\n"
        "For each department:\n"
        "- Department name and purpose\n"
        "- Roles included\n"
        "- Key responsibilities\n"
        "- Headcount at current stage\n\n"
        "## Role Descriptions (key roles)\n"
        "For top 5 most critical roles:\n"
        "- Title, level, scope\n"
        "- Direct reports (if any)\n"
        "- Key performance metrics\n\n"
        "## Hiring Roadmap\n"
        "Next 5 hires in priority order with justification\n\n"
        "## Compensation Structure\n"
        "Salary bands by level (Junior/Mid/Senior/Lead/Manager/Director)\n\n"
        "## Equity Structure\n"
        "Recommended option pool allocation by role level",
        SYSTEM_HR,
    )


def cmd_compensation(role: str, location: str = "global") -> str:
    return ai_query(
        f"Provide compensation benchmarking for: {role} in {location}\n\n"
        "Include:\n"
        "## Base Salary Ranges\n"
        "- Junior level: $X - $X\n"
        "- Mid level: $X - $X\n"
        "- Senior level: $X - $X\n"
        "- Lead/Staff level: $X - $X\n"
        "- Manager level: $X - $X\n\n"
        "## Total Compensation\n"
        "- Typical bonus ranges (% of base)\n"
        "- Equity/stock expectations by stage (startup vs public)\n"
        "- Benefits market standard\n\n"
        "## Location Adjustments\n"
        "- Remote vs major cities comparison\n"
        "- Cost of living multipliers\n\n"
        "## Market Trends\n"
        "- Is this role in demand?\n"
        "- Expected salary growth\n"
        "- Competition for talent\n\n"
        "## Offer Strategy\n"
        "- How to structure a competitive offer\n"
        "- Common negotiation points\n"
        "- How to compete without highest salary",
        SYSTEM_HR,
    )


def cmd_handbook(company_name: str) -> str:
    return ai_query(
        f"Create an employee handbook outline for {company_name}.\n\n"
        "Sections:\n"
        "1. **Welcome & Company Story**\n"
        "2. **Mission, Vision & Values**\n"
        "3. **Employment Policies** (at-will, equal opportunity, etc.)\n"
        "4. **Working Hours & Flexibility**\n"
        "5. **Compensation & Benefits**\n"
        "6. **Time Off & Leave Policies**\n"
        "7. **Performance & Development**\n"
        "8. **Code of Conduct**\n"
        "9. **Communication Guidelines**\n"
        "10. **Remote Work Policy**\n"
        "11. **Technology & Security**\n"
        "12. **Health & Safety**\n"
        "13. **Disciplinary Procedures**\n"
        "14. **Offboarding Process**\n\n"
        "For each section: key points to cover, example policies, and modern best practices. "
        "Write in a friendly, accessible tone that employees will actually read.",
        SYSTEM_HR,
    )


def cmd_culture(company_name: str) -> str:
    return ai_query(
        f"Create a company culture and values document for {company_name}.\n\n"
        "Include:\n"
        "## Core Values (5-7)\n"
        "For each value:\n"
        "- Name and one-line definition\n"
        "- What it looks like in practice (3 examples)\n"
        "- What it doesn't look like (anti-patterns)\n"
        "- How we hire for it\n\n"
        "## Culture Principles\n"
        "How we work together, make decisions, and communicate\n\n"
        "## Leadership Principles\n"
        "What we expect from managers\n\n"
        "## Team Norms\n"
        "Meeting culture, async vs sync, feedback norms\n\n"
        "## Diversity, Equity & Inclusion\n"
        "Commitments and practices\n\n"
        "## How We Recognize People\n"
        "Recognition programs and appreciation practices\n\n"
        "Make it authentic, memorable, and truly differentiating.",
        SYSTEM_HR,
    )


def cmd_hire(role: str) -> str:
    """Full hiring package combining JD + interview guide + onboarding."""
    system = (
        "You are a world-class HR Director. Create a complete, ready-to-use hiring "
        "package that covers everything from job posting to first 30 days."
    )
    return ai_query(
        f"Create a complete hiring package for: {role}\n\n"
        "## 1. JOB DESCRIPTION (ready to post)\n"
        "Full job description with responsibilities, requirements, and benefits\n\n"
        "## 2. SOURCING STRATEGY\n"
        "Where to find candidates, what to say, cost estimates\n\n"
        "## 3. SCREENING CRITERIA\n"
        "Must-haves vs nice-to-haves, deal-breakers\n\n"
        "## 4. INTERVIEW PROCESS\n"
        "Number of rounds, who interviews, what to assess each round\n\n"
        "## 5. TOP 10 INTERVIEW QUESTIONS\n"
        "With what you're looking for in each answer\n\n"
        "## 6. OFFER PACKAGE\n"
        "Competitive compensation structure with negotiation room\n\n"
        "## 7. 30-DAY QUICK-START PLAN\n"
        "First month priorities for the new hire\n\n"
        "Be specific and immediately actionable.",
        system,
    )


def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "hr-manager.queue.jsonl"
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
    result = ai_query(instructions, SYSTEM_HR)
    write_orchestrator_result(subtask_id, result)
    logger.info("hr-manager: completed subtask '%s'", subtask_id)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("hr ") and msg_lower != "hr":
        return None

    rest = msg[3:].strip() if msg_lower.startswith("hr ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("hire "):
        return cmd_hire(rest[5:].strip())
    if rest_lower.startswith("jd "):
        parts = rest[3:].strip().split(" requirements:", 1)
        role = parts[0].strip()
        req = parts[1].strip() if len(parts) > 1 else ""
        return cmd_jd(role, req)
    if rest_lower.startswith("screen "):
        return cmd_screen(rest[7:].strip())
    if rest_lower.startswith("interview "):
        return cmd_interview(rest[10:].strip())
    if rest_lower.startswith("onboard "):
        return cmd_onboard(rest[8:].strip())
    if rest_lower.startswith("review "):
        return cmd_review(rest[7:].strip())
    if rest_lower.startswith("org "):
        parts = rest[4:].strip().split(" ", 1)
        company_type = parts[0]
        size = parts[1] if len(parts) > 1 else "10"
        return cmd_org(company_type, size)
    if rest_lower.startswith("compensation "):
        parts = rest[13:].strip().split(" in ", 1)
        role = parts[0].strip()
        location = parts[1].strip() if len(parts) > 1 else "global"
        return cmd_compensation(role, location)
    if rest_lower.startswith("handbook "):
        return cmd_handbook(rest[9:].strip())
    if rest_lower.startswith("culture "):
        return cmd_culture(rest[8:].strip())
    if rest_lower == "status":
        pipeline = load_pipeline()
        return f"👔 HR Pipeline: {len(pipeline)} active roles. Use `hr hire <role>` to get started."
    if rest_lower == "help" or not rest_lower:
        return (
            "👔 *HR Manager Commands:*\n"
            "  `hr hire <role>` — full hiring package\n"
            "  `hr jd <role>` — job description\n"
            "  `hr screen <cv>` — CV screening score\n"
            "  `hr interview <role>` — interview questions\n"
            "  `hr onboard <role>` — 90-day onboarding plan\n"
            "  `hr review <role>` — performance review template\n"
            "  `hr org <type> <size>` — org chart design\n"
            "  `hr compensation <role> in <location>` — salary benchmark\n"
            "  `hr handbook <company>` — employee handbook\n"
            "  `hr culture <company>` — culture & values doc"
        )

    return "Unknown HR command. Try `hr help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] hr-manager started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "hr-manager",
                    "message": response,
                })
                logger.info("hr-manager: handled command: %s", message[:60])

        pipeline = load_pipeline()
        write_state({
            "bot": "hr-manager",
            "ts": now_iso(),
            "status": "running",
            "pipeline_count": len(pipeline),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
