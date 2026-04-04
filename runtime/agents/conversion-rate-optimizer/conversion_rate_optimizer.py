"""ConversionRateOptimizer Bot — Funnel analysis and CRO specialist.

Systematically improves conversion rates across funnels and pages:
  - Funnel leak identification and analysis
  - A/B test design for pages and elements
  - Heatmap and UX analysis recommendations
  - Conversion-optimized copy generation
  - Full CRO audits
  - Quick-win CRO improvements
  - A/B test and conversion stats tracking

Commands (via chatlog / WhatsApp / Dashboard):
  cro analyze <funnel_description>  — analyze funnel for conversion leaks
  cro abtest <page_or_element>      — A/B test design for a page/element
  cro heatmap <page>                — heatmap and UX analysis recommendations
  cro copy <page_type>              — conversion-optimized copy for a page type
  cro audit <product_url>           — full CRO audit
  cro quick-wins <funnel>           — quick-win CRO improvements
  cro status                        — show A/B tests and conversion stats

State files:
  ~/.ai-employee/state/conversion-rate-optimizer.state.json
  ~/.ai-employee/state/cro-tests.json
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
STATE_FILE = AI_HOME / "state" / "conversion-rate-optimizer.state.json"
TESTS_FILE = AI_HOME / "state" / "cro-tests.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("CONVERSION_RATE_OPTIMIZER_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("conversion-rate-optimizer")

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


def load_tests() -> list:
    if not TESTS_FILE.exists():
        return []
    try:
        return json.loads(TESTS_FILE.read_text())
    except Exception:
        return []


def save_tests(tests: list) -> None:
    TESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TESTS_FILE.write_text(json.dumps(tests, indent=2))


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
        result = _query_ai_for_agent("conversion-rate-optimizer", prompt, system_prompt=system_prompt)
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
    queue_file = AGENT_TASKS_DIR / "conversion-rate-optimizer.queue.jsonl"
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
    logger.info("conversion-rate-optimizer: completed subtask '%s'", subtask_id)


SYSTEM_PROMPT = (
    "You are ConversionRateOptimizer, a CRO expert who has boosted conversion rates by 200-500% "
    "for e-commerce and SaaS funnels. You combine user psychology, data analysis, and systematic "
    "A/B testing to find and fix conversion leaks. You understand cognitive biases, persuasion "
    "principles, and which page elements move the needle most."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_analyze(funnel_description: str) -> str:
    return ai_query(
        f"Analyze this funnel for conversion leaks: {funnel_description}\n\n"
        "## Funnel Map\n"
        "Diagram each step with estimated conversion rates:\n"
        "[Step 1] → [CVR%] → [Step 2] → [CVR%] → ... → [Step N]\n\n"
        "## Leak Identification\n"
        "Rank each step by drop-off severity:\n"
        "| Step | Expected CVR | Likely Actual CVR | Gap | Priority |\n"
        "|------|-------------|-------------------|-----|----------|\n"
        "[fill all steps]\n\n"
        "## Root Cause Analysis (Top 3 Leaks)\n"
        "For each leak:\n"
        "- Why users drop off here (psychology + UX)\n"
        "- Evidence signals to look for (heatmaps, session recordings)\n"
        "- Fix hypothesis\n\n"
        "## Friction Inventory\n"
        "Every point of friction in the funnel (cognitive, technical, emotional)\n\n"
        "## Conversion Killers\n"
        "Top 5 elements likely hurting conversions most\n\n"
        "## Revenue Impact\n"
        "If top leak is fixed by 20%, what's the revenue uplift?\n\n"
        "## Optimization Roadmap\n"
        "Prioritized list of fixes by ICE score",
        SYSTEM_PROMPT,
    )


def cmd_abtest(page_or_element: str) -> str:
    tests = load_tests()
    result = ai_query(
        f"Design A/B tests for: {page_or_element}\n\n"
        "## Test Prioritization\n"
        "Elements ranked by conversion impact potential\n\n"
        "## 10 A/B Test Designs\n"
        "For each test:\n"
        "- **Test name**: [descriptive]\n"
        "- **Element**: [what to change]\n"
        "- **Hypothesis**: If we [change], conversion will [improve by X%] because [reason]\n"
        "- **Control (A)**: [current state]\n"
        "- **Variant (B)**: [new state — be specific]\n"
        "- **Primary metric**: [CVR / CTR / AOV]\n"
        "- **Guardrail metrics**: [metrics that shouldn't drop]\n"
        "- **ICE Score**: Impact [/10], Confidence [/10], Ease [/10] = [total]\n"
        "- **Sample size**: [needed per variant]\n"
        "- **Duration**: [days at typical traffic]\n\n"
        "## Testing Sequence\n"
        "Order to run tests for maximum learnings\n\n"
        "## Multivariate Opportunities\n"
        "Where to run MVT instead of A/B\n\n"
        "## Statistical Significance Guide\n"
        "How to call a winner confidently",
        SYSTEM_PROMPT,
    )
    test_entry = {
        "id": str(uuid.uuid4())[:8],
        "element": page_or_element,
        "created_at": now_iso(),
        "status": "designed",
    }
    tests.insert(0, test_entry)
    save_tests(tests[:100])
    return result


def cmd_heatmap(page: str) -> str:
    return ai_query(
        f"Provide heatmap and UX analysis recommendations for: {page}\n\n"
        "## Heatmap Analysis Framework\n"
        "What to look for in:\n"
        "- Click maps: [key patterns]\n"
        "- Scroll maps: [fold analysis]\n"
        "- Move maps: [attention indicators]\n\n"
        "## Expected Patterns for This Page Type\n"
        f"For a {page}, typical heatmap reveals:\n"
        "- Where attention concentrates\n"
        "- Common scroll depth patterns\n"
        "- Rage-click hotspots to watch\n\n"
        "## UX Issues to Investigate\n"
        "10 common UX problems for this page type\n\n"
        "## Session Recording Analysis\n"
        "What to watch for in Hotjar/FullStory recordings\n\n"
        "## Cognitive Load Assessment\n"
        "How to measure and reduce cognitive load on this page\n\n"
        "## Attention Hierarchy\n"
        "Ideal F-pattern or Z-pattern for this page\n\n"
        "## Mobile UX Review\n"
        "Mobile-specific issues to fix\n\n"
        "## Fixes Ranked by Impact\n"
        "10 UX changes based on typical heatmap findings",
        SYSTEM_PROMPT,
    )


def cmd_copy(page_type: str) -> str:
    return ai_query(
        f"Write conversion-optimized copy for a {page_type}\n\n"
        "## Copywriting Framework\n"
        f"Best persuasion framework for {page_type}: [AIDA/PAS/BAB/etc.]\n\n"
        "## Full Page Copy\n\n"
        "**Headline (5 variants):**\n"
        "[clear, compelling, outcome-focused]\n\n"
        "**Subheadline:**\n"
        "[supports headline, adds specificity]\n\n"
        "**Hero Section Body:**\n"
        "[2-3 sentences max]\n\n"
        "**Value Propositions (3):**\n"
        "Feature → Benefit → Outcome format\n\n"
        "**Social Proof Section:**\n"
        "[testimonial formats and placement]\n\n"
        "**Objection Handlers:**\n"
        "3 FAQ entries that eliminate friction\n\n"
        "**CTA (5 variants):**\n"
        "[action-oriented, benefit-clear]\n\n"
        "## Psychological Triggers Used\n"
        "Which cognitive biases are activated and where\n\n"
        "## Copy Testing Plan\n"
        "Which copy elements to A/B test first",
        SYSTEM_PROMPT,
    )


def cmd_audit(product_url: str) -> str:
    tests = load_tests()
    result = ai_query(
        f"Conduct a full CRO audit for: {product_url}\n\n"
        "## CRO Audit Score (0–100)\n"
        "| Category | Score | Key Issues |\n"
        "|----------|-------|------------|\n"
        "Value proposition clarity | /20 | [issues]\n"
        "Trust and credibility | /20 | [issues]\n"
        "UX and friction | /20 | [issues]\n"
        "Copy and messaging | /20 | [issues]\n"
        "CTA effectiveness | /20 | [issues]\n"
        "**Total**: /100\n\n"
        "## Critical Findings (Top 5)\n"
        "Issues costing the most conversions, with estimated impact\n\n"
        "## Benchmark Comparison\n"
        "Industry conversion rate benchmarks for this type of site\n\n"
        "## Quick Wins (fix in <1 day)\n"
        "5 high-impact, low-effort changes\n\n"
        "## Strategic Improvements (1-4 weeks)\n"
        "Deeper changes with bigger potential upside\n\n"
        "## A/B Test Roadmap\n"
        "First 10 tests to run in priority order\n\n"
        "## Expected Uplift\n"
        "Conversion rate improvement if all recommendations implemented",
        SYSTEM_PROMPT,
    )
    audit_entry = {
        "id": str(uuid.uuid4())[:8],
        "url": product_url,
        "created_at": now_iso(),
        "status": "audited",
    }
    tests.insert(0, audit_entry)
    save_tests(tests[:100])
    return result


def cmd_quick_wins(funnel: str) -> str:
    return ai_query(
        f"Identify quick-win CRO improvements for funnel: {funnel}\n\n"
        "## Quick Win Criteria\n"
        "Changes that take <4 hours to implement and move the needle\n\n"
        "## Top 15 Quick Wins (ICE scored)\n"
        "For each:\n"
        "- **Change**: [exactly what to do]\n"
        "- **Where**: [page/element]\n"
        "- **Time to implement**: [hours]\n"
        "- **Expected CVR lift**: [X%]\n"
        "- **ICE Score**: I[/10] C[/10] E[/10] = [total]\n\n"
        "## Highest ROI Quick Win\n"
        "The single change with best effort-to-return ratio\n\n"
        "## Copy Quick Wins\n"
        "5 headline/CTA changes to make today\n\n"
        "## Technical Quick Wins\n"
        "5 technical fixes (page speed, mobile, forms)\n\n"
        "## Trust Quick Wins\n"
        "5 credibility signals to add immediately\n\n"
        "## Implementation Order\n"
        "Exactly which order to implement for compounding effect",
        SYSTEM_PROMPT,
    )


def cmd_status() -> str:
    tests = load_tests()
    if not tests:
        return "No CRO tests tracked yet. Try: `cro abtest <page_or_element>`"
    lines = ["📈 *ConversionRateOptimizer — Test Stats:*"]
    lines.append(f"  Total tests/audits: {len(tests)}")
    running = sum(1 for t in tests if t.get("status") == "running")
    won = sum(1 for t in tests if t.get("status") == "won")
    lines.append(f"  Running: {running} | Winners: {won} | Designed: {len(tests) - running - won}")
    lines.append("\n*Recent tests:*")
    for t in tests[:5]:
        name = t.get("element", t.get("url", "?"))
        lines.append(f"  • `{t.get('id','?')}` — {str(name)[:50]} ({t.get('status','?')})")
    return "\n".join(lines)


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("cro ") and msg_lower != "cro":
        return None

    rest = msg[4:].strip() if msg_lower.startswith("cro ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("analyze "):
        return cmd_analyze(rest[8:].strip())
    if rest_lower.startswith("abtest "):
        return cmd_abtest(rest[7:].strip())
    if rest_lower.startswith("heatmap "):
        return cmd_heatmap(rest[8:].strip())
    if rest_lower.startswith("copy "):
        return cmd_copy(rest[5:].strip())
    if rest_lower.startswith("audit "):
        return cmd_audit(rest[6:].strip())
    if rest_lower.startswith("quick-wins "):
        return cmd_quick_wins(rest[11:].strip())
    if rest_lower == "status":
        return cmd_status()
    if rest_lower == "help" or not rest_lower:
        return (
            "📈 *ConversionRateOptimizer Commands:*\n"
            "  `cro analyze <funnel_description>` — funnel leak analysis\n"
            "  `cro abtest <page_or_element>` — A/B test design\n"
            "  `cro heatmap <page>` — heatmap and UX analysis\n"
            "  `cro copy <page_type>` — conversion-optimized copy\n"
            "  `cro audit <product_url>` — full CRO audit\n"
            "  `cro quick-wins <funnel>` — quick-win improvements\n"
            "  `cro status` — A/B tests and conversion stats"
        )

    return "Unknown cro command. Try `cro help`"


def main() -> None:
    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(f"[{now_iso()}] conversion-rate-optimizer started; poll_interval={POLL_INTERVAL}s; {ai_status}")

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
                    "bot": "conversion-rate-optimizer",
                    "message": response,
                })
                logger.info("conversion-rate-optimizer: handled command: %s", message[:60])

        tests = load_tests()
        write_state({
            "bot": "conversion-rate-optimizer",
            "ts": now_iso(),
            "status": "running",
            "total_tests": len(tests),
            "running_tests": sum(1 for t in tests if t.get("status") == "running"),
            "winning_tests": sum(1 for t in tests if t.get("status") == "won"),
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
