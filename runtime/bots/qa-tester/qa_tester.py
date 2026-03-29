"""QA Tester Bot — Testing strategy, test plans, and quality assurance.

Provides comprehensive quality assurance capabilities:
  - Test plan creation (functional, integration, E2E, performance)
  - Test case generation for features and APIs
  - Bug report templates and severity classification
  - Automated testing strategy (unit, integration, E2E)
  - Performance testing and load test design
  - API testing (Postman/pytest/httpx collections)
  - Accessibility testing (WCAG audit checklists)
  - Security testing (OWASP-based test cases)
  - Test coverage analysis and gap identification
  - Production readiness certification checklist

Commands (via chatlog / WhatsApp / Dashboard):
  qa plan <feature/project>        — create complete test plan
  qa testcases <feature>           — generate test cases for a feature
  qa api <endpoint/description>    — API test cases and collection
  qa bug <description>             — structured bug report template
  qa performance <system>          — performance/load test design
  qa security <system>             — security test cases (OWASP)
  qa accessibility <component>     — WCAG accessibility test checklist
  qa coverage <codebase>           — test coverage analysis and gaps
  qa readiness <project>           — production readiness checklist
  qa automate <test-type>          — automated testing strategy
  qa status                        — current QA projects

State files:
  ~/.ai-employee/state/qa-tester.state.json
  ~/.ai-employee/state/qa-projects.json
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
STATE_FILE = AI_HOME / "state" / "qa-tester.state.json"
PROJECTS_FILE = AI_HOME / "state" / "qa-projects.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("QA_TESTER_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("qa-tester")

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


SYSTEM_QA = (
    "You are a senior QA engineer and test automation specialist. "
    "You design comprehensive test strategies that catch real bugs before users do. "
    "You think adversarially: what can go wrong? what edge cases are missed? "
    "You write test cases in Given/When/Then format (BDD). "
    "You balance thoroughness with pragmatism — not every test is worth writing. "
    "You prioritize: critical user paths first, then risk-based coverage, then happy paths. "
    "Always provide test code examples (pytest/Jest/Playwright). "
    "Default to 'NEEDS WORK' unless evidence proves production readiness."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_plan(feature_or_project: str) -> str:
    return ai_query(
        f"Create a comprehensive test plan for: {feature_or_project}\n\n"
        "## Test Strategy Overview\n"
        "- Scope: what is and isn't being tested\n"
        "- Risk Assessment: highest risk areas and why\n"
        "- Test Levels: unit / integration / E2E / performance / security\n"
        "- Test Types: functional, regression, exploratory, smoke\n\n"
        "## Test Environment Requirements\n"
        "- Environment setup needed\n"
        "- Test data requirements\n"
        "- Tools and frameworks\n\n"
        "## Test Cases Summary\n"
        "List 20+ test scenarios organized by feature area\n\n"
        "## Automation Strategy\n"
        "- What to automate (ROI > manual cost)\n"
        "- What to keep manual\n"
        "- Pipeline integration\n\n"
        "## Entry/Exit Criteria\n"
        "- When testing begins (entry criteria)\n"
        "- When testing is done (exit criteria with metrics)\n\n"
        "## Timeline and Effort\n"
        "Estimated hours by test type",
        SYSTEM_QA,
    )


def cmd_testcases(feature: str) -> str:
    return ai_query(
        f"Generate comprehensive test cases for: {feature}\n\n"
        "## Happy Path Test Cases\n"
        "Format: Given/When/Then for normal successful flows\n\n"
        "## Negative Test Cases\n"
        "Invalid inputs, missing required fields, wrong types, boundary violations\n\n"
        "## Edge Cases\n"
        "Empty states, maximum values, concurrent operations, special characters\n\n"
        "## Error Handling Tests\n"
        "Network failures, timeouts, service unavailability, partial failures\n\n"
        "## Security Test Cases\n"
        "Authentication bypass attempts, injection, authorization boundary tests\n\n"
        "## Test Code Examples\n"
        "Write 3 test cases as actual Python (pytest) or JavaScript (Jest) code",
        SYSTEM_QA,
    )


def cmd_api(endpoint_description: str) -> str:
    return ai_query(
        f"API test cases for: {endpoint_description}\n\n"
        "## Endpoint Inventory\n"
        "List all endpoints to test with methods and paths\n\n"
        "## Functional Tests\n"
        "For each endpoint:\n"
        "- Success cases (200, 201, 204)\n"
        "- Error cases (400, 401, 403, 404, 422, 500)\n"
        "- Request/response schema validation\n\n"
        "## Authentication Tests\n"
        "- No token\n"
        "- Invalid token\n"
        "- Expired token\n"
        "- Wrong permissions\n\n"
        "## Edge Cases\n"
        "- Missing optional fields\n"
        "- Malformed JSON\n"
        "- Very large payloads\n"
        "- Concurrent requests\n\n"
        "## pytest-httpx / requests Test Code\n"
        "Complete working test file with 5+ test functions\n\n"
        "## Postman Collection Structure\n"
        "Folder and request organization for manual testing",
        SYSTEM_QA,
    )


def cmd_bug(description: str) -> str:
    return ai_query(
        f"Create a structured bug report and severity assessment for: {description}\n\n"
        "## Bug Report\n"
        "**Title**: [Concise, searchable title]\n"
        "**Severity**: Critical / High / Medium / Low\n"
        "**Priority**: P1 / P2 / P3 / P4\n"
        "**Severity Rationale**: Why this severity?\n\n"
        "## Reproduction Steps\n"
        "Numbered step-by-step reproduction with exact inputs\n\n"
        "## Expected vs Actual\n"
        "**Expected**: What should happen\n"
        "**Actual**: What actually happens (with error messages)\n\n"
        "## Environment\n"
        "Browser, OS, version, user account type, test data used\n\n"
        "## Impact Assessment\n"
        "- Users affected\n"
        "- Data impact (loss, corruption, exposure)\n"
        "- Workaround available?\n\n"
        "## Root Cause Hypothesis\n"
        "Most likely cause and suggested investigation area\n\n"
        "## Acceptance Criteria for Fix\n"
        "How to verify the bug is resolved",
        SYSTEM_QA,
    )


def cmd_performance(system: str) -> str:
    return ai_query(
        f"Performance and load test design for: {system}\n\n"
        "## Performance Requirements\n"
        "- Target response times (p50, p95, p99)\n"
        "- Throughput targets (requests/second)\n"
        "- Concurrent users (normal, peak)\n"
        "- Error rate threshold\n\n"
        "## Test Scenarios\n"
        "1. **Baseline**: Single user, warm system\n"
        "2. **Load Test**: Expected peak traffic\n"
        "3. **Stress Test**: 2x peak until failure\n"
        "4. **Soak Test**: Sustained load for 4+ hours\n"
        "5. **Spike Test**: Sudden traffic surge\n\n"
        "## k6 / Locust Script\n"
        "Complete working load test script\n\n"
        "## Monitoring During Tests\n"
        "Metrics to watch: CPU, memory, DB connections, error rates\n\n"
        "## Pass/Fail Criteria\n"
        "Specific thresholds that determine test outcome",
        SYSTEM_QA,
    )


def cmd_security(system: str) -> str:
    return ai_query(
        f"Security test cases based on OWASP Top 10 for: {system}\n\n"
        "## OWASP Top 10 Test Coverage\n"
        "For each applicable category, specific test cases:\n\n"
        "**A01 - Broken Access Control**\n"
        "- Horizontal privilege escalation tests\n"
        "- Vertical privilege escalation tests\n"
        "- Direct object reference tests\n\n"
        "**A02 - Cryptographic Failures**\n"
        "- Data transmission tests\n"
        "- Storage encryption tests\n\n"
        "**A03 - Injection**\n"
        "- SQL injection test payloads\n"
        "- Command injection tests\n"
        "- XSS test vectors\n\n"
        "**A04 - Insecure Design**\n"
        "- Business logic abuse tests\n"
        "- Rate limiting bypass tests\n\n"
        "**A07 - Authentication Failures**\n"
        "- Brute force tests\n"
        "- Session management tests\n\n"
        "## Test Tools\n"
        "OWASP ZAP, Burp Suite, or curl commands for each test category\n\n"
        "## Security Test Checklist\n"
        "20-item checklist before production deployment",
        SYSTEM_QA,
    )


def cmd_accessibility(component: str) -> str:
    return ai_query(
        f"WCAG accessibility test checklist for: {component}\n\n"
        "## Automated Tests (axe-core / Lighthouse)\n"
        "Which automated checks to run and expected results\n\n"
        "## Manual Test Cases\n"
        "For each WCAG 2.1 AA criterion:\n"
        "- Test steps\n"
        "- Pass criteria\n"
        "- Common failure patterns\n\n"
        "## Screen Reader Tests\n"
        "Test cases using VoiceOver (macOS), NVDA (Windows), TalkBack (Android)\n\n"
        "## Keyboard Navigation Tests\n"
        "Tab order, focus management, keyboard shortcuts\n\n"
        "## Color Contrast Tests\n"
        "Which elements need contrast verification\n\n"
        "## Mobile Accessibility Tests\n"
        "Touch target sizes, zoom behavior, orientation\n\n"
        "## Pass Criteria\n"
        "Definition of 'accessible enough for release'",
        SYSTEM_QA,
    )


def cmd_coverage(codebase: str) -> str:
    return ai_query(
        f"Test coverage analysis and gap identification for: {codebase}\n\n"
        "## Coverage Assessment\n"
        "- What is currently tested (if described)\n"
        "- Coverage targets: line, branch, function, statement\n\n"
        "## Critical Untested Areas\n"
        "Highest-risk code paths with no test coverage\n\n"
        "## Priority Test Additions\n"
        "Top 10 missing tests ranked by risk × effort:\n"
        "1. [Test name] — [Why critical] — [Effort: hours]\n\n"
        "## Test Debt Assessment\n"
        "Existing tests that are brittle, slow, or poorly written\n\n"
        "## Coverage Improvement Plan\n"
        "4-week plan to reach coverage targets\n\n"
        "## Measurement Commands\n"
        "pytest --cov or jest --coverage commands to measure current coverage",
        SYSTEM_QA,
    )


def cmd_readiness(project: str) -> str:
    return ai_query(
        f"Production readiness certification checklist for: {project}\n\n"
        "## VERDICT: READY / NEEDS WORK (default to NEEDS WORK)\n"
        "State your verdict upfront with key reasons\n\n"
        "## Functional Readiness\n"
        "- [ ] All acceptance criteria have passing tests\n"
        "- [ ] No critical or high severity bugs open\n"
        "- [ ] Edge cases and error states handled\n"
        "- [ ] Data migrations tested and reversible\n\n"
        "## Performance Readiness\n"
        "- [ ] Load tested at 2x expected peak\n"
        "- [ ] Response time SLAs met\n"
        "- [ ] Database query performance verified\n\n"
        "## Security Readiness\n"
        "- [ ] OWASP Top 10 reviewed\n"
        "- [ ] Authentication and authorization tested\n"
        "- [ ] No secrets in code or logs\n\n"
        "## Operational Readiness\n"
        "- [ ] Monitoring and alerting configured\n"
        "- [ ] Runbook written\n"
        "- [ ] Rollback plan tested\n\n"
        "## Required Fixes Before Go-Live\n"
        "Ordered list of blockers",
        SYSTEM_QA,
    )


def cmd_automate(test_type: str) -> str:
    return ai_query(
        f"Automated testing strategy and setup for: {test_type}\n\n"
        "## Framework Selection\n"
        "Best frameworks for this test type with rationale\n\n"
        "## Setup Guide\n"
        "Step-by-step setup: install, configure, first test\n\n"
        "## Test Structure\n"
        "Directory structure and naming conventions\n\n"
        "## Example Tests\n"
        "3-5 working test examples covering common patterns\n\n"
        "## CI/CD Integration\n"
        "GitHub Actions / GitLab CI workflow to run tests on every PR\n\n"
        "## Reporting\n"
        "Test result reporting and failure notification\n\n"
        "## Maintenance Tips\n"
        "How to keep tests from becoming flaky and burdensome",
        SYSTEM_QA,
    )


def cmd_status() -> str:
    projects = load_projects()
    if not projects:
        return "No QA projects recorded yet."
    lines = ["## QA Projects\n"]
    for p in projects[:10]:
        lines.append(f"- [{p.get('type', 'qa')}] {p.get('description', '')[:80]} — {p.get('created_at', '')[:10]}")
    return "\n".join(lines)


# ── Message Routing ────────────────────────────────────────────────────────────

COMMANDS = {
    "qa plan": (cmd_plan, 1),
    "qa testcases": (cmd_testcases, 1),
    "qa api": (cmd_api, 1),
    "qa bug": (cmd_bug, 1),
    "qa performance": (cmd_performance, 1),
    "qa security": (cmd_security, 1),
    "qa accessibility": (cmd_accessibility, 1),
    "qa coverage": (cmd_coverage, 1),
    "qa readiness": (cmd_readiness, 1),
    "qa automate": (cmd_automate, 1),
    "qa status": (lambda: cmd_status(), 0),
}


def process_message(text: str) -> str | None:
    text_lower = text.strip().lower()
    for prefix, (handler, needs_arg) in COMMANDS.items():
        if text_lower.startswith(prefix):
            arg = text[len(prefix):].strip() if needs_arg else ""
            projects = load_projects()
            projects.insert(0, {
                "id": str(uuid.uuid4())[:8],
                "type": prefix.replace("qa ", ""),
                "description": arg[:200],
                "created_at": now_iso(),
            })
            save_projects(projects[:50])
            if needs_arg:
                return handler(arg)
            return handler()
    return None


def process_queue() -> None:
    queue_file = AGENT_TASKS_DIR / "qa-tester.queue.jsonl"
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
                    f"QA Tester could not process: {task.get('input', '')}",
                    status="unhandled",
                )
        remaining.append(json.dumps(task))
    queue_file.write_text("\n".join(remaining) + "\n" if remaining else "")


# ── Main Loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    state = {
        "agent": "qa-tester",
        "started_at": now_iso(),
        "status": "running",
        "last_poll": now_iso(),
    }
    write_state(state)
    logger.info("QA Tester started.")
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
                if role == "user" and text.strip().lower().startswith("qa "):
                    result = process_message(text)
                    if result:
                        append_chatlog({
                            "id": str(uuid.uuid4()),
                            "role": "assistant",
                            "agent": "qa-tester",
                            "text": result,
                            "ts": now_iso(),
                        })
                processed.add(eid)

            state["last_poll"] = now_iso()
            write_state(state)
        except Exception as exc:
            logger.error("QA Tester error: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
